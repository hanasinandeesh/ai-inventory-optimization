"""
Unit tests for GeminiRecommendationProvider infrastructure adapter.
Verifies response parsing, structured output extraction, prompt construction,
error handling, timeout enforcement, API key configuration, and architectural isolation.
All tests use MOCKED Gemini clients — ZERO external network or real API calls.
"""

import time
from dataclasses import dataclass
from typing import Any

import pytest

from app.domain.transfer import PreValidatedCandidate
from app.infrastructure.ai.gemini_provider import (
    GeminiProviderError,
    GeminiRecommendationProvider,
)
from app.infrastructure.ai.prompts.recommendation import build_recommendation_prompt
from app.services.dtos import AIRecommendationInputDTO

# --- Mock Objects for Testing ---


@dataclass
class MockGeminiResponse:
    text: str | None = None
    parsed: Any | None = None


class MockGeminiClient:
    def __init__(self, response_text: str | None = None, delay_seconds: float = 0.0) -> None:
        self.response_text = response_text
        self.delay_seconds = delay_seconds
        self.captured_contents: str | None = None

    def generate_content(self, model: str, contents: str, config: Any = None) -> MockGeminiResponse:
        self.captured_contents = contents
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
        return MockGeminiResponse(text=self.response_text)


def create_sample_ai_input() -> AIRecommendationInputDTO:
    candidate = PreValidatedCandidate(
        candidate_id="CAND-DC-IND-DC-CHI",
        source_dc_code="DC-IND",
        available_surplus=450,
        feasible_quantity=180,
        transit_days=1,
        route_unit_cost=2.50,
        estimated_total_cost=450.00,
        can_arrive_before_stockout=True,
    )
    return AIRecommendationInputDTO(
        incident_code="INC-DC-CHI-SKU-8842-20260916",
        target_dc_code="DC-CHI",
        product_sku="SKU-8842",
        product_name="Salmon Fillets",
        category="Seafood",
        days_to_stockout=2.5,
        shortage_qty=180,
        severity="CRITICAL",
        prevalidated_candidates=[candidate],
    )


# --- 10 Minimum Required Tests ---


def test_gemini_provider_success() -> None:
    """1. Verify successful response parsing returns valid AIRecommendationOutputDTO."""
    mock_json = (
        '{"selected_candidate_id": "CAND-DC-IND-DC-CHI", '
        '"rationale": "Indianapolis selected due to optimal transit lead time."}'
    )
    mock_client = MockGeminiClient(response_text=mock_json)
    provider = GeminiRecommendationProvider(api_key="fake-test-key", client=mock_client)

    result = provider.generate_recommendation(create_sample_ai_input())

    assert result.selected_candidate_id == "CAND-DC-IND-DC-CHI"
    assert result.rationale == "Indianapolis selected due to optimal transit lead time."


def test_gemini_provider_malformed_response() -> None:
    """2. Verify unparseable non-JSON output raises GeminiProviderError."""
    mock_client = MockGeminiClient(response_text="INVALID_NON_JSON_RESPONSE")
    provider = GeminiRecommendationProvider(api_key="fake-test-key", client=mock_client)

    with pytest.raises(GeminiProviderError) as exc_info:
        provider.generate_recommendation(create_sample_ai_input())

    assert "Failed to parse Gemini JSON output" in str(exc_info.value)


def test_gemini_provider_missing_candidate_id() -> None:
    """3. Verify missing selected_candidate_id field raises GeminiProviderError."""
    mock_json = '{"rationale": "Selected Indianapolis DC"}'
    mock_client = MockGeminiClient(response_text=mock_json)
    provider = GeminiRecommendationProvider(api_key="fake-test-key", client=mock_client)

    with pytest.raises(GeminiProviderError) as exc_info:
        provider.generate_recommendation(create_sample_ai_input())

    assert "missing required 'selected_candidate_id'" in str(exc_info.value)


def test_gemini_provider_missing_rationale() -> None:
    """4. Verify missing rationale field raises GeminiProviderError."""
    mock_json = '{"selected_candidate_id": "CAND-DC-IND-DC-CHI"}'
    mock_client = MockGeminiClient(response_text=mock_json)
    provider = GeminiRecommendationProvider(api_key="fake-test-key", client=mock_client)

    with pytest.raises(GeminiProviderError) as exc_info:
        provider.generate_recommendation(create_sample_ai_input())

    assert "missing required 'rationale'" in str(exc_info.value)


def test_gemini_provider_timeout() -> None:
    """5. Verify provider call exceeding timeout_seconds raises GeminiProviderError."""
    mock_client = MockGeminiClient(
        response_text='{"selected_candidate_id": "CAND-DC-IND-DC-CHI", "rationale": "ok"}',
        delay_seconds=0.3,
    )
    provider = GeminiRecommendationProvider(
        api_key="fake-test-key", timeout_seconds=0.05, client=mock_client
    )

    with pytest.raises(GeminiProviderError) as exc_info:
        provider.generate_recommendation(create_sample_ai_input())

    assert "timed out after 0.05 seconds" in str(exc_info.value)


def test_gemini_provider_api_failure() -> None:
    """6. Verify underlying API exception is wrapped in GeminiProviderError."""

    def failing_client(prompt: str):
        raise RuntimeError("Gemini API connection error 503")

    provider = GeminiRecommendationProvider(api_key="fake-test-key", client=failing_client)

    with pytest.raises(GeminiProviderError) as exc_info:
        provider.generate_recommendation(create_sample_ai_input())

    assert "Gemini API call failure" in str(exc_info.value)


def test_gemini_provider_api_key_configuration() -> None:
    """7. Verify missing API key raises GeminiProviderError prior to client call."""
    provider = GeminiRecommendationProvider(api_key="")

    with pytest.raises(GeminiProviderError) as exc_info:
        provider.generate_recommendation(create_sample_ai_input())

    assert "Gemini API key is not configured" in str(exc_info.value)


def test_gemini_prompt_contains_business_context() -> None:
    """8. Verify prompt construction embeds all required business context and candidates."""
    input_data = create_sample_ai_input()
    prompt = build_recommendation_prompt(input_data)

    assert "INC-DC-CHI-SKU-8842-20260916" in prompt
    assert "DC-CHI" in prompt
    assert "SKU-8842" in prompt
    assert "Salmon Fillets" in prompt
    assert "Seafood" in prompt
    assert "CRITICAL" in prompt
    assert "2.5 days" in prompt
    assert "180 units" in prompt
    assert "CAND-DC-IND-DC-CHI" in prompt
    assert "DC-IND" in prompt


def test_gemini_prompt_restricts_ai_authority() -> None:
    """9. Verify prompt contains explicit restrictive guardrails limiting AI authority."""
    prompt = build_recommendation_prompt(create_sample_ai_input())

    assert "Select exactly ONE candidate_id from the supplied candidate list" in prompt
    assert "Do NOT invent, assume, or select any candidate_id not listed" in prompt
    assert "Do NOT modify transfer quantity, available surplus, transit days, or cost" in prompt
    assert "Do NOT calculate or modify cost or transfer quantity" in prompt


def test_gemini_provider_no_database_dependency() -> None:
    """10. Verify app.infrastructure.ai has ZERO database or ORM dependencies."""
    import inspect

    import app.infrastructure.ai.gemini_provider as provider_module
    import app.infrastructure.ai.prompts.recommendation as prompt_module

    for mod in (provider_module, prompt_module):
        source = inspect.getsource(mod)
        assert "sqlalchemy" not in source.lower()
        assert "from app.infrastructure.db" not in source
        assert "repository" not in source.lower()
        assert "session" not in source.lower()
