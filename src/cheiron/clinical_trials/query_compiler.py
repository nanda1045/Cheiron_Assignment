"""Compile allow-listed cohort filters into ClinicalTrials.gov API parameters."""

from dataclasses import dataclass
from typing import ClassVar

from cheiron.domain.enums import FilterField, FilterOperator
from cheiron.domain.plan import CohortSpec, FilterClause

DEFAULT_STUDY_FIELDS = (
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "StartDate",
    "StartDateType",
    "Phase",
    "StudyType",
    "EnrollmentCount",
    "EnrollmentType",
    "LeadSponsorName",
    "LeadSponsorClass",
    "Condition",
    "InterventionName",
    "InterventionType",
    "LocationCountry",
)


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    """Safe API parameters plus filters that require exact local evaluation."""

    cohort_id: str
    params: dict[str, str]
    post_filters: tuple[FilterClause, ...]


class ClinicalTrialsQueryCompiler:
    """Translate a validated cohort without accepting arbitrary API syntax."""

    _SEARCH_PARAMETERS: ClassVar[dict[FilterField, str]] = {
        FilterField.CONDITION: "query.cond",
        FilterField.INTERVENTION: "query.intr",
        FilterField.SPONSOR: "query.spons",
        FilterField.COUNTRY: "query.locn",
    }
    _ADVANCED_SEARCH_AREAS: ClassVar[dict[FilterField, str]] = {
        FilterField.PHASE: "Phase",
        FilterField.STUDY_TYPE: "StudyType",
    }
    _SEARCH_OPERATORS: ClassVar[frozenset[FilterOperator]] = frozenset(
        {
            FilterOperator.CONTAINS,
            FilterOperator.EQUALS,
            FilterOperator.IN,
        }
    )
    _EXACT_OPERATORS: ClassVar[frozenset[FilterOperator]] = frozenset(
        {
            FilterOperator.EQUALS,
            FilterOperator.IN,
        }
    )

    def __init__(self, fields: tuple[str, ...] = DEFAULT_STUDY_FIELDS) -> None:
        self._fields = fields

    def compile(self, cohort: CohortSpec) -> CompiledQuery:
        grouped_terms: dict[str, list[str]] = {}
        advanced_terms: list[str] = []
        post_filters: list[FilterClause] = []

        for filter_clause in cohort.filters:
            parameter = self._SEARCH_PARAMETERS.get(filter_clause.field)
            if parameter is not None and filter_clause.operator in self._SEARCH_OPERATORS:
                grouped_terms.setdefault(parameter, []).extend(
                    str(value) for value in filter_clause.values
                )
                continue

            if (
                filter_clause.field is FilterField.STATUS
                and filter_clause.operator in self._EXACT_OPERATORS
            ):
                grouped_terms.setdefault("filter.overallStatus", []).extend(
                    str(value) for value in filter_clause.values
                )
                continue

            advanced_term = self._compile_advanced_term(filter_clause)
            if advanced_term is not None:
                advanced_terms.append(advanced_term)
                continue

            post_filters.append(filter_clause)

        params = {
            parameter: self._join_parameter_values(parameter, values)
            for parameter, values in grouped_terms.items()
        }
        if advanced_terms:
            params["query.term"] = " AND ".join(advanced_terms)
        params.update(
            {
                "format": "json",
                "fields": ",".join(self._fields),
                "pageSize": "1000",
                "countTotal": "true",
            }
        )
        return CompiledQuery(
            cohort_id=cohort.id,
            params=params,
            post_filters=tuple(post_filters),
        )

    def _compile_advanced_term(self, clause: FilterClause) -> str | None:
        area = self._ADVANCED_SEARCH_AREAS.get(clause.field)
        if area is not None and clause.operator in self._EXACT_OPERATORS:
            return self._join_area_terms(area, [str(value) for value in clause.values])

        if clause.field is FilterField.START_YEAR:
            return self._compile_start_year_term(clause)
        return None

    @classmethod
    def _compile_start_year_term(cls, clause: FilterClause) -> str | None:
        if any(not isinstance(value, int) or isinstance(value, bool) for value in clause.values):
            return None

        years = [int(value) for value in clause.values]
        if clause.operator is FilterOperator.GREATER_THAN_OR_EQUAL:
            return cls._date_range_term(f"01/01/{years[0]}", "MAX")
        if clause.operator is FilterOperator.LESS_THAN_OR_EQUAL:
            return cls._date_range_term("MIN", f"12/31/{years[0]}")
        if clause.operator is FilterOperator.BETWEEN:
            return cls._date_range_term(f"01/01/{years[0]}", f"12/31/{years[1]}")
        if clause.operator is FilterOperator.EQUALS:
            return cls._date_range_term(f"01/01/{years[0]}", f"12/31/{years[0]}")
        if clause.operator is FilterOperator.IN:
            return cls._join_expressions(
                [
                    cls._date_range_term(f"01/01/{year}", f"12/31/{year}")
                    for year in years
                ]
            )
        return None

    @classmethod
    def _date_range_term(cls, lower: str, upper: str) -> str:
        return f"AREA[StartDate]RANGE[{lower}, {upper}]"

    @classmethod
    def _join_area_terms(cls, area: str, values: list[str]) -> str:
        return cls._join_expressions([f"AREA[{area}]{value}" for value in values])

    @staticmethod
    def _join_expressions(expressions: list[str]) -> str:
        if len(expressions) == 1:
            return expressions[0]
        return f"({' OR '.join(expressions)})"

    @classmethod
    def _join_parameter_values(cls, parameter: str, values: list[str]) -> str:
        if parameter == "filter.overallStatus":
            return "|".join(values)
        return cls._join_search_terms(values)

    @staticmethod
    def _join_search_terms(values: list[str]) -> str:
        normalized = [" ".join(value.split()).replace('"', "") for value in values]
        if len(normalized) == 1:
            return normalized[0]
        return " OR ".join(f'"{value}"' for value in normalized)
