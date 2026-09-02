"""
Manual job ingestion — the platform overview's documented answer for
ToS-sensitive sources that can't be automated: "the user browses and pastes
in what they find, which then runs through the identical scoring pipeline
as anything scraped automatically." This is that pipeline entry point.

Concretely needed for Seek, Indeed, TopCV (real infrastructure-level 403s
to an honest bot identity, independent of robots.txt), VietnamWorks
(listings only materialize via client-side JS, no discoverable API), and
CareerBuilder.vn (expired TLS certificate) — none of which get an automated
connector (see connectors.py's module docstring for why), plus anywhere
else the user finds a posting worth scoring that isn't on one of the
connected ATS platforms.
"""

from __future__ import annotations

import hashlib
import time

from . import db, eligibility, salary, scorer
from .config import JURISDICTIONS
from .connectors import Job


class ManualJobError(ValueError):
    """Raised for invalid manual-entry input (missing required fields,
    unknown country code) — a hard stop, not silently defaulted."""


def ingest_manual_job(
    url: str,
    title: str,
    company: str,
    location: str,
    description: str,
    country_code: str,
) -> str:
    """Score and persist a manually-pasted job posting through the exact
    same stage-1 scorer, eligibility detector, and salary estimator as a
    scraped job. Returns the job id."""
    if not url or not url.strip():
        raise ManualJobError("A job URL is required (used to detect duplicates).")
    if not title or not title.strip():
        raise ManualJobError("A job title is required.")
    if not description or not description.strip():
        raise ManualJobError("A job description is required — scoring needs actual JD text.")

    jurisdiction = JURISDICTIONS.get(country_code)
    if jurisdiction is None:
        raise ManualJobError(f"Unknown country code {country_code!r}.")

    # Stable id from the URL so re-pasting the same posting updates it
    # in place (upsert_job's ON CONFLICT) rather than creating a duplicate.
    url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]

    job = Job(
        source="manual",
        board_or_company=(company or "manual").strip() or "manual",
        external_id=url_hash,
        title=title.strip(),
        location_raw=(location or "").strip(),
        url=url.strip(),
        description_raw=description.strip(),
        country_hint=country_code,
        fetched_at=time.time(),
        company_name=(company or "").strip(),
    )

    breakdown = scorer.score_job(job.title, job.description_raw)
    signal = eligibility.assess(job.description_raw, jurisdiction)
    salary_estimate = salary.estimate_salary(job)

    conn = db.get_connection()
    try:
        job_id = db.upsert_job(conn, job, breakdown, signal, salary_estimate=salary_estimate, origin="manual")
    finally:
        conn.close()
    return job_id
