"""
Bespoke company-portal loaders, for employers whose own public vacancy page
is the only way in — no Greenhouse/Lever/Ashby/Workable/Recruitee board
exists for them (see connectors.py's module docstring: "bespoke career
sites follow the same pattern — one function that returns normalized Job
objects, gated by robots_check first").

Added Oct 2026 for Norway, from a user-supplied list of 50 Norwegian
employers. Reading every portal in a browser showed that only Kongsberg
currently has project/program roles in Norway that fit the candidate (the
rest had none, or only internships/technicians/AI-engineering roles), and
Kongsberg's vacancy pages are server-rendered public HTML, so they can be
re-read on every refresh instead of being a one-off paste.

Every request goes through robots_check first, with the project's
honestly-identified bot user-agent. Registered per country in
PORTAL_LOADERS so `main.py --countries NO` refreshes them like any other
connector.
"""

from __future__ import annotations

import re
import time
from typing import Callable

import requests
from bs4 import BeautifulSoup

from . import robots_check
from .connectors import Job, REQUEST_TIMEOUT

_KONGSBERG_BASE = "https://www.kongsberg.com"
_KONGSBERG_LIST = _KONGSBERG_BASE + "/careers/vacancies/"

# Kongsberg's list mixes English and Norwegian titles and ~70 vacancies of
# every kind (operators, welders, developers...). Only roles that fit a
# program/project-management profile are loaded: project/program managers,
# coordinators and planners, change/configuration management, the program
# office, and project engineers (English or Norwegian title).
_KONGSBERG_RELEVANT = re.compile(
    r"project manager|projects? coordinator|project engineer|project planner|"
    r"program(me)? (manager|office)|change manager|configuration management|"
    r"strategic planning|"
    r"prosjektleder|delprosjektleder|prosjektplanlegger|jobbpakkeleder",
    re.IGNORECASE,
)

# Vacancy locations read "<business unit>, <town(s)>"; the list also has
# non-Norwegian sites (Houston, Port Coquitlam, Gdynia). Only a posting in
# one of these Norwegian places is tagged NO. "Moss" and "Asker" are fine
# HERE (matched against a Kongsberg-specific location string, not free-
# form text — unlike connectors._COUNTRY_KEYWORDS, where they're too
# ambiguous).
_NORWEGIAN_PLACES = (
    "kongsberg", "asker", "moss", "rygge", "horten", "trondheim", "skøyen",
    "skoyen", "kjeller", "fredrikstad", "ålesund", "alesund", "oslo",
    "lysaker", "arsenalet", "bergen", "stavanger", "raufoss",
)

# Titles with obvious typos on the live site (observed: "Porject Manager for
# Advanced Satellite Systems") — fixed so job_function.classify() and the
# stage-1 title keywords still recognise them as project-manager roles.
_TITLE_FIXES = {"Porject": "Project"}


def _get_html(url: str) -> str:
    robots_check.assert_allowed(url, target_label=url)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": robots_check.DEFAULT_USER_AGENT})
    resp.raise_for_status()
    robots_check.polite_delay()
    # Decode explicitly: the server's charset header is unreliable and a
    # wrong guess turns every apostrophe/ø into mojibake.
    return resp.content.decode("utf-8", errors="replace")


def fetch_kongsberg_jobs(country_code: str = "NO") -> list[Job]:
    soup = BeautifulSoup(_get_html(_KONGSBERG_LIST), "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"^/careers/vacancies/.+/$")):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        title_part, _, rest = text.partition(" Location:")
        title = title_part.strip()
        for typo, fix in _TITLE_FIXES.items():
            title = title.replace(typo, fix)
        location = re.sub(r"\s*read more\s*$", "", rest, flags=re.IGNORECASE).strip()
        if href in seen or not _KONGSBERG_RELEVANT.search(title):
            continue
        if not any(place in location.lower() for place in _NORWEGIAN_PLACES):
            continue
        seen.add(href)

        url = _KONGSBERG_BASE + href
        detail = BeautifulSoup(_get_html(url), "html.parser")
        main = detail.find("main") or detail.find("article")
        if main is None:
            continue
        for tag in main.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        body = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()
        if not body:
            continue

        job = Job(
            source="portal",
            board_or_company="kongsberg",
            external_id=href.strip("/").split("/")[-1],
            title=title,
            location_raw=f"{location}, Norway",
            url=url,
            description_raw=body,
            country_hint=country_code,
            fetched_at=time.time(),
            company_name="Kongsberg",
        )
        job._source_country_code = "NO"
        jobs.append(job)
    return jobs


# Country code -> loaders whose Job objects are tagged for that country.
PORTAL_LOADERS: dict[str, list[Callable[[str], list[Job]]]] = {
    "NO": [fetch_kongsberg_jobs],
}
