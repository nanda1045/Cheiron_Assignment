"""Generic distinct-study aggregations and specialized histogram/scatter/network analyses."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from hashlib import sha256
from itertools import product
from math import ceil, sqrt

from cheiron.analysis.errors import MissingCohortError, UnsupportedAnalysisError
from cheiron.analysis.evidence import cohort_filter_evidence_paths
from cheiron.analysis.filtering import RecordFilter
from cheiron.analysis.models import (
    AnalysisDatum,
    AnalysisResult,
    NetworkAnalysis,
    NetworkEdgeAnalysis,
    NetworkNodeAnalysis,
    TabularAnalysis,
)
from cheiron.clinical_trials.models import TrialRecord
from cheiron.clinical_trials.normalizer import (
    CONDITIONS_PATH,
    ENROLLMENT_COUNT_PATH,
    INTERVENTIONS_PATH,
    LOCATIONS_PATH,
    PHASES_PATH,
    SPONSOR_CLASS_PATH,
    SPONSOR_NAME_PATH,
    START_DATE_PATH,
)
from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    RelationshipEntity,
)
from cheiron.domain.plan import AnalysisPlan, DimensionSpec
from cheiron.domain.visualization import ScalarValue

PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Not Applicable",
}
PHASE_ORDER = {label: index for index, label in enumerate(PHASE_LABELS.values())}

DIMENSION_EVIDENCE_PATHS = {
    DimensionField.START_YEAR: (START_DATE_PATH,),
    DimensionField.PHASE: (PHASES_PATH,),
    DimensionField.INTERVENTION_TYPE: (f"{INTERVENTIONS_PATH}.type",),
    DimensionField.SPONSOR_CLASS: (SPONSOR_CLASS_PATH,),
    DimensionField.COUNTRY: (f"{LOCATIONS_PATH}.country",),
    DimensionField.ENROLLMENT: (ENROLLMENT_COUNT_PATH,),
    DimensionField.SPONSOR: (SPONSOR_NAME_PATH,),
    DimensionField.INTERVENTION: (f"{INTERVENTIONS_PATH}.name",),
}

RELATIONSHIP_EVIDENCE_PATHS = {
    RelationshipEntity.SPONSOR: (SPONSOR_NAME_PATH,),
    RelationshipEntity.INTERVENTION: (f"{INTERVENTIONS_PATH}.name",),
    RelationshipEntity.CONDITION: (CONDITIONS_PATH,),
    RelationshipEntity.COUNTRY: (f"{LOCATIONS_PATH}.country",),
}


class AnalysisEngine:
    """Execute an allow-listed plan over normalized records without model involvement."""

    def __init__(self, record_filter: RecordFilter | None = None) -> None:
        self._record_filter = record_filter or RecordFilter()

    def execute(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, Iterable[TrialRecord]],
    ) -> tuple[AnalysisResult, frozenset[str], int]:
        filtered_cohorts, input_nct_ids = self._filter_cohorts(plan, cohort_records)

        if plan.intent is AnalysisIntent.RELATIONSHIP:
            result: AnalysisResult = self._network(plan, filtered_cohorts)
        elif plan.intent is AnalysisIntent.HISTOGRAM:
            result = self._histogram(plan, filtered_cohorts)
        elif plan.intent is AnalysisIntent.SCATTER:
            result = self._scatter(plan, filtered_cohorts)
        else:
            result = self._grouped_aggregation(plan, filtered_cohorts)
        used_nct_ids = self._result_nct_ids(result)
        excluded_count = len(input_nct_ids - used_nct_ids)
        return result, used_nct_ids, excluded_count

    def _filter_cohorts(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, Iterable[TrialRecord]],
    ) -> tuple[dict[str, tuple[TrialRecord, ...]], frozenset[str]]:
        filtered: dict[str, tuple[TrialRecord, ...]] = {}
        input_nct_ids: set[str] = set()
        for cohort in plan.cohorts:
            if cohort.id not in cohort_records:
                raise MissingCohortError(f"missing records for planned cohort {cohort.id!r}")
            records = tuple(cohort_records[cohort.id])
            input_nct_ids.update(record.nct_id for record in records)
            matching = self._record_filter.filter(records, cohort.filters)
            filtered[cohort.id] = matching
        return filtered, frozenset(input_nct_ids)

    def _grouped_aggregation(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, tuple[TrialRecord, ...]],
    ) -> TabularAnalysis:
        dimension_specs = list(plan.dimensions)
        include_cohort = len(plan.cohorts) > 1
        dimension_fields = [dimension.field.value for dimension in dimension_specs]
        if include_cohort:
            dimension_fields.append(DimensionField.COHORT.value)

        groups: dict[tuple[ScalarValue, ...], dict[str, TrialRecord]] = defaultdict(dict)
        cohort_labels = {cohort.id: cohort.label for cohort in plan.cohorts}

        for cohort in plan.cohorts:
            for record in cohort_records[cohort.id]:
                value_sets = [self._dimension_values(record, spec) for spec in dimension_specs]
                if any(not values for values in value_sets):
                    continue
                for combination in product(*value_sets):
                    group_key = (
                        (*combination, cohort_labels[cohort.id]) if include_cohort else combination
                    )
                    groups[group_key][record.nct_id] = record

        measure_field = self._measure_output_field(plan)
        evidence_paths = self._evidence_paths(plan, dimension_specs)
        data: list[AnalysisDatum] = []
        for group_key, record_map in groups.items():
            contributors = tuple(sorted(record_map.values(), key=lambda record: record.nct_id))
            measure_value, measured_contributors = self._aggregate(plan, contributors)
            if measure_value is None:
                continue
            values: dict[str, ScalarValue] = dict(zip(dimension_fields, group_key, strict=True))
            values[measure_field] = measure_value
            datum_id = self._stable_id((*group_key, measure_field))
            data.append(
                AnalysisDatum(
                    id=datum_id,
                    values=values,
                    contributors=measured_contributors,
                    evidence_paths=evidence_paths,
                )
            )

        self._sort_data(data, plan, dimension_fields, measure_field)
        if plan.limit is not None:
            data = data[: plan.limit]
        return TabularAnalysis(
            records=tuple(data),
            measure_field=measure_field,
            dimension_fields=tuple(dimension_fields),
        )

    def _histogram(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, tuple[TrialRecord, ...]],
    ) -> TabularAnalysis:
        records = self._unique_records(cohort_records.values())
        enrolled = [record for record in records if record.enrollment_count is not None]
        if not enrolled:
            return TabularAnalysis(
                records=(),
                measure_field="trial_count",
                dimension_fields=("bin",),
            )

        enrollment_values = [
            record.enrollment_count for record in enrolled if record.enrollment_count is not None
        ]
        minimum = min(enrollment_values)
        maximum = max(enrollment_values)
        bin_count = min(10, max(1, ceil(sqrt(len(enrolled)))))
        width = max(1, ceil((maximum - minimum + 1) / bin_count))
        bins: dict[int, list[TrialRecord]] = defaultdict(list)
        for record in enrolled:
            assert record.enrollment_count is not None
            bin_index = min((record.enrollment_count - minimum) // width, bin_count - 1)
            bins[bin_index].append(record)

        data: list[AnalysisDatum] = []
        for bin_index in range(bin_count):
            lower = minimum + bin_index * width
            upper = min(maximum, lower + width - 1)
            contributors = tuple(sorted(bins.get(bin_index, []), key=lambda record: record.nct_id))
            data.append(
                AnalysisDatum(
                    id=f"enrollment-{lower}-{upper}",
                    values={
                        "bin": f"{lower:,}-{upper:,}",
                        "bin_start": lower,
                        "bin_end": upper,
                        "trial_count": len(contributors),
                    },
                    contributors=contributors,
                    evidence_paths=(ENROLLMENT_COUNT_PATH,),
                )
            )
        return TabularAnalysis(
            records=tuple(data),
            measure_field="trial_count",
            dimension_fields=("bin",),
        )

    def _scatter(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, tuple[TrialRecord, ...]],
    ) -> TabularAnalysis:
        records = self._unique_records(cohort_records.values())
        data: list[AnalysisDatum] = []
        for record in records:
            if record.start_date is None or record.enrollment_count is None:
                continue
            data.append(
                AnalysisDatum(
                    id=record.nct_id.casefold(),
                    values={
                        "nct_id": record.nct_id,
                        "start_year": record.start_date.year,
                        "enrollment": record.enrollment_count,
                    },
                    contributors=(record,),
                    evidence_paths=(START_DATE_PATH, ENROLLMENT_COUNT_PATH),
                )
            )
        data.sort(
            key=lambda datum: (
                self._numeric_value(datum.values["start_year"]),
                str(datum.values["nct_id"]),
            )
        )
        return TabularAnalysis(
            records=tuple(data),
            measure_field="enrollment",
            dimension_fields=("start_year",),
        )

    def _network(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, tuple[TrialRecord, ...]],
    ) -> NetworkAnalysis:
        relationship = plan.relationship
        if relationship is None:
            raise UnsupportedAnalysisError("network analysis requires relationship details")
        records = self._unique_records(cohort_records.values())
        pair_records: dict[tuple[str, str], dict[str, TrialRecord]] = defaultdict(dict)
        labels: dict[str, str] = {}

        for record in records:
            source_values = self._entity_values(record, relationship.source)
            target_values = self._entity_values(record, relationship.target)
            for source_label, target_label in product(source_values, target_values):
                if relationship.source is relationship.target and source_label >= target_label:
                    continue
                source_id = self._entity_id(relationship.source, source_label)
                target_id = self._entity_id(relationship.target, target_label)
                labels[source_id] = source_label
                labels[target_id] = target_label
                pair_records[(source_id, target_id)][record.nct_id] = record

        pair_records = {
            pair: contributors
            for pair, contributors in pair_records.items()
            if len(contributors) >= relationship.minimum_weight
        }
        selected_pairs: dict[tuple[str, str], dict[str, TrialRecord]] = {}
        selected_node_ids: set[str] = set()
        for pair, contributors in sorted(
            pair_records.items(), key=lambda item: (-len(item[1]), item[0])
        ):
            new_node_ids = set(pair) - selected_node_ids
            if len(selected_node_ids) + len(new_node_ids) > relationship.max_nodes:
                continue
            selected_pairs[pair] = contributors
            selected_node_ids.update(pair)
        pair_records = selected_pairs
        visible_node_records: dict[str, dict[str, TrialRecord]] = defaultdict(dict)
        for (source_id, target_id), contributors in pair_records.items():
            visible_node_records[source_id].update(contributors)
            visible_node_records[target_id].update(contributors)

        source_paths = RELATIONSHIP_EVIDENCE_PATHS[relationship.source]
        target_paths = RELATIONSHIP_EVIDENCE_PATHS[relationship.target]
        nodes = tuple(
            NetworkNodeAnalysis(
                id=node_id,
                label=labels[node_id],
                entity_type=node_id.split(":", maxsplit=1)[0],
                value=len(visible_node_records[node_id]),
                contributors=tuple(
                    sorted(
                        visible_node_records[node_id].values(),
                        key=lambda record: record.nct_id,
                    )
                ),
                evidence_paths=source_paths
                if node_id.startswith(f"{relationship.source.value}:")
                else target_paths,
            )
            for node_id in sorted(visible_node_records, key=lambda value: labels[value].casefold())
        )
        edges = tuple(
            NetworkEdgeAnalysis(
                id=self._stable_id((source_id, target_id)),
                source=source_id,
                target=target_id,
                weight=len(contributors),
                contributors=tuple(sorted(contributors.values(), key=lambda record: record.nct_id)),
                evidence_paths=tuple(dict.fromkeys((*source_paths, *target_paths))),
            )
            for (source_id, target_id), contributors in sorted(
                pair_records.items(), key=lambda item: (-len(item[1]), item[0])
            )
        )
        return NetworkAnalysis(nodes=nodes, edges=edges)

    @staticmethod
    def _dimension_values(record: TrialRecord, dimension: DimensionSpec) -> tuple[ScalarValue, ...]:
        field = dimension.field
        if field is DimensionField.START_YEAR:
            return (record.start_date.year,) if record.start_date else ()
        if field is DimensionField.PHASE:
            return tuple(
                PHASE_LABELS.get(phase, phase.replace("_", " ").title()) for phase in record.phases
            )
        if field is DimensionField.INTERVENTION_TYPE:
            return tuple(
                dict.fromkeys(
                    intervention.type.replace("_", " ").title()
                    for intervention in record.interventions
                    if intervention.type
                )
            )
        if field is DimensionField.SPONSOR_CLASS:
            return (
                (record.lead_sponsor_class.replace("_", " ").title(),)
                if record.lead_sponsor_class
                else ()
            )
        if field is DimensionField.COUNTRY:
            return record.countries
        if field is DimensionField.ENROLLMENT:
            return (record.enrollment_count,) if record.enrollment_count is not None else ()
        if field is DimensionField.SPONSOR:
            return (record.lead_sponsor_name,) if record.lead_sponsor_name else ()
        if field is DimensionField.INTERVENTION:
            return tuple(intervention.name for intervention in record.interventions)
        if field is DimensionField.COHORT:
            raise UnsupportedAnalysisError("cohort is injected automatically for comparisons")
        return ()

    @staticmethod
    def _entity_values(record: TrialRecord, entity: RelationshipEntity) -> tuple[str, ...]:
        if entity is RelationshipEntity.SPONSOR:
            return (record.lead_sponsor_name,) if record.lead_sponsor_name else ()
        if entity is RelationshipEntity.INTERVENTION:
            return tuple(intervention.name for intervention in record.interventions)
        if entity is RelationshipEntity.CONDITION:
            return record.conditions
        if entity is RelationshipEntity.COUNTRY:
            return record.countries
        return ()

    @staticmethod
    def _aggregate(
        plan: AnalysisPlan,
        contributors: tuple[TrialRecord, ...],
    ) -> tuple[ScalarValue, tuple[TrialRecord, ...]]:
        aggregation = plan.measure.aggregation
        if aggregation is Aggregation.COUNT_DISTINCT:
            return len(contributors), contributors
        if aggregation is Aggregation.COUNT:
            return len(contributors), contributors
        enrollment_records = tuple(
            record for record in contributors if record.enrollment_count is not None
        )
        values = [record.enrollment_count for record in enrollment_records]
        if not values:
            return None, ()
        numeric_values = [value for value in values if value is not None]
        if aggregation is Aggregation.SUM:
            return sum(numeric_values), enrollment_records
        if aggregation is Aggregation.AVERAGE:
            return round(sum(numeric_values) / len(numeric_values), 2), enrollment_records
        raise UnsupportedAnalysisError(f"unsupported grouped aggregation {aggregation.value!r}")

    @staticmethod
    def _measure_output_field(plan: AnalysisPlan) -> str:
        aggregation = plan.measure.aggregation
        if aggregation in {Aggregation.COUNT, Aggregation.COUNT_DISTINCT}:
            return "trial_count"
        if aggregation is Aggregation.SUM:
            return "enrollment_sum"
        if aggregation is Aggregation.AVERAGE:
            return "average_enrollment"
        return plan.measure.field.value

    @staticmethod
    def _evidence_paths(plan: AnalysisPlan, dimensions: list[DimensionSpec]) -> tuple[str, ...]:
        paths = list(cohort_filter_evidence_paths(plan.cohorts))
        for dimension in dimensions:
            paths.extend(DIMENSION_EVIDENCE_PATHS.get(dimension.field, ()))
        if plan.measure.field.value == "enrollment":
            paths.append(ENROLLMENT_COUNT_PATH)
        return tuple(dict.fromkeys(paths))

    @staticmethod
    def _sort_data(
        data: list[AnalysisDatum],
        plan: AnalysisPlan,
        dimension_fields: list[str],
        measure_field: str,
    ) -> None:
        sort_spec = plan.sort
        if sort_spec is not None:
            reverse = sort_spec.direction.value == "descending"
            data.sort(
                key=lambda datum: AnalysisEngine._sortable(datum.values.get(sort_spec.field)),
                reverse=reverse,
            )
            return
        primary = dimension_fields[0]
        if primary == DimensionField.PHASE.value:
            data.sort(
                key=lambda datum: (
                    PHASE_ORDER.get(str(datum.values[primary]), len(PHASE_ORDER)),
                    str(datum.values.get(DimensionField.COHORT.value, "")),
                )
            )
        elif primary == DimensionField.START_YEAR.value:
            data.sort(key=lambda datum: AnalysisEngine._numeric_value(datum.values[primary]))
        else:
            data.sort(
                key=lambda datum: (
                    -AnalysisEngine._numeric_value(datum.values[measure_field]),
                    datum.id,
                )
            )

    @staticmethod
    def _sortable(value: ScalarValue) -> tuple[int, float | str]:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return (0, float(value))
        return (1, "" if value is None else str(value).casefold())

    @staticmethod
    def _numeric_value(value: ScalarValue) -> float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        raise UnsupportedAnalysisError(f"expected a numeric value, received {value!r}")

    @staticmethod
    def _result_nct_ids(result: AnalysisResult) -> frozenset[str]:
        if isinstance(result, TabularAnalysis):
            return frozenset(
                record.nct_id for datum in result.records for record in datum.contributors
            )
        return frozenset(record.nct_id for edge in result.edges for record in edge.contributors)

    @staticmethod
    def _unique_records(
        cohorts: Iterable[tuple[TrialRecord, ...]],
    ) -> tuple[TrialRecord, ...]:
        records: dict[str, TrialRecord] = {}
        for cohort in cohorts:
            for record in cohort:
                records[record.nct_id] = record
        return tuple(sorted(records.values(), key=lambda record: record.nct_id))

    @staticmethod
    def _entity_id(entity: RelationshipEntity, label: str) -> str:
        return f"{entity.value}:{AnalysisEngine._stable_id((label,))}"

    @staticmethod
    def _stable_id(values: tuple[object, ...]) -> str:
        parts = []
        for value in values:
            normalized = "".join(
                character if character.isalnum() else "-" for character in str(value).casefold()
            )
            parts.append("-".join(part for part in normalized.split("-") if part))
        slug = "--".join(parts) or "datum"
        digest_input = "\x1f".join(f"{type(value).__name__}:{value}" for value in values).encode()
        digest = sha256(digest_input).hexdigest()[:10]
        return f"{slug[:148]}--{digest}"
