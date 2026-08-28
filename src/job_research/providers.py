"""Where the LLM backend's web searches actually go.

`LLMScraper` needs two things from an LLM, and neither is "generate text":

1. **A web search restricted to a set of domains.** Every source in the catalog
   is a domain, and a search that wanders off it returns listings the scraper
   then has to throw away.
2. **The URLs that search actually returned.** The scraper validates every
   extracted `job_url` against them — that check is the only thing standing
   between the report and a plausible-looking fabricated link. A provider that
   cannot report its own search results is therefore unusable here, which is
   why `SearchResponse` carries `result_urls` rather than just text.

Both providers below satisfy that contract through different mechanisms:
Anthropic's server-side `web_search` tool (`allowed_domains`, results returned
as `web_search_tool_result` blocks) and OpenRouter's `web` plugin
(`include_domains`, results returned as `url_citation` annotations).

The scraper's prompt, JSON parsing, and URL validation are provider-agnostic
and live in `scraper.py`; everything vendor-shaped lives here.
"""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import anthropic
import requests

logger = logging.getLogger(__name__)

Turn = Mapping[str, str]
"""One conversation turn: `{"role": "user" | "assistant", "content": ...}`."""

_MIN_SECONDS_BETWEEN_CALLS = 2.0
_MAX_ATTEMPTS = 3
_DEFAULT_RETRY_AFTER = 60


class ProviderError(RuntimeError):
    """A provider could not complete a request, after exhausting its retries."""


@dataclass(frozen=True)
class SearchResponse:
    """What one web-search call produced."""

    text: str
    """The model's own output, which the scraper parses as a JSON array."""
    result_urls: set[str] = field(default_factory=set)
    """Ground-truth URLs the search engine returned. Empty means "unknown",
    not "none found" — the scraper skips URL validation rather than
    discarding every listing when a provider reports no citations."""


class SearchProvider(Protocol):
    """What the LLM backend needs from an LLM vendor."""

    name: str
    """Shown in logs and in the UI's per-source health line."""

    model: str

    def search(
        self,
        *,
        system: str,
        messages: Sequence[Turn],
        allowed_domains: Sequence[str],
        max_searches: int,
    ) -> SearchResponse: ...

    def complete(self, *, system: str, messages: Sequence[Turn]) -> str:
        """A plain completion with no web search, for re-asking for clean JSON."""
        ...


def _retry_after(headers: Mapping[str, Any], default: int = _DEFAULT_RETRY_AFTER) -> int:
    """Seconds to wait per a `retry-after` header, falling back to *default*."""
    raw = headers.get("retry-after")
    if raw:
        try:
            return max(int(float(raw)), 1)
        except (ValueError, TypeError):
            pass
    return default


class _Throttle:
    """Spaces calls out, so a burst of sources does not trip a rate limit.

    Per instance rather than per process: two providers are two sets of
    credentials against two APIs, and making one wait for the other buys
    nothing.
    """

    def __init__(self, min_interval: float = _MIN_SECONDS_BETWEEN_CALLS) -> None:
        self._min_interval = min_interval
        self._last_call: float = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()


class AnthropicProvider:
    """The Claude API's server-side `web_search` tool, called directly.

    Retries are handled here rather than by the SDK (`max_retries=0`) so a 429
    honours the `retry-after` header the API sends, instead of the SDK's own
    backoff schedule.
    """

    name = "anthropic"

    # The tool version is tied to the model: the `_20260209` variant with
    # dynamic filtering needs Opus 4.6 / Sonnet 4.6 or newer, while this
    # project's default model is Haiku 4.5, which only offers the basic one.
    # Bump both together or not at all.
    _TOOL_TYPE = "web_search_20250305"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        self.model = model
        self._throttle = _Throttle()

    def search(
        self,
        *,
        system: str,
        messages: Sequence[Turn],
        allowed_domains: Sequence[str],
        max_searches: int,
    ) -> SearchResponse:
        tools = [
            {
                "type": self._TOOL_TYPE,
                "name": "web_search",
                "max_uses": max_searches,
                "allowed_domains": list(allowed_domains),
                "user_location": {"type": "approximate", "country": "DE"},
            }
        ]
        response = self._call(messages, system=system, tools=tools)
        return SearchResponse(
            text=self._text_of(response),
            result_urls=self._result_urls_of(response),
        )

    def complete(self, *, system: str, messages: Sequence[Turn]) -> str:
        return self._text_of(self._call(messages, system=system))

    # ----------------------------------------------------------------- private

    def _call(
        self,
        messages: Sequence[Turn],
        *,
        system: str,
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        self._throttle.wait()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": list(messages),
            "system": system,
        }
        if tools:
            kwargs["tools"] = tools

        for attempt in range(_MAX_ATTEMPTS):
            try:
                response: anthropic.types.Message = self._client.messages.create(**kwargs)
                return response
            except anthropic.RateLimitError as exc:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
                wait = _retry_after(exc.response.headers)
                logger.warning(
                    "Anthropic rate limited (attempt %d) — retrying in %ds", attempt + 1, wait
                )
                time.sleep(wait)
            except anthropic.APIStatusError as exc:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
                wait = 2**attempt
                logger.warning(
                    "Anthropic error (attempt %d): %s — retrying in %ds", attempt + 1, exc, wait
                )
                time.sleep(wait)
        raise ProviderError("unreachable")

    @staticmethod
    def _text_of(response: anthropic.types.Message) -> str:
        return "\n\n".join(block.text for block in response.content if block.type == "text")

    @staticmethod
    def _result_urls_of(response: anthropic.types.Message) -> set[str]:
        """Pull ground-truth URLs out of `web_search_tool_result` blocks.

        A failed search returns the same block type with an error *object*
        rather than a list of results, so this walks defensively instead of
        indexing.
        """
        urls: set[str] = set()
        for block in response.content:
            if getattr(block, "type", None) != "web_search_tool_result":
                continue
            content = getattr(block, "content", None)
            if not isinstance(content, list):
                logger.warning("Web search returned an error block: %.200s", content)
                continue
            for result in content:
                if getattr(result, "type", None) == "web_search_result":
                    url = getattr(result, "url", None)
                    if url:
                        urls.add(url)
        return urls


class OpenRouterProvider:
    """OpenRouter's `web` plugin, over the OpenAI-compatible chat endpoint.

    One model string reaches every vendor OpenRouter fronts, so the useful
    knob here is `model` rather than the code. Two OpenRouter specifics are
    worth knowing before changing anything:

    * **`max_results` is not `max_uses`.** Anthropic caps how many *searches*
      the model may run; OpenRouter caps how many *results* come back. They
      are not convertible, so they are configured separately.
    * **Domain filtering depends on the engine.** `include_domains` is honoured
      by the Exa engine and by Anthropic's and OpenAI's native search, but
      Google's native search ignores it. With a Gemini model, pin
      `engine="exa"` or accept that searches will wander off-domain — the
      scraper will then discard most of what comes back as unvalidated.
    """

    name = "openrouter"

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        max_results: int = 10,
        engine: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._max_results = max_results
        self._engine = engine
        self._timeout = timeout
        self._throttle = _Throttle()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # Identifies the caller on openrouter.ai. Optional, and carries
                # no credentials — it only attributes usage to this tool.
                "HTTP-Referer": "https://github.com/Cherubeam/job-research",
                "X-Title": "job-research",
            }
        )

    def search(
        self,
        *,
        system: str,
        messages: Sequence[Turn],
        allowed_domains: Sequence[str],
        max_searches: int,
    ) -> SearchResponse:
        plugin: dict[str, Any] = {
            "id": "web",
            "max_results": self._max_results,
            "include_domains": list(allowed_domains),
        }
        if self._engine:
            plugin["engine"] = self._engine

        payload = self._payload(system, messages)
        payload["plugins"] = [plugin]
        message = self._call(payload)
        return SearchResponse(
            text=self._text_of(message),
            result_urls=self._result_urls_of(message),
        )

    def complete(self, *, system: str, messages: Sequence[Turn]) -> str:
        return self._text_of(self._call(self._payload(system, messages)))

    # ----------------------------------------------------------------- private

    def _payload(
        self, system: str, messages: Sequence[Turn], max_tokens: int = 4096
    ) -> dict[str, Any]:
        """Build the request body. OpenRouter takes the system prompt as the
        first message rather than a separate field."""
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST *payload*, retrying rate limits and server errors.

        Returns the assistant message object, which carries both the text and
        the `annotations` the citation URLs come from.
        """
        self._throttle.wait()
        for attempt in range(_MAX_ATTEMPTS):
            last = attempt == _MAX_ATTEMPTS - 1
            try:
                response = self._session.post(self.BASE_URL, json=payload, timeout=self._timeout)
            except requests.RequestException as exc:
                if last:
                    raise ProviderError(f"OpenRouter request failed: {exc}") from exc
                wait = 2**attempt
                logger.warning(
                    "OpenRouter connection error (attempt %d): %s — retrying in %ds",
                    attempt + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if last:
                    raise ProviderError(
                        f"OpenRouter returned {response.status_code}: {response.text[:200]}"
                    )
                wait = _retry_after(response.headers) if response.status_code == 429 else 2**attempt
                logger.warning(
                    "OpenRouter %d (attempt %d) — retrying in %ds",
                    response.status_code,
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
                continue

            if not response.ok:
                raise ProviderError(
                    f"OpenRouter returned {response.status_code}: {response.text[:200]}"
                )
            return self._message_of(response.json())

        raise ProviderError("unreachable")

    @staticmethod
    def _message_of(body: dict[str, Any]) -> dict[str, Any]:
        """Extract the assistant message, turning OpenRouter's 200-with-error
        responses into exceptions rather than empty results."""
        if isinstance(body.get("error"), dict):
            error = body["error"]
            raise ProviderError(
                f"OpenRouter error {error.get('code', '?')}: {error.get('message', body)}"
            )
        choices = body.get("choices") or []
        if not choices:
            raise ProviderError(f"OpenRouter returned no choices: {str(body)[:200]}")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderError(f"OpenRouter returned no message: {str(body)[:200]}")
        return message

    @staticmethod
    def _text_of(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        # Some models answer with the multi-part content form.
        if isinstance(content, list):
            return "\n\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return ""

    @staticmethod
    def _result_urls_of(message: dict[str, Any]) -> set[str]:
        """Pull ground-truth URLs out of `url_citation` annotations."""
        urls: set[str] = set()
        for annotation in message.get("annotations") or []:
            if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                continue
            citation = annotation.get("url_citation")
            if isinstance(citation, dict) and citation.get("url"):
                urls.add(citation["url"])
        return urls
