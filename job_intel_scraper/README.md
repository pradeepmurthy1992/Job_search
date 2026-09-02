# Job Intelligence Scraper — skeleton

A working starting point for the discovery + two-stage scoring half of the
platform described in `job-intelligence-platform-overview.md`, wired for
three target jurisdictions: Vietnam, Netherlands, Australia. Candidate
stance baked into `config.py`: employer-sponsorship-only in all three
countries, candidate age 35 (so the Dutch under-30 HSM rate never applies),
and Australia scoped beyond pure automotive per the 2026-09 expansion note.

## What's real vs. what's a stub

**Real / runnable:**
- `robots_check.py` — enforces the "never scrape a disallowed target" rule
  for every connector, fails closed if robots.txt can't even be fetched.
- `connectors.py` — actual HTTP calls against the public Greenhouse, Lever,
  Workable, and Recruitee JSON APIs. Works as soon as you add real board
  tokens in `config.py` (two are already filled in from research — see
  "Verified target companies" below).
- `eligibility.py` — keyword-based sponsorship / citizenship-restriction /
  language-requirement detection, kept as a separate visible signal from the
  fit score on purpose.
- `scorer.py` — stage-1 keyword-weighted composite score using Pradeep's
  actual resume keywords (title, domain, tools, methodology, seniority),
  now including mining/rail/infrastructure terms for the AU sector expansion.
- `db.py` — SQLite with WAL mode + busy_timeout, matching the platform's
  concurrency notes.
- `llm_client.py` — stage-2 semantic scoring, **pluggable between two
  genuinely free backends**: Google Gemini's free tier (no credit card, ~1,500
  requests/day on Flash models) or a fully local Ollama model (zero cost,
  zero rate limit, nothing leaves the machine). See "Which LLM backend"
  below before picking one.
- `main.py` — CLI orchestrator: discovery → stage-1 → eligibility for every
  configured country, with `--stage2` to also run LLM scoring, enforcing the
  per-country token ceiling and never re-scoring a cached job.

**Stubbed, on purpose:**
- Local job-board connectors (Seek, Indeed.nl, VietnamWorks, TopCV, etc.) —
  each needs its own robots.txt/ToS review before a scraper gets written
  against it; they're listed in `config.py` as a checklist, not implemented,
  so nothing gets built without that review actually happening. For
  Australia especially, treat this as the priority gap: most real target
  employers there (mining/rail/infrastructure corporates) run Workday or
  SuccessFactors, which neither this skeleton nor a lightweight JSON API
  covers — Seek/Indeed scraping is the realistic near-term path.
- The Flask dashboard, LaTeX cover-letter pipeline, AES-256-GCM mobile
  export, and git-tracked-secrets guard from the platform overview aren't
  part of this skeleton — this covers discovery + two-stage scoring +
  eligibility only.

## Which LLM backend should you use?

You asked whether a paid Gemini key is even needed — it isn't:

- **Gemini free tier** (`JOB_INTEL_LLM_BACKEND=gemini`): sign up at
  https://aistudio.google.com/apikey — genuinely free, no credit card, as of
  Sep 2026 gemini-2.5-flash gives ~15 requests/minute and 1,500/day, which a
  150–250-job-per-run ceiling will never come close to hitting. The one real
  tradeoff: Google's free-tier terms allow using your inputs for model
  training, which cuts against this platform's own "nothing leaves the
  machine" design goal. Fine for a personal job search; know it's happening.
- **Local Ollama** (`JOB_INTEL_LLM_BACKEND=ollama`, the default): install
  from https://ollama.com, then `ollama pull qwen2.5:7b` (comfortable on
  16GB RAM) or a smaller model like `gemma2:4b` on 8GB machines. Completely
  free, no rate limit, no data ever leaves your laptop — actually the better
  philosophical fit for this platform than the cloud option. Slightly less
  sharp at nuanced JD-to-resume reasoning than Gemini 2.5 Flash, and slower
  per call on modest hardware, but there's no quota to run out of.

Set the env var and (for Gemini) `GEMINI_API_KEY` before running with
`--stage2`. Nothing else in the codebase needs to change to switch backends.

## Verified target companies (from web research, Sep 2026)

Real research, not invented tokens — and it turned up less than expected,
which is itself useful information:

- **Fastned (Netherlands)** — EV charging infrastructure (not vehicle
  manufacturing, but a genuine adjacent-sector fit for program/cost-
  engineering background). Confirmed on **Recruitee** at
  `fastned.recruitee.com`. High confidence — found directly in search
  results as the company's own domain. Pre-filled in `config.py`.
- **Applied EV (Australia)** — Melbourne autonomous/electric commercial-
  vehicle platform maker. Found recruiting via **Workable** at
  `apply.workable.com/applied-ev`. Medium confidence — confirm the exact
  account slug against the live careers page before relying on it. Pre-
  filled in `config.py`.
- **Vietnam** — no automotive/EV employer was confirmed on Greenhouse,
  Lever, Workable, or Recruitee. Selex Motors (the most plausible EV
  scale-up match) recruits via Facebook/ITviec/LinkedIn, not a scrapable
  public ATS API. Vietnam discovery will have to lean on local job boards
  (VietnamWorks, TopCV, CareerBuilder.vn) rather than direct ATS connectors.
- **Tritium and SEA Electric (Australia)** — both real EV-adjacent
  companies, but found on Employment Hero / bespoke career sites, not any
  of the four ATS platforms this skeleton connects to.

Bottom line: Greenhouse/Lever/Workable/Recruitee cover a real but small
slice of these three markets — mostly scale-ups, not the larger corporates.
Don't expect this connector set alone to surface most of the actual job
volume; it's a genuinely-working start, not full coverage.

## Setup

```bash
pip install -r requirements.txt
```

Add real board tokens for your target companies into `config.py`'s
`JURISDICTIONS` dict as you find them — check a company's careers page URL
for `greenhouse.io`, `lever.co`, `workable.com`, or `recruitee.com` in it.

## Run

```bash
python -m job_intel_scraper.main --countries VN NL AU
```

Stage 1 + eligibility only, one country:

```bash
python -m job_intel_scraper.main --countries AU --limit 50
```

Stage 1 + eligibility + stage-2 LLM scoring:

```bash
export JOB_INTEL_LLM_BACKEND=ollama   # or "gemini" + GEMINI_API_KEY
python -m job_intel_scraper.main --countries NL --stage2
```

Results land in `jobs.db` (SQLite) — columns include stage-1 score breakdown,
eligibility verdict/note, and llm_score/llm_reasoning once stage 2 has run.

## Before you rely on this for real applications

1. Confirm the actual ANZSCO occupation-code fit for Australia and re-check
   the NL Highly Skilled Migrant salary threshold each hiring season — both
   are noted as "verify before trusting" in `config.py`'s `visa_note`
   fields, since both change and neither should be silently assumed correct.
2. ~~Fix the `[program/platform name]` placeholder bracket in the resume~~ —
   done; see `Pradeep_Moorthy_Resume_Fixed.docx` delivered alongside this
   skeleton.
3. Add and individually review the local job-board connectors (Seek,
   Indeed.nl, VietnamWorks, etc.) — the four ATS platforms wired up here
   cover real but limited ground in these three markets, per the research
   notes above.
4. Confirm the Applied EV Workable slug and consider adding more discovered
   companies as you find them — this list will only grow through the same
   kind of manual verification, not guessing.
