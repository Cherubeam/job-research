"""Tests for config.py"""

import json
from pathlib import Path

from job_research.config import Config, JobSearchParams, WorkType


def test_config_default_construction():
    config = Config()
    assert config.verbose is False
    assert config.claude_api_key is None
    assert config.claude_model == "claude-haiku-4-5-20251001"
    assert config.max_jobs_per_search == 200
    assert isinstance(config.search_params, JobSearchParams)


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("JOB_KEYWORDS", "ML Engineer")
    monkeypatch.setenv("LOCATION", "Munich")
    monkeypatch.setenv("WORK_TYPE", "Remote only")
    monkeypatch.setenv("SALARY_MINIMUM", "60000")
    monkeypatch.setenv("SALARY_MAXIMUM", "130000")
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("MAX_JOBS_PER_SEARCH", "30")
    monkeypatch.setenv("VERBOSE", "true")
    monkeypatch.setenv("SCRAPER_BACKEND", "claude")

    config = Config.from_env()

    assert config.search_params.keywords == "ML Engineer"
    assert config.search_params.location == "Munich"
    assert config.search_params.work_type == WorkType.REMOTE
    assert config.search_params.salary_minimum == 60000
    assert config.search_params.salary_maximum == 130000
    assert config.claude_api_key == "sk-test-key"
    assert config.claude_model == "claude-haiku-4-5-20251001"
    assert config.max_jobs_per_search == 30
    assert config.verbose is True


def test_config_from_env_defaults_only_indeed(monkeypatch):
    """Without SEARCH_* env vars, only Indeed should be enabled."""
    # Prevent .env file from injecting values
    monkeypatch.setattr("job_research.config.load_dotenv", lambda: None)
    # Clear any SEARCH_* vars that might be set
    for board in [
        "STEPSTONE",
        "INDEED",
        "LINKEDIN",
        "MONSTER",
        "HONEYPOT",
        "STARTUPS",
        "ARBEITSAGENTUR",
    ]:
        monkeypatch.delenv(f"SEARCH_{board}", raising=False)
    monkeypatch.delenv("SCRAPER_BACKEND", raising=False)

    config = Config.from_env()

    assert config.job_boards.search_indeed is True
    assert config.job_boards.search_stepstone is False
    assert config.job_boards.search_linkedin is False
    assert config.job_boards.search_monster is False
    assert config.job_boards.search_honeypot is False
    assert config.job_boards.search_startups is False
    assert config.job_boards.search_arbeitsagentur is False


def test_config_from_json(tmp_path: Path):
    data = {
        "search_params": {
            "keywords": "Data Scientist",
            "location": "Hamburg",
        },
        "job_boards": {},
        "output": {},
        "verbose": True,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(data))

    config = Config.from_json(config_file)
    assert config.search_params.keywords == "Data Scientist"
    assert config.search_params.location == "Hamburg"
    assert config.verbose is True


def test_config_to_dict():
    config = Config()
    d = config.to_dict()

    assert "search_params" in d
    assert "job_boards" in d
    assert "output" in d
    assert "keywords" in d["search_params"]
    assert "output_format" in d["output"]
