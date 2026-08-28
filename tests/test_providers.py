"""Tests for providers.py — the vendor-shaped half of the LLM backend.

Two things matter here and are worth stating plainly, because the scraper
depends on both and neither is obvious from the call site:

* **Domain restriction reaches the vendor.** Each provider spells it
  differently (`allowed_domains` vs `include_domains`); a silent drop would
  send unrestricted searches and quietly bill for results the scraper throws
  away.
* **Citation URLs come back.** They are the scraper's only defence against
  fabricated job links, and each vendor buries them somewhere different.
"""

from unittest.mock import MagicMock, patch

import anthropic
import pytest
import requests

from job_research.providers import (
    AnthropicProvider,
    OpenRouterProvider,
    ProviderError,
    SearchResponse,
)


# ------------------------------------------------------------------- fixtures


def _anthropic_response(text: str = "[]", search_urls: list[str] | None = None) -> MagicMock:
    """A Messages API response with a text block and optional search results."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    blocks = [text_block]

    if search_urls is not None:
        results = []
        for url in search_urls:
            result = MagicMock()
            result.type = "web_search_result"
            result.url = url
            results.append(result)
        search_block = MagicMock()
        search_block.type = "web_search_tool_result"
        search_block.content = results
        blocks.insert(0, search_block)

    response = MagicMock()
    response.content = blocks
    return response


@pytest.fixture
def anthropic_provider() -> AnthropicProvider:
    with patch("job_research.providers.anthropic.Anthropic"):
        return AnthropicProvider(api_key="sk-test", model="claude-haiku-4-5-20251001")


@pytest.fixture
def openrouter_provider() -> OpenRouterProvider:
    provider = OpenRouterProvider(api_key="sk-or-test", model="anthropic/claude-haiku-4.5")
    provider._session = MagicMock()
    return provider


def _openrouter_response(
    status: int = 200, body: dict | None = None, headers: dict | None = None
) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.ok = 200 <= status < 300
    response.headers = headers or {}
    response.text = str(body)
    response.json.return_value = body or {}
    return response


def _openrouter_message(text: str = "[]", urls: list[str] | None = None) -> dict:
    message: dict = {"role": "assistant", "content": text}
    if urls is not None:
        message["annotations"] = [
            {"type": "url_citation", "url_citation": {"url": url, "title": "t"}} for url in urls
        ]
    return {"choices": [{"message": message}]}


# ------------------------------------------------------------------ Anthropic


class TestAnthropicProvider:
    def test_client_created_with_max_retries_zero(self):
        """SDK retries are off so this module can honour the retry-after header itself."""
        with patch("job_research.providers.anthropic.Anthropic") as mock_anthropic:
            AnthropicProvider(api_key="sk-test", model="claude-haiku-4-5-20251001")
        mock_anthropic.assert_called_once_with(api_key="sk-test", max_retries=0)

    def test_search_restricts_the_tool_to_the_given_domains(self, anthropic_provider):
        anthropic_provider._client.messages.create.return_value = _anthropic_response()

        anthropic_provider.search(
            system="sys",
            messages=[{"role": "user", "content": "find jobs"}],
            allowed_domains=["stepstone.de", "monster.de"],
            max_searches=7,
        )

        tool = anthropic_provider._client.messages.create.call_args.kwargs["tools"][0]
        assert tool["allowed_domains"] == ["stepstone.de", "monster.de"]
        assert tool["max_uses"] == 7

    def test_complete_sends_no_tools(self, anthropic_provider):
        """The JSON re-ask must not run (and bill for) another round of searches."""
        anthropic_provider._client.messages.create.return_value = _anthropic_response("[]")

        anthropic_provider.complete(system="sys", messages=[{"role": "user", "content": "hi"}])

        assert "tools" not in anthropic_provider._client.messages.create.call_args.kwargs

    def test_search_returns_text_and_citation_urls(self, anthropic_provider):
        anthropic_provider._client.messages.create.return_value = _anthropic_response(
            "[]", ["https://de.indeed.com/viewjob?jk=abc", "https://de.indeed.com/viewjob?jk=def"]
        )

        result = anthropic_provider.search(
            system="sys", messages=[], allowed_domains=["de.indeed.com"], max_searches=3
        )

        assert isinstance(result, SearchResponse)
        assert result.text == "[]"
        assert result.result_urls == {
            "https://de.indeed.com/viewjob?jk=abc",
            "https://de.indeed.com/viewjob?jk=def",
        }

    def test_no_search_blocks_yields_no_urls(self, anthropic_provider):
        anthropic_provider._client.messages.create.return_value = _anthropic_response("[]")
        result = anthropic_provider.search(
            system="sys", messages=[], allowed_domains=[], max_searches=1
        )
        assert result.result_urls == set()

    def test_a_failed_search_block_does_not_crash(self, anthropic_provider):
        """A web search error arrives as HTTP 200 with an error *object* where the
        result list would be — indexing it would raise instead of degrading."""
        error_block = MagicMock()
        error_block.type = "web_search_tool_result"
        error_block.content = {"error_code": "max_uses_exceeded"}
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "[]"
        response = MagicMock()
        response.content = [error_block, text_block]
        anthropic_provider._client.messages.create.return_value = response

        result = anthropic_provider.search(
            system="sys", messages=[], allowed_domains=[], max_searches=1
        )

        assert result.result_urls == set()

    def test_retries_on_server_error(self, anthropic_provider):
        """Non-429 APIStatusError uses short exponential backoff."""
        error = anthropic.APIStatusError(
            "server error", response=MagicMock(status_code=500), body={}
        )
        success = _anthropic_response()
        anthropic_provider._client.messages.create.side_effect = [error, success]

        with patch("job_research.providers.time.sleep") as mock_sleep:
            anthropic_provider.complete(system="sys", messages=[])

        assert anthropic_provider._client.messages.create.call_count == 2
        mock_sleep.assert_any_call(1)  # 2**0

    def test_rate_limit_uses_retry_after_header(self, anthropic_provider):
        response_mock = MagicMock(status_code=429)
        response_mock.headers = {"retry-after": "30"}
        error = anthropic.RateLimitError("rate limited", response=response_mock, body={})
        anthropic_provider._client.messages.create.side_effect = [error, _anthropic_response()]

        with patch("job_research.providers.time.sleep") as mock_sleep:
            anthropic_provider.complete(system="sys", messages=[])

        mock_sleep.assert_any_call(30)

    def test_rate_limit_defaults_to_60s(self, anthropic_provider):
        response_mock = MagicMock(status_code=429)
        response_mock.headers = {}
        error = anthropic.RateLimitError("rate limited", response=response_mock, body={})
        anthropic_provider._client.messages.create.side_effect = [error, _anthropic_response()]

        with patch("job_research.providers.time.sleep") as mock_sleep:
            anthropic_provider.complete(system="sys", messages=[])

        mock_sleep.assert_any_call(60)

    def test_gives_up_after_three_attempts(self, anthropic_provider):
        error = anthropic.APIStatusError("nope", response=MagicMock(status_code=503), body={})
        anthropic_provider._client.messages.create.side_effect = [error, error, error]

        with patch("job_research.providers.time.sleep"):
            with pytest.raises(anthropic.APIStatusError):
                anthropic_provider.complete(system="sys", messages=[])

        assert anthropic_provider._client.messages.create.call_count == 3


# ----------------------------------------------------------------- OpenRouter


class TestOpenRouterProvider:
    def test_authenticates_with_a_bearer_token(self):
        provider = OpenRouterProvider(api_key="sk-or-test", model="m")
        assert provider._session.headers["Authorization"] == "Bearer sk-or-test"

    def test_search_restricts_the_plugin_to_the_given_domains(self, openrouter_provider):
        openrouter_provider._session.post.return_value = _openrouter_response(
            body=_openrouter_message()
        )

        openrouter_provider.search(
            system="sys",
            messages=[{"role": "user", "content": "find jobs"}],
            allowed_domains=["stepstone.de", "monster.de"],
            max_searches=7,
        )

        payload = openrouter_provider._session.post.call_args.kwargs["json"]
        plugin = payload["plugins"][0]
        assert plugin["id"] == "web"
        assert plugin["include_domains"] == ["stepstone.de", "monster.de"]
        assert plugin["max_results"] == 10

    def test_engine_is_omitted_unless_pinned(self, openrouter_provider):
        openrouter_provider._session.post.return_value = _openrouter_response(
            body=_openrouter_message()
        )
        openrouter_provider.search(
            system="sys", messages=[], allowed_domains=["a.de"], max_searches=1
        )
        plugin = openrouter_provider._session.post.call_args.kwargs["json"]["plugins"][0]
        assert "engine" not in plugin

    def test_engine_is_sent_when_pinned(self):
        provider = OpenRouterProvider(api_key="k", model="m", engine="exa")
        provider._session = MagicMock()
        provider._session.post.return_value = _openrouter_response(body=_openrouter_message())

        provider.search(system="sys", messages=[], allowed_domains=["a.de"], max_searches=1)

        plugin = provider._session.post.call_args.kwargs["json"]["plugins"][0]
        assert plugin["engine"] == "exa"

    def test_system_prompt_is_sent_as_the_first_message(self, openrouter_provider):
        """OpenRouter has no separate system field — dropping it would unprompt the model."""
        openrouter_provider._session.post.return_value = _openrouter_response(
            body=_openrouter_message()
        )

        openrouter_provider.search(
            system="you are a job search assistant",
            messages=[{"role": "user", "content": "find jobs"}],
            allowed_domains=["a.de"],
            max_searches=1,
        )

        messages = openrouter_provider._session.post.call_args.kwargs["json"]["messages"]
        assert messages[0] == {"role": "system", "content": "you are a job search assistant"}
        assert messages[1] == {"role": "user", "content": "find jobs"}

    def test_complete_sends_no_web_plugin(self, openrouter_provider):
        """The JSON re-ask must not run (and bill for) another round of searches."""
        openrouter_provider._session.post.return_value = _openrouter_response(
            body=_openrouter_message()
        )

        openrouter_provider.complete(system="sys", messages=[])

        assert "plugins" not in openrouter_provider._session.post.call_args.kwargs["json"]

    def test_search_returns_text_and_citation_urls(self, openrouter_provider):
        openrouter_provider._session.post.return_value = _openrouter_response(
            body=_openrouter_message(
                "[]",
                [
                    "https://de.indeed.com/viewjob?jk=abc",
                    "https://de.indeed.com/viewjob?jk=def",
                ],
            )
        )

        result = openrouter_provider.search(
            system="sys", messages=[], allowed_domains=["de.indeed.com"], max_searches=1
        )

        assert result.text == "[]"
        assert result.result_urls == {
            "https://de.indeed.com/viewjob?jk=abc",
            "https://de.indeed.com/viewjob?jk=def",
        }

    def test_ignores_annotations_that_are_not_citations(self, openrouter_provider):
        body = _openrouter_message("[]")
        body["choices"][0]["message"]["annotations"] = [
            {"type": "file_citation", "file_citation": {"file_id": "f1"}},
            {"type": "url_citation", "url_citation": {"url": "https://example.com/1"}},
        ]
        openrouter_provider._session.post.return_value = _openrouter_response(body=body)

        result = openrouter_provider.search(
            system="sys", messages=[], allowed_domains=[], max_searches=1
        )

        assert result.result_urls == {"https://example.com/1"}

    def test_reads_multi_part_content(self, openrouter_provider):
        """Some models answer with the list form of `content` rather than a string."""
        body = _openrouter_message()
        body["choices"][0]["message"]["content"] = [
            {"type": "text", "text": "part one"},
            {"type": "text", "text": "part two"},
        ]
        openrouter_provider._session.post.return_value = _openrouter_response(body=body)

        result = openrouter_provider.search(
            system="sys", messages=[], allowed_domains=[], max_searches=1
        )

        assert result.text == "part one\n\npart two"

    def test_error_body_on_a_200_is_raised(self, openrouter_provider):
        """OpenRouter reports some failures as HTTP 200 with an error object; treating
        that as an empty answer would look like a job market with no openings."""
        openrouter_provider._session.post.return_value = _openrouter_response(
            body={"error": {"code": 402, "message": "insufficient credits"}}
        )

        with pytest.raises(ProviderError, match="insufficient credits"):
            openrouter_provider.search(
                system="sys", messages=[], allowed_domains=[], max_searches=1
            )

    def test_missing_choices_is_raised(self, openrouter_provider):
        openrouter_provider._session.post.return_value = _openrouter_response(body={"choices": []})
        with pytest.raises(ProviderError, match="no choices"):
            openrouter_provider.complete(system="sys", messages=[])

    def test_rate_limit_uses_retry_after_header(self, openrouter_provider):
        openrouter_provider._session.post.side_effect = [
            _openrouter_response(status=429, headers={"retry-after": "30"}),
            _openrouter_response(body=_openrouter_message()),
        ]

        with patch("job_research.providers.time.sleep") as mock_sleep:
            openrouter_provider.complete(system="sys", messages=[])

        mock_sleep.assert_any_call(30)
        assert openrouter_provider._session.post.call_count == 2

    def test_server_error_is_retried(self, openrouter_provider):
        openrouter_provider._session.post.side_effect = [
            _openrouter_response(status=500),
            _openrouter_response(body=_openrouter_message("[]")),
        ]

        with patch("job_research.providers.time.sleep"):
            assert openrouter_provider.complete(system="sys", messages=[]) == "[]"

        assert openrouter_provider._session.post.call_count == 2

    def test_client_error_is_not_retried(self, openrouter_provider):
        """A 400 will fail identically on the next attempt — retrying only wastes time."""
        openrouter_provider._session.post.return_value = _openrouter_response(
            status=400, body={"detail": "bad model"}
        )

        with patch("job_research.providers.time.sleep"):
            with pytest.raises(ProviderError, match="400"):
                openrouter_provider.complete(system="sys", messages=[])

        assert openrouter_provider._session.post.call_count == 1

    def test_connection_errors_are_retried_then_raised(self, openrouter_provider):
        openrouter_provider._session.post.side_effect = requests.ConnectionError("no route")

        with patch("job_research.providers.time.sleep"):
            with pytest.raises(ProviderError, match="request failed"):
                openrouter_provider.complete(system="sys", messages=[])

        assert openrouter_provider._session.post.call_count == 3
