"""Deterministic scalar aggregation and datum-level provenance."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cheiron.analysis.errors import MissingCohortError
from cheiron.analysis.evidence import cohort_filter_evidence_paths
from cheiron.analysis.filtering import RecordFilter
from cheiron.clinical_trials.models import TrialRecord
from cheiron.clinical_trials.normalizer import ENROLLMENT_COUNT_PATH
from cheiron.domain.answer import ScalarAnswer, ScalarAnswerPlan
from cheiron.domain.enums import Aggregation, MeasureField
from cheiron.domain.response import Citation
from cheiron.provenance.builder import ProvenanceCatalog


@dataclass(frozen=True, slots=True)
class ScalarAnswerArtifacts:
    answer: ScalarAnswer
    citations: dict[str, Citation]
    used_nct_ids: frozenset[str]
    excluded_count: int


class ScalarAnswerPipeline:
    """Compute one allow-listed aggregate without asking the model to write facts."""

    def __init__(self, record_filter: RecordFilter | None = None) -> None:
        self._record_filter = record_filter or RecordFilter()

    def run(
        self,
        plan: ScalarAnswerPlan,
        cohort_records: Mapping[str, Iterable[TrialRecord]],
        *,
        include_citations: bool,
    ) -> ScalarAnswerArtifacts:
        cohort = plan.cohorts[0]
        if cohort.id not in cohort_records:
            raise MissingCohortError(f"missing records for planned cohort {cohort.id!r}")
        records = tuple(cohort_records[cohort.id])
        unique_records = {record.nct_id: record for record in records}
        matching = self._record_filter.filter(unique_records.values(), cohort.filters)
        contributors = self._contributors(plan, matching)
        value = self._aggregate(plan, contributors)
        evidence_paths = list(cohort_filter_evidence_paths(plan.cohorts))
        if plan.measure.field is MeasureField.ENROLLMENT:
            evidence_paths.append(ENROLLMENT_COUNT_PATH)
        normalized_paths = tuple(dict.fromkeys(evidence_paths))

        provenance = ProvenanceCatalog(enabled=include_citations)
        citation_ids = provenance.references_for(
            "scalar-answer",
            contributors,
            normalized_paths,
        )
        used_nct_ids = frozenset(record.nct_id for record in contributors)
        return ScalarAnswerArtifacts(
            answer=ScalarAnswer(
                title=plan.measure.label,
                text=self._answer_text(plan, value, len(contributors)),
                value=value,
                unit=plan.measure.unit,
                citation_ids=citation_ids,
            ),
            citations=provenance.citations,
            used_nct_ids=used_nct_ids,
            excluded_count=len(set(unique_records) - used_nct_ids),
        )

    @staticmethod
    def _contributors(
        plan: ScalarAnswerPlan,
        matching: tuple[TrialRecord, ...],
    ) -> tuple[TrialRecord, ...]:
        if plan.measure.field is MeasureField.NCT_ID:
            return matching
        return tuple(record for record in matching if record.enrollment_count is not None)

    @staticmethod
    def _aggregate(
        plan: ScalarAnswerPlan,
        contributors: tuple[TrialRecord, ...],
    ) -> int | float | None:
        aggregation = plan.measure.aggregation
        if aggregation in {Aggregation.COUNT, Aggregation.COUNT_DISTINCT}:
            return len(contributors)
        values = [
            record.enrollment_count
            for record in contributors
            if record.enrollment_count is not None
        ]
        if not values:
            return None
        if aggregation is Aggregation.SUM:
            return sum(values)
        if aggregation is Aggregation.AVERAGE:
            return round(sum(values) / len(values), 2)
        raise AssertionError(f"validated scalar aggregation became unsupported: {aggregation}")

    @staticmethod
    def _answer_text(
        plan: ScalarAnswerPlan,
        value: int | float | None,
        contributor_count: int,
    ) -> str:
        if plan.measure.field is MeasureField.NCT_ID:
            count = int(value or 0)
            noun = "trial" if count == 1 else "trials"
            verb = "was" if count == 1 else "were"
            return f"{count:,} matching clinical {noun} {verb} found in the source snapshot."
        if value is None:
            return "No matching trials reported planned enrollment."
        formatted = f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"
        if plan.measure.aggregation is Aggregation.AVERAGE:
            return (
                f"Average planned enrollment is {formatted} participants across "
                f"{contributor_count:,} matching trials that reported enrollment."
            )
        return (
            f"Total planned enrollment is {formatted} participants across "
            f"{contributor_count:,} matching trials that reported enrollment."
        )
