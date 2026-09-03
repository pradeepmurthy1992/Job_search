"""
Orchestrator CLI — discovery + stage-1 scoring + eligibility flagging, and
(optionally) stage-2 semantic scoring, for one or more target jurisdictions
in a single run.

Stage 2 is off by default (--stage2 to enable) since it needs either a free
Gemini API key or a locally-running Ollama model configured first — see
llm_client.py for both options and how to set each one up.

Usage:
    python -m job_intel_scraper.main --countries VN NL AU
    python -m job_intel_scraper.main --countries AU --limit 50
    python -m job_intel_scraper.main --countries NL --stage2
"""

from __future__ import annotations

import argparse
import sys
import uuid
import time
from pathlib import Path

from . import connectors, db, scorer, eligibility, llm_client, git_guard, salary
from .config import JURISDICTIONS, GLOBAL_MAX_LLM_TOKENS_PER_RUN

RESUME_TEXT_PATH = Path(__file__).parent / "resume_summary.txt"


def _load_resume_text() -> str:
    """Short resume summary fed to the LLM prompt — NOT the full resume, to
    keep prompt-token cost down. Falls back to a hardcoded summary if
    resume_summary.txt hasn't been created yet."""
    if RESUME_TEXT_PATH.exists():
        return RESUME_TEXT_PATH.read_text()
    return (
        "11+ years automotive Program/Project Management, VAVE & cost "
        "engineering across OEM, Tier-1, and EV environments (Tata Motors, "
        "Mahindra & Mahindra, TVS Motor, Nissan Ashok Leyland Technologies, "
        "Ather Energy). Patent holder (vehicle door-slam testing). Python/"
        "VBA/TCL automation, Power BI, PLM (CATIA, Enovia), Altair HyperMesh, "
        "Agile & Waterfall delivery, PMP (in progress), MBA in Business "
        "Analytics (in progress)."
    )


def _run_stage2(conn, jurisdiction, run_id: str, global_budget_remaining: int) -> int:
    """Runs stage-2 for one country, stopping at whichever comes first: the
    country's own max_llm_tokens_per_run, or global_budget_remaining (the
    run-wide GLOBAL_MAX_LLM_TOKENS_PER_RUN ceiling, tracked across every
    country in this CLI invocation — see config.py for why this exists
    alongside the per-country one). Returns tokens actually used, so the
    caller can decrement its running global total."""
    client = llm_client.build_client_from_env()
    resume_text = _load_resume_text()

    candidates = db.get_unscored_candidates(conn, jurisdiction.country_code)
    tokens_used_this_run = 0
    scored = 0
    skipped_low_score = 0

    for row in candidates:
        if not scorer.clears_llm_threshold_from_total_score(row["stage1_score"]):
            skipped_low_score += 1
            continue

        if tokens_used_this_run >= jurisdiction.max_llm_tokens_per_run:
            print(
                f"  [stage2] per-country token ceiling "
                f"({jurisdiction.max_llm_tokens_per_run}) reached — stopping "
                f"stage-2 for {jurisdiction.name} this run, {len(candidates) - scored} "
                f"jobs left unscored (they remain llm_scored=0 for next run)."
            )
            break

        if tokens_used_this_run >= global_budget_remaining:
            print(
                f"  [stage2] GLOBAL token ceiling for this entire run "
                f"({GLOBAL_MAX_LLM_TOKENS_PER_RUN}) reached mid-country — "
                f"stopping stage-2 for {jurisdiction.name} (and every "
                f"country after it this run), {len(candidates) - scored} "
                f"jobs left unscored here (they remain llm_scored=0 for "
                f"next run)."
            )
            break

        try:
            result = client.score_fit(resume_text, row["title"], row["description_raw"])
        except Exception as exc:  # noqa: BLE001 - one bad call shouldn't kill the run
            print(f"  [stage2] LLM call failed for {row['url']}: {exc}")
            continue

        db.record_llm_result(conn, row["id"], result)
        run_tokens = result.prompt_tokens + result.completion_tokens
        db.add_run_tokens(conn, run_id, run_tokens)
        tokens_used_this_run += run_tokens
        scored += 1

    print(
        f"  [stage2] scored {scored} jobs, skipped {skipped_low_score} below "
        f"threshold, used ~{tokens_used_this_run} tokens this run."
    )
    return tokens_used_this_run


def run(country_codes: list[str], limit_override: int | None = None, run_stage2: bool = False) -> None:
    try:
        git_guard.run_guard()
    except git_guard.GitGuardError as exc:
        print(f"[main] {exc}", file=sys.stderr)
        sys.exit(1)

    conn = db.get_connection()
    global_tokens_used = 0

    for code in country_codes:
        jurisdiction = JURISDICTIONS.get(code)
        if jurisdiction is None:
            print(f"[main] unknown country code {code!r}, skipping", file=sys.stderr)
            continue

        if run_stage2 and global_tokens_used >= GLOBAL_MAX_LLM_TOKENS_PER_RUN:
            print(
                f"\n[main] GLOBAL token ceiling ({GLOBAL_MAX_LLM_TOKENS_PER_RUN}) "
                f"already reached this run — skipping stage-2 for {jurisdiction.name} "
                f"and every remaining country. Stage-1 discovery/scoring still runs "
                f"(it's free); only LLM stage-2 is capped."
            )
            run_stage2_for_this_country = False
        else:
            run_stage2_for_this_country = run_stage2

        run_id = str(uuid.uuid4())
        started_at = time.time()
        limit = limit_override or jurisdiction.max_jobs_per_run

        print(f"\n=== {jurisdiction.name} ({code}) — run {run_id[:8]} ===")

        has_any_board = any([
            jurisdiction.greenhouse_boards, jurisdiction.lever_boards,
            jurisdiction.workable_boards, jurisdiction.recruitee_boards,
        ])
        if not has_any_board:
            print(
                f"  No Greenhouse/Lever/Workable/Recruitee boards configured for "
                f"{jurisdiction.name} yet. Add them in config.py, or add a bespoke "
                f"connector for {', '.join(jurisdiction.local_job_boards) or 'the local job boards'}."
            )
            conn.execute(
                "INSERT INTO run_ledger (run_id, started_at, finished_at, country_hint, jobs_fetched, jobs_llm_scored, llm_tokens_used) VALUES (?,?,?,?,?,?,?)",
                (run_id, started_at, time.time(), code, 0, 0, 0),
            )
            conn.commit()
            continue

        jobs = connectors.fetch_all(jurisdiction)[:limit]
        print(f"  Fetched {len(jobs)} postings (capped at {limit} per config).")

        scored_count = 0
        eligible_count = 0
        for job in jobs:
            breakdown = scorer.score_job(job.title, job.description_raw)
            signal = eligibility.assess(job.description_raw, jurisdiction)
            salary_estimate = salary.estimate_salary(job)
            db.upsert_job(conn, job, breakdown, signal, salary_estimate=salary_estimate)
            scored_count += 1
            if signal.verdict != "hard_exclude":
                eligible_count += 1

        print(
            f"  Stage-1 scored {scored_count} jobs; "
            f"{eligible_count} not hard-excluded on eligibility; "
            f"{scored_count - eligible_count} excluded (citizenship-restricted)."
        )

        conn.execute(
            """
            INSERT INTO run_ledger (run_id, started_at, finished_at, country_hint, jobs_fetched, jobs_llm_scored, llm_tokens_used)
            VALUES (?,?,?,?,?,?,?)
            """,
            (run_id, started_at, time.time(), code, len(jobs), 0, 0),
        )
        conn.commit()

        if run_stage2_for_this_country:
            global_budget_remaining = GLOBAL_MAX_LLM_TOKENS_PER_RUN - global_tokens_used
            tokens_this_country = _run_stage2(conn, jurisdiction, run_id, global_budget_remaining)
            global_tokens_used += tokens_this_country

    if run_stage2:
        print(f"\n[main] Total LLM tokens used this run (all countries): {global_tokens_used}")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Intelligence Platform — discovery + two-stage scoring")
    parser.add_argument(
        "--countries", nargs="+", choices=list(JURISDICTIONS.keys()), default=list(JURISDICTIONS.keys()),
        help="Which jurisdictions to run (default: all configured).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Override per-country job-count ceiling for this run.")
    parser.add_argument(
        "--stage2", action="store_true",
        help="Also run LLM semantic scoring (needs JOB_INTEL_LLM_BACKEND env "
             "var set to 'gemini' or 'ollama' — see llm_client.py).",
    )
    args = parser.parse_args()
    run(args.countries, args.limit, run_stage2=args.stage2)


if __name__ == "__main__":
    main()
