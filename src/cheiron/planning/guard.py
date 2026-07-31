"""Application-side checks for model-produced semantic plans."""

from collections.abc import Iterable, Sequence
from typing import NoReturn

from cheiron.domain.enums import (
    AnalysisIntent,
    FilterField,
    FilterOperator,
)
from cheiron.domain.plan import AnalysisPlan, CohortSpec, FilterClause
from cheiron.domain.request import QueryRequest
from cheiron.planning.errors import ModelPlanRejectedError

_LIST_FILTERS = (
    ("conditions", FilterField.CONDITION),
    ("interventions", FilterField.INTERVENTION),
    ("phases", FilterField.PHASE),
    ("statuses", FilterField.STATUS),
    ("sponsors", FilterField.SPONSOR),
    ("sponsor_classes", FilterField.SPONSOR_CLASS),
    ("countries", FilterField.COUNTRY),
    ("study_types", FilterField.STUDY_TYPE),
)

_TEXT_OPERATORS = {
    FilterOperator.CONTAINS,
    FilterOperator.EQUALS,
    FilterOperator.IN,
}


class ModelPlanGuard:
    """Reject schema-valid plans that violate authoritative request fields."""

    def validate(self, request: QueryRequest, plan: AnalysisPlan) -> None:
        preferred = request.options.preferred_visualization
        if preferred is not None and plan.visualization is not preferred:
            self._reject("model plan ignored the preferred visualization")

        for attribute, field in _LIST_FILTERS:
            raw_values = getattr(request.filters, attribute)
            expected = [getattr(value, "value", value) for value in raw_values]
            if expected:
                self._validate_list_filter(plan, field, expected)

        self._validate_year_filters(request, plan)

    def _validate_list_filter(
        self,
        plan: AnalysisPlan,
        field: FilterField,
        expected_values: Sequence[str],
    ) -> None:
        expected = self._normalized(expected_values)
        values_by_cohort: list[frozenset[str]] = []
        for cohort in plan.cohorts:
            clauses = self._clauses(cohort, field)
            if len(clauses) != 1 or clauses[0].operator not in _TEXT_OPERATORS:
                self._reject(f"model plan did not preserve structured {field.value} filters")
            actual = self._normalized(str(value) for value in clauses[0].values)
            if not actual or not actual <= expected:
                self._reject(f"model plan changed structured {field.value} values")
            values_by_cohort.append(actual)

        if all(values == expected for values in values_by_cohort):
            return
        if plan.intent is AnalysisIntent.COMPARISON and field is FilterField.INTERVENTION:
            combined = frozenset().union(*values_by_cohort)
            total_values = sum(len(values) for values in values_by_cohort)
            if combined == expected and total_values == len(combined):
                return
        self._reject(f"model plan did not apply all structured {field.value} values")

    def _validate_year_filters(self, request: QueryRequest, plan: AnalysisPlan) -> None:
        lower = request.filters.start_year_from
        upper = request.filters.start_year_to
        if lower is None and upper is None:
            return

        if lower is not None and upper is not None:
            expected_operator = FilterOperator.BETWEEN
            expected_values = [lower, upper]
        elif lower is not None:
            expected_operator = FilterOperator.GREATER_THAN_OR_EQUAL
            expected_values = [lower]
        else:
            assert upper is not None
            expected_operator = FilterOperator.LESS_THAN_OR_EQUAL
            expected_values = [upper]

        for cohort in plan.cohorts:
            clauses = self._clauses(cohort, FilterField.START_YEAR)
            if (
                len(clauses) != 1
                or clauses[0].operator is not expected_operator
                or clauses[0].values != expected_values
            ):
                self._reject("model plan changed the structured start-year range")

    @staticmethod
    def _clauses(cohort: CohortSpec, field: FilterField) -> list[FilterClause]:
        return [clause for clause in cohort.filters if clause.field is field]

    @staticmethod
    def _normalized(values: Iterable[object]) -> frozenset[str]:
        return frozenset(" ".join(str(value).casefold().split()) for value in values)

    @staticmethod
    def _reject(message: str) -> NoReturn:
        raise ModelPlanRejectedError(message)
