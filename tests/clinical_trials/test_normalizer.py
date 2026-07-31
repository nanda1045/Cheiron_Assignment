"""Tests for loss-aware ClinicalTrials.gov study normalization."""

from typing import Any

from cheiron.clinical_trials.models import DatePrecision
from cheiron.clinical_trials.normalizer import (
    LOCATIONS_PATH,
    PHASES_PATH,
    TrialNormalizer,
)


def test_normalizer_preserves_partial_dates_and_deduplicates_entities(
    first_page: dict[str, Any],
) -> None:
    study = first_page["studies"][0]

    record = TrialNormalizer().normalize(study)

    assert record.nct_id == "NCT00000001"
    assert record.start_date is not None
    assert record.start_date.precision is DatePrecision.MONTH
    assert record.start_date.original == "2021-04"
    assert record.countries == ("Canada", "United States")
    assert len(record.interventions) == 1
    assert record.source_values[PHASES_PATH] == ["PHASE3"]
    assert record.source_values[f"{LOCATIONS_PATH}.country"] == [
        "Canada",
        "United States",
    ]


def test_normalizer_accepts_missing_optional_modules() -> None:
    record = TrialNormalizer().normalize(
        {"protocolSection": {"identificationModule": {"nctId": "NCT99999999"}}}
    )

    assert record.start_date is None
    assert record.conditions == ()
    assert record.countries == ()


def test_normalize_many_excludes_invalid_and_duplicate_records(
    first_page: dict[str, Any],
) -> None:
    study = first_page["studies"][0]
    result = TrialNormalizer().normalize_many([study, study, {"protocolSection": {}}])

    assert len(result.records) == 1
    assert result.excluded_count == 2
    assert len(result.warnings) == 2
