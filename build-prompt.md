# Build Prompt — Job Intelligence Platform for Pradeep Moorthy (VN / NL / AU)

Paste this whole prompt into your coding agent (Claude Code or similar) inside the
project's repo root. It assumes the architecture in `job-intelligence-platform-overview.md`
(revised version) as the target design, and the candidate profile below as ground truth.

**A working starting point already exists**: the `job_intel_scraper/` package
(delivered alongside this prompt) implements jurisdiction config, eligibility
detection, Greenhouse/Lever/Workable/Recruitee connectors, the stage-1 scorer,
SQLite persistence, and a pluggable stage-2 LLM client (Gemini free tier or a
fully local Ollama model — see its README's "Which LLM backend" section). Tell
your coding agent to extend that codebase, not start from scratch — the "what
to build" list below is written as extensions to it, and the acceptance checks
assume its existing design choices (e.g. never re-scoring a cached job,
per-country token ceilings) rather than asking you to invent them.

---

## Candidate profile (ground truth for scoring keywords and cover letters)

- 11+ years, Automotive Program/Project Management, VAVE & Cost Engineering.
- Employers: Tata Motors, Mahindra & Mahindra (M&M AFS), TVS Motor, Nissan Ashok
  Leyland Technologies, Ather Energy (current).
- Domains: OEM + Tier-1 + EV. Vehicle development, validation, engineering change
  management, BOM/cost optimization, PLM (Enovia, CATIA V5/V6), Altair HyperMesh.
- Automation/analytics: Python, VBA, TCL for reporting automation; Power BI
  dashboarding; JIRA/Agile + MS Project/Waterfall; pursuing MBA in Business
  Analytics (SRM University, 2025–2026).
- Credentials: granted patent (vehicle door-slam testing methodology); PMP (PMI)
  in progress, expected Oct 2026.
- Quantified wins: ₹10M+ annual VAVE savings, 15% project-delay reduction, 50–60%
  projected meshing-time cut, 12% fuel-efficiency improvement, 8–10% cost cuts via
  supplier negotiation/resource restructuring.
- Languages: Tamil & English (proficient), Hindi (conversant). **No stated Dutch
  or Vietnamese.**
- Currently based in Pune, India, age 35.
- **Visa stance (decided 2026-09): employer-sponsored routes only, in all three
  countries.** No self-funded/independent pathway is being pursued right now —
  `sponsorship_required=True` on every jurisdiction profile reflects this.
- The `[[program/platform name]` placeholder bracket in the original resume's
  Tata Motors bullet has been fixed (replaced with "the CV Operations
  portfolio," matching phrasing already used in the next bullet) —
  `Pradeep_Moorthy_Resume_Fixed.docx` is the corrected file. Don't regenerate
  cover letters against the original PDF.

## Target jurisdictions — build these as first-class config, not afterthoughts

1. **Vietnam**
   - Foreign hires need an employer-sponsored work permit (Decree 219/2025 as of
     2026); the employer must justify why a Vietnamese worker can't fill the role.
     Some exemptions exist for capital-contributor/board-member roles or recognized
     experts in tech/innovation fields, but a standard PM hire will go through the
     standard work-permit route — sponsorship must exist before applying.
   - Practical implication for the scorer: treat every VN posting as
     sponsorship-required by default; only relax that if the JD explicitly says
     the role is open to foreign nationals / will sponsor a work permit.
   - Discovery: VinFast, Thaco, Toyota Vietnam, Honda Vietnam, Ford Vietnam, Bosch
     Vietnam, and other OEM/Tier-1 JV career pages, plus VietnamWorks, TopCV,
     CareerBuilder.vn, and LinkedIn as aggregator sources. Many of these run on
     local ATS or bespoke career pages, not Workday/Greenhouse — budget scraper
     time accordingly and confirm each target's `robots.txt` before building it.
   - JD language: expect a mix of English and Vietnamese at JV/MNC sites; flag
     (don't discard) Vietnamese-only postings for manual review rather than
     silently mis-scoring them with an English-only keyword pass.

2. **Netherlands**
   - Realistic path is the Highly Skilled Migrant (kennismigrant) visa, sponsored
     by an IND-"recognized sponsor" employer. Candidate is 35, so **only the
     30-and-over threshold applies: ~€5,942 gross/month as of Jan 1, 2026** — the
     under-30 (~€4,357) and reduced/search-year (~€3,122) rates are not relevant
     and should not be used to judge fit. This number is wage-indexed annually by
     the IND, so store it as a config value to re-check each hiring season, not a
     hardcoded constant. Treat "does this employer hold recognized-sponsor
     status" as a gray-area signal the scorer can only approximate from JD
     language (e.g. "relocation support," "visa sponsorship available") — flag,
     don't assume.
   - Practical implication: the eligibility filter should look for explicit
     relocation/sponsorship language in the JD; absence of that language is a
     caution flag, not an automatic reject, since many employers sponsor without
     saying so in the posting — but given the employer-sponsored-only stance,
     sponsorship-confirmed postings should sort/rank ahead of ambiguous ones.
   - Discovery: **Fastned confirmed via research — runs its careers site on
     Recruitee at `fastned.recruitee.com`** (EV charging infrastructure, not
     vehicle manufacturing, but a genuine adjacent-sector fit). DAF Trucks, VDL
     Groep, Prodrive Technologies, and Bosch NL are plausible targets but weren't
     confirmed on any lightweight-API ATS during research — likely Workday or
     SmartRecruiters, needing a bespoke connector. Supplement with Indeed.nl,
     LinkedIn, and NationaleVacaturebank.
   - Language: flag postings that explicitly require Dutch fluency (B2+/native)
     as a lower-priority match, since none is currently stated on the resume.

3. **Australia — scope confirmed expanded (2026-09) beyond pure automotive**
   - Local vehicle manufacturing (Holden/Ford/Toyota assembly) ended around 2017,
     so the horizon deliberately widens to sectors where the program/VAVE/cost-
     engineering background transfers directly: (1) mining & heavy-equipment
     OEMs — Caterpillar, Komatsu, Liebherr Australia, Bradken; (2) rail rolling
     stock — Alstom, Downer EDI Rail, UGL Rail; (3) EV/automotive-adjacent
     scale-ups — **Applied EV, confirmed recruiting via Workable at
     `apply.workable.com/applied-ev`** (medium confidence — verify the slug),
     plus Tritium and SEA Electric (found on Employment Hero/bespoke sites, not
     yet connector-covered); (4) general/industrial manufacturing program
     management; (5) infrastructure & engineering PM consultancies — Aurecon,
     WSP, AECOM, Jacobs, GHD, whose large program-delivery practices value
     PMP-track, VAVE, and cost-engineering backgrounds without requiring
     automotive-specific product knowledge.
   - Most of (1), (2), and (5) are large corporates on Workday or SuccessFactors —
     **treat Seek.com.au and Indeed.com.au as primary discovery sources for
     Australia, not secondary**, until bespoke connectors for those ATS platforms
     exist.
   - Visa-wise, Australia's points-tested and employer-sponsored pathways (482,
     186, 189, 190, 491) key off specific ANZSCO occupation codes, not job titles.
     "Program Manager" isn't a clean standalone code — the closest fits are likely
     **Engineering Manager (133211)** or a manufacturing-specific management code,
     depending on which duties dominate. This needs to be confirmed against the
     official ANZSCO descriptions on the Department of Home Affairs site before
     the platform treats any AU posting as "visa-pathway eligible." Given the
     employer-sponsored-only stance, the 482 (Temporary Skill Shortage) pathway is
     the realistic near-term target, not the points-tested 189/190/491 routes.
   - Language: English-only market, so no language-detection flag needed here —
     but do detect Australian citizenship/PR-only and security-clearance-required
     postings (common in government/defense-adjacent roles — Thales Australia,
     Rheinmetall Defence Australia, BAE Systems Australia) and treat those as hard
     excludes, not soft flags.

## What to build (in priority order)

1. **Jurisdiction config module** (`config/jurisdictions.py` or equivalent):
   one object per country with the fields above — eligibility default,
   sponsorship-keyword list, language-requirement keyword list, occupation-code
   hint, currency, job-board/ATS source list, per-country job-count and
   token-spend ceilings.
2. **Eligibility/sponsorship detector**: a keyword + regex pass over each JD that
   flags (a) explicit sponsorship/relocation language, (b) explicit
   citizenship/PR-only exclusions, (c) explicit language requirements. Surface
   this as a visible signal in the dashboard next to the two score layers — never
   silently fold it into a single composite number, since a high JD-match score
   on a citizenship-restricted role is a false positive the user needs to see as
   such, not a filtered-out row they never learn existed.
3. **Per-country discovery connectors**: extend the existing ATS connector layer
   with the country-specific job boards listed above. Check `robots.txt` for
   every new target before writing the connector, per the existing safety rule —
   no exceptions for "it's just a job board."
4. **Dashboard country filter**: add a country facet to the existing scored-jobs
   view so Vietnam/Netherlands/Australia can be viewed separately or combined.
5. **Cost ceilings per country**: extend the existing global job-count/token
   ceiling to also cap spend per jurisdiction per run, so one high-volume market
   can't starve the other two of LLM-scoring budget in a shared run.
6. **Resume data-contract check**: before any cover-letter generation call, fail
   loudly (don't silently proceed) if the source resume text contains obvious
   placeholder markers like `[[`, `[TBD]`, `[program/platform name]`, etc. — this
   is the same "data-contract mismatch" failure class the reliability notes
   describe for scrapers, just on the resume-ingestion side instead.
7. **Regression tests**: one test per jurisdiction connector confirming it
   returns non-zero, correctly-shaped results against a known-good fixture, per
   the existing "re-audit every connector against the same failure pattern"
   practice — don't let a silent zero-result bug reappear on a new country the
   way it did on earlier scrapers.

## Acceptance checks before calling this done

- [ ] Running a scoring pass produces separate, visibly-labeled eligibility flags
      (sponsorship/relocation, citizenship-restriction, language-requirement) for
      every job, independent of the JD-match score.
- [ ] No jurisdiction's LLM spend can exceed its configured per-country ceiling
      even if the other two are under budget.
- [ ] Every new connector has been checked against that target's `robots.txt`
      and the check is recorded (not just done once and forgotten).
- [ ] A resume containing a placeholder bracket fails cover-letter generation
      with a clear error rather than producing a cover letter with the bracket
      (or a hallucinated fill-in) in it.
- [ ] Dashboard can filter to a single country or show all three combined.
- [ ] Personal-data-file git-tracking guard still runs before every scrape/sync,
      unchanged from the existing design.
