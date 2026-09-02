"""
Local Flask dashboard — read-only-except-status-tracking view over jobs.db.

Not a public-facing deployment (per the platform overview's "Local
dashboard" section and "no cloud hosting" non-goal): binds to localhost only
by default. Shows both scoring layers side by side (stage-1 keyword score
and, once run, stage-2 LLM score/reasoning) plus the eligibility signal as
its own visible column — never folded into a single composite number, per
eligibility.py's own design note. Supports a country facet (VN/NL/AU,
combined or separate) and application-status tracking (applied/interview/
offer/rejected, with notes and a computed days-since-applied).
"""

from __future__ import annotations

import json
import threading
import time

from flask import Flask, render_template, request, redirect, url_for, jsonify

from . import db, cover_letter, resume_contract, manual_job
from .config import JURISDICTIONS

app = Flask(__name__)

COUNTRY_CHOICES = ["ALL"] + list(JURISDICTIONS.keys())

# Stalled-application follow-up threshold. A job still sitting at
# 'applied' with no status change after this many days gets flagged in the
# dashboard — borrowed from a comparable job-search tool's default cadence
# (10 days) for "this is worth a nudge, not just silently waiting."
FOLLOW_UP_THRESHOLD_DAYS = 10

# In-memory cover-letter generation status, keyed by job_id — polled by the
# dashboard's JS while a generation is running. Deliberately not persisted
# to SQLite: this is ephemeral UI state for "is the on-demand generation I
# just triggered still running", not part of the durable jobs record (the
# archive on disk, written by cover_letter.py, is the durable record).
_letter_status: dict[str, dict] = {}
_letter_status_lock = threading.Lock()


def _run_generation(job_id: str) -> None:
    with _letter_status_lock:
        _letter_status[job_id] = {"state": "running", "message": "Generating..."}
    try:
        result = cover_letter.generate_cover_letter(job_id)
        with _letter_status_lock:
            _letter_status[job_id] = {
                "state": "done",
                "message": result.compile_message,
                "compile_status": result.compile_status,
                "archive_dir": result.archive_dir,
                "pdf_path": result.pdf_path,
                "tex_path": result.tex_path,
                "grounding_ok": result.grounding_ok,
                "grounding_concerns": result.grounding_concerns,
            }
    except (cover_letter.CoverLetterError, resume_contract.ResumeContractError) as exc:
        with _letter_status_lock:
            _letter_status[job_id] = {"state": "error", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI, don't crash the thread silently
        with _letter_status_lock:
            _letter_status[job_id] = {"state": "error", "message": f"Unexpected error: {exc}"}


def _shape_job_row(row) -> dict:
    """Turn one sqlite3.Row into a plain dict with the extra display fields
    the template needs (days-since-applied, parsed breakdown, etc.) —
    computed here rather than in Jinja since Python is a much better place
    for date arithmetic and JSON parsing than a template language."""
    d = dict(row)
    d["stage1_breakdown"] = json.loads(d.get("stage1_breakdown") or "{}")

    applied_at = d.get("applied_at")
    d["days_since_applied"] = (
        int((time.time() - applied_at) // 86400) if applied_at else None
    )
    d["needs_follow_up"] = (
        d["application_status"] == "applied"
        and d["days_since_applied"] is not None
        and d["days_since_applied"] >= FOLLOW_UP_THRESHOLD_DAYS
    )

    jurisdiction = JURISDICTIONS.get(d["country_hint"])
    d["country_name"] = jurisdiction.name if jurisdiction else d["country_hint"]
    d["currency"] = jurisdiction.currency if jurisdiction else ""

    posted_at = d.get("posted_at")
    d["days_since_posted"] = int((time.time() - posted_at) // 86400) if posted_at else None

    return d


def _compute_kpis(jobs: list[dict]) -> dict:
    total = len(jobs)
    if total == 0:
        return {"total": 0, "avg_match_pct": None, "avg_salary_usd_month": None, "sponsorship_confirmed": 0}

    match_pcts = [j["match_pct"] for j in jobs if j.get("match_pct") is not None]
    salaries = [j["salary_usd_month_min"] for j in jobs if j.get("salary_usd_month_min") is not None]
    sponsorship_confirmed = sum(1 for j in jobs if j.get("eligibility_verdict") == "likely_eligible")

    return {
        "total": total,
        "avg_match_pct": round(sum(match_pcts) / len(match_pcts), 1) if match_pcts else None,
        "avg_salary_usd_month": round(sum(salaries) / len(salaries)) if salaries else None,
        "sponsorship_confirmed": sponsorship_confirmed,
    }


@app.route("/")
def index():
    return redirect(url_for("jobs_view", country="ALL"))


def _parse_float_filter(raw: str) -> float | None:
    """Defensive float parsing for a query-string filter value. type="number"
    inputs don't reliably block every non-numeric string across browsers
    (a pasted "4,000" with a thousands separator gets through in practice),
    and a URL can always be edited by hand regardless of what the form
    enforces — either way, a bad filter value should be ignored, not crash
    the whole page with an unhandled ValueError (this happened for real
    during testing: min_match=abc and min_salary=4,000 both 500'd)."""
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


@app.route("/jobs")
def jobs_view():
    country = request.args.get("country", "ALL")
    days_posted = request.args.get("days_posted", "").strip()
    location = request.args.get("location", "").strip()
    company = request.args.get("company", "").strip()
    min_match = request.args.get("min_match", "").strip()
    sponsorship = request.args.get("sponsorship", "").strip()
    min_salary = request.args.get("min_salary", "").strip()

    filter_kwargs = dict(
        country=None if country == "ALL" else country,
        posted_within_days=int(days_posted) if days_posted.isdigit() else None,
        location_contains=location or None,
        company_contains=company or None,
        min_match_pct=_parse_float_filter(min_match),
        eligibility_verdict=sponsorship or None,
        min_salary_usd_month=_parse_float_filter(min_salary),
    )

    conn = db.get_connection()
    try:
        rows = db.list_jobs(conn, **filter_kwargs)
    finally:
        conn.close()

    jobs = [_shape_job_row(r) for r in rows]
    kpis = _compute_kpis(jobs)

    conn = db.get_connection()
    try:
        counts = {code: len(db.list_jobs(conn, country=code)) for code in JURISDICTIONS}
        counts["ALL"] = sum(counts.values())
    finally:
        conn.close()

    return render_template(
        "dashboard.html",
        jobs=jobs,
        country=country,
        country_choices=COUNTRY_CHOICES,
        jurisdictions=JURISDICTIONS,
        counts=counts,
        statuses=db.VALID_APPLICATION_STATUSES,
        FOLLOW_UP_THRESHOLD_DAYS=FOLLOW_UP_THRESHOLD_DAYS,
        kpis=kpis,
        filters={
            "days_posted": days_posted, "location": location, "company": company,
            "min_match": min_match, "sponsorship": sponsorship, "min_salary": min_salary,
        },
    )


@app.route("/jobs/manual", methods=["POST"])
def add_manual_job():
    redirect_country = request.form.get("redirect_country", "ALL")
    try:
        manual_job.ingest_manual_job(
            url=request.form.get("url", ""),
            title=request.form.get("title", ""),
            company=request.form.get("company", ""),
            location=request.form.get("location", ""),
            description=request.form.get("description", ""),
            country_code=request.form.get("country_code", ""),
        )
    except manual_job.ManualJobError as exc:
        return jsonify({"error": str(exc)}), 400

    return redirect(url_for("jobs_view", country=redirect_country))


@app.route("/jobs/<path:job_id>/status", methods=["POST"])
def update_status(job_id):
    status = request.form.get("application_status", "not_applied")
    notes = request.form.get("application_notes", "")
    redirect_country = request.form.get("redirect_country", "ALL")

    conn = db.get_connection()
    try:
        db.update_application_status(conn, job_id, status, notes)
    except (ValueError, KeyError) as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()

    return redirect(url_for("jobs_view", country=redirect_country))


@app.route("/jobs/<path:job_id>/cover-letter", methods=["POST"])
def trigger_cover_letter(job_id):
    with _letter_status_lock:
        current = _letter_status.get(job_id)
        if current and current["state"] == "running":
            return jsonify(current), 409

    thread = threading.Thread(target=_run_generation, args=(job_id,), daemon=True)
    thread.start()
    return jsonify({"state": "running", "message": "Generating..."})


@app.route("/jobs/<path:job_id>/cover-letter/status")
def cover_letter_status(job_id):
    with _letter_status_lock:
        status = _letter_status.get(job_id, {"state": "idle", "message": ""})
    return jsonify(status)


def main() -> None:
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    main()
