"""
robots.txt gating — no target is scraped, ever, if it disallows bot access.

This is a hard rule from the platform overview: "Platforms whose robots.txt
explicitly disallows automated access are permanently excluded, full stop,
not worked around." This module is the single choke point that enforces it,
so every connector calls through here rather than each re-implementing its
own check (and potentially getting it wrong).
"""

from __future__ import annotations

from urllib.parse import urlparse
import time

import requests
from protego import Protego

# Cache parsed robots.txt rulesets per host for the life of the process so
# we don't re-fetch it on every single job URL.
_CACHE: dict[str, Protego | None] = {}
# None in the cache means "fetch failed / disallow everything" — a sentinel
# distinct from "haven't checked this host yet".
_DISALLOW_ALL = object()

DEFAULT_USER_AGENT = "JobIntelBot/1.0 (+contact: pradeepmoorthy92@gmail.com)"


def _get_parser(base_url: str):
    """Returns a Protego ruleset, or the _DISALLOW_ALL sentinel if
    robots.txt couldn't be fetched at all (fail closed, never assume
    permission). Uses protego rather than the stdlib urllib.robotparser:
    the stdlib parser doesn't implement the `*`/`$` wildcard extension real
    sites rely on (e.g. Seek's `Disallow: */job/`) — it silently treats `*`
    as a literal character, which was observed to make an actually-
    disallowed path (Seek's job detail pages) read as allowed. protego is
    Scrapy's own robots.txt library and implements the real spec correctly.
    """
    parsed = urlparse(base_url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host not in _CACHE:
        try:
            resp = requests.get(f"{host}/robots.txt", timeout=10, headers={"User-Agent": DEFAULT_USER_AGENT})
            if resp.status_code in (401, 403):
                _CACHE[host] = _DISALLOW_ALL
            elif resp.status_code >= 400:
                # No robots.txt at all (404 etc.) conventionally means
                # everything is allowed — an empty ruleset parses that way.
                _CACHE[host] = Protego.parse("")
            else:
                # A real robots.txt in the wild (observed on
                # vietnamworks.com) can be served with a leading UTF-8 BOM;
                # strip it so it doesn't get treated as part of the first
                # directive name.
                content = resp.text.lstrip("﻿")
                _CACHE[host] = Protego.parse(content)
        except Exception:
            # If robots.txt can't be fetched at all, fail closed: treat as
            # disallowed rather than assuming permission.
            _CACHE[host] = _DISALLOW_ALL
    return _CACHE[host]


def is_allowed(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Return True only if robots.txt explicitly permits fetching this URL."""
    parser = _get_parser(url)
    if parser is _DISALLOW_ALL:
        return False
    return parser.can_fetch(url, user_agent)


def assert_allowed(url: str, target_label: str) -> None:
    """
    Raise if a target is not scrapable. Call this once when a connector is
    first configured (not just at request time) so a disallowed target never
    gets built in the first place.
    """
    if not is_allowed(url):
        raise PermissionError(
            f"robots.txt for {target_label!r} ({url}) disallows automated "
            f"access — this target must not be scraped, per platform policy."
        )


def polite_delay(seconds: float = 1.5) -> None:
    """Simple shared rate-limit between requests to any single host."""
    time.sleep(seconds)
