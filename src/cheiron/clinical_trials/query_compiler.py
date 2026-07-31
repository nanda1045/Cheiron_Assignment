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

    _PUSH_DOWN_PARAMETERS: ClassVar[dict[FilterField, str]] = {
        FilterField.CONDITION: "query.cond",
        FilterField.INTERVENTION: "query.intr",
        FilterField.SPONSOR: "query.spons",
        FilterField.COUNTRY: "query.locn",
    }

    def __init__(self, fields: tuple[str, ...] = DEFAULT_STUDY_FIELDS) -> None:
        self._fields = fields

    def compile(self, cohort: CohortSpec) -> CompiledQuery:
        grouped_terms: dict[str, list[str]] = {}
        post_filters: list[FilterClause] = []

        for filter_clause in cohort.filters:
            parameter = self._PUSH_DOWN_PARAMETERS.get(filter_clause.field)
            if parameter is not None and filter_clause.operator in {
                FilterOperator.CONTAINS,
                FilterOperator.EQUALS,
                FilterOperator.IN,
            }:
                grouped_terms.setdefault(parameter, []).extend(
                    str(value) for value in filter_clause.values
                )
            else:
                post_filters.append(filter_clause)

        params = {
            parameter: self._join_search_terms(values)
            for parameter, values in grouped_terms.items()
        }
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

    @staticmethod
    def _join_search_terms(values: list[str]) -> str:
        normalized = [" ".join(value.split()).replace('"', "") for value in values]
        if len(normalized) == 1:
            return normalized[0]
        return " OR ".join(f'"{value}"' for value in normalized)
