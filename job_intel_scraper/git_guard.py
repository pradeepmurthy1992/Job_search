"""
Personal-data git-tracking guard — the platform overview's "Automated safety
guards" section, made runnable.

A .gitignore rule only prevents a file from being tracked in the FUTURE; it
does nothing to un-track a file that was already committed before the rule
existed. So this module checks both halves independently:
  (a) is the pattern actually present in .gitignore?
  (b) is anything matching that pattern already tracked by git right now?

Either failing is a hard stop, not a warning — call `run_guard()` (or the
`check_git_guard` CLI below) before every scrape/sync run and before every
commit. This has no opinion on *how* you commit; it only refuses to let the
scrape/sync/commit proceed while the guard is red.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The exact patterns this guard enforces — kept in sync with the repo's
# .gitignore and the ground rules in build-prompt.md / the platform overview.
# Never commit: the scraped-jobs database, secrets, the resume, or PDFs.
PROTECTED_PATTERNS = [
    "job_intel_scraper/jobs.db",
    "job_intel_scraper/jobs.db-*",
    ".env",
    "*.pdf",
    "Pradeep_Moorthy_Resume_Fixed.docx",
]


class GitGuardError(RuntimeError):
    """Raised when the personal-data git-tracking guard fails. Callers
    should treat this as a hard stop, not something to catch and ignore."""


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GitGuardError(
            "Not inside a git repository — cannot verify the personal-data "
            "tracking guard. Run `git init` first."
        )
    return Path(result.stdout.strip())


def _gitignore_text(repo_root: Path) -> str:
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        return ""
    return gitignore_path.read_text()


def _missing_from_gitignore(repo_root: Path) -> list[str]:
    text = _gitignore_text(repo_root)
    lines = {line.strip() for line in text.splitlines()}
    return [p for p in PROTECTED_PATTERNS if p not in lines]


def _already_tracked(repo_root: Path) -> list[str]:
    """Ask git itself which tracked files match each protected glob — this
    is the half a .gitignore rule alone can never fix retroactively."""
    tracked_hits: list[str] = []
    for pattern in PROTECTED_PATTERNS:
        result = subprocess.run(
            ["git", "ls-files", "--", pattern],
            capture_output=True, text=True, cwd=repo_root,
        )
        matches = [line for line in result.stdout.splitlines() if line.strip()]
        tracked_hits.extend(matches)
    return tracked_hits


def run_guard() -> None:
    """Hard-stop entry point. Raises GitGuardError with a specific,
    actionable message if either half of the check fails. Call this before
    every scrape/sync operation and before every commit."""
    repo_root = _repo_root()

    missing = _missing_from_gitignore(repo_root)
    if missing:
        raise GitGuardError(
            "Personal-data git-tracking guard FAILED: the following patterns "
            "are not in .gitignore: " + ", ".join(missing) + ". Add them "
            "before proceeding — a scrape/sync/commit must not run while "
            "this is unresolved."
        )

    tracked = _already_tracked(repo_root)
    if tracked:
        raise GitGuardError(
            "Personal-data git-tracking guard FAILED: these files are "
            "already tracked by git despite matching a protected pattern "
            "(a .gitignore rule cannot undo a prior commit): "
            + ", ".join(tracked) + ". Run `git rm --cached <file>` for each "
            "one, commit that removal, then retry."
        )


def check_git_guard() -> None:
    """CLI entry point: `python -m job_intel_scraper.git_guard`. Exits
    non-zero with a clear message on failure, prints a confirmation on
    success, so it can be run standalone before a manual commit."""
    try:
        run_guard()
    except GitGuardError as exc:
        print(f"[git_guard] {exc}", file=sys.stderr)
        sys.exit(1)
    print(
        "[git_guard] OK — all protected patterns are in .gitignore and none "
        "are tracked."
    )


if __name__ == "__main__":
    check_git_guard()
