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


def clears_llm_threshold_from_domain_score(domain_score: float, threshold: float = 45.0) -> bool:
    """
    Gate for stage 2, taking the raw stored 'domain' category point value
    (0 to WEIGHTS['domain']) rather than a full ScoreBreakdown — this is what
    main.py uses when re-checking a job already persisted to SQLite, where
    only the JSON-serialized by_category dict is available, not the original
    object. Single source of truth for the threshold formula so main.py never
    has to re-derive it (a previous version of this file did, incorrectly).
    """
    return domain_score >= threshold * (WEIGHTS["domain"] / 100)


def clears_llm_threshold(breakdown: ScoreBreakdown, threshold: float = 45.0) -> bool:
    """
    Gate for stage 2. Per the platform design this should key off the JD-match
    component specifically, not the blended total — here that's approximated
    as the 'domain' category, since that's the closest proxy to "does this JD
    actually match the candidate's field" as opposed to generic title/tool
    overlap. Tune the threshold against real results before trusting it.
    """
    return clears_llm_threshold_from_domain_score(breakdown.by_category.get("domain", 0.0), threshold)
