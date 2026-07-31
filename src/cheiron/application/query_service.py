"""End-to-end query orchestration with explicit completeness and provenance."""

from collections.abc import Sequence
from time import monotonic
from typing import Protocol
from uuid import UUID

from cheiron.analysis.pipeline import AnalysisPipeline
from cheiron.clinical_trials.errors import QueryTooBroadError
from cheiron.clinical_trials.models import (
    CohortRetrieval,
    DatasetVersion,
    NormalizationWarning,
)
from cheiron.clinical_trials.normalizer import TrialNormalizer
from cheiron.clinical_trials.query_compiler import (
    ClinicalTrialsQueryCompiler,
    CompiledQuery,
)
from cheiron.domain.enums import CompletenessStatus
from cheiron.domain.plan import CohortSpec
from cheiron.domain.request import QueryRequest
from cheiron.domain.response import (
    Completeness,
    PlannerMetadata,
    Provenance,
    QuerySummary,
    RecordCounts,
    ResponseMetadata,
    SourceMetadata,
    SuccessResponse,
)
from cheiron.planning.base import Planner


class ClinicalTrialsGateway(Protocol):
    """Upstream operations required by query orchestration."""

    async def get_version(self) -> DatasetVersion: ...

    async def fetch_studies(
        self,
        query: CompiledQuery,
        *,
        max_studies: int,
    ) -> CohortRetrieval: ...


class QueryService:
    """Produce a complete public response or raise a typed boundary failure."""

    def __init__(
        self,
        *,
        planner: Planner,
        clinical_trials: ClinicalTrialsGateway,
        source_endpoint: str,
        max_studies: int,
        compiler: ClinicalTrialsQueryCompiler | None = None,
        normalizer: TrialNormalizer | None = None,
        analysis: AnalysisPipeline | None = None,
    ) -> None:
        self._planner = planner
        self._clinical_trials = clinical_trials
        self._source_endpoint = source_endpoint.rstrip("/")
        self._max_studies = max_studies
        self._compiler = compiler or ClinicalTrialsQueryCompiler()
        self._normalizer = normalizer or TrialNormalizer()
        self._analysis = analysis or AnalysisPipeline()

    async def execute(self, request: QueryRequest, *, request_id: UUID) -> SuccessResponse:
        started_at = monotonic()
        planning = await self._planner.plan(request)
        version = await self._clinical_trials.get_version()
        max_studies, limit_warnings = self._effective_limit(request)
        retrievals = await self._retrieve(planning.plan.cohorts, max_studies)

        records_by_cohort = {}
        normalization_excluded = 0
        normalization_warnings: list[str] = []
        for retrieval in retrievals:
            normalized = self._normalizer.normalize_many(retrieval.studies)
            records_by_cohort[retrieval.cohort_id] = normalized.records
            normalization_excluded += normalized.excluded_count
            normalization_warnings.extend(
                self._normalization_warning(warning) for warning in normalized.warnings
            )

        artifacts = self._analysis.run(
            planning.plan,
            records_by_cohort,
            include_citations=request.options.include_citations,
        )
        retrieved_count = sum(len(retrieval.studies) for retrieval in retrievals)
        excluded_count = normalization_excluded + artifacts.excluded_count
        warnings = self._bounded_warnings(
            [*planning.warnings, *limit_warnings, *normalization_warnings]
        )
        retrieved_at = max(retrieval.retrieved_at for retrieval in retrievals)

        return SuccessResponse(
            request_id=request_id,
            query=QuerySummary(
                original=request.query,
                interpretation=planning.plan.interpretation,
                warnings=list(planning.warnings),
            ),
            plan=planning.plan,
            visualization=artifacts.visualization,
            provenance=Provenance(
                source=SourceMetadata(
                    api_version=version.api_version,
                    data_timestamp=version.data_timestamp,
                    retrieved_at=retrieved_at,
                    endpoint=f"{self._source_endpoint}/studies",
                ),
                citations=artifacts.citations,
            ),
            meta=ResponseMetadata(
                planner=PlannerMetadata(
                    mode=planning.mode,
                    model=planning.model,
                    capability_limited=planning.capability_limited,
                ),
                record_counts=RecordCounts(
                    matched=sum(retrieval.matched_count for retrieval in retrievals),
                    retrieved=retrieved_count,
                    used=len(artifacts.used_nct_ids),
                    excluded=excluded_count,
                ),
                completeness=Completeness(
                    status=CompletenessStatus.COMPLETE,
                    is_complete=True,
                    pages_retrieved=sum(retrieval.pages_retrieved for retrieval in retrievals),
                ),
                duration_ms=max(0, round((monotonic() - started_at) * 1_000)),
                warnings=warnings,
            ),
        )

    async def _retrieve(
        self,
        cohorts: Sequence[CohortSpec],
        max_studies: int,
    ) -> list[CohortRetrieval]:
        retrievals: list[CohortRetrieval] = []
        retrieved_count = 0
        for cohort in cohorts:
            compiled = self._compiler.compile(cohort)
            remaining = max_studies - retrieved_count
            try:
                retrieval = await self._clinical_trials.fetch_studies(
                    compiled,
                    max_studies=max(0, remaining),
                )
            except QueryTooBroadError as error:
                raise QueryTooBroadError(
                    retrieved_count + error.matched_count,
                    max_studies,
                ) from error
            retrievals.append(retrieval)
            retrieved_count += len(retrieval.studies)
        return retrievals

    def _effective_limit(self, request: QueryRequest) -> tuple[int, list[str]]:
        requested = request.options.max_studies
        if requested is None or requested <= self._max_studies:
            return requested or self._max_studies, []
        return self._max_studies, [
            f"Requested max_studies={requested} exceeded the server cap; "
            f"applied {self._max_studies}."
        ]

    @staticmethod
    def _normalization_warning(warning: NormalizationWarning) -> str:
        nct_id = warning.nct_id or "unknown study"
        return f"{nct_id}: {warning.field_path}: {warning.message}"

    @staticmethod
    def _bounded_warnings(warnings: Sequence[str], limit: int = 20) -> list[str]:
        if len(warnings) <= limit:
            return list(warnings)
        omitted = len(warnings) - limit
        return [*warnings[:limit], f"{omitted} additional warnings omitted."]
