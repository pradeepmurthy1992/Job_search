"""
Eligibility signal detection — kept strictly separate from the fit score.

A job can be a 95% skills/experience match and still be something Pradeep
cannot legally take (citizenship-restricted, no sponsorship, language-gated).
That's a different axis than "is this job relevant to my resume," and folding
the two into one composite number would hide exactly the failure mode a
cross-border job search needs surfaced: a great-looking match that's actually
a dead end. So this returns a separate, visible flag set, never a discount
applied silently to the fit score.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import JurisdictionProfile


@dataclass
class EligibilitySignal:
    sponsorship_mentioned: bool
    citizenship_restricted: bool
    language_requirement_flagged: bool
    matched_keywords: list[str]
    verdict: str  # "likely_eligible" | "flag_for_review" | "hard_exclude"
    note: str


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def assess(job_description: str, jurisdiction: JurisdictionProfile) -> EligibilitySignal:
    text = job_description or ""

    citizenship_hits = _contains_any(text, jurisdiction.citizenship_restricted_keywords)
    if citizenship_hits:
        return EligibilitySignal(
            sponsorship_mentioned=False,
            citizenship_restricted=True,
            language_requirement_flagged=False,
            matched_keywords=citizenship_hits,
            verdict="hard_exclude",
            note=(
                f"Excluded: posting restricts eligibility to citizens/PR holders "
                f"({', '.join(citizenship_hits)})."
            ),
        )

    sponsorship_hits = _contains_any(text, jurisdiction.sponsorship_keywords)
    language_hits = _contains_any(text, jurisdiction.language_requirement_keywords)

    if sponsorship_hits:
        verdict = "likely_eligible"
        note = f"Sponsorship/relocation language found: {', '.join(sponsorship_hits)}."
    else:
        # Absence of sponsorship language is a caution flag, not a rejection —
        # see jurisdiction.visa_note for why (many employers sponsor without
        # saying so in the JD; Vietnam is the exception where absence should
        # weigh more heavily since sponsorship there is legally mandatory and
        # employers who offer it usually do say so).
        verdict = "flag_for_review"
        note = (
            "No explicit sponsorship/relocation language found — "
            f"does not necessarily mean the role is closed. {jurisdiction.visa_note}"
        )

    if language_hits:
        note += f" Local-language requirement detected: {', '.join(language_hits)}."

    return EligibilitySignal(
        sponsorship_mentioned=bool(sponsorship_hits),
        citizenship_restricted=False,
        language_requirement_flagged=bool(language_hits),
        matched_keywords=sponsorship_hits + language_hits,
        verdict=verdict,
        note=note,
    )
