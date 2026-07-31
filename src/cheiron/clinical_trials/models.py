"""Typed upstream response fragments and normalized clinical-trial records."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from cheiron.domain.response import EvidenceValue


class DatasetVersion(BaseModel):
    """Version metadata returned by ``GET /version``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    api_version: str = Field(validation_alias=AliasChoices("apiVersion", "api_version"))
    data_timestamp: datetime = Field(
        validation_alias=AliasChoices("dataTimestamp", "data_timestamp")
    )


class StudyPage(BaseModel):
    """Minimal page envelope returned by ``GET /studies``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    studies: list[dict[str, Any]] = Field(default_factory=list)
    next_page_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("nextPageToken", "next_page_token"),
    )
    total_count: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("totalCount", "total_count"),
    )


@dataclass(frozen=True, slots=True)
class CohortRetrieval:
    """Complete raw records retrieved for one named analysis cohort."""

    cohort_id: str
    studies: tuple[dict[str, Any], ...]
    matched_count: int
    pages_retrieved: int
    retrieved_at: datetime
    query_params: dict[str, str]


class DatePrecision(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


@dataclass(frozen=True, slots=True)
class PartialDate:
    """ClinicalTrials.gov date with its original precision preserved."""

    original: str
    year: int
    month: int | None
    day: int | None
    precision: DatePrecision
    date_type: str | None = None


@dataclass(frozen=True, slots=True)
class Intervention:
    name: str
    type: str | None


@dataclass(frozen=True, slots=True)
class TrialRecord:
    """Purpose-built, immutable subset of a ClinicalTrials.gov study record."""

    nct_id: str
    brief_title: str | None
    overall_status: str | None
    start_date: PartialDate | None
    phases: tuple[str, ...]
    study_type: str | None
    enrollment_count: int | None
    enrollment_type: str | None
    lead_sponsor_name: str | None
    lead_sponsor_class: str | None
    conditions: tuple[str, ...]
    interventions: tuple[Intervention, ...]
    countries: tuple[str, ...]
    source_values: dict[str, EvidenceValue] = field(default_factory=dict, compare=False)


@dataclass(frozen=True, slots=True)
class NormalizationWarning:
    nct_id: str | None
    field_path: str
    message: str


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    records: tuple[TrialRecord, ...]
    excluded_count: int
    warnings: tuple[NormalizationWarning, ...]
