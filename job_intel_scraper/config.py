"""
Per-jurisdiction configuration for the job intelligence scraper.

Each country is a first-class config object (not a hardcoded assumption) —
see job-intelligence-platform-overview.md's "Jurisdiction profiles" section
for why this matters once more than one target country is in play.

CANDIDATE STANCE (set 2026-09): employer-sponsored routes only, in all three
countries — no self-funded/independent visa pathway is being pursued right
now. `sponsorship_required=True` on every profile reflects that; it changes
how eligibility.py treats an absent sponsorship mention (see that module's
docstring) but does not hard-exclude ambiguous postings, since most JDs never
mention sponsorship either way.

Candidate is 35 — old enough that the Dutch HSM "under 30" reduced threshold
never applies. Only the 30-and-over rate is relevant and is the only one kept
active in the NL profile below.

Fill in real board tokens as you find them on each target company's careers
page — the URL itself usually gives it away:
  boards.greenhouse.io/<token>   or   job-boards.greenhouse.io/<token>
  jobs.lever.co/<token>
  apply.workable.com/<token>
  <token>.recruitee.com
Two are pre-filled below from actual web research (see README "Verified
target companies" for how each was confirmed and how confident to be in it).
Everything else is a category suggestion, not a confirmed token — most
large employers in these three markets run Workday or SuccessFactors, which
this skeleton does not scrape (see README for why, and what to do instead).
"""

from dataclasses import dataclass, field


@dataclass
class JurisdictionProfile:
    name: str
    country_code: str  # ISO 3166-1 alpha-2, used for location filtering
    currency: str
    # Keywords that, if found in a JD, indicate the employer is open to
    # sponsoring a foreign hire. Case-insensitive substring match.
    sponsorship_keywords: list[str]
    # Keywords indicating the role is closed to non-citizens/non-PR holders.
    # These are hard excludes, not soft flags.
    citizenship_restricted_keywords: list[str]
    # Local-language requirement keywords worth flagging (skip for
    # English-only markets like Australia).
    language_requirement_keywords: list[str]
    # Whether the candidate is only pursuing employer-sponsored routes here.
    # True for all three right now — kept as a field (not a global constant)
    # so it can be flipped per-country later without touching eligibility.py.
    sponsorship_required: bool = True
    # Greenhouse board tokens (company slug from boards.greenhouse.io/<slug>)
    greenhouse_boards: list[str] = field(default_factory=list)
    # Lever company slugs (from jobs.lever.co/<slug>)
    lever_boards: list[str] = field(default_factory=list)
    # Workable account slugs (from apply.workable.com/<slug>)
    workable_boards: list[str] = field(default_factory=list)
    # Recruitee subdomains (from <slug>.recruitee.com)
    recruitee_boards: list[str] = field(default_factory=list)
    # Some Recruitee customers white-label onto their own domain instead of
    # <slug>.recruitee.com (e.g. Allego uses join.allego.eu) — the API path
    # structure is unchanged, just the host. Keyed by a label (for logging)
    # -> full custom hostname.
    recruitee_custom_domains: dict[str, str] = field(default_factory=dict)
    # Non-ATS job boards to eventually add bespoke connectors for.
    # Kept here as a checklist, not implemented in this skeleton.
    local_job_boards: list[str] = field(default_factory=list)
    # Per-run guardrails, independent of the global ceiling.
    max_jobs_per_run: int = 200
    max_llm_tokens_per_run: int = 200_000
    # Free-text note on visa/occupation nuance — surfaced in reports so the
    # human reviewer sees the caveat, not just a score.
    visa_note: str = ""


JURISDICTIONS: dict[str, JurisdictionProfile] = {
    "VN": JurisdictionProfile(
        name="Vietnam",
        country_code="VN",
        currency="VND",
        sponsorship_keywords=[
            "work permit sponsorship", "sponsor work permit", "visa sponsorship",
            "open to foreign nationals", "expat package", "relocation support",
            "work permit provided",
        ],
        citizenship_restricted_keywords=[
            "vietnamese nationals only", "must be a vietnamese citizen",
        ],
        language_requirement_keywords=[
            "fluent vietnamese", "native vietnamese", "vietnamese language required",
        ],
        sponsorship_required=True,
        # No purely automotive/EV employer in Vietnam was confirmed on these
        # 4 platforms (VinFast->Zoho Recruit, Bosch->SmartRecruiters, Thaco/
        # Toyota/Honda/Ford VN -> Facebook/local boards, Selex Motors and
        # Dat Bike -> no formal ATS at all). But broadening beyond pure
        # automotive branding to the same manufacturing/NPI/VAVE discipline
        # at Western multinationals with Vietnam factories turned up real,
        # live-verified hits (Sep 2026):
        greenhouse_boards=["axon"],
        # Axon (public-safety hardware, HCMC site) — Greenhouse, board
        # token "axon". Not automotive-branded, but genuinely the same
        # NPI/manufacturing Program Management discipline. Verified live:
        # 22 of 511 postings are Ho Chi Minh City-based as of Sep 2026,
        # including "Employee Experience Program Manager II" and
        # "Engineering Manager, Connected Devices".
        lever_boards=["uei"],
        # Universal Electronics Inc. (consumer-electronics manufacturer,
        # Hai Duong City factory) — Lever, slug "uei". Verified live: 7 of
        # 17 postings are Hai Duong-based, including "NPI Electronics
        # Engineer" — direct NPI/manufacturing-engineering overlap.
        # (Ajax Systems, slug "ajax", also has a real Hanoi factory and is
        # genuinely on Lever, but had zero Vietnam-tagged postings when
        # checked — not added to avoid an always-empty board; worth
        # re-checking periodically since the factory is real and growing.)
        workable_boards=[],
        recruitee_boards=["onemobility"],
        # One Mobility Group (automotive sensor/connectivity/electrification
        # solutions, operates in 13 countries incl. Vietnam) — Recruitee,
        # slug "onemobility". Direct domain fit, not just adjacent. Verified
        # live: 1 of 25 postings is Vietnam-based ("Global Operational
        # Excellence Expert," Hai Phong) — low volume but a genuine hit.
        local_job_boards=["vietnamworks.com", "topcv.vn", "careerbuilder.vn", "linkedin.com"],
        max_jobs_per_run=150,
        max_llm_tokens_per_run=150_000,
        visa_note=(
            "Sponsorship is a legal precondition, not just a preference — a "
            "foreign hire needs an employer-obtained work permit under Decree "
            "219/2025, and the employer must justify why a Vietnamese worker "
            "couldn't fill the role. Only relax the eligibility flag when the "
            "JD explicitly mentions work permit sponsorship or openness to "
            "foreign nationals. Expect mixed English/Vietnamese postings at "
            "JV/MNC sites — a Vietnamese-only JD should be flagged for manual "
            "review, not auto-scored with English keywords."
        ),
    ),
    "NL": JurisdictionProfile(
        name="Netherlands",
        country_code="NL",
        currency="EUR",
        sponsorship_keywords=[
            "visa sponsorship", "relocation package", "relocation support",
            "highly skilled migrant", "kennismigrant", "recognized sponsor",
            "we sponsor", "international candidates welcome",
        ],
        citizenship_restricted_keywords=[
            "eu citizens only", "must have eu work permit", "dutch nationals only",
        ],
        language_requirement_keywords=[
            "fluent dutch", "native dutch", "dutch language required", "dutch (c1",
        ],
        sponsorship_required=True,
        # ChargePoint (global EV charging, Amsterdam office) confirmed on
        # Greenhouse, board token "chargepoint" — live-verified Sep 2026:
        # 1 of 31 postings is Amsterdam-tagged ("Supply Chain Coordinator").
        # Low current volume but a large, direct-sector employer worth
        # tracking.
        greenhouse_boards=["chargepoint"],
        lever_boards=[],
        workable_boards=[],
        # Fastned confirmed via web research (Sep 2026): runs its own careers
        # site on Recruitee at fastned.recruitee.com. High confidence — the
        # domain itself appeared directly in search results. Fastned is EV
        # charging infrastructure, not vehicle manufacturing, but its program/
        # ops roles are a genuine adjacent-sector fit for VAVE/cost-engineering
        # and program-management background.
        # Allego (EV charging infra, Arnhem) and GreenFlux (EV charge-point
        # management SaaS, Amsterdam) and Eneco eMobility (smart EV
        # charging, NL/BE/LUX) confirmed via live web research (Sep 2026) —
        # all three on Recruitee. GreenFlux's careers page explicitly
        # advertises "visa sponsorship and relocation compensation to
        # expats" — a strong positive signal given the employer-sponsored-
        # only stance. Note: Allego is white-labeled at join.allego.eu
        # (not <slug>.recruitee.com) — confirm this connector handles a
        # custom domain, not just the default subdomain pattern.
        # Extended-domain pass (Sep 2026) — Brainport Eindhoven high-tech/
        # precision-manufacturing cluster turned out to be the single
        # strongest new vein: NTS Group (Recruitee, "nts") does the same
        # QLTC (Quality/Logistics/Technology/Cost) discipline as automotive
        # VAVE/NPI, just for semiconductor/life-sciences/defense OEMs — 50
        # of 65 live postings are NL-based, including multiple Project/
        # Program Manager and Category/Supplier Manager roles. Rocsys
        # (Recruitee, "rocsys" — robotic EV/truck charging automation,
        # Rijswijk) and LeydenJar Technologies (Recruitee, "leydenjar" —
        # silicon-anode battery manufacturing scale-up, Eindhoven/Leiden,
        # has a live "Senior Program Manager" role) both confirmed with
        # real NL postings. Milence (Recruitee, custom domain
        # jobs.milence.com — heavy-duty truck charging network, a JV of
        # Daimler Truck/Traton/Volvo Group) confirmed too, though currently
        # only 1 open role. Two "obvious" next EV-charging names — Shell
        # Recharge Solutions/NewMotion and Eneco's parent (non-eMobility)
        # brand — both recently abandoned Recruitee (their subdomains now
        # redirect to Recruitee's "not hosted" page); don't re-add them
        # without re-verifying first. Battolyser Systems (battery/
        # electrolyser cleantech) is genuinely Recruitee-hosted but 404s
        # right now — worth re-checking periodically, not added yet.
        recruitee_boards=["fastned", "greenflux", "enecoemobility", "nts", "rocsys", "leydenjar"],
        recruitee_custom_domains={"allego": "join.allego.eu", "milence": "jobs.milence.com"},
        local_job_boards=["indeed.nl", "nationalevacaturebank.nl", "linkedin.com"],
        max_jobs_per_run=150,
        max_llm_tokens_per_run=150_000,
        visa_note=(
            "Candidate is 35, so only the 30-and-over Highly Skilled Migrant "
            "threshold is relevant: ~EUR 5,942 gross/month as of Jan 1, 2026 "
            "(the under-30 ~EUR 4,357 and reduced ~EUR 3,122 rates do not "
            "apply and should not be used to judge fit). This threshold is "
            "wage-indexed annually by the IND — re-check it before each "
            "hiring season rather than trusting this constant long-term. "
            "Employer must hold IND 'recognized sponsor' status. Absence of "
            "sponsorship language in a JD is a caution flag, not an automatic "
            "reject — many employers sponsor without stating it, but since "
            "the candidate stance here is employer-sponsored-only, treat "
            "explicit sponsorship mentions as the higher-priority tier when "
            "sorting results, not as a filter that discards the rest."
        ),
    ),
    "AU": JurisdictionProfile(
        name="Australia",
        country_code="AU",
        currency="AUD",
        sponsorship_keywords=[
            "visa sponsorship available", "sponsorship available", "482 visa",
            "will sponsor", "employer sponsored visa", "relocation assistance",
        ],
        citizenship_restricted_keywords=[
            "must be an australian citizen", "australian citizenship required",
            "full working rights in australia required", "pr holders only",
            "baseline clearance", "nv1 clearance", "security clearance required",
        ],
        language_requirement_keywords=[],  # English-only market; no flag needed
        sponsorship_required=True,
        greenhouse_boards=[], lever_boards=[],
        # Applied EV (Melbourne autonomous/electric commercial-vehicle
        # platform maker) found via web research (Sep 2026) recruiting on
        # Workable under the apply.workable.com/applied-ev URL — re-verified
        # live (Sep 2026) but currently has ZERO open roles on this feed;
        # keep configured since that changes over time. Zoomo (light-EV
        # last-mile delivery fleets, AU-founded/global) confirmed live on
        # Workable too — note its feed isn't country-filtered (returns jobs
        # across AU/UK/US/EU), which is exactly why fetch_all() applies a
        # per-jurisdiction location filter rather than trusting the board
        # list alone.
        workable_boards=["applied-ev", "zoomo"],
        recruitee_boards=[],
        local_job_boards=["seek.com.au", "indeed.com.au", "linkedin.com"],
        max_jobs_per_run=250,  # AU volume via Seek/Indeed tends to be higher
        max_llm_tokens_per_run=250_000,
        visa_note=(
            "EXPANDED SCOPE (2026-09): local vehicle-assembly OEM presence "
            "ended ~2017, so don't confine discovery to badge-name automotive. "
            "Sectors where the program/VAVE/cost-engineering background "
            "transfers directly: (1) mining & heavy-equipment OEMs — "
            "Caterpillar, Komatsu, Liebherr Australia, Bradken; (2) rail "
            "rolling stock — Alstom, Downer EDI Rail, UGL Rail; (3) EV/"
            "automotive-adjacent scale-ups — Applied EV (Workable, above), "
            "Tritium, SEA Electric (both found on Employment Hero / bespoke "
            "sites during research, not scrapable via this skeleton's "
            "connectors yet); (4) industrial/general manufacturing program "
            "management; (5) infrastructure & engineering PM consultancies — "
            "Aurecon, WSP, AECOM, Jacobs, GHD, who run large program-delivery "
            "practices and value PMP-track, VAVE, and cost-engineering "
            "backgrounds even without automotive-specific product knowledge. "
            "Most of (1), (2), and (5) are large corporates that run Workday "
            "or SuccessFactors, not Greenhouse/Lever/Workable/Recruitee — "
            "treat Seek and Indeed.com.au as PRIMARY discovery sources for "
            "Australia, not a fallback, until bespoke connectors for those "
            "ATS platforms exist. Visa pathways (482/186/189/190/491) key off "
            "ANZSCO occupation codes, not job titles — 'Program Manager' has "
            "no clean standalone code; closest candidates are likely "
            "Engineering Manager (133211) or a manufacturing-specific code — "
            "confirm against the official ANZSCO description before treating "
            "any posting as visa-pathway-eligible. Defence/security-cleared "
            "roles (common at Thales Australia, Rheinmetall Defence Australia, "
            "BAE Systems Australia) usually require citizenship or long "
            "residency for clearance — treated as citizenship-restricted "
            "hard-excludes by default here, confirm case by case if pursuing."
        ),
    ),
}


# Core resume keywords used by the stage-1 scorer (see scorer.py). Keep this
# in sync with the actual resume — these are NOT invented; they're pulled
# directly from Pradeep Moorthy's resume sections (summary, core competencies,
# tools, experience bullets).
RESUME_KEYWORDS = {
    "title": [
        "program manager", "project manager", "senior manager", "manager",
        "assistant manager", "engineer", "vave", "value engineering",
    ],
    "domain": [
        "automotive", "vehicle development", "vehicle integration", "oem",
        "tier-1", "tier 1", "ev", "electric vehicle", "commercial vehicle",
        "new product development", "npd", "cost engineering", "cost optimization",
        "bom", "bill of materials", "plm", "engineering change management", "ecn",
        # Added for the AU sector expansion — mining/rail/infrastructure PM
        # roles describe the same skill set with different domain nouns.
        "heavy equipment", "mining", "rail", "rolling stock", "infrastructure",
        "manufacturing program", "program delivery",
    ],
    "tools": [
        "catia", "enovia", "altair hypermesh", "hyper mesh", "autocad",
        "power bi", "python", "vba", "tcl", "ms project", "jira",
    ],
    "methodology": [
        "agile", "waterfall", "hybrid", "scrum", "sprint planning",
        "risk management", "stakeholder management", "cross-functional",
    ],
    "seniority_signals": [
        "11+ years", "senior manager", "manager", "head of", "lead",
    ],
}
