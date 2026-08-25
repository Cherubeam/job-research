"""Tests for pipeline.relevance — scored title matching and negative keywords."""

import pytest

from job_research.analyzer import JobListing
from job_research.pipeline import relevance

ALTERNATIVES = ["Machine Learning Engineer", "ML Engineer", "Deep Learning Engineer"]


# ------------------------------------------------------------------- scoring


def test_exact_title_scores_one():
    assert relevance.score_title("AI Engineer", "AI Engineer") == 1.0


def test_seniority_and_gender_markers_do_not_dilute_the_score():
    """Extra words in the title are free; only phrase coverage counts."""
    assert relevance.score_title("Senior AI Engineer (m/w/d)", "AI Engineer") == 1.0


def test_scoring_is_case_insensitive():
    assert relevance.score_title("ai engineer", "AI Engineer") == 1.0


def test_alternative_phrase_can_carry_the_match():
    score = relevance.score_title("Machine Learning Engineer", "AI Engineer", ALTERNATIVES)
    assert score == 1.0


def test_sharing_only_the_generic_role_noun_scores_half():
    """The exact case the old single-token filter let through."""
    assert relevance.score_title("Sales Engineer", "AI Engineer") == 0.5


def test_unrelated_title_scores_zero():
    assert relevance.score_title("Shopify Backend Developer", "AI Engineer", ALTERNATIVES) == 0.0


def test_partial_phrase_coverage_scores_proportionally():
    # "Deep Learning Engineer" -> 2 of 3 tokens present
    score = relevance.score_title("Deep Learning Researcher", "AI Engineer", ALTERNATIVES)
    assert score == pytest.approx(2 / 3)


def test_tokens_scattered_across_phrases_do_not_add_up_to_a_match():
    """Coverage is judged per phrase, not against the pooled token set.

    "Deep Sea Machine Operator" borrows "deep" from one alternative and
    "machine" from another. The old rule kept anything sharing a single token
    with the pool, so it passed; per-phrase, its best coverage is 1 of 3.
    """
    score = relevance.score_title("Deep Sea Machine Operator", "AI Engineer", ALTERNATIVES)
    assert score == pytest.approx(1 / 3)
    assert score < relevance.DEFAULT_THRESHOLD


def test_a_related_specialisation_still_matches():
    """Coverage is about the phrase, so adjacent roles are not over-filtered."""
    score = relevance.score_title("Machine Vision Engineer", "AI Engineer", ALTERNATIVES)
    assert score >= relevance.DEFAULT_THRESHOLD


def test_empty_title_scores_zero():
    assert relevance.score_title("", "AI Engineer") == 0.0


def test_title_of_only_stopwords_scores_zero():
    assert relevance.score_title("Senior (m/w/d)", "AI Engineer") == 0.0


# ------------------------------------------------------------ exclusions


def test_excluded_phrase_matches_on_token_boundaries():
    assert relevance.is_excluded("Sales Engineer", ["sales"])


def test_excluded_phrase_does_not_match_inside_a_longer_word():
    """Excluding "sales" must not reject Salesforce roles."""
    assert not relevance.is_excluded("Salesforce Engineer", ["sales"])


def test_multi_word_exclusion_requires_the_whole_sequence():
    assert relevance.is_excluded("Working Student Data Science", ["working student"])
    assert not relevance.is_excluded("Student Assistant", ["working student"])


def test_no_exclusions_excludes_nothing():
    assert not relevance.is_excluded("AI Engineer", [])


# --------------------------------------------------------------- filtering


def _listings(*titles: str) -> list[JobListing]:
    return [JobListing(title=t, company=f"Co{i}") for i, t in enumerate(titles)]


def test_filter_keeps_relevant_and_drops_noise():
    listings = _listings(
        "AI Engineer",
        "Senior Machine Learning Engineer",
        "Sales Engineer",
        "Shopify Backend Developer",
    )
    result = relevance.filter_by_relevance(listings, "AI Engineer", ALTERNATIVES)
    assert [lst.title for lst in result] == [
        "AI Engineer",
        "Senior Machine Learning Engineer",
    ]


def test_filter_applies_exclusions_before_scoring():
    listings = _listings("Werkstudent AI Engineer", "AI Engineer")
    result = relevance.filter_by_relevance(
        listings, "AI Engineer", excluded_keywords=["werkstudent"]
    )
    assert [lst.title for lst in result] == ["AI Engineer"]


def test_threshold_is_configurable():
    listings = _listings("Sales Engineer")
    assert relevance.filter_by_relevance(listings, "AI Engineer", threshold=0.5) == listings
    assert relevance.filter_by_relevance(listings, "AI Engineer", threshold=0.6) == []


def test_single_token_query_matches_any_title_containing_it():
    """A deliberately broad search should stay broad."""
    listings = _listings("Software Engineer", "Senior Manager")
    result = relevance.filter_by_relevance(listings, "Engineer")
    assert [lst.title for lst in result] == ["Software Engineer"]
