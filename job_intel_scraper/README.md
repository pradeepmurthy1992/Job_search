# Job Intelligence Scraper — skeleton

A working starting point for the discovery + two-stage scoring half of the
platform described in `job-intelligence-platform-overview.md`, wired for
eight target jurisdictions: Vietnam, Netherlands, Australia (original
scope), plus United States, United Kingdom, Germany, United Arab Emirates,
and Singapore (all added Sep 2026 per user request). Candidate stance
baked into `config.py`: employer-sponsorship-only in ALL EIGHT countries —
no self-funded/independent visa pathway anywhere, no exception (this
specifically excludes the UAE's self-sponsored Golden Visa route even
though the candidate's likely salary would qualify). Candidate age 35 (so
the Dutch under-30 HSM rate never applies). Each country's `visa_note` in config.py
is real, researched immigration-rule detail (current 2026 salary
thresholds, sponsorship mechanics, real sponsorship/restriction phrases
found in live postings where possible) — never invented, matching the
rigor of the original NL Highly Skilled Migrant threshold research.

## Self-audit fixes (Sep 2026)

Three real gaps found by re-reading the codebase against the platform
overview's own stated requirements, not hypothetical — each reproduced
against real data before being fixed:

1. **No global LLM-token ceiling across a multi-country run.** The
   platform overview explicitly calls for this ("should be set per-country
   as well as globally... otherwise one large market can consume the
   entire run's budget"), and a comment in `config.py` referenced it, but
   it was never actually implemented — only the per-country ceiling was.
   With 7 countries' per-country ceilings summing to ~1.45M tokens, a
   single `--stage2` run had nothing stopping it from spending all of it.
   Added `GLOBAL_MAX_LLM_TOKENS_PER_RUN` (config.py) and wired it into
   `main.py`'s `run()` — it stops the ENTIRE run, not just one country,
   once hit, whether that happens mid-country or before a later country's
   turn even starts. Verified with an isolated synthetic test covering
   both cases.
2. **LLM token spend was tracked but never surfaced anywhere.** `run_ledger`
   recorded it correctly, but the dashboard had zero visibility into it —
   directly contradicts the overview's "cost is visible rather than
   assumed" requirement. Added a "LLM tokens used (all-time)" KPI card,
   per-job token counts next to the stage-2 score, and a `/usage` detail
   page (`db.get_usage_summary()` / `db.get_recent_runs()`) showing every
   run's country, jobs fetched/scored, and token spend.
3. **A job matching multiple target countries only ever showed up under
   one of them.** The database key (`source:board:external_id`) doesn't
   include country, and `country_hint` is (deliberately) never overwritten
   on conflict — so a job whose location genuinely fits two target
   countries (e.g. a "Remote - Europe" role) got silently attributed to
   whichever country's scrape happened to run first in the CLI argument
   order, and was invisible on every other matching country's tab (though
   still visible under "ALL"). Confirmed this wasn't hypothetical: 4 real
   Waymo postings match both US and GB. Fixed with a new
   `matched_countries` column, merged atomically inside the same
   `INSERT ... ON CONFLICT` statement `upsert_job` already used (no
   separate read-before-write needed) — one row per physical posting,
   visible on every country tab it legitimately matches, with a single
   shared application-status/notes/LLM-score record (not duplicated per
   country). Existing rows backfilled from `country_hint` automatically on
   migration.
4. **`get_unscored_candidates` had no priority ordering and still filtered
   on `country_hint` instead of `matched_countries`.** Fixed alongside #3
   — stage-2 candidates are now processed best-stage1-score-first (so a
   token ceiling that stops the loop partway through has already spent
   its budget on the strongest matches) and considered under every
   country a job matches, not just its first-seen one.
5. **The stage-2 gate itself only looked at the 'domain' keyword category,
   not the blended score.** This was the most consequential bug: it
   required ~5+ literal automotive-jargon hits (OEM/Tier-1/BOM/PLM/ECN)
   just to reach stage-2, which systematically excluded exactly the
   adjacent-sector companies the whole multi-country domain-expansion
   strategy was built to find. Live-verified: only 9 of 586 real jobs
   (1.5%) cleared it, and AirTrunk's "Senior Project Manager" — a
   near-perfect title match (28.1/30) and the #5 stage-1 result overall —
   scored domain=6.0 (need 13.5) since a data-centre developer's JD
   doesn't use automotive vocabulary at all, and never got an LLM look.
   `scorer.clears_llm_threshold_from_total_score()` now gates on the
   blended stage1_score total instead, letting a strong title/
   methodology/seniority match compensate for sparse domain jargon — the
   default threshold (45.0) was picked to land near the real top-10%
   cutoff (44.1) observed across the dataset, not an arbitrary number.
6. **`resume_summary.txt` (fed to every stage-2 prompt) still said "Vietnam,
   the Netherlands, or Australia" only** — never updated when US/UK/
   Germany/UAE were added. This was actively corrupting the first stage-2
   run under the new gate: the LLM correctly-but-wrongly flagged 6 of 9
   scored jobs for "geographic mismatch" against countries the candidate
   now explicitly wants included. Fixed and every affected score was
   reset and re-run with the corrected profile (scores moved up
   meaningfully once the stale penalty was gone — e.g. one Waymo role
   went from 55/100 to 88/100 on the exact same job).
7. **No retry/backoff on Gemini rate-limit responses.** Fixing #5 (many
   more real candidates now qualify for stage-2 per run) immediately
   saturated Gemini's free-tier ~15 req/min limit live — most calls in
   that run failed outright with 429 and were simply skipped rather than
   paced, wasting the run instead of just taking longer. Added
   `_post_gemini_with_retry()` (exponential backoff, honors `Retry-After`
   when the API sends one) and wired it into all three `GeminiClient`
   methods.

## What's real vs. what's a stub

**Real / runnable:**
- `robots_check.py` — enforces the "never scrape a disallowed target" rule
  for every connector, fails closed if robots.txt can't even be fetched.
  Uses `protego` (Scrapy's robots.txt library), not the stdlib
  `urllib.robotparser` — the stdlib parser doesn't implement the `*`/`$`
  wildcard extension real sites rely on (observed live: it silently
  misread Seek's `Disallow: */job/` as never matching anything, which
  would have let a genuinely-disallowed path through) and also chokes on a
  robots.txt served with a leading UTF-8 BOM (observed on
  vietnamworks.com), which this module strips before parsing.
- `connectors.py` — actual HTTP calls against the public Greenhouse, Lever,
  Workable, and Recruitee JSON APIs, with real board tokens for Fastned,
  Allego, GreenFlux, Eneco eMobility (NL, Recruitee — Allego is
  white-labeled at `join.allego.eu`, not `<slug>.recruitee.com`), and
  Applied EV, Zoomo (AU, Workable) — see "Verified target companies"
  below. Also captures posting date and, where the source provides it
  (Recruitee), a structured salary field. A company's board can span
  multiple countries (observed live: Zoomo's Workable feed returned UK
  roles under an Australia-focused search) — `fetch_all()` drops any job
  whose actual location doesn't match the jurisdiction being fetched,
  using a structured country code from the source when available and
  free-text keyword matching otherwise.
- `salary.py` — approximate pay-in-USD/month, checking each source's
  structured salary field first (Recruitee provides one) and falling back
  to regex extraction from the JD text otherwise. Never estimates a figure
  for a posting that doesn't state one ("not disclosed", not a guess), and
  guards against real false positives found during testing — a bare
  currency+number+period match can hit a training budget or a revenue
  figure instead of an actual salary (Fastned's "training and development
  budget of €3,000 per year" matched the naive pattern before this was
  fixed), so extraction rejects matches near non-salary context words
  (budget, bonus, revenue, funding, allowance, etc.) and applies a
  plausibility floor/ceiling. FX rates are a static, manually-maintained
  table (`FX_TO_USD`) — no live-rate API, so no new dependency; re-check
  periodically, same pattern as the NL visa threshold in `config.py`.
- `manual_job.py` — the platform overview's documented manual-paste
  workflow for sources that can't be automated (see below): runs pasted
  postings through the identical scorer/eligibility/salary pipeline as a
  scraped job.
- `company_discovery.py` — automates the periodic research pass that
  manually found Allego/GreenFlux/Eneco eMobility/Zoomo: prompts Gemini
  with search grounding (`tools: [{"google_search": {}}]`) for companies
  in each country's target sectors that use one of the 4 connected ATS
  platforms, then **independently verifies every candidate** by actually
  calling the real endpoint via `connectors.py` — an LLM-guessed slug that
  returns nothing is reported as unverified, never silently trusted.
  Prints a report; never writes to `config.py` directly, since sector-fit
  judgment on a new company still needs a human look, same as every
  existing board token there. Needs `GEMINI_API_KEY` (Ollama has no
  search-grounding tool):
  ```bash
  export GEMINI_API_KEY=your-key-here
  python -m job_intel_scraper.company_discovery --countries VN NL AU
  ```
  **Live-confirmed caveat (Sep 2026):** the `google_search` grounding tool
  hits a 429 quota error on a bare free-tier key — plain text generation
  works fine, but grounding needs billing enabled on the Google Cloud
  project behind the key to get usable quota. Until then, ask Claude Code
  to run a research pass instead (free, uses its own search tools) — that's
  how Allego/GreenFlux/Eneco eMobility/Zoomo were actually found.
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
  per-country token ceiling and never re-scoring a cached job. Runs the
  personal-data git-tracking guard (`git_guard.py`) as a hard-stop pre-flight
  check before every run.
- `git_guard.py` — the "never let a `.gitignore` rule alone undo a prior
  commit" guard from the platform overview. Checks both halves: that every
  protected pattern (jobs.db, .env, the resume, the cover-letter archive) is
  actually in `.gitignore`, and that none of them are already tracked by
  git. Run standalone with `python -m job_intel_scraper.git_guard` before
  every commit.
- `resume_contract.py` — the resume data-contract check: extracts text from
  `Pradeep_Moorthy_Resume_Fixed.docx` (via `python-docx`) and fails loudly
  (`ResumeContractError`) if it finds leftover placeholder markers (`[[`,
  `[TBD]`, `[program/platform name]`-shaped brackets, etc.) before any
  cover-letter generation is allowed to proceed.
- `dashboard.py` + `templates/dashboard.html` — the local Flask dashboard:
  both scoring layers side by side, the eligibility signal as its own
  visible column (never blended into a score), a VN/NL/AU country filter,
  application-status tracking (applied/interview/offer/rejected, notes,
  days-since-applied), an on-demand "Generate Cover Letter" button per job
  with live status polling, and a filter bar (posted-within, location,
  company, min match %, sponsorship verdict, min salary) backed by real
  SQL filtering in `db.list_jobs()`, not client-side JS. KPI cards up top
  (total jobs, avg match %, avg stated salary, sponsorship-confirmed
  count) and an "Add a job manually" form wired to `manual_job.py`.
- `cover_letter.py` — on-demand LaTeX cover-letter generation, triggered
  only for one specific job at a time (never automatically for every
  match). Runs the git-tracking guard and the resume data-contract check
  first, drafts the letter body via the configured LLM backend
  (`llm_client.draft_cover_letter`), renders it into
  `latex/cover_letter_template.tex`, and attempts to compile with `xelatex`
  — if `xelatex` isn't installed or fails, the `.tex` source and the rest of
  the archive are still written, and the failure is reported rather than
  silently swallowed. Each generation is archived under
  `job_intel_scraper/applications/<job_id>/<timestamp>/`: the `.tex` (and
  `.pdf` if compiled), the resume version actually used, a JSON snapshot of
  the job posting, and generation metadata (LLM backend, token counts,
  compile status) — so the record survives even if the original listing is
  later taken down. This archive directory is gitignored and covered by
  `git_guard.py`, same sensitivity class as the resume itself.

**Evaluated and deliberately NOT automated (use the manual-paste form instead):**
- **Seek.com.au, Indeed.com.au, Indeed.nl, TopCV.vn** — robots.txt actually
  *permits* their search-listing pages (checked with `protego`, correctly
  this time), but their real servers return HTTP 403 to an honestly-
  identified bot regardless — infrastructure-level blocking, not a
  robots.txt matter. Not worked around (no browser fingerprint spoofing,
  no proxy rotation) — same "not an exception" policy as robots.txt itself.
- **VietnamWorks** — robots.txt allows it and the server doesn't block the
  request, but its job listings only materialize via client-side
  JavaScript after page load (no server-rendered content, no discoverable
  JSON API) — would need a full headless-browser dependency to automate,
  which is out of scope here.
- **CareerBuilder.vn** — TLS certificate is expired; can't be fetched over
  HTTPS at all regardless of policy.
- For all of the above, `manual_job.py` + the dashboard's "Add a job
  manually" form is the intended path: browse it yourself, paste the
  URL/title/company/location/description, and it scores identically to a
  scraped job. This is the platform overview's own documented answer for
  exactly this situation, not a new design decision.

**Still stubbed:**
- The AES-256-GCM mobile export from the platform overview isn't part of
  this codebase yet.

**Also real / runnable now:** the Flask dashboard (`dashboard.py`), the
resume data-contract check (`resume_contract.py`), the on-demand LaTeX
cover-letter pipeline (`cover_letter.py`), and the personal-data
git-tracking guard (`git_guard.py`) — see their entries above. Cover-letter
PDF compilation needs `xelatex` on PATH (MiKTeX or TeX Live); without it,
the `.tex` source is still generated and archived, just not compiled.

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
- **Allego (Netherlands)** — EV charging infrastructure (Arnhem). Confirmed
  on **Recruitee**, white-labeled at `join.allego.eu` (not the default
  `<slug>.recruitee.com` pattern — `config.py`'s `recruitee_custom_domains`
  handles this). High confidence, live-verified. A different, unrelated US
  company also named "Allego" is on Workable at
  `apply.workable.com/allego-1` — confirmed NOT the same company; don't
  reuse that slug.
- **GreenFlux (Netherlands)** — EV charge-point management SaaS
  (Amsterdam). Confirmed on **Recruitee** at `greenflux.recruitee.com`.
  High confidence. Careers page explicitly advertises visa sponsorship and
  relocation compensation for expats.
- **Eneco eMobility (Netherlands)** — smart EV charging (NL/BE/LUX).
  Confirmed on **Recruitee** at `enecoemobility.recruitee.com`. High
  confidence. Several roles state a real structured salary (EUR/month).
- **Applied EV (Australia)** — Melbourne autonomous/electric commercial-
  vehicle platform maker. Confirmed on **Workable** at
  `apply.workable.com/applied-ev` — live-reverified Sep 2026, but currently
  has **zero** open roles on this feed; kept configured since that changes.
- **Zoomo (Australia-founded, now global)** — light EVs (e-bikes/scooters)
  for last-mile delivery fleets. Confirmed on **Workable** at
  `apply.workable.com/zoomo`. High confidence, but its feed is NOT
  country-filtered — currently only has UK-based roles open, which
  `fetch_all()`'s location filter correctly excludes from the AU results
  rather than mislabeling them.
- **NTS Group (Netherlands)** — high-tech precision manufacturing/
  mechatronics (Brainport Eindhoven cluster), building systems supplier
  for semiconductor/life-sciences/defense OEMs. Confirmed on **Recruitee**
  at `nts.recruitee.com`. High confidence, live-verified: 50 of 65
  postings are NL-based, including multiple Project/Program Manager and
  Category/Supplier Manager roles. Not automotive-branded, but the same
  QLTC (Quality/Logistics/Technology/Cost) discipline as VAVE/NPI —
  currently the single strongest NL vein by volume.
- **Rocsys (Netherlands)** — robotic EV/truck charging automation
  (Rijswijk). Confirmed on **Recruitee** at `rocsys.recruitee.com`. High
  confidence: 4 of 5 postings NL-based.
- **LeydenJar Technologies (Netherlands)** — silicon-anode battery
  manufacturing scale-up (Eindhoven/Leiden). Confirmed on **Recruitee** at
  `leydenjar.recruitee.com`. High confidence: 6 of 6 postings NL-based,
  including a live "Senior Program Manager" role.
- **Milence (Netherlands)** — heavy-duty truck charging network (JV of
  Daimler Truck/Traton/Volvo Group). Confirmed on **Recruitee**,
  white-labeled at `jobs.milence.com`. High confidence, but currently only
  1 open role.
- **ChargePoint (Netherlands)** — global EV charging infrastructure,
  Amsterdam office. Confirmed on **Greenhouse** at
  `boards.greenhouse.io/chargepoint`. High confidence, but currently only
  1 of 31 postings is Amsterdam-based — low volume for a large employer,
  worth re-checking periodically.
- Two "obvious" next EV-charging names for NL were checked and **ruled
  out**: Shell Recharge Solutions/NewMotion and Eneco's parent
  (non-eMobility) brand both recently abandoned Recruitee — their
  subdomains now redirect to Recruitee's "not hosted" page. Don't re-add
  without re-verifying first. Battolyser Systems (battery/electrolyser
  cleantech) is genuinely Recruitee-hosted but currently 404s — worth a
  periodic re-check, not added yet.
- **Axon (Vietnam)** — public-safety hardware (body cameras, TASERs), Ho
  Chi Minh City site. Not automotive-branded, but genuinely the same
  NPI/manufacturing Program Management discipline. Confirmed on
  **Greenhouse** at `boards.greenhouse.io/axon`. High confidence,
  live-verified: dozens of HCMC-based postings including "Employee
  Experience Program Manager II" and "Engineering Manager, Connected
  Devices." The single best functional match found for Vietnam despite
  the domain mismatch — same reasoning as the AU sector expansion.
- **Universal Electronics Inc. / UEI (Vietnam)** — consumer-electronics
  contract manufacturer, Hai Duong City factory. Confirmed on **Lever** at
  `jobs.lever.co/uei`. High confidence, live-verified: 7 of 17 postings
  are Hai Duong-based, including "NPI Electronics Engineer" — direct
  NPI/manufacturing-engineering overlap.
- **One Mobility Group (Vietnam)** — automotive sensor/connectivity/
  electrification solutions, operates in 13 countries incl. Vietnam.
  Confirmed on **Recruitee** at `onemobility.recruitee.com`. Direct
  domain fit, though currently only 1 of 25 postings is Vietnam-based.
- **Ajax Systems (Vietnam)** — IoT security/alarm systems with a real,
  large new Hanoi manufacturing plant. Genuinely confirmed on **Lever**
  (`jobs.lever.co/ajax`), but had **zero** Vietnam-tagged postings when
  checked — not added to config to avoid an always-empty board; worth
  re-checking periodically since the factory is real and growing.
- VietnamWorks was separately evaluated as a scraping target (see
  "Evaluated and deliberately NOT automated" above) and isn't automatable
  without a headless-browser dependency — use the manual-paste form for
  anything not covered by the companies above.
- **AirTrunk (Australia)** — hyperscale data-centre developer, Sydney HQ.
  Confirmed on **Greenhouse** at `boards.greenhouse.io/airtrunk`. High
  confidence, live-verified: 33 of 79 postings are AU-tagged
  (Sydney/Melbourne/Western Sydney), including direct title matches —
  Commercial Manager, Cost Manager (x2), Senior Project Manager, Program
  Manager, Design Manager. Not automotive, but the strongest AU find so
  far — infrastructure/construction program delivery at this scale is a
  close functional match for VAVE/cost-engineering/program-management.
- **Bradken (Australia)** — mining/heavy-equipment wear-parts
  manufacturer. Confirmed on **Greenhouse** at
  `boards.greenhouse.io/bradken` (its public careers page is hosted at
  `job-boards.eu.greenhouse.io/bradken`, but the underlying API is on the
  same standard host — no special handling needed). High confidence: 9 of
  43 postings AU-tagged, including "Management Cost Accountant" (Perth).
- **Emesent (Australia)** — autonomous drone/mapping tech for underground
  mining, Brisbane. Confirmed on **Lever** at `jobs.lever.co/Emesent`
  (note: case-sensitive slug, capital E — lowercase 404s). High
  confidence: 9 of 9 postings are 100% Brisbane-based.
- **Relectrify (Australia)** — Melbourne battery-storage/EV-adjacent
  scale-up. Confirmed real on **Workable** at
  `apply.workable.com/relectrify`, currently zero open roles — kept
  configured on the same "empty now, re-check later" logic as Applied EV.
- Aurecon, WSP Australia, GHD, AECOM, and Jacobs (the major AU
  infrastructure/engineering consultancies) were checked and definitively
  ruled out: Workday, Oracle Recruiting Cloud, Oracle Recruiting Cloud,
  SmartRecruiters, and Avature respectively — none scrapable by this
  system. Also ruled out with direct evidence this round: Downer EDI Rail
  (Oracle), UGL Rail (Oracle Taleo), Alstom Australia/Komatsu
  Australia/Liebherr Australia (all SAP SuccessFactors), Novonix
  (Dayforce), Sun Metals (Elmo Talent), Beca/SMEC (Workday), Calibre
  Group (LiveHire), Advanced Navigation (Rippling ATS), Seeing Machines
  (Teamtailor), Baraja (SwagApp). Redflow entered liquidation in 2024/25 —
  remove from consideration entirely, not just an ATS mismatch.
- Every purely automotive/EV manufacturing multinational checked for
  Vietnam (Denso, ZF, Aptiv, Hyundai Mobis, Yazaki, Continental, plus
  Intel/Samsung/Foxconn/LG/Jabil/Flex/Benchmark/Sanmina/Celestica on the
  semiconductor/EMS side) runs Workday, SuccessFactors, or a proprietary
  portal — a consistent pattern across two full research rounds, not an
  absence-of-evidence gap. Vietnam's real yield on these 4 platforms
  comes from newer VC-backed hardware/deeptech companies with a Vietnam
  engineering office (the pattern behind Axon/UEI/One Mobility), not
  legacy manufacturers — worth remembering when deciding where to spend a
  future research pass.

### Singapore (added Sep 2026)

No automotive OEM/Tier-1 presence at all on these 4 platforms (Singapore
has no local vehicle manufacturing) — confirmed absent via direct token
checks for Bosch, Continental, ZF, Denso, ST Engineering, SIA Engineering,
Rolls-Royce, Safran, Collins Aerospace, and others.

- **Portcast (Singapore)** — Singapore-HQ logistics/freight-AI startup.
  Confirmed on **Lever** at `jobs.lever.co/portcast`. Strongest single
  find: 4 of 9 postings Singapore-tagged, including a literal "Technical
  Program Manager" role.
- **Moloco (Singapore)** — AdTech/AI with a real Singapore APAC office.
  Confirmed on **Greenhouse** at `boards.greenhouse.io/moloco`. 3 of 46
  postings SG-tagged, including "GTM Program Manager."
- **Xendit (Singapore)** — Indonesia-founded fintech with real SEA/
  Singapore operations. Confirmed on **Greenhouse** at
  `boards.greenhouse.io/xendit`. 7 of 24 postings include Singapore among
  eligible locations (multi-city postings); no PM title live yet.
- **Ninja Van (Singapore)** — Singapore-HQ logistics/last-mile delivery
  unicorn. Confirmed on **Lever** at `jobs.lever.co/ninjavan`. 13 of 157
  postings SG-tagged; currently driver/warehouse/sales-ops roles only, no
  PM titles live, but a large active board worth monitoring.
- Confirmed real but currently zero open postings (same "verified real,
  re-check periodically" treatment as Ajax Systems/VDL ETG elsewhere):
  **Beam Mobility** and **Neuron Mobility** (both Singapore-founded
  e-scooter/micromobility EV companies, Workable), **GlobalFoundries** and
  **Infineon** (real Singapore semiconductor operations, Workable).
  **Crown Equipment** (material-handling/forklift manufacturer, states a
  Singapore regional HQ, Workable "crown-equipment") has 68 live postings
  but all currently Australia-tagged, zero Singapore.
- The COMPASS points-based Employment Pass framework (in effect since Sep
  2023) makes Singapore genuinely different from every other target
  country's eligibility signal: clearing the salary floor is necessary but
  not sufficient — two of the six scoring criteria (the employer's own
  local-hiring track record, workforce-nationality diversity mix) are
  invisible from a job posting and outside the candidate's control. See
  `config.py`'s SG `visa_note` for the full breakdown, including the SGD
  22,500/month threshold that exempts an offer from COMPASS scoring
  entirely, and why "open to Singaporeans and PRs" is routine Fair
  Consideration Framework compliance language that commonly coexists with
  active sponsorship — not the hard restriction it would be almost
  anywhere else.
- **Tritium and SEA Electric (Australia)** — both real EV-adjacent
  companies, but found on Employment Hero / bespoke career sites, not any
  of the four ATS platforms this skeleton connects to.

Bottom line: Greenhouse/Lever/Workable/Recruitee cover a real but small
slice of these three markets — mostly scale-ups, not the larger corporates,
and it changes week to week (Applied EV had open AU roles when first
researched, zero a few weeks later). Don't expect this connector set alone
to surface most of the actual job volume — the manual-paste workflow is
the realistic primary path for Vietnam and for the large AU
mining/rail/infrastructure employers, not a fallback.

### US / UK / Germany / UAE (added Sep 2026)

Much stronger yield than VN/NL/AU on a per-country basis — the US in
particular hit its 300-job-per-run cap on the first live scrape. Every
company below independently verified against the live API (job counts,
actual location tags) before being added, same discipline as everything
above.

- **Waymo (US/UK)** — Alphabet's autonomous-driving/robotaxi unit.
  Confirmed on **Greenhouse** at `boards.greenhouse.io/waymo`. The
  strongest single find across all 7 countries: 345 total postings, 84
  US-tagged and 20 UK-tagged, including direct title matches — "NPI
  Program Manager" (Novi, MI), "Lead Technical Program Manager,
  Simulation," "Program Manager, UK Regulatory," "Program Manager –
  Vehicle Recovery, Safety & Logistics" (London). Not automotive by this
  system's strict company_sector.py classification (Waymo integrates
  autonomous tech into vehicles built by others, doesn't manufacture them)
  but a very close functional match regardless.
- **Lucid Motors (US)** — EV OEM. Confirmed on **Greenhouse** at
  `boards.greenhouse.io/lucidmotors`. 333 total, 264 US-tagged. Genuine
  automotive-OEM domain match, classified as automotive in
  company_sector.py.
- **Zipline (US)** — drone logistics/hardware manufacturer. Confirmed on
  **Greenhouse** at `boards.greenhouse.io/flyzipline`. 334 total postings,
  strong NPI-discipline fit ("NPI Technical Program Manager") — same
  non-automotive-branded-but-same-discipline pattern as Axon (Vietnam).
- **INEOS Automotive (GB/DE)** — Grenadier 4x4 OEM, UK-headquartered with
  its engineering HQ in Böblingen, Germany. Confirmed on **Workable** at
  `apply.workable.com/ineos-automotive`. 16 total postings. Genuine direct-
  domain automotive OEM — Procurement Lead (Powertrain/Electrics/Interior),
  Supplier Risk Manager, Quality Engineer roles are strong VAVE/cost-
  engineering matches. Classified as automotive.
- **FREE NOW (Germany)** — BMW Group / Mercedes-Benz Mobility ride-hailing
  JV, Hamburg HQ. Confirmed on **Greenhouse** at
  `boards.greenhouse.io/freenow`. 28 Germany-tagged postings (Hamburg/
  Berlin), including Engineering Manager and General Manager roles — real
  automotive-parent lineage, though the company itself is a mobility
  service, not a vehicle manufacturer (classified as not-automotive).
- **Aldar Properties PJSC (UAE)** — Abu Dhabi's largest master-developer,
  major mixed-use/infrastructure programs. Confirmed on **Lever** at
  `jobs.lever.co/aldar`. 48 UAE-tagged postings (Abu Dhabi/Dubai). Not
  automotive, but large-scale development/infrastructure program delivery
  is a genuine functional match — same domain-expansion reasoning as
  AirTrunk (Australia). Two live postings are explicitly tagged "UAE
  Nationals" — a real, current example of Emiratisation restriction
  (private-sector mainland companies with 50+ employees face a 2%/year
  Emirati-hiring quota with real financial penalties for shortfalls;
  free-zone entities are exempt — see config.py's AE visa_note for detail).
- Also confirmed real but currently thin on PM-titled roles, kept
  configured on the same "real board, re-check over time" logic as
  Applied EV/Relectrify: **Kodiak Robotics** (autonomous trucking,
  Greenhouse), **Samsara** (IoT/fleet hardware, Greenhouse), **Archer
  Aviation** (eVTOL/aerospace manufacturing, Greenhouse), **Redwood
  Materials** (battery/critical-materials manufacturing, Greenhouse),
  **Group14 Technologies** (silicon battery tech, Greenhouse) — all US.
  ChargePoint's existing Greenhouse board also carries thin US/UK/Germany
  volume alongside its NL postings.
- Ruled out with direct evidence: Ford (Oracle Cloud), Magna/Aptiv/
  BorgWarner/Adient (all Workday), Rivian/Joby Aviation (iCIMS), Tesla
  (proprietary in-house), McLaren/Bentley/Aston Martin (bespoke
  platforms), Volkswagen Group (own portal), Bosch (SmartRecruiters), ZF
  (SAP SuccessFactors), Masdar/Turner & Townsend (SmartRecruiters), DP
  World/AECOM/Mace/WSP/Jacobs/ACWA Power/Kuehne+Nagel (no evidence of any
  of the 4 platforms — large enterprise infra/logistics players
  consistently run custom or enterprise-class systems). GM/Stellantis/
  JLR/Nissan UK/Mahle/Brose/Continental/Hella were not positively
  confirmed either way — treat as likely-but-unverified Workday/
  SuccessFactors-class, worth a direct-fetch check in a future pass
  rather than assumed.
- No Stuttgart/Baden-Württemberg equivalent to Netherlands' Brainport
  Eindhoven cluster (NTS Group) was found for Germany — flagged as the
  single biggest open research gap from this round, since Recruitee/
  Workable customers are structurally harder to find via search-engine
  discovery than Greenhouse/Lever ones (weaker indexing).

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

### Dashboard

```bash
python -m job_intel_scraper.dashboard
```

Opens a local server at http://127.0.0.1:5000 (binds to localhost only).
Filter by country, update application status/notes inline, and click
"Generate" on any job to kick off on-demand cover-letter generation — the
button polls for status and shows the result (compiled/failed/xelatex not
found) without a page reload.

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
