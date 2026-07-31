"""Exact local evaluation of cohort predicates over normalized records."""

from collections.abc import Callable, Iterable

from cheiron.clinical_trials.models import TrialRecord
from cheiron.domain.enums import FilterField, FilterOperator
from cheiron.domain.plan import FilterClause, PlanValue

RecordValues = tuple[str | int, ...]


class RecordFilter:
    """Recheck all model-selected filters after upstream search retrieval."""

    def filter(
        self,
        records: Iterable[TrialRecord],
        clauses: Iterable[FilterClause],
    ) -> tuple[TrialRecord, ...]:
        filters = tuple(clauses)
        return tuple(record for record in records if self.matches_all(record, filters))

    def matches_all(self, record: TrialRecord, clauses: Iterable[FilterClause]) -> bool:
        return all(self.matches(record, clause) for clause in clauses)

    def matches(self, record: TrialRecord, clause: FilterClause) -> bool:
        record_values = self._values(record, clause.field)
        if not record_values:
            return False

        if clause.operator is FilterOperator.CONTAINS:
            expected = self._normalized_string(clause.values[0])
            return any(
                expected in self._normalized_string(value)
                for value in record_values
                if isinstance(value, str)
            )
        if clause.operator is FilterOperator.EQUALS:
            return self._any_equal(record_values, clause.values[0])
        if clause.operator is FilterOperator.IN:
            return any(self._any_equal(record_values, expected) for expected in clause.values)
        if clause.operator is FilterOperator.BETWEEN:
            lower, upper = clause.values
            return self._any_numeric(record_values, lambda value: int(lower) <= value <= int(upper))
        if clause.operator is FilterOperator.GREATER_THAN_OR_EQUAL:
            threshold = int(clause.values[0])
            return self._any_numeric(record_values, lambda value: value >= threshold)
        if clause.operator is FilterOperator.LESS_THAN_OR_EQUAL:
            threshold = int(clause.values[0])
            return self._any_numeric(record_values, lambda value: value <= threshold)
        return False

    @staticmethod
    def _values(record: TrialRecord, field: FilterField) -> RecordValues:
        if field is FilterField.CONDITION:
            return record.conditions
        if field is FilterField.INTERVENTION:
            return tuple(intervention.name for intervention in record.interventions)
        if field is FilterField.PHASE:
            return record.phases
        if field is FilterField.SPONSOR:
            return (record.lead_sponsor_name,) if record.lead_sponsor_name else ()
        if field is FilterField.SPONSOR_CLASS:
            return (record.lead_sponsor_class,) if record.lead_sponsor_class else ()
        if field is FilterField.COUNTRY:
            return record.countries
        if field is FilterField.STATUS:
            return (record.overall_status,) if record.overall_status else ()
        if field is FilterField.STUDY_TYPE:
            return (record.study_type,) if record.study_type else ()
        if field is FilterField.START_YEAR:
            return (record.start_date.year,) if record.start_date else ()
        if field is FilterField.ENROLLMENT:
            return (record.enrollment_count,) if record.enrollment_count is not None else ()
        return ()

    @classmethod
    def _any_equal(cls, record_values: RecordValues, expected: PlanValue) -> bool:
        if isinstance(expected, int):
            return expected in record_values
        normalized_expected = cls._normalized_string(expected)
        return any(
            cls._normalized_string(value) == normalized_expected
            for value in record_values
            if isinstance(value, str)
        )

    @staticmethod
    def _any_numeric(record_values: RecordValues, predicate: Callable[[int], bool]) -> bool:
        return any(predicate(value) for value in record_values if isinstance(value, int))

    @staticmethod
    def _normalized_string(value: str | int) -> str:
        return " ".join(str(value).casefold().split())
