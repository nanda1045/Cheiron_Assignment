"""Semantic, partial-match evaluation for model-backed planning decisions."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal, Protocol

from pydantic import Field, model_validator

from cheiron.domain.answer import ScalarAnswerPlan
from cheiron.domain.base import DomainModel
from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    FilterField,
    FilterOperator,
    MeasureField,
    RelationshipEntity,
    VisualizationType,
)
from cheiron.domain.plan import AnalysisPlan, FilterClause
from cheiron.domain.request import QueryRequest
from cheiron.planning.errors import ClarificationNeeded, UnsupportedQuestion
from cheiron.planning.models import PlanningResult

EvalRoute = Literal["visualization", "scalar_answer", "clarification", "unsupported"]


class ExpectedFilter(DomainModel):
    """A filter that must occur in at least the requested number of cohorts."""

    field: FilterField
    operator: FilterOperator | None = None
    values: list[str | int] = Field(min_length=1, max_length=20)
    minimum_cohort_matches: int = Field(default=1, ge=1, le=5)


class ExpectedDecision(DomainModel):
    """Stable semantic properties, excluding presentation wording and generated IDs."""

    route: EvalRoute
    intent: AnalysisIntent | None = None
    visualization: VisualizationType | None = None
    dimensions: list[DimensionField] | None = None
    measure_field: MeasureField | None = None
    aggregation: Aggregation | None = None
    cohort_count: int | None = Field(default=None, ge=1, le=5)
    relationship_source: RelationshipEntity | None = None
    relationship_target: RelationshipEntity | None = None
    filters: list[ExpectedFilter] = Field(default_factory=list)
    forbidden_filters: list[ExpectedFilter] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_route_specific_fields(self) -> "ExpectedDecision":
        visualization_fields = (
            self.intent,
            self.visualization,
            self.dimensions,
            self.relationship_source,
            self.relationship_target,
        )
        if self.route != "visualization" and any(
            value is not None for value in visualization_fields
        ):
            raise ValueError("visualization-only expectations require the visualization route")
        return self


class PlannerEvalCase(DomainModel):
    """One versioned natural-language planner benchmark case."""

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    category: str = Field(min_length=1, max_length=80)
    request: QueryRequest
    expected: ExpectedDecision


class CheckResult(DomainModel):
    """One independently scored semantic assertion."""

    name: str
    passed: bool
    expected: str
    actual: str


class PlannerCaseResult(DomainModel):
    """Observed route, duration, and assertions for one benchmark case."""

    id: str
    category: str
    passed: bool
    duration_ms: int = Field(ge=0)
    expected_route: EvalRoute
    actual_route: EvalRoute | Literal["error"]
    checks: list[CheckResult]
    observed_plan: dict[str, object] | None = None
    detail: str | None = None
    error: str | None = None


class PlannerEvalReport(DomainModel):
    """Machine-readable summary suitable for CI and README evidence."""

    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    model: str
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    check_pass_rate: float = Field(ge=0, le=1)
    duration_ms: int = Field(ge=0)
    cases: list[PlannerCaseResult]


class Planner(Protocol):
    """Small planner boundary that keeps evaluation independent of one provider."""

    async def plan(self, request: QueryRequest) -> PlanningResult: ...


def load_planner_cases(path: Path) -> list[PlannerEvalCase]:
    """Load and validate a JSON array before any paid model request is made."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("planner eval dataset must be a JSON array")
    cases = [PlannerEvalCase.model_validate(item) for item in payload]
    identifiers = [case.id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("planner eval case IDs must be unique")
    return cases


async def evaluate_planner(
    planner: Planner,
    cases: Sequence[PlannerEvalCase],
    *,
    model: str,
) -> PlannerEvalReport:
    """Evaluate cases sequentially for predictable rate and cost behavior."""

    started = perf_counter()
    results = [await _evaluate_case(planner, case) for case in cases]
    passed_cases = sum(result.passed for result in results)
    checks = [check for result in results for check in result.checks]
    passed_checks = sum(check.passed for check in checks)
    return PlannerEvalReport(
        generated_at=datetime.now(UTC),
        model=model,
        total_cases=len(results),
        passed_cases=passed_cases,
        pass_rate=_ratio(passed_cases, len(results)),
        total_checks=len(checks),
        passed_checks=passed_checks,
        check_pass_rate=_ratio(passed_checks, len(checks)),
        duration_ms=round((perf_counter() - started) * 1_000),
        cases=results,
    )


async def _evaluate_case(planner: Planner, case: PlannerEvalCase) -> PlannerCaseResult:
    started = perf_counter()
    detail: str | None = None
    observed_plan: dict[str, object] | None = None
    try:
        planning_result = await planner.plan(case.request)
        plan = planning_result.plan
        observed_plan = plan.model_dump(mode="json")
        route: EvalRoute = plan.output_type
        checks = _plan_checks(case.expected, plan)
        error = None
    except ClarificationNeeded as exception:
        route = "clarification"
        checks = []
        detail = str(exception)
        error = None
    except UnsupportedQuestion as exception:
        route = "unsupported"
        checks = []
        detail = str(exception)
        error = None
    except Exception as exception:
        return PlannerCaseResult(
            id=case.id,
            category=case.category,
            passed=False,
            duration_ms=round((perf_counter() - started) * 1_000),
            expected_route=case.expected.route,
            actual_route="error",
            checks=[],
            observed_plan=None,
            detail=None,
            error=f"{type(exception).__name__}: {exception}",
        )
    route_check = _check("route", case.expected.route, route)
    all_checks = [route_check, *checks] if route == case.expected.route else [route_check]
    return PlannerCaseResult(
        id=case.id,
        category=case.category,
        passed=all(check.passed for check in all_checks),
        duration_ms=round((perf_counter() - started) * 1_000),
        expected_route=case.expected.route,
        actual_route=route,
        checks=all_checks,
        observed_plan=observed_plan,
        detail=detail,
        error=error,
    )


def _plan_checks(
    expected: ExpectedDecision,
    plan: AnalysisPlan | ScalarAnswerPlan,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    if expected.route == "visualization" and isinstance(plan, AnalysisPlan):
        checks.extend(
            (
                _check_if_set("intent", expected.intent, plan.intent),
                _check_if_set("visualization", expected.visualization, plan.visualization),
                _check_if_set(
                    "dimensions",
                    expected.dimensions,
                    [dimension.field for dimension in plan.dimensions],
                ),
            )
        )
        if expected.relationship_source is not None:
            actual = plan.relationship.source if plan.relationship is not None else None
            checks.append(_check("relationship_source", expected.relationship_source, actual))
        if expected.relationship_target is not None:
            actual = plan.relationship.target if plan.relationship is not None else None
            checks.append(_check("relationship_target", expected.relationship_target, actual))

    checks.extend(
        (
            _check_if_set("measure_field", expected.measure_field, plan.measure.field),
            _check_if_set("aggregation", expected.aggregation, plan.measure.aggregation),
            _check_if_set("cohort_count", expected.cohort_count, len(plan.cohorts)),
        )
    )
    checks.extend(
        _filter_check(filter_expectation, plan) for filter_expectation in expected.filters
    )
    checks.extend(
        _filter_absence_check(filter_expectation, plan)
        for filter_expectation in expected.forbidden_filters
    )
    return [check for check in checks if check.name]


def _filter_check(
    expected: ExpectedFilter,
    plan: AnalysisPlan | ScalarAnswerPlan,
) -> CheckResult:
    matches = sum(
        any(_filter_matches(expected, clause) for clause in cohort.filters)
        for cohort in plan.cohorts
    )
    label = f"filter:{expected.field.value}:{','.join(map(str, expected.values))}"
    return CheckResult(
        name=label,
        passed=matches >= expected.minimum_cohort_matches,
        expected=f">={expected.minimum_cohort_matches} cohort(s)",
        actual=f"{matches} cohort(s)",
    )


def _filter_absence_check(
    expected: ExpectedFilter,
    plan: AnalysisPlan | ScalarAnswerPlan,
) -> CheckResult:
    matches = sum(
        any(_filter_matches(expected, clause) for clause in cohort.filters)
        for cohort in plan.cohorts
    )
    label = f"forbidden_filter:{expected.field.value}:{','.join(map(str, expected.values))}"
    return CheckResult(
        name=label,
        passed=matches == 0,
        expected="0 cohort(s)",
        actual=f"{matches} cohort(s)",
    )


def _filter_matches(expected: ExpectedFilter, actual: FilterClause) -> bool:
    if actual.field is not expected.field:
        return False
    if expected.operator is not None and actual.operator is not expected.operator:
        return False
    expected_values = {_normalize_value(value) for value in expected.values}
    actual_values = {_normalize_value(value) for value in actual.values}
    return expected_values.issubset(actual_values)


def _normalize_value(value: str | int) -> str | int:
    return " ".join(value.casefold().split()) if isinstance(value, str) else value


def _check_if_set(name: str, expected: object | None, actual: object) -> CheckResult:
    if expected is None:
        return CheckResult(name="", passed=True, expected="", actual="")
    return _check(name, expected, actual)


def _check(name: str, expected: object, actual: object) -> CheckResult:
    expected_text = _display(expected)
    actual_text = _display(actual)
    return CheckResult(
        name=name,
        passed=expected_text == actual_text,
        expected=expected_text,
        actual=actual_text,
    )


def _display(value: object) -> str:
    if isinstance(value, list):
        return json.dumps([getattr(item, "value", item) for item in value], sort_keys=True)
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0
