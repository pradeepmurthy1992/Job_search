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


# Hard ceiling on total LLM token spend across an ENTIRE multi-country run
# (e.g. `--countries VN NL AU US GB DE AE --stage2`), independent of each
# jurisdiction's own max_llm_tokens_per_run. Per the platform overview:
# "this ceiling should be set per-country as well as globally... otherwise
# one large market can consume the entire run's budget before the other
# countries are scored at all." This was referenced in a comment
# (JurisdictionProfile.max_jobs_per_run's docstring above) since the
# original 3-country build but never actually implemented — worth noting
# now that 7 countries' per-country ceilings sum to ~1.45M tokens with
# nothing previously stopping a single `--stage2` run from spending all of
# it. main.py checks this before calling _run_stage2 for each country and
# stops the whole run (not just one country) once it's hit.
GLOBAL_MAX_LLM_TOKENS_PER_RUN = 500_000


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
        greenhouse_boards=["axon", "formlabs"],
        # Axon (public-safety hardware, HCMC site) — Greenhouse, board
        # token "axon". Not automotive-branded, but genuinely the same
        # NPI/manufacturing Program Management discipline. Verified live:
        # 22 of 511 postings are Ho Chi Minh City-based as of Sep 2026,
        # including "Employee Experience Program Manager II" and
        # "Engineering Manager, Connected Devices".
        # Formlabs (3D printing/additive manufacturing hardware) —
        # Greenhouse, board token "formlabs". Found via my.greenhouse.io's
        # candidate job search, not the systematic per-country sweep —
        # confirmed live: literal "Operation Program Manager, Southeast
        # Asia" role based in Hanoi. Same NPI/manufacturing-PM discipline
        # fit as Axon.
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
        # Autocraft Solutions Group (UK parent, Arnhem NL production site) —
        # EV battery remanufacturing/assembly, "industry":"Automotive" per
        # the API itself. Confirmed on Workable, live-verified: 3 of 4
        # postings are Arnhem/NL-tagged (1 UK role correctly excluded by
        # the location filter), including "Production Manager - Electric
        # Vehicle Battery Remanufacturing" — one of the strongest direct
        # functional fits found across all three countries.
        # (VDL ETG Eindhoven has its own separate Workable board, slug
        # "vdl-etg", confirmed real and distinct from the VDL ETG Singapore
        # subsidiary — but 0 open postings right now, so not added; worth
        # rechecking since the Brainport precision-manufacturing fit is
        # strong, same category as NTS Group.)
        workable_boards=["autocraft-solutions-group"],
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
        # AirTrunk (hyperscale data-centre developer, Sydney HQ) — the
        # single strongest AU find so far. Confirmed on Greenhouse, board
        # "airtrunk", live-verified: 33 of 79 postings are AU-tagged
        # (Sydney/Melbourne/Western Sydney), including direct title
        # matches — Commercial Manager, Cost Manager (x2), Design Manager,
        # Senior Project Manager. Not automotive, but multi-billion-dollar
        # infrastructure/construction program delivery is a close
        # functional match for VAVE/cost-engineering/program-management,
        # same reasoning as the original AU sector-expansion note below.
        # Bradken (mining/heavy-equipment wear-parts manufacturer, already
        # named in the visa_note below as a target sector) confirmed on
        # Greenhouse too, board "bradken" — its public careers page is
        # hosted on job-boards.eu.greenhouse.io, but the underlying API is
        # on the same standard boards-api.greenhouse.io host our connector
        # already uses, so no special handling was needed. Live-verified:
        # 9 of 43 postings AU-tagged, including "Management Cost
        # Accountant" (Perth).
        greenhouse_boards=["airtrunk", "bradken"],
        # Emesent (autonomous drone/mapping tech for underground mining,
        # Brisbane) confirmed on Lever — note the slug is case-sensitive:
        # "Emesent" (capital E), lowercase 404s. Live-verified: 9 of 9
        # postings are 100% Brisbane-based, including "Senior Product
        # Manager" and "Engineering Manager - Data Processing".
        lever_boards=["Emesent"],
        # Applied EV (Melbourne autonomous/electric commercial-vehicle
        # platform maker) found via web research (Sep 2026) recruiting on
        # Workable under the apply.workable.com/applied-ev URL — re-verified
        # live (Sep 2026) but currently has ZERO open roles on this feed;
        # keep configured since that changes over time. Zoomo (light-EV
        # last-mile delivery fleets, AU-founded/global) confirmed live on
        # Workable too — note its feed isn't country-filtered (returns jobs
        # across AU/UK/US/EU), which is exactly why fetch_all() applies a
        # per-jurisdiction location filter rather than trusting the board
        # list alone. Relectrify (Melbourne battery-storage/EV-adjacent
        # scale-up) confirmed real on Workable too, currently zero open
        # roles — same "keep configured, currently empty" treatment as
        # Applied EV.
        workable_boards=["applied-ev", "zoomo", "relectrify"],
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
    "US": JurisdictionProfile(
        name="United States",
        country_code="US",
        currency="USD",
        sponsorship_keywords=[
            "we will sponsor", "h-1b sponsorship available", "will sponsor visa",
            "immigration support", "we sponsor employment visas",
            "sponsorship available for this role", "visa sponsorship available",
            "we retain an immigration lawyer",
        ],
        # H-1B is a lottery, not a queue — real research (Sep 2026) found a
        # blanket "no sponsorship" disclaimer is EXTREMELY common in US
        # postings regardless of role seniority (live-verified on KPMG,
        # PrizePicks, LaunchDarkly, Wayfair, BTIG), and functionally means
        # the same thing as a citizenship restriction for a candidate who
        # needs sponsorship — so these are hard-excludes here, not a softer
        # flag, matching how sponsorship_required=True is meant to work.
        citizenship_restricted_keywords=[
            "no sponsorship available", "unable to sponsor", "without sponsorship",
            "no visa sponsorship", "does not sponsor visas", "not able to sponsor",
            "no h-1b sponsorship", "us citizens only", "must be a us citizen",
            "authorized to work in the united states without visa sponsorship",
        ],
        language_requirement_keywords=[],  # English-only market; no flag needed
        sponsorship_required=True,
        # Waymo (Alphabet AV/robotaxi) — Greenhouse "waymo". Best single
        # find across all 7 jurisdictions: 345 total postings, 84 US-tagged
        # including "NPI Program Manager" (Novi, MI — direct automotive-NPI
        # fit) and multiple other PM/TPM titles.
        # Lucid Motors (EV OEM) — Greenhouse "lucidmotors". 333 total, 264
        # US-tagged, genuine automotive-OEM domain match (Sr. Program
        # Manager Supplier Industrialization, HR PMO, Supply Chain).
        # Zipline (drone logistics/hardware mfg) — Greenhouse "flyzipline".
        # 334 total, strong NPI-discipline fit (NPI Technical Program
        # Manager, TPM Manufacturing Engineering) — same pattern as Axon
        # in the VN config (non-automotive-branded, same NPI/manufacturing-
        # PM discipline).
        # Kodiak Robotics (autonomous trucking), Samsara (IoT/fleet
        # hardware), Archer Aviation (eVTOL/aerospace mfg), Redwood
        # Materials (battery/critical-materials mfg), Group14 Technologies
        # (silicon battery tech) — all confirmed live and real, currently
        # thinner PM-titled volume; kept configured on the same
        # "real board, re-check over time" logic as Applied EV/Relectrify.
        # Sep 2026 expansion — all live-verified with genuine US-tagged
        # Program/Project Manager titles:
        # Nuro (AV delivery robots) — 3 PM-titled incl. "Senior Program
        # Manager, Perception Data Operations" (Mountain View, CA).
        # Motional (Aptiv/Hyundai AV JV) — 4 PM-titled incl. "Staff
        # Technical Program Manager" (Boston/Pittsburgh/Remote US).
        # Solid Power (solid-state EV battery mfr) — "Program Manager/
        # Senior Program Manager" (Thornton, CO).
        # Sila Nanotechnologies (battery materials) — 2 PM-titled incl.
        # "Senior Project Manager, Capital Projects" (Alameda, CA).
        # Faraday Future (EV OEM) — "Project Management Specialist"
        # (El Segundo, CA).
        # May Mobility (autonomous shuttle operator) — "Senior Autonomy
        # Technical Project Manager" (Ann Arbor, MI).
        # Scout Motors (VW's US truck/OEM brand) — 3 PM-titled incl. "IT
        # Project Manager, AI" (Charlotte, NC).
        # Gotion (EV battery gigafactory) — 6 PM-titled incl. "Program
        # Manager" and multiple "Technical Program Manager, Battery"
        # (Fremont/Irvine, CA). Note: ~13/145 of its postings (mostly
        # manufacturing/technician roles, not the PM ones) carry explicit
        # US-citizenship/no-sponsorship language — worth flagging per-
        # posting via eligibility.py rather than excluding the company.
        # Formlabs (3D printing/additive manufacturing hardware) — found
        # via my.greenhouse.io's candidate search, same NPI/manufacturing-
        # PM discipline as Zipline/Axon. 8 PM-titled US roles confirmed
        # live (Somerville, MA), incl. "Technical Program Manager" and
        # "Senior Technical Program Manager".
        greenhouse_boards=[
            "waymo", "lucidmotors", "flyzipline", "kodiak", "samsara",
            "archer56", "redwoodmaterials", "group14", "chargepoint",
            "nuro", "motional", "solidpower", "silananotechnologies",
            "faradayfuture", "maymobility", "scoutmotors", "gotion",
            "formlabs",
        ],
        # Zoox (Amazon robotaxi/AV) — Lever "zoox", 32 US PM-titled roles,
        # by far the deepest single find of this round (Foster City, CA).
        # Aeva (automotive lidar/sensing) — Lever "aeva", 2 PM-titled incl.
        # "Staff Module Engineering Program Manager" (Mountain View, CA).
        lever_boards=["zoox", "aeva"],
        workable_boards=["ineos-automotive"],
        recruitee_boards=[],
        local_job_boards=["linkedin.com", "indeed.com"],
        max_jobs_per_run=2700,  # true uncapped US-matched total measured at 2,514 postings after the Sep 2026 expansion (9 companies + Formlabs) plus two location-matching fixes: US state names/abbreviations (see _COUNTRY_KEYWORDS/_US_STATE_ABBREVIATIONS in connectors.py) and a bare "Remote - UK" false-positive fix; set above that so nothing is silently truncated — stage-1 scoring is free, only stage-2 LLM calls are cost-gated separately via max_llm_tokens_per_run
        max_llm_tokens_per_run=300_000,
        visa_note=(
            "H-1B is the only realistic route for this profile (L-1 needs "
            "1+ year prior employment at a foreign affiliate of the same "
            "employer first; O-1 'extraordinary ability' is a narrow "
            "long-shot without patents/awards/press). It is a lottery, not "
            "a queue: FY2026-27 registration ran Mar 4-19 2026, cap 85,000/"
            "year, demand runs 3-4x the cap. A Feb 27 2026 DHS rule "
            "replaced pure-random selection with WAGE-LEVEL-WEIGHTED "
            "selection — entries scale with the DOL OEWS wage level (I-IV) "
            "the offered salary meets (Level IV = 4 entries, Level I = 1), "
            "so a higher-paying offer now has materially better lottery "
            "odds; worth weighting a job's stated salary as a secondary "
            "signal when comparing US postings. A Sept 2025 proclamation "
            "imposing a $100K fee on new H-1B petitions for candidates "
            "outside the US was struck down by a federal judge Jun 8 2026; "
            "DHS has appealed — status is UNRESOLVED, treat as a live risk "
            "factor, not settled law, and re-check before relying on it. "
            "No fixed salary floor for H-1B itself, but the prevailing-wage/"
            "LCA requirement (employer must pay the higher of the DOL "
            "prevailing wage by SOC code + metro, or actual wage for "
            "similar employees) now indirectly matters via the weighted "
            "lottery. Given how common a blanket 'no sponsorship' "
            "disclaimer is regardless of seniority, absence of positive "
            "sponsorship language should be weighted more cautiously here "
            "than in NL — this is closer to Vietnam's 'absence weighs "
            "heavily' treatment than NL's 'absence is not a rejection'."
        ),
    ),
    "GB": JurisdictionProfile(
        name="United Kingdom",
        country_code="GB",
        currency="GBP",
        sponsorship_keywords=[
            "skilled worker visa sponsorship", "home office licensed sponsor",
            "we are able to sponsor", "certificate of sponsorship provided",
            "visa sponsorship available", "sponsor licence",
        ],
        citizenship_restricted_keywords=[
            "unable to sponsor", "does not hold a sponsor licence",
            "right to work in the uk required", "must have existing right to work",
            "uk citizens only",
        ],
        language_requirement_keywords=[],  # English-only market; no flag needed
        sponsorship_required=True,
        # Waymo (Greenhouse "waymo", shared board with US) — 20 UK-tagged
        # postings including "Program Manager, UK Regulatory" and "Program
        # Manager – Vehicle Recovery, Safety & Logistics" (both London).
        # INEOS Automotive (Grenadier 4x4 OEM, UK HQ) — confirmed on
        # Workable "ineos-automotive": genuine direct-domain UK automotive
        # OEM. No PM-titled role currently, but Procurement Lead and
        # Supplier Risk Manager roles are strong VAVE/cost-engineering
        # adjacents — most roles are actually at the Böblingen, Germany
        # engineering HQ, hence also listed under DE below.
        # Autocraft Solutions Group (Workable, already in NL config) — UK
        # parent company, has UK-tagged postings (e.g. Quality Engineer,
        # Wellingborough) alongside its NL production-site roles.
        # Wayve (autonomous driving, London) — Greenhouse "wayve",
        # live-verified: 6 genuine Program/Technical-Program-Manager
        # titled roles in London, strongest single find for GB.
        # Fastned (EV charging, already in NL config) — same live board,
        # 3 UK-tagged postings (London) incl. "Senior Expansion Manager
        # UK" — expansion/programme-management-flavored, not literally
        # "Project Manager" but a real fit.
        greenhouse_boards=["waymo", "chargepoint", "wayve"],
        lever_boards=[],
        workable_boards=["ineos-automotive", "autocraft-solutions-group"],
        recruitee_boards=["fastned"],
        local_job_boards=["linkedin.com", "indeed.co.uk"],
        max_jobs_per_run=200,
        max_llm_tokens_per_run=200_000,
        visa_note=(
            "Skilled Worker visa is the only realistic route. Employer "
            "MUST hold a Home Office Sponsor Licence and issue a "
            "Certificate of Sponsorship — no licence, no route, full stop; "
            "this is the single most decisive UK filter, more binary than "
            "NL's 'recognized sponsor' status. Current minimum salary "
            "threshold: GBP 41,700/year (in effect since Jul 22 2025, up "
            "from GBP 38,700) — but the REAL threshold is 'higher of "
            "GBP 41,700 or the occupation's SOC-code going rate', so an "
            "actual floor can exceed 41,700 depending on job code; "
            "wage-indexed, re-check before each hiring season like NL's "
            "HSM threshold. Role must also meet RQF Level 6 skill level "
            "and an eligible SOC code. English requirement is CEFR B2 — "
            "not usually a blocker for this candidate. UK employment "
            "lawyers note blanket 'no sponsorship' exclusions carry "
            "discrimination-claim risk under UK law even though they "
            "remain common — an interesting nuance absent from the other "
            "three original markets. As of 2026 there are ~127,652 "
            "licensed Skilled Worker sponsors, a large pool, but licence-"
            "holding still needs per-company verification, never assumed."
        ),
    ),
    "DE": JurisdictionProfile(
        name="Germany",
        country_code="DE",
        currency="EUR",
        sponsorship_keywords=[
            "visasponsoring", "visa-sponsoring", "blue card sponsorship",
            "unterstützung bei der blauen karte", "relocation package",
            "relocation support", "international candidates welcome",
            "we sponsor work visas",
        ],
        citizenship_restricted_keywords=[
            "eu citizens only", "eu-staatsangehörigkeit erforderlich",
            "must have german work permit", "deutsche staatsangehörigkeit erforderlich",
        ],
        language_requirement_keywords=[
            "fluent german", "verhandlungssicheres deutsch", "deutsch (c1",
            "german language required", "native german",
        ],
        sponsorship_required=True,
        # ChargePoint (Greenhouse "chargepoint", shared board with NL/US/
        # UK) — thin but real Germany-tagged volume (Marketing Manager -
        # Europe, Munich).
        # FREE NOW (BMW Group / Mercedes-Benz Mobility JV, Hamburg HQ) —
        # confirmed on Greenhouse "freenow": 28 Germany-tagged postings
        # (Hamburg/Berlin) including Engineering Manager and General
        # Manager roles — real automotive-parent lineage (BMW/Mercedes-
        # Benz backing) even though current reqs skew commercial/tech
        # rather than program-management.
        # INEOS Automotive (Workable "ineos-automotive") — most roles are
        # actually at the Böblingen, Germany engineering HQ (Grenadier 4x4
        # OEM's technical centre), not just the UK entries above.
        # FINN (Lever "finn", Munich car-subscription/fleet-management
        # scaleup) — 28 live postings, nearly all Munich/Germany, incl.
        # fleet-operations roles (Compound Manager, Senior Fleet
        # Coordinator) directly in the vehicle-fleet domain.
        # instagrid (Recruitee "instagrid", Ludwigsburg portable-battery/
        # energy-storage company) — confirmed live "Technical Project
        # Manager - Product Delivery" opening in Ludwigsburg, DE.
        greenhouse_boards=["chargepoint", "freenow"],
        lever_boards=["finn"],
        workable_boards=["ineos-automotive"],
        recruitee_boards=["instagrid"],
        local_job_boards=["linkedin.com", "stepstone.de"],
        max_jobs_per_run=200,
        max_llm_tokens_per_run=200_000,
        visa_note=(
            "EU Blue Card (Blaue Karte EU, Residence Act para 18g) is the "
            "primary route. Standard minimum gross salary (2026): "
            "EUR 50,700/year (EUR 4,225/month) — 50% of the statutory "
            "pension insurance contribution-assessment ceiling, set "
            "annually by the BMI. REDUCED shortage-occupation "
            "(Mangelberufe) threshold (2026): EUR 45,934.20/year "
            "(EUR 3,827.85/month) — 45.3% of the same ceiling; the "
            "shortage list is occupation-CODE based and explicitly "
            "includes mechanical/electrical/civil engineering, so a "
            "posting with genuine engineering/technical scope (e.g. "
            "'Program Manager - Vehicle Engineering') plausibly qualifies "
            "for the reduced rate, while a generically-titled 'Program "
            "Manager' without an engineering nexus should be judged "
            "against the standard EUR 50,700 floor — default to the "
            "standard threshold unless the JD is clearly engineering-"
            "coded. Both figures are wage-indexed annually — re-check at "
            "the next BMI cycle, same discipline as NL's HSM threshold. "
            "Alternative: standard work-visa route (Aufenthaltserlaubnis "
            "zur Erwerbstätigkeit, para 18a/18b) has no fixed salary floor "
            "but pay must be 'customary for the region/sector' and the "
            "path to permanent residency is slower (~4-5 years vs 21-27 "
            "months on Blue Card) — treat as a fallback, not the primary "
            "target, since this candidate's seniority likely clears the "
            "Blue Card threshold anyway. Language is genuinely mixed, not "
            "a safe default either way: large automotive MNCs (BMW, "
            "Mercedes-Benz, VW) commonly run global/cross-functional "
            "program roles in English, while Mittelstand/Tier-1 suppliers "
            "and domestically-facing roles more often expect German — "
            "surface language_requirement_keywords per-posting rather "
            "than assuming a blanket answer for the whole German market."
        ),
    ),
    "AE": JurisdictionProfile(
        name="United Arab Emirates",
        country_code="AE",
        currency="AED",
        sponsorship_keywords=[
            "visa sponsorship provided", "employment visa and emirates id provided",
            "we will sponsor your visa", "relocation support", "visa provided",
            "medical and emirates id processing included",
        ],
        # UAE Nationals-only / Emiratisation restrictions are a real,
        # PRESENT-DAY factor, not a hypothetical — live-verified Sep 2026
        # on Aldar Properties' own postings (see visa_note).
        citizenship_restricted_keywords=[
            "uae nationals only", "emiratisation position", "must be a uae national",
        ],
        language_requirement_keywords=[],  # English-primary for the expatriate-track private sector
        sponsorship_required=True,
        # Aldar Properties PJSC (Abu Dhabi's largest master-developer,
        # major mixed-use/infrastructure development programs) — Lever
        # "aldar". Live-verified: 48 UAE-tagged postings (Abu Dhabi/
        # Dubai). Not automotive, but large-scale development/
        # infrastructure program delivery is a genuine functional match
        # for program-management/cost-engineering background — same
        # domain-expansion reasoning as AirTrunk in the AU config. Two
        # live postings are explicitly tagged "UAE Nationals" — a real
        # example of the Emiratisation restriction below, not a guess.
        greenhouse_boards=[],
        lever_boards=["aldar"],
        workable_boards=[],
        recruitee_boards=[],
        local_job_boards=["linkedin.com", "bayut.com", "gulftalent.com"],
        max_jobs_per_run=200,
        max_llm_tokens_per_run=200_000,
        visa_note=(
            "Standard route: employer-sponsored Employment Visa + Emirates "
            "ID via MOHRE (Ministry of Human Resources and Emiratisation). "
            "No fixed minimum-salary threshold like NL/DE/GB — sponsorship "
            "is tied to a labor contract/offer letter, medical fitness, "
            "and Emirates ID issuance, not an income floor. The candidate "
            "would also independently qualify for a self-sponsored "
            "'Golden Visa' (10-year residency for high earners) given "
            "likely salary level, but that is explicitly NOT the target "
            "route here — this candidate's stance is employer-sponsored "
            "routes only, everywhere, no exception. Mainland vs free-zone "
            "matters practically: mainland companies sponsor via MOHRE "
            "directly and mainland licenses of 50+ employees (now also "
            "20-49) are subject to a 2%/year Emiratisation quota increase "
            "(cumulative to 10% since the policy's start), with real "
            "penalties (AED 6,000/month per unfilled Emirati position, "
            "escalating annually — documented cases of AED 432,000/year "
            "exposure for a mid-sized shortfall); free-zone entities "
            "(DMCC, DIFC, ADGM, Dubai South, etc.) sponsor through their "
            "own free-zone authority and are EXEMPT from mainland "
            "Emiratisation quotas — a JD or company page mentioning a "
            "free-zone entity is a soft positive signal worth noting. "
            "Emiratisation-driven 'UAE Nationals only' restrictions "
            "concentrate disproportionately on management/AVP-and-above "
            "and finance/marketing-strategy roles at MAINLAND companies, "
            "less so on free-zone or purely technical/engineering roles — "
            "live-confirmed on Aldar's own postings (Sep 2026). English is "
            "the practical working language for expatriate-track private-"
            "sector roles in the target sectors — no language barrier "
            "expected."
        ),
    ),
    "SG": JurisdictionProfile(
        name="Singapore",
        country_code="SG",
        currency="SGD",
        sponsorship_keywords=[
            "employment pass sponsorship available", "we will sponsor your ep",
            "relocation package", "relocation assistance to singapore",
            "visa sponsorship provided", "international candidates welcome",
        ],
        # Singapore's Fair Consideration Framework REQUIRES most EP
        # applications to be advertised on MyCareersFuture.sg for 14+ days
        # open to all candidates first — so "open to Singaporeans and PRs"
        # / FCF-boilerplate language is routine compliance text that
        # commonly COEXISTS with active EP sponsorship, not a restriction.
        # Only the harder "...ONLY" phrasing below is treated as a real
        # exclusion — eligibility.py's citizenship_restricted_keywords are
        # hard excludes, so this distinction matters more here than
        # anywhere else in the config: getting it wrong would hard-exclude
        # a large share of genuinely sponsorable Singapore postings.
        citizenship_restricted_keywords=[
            "singapore citizens and prs only", "open only to singapore citizens",
            "must have valid singapore work authorization", "no visa sponsorship",
            "we are unable to sponsor",
        ],
        language_requirement_keywords=[],  # English-primary for PMET/expat-track roles
        sponsorship_required=True,
        # Automotive OEM/Tier-1 presence on these 4 platforms is
        # effectively zero for Singapore (no local vehicle manufacturing;
        # large industrials/semis/aerospace default to Workday/
        # SuccessFactors, confirmed absent via direct token checks for
        # Bosch, Continental, ZF, Denso, ST Engineering, SIA Engineering,
        # Rolls-Royce, Safran, Collins Aerospace, and others — Sep 2026).
        # Portcast (Singapore-HQ logistics/freight-AI startup) — Lever
        # "portcast", live-verified: 4 of 9 postings Singapore-tagged,
        # including a literal "Technical Program Manager" role. Strongest
        # single find for this country.
        greenhouse_boards=["moloco", "xendit"],
        # Moloco (AdTech/AI, real Singapore APAC office) — Greenhouse
        # "moloco", 3 of 46 SG-tagged incl. "GTM Program Manager".
        # Xendit (Indonesia-founded fintech, real SEA/Singapore ops) —
        # Greenhouse "xendit", 7 of 24 include Singapore among eligible
        # locations (multi-city postings); no PM title live yet.
        # WeRide (autonomous driving/robotaxi, One-north Singapore R&D hub)
        # — Lever "weride", live-verified: literal "Global Technical
        # Project Manager" role at One-north, Singapore.
        lever_boards=["portcast", "ninjavan", "weride"],
        # Ninja Van (Singapore-HQ logistics/last-mile delivery unicorn) —
        # Lever "ninjavan", 13 of 157 SG-tagged; currently driver/
        # warehouse/sales-ops roles only, no PM titles live, but a large
        # active board worth monitoring.
        workable_boards=[],
        # Beam Mobility and Neuron Mobility (both Singapore-founded e-
        # scooter/micromobility EV companies, Workable "beam-mobility" /
        # "neuron-mobility") and GlobalFoundries/Infineon (real Singapore
        # semiconductor operations, Workable "globalfoundries" /
        # "infineon") all confirmed as genuine, live boards but currently
        # zero open postings — not added to avoid an always-empty board,
        # same "verified real, currently empty" treatment as Ajax Systems
        # (Vietnam) and VDL ETG (Netherlands); worth re-checking
        # periodically. Crown Equipment (material-handling/forklift
        # manufacturer, states a Singapore regional HQ, Workable
        # "crown-equipment") has 68 live postings but all currently
        # AU-tagged, zero Singapore — also worth re-checking, not added
        # here since it wouldn't currently surface anything for this
        # jurisdiction.
        recruitee_boards=[],
        local_job_boards=["mycareersfuture.gov.sg", "linkedin.com"],
        max_jobs_per_run=150,
        max_llm_tokens_per_run=150_000,
        visa_note=(
            "Employment Pass (EP), administered by MOM, is the operative "
            "route. Since 1 Sep 2023 ALL new EP applications are assessed "
            "under COMPASS (Complementarity Assessment Framework) — a "
            "points-based system layered ON TOP OF a salary floor, not a "
            "simple pass/fail threshold like most other target countries. "
            "Current (2026) qualifying salary floor: SGD 5,600/month at "
            "the youngest band, rising on an age-progressive sliding scale "
            "to SGD 10,700/month at age 45+ (financial-services roles: "
            "SGD 6,200 rising to SGD 11,800). At candidate's age (35) the "
            "real floor sits well above the SGD 5,600 headline figure — "
            "likely in the SGD 8,600-9,600 range by interpolation of "
            "MOM's published curve (not a directly-quoted MOM figure; "
            "verify before relying on it for a specific offer). A floor "
            "increase to SGD 6,000/6,600 is already announced for Jan "
            "2027. Separately from the salary floor, the applicant must "
            "score >=40 of 80 possible COMPASS points across six criteria "
            "(salary margin above local peers, qualifications, workforce-"
            "nationality diversity at the employer, the EMPLOYER's own "
            "track record hiring local PMETs, shortage-occupation bonus, "
            "strategic-sector bonus) — two of the six (employer's local-"
            "hiring record, workforce diversity mix) are entirely outside "
            "the candidate's control and invisible from a job posting, so "
            "unlike US H-1B lottery odds or a clean salary-threshold "
            "country, Singapore should be treated as 'sponsorship-"
            "plausible, pass-uncertain' rather than a clean signal either "
            "way. KEY EXEMPTION: a fixed monthly salary of SGD 22,500+ "
            "skips COMPASS scoring entirely (straight pass on salary "
            "alone) — a posting stating pay at or above that level is a "
            "strong positive signal worth weighting heavily. Most EP "
            "applications also require the employer to have advertised "
            "the role on MyCareersFuture.sg for 14+ days under the Fair "
            "Consideration Framework BEFORE filing — this is why 'open to "
            "Singaporeans and PRs' / FCF-referencing language is routine "
            "compliance boilerplate that commonly coexists with active EP "
            "sponsorship, not a restriction (see citizenship_restricted_"
            "keywords above for the harder phrasing that IS treated as a "
            "real exclusion). S Pass (mid-skilled, SGD 3,150+ floor) is "
            "not relevant given this candidate's seniority."
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
