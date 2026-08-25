"""Tests for stable job identity — the slug+hash id and its normalization."""

import pytest

from job_research.identity import identity_key, job_id, normalize_location, normalize_text


# ------------------------------------------------------------- normalization


@pytest.mark.parametrize(
    "title",
    [
        "AI Engineer (m/w/d)",
        "AI Engineer (w/m/d)",
        "AI Engineer m/w/d",
        "AI Engineer (all genders)",
        "  ai   engineer  ",
        "AI-Engineer",
    ],
)
def test_gender_markers_and_punctuation_normalize_away(title):
    assert normalize_text(title) == normalize_text("AI Engineer")


@pytest.mark.parametrize(
    "location",
    ["Berlin", "Berlin, Germany", "Berlin, Berlin, Deutschland", "Berlin (Remote)"],
)
def test_location_variants_normalize_together(location):
    assert normalize_location(location) == "berlin"


def test_different_cities_stay_distinct():
    assert normalize_location("Berlin") != normalize_location("München")


# -------------------------------------------------------------------- job_id


def test_same_posting_gets_the_same_id_however_it_is_spelled():
    """The whole point: Indeed and the Bundesagentur must agree on the id."""
    a = job_id("AI Engineer (m/w/d)", "Acme GmbH", "Berlin, Germany")
    b = job_id("ai engineer", "Acme GmbH", "Berlin")
    assert a == b


def test_id_is_stable_across_calls():
    assert job_id("AI Engineer", "Acme", "Berlin") == job_id("AI Engineer", "Acme", "Berlin")


def test_id_is_readable():
    assert job_id("AI Engineer", "Acme GmbH", "Berlin").startswith("ai-engineer-acme-gmbh-berlin-")


def test_id_ends_in_a_hex_digest():
    slug, _, digest = job_id("AI Engineer", "Acme", "Berlin").rpartition("-")
    assert slug
    assert len(digest) == 8
    assert all(c in "0123456789abcdef" for c in digest)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (("AI Engineer", "Acme", "Berlin"), ("AI Engineer", "Acme", "Munich")),
        (("AI Engineer", "Acme", "Berlin"), ("AI Engineer", "Globex", "Berlin")),
        (("AI Engineer", "Acme", "Berlin"), ("ML Engineer", "Acme", "Berlin")),
    ],
)
def test_different_postings_get_different_ids(a, b):
    assert job_id(*a) != job_id(*b)


def test_umlauts_transliterate_rather_than_disappear():
    """ "Müller" must not become "Mller", nor collide with "Muller"."""
    ident = job_id("Ingenieur", "Müller GmbH", "München")
    assert "mueller" in ident
    assert "muenchen" in ident
    assert ident != job_id("Ingenieur", "Muller GmbH", "Munchen")


def test_id_is_filesystem_safe():
    """It may become a filename in a Markdown vault, so nothing exotic."""
    ident = job_id("Senior AI/ML Engineer (m/w/d) — 100% Remote!", "Acme & Co. KG", "Köln")
    assert all(c.islower() or c.isdigit() or c == "-" for c in ident)
    assert "--" not in ident
    assert not ident.startswith("-") and not ident.endswith("-")


def test_long_titles_are_truncated_at_a_word_boundary():
    ident = job_id(
        "Senior Principal Distinguished Machine Learning Infrastructure Platform Engineer",
        "A Very Long Company Name GmbH und Co KGaA",
        "Berlin",
    )
    slug = ident.rsplit("-", 1)[0]
    assert len(slug) <= 60
    # Truncation must not leave a partial word at the end.
    assert not slug.endswith("-")


def test_truncated_slugs_still_get_distinct_ids():
    """Two postings whose slugs collide after truncation must not share an id."""
    prefix = "Senior Principal Distinguished Machine Learning Infrastructure Platform"
    a = job_id(f"{prefix} Engineer", "Acme", "Berlin")
    b = job_id(f"{prefix} Architect", "Acme", "Berlin")
    assert a.rsplit("-", 1)[0] == b.rsplit("-", 1)[0]  # same slug
    assert a != b  # different id


def test_empty_fields_still_produce_a_usable_id():
    ident = job_id("", "", "")
    assert ident.startswith("job-")
    assert len(ident) > len("job-")


def test_identity_key_matches_the_id_input():
    """The id is derived from the identity, so the two cannot drift apart."""
    key = identity_key("AI Engineer (m/w/d)", "Acme GmbH", "Berlin, Germany")
    assert key == ("ai engineer", "acme gmbh", "berlin")
