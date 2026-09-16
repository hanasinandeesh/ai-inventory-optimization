"""
Local smoke-test script for Gemini AI adapter integration.
Runs ONLY when explicitly executed via CLI (`python scripts/smoke_test_gemini.py`).
Is NOT executed as part of normal pytest suite.
"""

import sys

from app.core.config import settings
from app.domain.transfer import PreValidatedCandidate
from app.infrastructure.ai.gemini_provider import (
    GeminiProviderError,
    GeminiRecommendationProvider,
)
from app.services.dtos import AIRecommendationInputDTO


def run_smoke_test() -> None:
    print("--- Starting Gemini AI Adapter Smoke Test ---")

    api_key = settings.GEMINI_API_KEY
    if not api_key or not api_key.strip():
        print("[SKIP] GEMINI_API_KEY environment variable is not configured.")
        print("To run this smoke test, set GEMINI_API_KEY in your .env file.")
        sys.exit(0)

    print(f"Configured Model: {settings.GEMINI_MODEL}")
    print(f"Configured Timeout: {settings.GEMINI_TIMEOUT_SECONDS} seconds")

    provider = GeminiRecommendationProvider(
        api_key=api_key,
        model_name=settings.GEMINI_MODEL,
        timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
    )

    candidate_ind = PreValidatedCandidate(
        candidate_id="CAND-DC-IND-DC-CHI",
        source_dc_code="DC-IND",
        available_surplus=450,
        feasible_quantity=180,
        transit_days=1,
        route_unit_cost=2.50,
        estimated_total_cost=450.00,
        can_arrive_before_stockout=True,
    )

    sample_input = AIRecommendationInputDTO(
        incident_code="INC-DC-CHI-SKU-8842-20260916",
        target_dc_code="DC-CHI",
        product_sku="SKU-8842",
        product_name="Salmon Fillets",
        category="Seafood",
        days_to_stockout=2.5,
        shortage_qty=180,
        severity="CRITICAL",
        prevalidated_candidates=[candidate_ind],
    )

    try:
        output = provider.generate_recommendation(sample_input)
        print("\n[SUCCESS] Received valid AIRecommendationOutputDTO from Gemini API:")
        print(f"  Selected Candidate ID: {output.selected_candidate_id}")
        print(f"  Rationale Preview:     {output.rationale[:120]}...")
        assert output.selected_candidate_id == "CAND-DC-IND-DC-CHI"
        assert len(output.rationale.strip()) > 0
        print("\nSmoke Test PASSED!")
    except GeminiProviderError as exc:
        print(f"\n[FAILURE] Gemini Provider Error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[FAILURE] Unexpected Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_test()
