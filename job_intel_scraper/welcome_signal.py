"""
Positive relocation/sponsorship signal detection, for the dashboard's
"Sponsorship/relocation offered" filter.

No JD in the live dataset says anything like "Indian candidates welcome" (0
hits for any nationality-openness phrasing across ~3,400 postings), so
"are Indians welcome" can't be answered literally. The real, honest proxy
for a candidate needing sponsorship from abroad is whether the JD affirmatively
offers visa sponsorship or relocation help — and, just as important, that
the same phrases appear constantly in NEGATED form ("relocation assistance
will not be provided", "visa sponsorship is not available"). A naive substring
match would count those as positives, so every match is checked for
negation in a window around it.

Returns "offered" (plain positive), "conditional" (hedged: "may provide",
"certain positions may be eligible"), or "none". Absence of a signal is not
evidence of a closed role — it just means the JD doesn't say either way.
"""

from __future__ import annotations

import html
import re

_POSITIVE = re.compile(
    r"relocation (?:assistance|support|package|benefits?|allowance|bonus|stipend|help|program|services)"
    r"|(?:visa|work permit|work visa|immigration) (?:sponsorship|support|assistance)"
    r"|(?:will|can|may|able to|happy to) sponsor"
    r"|we sponsor|sponsor(?:ing|s)? (?:work )?visas?"
    r"|sponsorship (?:is )?(?:available|provided|offered)",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:not|no|unable|cannot|can't|won't|without|isn't|aren't|never|neither|nor)\b"
    r"|does not|do not|will not|is not|are not",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"\b(?:may|might|certain positions?|some positions?|select(?:ed)? (?:roles?|candidates?)|"
    r"eligible|case[- ]by[- ]case|when appropriate|if applicable)\b",
    re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")

_WINDOW_BEFORE = 55
_WINDOW_AFTER = 55


def assess(description: str) -> str:
    text = _TAGS.sub(" ", html.unescape(html.unescape(description or "")))
    text = re.sub(r"\s+", " ", text)
    best = "none"
    for m in _POSITIVE.finditer(text):
        before = text[max(0, m.start() - _WINDOW_BEFORE):m.start()]
        after = text[m.end():m.end() + _WINDOW_AFTER]
        if _NEGATION.search(before) or _NEGATION.search(after):
            continue
        if _HEDGE.search(before) or _HEDGE.search(after):
            best = "conditional" if best == "none" else best
        else:
            return "offered"
    return best
