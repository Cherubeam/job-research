"""Utility functions for job research"""

import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional


def create_cache_key(
    board: str,
    keywords: str,
    location: str,
    work_type: str = "",
    seniority_level: str = "",
    salary_min: int = 0,
    salary_max: int = 0,
) -> str:
    """Create a cache key from search parameters"""
    key_str = f"{board}:{keywords}:{location}:{work_type}:{seniority_level}:{salary_min}:{salary_max}"
    return hashlib.md5(key_str.encode()).hexdigest()


def save_cache(cache_dir: Path, key: str, data: Any, duration_hours: int = 24) -> None:
    """Save data to cache"""
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_entry = {
        "data": data,
        "timestamp": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=duration_hours)).isoformat(),
    }

    cache_file = cache_dir / f"{key}.json"
    with open(cache_file, 'w') as f:
        json.dump(cache_entry, f)


def load_cache(cache_dir: Path, key: str) -> Optional[Any]:
    """Load data from cache if valid"""
    cache_file = cache_dir / f"{key}.json"

    if not cache_file.exists():
        return None

    with open(cache_file, 'r') as f:
        cache_entry = json.load(f)

    expires_at = datetime.fromisoformat(cache_entry["expires_at"])
    if datetime.now() > expires_at:
        cache_file.unlink()  # Delete expired cache
        return None

    return cache_entry["data"]


def ensure_directories(output_dir: Path, cache_dir: Path) -> None:
    """Ensure required directories exist"""
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)


def format_salary(min_salary: Optional[int], max_salary: Optional[int], currency: str = "EUR") -> str:
    """Format salary range as string"""
    if not min_salary or not max_salary:
        return "N/A"
    return f"{currency} {min_salary:,} - {max_salary:,}"


def generate_output_filename(prefix: str = "job_search", ext: str = "md") -> str:
    """Generate a timestamped output filename."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{prefix}_{timestamp}.{ext}"


def extract_number_from_text(text: str) -> Optional[int]:
    """Extract first number from text"""
    import re
    match = re.search(r'\d+(?:\.\d+)?', text.replace('.', '').replace(',', ''))
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None
    return None
