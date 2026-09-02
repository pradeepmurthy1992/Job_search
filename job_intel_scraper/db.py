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


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.executescript(SCHEMA)
    return conn


def upsert_job(conn: sqlite3.Connection, job, breakdown, eligibility) -> str:
    job_id = f"{job.source}:{job.board_or_company}:{job.external_id}"
    now = time.time()
    conn.execute(
        """
        INSERT INTO jobs (
            id, source, board_or_company, country_hint, title, location_raw,
            url, description_raw, stage1_score, stage1_breakdown,
            eligibility_verdict, eligibility_note, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            location_raw=excluded.location_raw,
            description_raw=excluded.description_raw,
            stage1_score=excluded.stage1_score,
            stage1_breakdown=excluded.stage1_breakdown,
            eligibility_verdict=excluded.eligibility_verdict,
            eligibility_note=excluded.eligibility_note,
            last_seen_at=excluded.last_seen_at
        """,
        (
            job_id, job.source, job.board_or_company, job.country_hint,
            job.title, job.location_raw, job.url, job.description_raw,
            breakdown.total, json.dumps(breakdown.by_category),
            eligibility.verdict, eligibility.note, now, now,
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
    logic stays in one place (scorer.py)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, title, description_raw, stage1_breakdown, url
        FROM jobs
        WHERE country_hint = ? AND llm_scored = 0 AND eligibility_verdict != 'hard_exclude'
        """,
        (country_code,),
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


def list_jobs(conn: sqlite3.Connection, country: str | None = None) -> list[sqlite3.Row]:
    """Jobs for the dashboard, best-scored first. Ranks by the LLM score when
    a job has been stage-2 scored (a real semantic-fit judgment), falling
    back to the stage-1 composite for everything else — so a strong stage-1
    match that hasn't been through stage 2 yet doesn't get buried under
    weaker stage-2-scored jobs."""
    conn.row_factory = sqlite3.Row
    query = """
        SELECT *, COALESCE(llm_score, stage1_score) AS display_score
        FROM jobs
        {where}
        ORDER BY display_score DESC, first_seen_at DESC
    """
    if country:
        rows = conn.execute(
            query.format(where="WHERE country_hint = ?"), (country,)
        ).fetchall()
    else:
        rows = conn.execute(query.format(where="")).fetchall()
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
