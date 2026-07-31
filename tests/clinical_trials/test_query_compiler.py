"""Tests for the allow-listed ClinicalTrials.gov query compiler."""

from cheiron.clinical_trials.query_compiler import ClinicalTrialsQueryCompiler
from cheiron.domain.enums import FilterField, FilterOperator
from cheiron.domain.plan import CohortSpec, FilterClause


def test_compiler_pushes_search_fields_and_preserves_exact_post_filters() -> None:
    cohort = CohortSpec(
        id="melanoma-drugs",
        label="Melanoma drugs",
        filters=[
            FilterClause(
                field=FilterField.CONDITION,
                operator=FilterOperator.CONTAINS,
                values=["Melanoma"],
            ),
            FilterClause(
                field=FilterField.INTERVENTION,
                operator=FilterOperator.IN,
                values=["Pembrolizumab", "Nivolumab"],
            ),
            FilterClause(
                field=FilterField.START_YEAR,
                operator=FilterOperator.GREATER_THAN_OR_EQUAL,
                values=[2015],
            ),
        ],
    )

    compiled = ClinicalTrialsQueryCompiler().compile(cohort)

    assert compiled.params["query.cond"] == "Melanoma"
    assert compiled.params["query.intr"] == '"Pembrolizumab" OR "Nivolumab"'
    assert compiled.params["pageSize"] == "1000"
    assert compiled.params["countTotal"] == "true"
    assert [post_filter.field for post_filter in compiled.post_filters] == [FilterField.START_YEAR]


def test_compiler_removes_query_language_quotes_from_values() -> None:
    cohort = CohortSpec(
        id="safe",
        label="Safe",
        filters=[
            FilterClause(
                field=FilterField.CONDITION,
                operator=FilterOperator.CONTAINS,
                values=['  Lung "Cancer"  '],
            )
        ],
    )

    compiled = ClinicalTrialsQueryCompiler().compile(cohort)

    assert compiled.params["query.cond"] == "Lung Cancer"
