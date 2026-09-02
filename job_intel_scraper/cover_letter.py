"""
On-demand LaTeX cover-letter generation pipeline.

Per the platform overview's "On-demand application materials" section: a
cover letter is generated only when explicitly requested for one specific
job (this module is never called automatically for every scored match),
grounded strictly in the candidate's actual resume content (enforced by
resume_contract's data-contract check, which this module hard-stops on
rather than catching), and compiled through a LaTeX toolchain. Each
generated application is archived — the .tex source (and .pdf if XeLaTeX
compiled it), the resume version actually used, and a snapshot of the job
posting — so the record survives even if the original listing disappears.
"""

from __future__ import annotations

import json
import re
import shutil
import string
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from . import db, git_guard, llm_client, resume_contract
from .config import JURISDICTIONS

APPLICATIONS_DIR = Path(__file__).parent / "applications"
LATEX_TEMPLATE_PATH = Path(__file__).parent / "latex" / "cover_letter_template.tex"

CANDIDATE_NAME = "Pradeep Moorthy"
CANDIDATE_LOCATION = "Pune, India"
CANDIDATE_EMAIL = "pradeepmoorthy92@gmail.com"
CANDIDATE_PHONE = "+91 7708084410"


class CoverLetterError(RuntimeError):
    """Raised for failures that should stop generation entirely (resume
    contract failure, missing job, missing template) — distinct from a
    LaTeX compile failure, which is reported in the result instead of
    raised, since the .tex source and archive are still useful without a
    compiled PDF."""


@dataclass
class CoverLetterResult:
    job_id: str
    archive_dir: str
    tex_path: str
    pdf_path: str | None
    compile_status: str  # "compiled" | "xelatex_not_found" | "compile_failed"
    compile_message: str
    prompt_tokens: int
    completion_tokens: int


def _latex_escape(text: str) -> str:
    """Escape characters LaTeX treats specially, so arbitrary LLM-generated
    or JD-derived text (which may contain &, %, $, #, _, {, }, ~, ^, \\)
    doesn't break compilation or get silently mis-rendered."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    pattern = re.compile("|".join(re.escape(k) for k in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], text)


def _safe_dirname(job_id: str) -> str:
    """job_id is 'source:board:external_id' — colons aren't valid in
    Windows path segments, so this makes a filesystem-safe archive folder
    name without losing the original id (kept in meta.json verbatim)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", job_id)


def _render_tex(company: str, job_title: str, letter_body: str) -> str:
    template_text = LATEX_TEMPLATE_PATH.read_text()
    template = string.Template(template_text)
    return template.substitute(
        CANDIDATE_NAME=_latex_escape(CANDIDATE_NAME),
        CANDIDATE_LOCATION=_latex_escape(CANDIDATE_LOCATION),
        CANDIDATE_EMAIL=_latex_escape(CANDIDATE_EMAIL),
        CANDIDATE_PHONE=_latex_escape(CANDIDATE_PHONE),
        COMPANY=_latex_escape(company),
        JOB_TITLE=_latex_escape(job_title),
        LETTER_BODY=_latex_escape(letter_body).replace("\n\n", "\n\n\\par\n"),
    )


def _compile_tex(tex_path: Path, output_dir: Path) -> tuple[str, str, Path | None]:
    """Attempt to compile with xelatex. Returns (status, message, pdf_path).
    A missing xelatex binary or a compile error is reported, not raised —
    the .tex source and the rest of the archive are still written either
    way, so a machine without LaTeX installed yet still gets a usable
    artifact to compile later."""
    try:
        result = subprocess.run(
            [
                "xelatex",
                "-interaction=nonstopmode",
                f"-output-directory={output_dir}",
                str(tex_path),
            ],
            capture_output=True, text=True, timeout=60, cwd=output_dir,
        )
    except FileNotFoundError:
        return (
            "xelatex_not_found",
            "xelatex is not on PATH — install MiKTeX or TeX Live, then "
            "re-run generation for this job (or compile the .tex manually).",
            None,
        )
    except subprocess.TimeoutExpired:
        return ("compile_failed", "xelatex timed out after 60s.", None)

    log_path = output_dir / "compile_log.txt"
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""))

    pdf_path = tex_path.with_suffix(".pdf")
    if result.returncode == 0 and pdf_path.exists():
        return ("compiled", "Compiled successfully.", pdf_path)

    return (
        "compile_failed",
        f"xelatex exited {result.returncode} — see compile_log.txt in the archive dir.",
        None,
    )


def generate_cover_letter(job_id: str) -> CoverLetterResult:
    git_guard.run_guard()

    conn = db.get_connection()
    try:
        job = db.get_job(conn, job_id)
    finally:
        conn.close()
    if job is None:
        raise CoverLetterError(f"No job found with id {job_id!r}")

    # Hard stop on a placeholder-bearing resume — never silently proceed.
    resume_text = resume_contract.load_and_check_resume()

    jurisdiction = JURISDICTIONS.get(job["country_hint"])
    company = job["board_or_company"]

    client = llm_client.build_client_from_env()
    letter = client.draft_cover_letter(
        resume_text=resume_text,
        job_title=job["title"],
        company=company,
        job_description=job["description_raw"] or "",
    )

    archive_dir = APPLICATIONS_DIR / _safe_dirname(job_id) / str(int(time.time()))
    archive_dir.mkdir(parents=True, exist_ok=True)

    tex_content = _render_tex(company, job["title"], letter.letter_body)
    tex_path = archive_dir / "cover_letter.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    compile_status, compile_message, pdf_path = _compile_tex(tex_path, archive_dir)

    shutil.copy2(resume_contract.DEFAULT_RESUME_PATH, archive_dir / resume_contract.DEFAULT_RESUME_PATH.name)

    job_snapshot = {
        "job_id": job["id"],
        "title": job["title"],
        "company": company,
        "url": job["url"],
        "location_raw": job["location_raw"],
        "country_hint": job["country_hint"],
        "description_raw": job["description_raw"],
        "eligibility_verdict": job["eligibility_verdict"],
        "eligibility_note": job["eligibility_note"],
        "snapshot_taken_at": time.time(),
    }
    (archive_dir / "job_snapshot.json").write_text(json.dumps(job_snapshot, indent=2))

    meta = {
        "job_id": job["id"],
        "generated_at": time.time(),
        "llm_backend": type(client).__name__,
        "prompt_tokens": letter.prompt_tokens,
        "completion_tokens": letter.completion_tokens,
        "compile_status": compile_status,
        "compile_message": compile_message,
        "visa_note": jurisdiction.visa_note if jurisdiction else None,
    }
    (archive_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    return CoverLetterResult(
        job_id=job["id"],
        archive_dir=str(archive_dir),
        tex_path=str(tex_path),
        pdf_path=str(pdf_path) if pdf_path else None,
        compile_status=compile_status,
        compile_message=compile_message,
        prompt_tokens=letter.prompt_tokens,
        completion_tokens=letter.completion_tokens,
    )
