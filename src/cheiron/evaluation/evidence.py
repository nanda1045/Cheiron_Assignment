"""Deterministic analysis and datum-level provenance evaluation."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field, TypeAdapter, model_validator

from cheiron.analysis.answer import ScalarAnswerPipeline
from cheiron.analysis.pipeline import AnalysisPipeline
from cheiron.clinical_trials.models import TrialRecord
from cheiron.clinical_trials.normalizer import TrialNormalizer
from cheiron.domain.answer import ScalarAnswerPlan
from cheiron.domain.base import DomainModel
from cheiron.domain.plan import AnalysisPlan
from cheiron.domain.response import Citation
from cheiron.domain.visualization import (
    CartesianVisualizationSpec,
    NetworkVisualizationSpec,
    ScalarValue,
)

SemanticPlanAdapter: TypeAdapter[AnalysisPlan | ScalarAnswerPlan] = TypeAdapter(
    AnalysisPlan | ScalarAnswerPlan
)


class ExpectedNetworkNode(DomainModel):
    label: str
    entity_type: str
    value: int | float


class ExpectedNetworkEdge(DomainModel):
    source_label: str
    target_label: str
    weight: int


class ExpectedEvidenceResult(DomainModel):
    output_type: Literal["visualization", "scalar_answer"]
    tabular_values: list[dict[str, ScalarValue]] | None = None
    network_nodes: list[ExpectedNetworkNode] | None = None
    network_edges: list[ExpectedNetworkEdge] | None = None
    scalar_value: int | float | None = None
    used_nct_ids: list[str]
    excluded_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_expected_payload(self) -> "ExpectedEvidenceResult":
        payloads = (self.tabular_values, self.network_nodes, self.scalar_value)
        if sum(payload is not None for payload in payloads) != 1:
            raise ValueError("exactly one expected result payload is required")
        if self.network_edges is not None and self.network_nodes is None:
            raise ValueError("network edges require expected network nodes")
        return self


class EvidenceEvalCase(DomainModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    category: str = Field(min_length=1, max_length=80)
    plan: AnalysisPlan | ScalarAnswerPlan
    include_citations: bool = True
    expected: ExpectedEvidenceResult


class EvidenceCheck(DomainModel):
    name: str
    passed: bool
    expected: str
    actual: str


class EvidenceCaseResult(DomainModel):
    id: str
    category: str
    passed: bool
    duration_ms: int = Field(ge=0)
    checks: list[EvidenceCheck]
    error: str | None = None


class EvidenceEvalReport(DomainModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    fixture_studies: int = Field(ge=0)
    normalized_records: int = Field(ge=0)
    normalization_excluded: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    check_pass_rate: float = Field(ge=0, le=1)
    duration_ms: int = Field(ge=0)
    cases: list[EvidenceCaseResult]


def load_evidence_cases(path: Path) -> list[EvidenceEvalCase]:
    """Load semantic plans and expected deterministic outputs from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("evidence eval dataset must be a JSON array")
    cases: list[EvidenceEvalCase] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each evidence eval case must be an object")
        normalized = dict(item)
        normalized["plan"] = SemanticPlanAdapter.validate_python(item.get("plan"))
        cases.append(EvidenceEvalCase.model_validate(normalized))
    identifiers = [case.id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("evidence eval case IDs must be unique")
    return cases


def load_fixture_studies(paths: Sequence[Path]) -> list[dict[str, object]]:
    """Combine frozen ClinicalTrials.gov pages without reaching the network."""

    studies: list[dict[str, object]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("studies"), list):
            raise ValueError(f"fixture {path} does not contain a studies array")
        for study in payload["studies"]:
            if not isinstance(study, dict):
                raise ValueError(f"fixture {path} contains a non-object study")
            studies.append(study)
    return studies


def evaluate_evidence(
    cases: Sequence[EvidenceEvalCase],
    studies: Sequence[dict[str, object]],
) -> EvidenceEvalReport:
    """Normalize once, execute every plan, and prove each evidence reference."""

    started = perf_counter()
    normalization = TrialNormalizer().normalize_many(studies)
    record_map = {record.nct_id: record for record in normalization.records}
    results = [_evaluate_case(case, normalization.records, record_map) for case in cases]
    checks = [check for result in results for check in result.checks]
    passed_cases = sum(result.passed for result in results)
    passed_checks = sum(check.passed for check in checks)
    return EvidenceEvalReport(
        generated_at=datetime.now(UTC),
        fixture_studies=len(studies),
        normalized_records=len(normalization.records),
        normalization_excluded=normalization.excluded_count,
        total_cases=len(results),
        passed_cases=passed_cases,
        pass_rate=_ratio(passed_cases, len(results)),
        total_checks=len(checks),
        passed_checks=passed_checks,
        check_pass_rate=_ratio(passed_checks, len(checks)),
        duration_ms=round((perf_counter() - started) * 1_000),
        cases=results,
    )


def _evaluate_case(
    case: EvidenceEvalCase,
    records: tuple[TrialRecord, ...],
    record_map: dict[str, TrialRecord],
) -> EvidenceCaseResult:
    started = perf_counter()
    try:
        cohort_records = {cohort.id: records for cohort in case.plan.cohorts}
        if isinstance(case.plan, AnalysisPlan):
            visualization_artifacts = AnalysisPipeline().run(
                case.plan,
                cohort_records,
                include_citations=case.include_citations,
            )
            checks = _visualization_checks(case, visualization_artifacts.visualization)
            citations = visualization_artifacts.citations
            used_nct_ids = visualization_artifacts.used_nct_ids
            excluded_count = visualization_artifacts.excluded_count
            reference_ids = _visualization_reference_ids(
                visualization_artifacts.visualization
            )
        else:
            answer_artifacts = ScalarAnswerPipeline().run(
                case.plan,
                cohort_records,
                include_citations=case.include_citations,
            )
            checks = [
                _check("output_type", case.expected.output_type, "scalar_answer"),
                _check(
                    "scalar_value",
                    case.expected.scalar_value,
                    answer_artifacts.answer.value,
                ),
            ]
            citations = answer_artifacts.citations
            used_nct_ids = answer_artifacts.used_nct_ids
            excluded_count = answer_artifacts.excluded_count
            reference_ids = set(answer_artifacts.answer.citation_ids)
            if case.plan.measure.aggregation.value in {"count", "count_distinct"}:
                cited_trials = {citations[item].nct_id for item in reference_ids}
                checks.append(
                    _check(
                        "scalar_citation_cardinality",
                        answer_artifacts.answer.value,
                        len(cited_trials),
                    )
                )

        checks.extend(
            (
                _check(
                    "used_nct_ids",
                    sorted(case.expected.used_nct_ids),
                    sorted(used_nct_ids),
                ),
                _check("excluded_count", case.expected.excluded_count, excluded_count),
                *_provenance_checks(
                    enabled=case.include_citations,
                    citations=citations,
                    reference_ids=reference_ids,
                    used_nct_ids=used_nct_ids,
                    record_map=record_map,
                ),
            )
        )
        return EvidenceCaseResult(
            id=case.id,
            category=case.category,
            passed=all(check.passed for check in checks),
            duration_ms=round((perf_counter() - started) * 1_000),
            checks=checks,
        )
    except Exception as exception:
        return EvidenceCaseResult(
            id=case.id,
            category=case.category,
            passed=False,
            duration_ms=round((perf_counter() - started) * 1_000),
            checks=[],
            error=f"{type(exception).__name__}: {exception}",
        )


def _visualization_checks(
    case: EvidenceEvalCase,
    visualization: CartesianVisualizationSpec | NetworkVisualizationSpec,
) -> list[EvidenceCheck]:
    checks = [_check("output_type", case.expected.output_type, "visualization")]
    if isinstance(visualization, CartesianVisualizationSpec):
        values = [datum.values for datum in visualization.data.records]
        checks.append(_check("tabular_values", case.expected.tabular_values, values))
        if not case.include_citations:
            return checks
        for datum in visualization.data.records:
            if "trial_count" in datum.values:
                checks.append(
                    _check(
                        f"datum_citation_cardinality:{datum.id}",
                        datum.values["trial_count"],
                        len(datum.citation_ids),
                    )
                )
            elif visualization.type.value == "scatter_plot":
                checks.append(
                    _check(f"datum_citation_cardinality:{datum.id}", 1, len(datum.citation_ids))
                )
        return checks

    nodes = sorted(
        (
            {"label": node.label, "entity_type": node.entity_type, "value": node.value}
            for node in visualization.data.nodes
        ),
        key=lambda node: (str(node["entity_type"]), str(node["label"])),
    )
    node_labels = {node.id: node.label for node in visualization.data.nodes}
    edges = sorted(
        (
            {
                "source_label": node_labels[edge.source],
                "target_label": node_labels[edge.target],
                "weight": edge.weight,
            }
            for edge in visualization.data.edges
        ),
        key=lambda edge: (str(edge["source_label"]), str(edge["target_label"])),
    )
    expected_nodes = (
        sorted(
            [node.model_dump(mode="json") for node in case.expected.network_nodes],
            key=lambda node: (str(node["entity_type"]), str(node["label"])),
        )
        if case.expected.network_nodes is not None
        else None
    )
    expected_edges = (
        sorted(
            [edge.model_dump(mode="json") for edge in case.expected.network_edges],
            key=lambda edge: (str(edge["source_label"]), str(edge["target_label"])),
        )
        if case.expected.network_edges is not None
        else None
    )
    checks.extend(
        (
            _check("network_nodes", expected_nodes, nodes),
            _check("network_edges", expected_edges, edges),
        )
    )
    if not case.include_citations:
        return checks
    checks.extend(
        _check(f"node_citation_cardinality:{node.id}", node.value, len(node.citation_ids))
        for node in visualization.data.nodes
    )
    checks.extend(
        _check(f"edge_citation_cardinality:{edge.id}", edge.weight, len(edge.citation_ids))
        for edge in visualization.data.edges
    )
    return checks


def _provenance_checks(
    *,
    enabled: bool,
    citations: dict[str, Citation],
    reference_ids: set[str],
    used_nct_ids: frozenset[str],
    record_map: dict[str, TrialRecord],
) -> list[EvidenceCheck]:
    if not enabled:
        return [
            _check("citations_disabled_catalog", 0, len(citations)),
            _check("citations_disabled_references", 0, len(reference_ids)),
        ]

    checks = [
        _check("all_references_resolve", sorted(reference_ids), sorted(citations)),
        _check(
            "cited_trials_equal_used_trials",
            sorted(used_nct_ids),
            sorted({citation.nct_id for citation in citations.values()}),
        ),
    ]
    for citation_id, citation in citations.items():
        record = record_map.get(citation.nct_id)
        checks.append(
            _check(
                f"citation_record_exists:{citation_id}",
                True,
                record is not None,
            )
        )
        if record is None:
            continue
        checks.append(
            _check(
                f"citation_url:{citation_id}",
                f"https://clinicaltrials.gov/study/{citation.nct_id}",
                str(citation.study_url),
            )
        )
        for evidence in citation.evidence:
            checks.append(
                _check(
                    f"evidence:{citation_id}:{evidence.field_path}",
                    record.source_values.get(evidence.field_path),
                    evidence.value,
                )
            )
    return checks


def _visualization_reference_ids(
    visualization: CartesianVisualizationSpec | NetworkVisualizationSpec,
) -> set[str]:
    if isinstance(visualization, CartesianVisualizationSpec):
        return {item for datum in visualization.data.records for item in datum.citation_ids}
    node_references = {
        item for node in visualization.data.nodes for item in node.citation_ids
    }
    edge_references = {
        item for edge in visualization.data.edges for item in edge.citation_ids
    }
    return node_references | edge_references


def _check(name: str, expected: object, actual: object) -> EvidenceCheck:
    expected_text = json.dumps(expected, sort_keys=True, default=str)
    actual_text = json.dumps(actual, sort_keys=True, default=str)
    return EvidenceCheck(
        name=name,
        passed=expected_text == actual_text,
        expected=expected_text,
        actual=actual_text,
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0
