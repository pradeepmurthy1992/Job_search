"""
Approximate pay-in-USD-per-month estimation.

Per user decision (Sep 2026): extract a salary ONLY when the posting (or
the source's own structured field, e.g. Recruitee's `salary` object) states
one — never estimate a market-rate figure for postings that don't disclose
pay. A job with no stated salary shows as "not disclosed," not a guess.
FX conversion uses a static, manually-maintained table rather than a live
FX API (no new external dependency) — same pattern as the NL Highly
Skilled Migrant threshold in config.py: a config value to re-check
periodically, not a constant to trust indefinitely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Approximate USD conversion rates, set 2026-09. Re-check periodically —
# these drift, sometimes significantly (VND especially). Not a live feed,
# by design (see module docstring).
FX_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "AUD": 0.66,
    "GBP": 1.27,
    "VND": 0.0000395,
}

_CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "USD": "USD",
    "€": "EUR", "EUR": "EUR",
    "£": "GBP", "GBP": "GBP",
    "A$": "AUD", "AU$": "AUD", "AUD": "AUD",
    "VND": "VND", "VNĐ": "VND", "₫": "VND",
}

_PERIOD_TO_MONTHLY_FACTOR = {
    "year": 1 / 12, "annum": 1 / 12, "annually": 1 / 12, "p.a.": 1 / 12, "pa": 1 / 12,
    "month": 1.0, "monthly": 1.0,
    "week": 4.345, "weekly": 4.345,
    "hour": 173.2, "hourly": 173.2, "hr": 173.2,  # ~173 working hours/month
    "day": 21.7, "daily": 21.7,  # ~21.7 working days/month
}

# Full period words need a "per "/"/" prefix to avoid false-matching an
# unrelated sentence ("the offer expires by month end"); "p.a."/"pa" are
# self-contained abbreviations for "per annum" so they don't need one, but
# stay a whole-word match so they don't fire mid-token. Two named groups
# (not one, since the two branches have different prefix requirements) —
# callers combine whichever one actually matched.
_PERIOD_PATTERN = (
    r"(?:per\s+|/)\s*(?P<period_word>year|annum|annually|month|monthly|week|weekly|hour|hourly|hr|day|daily)"
    # "p.a." ends in a non-word char (the trailing period), so a closing \b
    # after it never matches (\b needs a word/non-word transition, and both
    # sides of that position are non-word) — no trailing \b for that
    # branch. "pa" alone still gets one, so it doesn't match inside "paid".
    r"|\b(?P<period_abbrev>p\.a\.|pa\b)"
)

_NUMBER = r"[\d,.]+(?:\s*[kK])?"

# Matches: "$80,000 - $100,000 per year", "€4,500/month", "VND 40,000,000/month",
# "AUD 120k p.a.", "USD 5,000 - 6,000 monthly", etc. Deliberately conservative —
# false negatives (missing a statable salary) are far less harmful here than
# false positives (inventing one), matching the "never guess" design choice.
_SALARY_PATTERN = re.compile(
    r"(?P<currency>US\$|AU\$|A\$|VN[DĐ]|₫|[$€£]|USD|EUR|GBP|AUD|VND)\s*"
    r"(?P<low>" + _NUMBER + r")"
    r"(?:\s*[-–to]+\s*(?P<currency2>US\$|AU\$|A\$|VN[DĐ]|₫|[$€£]|USD|EUR|GBP|AUD|VND)?\s*(?P<high>" + _NUMBER + r"))?"
    r"\s*(?:" + _PERIOD_PATTERN + r")?",
    re.IGNORECASE,
)


@dataclass
class SalaryEstimate:
    stated: bool
    usd_per_month_min: float | None
    usd_per_month_max: float | None
    raw_currency: str | None
    raw_period: str | None
    source: str  # "structured" | "extracted_from_text" | "not_disclosed"
    note: str


def _parse_number(text: str) -> float | None:
    text = text.strip()
    multiplier = 1.0
    if text.lower().endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    text = text.replace(",", "")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _normalize_currency(raw: str) -> str | None:
    return _CURRENCY_SYMBOLS.get(raw.strip().upper()) or _CURRENCY_SYMBOLS.get(raw.strip())


def _to_usd_per_month(amount: float, currency: str, period: str | None) -> float | None:
    rate = FX_TO_USD.get(currency)
    if rate is None:
        return None
    monthly_factor = _PERIOD_TO_MONTHLY_FACTOR.get((period or "").lower(), 1.0)
    return amount * rate * monthly_factor


def _from_structured(job) -> SalaryEstimate | None:
    """Prefer a structured salary field when the source provides one (e.g.
    Recruitee's `salary` object) — more reliable than regexing free text."""
    salary_min = getattr(job, "salary_min", None)
    salary_max = getattr(job, "salary_max", None)
    currency_raw = getattr(job, "salary_currency", None)
    period_raw = getattr(job, "salary_period", None)

    if salary_min is None and salary_max is None:
        return None
    if not currency_raw:
        return None

    # Recruitee's API returns salary.min/max as numeric-looking strings
    # ("6453"), not numbers — coerce defensively rather than assuming any
    # source's "structured" field is already the right type.
    salary_min = _parse_number(str(salary_min)) if salary_min is not None else None
    salary_max = _parse_number(str(salary_max)) if salary_max is not None else None

    currency = _normalize_currency(currency_raw)
    if not currency:
        return SalaryEstimate(
            stated=True, usd_per_month_min=None, usd_per_month_max=None,
            raw_currency=currency_raw, raw_period=period_raw,
            source="structured",
            note=f"Structured salary given in unrecognized currency {currency_raw!r} — FX table has no rate for it.",
        )

    low = _to_usd_per_month(salary_min, currency, period_raw) if salary_min is not None else None
    high = _to_usd_per_month(salary_max, currency, period_raw) if salary_max is not None else None
    return SalaryEstimate(
        stated=True, usd_per_month_min=low, usd_per_month_max=high,
        raw_currency=currency, raw_period=period_raw, source="structured",
        note=f"From posting's structured salary field ({currency} {period_raw or 'period unspecified'}).",
    )


# A currency+number+period match is ambiguous on its own — job descriptions
# routinely mention OTHER money figures that aren't salary (a training
# budget, an equipment allowance, a signing bonus separate from base pay,
# funding raised, revenue). Observed live: Fastned's "training and
# development budget of €3,000 per year" matched the bare pattern and
# produced a nonsense $270/month "salary". Most real postings state a plain
# "$X - $Y per year" without ever using the word "salary" nearby, so this
# is a blocklist, not a required-keyword allowlist — reject only when a
# specific non-salary context word appears close to the match.
_NON_SALARY_CONTEXT_KEYWORDS = re.compile(
    r"\b(budget|allowance|stipend|bonus|revenue|funding|raised|discount|"
    r"reimburse|training|development\s*budget|equipment|travel)\b", re.IGNORECASE,
)
_CONTEXT_WINDOW_CHARS = 60


def _from_text(description: str) -> SalaryEstimate | None:
    if not description:
        return None

    for match in _SALARY_PATTERN.finditer(description):
        currency = _normalize_currency(match.group("currency"))
        if not currency:
            continue

        low_val = _parse_number(match.group("low"))
        high_raw = match.group("high")
        high_val = _parse_number(high_raw) if high_raw else None
        if low_val is None:
            continue

        period_match = re.search(_PERIOD_PATTERN, match.group(0), re.IGNORECASE)
        period = None
        if period_match:
            period = (period_match.group("period_word") or period_match.group("period_abbrev") or "").lower()
        # No period stated — don't guess which one. An unlabeled number is
        # at least as likely to be annual as monthly in most English-
        # language job postings, so defaulting to "monthly" would
        # misrepresent the figure by roughly 12x.
        if period is None:
            continue

        window_start = max(0, match.start() - _CONTEXT_WINDOW_CHARS)
        window = description[window_start:match.start()]
        if _NON_SALARY_CONTEXT_KEYWORDS.search(window):
            continue

        usd_low = _to_usd_per_month(low_val, currency, period)
        usd_high = _to_usd_per_month(high_val, currency, period) if high_val is not None else usd_low

        # Sanity floor/ceiling against a stray number that slipped past the
        # context check. No real professional role pays under ~$100/month
        # or over ~$250,000/month; outside that band, keep looking rather
        # than report something misleading.
        if usd_low is not None and not (100 <= usd_low <= 250_000):
            continue

        return SalaryEstimate(
            stated=True, usd_per_month_min=usd_low, usd_per_month_max=usd_high,
            raw_currency=currency, raw_period=period, source="extracted_from_text",
            note=f"Extracted from JD text: {match.group(0).strip()!r} (period: {period}).",
        )

    return None


def estimate_salary(job, description: str | None = None) -> SalaryEstimate:
    """Estimate approx pay in USD/month for a job. Checks the source's own
    structured salary field first, then falls back to regex extraction from
    the job description. Returns 'not disclosed' rather than guessing when
    neither is available — see module docstring for why."""
    structured = _from_structured(job)
    if structured is not None:
        return structured

    text_result = _from_text(description if description is not None else getattr(job, "description_raw", ""))
    if text_result is not None:
        return text_result

    return SalaryEstimate(
        stated=False, usd_per_month_min=None, usd_per_month_max=None,
        raw_currency=None, raw_period=None, source="not_disclosed",
        note="No salary stated in the posting or its structured data — not disclosed, not estimated.",
    )
