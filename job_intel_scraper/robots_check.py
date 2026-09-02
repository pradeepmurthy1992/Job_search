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
from urllib.robotparser import RobotFileParser
import time

# Cache robots.txt parsers per host for the life of the process so we don't
# re-fetch it on every single job URL.
_CACHE: dict[str, RobotFileParser] = {}

DEFAULT_USER_AGENT = "JobIntelBot/1.0 (+contact: pradeepmoorthy92@gmail.com)"


def _get_parser(base_url: str) -> RobotFileParser:
    parsed = urlparse(base_url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host not in _CACHE:
        rp = RobotFileParser()
        rp.set_url(f"{host}/robots.txt")
        try:
            rp.read()
        except Exception:
            # If robots.txt can't be fetched at all, fail closed: treat as
            # disallowed rather than assuming permission.
            rp.disallow_all = True
        _CACHE[host] = rp
    return _CACHE[host]


def is_allowed(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Return True only if robots.txt explicitly permits fetching this URL."""
    parser = _get_parser(url)
    return parser.can_fetch(user_agent, url)


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
