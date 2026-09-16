"""
Gemini infrastructure adapter for AI transfer recommendation provider interface.
Encapsulates Gemini SDK calls, prompt building, response parsing, and timeout execution.
Contains ZERO database, ORM, FastAPI, or domain layer dependencies.
"""

import concurrent.futures
import json
import logging
import time
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.infrastructure.ai.prompts.recommendation import build_recommendation_prompt
from app.services.dtos import AIRecommendationInputDTO, AIRecommendationOutputDTO
from app.services.exceptions import ApplicationServiceError

logger = logging.getLogger(__name__)


class GeminiProviderError(ApplicationServiceError):
    """Exception raised when the Gemini recommendation provider fails."""

    pass


class GeminiRecommendationProvider:
    """
    Infrastructure implementation of AIRecommendationProviderInterface using Gemini.
    Translates application DTOs into Gemini requests and parses structured output responses.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self._model_name = model_name if model_name is not None else settings.GEMINI_MODEL
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.GEMINI_TIMEOUT_SECONDS
        )
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self._api_key or not self._api_key.strip():
            raise GeminiProviderError(
                "Gemini API key is not configured. Set GEMINI_API_KEY environment variable."
            )

        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        """
        Generates a transfer recommendation decision using Gemini API.
        Executes bounded timeout and returns validated AIRecommendationOutputDTO.
        """

        prompt = build_recommendation_prompt(input_data)
        start_time = time.perf_counter()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._call_gemini_api, prompt)
                response = future.result(timeout=self._timeout_seconds)

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Gemini recommendation provider call succeeded",
                extra={
                    "provider": "gemini",
                    "model": self._model_name,
                    "operation": "recommendation",
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                },
            )
        except concurrent.futures.TimeoutError as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Gemini recommendation provider call timed out",
                extra={
                    "provider": "gemini",
                    "model": self._model_name,
                    "operation": "recommendation",
                    "latency_ms": round(latency_ms, 2),
                    "status": "timeout",
                },
            )
            raise GeminiProviderError(
                f"Gemini API request timed out after {self._timeout_seconds} seconds"
            ) from exc
        except GeminiProviderError:
            raise
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Gemini recommendation provider call failed",
                extra={
                    "provider": "gemini",
                    "model": self._model_name,
                    "operation": "recommendation",
                    "latency_ms": round(latency_ms, 2),
                    "status": "error",
                },
            )
            raise GeminiProviderError(f"Gemini API call failure: {exc}") from exc

        return self._parse_response(response)

    def _call_gemini_api(self, prompt: str) -> Any:
        client = self._get_client()

        # If client is a custom mock/fake passed in tests
        if hasattr(client, "generate_content"):
            config = types.GenerateContentConfig(response_mime_type="application/json")
            return client.generate_content(
                model=self._model_name,
                contents=prompt,
                config=config,
            )
        elif hasattr(client, "models") and hasattr(client.models, "generate_content"):
            config = types.GenerateContentConfig(response_mime_type="application/json")
            return client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=config,
            )
        elif callable(client):
            return client(prompt)
        else:
            raise GeminiProviderError("Invalid Gemini client instance provided")

    def _parse_response(self, response: Any) -> AIRecommendationOutputDTO:
        text_content: str | None = None
        data: dict[str, Any] | None = None

        if isinstance(response, str):
            text_content = response
        elif isinstance(response, dict):
            data = response
        elif hasattr(response, "parsed") and response.parsed is not None:
            parsed = response.parsed
            if isinstance(parsed, dict):
                data = parsed
            else:
                data = {
                    "selected_candidate_id": getattr(parsed, "selected_candidate_id", None),
                    "rationale": getattr(parsed, "rationale", None),
                }
        elif hasattr(response, "text") and response.text:
            text_content = response.text
        else:
            raise GeminiProviderError("Malformed or empty response payload from Gemini API")

        if data is None and text_content is not None:
            cleaned = text_content.strip()
            if cleaned.startswith("```"):
                parts = cleaned.split("```")
                if len(parts) >= 2:
                    cleaned = parts[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                cleaned = cleaned.strip()

            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise GeminiProviderError(f"Failed to parse Gemini JSON output: {exc}") from exc

        if not isinstance(data, dict):
            raise GeminiProviderError("Gemini API response is not a valid JSON object")

        selected_candidate_id = data.get("selected_candidate_id")
        rationale = data.get("rationale")

        if (
            not selected_candidate_id
            or not isinstance(selected_candidate_id, str)
            or not selected_candidate_id.strip()
        ):
            raise GeminiProviderError(
                "Gemini response payload missing required 'selected_candidate_id' string field"
            )

        if not rationale or not isinstance(rationale, str) or not rationale.strip():
            raise GeminiProviderError(
                "Gemini response payload missing required 'rationale' string field"
            )

        return AIRecommendationOutputDTO(
            selected_candidate_id=selected_candidate_id.strip(),
            rationale=rationale.strip(),
        )
