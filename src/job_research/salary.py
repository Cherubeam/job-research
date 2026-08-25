"""Parsing free-text salary strings into an annual EUR range.

Job boards state pay in whatever unit the employer used — per hour, per month,
per year — and surround it with numbers that are not pay at all: contract hours,
a posting year, a team size. Reading "the first two integers" as a range gets
all of these wrong.

Two rules do most of the work:

* **Detect the period** from the words around the figure and convert to annual,
  so an hourly rate and a salary are comparable.
* **Reject implausible figures for that period.** A 35 in a string about annual
  pay is contract hours; a 2026 is the posting year. Banding by period discards
  both without special-casing either.
"""

import re

# Hours per week x weeks per year. The German statutory-ish full-time week is
# closer to 38-40; 40 keeps the arithmetic conventional and the result an
# estimate either way.
_HOURS_PER_YEAR = 40 * 52
_MONTHS_PER_YEAR = 12

_HOURLY_MARKERS = re.compile(
    r"(pro\s+stunde|je\s+stunde|stündlich|per\s+hour|/\s*(h|hr|std|stunde)\b|"
    r"\bp\.?\s*h\.?\b|\bhourly\b|€\s*/\s*std)",
    re.IGNORECASE,
)
_MONTHLY_MARKERS = re.compile(
    r"(pro\s+monat|je\s+monat|monatlich|per\s+month|/\s*(monat|month|mo)\b|"
    r"\bp\.?\s*m\.?\b|\bmonthly\b|\bbrutto\s*/\s*monat)",
    re.IGNORECASE,
)

# Figures that cannot be pay for the detected period. Anything outside the band
# is noise: contract hours, a posting year, a headcount.
_PLAUSIBLE = {
    "hour": (5, 2_000),
    "month": (400, 200_000),
    "year": (10_000, 2_000_000),
}

# "35 Std./Woche", "39h/Woche" — contract hours, never pay. Removed before
# parsing so the number cannot be mistaken for a bound.
_HOURS_PER_WEEK = re.compile(
    r"\d+([.,]\d+)?\s*(std|stunden|stunde|h|hours?)\s*\.?\s*/?\s*(woche|week|wk)\b",
    re.IGNORECASE,
)


def detect_period(text: str) -> str:
    """Return the pay period *text* describes: "hour", "month", or "year"."""
    if _HOURLY_MARKERS.search(text):
        return "hour"
    if _MONTHLY_MARKERS.search(text):
        return "month"
    return "year"


def to_annual(amount: float, period: str) -> int:
    """Convert *amount* stated per *period* into an annual figure."""
    if period == "hour":
        return round(amount * _HOURS_PER_YEAR)
    if period == "month":
        return round(amount * _MONTHS_PER_YEAR)
    return round(amount)


def parse_salary_range(salary_str: str) -> tuple[int | None, int | None]:
    """Parse a salary string into an annual (min, max) in whole currency units.

    Returns `(None, None)` when nothing plausible is found — an honest "unknown"
    beats a confident wrong number, since a bad figure silently skews every
    salary statistic downstream.
    """
    if not salary_str or not salary_str.strip():
        return None, None

    period = detect_period(salary_str)

    text = _HOURS_PER_WEEK.sub(" ", salary_str)
    # "70k" -> "70000", before separators are touched.
    text = re.sub(r"(\d+)\s*[kK]\b", lambda m: str(int(m.group(1)) * 1000), text)
    text = re.sub(r"[€$£]", " ", text)
    # German thousands separator: 70.000 -> 70000. Only when exactly three
    # digits follow, so a decimal like "25.50" survives as a decimal.
    text = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", text)
    # English thousands separator, and the German decimal comma.
    text = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", text)
    text = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", text)

    low, high = _PLAUSIBLE[period]
    values = [
        annual
        for raw in re.findall(r"\d+(?:\.\d+)?", text)
        if low <= float(raw) <= high
        for annual in [to_annual(float(raw), period)]
    ]

    if not values:
        return None, None
    if len(values) == 1:
        return values[0], None
    return min(values[0], values[1]), max(values[0], values[1])
