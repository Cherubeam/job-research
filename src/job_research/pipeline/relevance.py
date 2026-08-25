"""Scoring a job title against what the user actually searched for.

This replaces a single-token OR test that kept any title sharing one word with
the query. With the default alternatives, that token set was
`{ai, engineer, machine, learning, artificial, intelligence, deep, ml}`, so
"Sales Engineer" and "Learning & Development Manager" both passed.

Scoring instead asks *what fraction of a search phrase the title covers*, and
keeps titles that clear a threshold. "Sales Engineer" covers 1 of the 2 tokens
in "AI Engineer" — 0.5, below the 0.6 default — while "Senior AI Engineer
(m/w/d)" covers both.
"""

import logging
import re

from job_research.analyzer import JobListing

logger = logging.getLogger(__name__)

# Words that carry no signal about *what kind* of role a title describes:
# seniority markers, gender markers, and grammatical filler. Removed from both
# the query and the title so they neither create nor block a match.
_TITLE_STOPWORDS = frozenset(
    {
        "senior",
        "junior",
        "lead",
        "staff",
        "principal",
        "head",
        "m/w/d",
        "f/m/d",
        "w/m/d",
        "gn",
        "d",
        "m",
        "f",
        "w",
        "in",
        "und",
        "and",
        "the",
        "for",
        "of",
        "de",
        "der",
        "die",
        "das",
    }
)

DEFAULT_THRESHOLD = 0.6
"""Keep a title covering more than half of some search phrase.

0.5 exactly is the "shares only the generic role noun" case — "Sales Engineer"
against "AI Engineer" — which is precisely the noise this exists to remove.
"""


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.split(r"[\s/,;()\-]+", text.lower())
        if token and token not in _TITLE_STOPWORDS
    ]


def score_title(title: str, keywords: str, alternatives: list[str] | None = None) -> float:
    """Return how well *title* covers the best-matching search phrase, in [0, 1].

    A phrase whose tokens all appear in the title scores 1.0. Otherwise the
    score is the largest fraction of any single phrase's tokens that the title
    contains — judged per phrase, not against the pooled token set, so a title
    cannot be rescued by collecting one token each from several phrases.
    """
    phrases = [keywords, *(alternatives or [])]
    title_tokens = set(_tokenize(title))
    if not title_tokens:
        return 0.0

    best = 0.0
    for phrase in phrases:
        phrase_tokens = set(_tokenize(phrase))
        if not phrase_tokens:
            continue
        covered = len(phrase_tokens & title_tokens) / len(phrase_tokens)
        best = max(best, covered)
    return best


def is_excluded(title: str, excluded_keywords: list[str]) -> bool:
    """True if *title* contains any excluded phrase.

    Matched on token sequences rather than raw substrings, so excluding "sales"
    does not also reject "Salesforce Engineer".
    """
    title_tokens = re.split(r"[\s/,;()\-]+", title.lower())
    for phrase in excluded_keywords:
        wanted = [t for t in re.split(r"[\s/,;()\-]+", phrase.lower()) if t]
        if not wanted:
            continue
        span = len(wanted)
        if any(title_tokens[i : i + span] == wanted for i in range(len(title_tokens) - span + 1)):
            return True
    return False


def filter_by_relevance(
    listings: list[JobListing],
    keywords: str,
    alternatives: list[str] | None = None,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    excluded_keywords: list[str] | None = None,
) -> list[JobListing]:
    """Keep listings whose title scores at or above *threshold* and is not excluded."""
    excluded_keywords = excluded_keywords or []
    kept = []
    for listing in listings:
        if is_excluded(listing.title, excluded_keywords):
            logger.debug("Excluded by keyword: %s", listing.title)
            continue
        score = score_title(listing.title, keywords, alternatives)
        if score < threshold:
            logger.debug("Below relevance threshold (%.2f): %s", score, listing.title)
            continue
        kept.append(listing)
    return kept
