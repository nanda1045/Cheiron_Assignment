"""Public response envelopes and normalized source provenance."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, HttpUrl, model_validator

from cheiron.domain.answer import ScalarAnswer, SemanticPlan
from cheiron.domain.base import DomainModel
from cheiron.domain.enums import CompletenessStatus, PlannerMode
from cheiron.domain.visualization import ScalarValue, VisualizationSpec

type EvidenceValue = ScalarValue | list[ScalarValue]


class Evidence(DomainModel):
    field_path: str = Field(min_length=1, max_length=300)
    value: EvidenceValue


class Citation(DomainModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^cit-[a-z0-9-]+$")
    nct_id: str = Field(pattern=r"^NCT\d{8}$")
    study_url: HttpUrl
    evidence: list[Evidence] = Field(min_length=1)


class SourceMetadata(DomainModel):
    name: Literal["ClinicalTrials.gov"] = "ClinicalTrials.gov"
    api_version: str = Field(min_length=1, max_length=40)
    data_timestamp: datetime
    retrieved_at: datetime
    endpoint: HttpUrl


class Provenance(DomainModel):
    source: SourceMetadata
    citations: dict[str, Citation] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_citation_keys(self) -> "Provenance":
        mismatched = [key for key, citation in self.citations.items() if key != citation.id]
        if mismatched:
            raise ValueError("citation dictionary keys must match citation ids")
        return self


class RecordCounts(DomainModel):
    matched: int = Field(ge=0)
    retrieved: int = Field(ge=0)
    used: int = Field(ge=0)
    excluded: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "RecordCounts":
        if self.used + self.excluded > self.retrieved:
            raise ValueError("used plus excluded cannot exceed retrieved")
        return self


class Completeness(DomainModel):
    status: CompletenessStatus
    is_complete: bool
    pages_retrieved: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_status(self) -> "Completeness":
        if self.is_complete != (self.status is CompletenessStatus.COMPLETE):
            raise ValueError("is_complete must agree with completeness status")
        return self


class PlannerMetadata(DomainModel):
    mode: PlannerMode
    model: str | None = Field(default=None, max_length=100)
    capability_limited: bool = False


class QuerySummary(DomainModel):
    original: str = Field(min_length=3, max_length=2_000)
    interpretation: str = Field(min_length=3, max_length=500)
    structured_filters_authoritative: bool = True
    warnings: list[str] = Field(default_factory=list)


class ResponseMetadata(DomainModel):
    planner: PlannerMetadata
    record_counts: RecordCounts
    completeness: Completeness
    duration_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class SuccessResponse(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    status: Literal["ok"] = "ok"
    result_type: Literal["visualization", "scalar_answer"]
    query: QuerySummary
    plan: SemanticPlan
    visualization: VisualizationSpec | None = None
    answer: ScalarAnswer | None = None
    provenance: Provenance
    meta: ResponseMetadata

    @model_validator(mode="after")
    def validate_result_payload(self) -> "SuccessResponse":
        if self.result_type == "visualization":
            if self.visualization is None or self.answer is not None:
                raise ValueError("visualization results require only a visualization payload")
        elif self.answer is None or self.visualization is not None:
            raise ValueError("scalar answer results require only an answer payload")
        if self.result_type != self.plan.output_type:
            raise ValueError("result type must agree with semantic plan output type")
        return self


class Clarification(DomainModel):
    question: str = Field(min_length=3, max_length=500)
    missing_fields: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list, max_length=5)


class ClarificationResponse(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    status: Literal["clarification_required"] = "clarification_required"
    clarification: Clarification


class UnsupportedResponse(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    status: Literal["unsupported"] = "unsupported"
    reason: str = Field(min_length=3, max_length=500)
    suggestions: list[str] = Field(default_factory=list, max_length=5)


class ErrorDetail(DomainModel):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    context: dict[str, ScalarValue] = Field(default_factory=dict)


class ErrorResponse(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    status: Literal["error"] = "error"
    error: ErrorDetail


QueryResponse = Annotated[
    SuccessResponse | ClarificationResponse | UnsupportedResponse | ErrorResponse,
    Field(discriminator="status"),
]
