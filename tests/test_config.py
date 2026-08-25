"""Tests for config.py"""

import json
from pathlib import Path

from job_research.config import Config, JobSearchParams, WorkType
from job_research.sources import catalog


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


def _clear_source_env(monkeypatch):
    monkeypatch.setattr("job_research.config.load_dotenv", lambda: None)
    monkeypatch.delenv("ENABLED_SOURCES", raising=False)
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


def test_enabled_sources_default_to_the_registry(monkeypatch):
    _clear_source_env(monkeypatch)
    config = Config.from_env()
    assert set(config.search_params.enabled_sources) == set(catalog.DEFAULT_ENABLED)


def test_enabled_sources_read_from_env(monkeypatch):
    _clear_source_env(monkeypatch)
    monkeypatch.setenv("ENABLED_SOURCES", "stepstone, indeed")
    config = Config.from_env()
    assert config.search_params.enabled_sources == ["stepstone", "indeed"]


def test_unknown_source_ids_are_dropped_not_fatal(monkeypatch):
    """A typo should cost you one source, not the whole run."""
    _clear_source_env(monkeypatch)
    monkeypatch.setenv("ENABLED_SOURCES", "indeed, stepstoen")
    config = Config.from_env()
    assert config.search_params.enabled_sources == ["indeed"]


def test_all_unknown_source_ids_fall_back_to_defaults(monkeypatch):
    _clear_source_env(monkeypatch)
    monkeypatch.setenv("ENABLED_SOURCES", "nope, alsonope")
    config = Config.from_env()
    assert set(config.search_params.enabled_sources) == set(catalog.DEFAULT_ENABLED)


def test_legacy_search_vars_still_work(monkeypatch):
    """An existing .env must not silently change which boards get searched."""
    _clear_source_env(monkeypatch)
    monkeypatch.setenv("SEARCH_STEPSTONE", "true")
    monkeypatch.setenv("SEARCH_INDEED", "true")
    config = Config.from_env()
    assert config.search_params.enabled_sources == ["indeed", "stepstone"]


def test_enabled_sources_takes_precedence_over_legacy_vars(monkeypatch):
    _clear_source_env(monkeypatch)
    monkeypatch.setenv("SEARCH_STEPSTONE", "true")
    monkeypatch.setenv("ENABLED_SOURCES", "linkedin")
    config = Config.from_env()
    assert config.search_params.enabled_sources == ["linkedin"]


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
    assert "output" in d
    assert d["search_params"]["keywords"] == "AI Engineer"
    assert d["output"]["output_format"] == "markdown"
    assert set(d["search_params"]["enabled_sources"]) == set(catalog.DEFAULT_ENABLED)


def test_config_to_dict_covers_every_field_except_the_secret():
    """Generated from fields(), so a new field cannot go missing the way four did."""
    from dataclasses import fields

    d = Config().to_dict()
    expected = {f.name for f in fields(Config)} - {"claude_api_key"}
    assert set(d) == expected


def test_config_to_dict_excludes_the_api_key():
    d = Config(claude_api_key="sk-ant-secret").to_dict()
    assert "claude_api_key" not in d
    assert "sk-ant-secret" not in json.dumps(d)


def test_config_to_dict_is_json_serializable():
    """It gets written to disk, so Paths and Enums must already be plain."""
    json.dumps(Config().to_dict())


# ------------------------------------------------------- secret masking


def test_repr_masks_the_api_key():
    """A Config must never print its key: reprs reach tracebacks and CI logs."""
    secret = "sk-ant-api03-" + "A" * 80 + "mPoQAA"
    rendered = repr(Config(claude_api_key=secret))

    assert secret not in rendered
    assert "claude_api_key='sk-ant-…mPoQAA'" in rendered


def test_repr_hides_short_secrets_entirely():
    """Too short to show a prefix and suffix without giving most of it away."""
    assert "claude_api_key='***'" in repr(Config(claude_api_key="sk-ant-short"))


def test_repr_reports_a_missing_key_as_none():
    assert "claude_api_key=None" in repr(Config(claude_api_key=None))


def test_repr_still_shows_every_field():
    """Generated from fields(), so a newly added field cannot silently vanish."""
    from dataclasses import fields

    rendered = repr(Config())
    for f in fields(Config):
        assert f"{f.name}=" in rendered


def test_repr_survives_nesting_inside_another_object():
    """The mask must hold wherever the Config ends up, not just at top level."""
    secret = "sk-ant-api03-" + "B" * 80 + "zzTOP1"
    assert secret not in repr({"config": Config(claude_api_key=secret)})


def test_api_key_attribute_is_still_the_real_value():
    secret = "sk-ant-api03-" + "C" * 80
    assert Config(claude_api_key=secret).claude_api_key == secret
