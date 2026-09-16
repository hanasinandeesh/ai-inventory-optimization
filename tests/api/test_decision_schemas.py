"""
Unit tests for Planner Decision API Pydantic request/response schemas.
"""

import pytest
from pydantic import ValidationError

from app.schemas.decision import (
    ApproveRecommendationRequest,
    RejectRecommendationRequest,
)


def test_approve_recommendation_request_valid_no_comment() -> None:
    """Verify ApproveRecommendationRequest accepts valid planner_id without comment."""
    req = ApproveRecommendationRequest(planner_id="planner_john")
    assert req.planner_id == "planner_john"
    assert req.comment is None


def test_approve_recommendation_request_valid_with_comment() -> None:
    """Verify ApproveRecommendationRequest accepts valid planner_id with comment."""
    req = ApproveRecommendationRequest(
        planner_id="planner_john", comment="Approved for urgent replenishment"
    )
    assert req.planner_id == "planner_john"
    assert req.comment == "Approved for urgent replenishment"


def test_approve_recommendation_request_missing_planner_id() -> None:
    """Verify ApproveRecommendationRequest rejects missing planner_id."""
    with pytest.raises(ValidationError) as exc_info:
        ApproveRecommendationRequest()  # type: ignore[call-arg]
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("planner_id",) and err["type"] == "missing" for err in errors)


def test_reject_recommendation_request_valid() -> None:
    """Verify RejectRecommendationRequest accepts valid planner_id and rejection_reason."""
    req = RejectRecommendationRequest(
        planner_id="planner_john",
        rejection_reason="Alternative local inventory available",
    )
    assert req.planner_id == "planner_john"
    assert req.rejection_reason == "Alternative local inventory available"


def test_reject_recommendation_request_missing_planner_id() -> None:
    """Verify RejectRecommendationRequest rejects missing planner_id."""
    with pytest.raises(ValidationError) as exc_info:
        RejectRecommendationRequest(rejection_reason="Alternative local inventory available")  # type: ignore[call-arg]
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("planner_id",) and err["type"] == "missing" for err in errors)


def test_reject_recommendation_request_missing_rejection_reason() -> None:
    """Verify RejectRecommendationRequest rejects missing rejection_reason."""
    with pytest.raises(ValidationError) as exc_info:
        RejectRecommendationRequest(planner_id="planner_john")  # type: ignore[call-arg]
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("rejection_reason",) and err["type"] == "missing" for err in errors)
