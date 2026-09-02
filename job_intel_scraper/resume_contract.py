"""
Resume data-contract check — the same "data-contract mismatch" failure class
the platform overview's reliability notes describe for scrapers (a class of
bug that silently returned zero results instead of failing loudly), applied
here to the resume-ingestion side of the cover-letter pipeline.

The concrete incident this guards against already happened once: the
original resume had a `[[program/platform name]` placeholder bracket left in
a bullet (see build-prompt.md). If that had reached an LLM cover-letter
prompt, the model would have either echoed the bracket verbatim into a
generated cover letter, or silently hallucinated a plausible-sounding fill-in
— both bad outcomes, and both silent. This check makes that failure loud
instead: cover-letter generation must call `check_resume_contract()` (or the
convenience `load_and_check_resume()`) before ever sending resume text to an
LLM prompt or a LaTeX template, and must refuse to proceed if it raises.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

DEFAULT_RESUME_PATH = Path(__file__).parent.parent / "Pradeep_Moorthy_Resume_Fixed.docx"

# Each pattern is (compiled regex, human-readable label for the error message).
# Order matters only for readability of the reported match list.
_PLACEHOLDER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\[\["), "double open-bracket \"[[\""),
    (re.compile(r"\[TBD\]", re.IGNORECASE), "[TBD]"),
    (re.compile(r"\[TODO\]", re.IGNORECASE), "[TODO]"),
    (re.compile(r"\[FIXME\]", re.IGNORECASE), "[FIXME]"),
    (re.compile(r"\[XXX\]", re.IGNORECASE), "[XXX]"),
    (re.compile(r"\{\{.*?\}\}"), "template placeholder \"{{...}}\""),
    # Generic bracketed-phrase placeholder, e.g. "[program/platform name]" —
    # the exact shape of the incident that motivated this module. A resume
    # has no legitimate reason to contain a single square-bracketed phrase,
    # so this stays a strict check rather than an allowlist-based one.
    (re.compile(r"\[[A-Za-z][A-Za-z0-9 /_'.-]{1,80}\]"), "bracketed placeholder phrase"),
]


class ResumeContractError(ValueError):
    """Raised when resume text fails the placeholder-marker check. Callers
    (cover-letter generation, in particular) must treat this as a hard stop,
    never as something to catch, ignore, and proceed past."""


def check_resume_contract(resume_text: str, source_label: str = "resume") -> None:
    """Fail loudly if resume_text contains placeholder markers. Raises
    ResumeContractError listing every match found (not just the first) so
    the human fixing it sees the full scope in one pass."""
    hits: list[str] = []
    for pattern, label in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(resume_text):
            snippet = match.group(0)
            hits.append(f'{label}: "{snippet}"')

    if hits:
        raise ResumeContractError(
            f"Resume data-contract check FAILED for {source_label} — "
            f"{len(hits)} placeholder marker(s) found: " + "; ".join(hits) +
            ". Fix the source resume before generating any cover letter "
            "from it — do not proceed with a placeholder-bearing resume."
        )


def load_resume_text(path: Path = DEFAULT_RESUME_PATH) -> str:
    """Extract plain text from the .docx resume — paragraphs and any table
    cells, in document order, since a resume laid out with tables (common
    for a two-column format) would otherwise lose content read paragraph-
    only."""
    if not path.exists():
        raise FileNotFoundError(
            f"Resume file not found at {path} — cover-letter generation "
            "needs the actual resume, not just resume_summary.txt, to stay "
            "grounded in real content."
        )

    document = Document(str(path))
    parts: list[str] = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)

    return "\n".join(parts)


def load_and_check_resume(path: Path = DEFAULT_RESUME_PATH) -> str:
    """Convenience wrapper: load the resume and immediately run the
    data-contract check on it. This is what cover-letter generation should
    call — never load_resume_text() alone, which skips the check."""
    text = load_resume_text(path)
    check_resume_contract(text, source_label=str(path))
    return text
