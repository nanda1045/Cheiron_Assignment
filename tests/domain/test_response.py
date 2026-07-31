"""Validation tests for normalized source provenance."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cheiron.domain.response import Citation, Evidence, Provenance, SourceMetadata


def source_metadata() -> SourceMetadata:
    now = datetime.now(UTC)
    return SourceMetadata(
        api_version="2.0.5",
        data_timestamp=now,
        retrieved_at=now,
        endpoint="https://clinicaltrials.gov/api/v2/studies",
    )


def test_provenance_requires_dictionary_key_to_match_citation_id() -> None:
    citation = Citation(
        id="cit-nct01234567-phase",
        nct_id="NCT01234567",
        study_url="https://clinicaltrials.gov/study/NCT01234567",
        evidence=[Evidence(field_path="protocolSection.designModule.phases", value=["PHASE3"])],
    )

    with pytest.raises(ValidationError, match="keys must match"):
        Provenance(source=source_metadata(), citations={"wrong-key": citation})


def test_provenance_serializes_urls_as_json_strings() -> None:
    provenance = Provenance(source=source_metadata())

    payload = provenance.model_dump(mode="json")

    assert payload["source"]["endpoint"] == "https://clinicaltrials.gov/api/v2/studies"
