"""Tests for deterministic scalar answers and their exact evidence trail."""

from cheiron.analysis.answer import ScalarAnswerPipeline
from cheiron.clinical_trials.models import TrialRecord
from cheiron.domain.answer import ScalarAnswerPlan
from cheiron.domain.enums import Aggregation, FilterField, FilterOperator, MeasureField
from cheiron.domain.plan import CohortSpec, FilterClause, MeasureSpec


def answer_plan(
    *,
    field: MeasureField = MeasureField.NCT_ID,
    aggregation: Aggregation = Aggregation.COUNT_DISTINCT,
) -> ScalarAnswerPlan:
    return ScalarAnswerPlan(
        interpretation="Calculate one aggregate over matching trials.",
        cohorts=[
            CohortSpec(
                id="matching",
                label="Matching trials",
                filters=[
                    FilterClause(
                        field=FilterField.STATUS,
                        operator=FilterOperator.EQUALS,
                        values=["Recruiting"],
                    )
                ],
            )
        ],
        measure=MeasureSpec(
            field=field,
            aggregation=aggregation,
            label="Requested value",
            unit="trials" if field is MeasureField.NCT_ID else "participants",
        ),
    )


def test_scalar_count_is_filtered_worded_and_cited(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    artifacts = ScalarAnswerPipeline().run(
        answer_plan(),
        {"matching": normalized_trials},
        include_citations=True,
    )

    assert artifacts.answer.value == 1
    assert artifacts.answer.text == (
        "1 matching clinical trial was found in the source snapshot."
    )
    assert len(artifacts.answer.citation_ids) == 1
    assert len(artifacts.citations) == 1
    assert artifacts.used_nct_ids == frozenset({"NCT00000001"})
    assert artifacts.excluded_count == 1
    citation = artifacts.citations[artifacts.answer.citation_ids[0]]
    assert citation.nct_id == "NCT00000001"
    assert citation.evidence[0].field_path == "protocolSection.statusModule.overallStatus"


def test_scalar_average_uses_only_reported_enrollment(
    normalized_trials: tuple[TrialRecord, ...],
) -> None:
    plan = ScalarAnswerPlan(
        interpretation="Calculate average planned enrollment.",
        cohorts=[CohortSpec(id="matching", label="Matching trials")],
        measure=MeasureSpec(
            field=MeasureField.ENROLLMENT,
            aggregation=Aggregation.AVERAGE,
            label="Average planned enrollment",
            unit="participants",
        ),
    )

    artifacts = ScalarAnswerPipeline().run(
        plan,
        {"matching": normalized_trials},
        include_citations=False,
    )

    assert artifacts.answer.value == 190.0
    assert artifacts.answer.text.startswith("Average planned enrollment is 190.00 participants")
    assert artifacts.answer.citation_ids == []
    assert artifacts.citations == {}
