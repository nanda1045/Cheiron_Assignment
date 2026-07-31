"""Tests for deterministic charts and datum-level source traceability."""

from cheiron.analysis.pipeline import AnalysisPipeline
from cheiron.clinical_trials.models import TrialRecord
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
from cheiron.domain.plan import (
    AnalysisPlan,
    CohortSpec,
    DimensionSpec,
    FilterClause,
    MeasureSpec,
    RelationshipSpec,
)
from cheiron.domain.visualization import (
    CartesianVisualizationSpec,
    NetworkVisualizationSpec,
)


def trial_count_measure() -> MeasureSpec:
    return MeasureSpec(
        field=MeasureField.NCT_ID,
        aggregation=Aggregation.COUNT_DISTINCT,
        label="Trial count",
        unit="trials",
    )


def test_phase_distribution_has_one_citation_per_counted_trial(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.DISTRIBUTION,
        interpretation="Count unique melanoma studies in each trial phase.",
        cohorts=[
            CohortSpec(
                id="melanoma",
                label="Melanoma",
                filters=[
                    FilterClause(
                        field=FilterField.CONDITION,
                        operator=FilterOperator.CONTAINS,
                        values=["Melanoma"],
                    )
                ],
            )
        ],
        dimensions=[DimensionSpec(field=DimensionField.PHASE)],
        measure=trial_count_measure(),
        visualization=VisualizationType.BAR_CHART,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"melanoma": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    assert [datum.values["phase"] for datum in artifacts.visualization.data.records] == [
        "Phase 2",
        "Phase 3",
    ]
    for datum in artifacts.visualization.data.records:
        assert len(datum.citation_ids) == datum.values["trial_count"]
    assert len(artifacts.citations) == 2

    phase_three_datum = artifacts.visualization.data.records[1]
    phase_three_citation = artifacts.citations[phase_three_datum.citation_ids[0]]
    assert phase_three_citation.nct_id == "NCT00000001"
    assert {evidence.field_path: evidence.value for evidence in phase_three_citation.evidence} == {
        "protocolSection.conditionsModule.conditions": ["Melanoma"],
        "protocolSection.designModule.phases": ["PHASE3"],
    }


def test_country_counts_distinct_trials_not_location_rows(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.GEOGRAPHIC,
        interpretation="Rank countries by unique trial count.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        dimensions=[DimensionSpec(field=DimensionField.COUNTRY)],
        measure=trial_count_measure(),
        visualization=VisualizationType.BAR_CHART,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    by_country = {
        datum.values["country"]: datum.values["trial_count"]
        for datum in artifacts.visualization.data.records
    }
    assert by_country == {"United States": 2, "Canada": 1}


def test_comparison_adds_explicit_cohort_series(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.COMPARISON,
        interpretation="Compare phases for pembrolizumab and nivolumab.",
        cohorts=[
            CohortSpec(
                id="pembrolizumab",
                label="Pembrolizumab",
                filters=[
                    FilterClause(
                        field=FilterField.INTERVENTION,
                        operator=FilterOperator.CONTAINS,
                        values=["Pembrolizumab"],
                    )
                ],
            ),
            CohortSpec(
                id="nivolumab",
                label="Nivolumab",
                filters=[
                    FilterClause(
                        field=FilterField.INTERVENTION,
                        operator=FilterOperator.CONTAINS,
                        values=["Nivolumab"],
                    )
                ],
            ),
        ],
        dimensions=[DimensionSpec(field=DimensionField.PHASE)],
        measure=trial_count_measure(),
        visualization=VisualizationType.GROUPED_BAR_CHART,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {
            "pembrolizumab": normalized_trials,
            "nivolumab": normalized_trials,
        },
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    values = [datum.values for datum in artifacts.visualization.data.records]
    assert values == [
        {"phase": "Phase 2", "cohort": "Nivolumab", "trial_count": 1},
        {"phase": "Phase 3", "cohort": "Pembrolizumab", "trial_count": 1},
    ]
    assert artifacts.visualization.encoding.color is not None
    assert artifacts.visualization.encoding.color.field == "cohort"


def test_network_weights_and_nodes_are_fully_traceable(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.RELATIONSHIP,
        interpretation="Connect lead sponsors to interventions in their trials.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        measure=trial_count_measure(),
        visualization=VisualizationType.NETWORK_GRAPH,
        relationship=RelationshipSpec(
            source=RelationshipEntity.SPONSOR,
            target=RelationshipEntity.INTERVENTION,
        ),
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, NetworkVisualizationSpec)
    assert len(artifacts.visualization.data.edges) == 2
    for edge in artifacts.visualization.data.edges:
        assert len(edge.citation_ids) == edge.weight
    for node in artifacts.visualization.data.nodes:
        assert len(node.citation_ids) == node.value


def test_network_node_limit_keeps_complete_edges(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.RELATIONSHIP,
        interpretation="Show the strongest sponsor to intervention relationship.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        measure=trial_count_measure(),
        visualization=VisualizationType.NETWORK_GRAPH,
        relationship=RelationshipSpec(
            source=RelationshipEntity.SPONSOR,
            target=RelationshipEntity.INTERVENTION,
            max_nodes=2,
        ),
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, NetworkVisualizationSpec)
    assert len(artifacts.visualization.data.nodes) == 2
    assert len(artifacts.visualization.data.edges) == 1


def test_citations_can_be_disabled_without_changing_values(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.DISTRIBUTION,
        interpretation="Count unique trials by phase.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        dimensions=[DimensionSpec(field=DimensionField.PHASE)],
        measure=trial_count_measure(),
        visualization=VisualizationType.BAR_CHART,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=False,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    assert artifacts.citations == {}
    assert all(not datum.citation_ids for datum in artifacts.visualization.data.records)


def test_histogram_uses_deterministic_enrollment_bins(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.HISTOGRAM,
        interpretation="Show the distribution of planned enrollment.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        dimensions=[DimensionSpec(field=DimensionField.ENROLLMENT)],
        measure=trial_count_measure(),
        visualization=VisualizationType.HISTOGRAM,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    assert (
        sum(int(datum.values["trial_count"]) for datum in artifacts.visualization.data.records) == 2
    )


def test_time_series_is_sorted_and_counts_distinct_trials_by_year(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.TREND,
        interpretation="Show unique trial starts by year.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        dimensions=[DimensionSpec(field=DimensionField.START_YEAR)],
        measure=trial_count_measure(),
        visualization=VisualizationType.TIME_SERIES,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    assert [datum.values for datum in artifacts.visualization.data.records] == [
        {"start_year": 2019, "trial_count": 1},
        {"start_year": 2021, "trial_count": 1},
    ]
    assert artifacts.visualization.encoding.x.data_type.value == "temporal"


def test_scatter_preserves_one_traceable_point_per_trial(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = AnalysisPlan(
        intent=AnalysisIntent.SCATTER,
        interpretation="Compare trial start year with planned enrollment.",
        cohorts=[CohortSpec(id="all", label="All trials")],
        dimensions=[DimensionSpec(field=DimensionField.START_YEAR)],
        measure=MeasureSpec(
            field=MeasureField.ENROLLMENT,
            aggregation=Aggregation.NONE,
            label="Enrollment",
            unit="participants",
        ),
        visualization=VisualizationType.SCATTER_PLOT,
    )

    artifacts = AnalysisPipeline().run(
        plan,
        {"all": normalized_trials},
        include_citations=True,
    )

    assert isinstance(artifacts.visualization, CartesianVisualizationSpec)
    assert [datum.values for datum in artifacts.visualization.data.records] == [
        {"nct_id": "NCT00000002", "start_year": 2019, "enrollment": 80},
        {"nct_id": "NCT00000001", "start_year": 2021, "enrollment": 300},
    ]
    assert all(len(datum.citation_ids) == 1 for datum in artifacts.visualization.data.records)
