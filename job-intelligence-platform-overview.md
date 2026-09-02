# Job Intelligence Platform — Technical Overview (Revised)

> Revision note: the original draft described the platform as built for "a single,
> non-negotiable geographic constraint," while the scoring section already referred
> to "jurisdiction-specific eligibility signals" (plural). That was an internal
> inconsistency, not just a wording gap — with three simultaneous target countries
> (Vietnam, Netherlands, Australia) now in scope, a single hardcoded jurisdiction
> would silently mis-score two of every three markets. This revision fixes that and
> adds the signals a real multi-country job search needs: work-authorization
> detection, language-requirement detection, per-country job boards, and
> occupation/visa-pathway awareness. Sections changed from the original are marked.

A domain-aware job discovery and application-assistance platform built to search
**multiple, explicitly-configured target jurisdictions at once**, with an emphasis
on genuine reliability over feature breadth: every scraper, every LLM call, and
every automated action is deliberately gated, cached, and cost-conscious.
*(Changed: "single, non-negotiable geographic constraint" → multi-jurisdiction,
since eligibility rules, job boards, and language norms differ per country and
must be evaluated independently, not collapsed into one constraint.)*

## What it does

The system discovers job postings directly from company career sites (not just
aggregators), scores each one against a candidate profile using a two-stage
pipeline, and generates tailored application materials on demand — all through a
local dashboard, with no data leaving the user's machine except to an optional,
client-side-encrypted personal sync location.

## Architecture

**Discovery layer** — direct connectors for 20+ Applicant Tracking Systems
(Workday, Greenhouse, Lever, Oracle Cloud, SmartRecruiters, iCIMS, Taleo,
SuccessFactors, and several bespoke company career-site scrapers), plus a small
number of compliant aggregator integrations, **selected per target country**
*(new)* — e.g. Seek and Indeed.com.au for Australia, Indeed.nl and
NationaleVacaturebank for the Netherlands, VietnamWorks, TopCV, and CareerBuilder.vn
for Vietnam, since many employers in these markets don't run on the big
enterprise ATS platforms at all. Every new scraping target is checked against
`robots.txt` before being built; targets that explicitly disallow bot access are
not scraped, regardless of how the page might otherwise be accessible. A shared
HTTP layer handles retries, exponential backoff, and browser-fingerprint
consistency centrally, rather than duplicating that logic per connector.

**Jurisdiction profiles** *(new section)* — each target country is a config
object, not a hardcoded assumption:
- **Eligibility rule** — what "eligible" means there (self-sponsorship not
  possible, so filter for roles that state or imply visa/work-permit sponsorship;
  flag but don't discard roles that are ambiguous on this).
- **Occupation/visa-pathway hint** — e.g. Australia's skilled-visa pathways key
  off specific ANZSCO occupation codes, not job titles, so a "Program Manager"
  posting needs its actual duties checked against the closest code (Engineering
  Manager, Manufacturing Manager, etc.) rather than assumed eligible from the
  title alone.
- **Language requirement detection** — flags whether a posting requires the
  local language (common in Netherlands postings, less common at MNC/JV sites in
  Vietnam, essentially universal-English expectation in Australia).
- **Local job boards / ATS mix** for that country (see Discovery layer above).
- **Currency** the postings are typically denominated in, for downstream display
  normalization.

**Two-stage scoring** —
1. A fast, free, local TF-IDF/keyword composite scorer runs on every job (title
   match, JD keyword overlap, seniority detection, industry relevance, and
   **per-jurisdiction eligibility signals** — sponsorship/work-permit language
   detection and, where relevant, language-requirement detection *(expanded)*).
2. Jobs that clear a configurable relevance threshold on the JD-match component
   specifically are then passed to an LLM (Google Gemini) for genuine semantic
   JD-to-resume matching — real reasoning about fit, not just keyword density.

This two-stage design exists specifically so the expensive step never runs on
jobs the cheap step has already identified as poor fits. Every LLM-scored job is
cached by URL, so nothing is ever re-scored on a later run unless explicitly
requested — and every call's token usage (prompt, completion, total) is tracked
and surfaced, both per-job and as a running total, so cost is visible rather than
assumed.

**On-demand application materials** — a cover letter is generated only when
explicitly requested for a specific job (never automatically for every match),
grounded strictly in the candidate's actual resume content, and compiled through
a LaTeX toolchain to match a professionally-typeset resume format. Each generated
application is archived — cover letter, the resume version actually used, and a
snapshot of the job posting itself — so the record survives even if the original
listing is later taken down. *(Operational note, not an architecture change: the
resume feeding this pipeline should be free of placeholder text — e.g. a bracketed
`[program/platform name]` left in a bullet — since the LLM will either echo it
verbatim into a cover letter or silently guess a fill-in, both bad outcomes.)*

**Local dashboard** — a lightweight local web server (not a public-facing
deployment) presents scored jobs with both scoring layers visible side by side,
supports on-demand cover letter generation with live status polling, and includes
lightweight application-status tracking (applied / interview / offer / rejected,
with notes and a "days since applied" indicator). **Filterable by target country**
*(new)*, since a candidate running three jurisdictions at once needs to see them
separately, not as one undifferentiated list.

**Optional mobile access** — a static, single-file export of the current job list
can be generated for viewing on a phone, protected with client-side AES-256-GCM
envelope encryption (PBKDF2 key derivation, per-encryption random salt/nonce) so
the exported file is unreadable without a password even if the sync location
isn't fully trusted.

**Automated safety guards** — before every scrape or sync operation, the system
verifies that all personal-data file patterns are correctly excluded from version
control, and — more importantly — that none of them are *already* tracked (since
a `.gitignore` rule alone can't undo a file that was committed before the rule
existed). A failed check hard-stops the operation rather than proceeding with a
silent risk.

## Reliability engineering notes

This system went through several rounds of adversarial, line-by-line code review
rather than being trusted at face value after each change. That process caught
and fixed a systematic class of bug where several newly-added scrapers were
silently returning zero results — not from a network or anti-bot issue, but from
an internal data-contract mismatch that was easy to introduce and easy to miss
without full-file verification. The fix wasn't just patching the symptom; it
involved re-auditing every connector against the same failure pattern, confirming
the shared HTTP layer's anti-bot handling was actually being invoked where
expected, and closing the loop with automated regression checks that get re-run
on every review pass.

Other resilience decisions worth noting:
- SQLite access uses WAL mode with an explicit busy-timeout, since the dashboard,
  the scraping pipeline, and the sync process can all touch the same database
  independently.
- A hard ceiling on both job count and total token spend per LLM-scoring run
  exists specifically so a large scrape can never silently consume an entire
  day's API quota. **With three jurisdictions running, this ceiling should be
  set per-country as well as globally** *(new)* — otherwise one large market
  (e.g. Australia, with heavier Seek/Indeed volume) can consume the entire run's
  budget before the other two countries are scored at all.
- Manual, ToS-sensitive data sources (certain professional networks) are
  deliberately excluded from automation entirely — supported instead through a
  manual, on-demand workflow where the user browses and pastes in what they find,
  which then runs through the identical scoring pipeline as anything scraped
  automatically.
- Platforms whose `robots.txt` explicitly disallows automated access are
  permanently excluded, full stop, not worked around.

## Tech stack

Python (scraping, scoring, orchestration), SQLite (persistence), Flask (local
dashboard), Google Gemini API (semantic matching and cover letter drafting),
XeLaTeX (document generation), vanilla JS + Web Crypto API (client-side encrypted
export).

## Explicit non-goals

- No automated scraping of any platform whose terms of service or `robots.txt`
  prohibit it.
- No LLM calls beyond what's strictly gated and budgeted — this is not a system
  that scores everything with an LLM by default.
- No cloud hosting or third-party data sharing — the dashboard and database are
  local-only by design; the only optional external surface is a personal,
  encrypted, user-controlled sync target.
- No assumption that a job posting's stated location implies the candidate is
  legally eligible to take it *(new)* — eligibility is a detected/flagged signal,
  never an inferred yes.
