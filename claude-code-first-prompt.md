# First prompt to paste into Claude Code

Run this from `G:\CLAUDE\Jobs` (`cd G:\CLAUDE\Jobs` then `claude`). Paste the
whole block below as your first message.

---

Read `job-intelligence-platform-overview.md` and `build-prompt.md` in this
folder — they define the architecture and the per-country requirements
(Vietnam, Netherlands, Australia; employer-sponsorship-only; Australia scope
expanded beyond pure automotive). Then look at the existing
`job_intel_scraper/` package: it already has working jurisdiction config,
eligibility detection, Greenhouse/Lever/Workable/Recruitee connectors, the
stage-1 scorer, SQLite persistence, and a pluggable Gemini/Ollama stage-2
client. Extend this codebase — don't rewrite what's already there.

**Part 1 — Git and GitHub setup**

1. Check whether this folder is already a git repo (`git status`). If not,
   run `git init`.
2. Create or update `.gitignore` to exclude: `job_intel_scraper/jobs.db`,
   `job_intel_scraper/jobs.db-*`, `.env`, `*.pdf`,
   `Pradeep_Moorthy_Resume_Fixed.docx`, `__pycache__/`, `*.pyc`, `venv/`.
   My resume and the scraped-jobs database must never be committed — this
   matches the platform overview's own personal-data git-tracking guard, so
   treat this as a hard requirement, not a suggestion.
3. Before the first commit, run `git status` and show me exactly which files
   are staged — I want to eyeball the list before anything goes to GitHub.
4. My GitHub repo is: https://github.com/pradeepmurthy1992/Job_search
   Add it as the `origin` remote. Check first whether it already has any
   commits (e.g. a README created via the GitHub UI) — if it does, pull with
   `--allow-unrelated-histories` and resolve any conflicts rather than
   force-pushing over it. If `git push` fails because you're not
   authenticated, stop and tell me — don't try to work around it. I may need
   to run `gh auth login` first.
5. Once pushed, confirm the repo on GitHub actually shows the expected files
   and that `jobs.db`, `.env`, and the resume are NOT present there.

**Part 2 — Build, in this order**

1. The personal-data git-tracking guard described in the platform overview:
   before every scrape/sync, verify the excluded patterns are both (a) in
   `.gitignore` and (b) not already tracked from a prior commit — a
   `.gitignore` rule alone can't undo a file that's already committed. Hard-
   stop the operation if this check fails.
2. The resume data-contract check: fail loudly before any cover-letter
   generation if the resume text contains placeholder markers like `[[`,
   `[TBD]`, etc. (My resume is already fixed — `Pradeep_Moorthy_Resume_Fixed.docx`
   — but this check should exist regardless so it never silently regresses.)
3. The local Flask dashboard: scored jobs with both scoring layers visible,
   a country filter (VN/NL/AU, viewable separately or combined), and
   application-status tracking (applied/interview/offer/rejected, notes,
   days-since-applied).
4. Wire up the LaTeX cover-letter generation pipeline, on-demand only, per
   the overview.

**Ground rules**

- Ask me before adding any new external dependency, or before making an
  architecture choice that build-prompt.md hasn't already decided.
- Never commit `jobs.db`, `.env`, or any resume file — confirm this before
  every commit, not just the first one.
- If robots.txt disallows a target, don't build a scraper for it — no
  exceptions, per the existing platform rule.
