"""
Gemini-powered company/board discovery — automates the periodic research
pass that manually found Allego, GreenFlux, Eneco eMobility, and Zoomo
(see README's "Verified target companies"). Needs GEMINI_API_KEY (the
same free-tier key llm_client.py's Gemini backend uses) since Gemini's
search-grounding tool isn't available through Ollama.

Never writes directly to config.py, and never trusts the LLM's slug/URL
guess: every candidate is independently verified by actually calling the
real ATS endpoint (via connectors.py's own fetch functions) and confirming
it returns real postings before being reported. A "found" company with a
hallucinated slug that returns nothing is reported as unverified, not
silently dropped — so a near-miss is still visible for manual follow-up.
Even a verified hit is a suggestion for a human to review and add to
config.py, matching how every existing board token there carries a
confidence note from actual verification, not a blind guess.

Usage:
    python -m job_intel_scraper.company_discovery --countries VN NL AU
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

import requests

from . import connectors

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Short sector hints per country, drawn from build-prompt.md's target-
# jurisdiction descriptions — kept here rather than reused from
# config.py's `visa_note` field, which is long prose written for a human
# reader, not a compact list suited to a search prompt.
_SECTOR_HINTS: dict[str, str] = {
    "VN": (
        "automotive OEM/Tier-1 joint ventures, EV vehicle manufacturers or "
        "scale-ups, automotive component/parts manufacturers"
    ),
    "NL": (
        "EV charging infrastructure, automotive Tier-1 suppliers, electric "
        "vehicle manufacturers, mobility-as-a-service, automotive engineering "
        "consultancies"
    ),
    "AU": (
        "mining and heavy-equipment OEMs, rail rolling stock manufacturers, "
        "EV or automotive-adjacent scale-ups, industrial/general manufacturing "
        "program management, infrastructure and engineering program-delivery "
        "consultancies"
    ),
}

DISCOVERY_PROMPT_TEMPLATE = """Search the web for companies that meet ALL of these criteria:
1. Based in or actively hiring for roles located in {country_name}.
2. In one of these sectors: {sectors}.
3. Use one of these four applicant tracking systems for their careers page — Greenhouse \
(boards.greenhouse.io or job-boards.greenhouse.io), Lever (jobs.lever.co), Workable \
(apply.workable.com), or Recruitee (<company>.recruitee.com, or a custom domain whose careers \
page credits/is built on Recruitee).

For each company you find ACTUAL EVIDENCE for (a real URL you found in search results, not a \
plausible-looking guess), respond with a JSON array (no markdown fences, no commentary) of \
objects shaped exactly like:
{{"company": "<name>", "platform": "greenhouse|lever|workable|recruitee", \
"slug_or_url": "<the board token, company slug, account slug, or full URL you found>", \
"evidence": "<briefly, what you found and where>"}}

Only include a company if you found real evidence in actual search results. If you find none \
meeting all three criteria, respond with an empty JSON array: []
"""


@dataclass
class DiscoveredCandidate:
    company: str
    platform: str
    slug_or_url: str
    evidence: str


@dataclass
class VerifiedCandidate:
    candidate: DiscoveredCandidate
    verified: bool
    job_count: int
    note: str


def _call_gemini_with_search(prompt: str, api_key: str, model: str = "gemini-2.5-flash") -> str:
    url = GEMINI_API_URL.format(model=model)
    resp = requests.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _parse_candidates(text: str) -> list[DiscoveredCandidate]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return []

    candidates: list[DiscoveredCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            candidates.append(DiscoveredCandidate(
                company=str(item["company"]),
                platform=str(item["platform"]).lower().strip(),
                slug_or_url=str(item["slug_or_url"]).strip(),
                evidence=str(item.get("evidence", "")),
            ))
        except KeyError:
            continue
    return candidates


def _extract_slug(candidate: DiscoveredCandidate) -> str:
    """Candidates may come back as a bare slug or a full URL — normalize to
    what connectors.py expects (a board token/slug, or for Recruitee, a
    custom domain host when the URL isn't the default <slug>.recruitee.com)."""
    value = candidate.slug_or_url
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/")[0] if candidate.platform == "recruitee" and "." in value.split("/")[0] else value.rstrip("/")

    if candidate.platform == "recruitee":
        if value.endswith(".recruitee.com"):
            return value[: -len(".recruitee.com")]
        return value  # custom domain — caller passes it through as `host`
    # greenhouse/lever/workable: take the last path segment as the slug
    return value.rstrip("/").split("/")[-1]


def verify_candidate(candidate: DiscoveredCandidate) -> VerifiedCandidate:
    """Never trust the LLM's slug guess — actually call the real ATS
    endpoint and see if it returns real job postings. country_hint="XX" is
    a placeholder; verification doesn't need a real jurisdiction code since
    this bypasses fetch_all()'s location filter entirely to check the raw
    endpoint response."""
    slug = _extract_slug(candidate)
    try:
        if candidate.platform == "greenhouse":
            jobs = connectors.fetch_greenhouse_board(slug, "XX")
        elif candidate.platform == "lever":
            jobs = connectors.fetch_lever_board(slug, "XX")
        elif candidate.platform == "workable":
            jobs = connectors.fetch_workable_board(slug, "XX")
        elif candidate.platform == "recruitee":
            if "." in slug:  # a custom domain, not a bare slug
                jobs = connectors.fetch_recruitee_board(slug.split(".")[0], "XX", host=slug)
            else:
                jobs = connectors.fetch_recruitee_board(slug, "XX")
        else:
            return VerifiedCandidate(candidate, False, 0, f"Unknown platform {candidate.platform!r}")
    except Exception as exc:  # noqa: BLE001 - a failed guess is an expected, normal outcome here
        return VerifiedCandidate(candidate, False, 0, f"Could not verify (slug guessed as {slug!r}): {exc}")

    if not jobs:
        return VerifiedCandidate(candidate, False, 0, f"Endpoint responded (slug {slug!r}) but returned zero postings.")
    return VerifiedCandidate(candidate, True, len(jobs), f"VERIFIED live — {len(jobs)} posting(s) found (slug: {slug!r}).")


def discover_and_verify(country_code: str, api_key: str) -> list[VerifiedCandidate]:
    from .config import JURISDICTIONS  # local import: avoids a cycle with connectors at module load

    jurisdiction = JURISDICTIONS[country_code]
    sectors = _SECTOR_HINTS.get(country_code, "")
    prompt = DISCOVERY_PROMPT_TEMPLATE.format(country_name=jurisdiction.name, sectors=sectors)

    raw_text = _call_gemini_with_search(prompt, api_key)
    candidates = _parse_candidates(raw_text)
    return [verify_candidate(c) for c in candidates]


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini-powered company/board discovery")
    parser.add_argument("--countries", nargs="+", choices=["VN", "NL", "AU"], default=["VN", "NL", "AU"])
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "GEMINI_API_KEY is not set — discovery needs Gemini's search-grounding tool, "
            "which Ollama doesn't have. Get a free key at https://aistudio.google.com/apikey "
            "and set it before running this.",
            file=sys.stderr,
        )
        sys.exit(1)

    for code in args.countries:
        print(f"\n=== Discovery: {code} ===")
        results = discover_and_verify(code, api_key)
        if not results:
            print("  No candidates returned.")
            continue
        for r in results:
            status = "VERIFIED" if r.verified else "unverified"
            print(f"  [{status}] {r.candidate.company} — {r.candidate.platform} — {r.note}")
        verified = [r for r in results if r.verified]
        print(f"  {len(verified)}/{len(results)} candidate(s) verified live.")
        if verified:
            print("  Add to config.py manually after reviewing sector fit:")
            for r in verified:
                slug = _extract_slug(r.candidate)
                print(f"    {r.candidate.platform}: {slug!r}  ({r.candidate.company})")


if __name__ == "__main__":
    main()
