"""
Job-function classification — buckets a posting's title into a broad
discipline (Program Management, Engineering, ...) purely from the title
text, for the dashboard's "Function" filter.

Title-only, not title+description: the description contains far too much
incidental vocabulary (a Program Manager JD routinely mentions engineering,
sales, and finance stakeholders) to classify reliably from, whereas the
title itself is the strongest and most deliberate signal of what the role
actually is.

Keyword-based and priority-ordered (first category whose keyword appears
wins), the same deliberately-simple, auditable approach as
company_sector.py's classification — not a model, so a reviewer can read
every rule that drives it.
"""

from __future__ import annotations

# Order matters: checked top to bottom, first match wins. Program/Project
# Management is checked first since that's the candidate's actual target
# discipline and titles like "Manager, Programs & Product Operations" or
# "Senior Fleet Coordinator" should land there/Operations rather than
# being caught by a more generic later bucket.
_FUNCTION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Program/Project Management", [
        "program manager", "programme manager", "project manager",
        "technical program manager", "tpm", "delivery manager", "pmo",
        "program management", "project management",
    ]),
    ("Operations/Manufacturing", [
        "operations", "manufacturing", "production", "supply chain",
        "logistics", "warehouse", "fleet", "quality", "plant", "factory",
        "industrialization", "npi",
    ]),
    ("Engineering/Technical", [
        "engineer", "engineering", "developer", "software", "architect",
        "technician", "scientist", "technical lead", "devops", "qa",
    ]),
    ("Sales/Business Development", [
        "sales", "account manager", "account executive",
        "business development", "partnership", "customer success",
        "growth", "channel",
    ]),
    ("Finance/Legal", [
        "finance", "accounting", "accountant", "controller", "legal",
        "counsel", "compliance", "audit", "treasury", "tax",
    ]),
    ("Marketing/Communications", [
        "marketing", "communications", "brand", "content", "pr specialist",
        "public relations",
    ]),
    ("HR/People", [
        "human resources", "recruiter", "recruiting", "talent",
        "people operations", "hr business partner", "hr manager",
    ]),
]


def classify(title: str) -> str:
    """Returns the function bucket name, or "Other" if nothing matches."""
    text = (title or "").lower()
    for bucket, keywords in _FUNCTION_KEYWORDS:
        if any(kw in text for kw in keywords):
            return bucket
    return "Other"


FUNCTION_CHOICES = [name for name, _ in _FUNCTION_KEYWORDS] + ["Other"]
