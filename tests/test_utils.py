"""Tests for utils.py"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from job_research.utils import (
    create_cache_key,
    save_cache,
    load_cache,
    format_salary,
    extract_number_from_text,
)


def test_create_cache_key_is_deterministic():
    key1 = create_cache_key("board", "AI Engineer", "Berlin")
    key2 = create_cache_key("board", "AI Engineer", "Berlin")
    assert key1 == key2


def test_create_cache_key_differs_on_different_inputs():
    key1 = create_cache_key("board", "AI Engineer", "Berlin")
    key2 = create_cache_key("board", "ML Engineer", "Berlin")
    key3 = create_cache_key("board", "AI Engineer", "Munich")
    assert key1 != key2
    assert key1 != key3
    assert key2 != key3


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


def test_extract_number_from_text():
    assert extract_number_from_text("80000 EUR") == 80000
    assert extract_number_from_text("salary: 95.000") == 95000
    assert extract_number_from_text("no numbers here") is None
