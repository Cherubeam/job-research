"""Tests for salary.py — period detection and annualisation."""

import pytest

from job_research import salary


# ------------------------------------------------------------ period detection


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("25 € / Stunde", "hour"),
        ("25 EUR pro Stunde", "hour"),
        ("€25 per hour", "hour"),
        ("25 €/h", "hour"),
        ("5.000 € pro Monat", "month"),
        ("5000 EUR monatlich", "month"),
        ("5000 per month", "month"),
        ("70.000 € pro Jahr", "year"),
        ("70000 p.a.", "year"),
        ("70.000 - 95.000 €", "year"),
        ("", "year"),
    ],
)
def test_detect_period(text, expected):
    assert salary.detect_period(text) == expected


def test_period_defaults_to_year():
    """An unmarked figure on a job board is an annual salary far more often than not."""
    assert salary.detect_period("80000") == "year"


# --------------------------------------------------------------- annualising


@pytest.mark.parametrize(
    ("amount", "period", "expected"),
    [
        (70000, "year", 70000),
        (5000, "month", 60000),
        (25, "hour", 52000),
    ],
)
def test_to_annual(amount, period, expected):
    assert salary.to_annual(amount, period) == expected


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # plain annual ranges
        ("€70.000 - €95.000", (70000, 95000)),
        ("70000-95000", (70000, 95000)),
        ("EUR 80,000 to 120,000", (80000, 120000)),
        ("70k - 95k", (70000, 95000)),
        ("ab 60.000 €", (60000, None)),
        # period conversion
        ("5.000 € pro Monat", (60000, None)),
        ("4.000 - 5.000 € pro Monat", (48000, 60000)),
        ("25 € / Stunde", (52000, None)),
        ("25,50 € pro Stunde", (53040, None)),
        # figures that are not pay
        ("35 Std./Woche, 60.000 €", (60000, None)),
        ("2026: 70.000 - 95.000 €", (70000, 95000)),
        # nothing usable
        ("", (None, None)),
        ("   ", (None, None)),
        ("competitive", (None, None)),
        ("Gehalt nach Vereinbarung", (None, None)),
    ],
)
def test_parse_salary_range(raw, expected):
    assert salary.parse_salary_range(raw) == expected


def test_range_is_returned_low_to_high_even_when_written_backwards():
    assert salary.parse_salary_range("95.000 - 70.000 €") == (70000, 95000)


def test_implausible_annual_figures_are_discarded():
    """A team size or a job id must never become a salary bound."""
    assert salary.parse_salary_range("Team of 12, 5 offices") == (None, None)


def test_only_the_first_two_plausible_figures_are_used():
    """Trailing noise past the range must not widen it."""
    assert salary.parse_salary_range("70.000 - 95.000 € (Stufe 120.000 möglich)") == (70000, 95000)


def test_hourly_rate_below_the_plausible_floor_is_ignored():
    assert salary.parse_salary_range("2 € pro Stunde") == (None, None)


def test_annualised_hourly_matches_the_documented_convention():
    """40h x 52 weeks — an estimate, and the tests should say so out loud."""
    assert salary.parse_salary_range("50 € / Stunde") == (50 * 40 * 52, None)
