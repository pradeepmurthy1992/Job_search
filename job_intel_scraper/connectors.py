"""
Discovery-layer connectors. Greenhouse, Lever, Workable, and Recruitee all
expose public, documented, robots-friendly JSON APIs for their job boards,
which makes them the right first set to implement — no HTML scraping, no
anti-bot fingerprinting needed. Everything else in the platform overview's
"20+ ATS" list (Workday, SmartRecruiters, iCIMS, Taleo, SuccessFactors,
bespoke career sites) follows the same pattern: one function that returns a
list of normalized Job dicts, gated by robots_check first.

Workable and Recruitee were added after real research turned up companies
that actually use them (Applied EV on Workable, Fastned on Recruitee) —
Greenhouse and Lever alone came up close to empty across Vietnam,
Netherlands, and Australia searches, so restricting discovery to just those
two would have meant covering almost nothing in these three markets.

This module intentionally does NOT include the local job-board scrapers
(Seek, Indeed.nl, VietnamWorks, etc.) — those typically require either a
partner API agreement or careful, individually-reviewed HTML parsing, and
each one's robots.txt / ToS needs to be checked on its own before writing a
scraper against it. They're listed in config.py as a checklist, not stubbed
here, so nothing gets silently built without that review happening first.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any

import requests

from . import robots_check

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
LEVER_API = "https://api.lever.co/v0/postings/{company}"
WORKABLE_API = "https://apply.workable.com/api/v1/widget/accounts/{account}"
RECRUITEE_API = "https://{company}.recruitee.com/api/offers/"

REQUEST_TIMEOUT = 20


@dataclass
class Job:
    source: str            # "greenhouse" | "lever" | "workable" | "recruitee"
    board_or_company: str
    external_id: str
    title: str
    location_raw: str
    url: str
    description_raw: str
    country_hint: str      # which JurisdictionProfile this was fetched for
    fetched_at: float


def fetch_greenhouse_board(board_token: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Greenhouse board (content=true pulls
    full HTML job descriptions in one call, avoiding a second request per job)."""
    url = GREENHOUSE_API.format(board=board_token) + "?content=true"
    robots_check.assert_allowed(url, target_label=f"greenhouse:{board_token}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data.get("jobs", []):
        jobs.append(
            Job(
                source="greenhouse",
                board_or_company=board_token,
                external_id=str(posting.get("id")),
                title=posting.get("title", ""),
                location_raw=(posting.get("location") or {}).get("name", ""),
                url=posting.get("absolute_url", ""),
                description_raw=posting.get("content", "") or "",
                country_hint=country_hint,
                fetched_at=time.time(),
            )
        )
    robots_check.polite_delay()
    return jobs


def fetch_lever_board(company_slug: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Lever company board."""
    url = LEVER_API.format(company=company_slug) + "?mode=json"
    robots_check.assert_allowed(url, target_label=f"lever:{company_slug}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data:
        categories = posting.get("categories", {}) or {}
        jobs.append(
            Job(
                source="lever",
                board_or_company=company_slug,
                external_id=str(posting.get("id")),
                title=posting.get("text", ""),
                location_raw=categories.get("location", ""),
                url=posting.get("hostedUrl", ""),
                description_raw=(posting.get("descriptionPlain")
                                 or posting.get("description") or ""),
                country_hint=country_hint,
                fetched_at=time.time(),
            )
        )
    robots_check.polite_delay()
    return jobs


def fetch_workable_board(account_slug: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Workable account's public widget feed.
    No auth required; this endpoint does not support filtering/search, so it
    always returns the account's full current listing."""
    url = WORKABLE_API.format(account=account_slug)
    robots_check.assert_allowed(url, target_label=f"workable:{account_slug}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data.get("jobs", []):
        jobs.append(
            Job(
                source="workable",
                board_or_company=account_slug,
                external_id=str(posting.get("shortcode") or posting.get("id", "")),
                title=posting.get("title", ""),
                location_raw=posting.get("location", {}).get("location_str", "")
                if isinstance(posting.get("location"), dict) else str(posting.get("location", "")),
                url=posting.get("url", ""),
                description_raw=posting.get("description", "") or "",
                country_hint=country_hint,
                fetched_at=time.time(),
            )
        )
    robots_check.polite_delay()
    return jobs


def fetch_recruitee_board(company_slug: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Recruitee company careers site. No
    auth required; description is returned as full HTML in the list call."""
    url = RECRUITEE_API.format(company=company_slug)
    robots_check.assert_allowed(url, target_label=f"recruitee:{company_slug}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data.get("offers", []):
        location = posting.get("location") or posting.get("city", "") or ""
        jobs.append(
            Job(
                source="recruitee",
                board_or_company=company_slug,
                external_id=str(posting.get("id")),
                title=posting.get("title", ""),
                location_raw=location,
                url=f"https://{company_slug}.recruitee.com/o/{posting.get('slug', '')}",
                description_raw=posting.get("description", "") or "",
                country_hint=country_hint,
                fetched_at=time.time(),
            )
        )
    robots_check.polite_delay()
    return jobs


def fetch_all(jurisdiction) -> list[Job]:
    """Fetch every configured Greenhouse/Lever board for one JurisdictionProfile.
    Individual board failures are logged and skipped rather than aborting the
    whole run — one dead board token shouldn't take down the other nine."""
    results: list[Job] = []
    for board in jurisdiction.greenhouse_boards:
        try:
            results.extend(fetch_greenhouse_board(board, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001 - log-and-continue by design
            print(f"[connectors] greenhouse:{board} failed: {exc}")

    for company in jurisdiction.lever_boards:
        try:
            results.extend(fetch_lever_board(company, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] lever:{company} failed: {exc}")

    for account in jurisdiction.workable_boards:
        try:
            results.extend(fetch_workable_board(account, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] workable:{account} failed: {exc}")

    for company in jurisdiction.recruitee_boards:
        try:
            results.extend(fetch_recruitee_board(company, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] recruitee:{company} failed: {exc}")

    return results


def job_to_dict(job: Job) -> dict[str, Any]:
    return asdict(job)
