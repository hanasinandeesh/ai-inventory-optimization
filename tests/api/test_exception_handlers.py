"""
Unit and API tests for custom exception handlers.
Verifies error status codes, ErrorResponse schemas, error codes, and correlation ID preservation.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.exceptions import InvalidStateTransitionError


def test_invalid_state_transition_handler_mapping() -> None:
    """Verify InvalidStateTransitionError is mapped to HTTP 409
    with error_code INVALID_STATE_TRANSITION."""
    # Create a dummy endpoint on the app that raises InvalidStateTransitionError

    @app.get("/test-state-conflict")
    def dummy_state_conflict_endpoint():
        raise InvalidStateTransitionError(
            "TransferRecommendation '101' cannot be approved from status 'APPROVED'"
        )

    client = TestClient(app)
    response = client.get(
        "/test-state-conflict",
        headers={"X-Correlation-ID": "test-corr-id-12345"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "INVALID_STATE_TRANSITION"
    assert "cannot be approved" in payload["message"]
    assert payload["correlation_id"] == "test-corr-id-12345"
