"""
Stage 1: fast, free, local keyword/TF-IDF-style composite scorer.

Per the platform design, this is the cheap gate that decides which jobs are
even worth an LLM call in stage 2 — so it needs to be reasonably precise on
its own, not just a rough pre-filter. This implementation uses simple
weighted keyword overlap rather than a real TF-IDF/vector model; swap in
scikit-learn's TfidfVectorizer + cosine similarity against the resume text
for a stronger version once you're ready — the interface (a 0-100 score plus
a breakdown dict) can stay the same.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import RESUME_KEYWORDS

WEIGHTS = {
    "title": 30,
    "domain": 30,
    "tools": 20,
    "methodology": 10,
    "seniority_signals": 10,
}


@dataclass
class ScoreBreakdown:
    total: float  # 0-100
    by_category: dict[str, float]
    matched_terms: dict[str, list[str]]


def _category_score(text: str, terms: list[str]) -> tuple[float, list[str]]:
    text_lower = text.lower()
    hits = [t for t in terms if t.lower() in text_lower]
    if not terms:
        return 0.0, hits
    # Fraction of that category's vocabulary present, capped at 1.0.
    fraction = min(len(hits) / max(1, len(terms) * 0.4), 1.0)
    return fraction, hits


def score_job(title: str, description: str) -> ScoreBreakdown:
    combined = f"{title}\n{description}"
    by_category: dict[str, float] = {}
    matched_terms: dict[str, list[str]] = {}
    total = 0.0

    for category, terms in RESUME_KEYWORDS.items():
        fraction, hits = _category_score(combined, terms)
        weight = WEIGHTS.get(category, 0)
        category_points = fraction * weight
        by_category[category] = round(category_points, 1)
        matched_terms[category] = hits
        total += category_points

    return ScoreBreakdown(total=round(total, 1), by_category=by_category, matched_terms=matched_terms)


def clears_llm_threshold_from_total_score(total_score: float, threshold: float = 45.0) -> bool:
    """
    Gate for stage 2, taking the raw stored stage1_score column (0-100)
    rather than a full ScoreBreakdown — this is what main.py uses when
    re-checking a job already persisted to SQLite. Single source of truth
    for the threshold so main.py never has to re-derive it.

    Gates on the BLENDED total, not the 'domain' category alone — an
    earlier version did that (on the theory that domain keyword density is
    the best proxy for "does this JD match the candidate's field"), and it
    was a real bug in practice: live-verified against 586 real scraped
    jobs, the domain-only gate let through only 9 (1.5%) and specifically
    excluded the adjacent-sector companies the whole multi-country
    strategy was built to find — e.g. AirTrunk's "Senior Project Manager"
    (a data-centre developer, not automotive) scored a near-perfect 28.1/30
    on title but only 6.0/30 on domain, since data-centre program-
    management JDs don't use automotive jargon (OEM/Tier-1/BOM/PLM/ECN)
    at all, and never reached stage-2 despite being the #5 stage-1 match
    across every country. The blended total lets a strong title/
    methodology/seniority match compensate for a JD that's genuinely
    relevant but doesn't happen to use automotive-specific vocabulary —
    consistent with why the sector-expansion strategy exists in the first
    place. Default 45.0 was picked to land close to the real top-10%
    cutoff (44.1) observed across the 586-job dataset, not an arbitrary
    round number.
    """
    return total_score >= threshold


def clears_llm_threshold(breakdown: ScoreBreakdown, threshold: float = 45.0) -> bool:
    """Gate for stage 2 — see clears_llm_threshold_from_total_score for the
    reasoning behind gating on the blended total rather than one category."""
    return clears_llm_threshold_from_total_score(breakdown.total, threshold)
