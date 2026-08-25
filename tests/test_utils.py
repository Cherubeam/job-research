"""Tests for utils.py"""

from datetime import datetime, timedelta
from unittest.mock import patch

from job_research.utils import (
    create_cache_key,
    generate_output_filename,
    save_cache,
    load_cache,
    format_salary,
    extract_number_from_text,
)


def test_create_cache_key_is_deterministic():
    key1 = create_cache_key("board", keywords="AI Engineer", location="Berlin")
    key2 = create_cache_key("board", keywords="AI Engineer", location="Berlin")
    assert key1 == key2


def test_create_cache_key_ignores_keyword_argument_order():
    key1 = create_cache_key("board", keywords="AI Engineer", location="Berlin")
    key2 = create_cache_key("board", location="Berlin", keywords="AI Engineer")
    assert key1 == key2


def test_create_cache_key_differs_on_backend():
    key1 = create_cache_key("jobspy", keywords="AI Engineer")
    key2 = create_cache_key("claude_web_search", keywords="AI Engineer")
    assert key1 != key2


def test_create_cache_key_differs_on_different_inputs():
    key1 = create_cache_key("board", keywords="AI Engineer", location="Berlin")
    key2 = create_cache_key("board", keywords="ML Engineer", location="Berlin")
    key3 = create_cache_key("board", keywords="AI Engineer", location="Munich")
    assert key1 != key2
    assert key1 != key3
    assert key2 != key3


def test_create_cache_key_differs_on_work_type():
    key1 = create_cache_key("board", keywords="AI Engineer", work_type="Remote only")
    key2 = create_cache_key("board", keywords="AI Engineer", work_type="Onsite only")
    assert key1 != key2


def test_create_cache_key_distinguishes_added_parameters():
    """An extra fetch input must change the key, never collide with its absence."""
    key1 = create_cache_key("board", keywords="AI Engineer")
    key2 = create_cache_key("board", keywords="AI Engineer", boards=("de.indeed.com",))
    assert key1 != key2


def test_create_cache_key_does_not_collide_across_value_boundaries():
    """Values are repr'd, so "a"+"bc" cannot hash the same as "ab"+"c"."""
    key1 = create_cache_key("board", x="a", y="bc")
    key2 = create_cache_key("board", x="ab", y="c")
    assert key1 != key2


def test_save_and_load_cache_roundtrip(tmp_path):
    data = [{"title": "AI Engineer", "company": "TechCorp"}]
    key = "test_key"

    save_cache(tmp_path, key, data, duration_hours=24)
    loaded = load_cache(tmp_path, key)

    assert loaded == data


def test_load_cache_returns_none_for_missing(tmp_path):
    assert load_cache(tmp_path, "nonexistent") is None


def test_load_cache_returns_none_for_expired(tmp_path):
    data = {"value": 42}
    key = "expired_key"
    save_cache(tmp_path, key, data, duration_hours=1)

    # Patch datetime.now to be 2 hours in the future
    future = datetime.now() + timedelta(hours=2)
    with patch("job_research.utils.datetime") as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.fromisoformat = datetime.fromisoformat
        result = load_cache(tmp_path, key)

    assert result is None


def test_format_salary_with_values():
    assert format_salary(70000, 100000) == "EUR 70,000 - 100,000"


def test_format_salary_missing():
    assert format_salary(None, None) == "N/A"
    assert format_salary(70000, None) == "N/A"


def test_generate_output_filename_format():
    name = generate_output_filename("job_search", "md")
    assert name.startswith("job_search_")
    assert name.endswith(".md")
    # Timestamp part: YYYY-MM-DD_HHMMSS
    parts = name.removeprefix("job_search_").removesuffix(".md")
    assert len(parts) == len("2026-03-13_143000")


def test_generate_output_filename_csv():
    name = generate_output_filename("report", "csv")
    assert name.startswith("report_")
    assert name.endswith(".csv")


def test_extract_number_from_text():
    assert extract_number_from_text("80000 EUR") == 80000
    assert extract_number_from_text("salary: 95.000") == 95000
    assert extract_number_from_text("no numbers here") is None
