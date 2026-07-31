"""Tests for exact post-retrieval cohort filtering."""

from cheiron.analysis.filtering import RecordFilter
from cheiron.clinical_trials.models import TrialRecord
from cheiron.domain.enums import FilterField, FilterOperator
from cheiron.domain.plan import FilterClause


def test_contains_matches_condition_substrings(normalized_trials: tuple[TrialRecord, ...]) -> None:
    clause = FilterClause(
        field=FilterField.CONDITION,
        operator=FilterOperator.CONTAINS,
        values=["skin cancer"],
    )

    matching = RecordFilter().filter(normalized_trials, [clause])

    assert [record.nct_id for record in matching] == ["NCT00000002"]


def test_numeric_year_filter_uses_preserved_partial_date(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    clause = FilterClause(
        field=FilterField.START_YEAR,
        operator=FilterOperator.GREATER_THAN_OR_EQUAL,
        values=[2020],
    )

    matching = RecordFilter().filter(normalized_trials, [clause])

    assert [record.nct_id for record in matching] == ["NCT00000001"]
