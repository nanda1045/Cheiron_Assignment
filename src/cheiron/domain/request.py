"""Public request schema for natural-language visualization queries."""

from typing import Literal

from pydantic import Field, model_validator

from cheiron.domain.base import DomainModel
from cheiron.domain.enums import (
    RecruitmentStatus,
    SponsorClass,
    StudyType,
    TrialPhase,
    VisualizationType,
)


class QueryFilters(DomainModel):
    """Optional structured constraints that take precedence over parsed query values."""

    conditions: list[str] = Field(default_factory=list, max_length=10)
    interventions: list[str] = Field(default_factory=list, max_length=10)
    phases: list[TrialPhase] = Field(default_factory=list, max_length=6)
    statuses: list[RecruitmentStatus] = Field(default_factory=list, max_length=10)
    sponsors: list[str] = Field(default_factory=list, max_length=10)
    sponsor_classes: list[SponsorClass] = Field(default_factory=list, max_length=8)
    countries: list[str] = Field(default_factory=list, max_length=20)
    study_types: list[StudyType] = Field(default_factory=list, max_length=3)
    start_year_from: int | None = Field(default=None, ge=1900, le=2100)
    start_year_to: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def validate_year_range(self) -> "QueryFilters":
        if (
            self.start_year_from is not None
            and self.start_year_to is not None
            and self.start_year_from > self.start_year_to
        ):
            raise ValueError("start_year_from must be less than or equal to start_year_to")
        return self


class QueryOptions(DomainModel):
    """Optional controls that do not alter the semantic population definition."""

    include_citations: bool = True
    preferred_visualization: VisualizationType | None = None
    max_studies: int | None = Field(default=None, ge=1, le=100_000)


class QueryRequest(DomainModel):
    """Versioned public request accepted by the query endpoint."""

    schema_version: Literal["1.0"] = "1.0"
    query: str = Field(min_length=3, max_length=2_000)
    filters: QueryFilters = Field(default_factory=QueryFilters)
    options: QueryOptions = Field(default_factory=QueryOptions)
