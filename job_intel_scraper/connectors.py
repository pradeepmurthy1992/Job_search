"""
Discovery-layer connectors. Greenhouse, Lever, Workable, and Recruitee all
expose public, documented, robots-friendly JSON APIs for their job boards,
which makes them the right first set to implement — no HTML scraping, no
anti-bot fingerprinting needed. Everything else in the platform overview's
"20+ ATS" list (Workday, SmartRecruiters, iCIMS, Taleo, SuccessFactors,
bespoke career sites) follows the same pattern: one function that returns a
list of normalized Job dicts, gated by robots_check first.

Workable and Recruitee were added after real research turned up companies
that actually use them (Applied EV/Zoomo on Workable, Fastned/Allego/
GreenFlux/Eneco eMobility on Recruitee) — Greenhouse and Lever alone came
up close to empty across Vietnam, Netherlands, and Australia searches, so
restricting discovery to just those two would have meant covering almost
nothing in these three markets.

Local job boards (Seek, Indeed, VietnamWorks, TopCV, etc.) were evaluated
and deliberately NOT connected here: Seek/Indeed/TopCV return real robots.txt
permission for their search pages but their actual servers return 403 to an
honestly-identified bot regardless (infrastructure-level blocking, not a
robots.txt matter — not worked around, same as a robots.txt disallow),
VietnamWorks' listings only materialize via client-side JS (no server-
rendered content and no discoverable JSON API to call directly), and
CareerBuilder.vn's certificate is expired. Those sources go through the
platform overview's documented manual-paste workflow instead (see
manual_job.py) — the human browses and pastes, since automating them isn't
possible without either bypassing a block or a much larger headless-browser
dependency, neither of which is in scope here.

A company's ATS board can list jobs across MULTIPLE countries (observed on
Zoomo's Workable feed, which returned UK roles even though Zoomo was found
via an Australia-focused search) — so every fetched job is checked against
the jurisdiction's actual country, using structured country data from the
source when available (Workable, Recruitee) and free-text keyword matching
otherwise (Greenhouse, Lever). A job that clearly belongs to a different
country is dropped, not mislabeled.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

import requests

from . import robots_check

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
LEVER_API = "https://api.lever.co/v0/postings/{company}"
WORKABLE_API = "https://apply.workable.com/api/v1/widget/accounts/{account}"
RECRUITEE_API = "https://{host}/api/offers/"

REQUEST_TIMEOUT = 20

# Free-text keyword matching for sources that don't give a structured
# country code (Greenhouse, Lever). Deliberately conservative — country
# name plus a handful of major cities, not an exhaustive gazetteer.
_COUNTRY_KEYWORDS: dict[str, list[str]] = {
    "AU": ["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
           "canberra", "gold coast", "newcastle", "wollongong", "hobart", "darwin"],
    "NL": ["netherlands", "nederland", "holland", "amsterdam", "rotterdam",
           "utrecht", "the hague", "den haag", "eindhoven", "arnhem",
           "groningen", "tilburg", "nijmegen", "breda", "almere"],
    "VN": ["vietnam", "viet nam", "hanoi", "ha noi", "ho chi minh", "hcmc",
           "da nang", "hai phong", "can tho"],
    # "usa"/"united states" alone catches the vast majority of real US
    # location strings observed live (e.g. Zipline: "Austin, Texas, USA")
    # — the city list is a backup, not the primary signal, since a PM role
    # can legitimately be in any US city/state.
    "US": ["usa", "united states", "u.s.a", "novi", "southfield", "phoenix",
           "newark", "south san francisco", "mountain view", "pittsburgh",
           "seattle", "austin", "dallas", "houston", "chicago", "boston",
           "new york", "los angeles", "san diego", "atlanta", "cleveland"],
    "GB": ["united kingdom", "uk", "london", "england", "scotland", "wales",
           "manchester", "birmingham", "bristol", "leeds", "wellingborough",
           "upper heyford"],
    "DE": ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
           "frankfurt", "stuttgart", "cologne", "köln", "böblingen"],
    "AE": ["united arab emirates", "uae", "dubai", "abu dhabi", "sharjah"],
    "SG": ["singapore"],
}
_REMOTE_KEYWORDS = ["remote", "anywhere", "distributed", "work from home"]
# A "remote" location string is often tied to a SPECIFIC other country or
# US state ("Texas-Remote, United States", "France-Remote") — observed live
# on Axon's Greenhouse board, where several US/France-remote roles were
# wrongly passed through to Vietnam because the bare word "remote" alone
# was treated as ambiguous-but-plausible. If a remote listing explicitly
# names one of these, it's remote *for that place*, not global, so it
# should NOT pass through for a different jurisdiction.
# A one-off blocklist kept missing entries in practice (UAE slipped through
# on the first pass) — this is a broad common-name country list instead,
# built to be over-inclusive rather than patched gap-by-gap each time a new
# miss turns up. Deliberately excludes VN/NL/AU (and their common
# alternate names), since those are handled by _COUNTRY_KEYWORDS matching
# TRUE, not this list.
_OTHER_COUNTRY_SIGNALS = [
    "united states", "usa", "u.s.a", "u.s.", "america",
    "canada", "mexico",
    "brazil", "argentina", "colombia", "chile", "peru", "ecuador",
    "uruguay", "paraguay", "bolivia", "venezuela", "costa rica", "panama",
    "united kingdom", "england", "scotland", "wales",
    "ireland", "france", "germany", "spain", "italy", "portugal",
    "poland", "ukraine", "romania", "bulgaria", "hungary", "czech",
    "slovakia", "slovenia", "croatia", "serbia", "greece", "austria",
    "switzerland", "belgium", "luxembourg", "denmark", "sweden", "norway",
    "finland", "iceland", "estonia", "latvia", "lithuania", "malta",
    "cyprus", "moldova", "belarus", "albania", "bosnia", "montenegro",
    "north macedonia", "kosovo", "monaco", "andorra", "liechtenstein",
    "turkey", "russia", "armenia", "azerbaijan",  # "georgia" already covered via the US state entry below
    "israel", "lebanon", "jordan", "iraq", "iran", "syria",
    "saudi arabia", "united arab emirates", "qatar", "kuwait", "bahrain",
    "oman", "yemen", "egypt",
    "india", "pakistan", "bangladesh", "sri lanka", "nepal", "bhutan",
    "china", "japan", "korea", "taiwan", "hong kong", "mongolia",
    "philippines", "singapore", "malaysia", "indonesia", "thailand",
    "myanmar", "cambodia", "laos", "brunei",
    "new zealand", "fiji", "papua new guinea",
    "south africa", "nigeria", "kenya", "ghana", "morocco", "tunisia",
    "algeria", "ethiopia", "tanzania", "uganda", "zimbabwe", "zambia",
    "senegal", "ivory coast", "cameroon", "rwanda",
    "kazakhstan", "uzbekistan", "kyrgyzstan", "tajikistan", "turkmenistan",
    # US state names, since "<State>-Remote" is a common Greenhouse pattern
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
]

# Greenhouse location strings often lead with a 2-letter ISO-ish country/
# state code instead of a full name ("US-CA-Remote", "US-GA-Remote",
# "CA - Remote") — plain substring matching against _OTHER_COUNTRY_SIGNALS
# missed these live (observed: 6 US/Canada-remote roles leaked into a
# Netherlands run before this was added), and a blind substring check for
# a bare 2-letter code like "us" would false-positive on ordinary words
# ("campus", "customer") — so this is a separate, anchored regex applied
# only to the leading token of the location string.
_LEADING_CODE_PATTERN = re.compile(r"^\s*([A-Za-z]{2})\b[\s-]")
_KNOWN_COUNTRY_CODES = {
    "us", "ca", "uk", "gb", "de", "fr", "es", "it", "nl", "au", "vn", "ie",
    "nz", "in", "cn", "jp", "sg", "ae", "mx", "br", "ph", "pl", "se", "ch",
    "be", "dk", "no", "fi", "at", "pt", "za",
}


@dataclass
class Job:
    source: str            # "greenhouse" | "lever" | "workable" | "recruitee"
    board_or_company: str
    external_id: str
    title: str
    location_raw: str
    url: str
    description_raw: str
    country_hint: str      # which JurisdictionProfile this was fetched for
    fetched_at: float
    posted_at: float | None = None       # epoch seconds, when the source provides one
    company_name: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None     # "year" | "month" | "hour" | None
    # Internal-only, not persisted: structured country signal from the
    # source (ISO alpha-2) when available, used by _location_matches below.
    _source_country_code: str | None = field(default=None, repr=False, compare=False)


def _location_matches(job: Job, country_code: str) -> bool:
    """True if this job plausibly belongs to the target country. Prefers a
    structured country code from the source; falls back to keyword matching
    on the free-text location; a remote-sounding location with no country
    signal either way is let through rather than guessed at."""
    if job._source_country_code:
        return job._source_country_code.upper() == country_code.upper()

    text = (job.location_raw or "").lower()

    leading_code_match = _LEADING_CODE_PATTERN.match(text)
    if leading_code_match:
        code = leading_code_match.group(1).lower()
        if code == country_code.lower():
            return True
        if code in _KNOWN_COUNTRY_CODES:
            return False
        # An unrecognized 2-letter prefix isn't trusted either way — fall
        # through to the other checks rather than guess.

    if any(kw in text for kw in _COUNTRY_KEYWORDS.get(country_code, [])):
        return True
    if any(kw in text for kw in _REMOTE_KEYWORDS):
        # "Remote" tied to a specific other place ("Texas-Remote, United
        # States", "France-Remote") is remote *for that place*, not
        # global — don't pass it through for a different jurisdiction.
        if any(sig in text for sig in _OTHER_COUNTRY_SIGNALS):
            return False
        return True
    # No location text at all — don't discard on absence of a signal.
    if not text.strip():
        return True
    return False


def _parse_iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        # Handles "2026-08-19 12:21:10 UTC" and "2026-08-19T12:21:10Z" style
        # timestamps seen across these APIs.
        cleaned = value.replace(" UTC", "+00:00").replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except ValueError:
        return None


def fetch_greenhouse_board(board_token: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Greenhouse board (content=true pulls
    full HTML job descriptions in one call, avoiding a second request per job)."""
    url = GREENHOUSE_API.format(board=board_token) + "?content=true"
    robots_check.assert_allowed(url, target_label=f"greenhouse:{board_token}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data.get("jobs", []):
        job = Job(
            source="greenhouse",
            board_or_company=board_token,
            external_id=str(posting.get("id")),
            title=posting.get("title", ""),
            location_raw=(posting.get("location") or {}).get("name", ""),
            url=posting.get("absolute_url", ""),
            description_raw=posting.get("content", "") or "",
            country_hint=country_hint,
            fetched_at=time.time(),
            posted_at=_parse_iso_to_epoch(posting.get("first_published") or posting.get("updated_at")),
            company_name=posting.get("company_name", "") or board_token,
        )
        jobs.append(job)
    robots_check.polite_delay()
    return jobs


def fetch_lever_board(company_slug: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Lever company board."""
    url = LEVER_API.format(company=company_slug) + "?mode=json"
    robots_check.assert_allowed(url, target_label=f"lever:{company_slug}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []  # {"ok": false, ...} — board slug doesn't exist / no postings

    jobs: list[Job] = []
    for posting in data:
        categories = posting.get("categories", {}) or {}
        created_at_ms = posting.get("createdAt")
        job = Job(
            source="lever",
            board_or_company=company_slug,
            external_id=str(posting.get("id")),
            title=posting.get("text", ""),
            location_raw=categories.get("location", ""),
            url=posting.get("hostedUrl", ""),
            description_raw=(posting.get("descriptionPlain")
                             or posting.get("description") or ""),
            country_hint=country_hint,
            fetched_at=time.time(),
            posted_at=(created_at_ms / 1000.0) if isinstance(created_at_ms, (int, float)) else None,
            company_name=company_slug,
        )
        jobs.append(job)
    robots_check.polite_delay()
    return jobs


def fetch_workable_board(account_slug: str, country_hint: str) -> list[Job]:
    """Fetch all live postings for one Workable account's public widget feed.
    No auth required; this endpoint does not support filtering/search, so it
    always returns the account's full current listing — which can span
    multiple countries (see module docstring), hence the country_code capture
    for the location filter in fetch_all()."""
    url = WORKABLE_API.format(account=account_slug)
    robots_check.assert_allowed(url, target_label=f"workable:{account_slug}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data.get("jobs", []):
        location = posting.get("location", {})
        location_str = location.get("location_str", "") if isinstance(location, dict) else str(location or "")
        locations_list = posting.get("locations") or []
        country_code = None
        if locations_list and isinstance(locations_list[0], dict):
            country_code = locations_list[0].get("countryCode")

        job = Job(
            source="workable",
            board_or_company=account_slug,
            external_id=str(posting.get("shortcode") or posting.get("id", "")),
            title=posting.get("title", ""),
            location_raw=location_str or f"{posting.get('city', '')}, {posting.get('country', '')}".strip(", "),
            url=posting.get("url", ""),
            description_raw=posting.get("description", "") or "",
            country_hint=country_hint,
            fetched_at=time.time(),
            posted_at=_parse_iso_to_epoch(posting.get("published_on") or posting.get("created_at")),
            company_name=account_slug,
        )
        job._source_country_code = country_code
        jobs.append(job)
    robots_check.polite_delay()
    return jobs


def fetch_recruitee_board(company_slug: str, country_hint: str, host: str | None = None) -> list[Job]:
    """Fetch all live postings for one Recruitee company careers site. No
    auth required; description is returned as full HTML in the list call.
    `host` overrides the default <slug>.recruitee.com pattern for customers
    who white-label onto their own domain (e.g. Allego -> join.allego.eu) —
    the API path structure is unchanged, just the hostname."""
    actual_host = host or f"{company_slug}.recruitee.com"
    url = RECRUITEE_API.format(host=actual_host)
    robots_check.assert_allowed(url, target_label=f"recruitee:{company_slug}")

    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    jobs: list[Job] = []
    for posting in data.get("offers", []):
        location = posting.get("location") or posting.get("city", "") or ""
        salary = posting.get("salary") or {}
        job = Job(
            source="recruitee",
            board_or_company=company_slug,
            external_id=str(posting.get("id")),
            title=posting.get("title", ""),
            location_raw=location,
            url=f"https://{actual_host}/o/{posting.get('slug', '')}",
            description_raw=posting.get("description", "") or "",
            country_hint=country_hint,
            fetched_at=time.time(),
            posted_at=_parse_iso_to_epoch(posting.get("published_at") or posting.get("created_at")),
            company_name=posting.get("company_name", "") or company_slug,
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            salary_currency=salary.get("currency"),
            salary_period=salary.get("period"),
        )
        job._source_country_code = posting.get("country_code")
        jobs.append(job)
    robots_check.polite_delay()
    return jobs


def fetch_all(jurisdiction) -> list[Job]:
    """Fetch every configured board for one JurisdictionProfile, then drop
    any job whose actual location doesn't match that jurisdiction's country
    (see module docstring — a board can span multiple countries). Individual
    board failures are logged and skipped rather than aborting the whole
    run — one dead board token shouldn't take down the other nine."""
    results: list[Job] = []
    for board in jurisdiction.greenhouse_boards:
        try:
            results.extend(fetch_greenhouse_board(board, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001 - log-and-continue by design
            print(f"[connectors] greenhouse:{board} failed: {exc}")

    for company in jurisdiction.lever_boards:
        try:
            results.extend(fetch_lever_board(company, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] lever:{company} failed: {exc}")

    for account in jurisdiction.workable_boards:
        try:
            results.extend(fetch_workable_board(account, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] workable:{account} failed: {exc}")

    for company in jurisdiction.recruitee_boards:
        try:
            results.extend(fetch_recruitee_board(company, jurisdiction.country_code))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] recruitee:{company} failed: {exc}")

    for label, host in getattr(jurisdiction, "recruitee_custom_domains", {}).items():
        try:
            results.extend(fetch_recruitee_board(label, jurisdiction.country_code, host=host))
        except Exception as exc:  # noqa: BLE001
            print(f"[connectors] recruitee:{label} ({host}) failed: {exc}")

    matched = [j for j in results if _location_matches(j, jurisdiction.country_code)]
    dropped = len(results) - len(matched)
    if dropped:
        print(
            f"[connectors] {jurisdiction.name}: dropped {dropped} job(s) whose "
            f"location didn't match {jurisdiction.country_code} (board spans "
            f"multiple countries)."
        )
    return matched


def job_to_dict(job: Job) -> dict[str, Any]:
    d = asdict(job)
    d.pop("_source_country_code", None)
    return d
