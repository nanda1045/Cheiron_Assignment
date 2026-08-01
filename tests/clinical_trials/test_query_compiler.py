"""Tests for the allow-listed ClinicalTrials.gov query compiler."""

from cheiron.clinical_trials.query_compiler import ClinicalTrialsQueryCompiler
from cheiron.domain.enums import FilterField, FilterOperator
from cheiron.domain.plan import CohortSpec, FilterClause


def test_compiler_pushes_search_fields_and_selective_filters() -> None:
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
            FilterClause(
                field=FilterField.PHASE,
                operator=FilterOperator.IN,
                values=["Phase 2", "Phase 3"],
            ),
            FilterClause(
                field=FilterField.STUDY_TYPE,
                operator=FilterOperator.EQUALS,
                values=["Interventional"],
            ),
            FilterClause(
                field=FilterField.STATUS,
                operator=FilterOperator.IN,
                values=["Recruiting", "Not Yet Recruiting"],
            ),
        ],
    )

    compiled = ClinicalTrialsQueryCompiler().compile(cohort)

    assert compiled.params["query.cond"] == "Melanoma"
    assert compiled.params["query.intr"] == '"Pembrolizumab" OR "Nivolumab"'
    assert compiled.params["filter.overallStatus"] == "RECRUITING|NOT_YET_RECRUITING"
    assert compiled.params["query.term"] == (
        "AREA[StartDate]RANGE[01/01/2015, MAX] AND "
        "(AREA[Phase]PHASE2 OR AREA[Phase]PHASE3) AND "
        "AREA[StudyType]INTERVENTIONAL"
    )
    assert compiled.params["pageSize"] == "1000"
    assert compiled.params["countTotal"] == "true"
    assert compiled.post_filters == ()


def test_compiler_pushes_each_supported_start_year_operator() -> None:
    expected_terms = {
        FilterOperator.GREATER_THAN_OR_EQUAL: "AREA[StartDate]RANGE[01/01/2020, MAX]",
        FilterOperator.LESS_THAN_OR_EQUAL: "AREA[StartDate]RANGE[MIN, 12/31/2020]",
        FilterOperator.BETWEEN: "AREA[StartDate]RANGE[01/01/2020, 12/31/2022]",
        FilterOperator.EQUALS: "AREA[StartDate]RANGE[01/01/2020, 12/31/2020]",
        FilterOperator.IN: (
            "(AREA[StartDate]RANGE[01/01/2020, 12/31/2020] OR "
            "AREA[StartDate]RANGE[01/01/2022, 12/31/2022])"
        ),
    }

    for operator, expected in expected_terms.items():
        values = [2020, 2022] if operator in {FilterOperator.BETWEEN, FilterOperator.IN} else [2020]
        cohort = CohortSpec(
            id=f"year-{operator.value}",
            label="Year filter",
            filters=[
                FilterClause(
                    field=FilterField.START_YEAR,
                    operator=operator,
                    values=values,
                )
            ],
        )

        compiled = ClinicalTrialsQueryCompiler().compile(cohort)

        assert compiled.params["query.term"] == expected
        assert compiled.post_filters == ()


def test_compiler_keeps_unsafe_or_unsupported_filters_local() -> None:
    phase_contains = FilterClause(
        field=FilterField.PHASE,
        operator=FilterOperator.CONTAINS,
        values=["Phase 1"],
    )
    enrollment_filter = FilterClause(
        field=FilterField.ENROLLMENT,
        operator=FilterOperator.GREATER_THAN_OR_EQUAL,
        values=[100],
    )
    cohort = CohortSpec(
        id="local-only",
        label="Local filters",
        filters=[phase_contains, enrollment_filter],
    )

    compiled = ClinicalTrialsQueryCompiler().compile(cohort)

    assert "query.term" not in compiled.params
    assert "filter.overallStatus" not in compiled.params
    assert compiled.post_filters == (phase_contains, enrollment_filter)


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
