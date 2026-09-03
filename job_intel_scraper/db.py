"""
SQLite persistence. WAL mode + busy_timeout because the dashboard, the
scraping pipeline, and (eventually) the sync process can all touch this file
independently — per the platform overview's reliability notes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,             -- source:board:external_id
    source TEXT NOT NULL,
    board_or_company TEXT NOT NULL,
    country_hint TEXT NOT NULL,
    title TEXT NOT NULL,
    location_raw TEXT,
    url TEXT NOT NULL UNIQUE,
    description_raw TEXT,
    stage1_score REAL,
    stage1_breakdown TEXT,           -- JSON
    eligibility_verdict TEXT,
    eligibility_note TEXT,
    llm_scored INTEGER DEFAULT 0,    -- 0/1 — cache flag so nothing is re-scored
    llm_score REAL,
    llm_reasoning TEXT,
    llm_prompt_tokens INTEGER DEFAULT 0,
    llm_completion_tokens INTEGER DEFAULT 0,
    application_status TEXT DEFAULT 'not_applied',  -- applied/interview/offer/rejected
    application_notes TEXT,
    applied_at REAL,
    posted_at REAL,                  -- epoch seconds, when the source provides one
    company_name TEXT,
    salary_usd_month_min REAL,       -- approx pay in USD/month; NULL = not disclosed
    salary_usd_month_max REAL,
    salary_note TEXT,                -- how the figure was derived (structured/extracted/not disclosed)
    origin TEXT DEFAULT 'scraped',   -- 'scraped' | 'manual' (pasted via the dashboard)
    -- Every jurisdiction this job's location has matched, as a delimited
    -- string with leading/trailing commas (e.g. ",NL,DE,") so a substring
    -- check for ",DE," can't false-match ",DEV," or similar. country_hint
    -- stays the FIRST country this job was seen under (for display) and is
    -- never overwritten on conflict; matched_countries is the source of
    -- truth for "does this job show up on country X's tab" — a job whose
    -- location genuinely fits more than one target country (e.g. a
    -- "Remote Europe" role matching both NL and DE) is one row, visible on
    -- every tab it matches, not silently attributed to just whichever
    -- country's scrape ran first.
    matched_countries TEXT,
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS run_ledger (
    run_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    finished_at REAL,
    country_hint TEXT,
    jobs_fetched INTEGER DEFAULT 0,
    jobs_llm_scored INTEGER DEFAULT 0,
    llm_tokens_used INTEGER DEFAULT 0
);
"""


# Columns added to `jobs` after the table already existed on some machines
# (posted_at/company_name/salary_* were added mid-project). CREATE TABLE IF
# NOT EXISTS is a no-op once the table exists — it does NOT retroactively
# add new columns — so a jobs.db created before these were added would
# otherwise 500 the moment a filter referenced one of them by name
# (reproduced live: "no such column: company_name" on the dashboard's
# company filter). _migrate() below adds any column that's in SCHEMA but
# missing from the actual table, every time a connection is opened — the
# same "don't let a silent mismatch linger" instinct as the git-tracking
# guard, applied to the database instead of git.
_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA: list[tuple[str, str]] = [
    ("posted_at", "REAL"),
    ("company_name", "TEXT"),
    ("salary_usd_month_min", "REAL"),
    ("salary_usd_month_max", "REAL"),
    ("salary_note", "TEXT"),
    ("origin", "TEXT DEFAULT 'scraped'"),
    ("matched_countries", "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for column, ddl_type in _COLUMNS_ADDED_AFTER_INITIAL_SCHEMA:
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl_type}")
    # Backfill any row with no matched_countries (a newly-added column
    # defaults to NULL on every pre-existing row) from its country_hint, so
    # jobs scraped before this migration don't vanish from their own
    # country tab — list_jobs' country filter checks matched_countries,
    # not country_hint directly. Unconditional and idempotent: cheap no-op
    # once every row has a value, self-heals if one ever slips through.
    conn.execute(
        "UPDATE jobs SET matched_countries = ',' || country_hint || ',' "
        "WHERE matched_countries IS NULL"
    )
    conn.commit()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def upsert_job(conn: sqlite3.Connection, job, breakdown, eligibility, salary_estimate=None, origin: str = "scraped") -> str:
    job_id = f"{job.source}:{job.board_or_company}:{job.external_id}"
    now = time.time()
    salary_min = salary_estimate.usd_per_month_min if salary_estimate else None
    salary_max = salary_estimate.usd_per_month_max if salary_estimate else None
    salary_note = salary_estimate.note if salary_estimate else None
    # Wrapped in leading/trailing commas so a later substring check for
    # ",DE," can't false-match inside a longer code — see the schema
    # comment on matched_countries for why this exists (one row per
    # physical posting, visible on every country tab it legitimately
    # matches, rather than only the first one it was scraped under).
    new_country_wrapped = f",{job.country_hint},"
    conn.execute(
        """
        INSERT INTO jobs (
            id, source, board_or_company, country_hint, matched_countries, title, location_raw,
            url, description_raw, stage1_score, stage1_breakdown,
            eligibility_verdict, eligibility_note, posted_at, company_name,
            salary_usd_month_min, salary_usd_month_max, salary_note, origin,
            first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            location_raw=excluded.location_raw,
            description_raw=excluded.description_raw,
            stage1_score=excluded.stage1_score,
            stage1_breakdown=excluded.stage1_breakdown,
            eligibility_verdict=excluded.eligibility_verdict,
            eligibility_note=excluded.eligibility_note,
            posted_at=excluded.posted_at,
            company_name=excluded.company_name,
            salary_usd_month_min=excluded.salary_usd_month_min,
            salary_usd_month_max=excluded.salary_usd_month_max,
            salary_note=excluded.salary_note,
            matched_countries = CASE
                WHEN instr(jobs.matched_countries, excluded.matched_countries) > 0
                THEN jobs.matched_countries
                ELSE jobs.matched_countries || substr(excluded.matched_countries, 2)
            END,
            last_seen_at=excluded.last_seen_at
        """,
        (
            job_id, job.source, job.board_or_company, job.country_hint, new_country_wrapped,
            job.title, job.location_raw, job.url, job.description_raw,
            breakdown.total, json.dumps(breakdown.by_category),
            eligibility.verdict, eligibility.note,
            getattr(job, "posted_at", None), getattr(job, "company_name", "") or job.board_or_company,
            salary_min, salary_max, salary_note, origin,
            now, now,
        ),
    )
    conn.commit()
    return job_id


def job_already_llm_scored(conn: sqlite3.Connection, job_id: str) -> bool:
    row = conn.execute("SELECT llm_scored FROM jobs WHERE id=?", (job_id,)).fetchone()
    return bool(row and row[0])


def get_unscored_candidates(conn: sqlite3.Connection, country_code: str) -> list[sqlite3.Row]:
    """Jobs for this country that haven't been LLM-scored yet and weren't
    hard-excluded on eligibility. Stage-1 threshold filtering happens in
    main.py against the stored breakdown JSON, not here, so the threshold
    logic stays in one place (scorer.py).

    Ordered best-stage1-score-first: when a token ceiling (per-country or
    global) stops main.py's stage-2 loop partway through, it should have
    already spent its budget on the strongest candidates, not whichever
    ones happened to come back in arbitrary row order — reproduced live:
    the single best stage-1 match across all 590 jobs (Waymo, "Vehicle
    Package and Integration Lead", 57.5) didn't get scored in a real run
    because lower-scoring US candidates exhausted the budget first.

    Filters on matched_countries, not country_hint directly — same reason
    as list_jobs: a job whose location fits more than one target country
    needs to be a stage-2 candidate under EVERY country it matches, not
    just whichever one it was first seen under.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, title, description_raw, stage1_score, stage1_breakdown, url
        FROM jobs
        WHERE instr(matched_countries, ?) > 0 AND llm_scored = 0 AND eligibility_verdict != 'hard_exclude'
        ORDER BY stage1_score DESC
        """,
        (f",{country_code},",),
    ).fetchall()
    conn.row_factory = None
    return rows


def record_llm_result(conn: sqlite3.Connection, job_id: str, result) -> None:
    """Store the LLM verdict and mark this job cached — it will never be
    re-scored (and never re-billed) on a later run unless this flag is reset
    explicitly."""
    conn.execute(
        """
        UPDATE jobs SET
            llm_scored = 1,
            llm_score = ?,
            llm_reasoning = ?,
            llm_prompt_tokens = ?,
            llm_completion_tokens = ?
        WHERE id = ?
        """,
        (result.score, result.reasoning, result.prompt_tokens, result.completion_tokens, job_id),
    )
    conn.commit()


VALID_APPLICATION_STATUSES = ("not_applied", "applied", "interview", "offer", "rejected")


def list_jobs(
    conn: sqlite3.Connection,
    country: str | None = None,
    posted_within_days: int | None = None,
    location_contains: str | None = None,
    company_contains: str | None = None,
    min_match_pct: float | None = None,
    eligibility_verdict: str | None = None,
    min_salary_usd_month: float | None = None,
) -> list[sqlite3.Row]:
    """Jobs for the dashboard, best-scored first. Ranks by the LLM score when
    a job has been stage-2 scored (a real semantic-fit judgment), falling
    back to the stage-1 composite for everything else — so a strong stage-1
    match that hasn't been through stage 2 yet doesn't get buried under
    weaker stage-2-scored jobs.

    display_score is the raw 0-100(ish) composite; match_pct normalizes it
    against the maximum possible stage-1 total (sum of scorer.WEIGHTS) so
    the dashboard can filter/display "match %" on a consistent 0-100 scale
    regardless of whether a job has been stage-2 scored yet.
    """
    from .scorer import WEIGHTS
    max_possible = sum(WEIGHTS.values())

    conn.row_factory = sqlite3.Row
    clauses: list[str] = []
    params: list = []

    if country:
        # matched_countries, not country_hint — a job whose location fits
        # more than one target country is one row, visible on every tab it
        # legitimately matches (see upsert_job / the schema comment).
        clauses.append("instr(matched_countries, ?) > 0")
        params.append(f",{country},")
    if posted_within_days is not None:
        cutoff = time.time() - posted_within_days * 86400
        # Jobs with no posted_at at all are kept rather than silently
        # dropped by a recency filter that can't evaluate them — an
        # unknown post date isn't evidence the posting is stale.
        clauses.append("(posted_at IS NULL OR posted_at >= ?)")
        params.append(cutoff)
    if location_contains:
        clauses.append("LOWER(location_raw) LIKE ?")
        params.append(f"%{location_contains.lower()}%")
    if company_contains:
        clauses.append("LOWER(company_name) LIKE ?")
        params.append(f"%{company_contains.lower()}%")
    if min_match_pct is not None:
        clauses.append("(COALESCE(llm_score, stage1_score) / ?) * 100 >= ?")
        params.extend([max_possible, min_match_pct])
    if eligibility_verdict:
        clauses.append("eligibility_verdict = ?")
        params.append(eligibility_verdict)
    if min_salary_usd_month is not None:
        clauses.append("salary_usd_month_min >= ?")
        params.append(min_salary_usd_month)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT *, COALESCE(llm_score, stage1_score) AS display_score,
               (COALESCE(llm_score, stage1_score) / {max_possible}) * 100 AS match_pct
        FROM jobs
        {where}
        ORDER BY display_score DESC, first_seen_at DESC
    """
    rows = conn.execute(query, params).fetchall()
    conn.row_factory = None
    return rows


def get_job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.row_factory = None
    return row


def update_application_status(
    conn: sqlite3.Connection, job_id: str, status: str, notes: str | None
) -> None:
    """Update application-status tracking for one job. applied_at is set the
    first time a job moves to 'applied' and never overwritten afterwards —
    re-saving notes on an already-applied job (or moving it on to interview/
    offer/rejected) must not reset the "days since applied" clock."""
    if status not in VALID_APPLICATION_STATUSES:
        raise ValueError(f"Invalid application_status {status!r}")

    row = conn.execute("SELECT applied_at FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(f"No job with id {job_id!r}")
    applied_at = row[0]
    if status != "not_applied" and applied_at is None:
        applied_at = time.time()

    conn.execute(
        "UPDATE jobs SET application_status = ?, application_notes = ?, applied_at = ? WHERE id = ?",
        (status, notes, applied_at, job_id),
    )
    conn.commit()


def add_run_tokens(conn: sqlite3.Connection, run_id: str, tokens: int, jobs_scored_delta: int = 1) -> None:
    conn.execute(
        """
        UPDATE run_ledger
        SET llm_tokens_used = llm_tokens_used + ?, jobs_llm_scored = jobs_llm_scored + ?
        WHERE run_id = ?
        """,
        (tokens, jobs_scored_delta, run_id),
    )
    conn.commit()


def get_usage_summary(conn: sqlite3.Connection) -> dict:
    """All-time LLM token spend, for the dashboard's cost-visibility KPI —
    tracked in run_ledger since the start (via add_run_tokens) but never
    previously surfaced anywhere, which is exactly the "cost is visible
    rather than assumed" requirement the platform overview calls for."""
    row = conn.execute(
        "SELECT COALESCE(SUM(llm_tokens_used), 0), COALESCE(SUM(jobs_llm_scored), 0), COUNT(*) FROM run_ledger"
    ).fetchone()
    return {
        "total_tokens": row[0],
        "total_jobs_llm_scored": row[1],
        "total_runs": row[2],
    }


def get_recent_runs(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM run_ledger ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.row_factory = None
    return rows
