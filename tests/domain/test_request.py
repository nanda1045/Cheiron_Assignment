"""Validation tests for public query requests."""

import pytest
from pydantic import ValidationError

from cheiron.domain.request import QueryRequest


def test_request_defaults_are_frontend_friendly() -> None:
    request = QueryRequest(query="  Trials by phase for melanoma  ")

    assert request.query == "Trials by phase for melanoma"
    assert request.filters.conditions == []
    assert request.options.include_citations is True


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        QueryRequest.model_validate({"query": "Trials by phase", "drug_name": "Aspirin"})


def test_request_rejects_reversed_year_range() -> None:
    with pytest.raises(ValidationError, match="start_year_from"):
        QueryRequest.model_validate(
            {
                "query": "Trials over time",
                "filters": {"start_year_from": 2025, "start_year_to": 2020},
            }
        )
