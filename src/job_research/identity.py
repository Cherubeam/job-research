"""Stable identity for a job posting.

Two things depend on getting this right, and both are expensive to change later:

* **Deduplication** needs the same posting to look the same however it was
  reached — Indeed, LinkedIn, and the Bundesagentur spell the same job
  differently.
* **The store** needs the same posting to keep the same id across runs, so
  "which of these did I not see yesterday" has an answer.

`job_id` is therefore derived from the posting's *content*, never from its URL
(which differs per source) or its position in a result set.

**The id is human-readable on purpose.** If job records later become files in a
Markdown vault, the id becomes the filename, and `ai-engineer-acme-berlin-3f9c2a1b`
is a filename you can scan while `3f9c2a1b7e...` is not. Umlauts are folded
rather than stripped, so the slug survives a trip through a filesystem that is
particular about encoding.
"""

import hashlib
import re
import unicodedata

_HASH_LENGTH = 8
"""Hex characters of digest appended to the slug.

32 bits. The slug already encodes title, company, and location, so a collision
needs both an identical slug *and* an identical digest prefix — the digest is a
tiebreaker between near-identical postings, not the sole discriminator.
"""

_MAX_SLUG_LENGTH = 60
"""Long enough to stay readable, short enough to be a filename on any system."""

# German (and Nordic) letters that transliterate to more than one ASCII letter.
# Unicode decomposition alone turns "ü" into "u", which collapses "Müller" and
# "Muller" — correct for search, wrong for a name in an id.
_TRANSLITERATIONS = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "å": "aa",
        "æ": "ae",
        "ø": "oe",
    }
)

# Gender markers German postings append to titles. Stripped before comparison so
# "AI Engineer (m/w/d)" and "AI Engineer (all genders)" are one job.
_GENDER_MARKERS = re.compile(
    r"\(?\s*(m\s*[/|]\s*w\s*[/|]\s*d|w\s*[/|]\s*m\s*[/|]\s*d|m\s*[/|]\s*f\s*[/|]\s*d|"
    r"m\s*[/|]\s*w\s*[/|]\s*x|gn|d\s*[/|]\s*m\s*[/|]\s*w|all\s+genders|divers)\s*\)?",
    re.IGNORECASE,
)

# Country and region suffixes boards append inconsistently: one source says
# "Berlin", another "Berlin, Germany", a third "Berlin, Berlin, Deutschland".
_LOCATION_NOISE = frozenset({"germany", "deutschland", "de", "remote", "hybrid", "onsite"})


def normalize_text(value: str) -> str:
    """Reduce a title or company name to its comparable core."""
    value = _GENDER_MARKERS.sub(" ", value.lower())
    return re.sub(r"[^\w]+", " ", value).strip()


def normalize_location(location: str) -> str:
    """Reduce a location to its most specific place name.

    Boards disagree about how much administrative context to append, so only the
    leading component is kept and country/work-mode noise is dropped. "Berlin",
    "Berlin, Germany", and "Berlin, Berlin, Deutschland" all become "berlin",
    while "Berlin" and "Munich" stay distinct.
    """
    head = location.split(",")[0]
    words = [w for w in normalize_text(head).split() if w not in _LOCATION_NOISE]
    return " ".join(words)


def identity_key(title: str, company: str, location: str) -> tuple[str, str, str]:
    """The normalized triple that identifies one posting."""
    return (normalize_text(title), normalize_text(company), normalize_location(location))


def _slugify(*parts: str) -> str:
    """Build a filesystem-safe, readable slug from *parts*."""
    joined = " ".join(part for part in parts if part)
    folded = joined.lower().translate(_TRANSLITERATIONS)
    ascii_only = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if len(slug) > _MAX_SLUG_LENGTH:
        # Cut at a word boundary so the slug does not end mid-word.
        slug = slug[:_MAX_SLUG_LENGTH].rsplit("-", 1)[0]
    return slug or "job"


def job_id(title: str, company: str, location: str) -> str:
    """A stable, readable id for one posting.

    Same posting, same id — across runs, and across the sources that found it.
    The digest is taken from the normalized identity rather than the slug, so two
    postings whose slugs collide after truncation still get different ids.
    """
    key = identity_key(title, company, location)
    digest = hashlib.sha256("\x1f".join(key).encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    return f"{_slugify(*key)}-{digest}"
