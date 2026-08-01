"""Tests for exact-value and datum-level provenance evaluation."""

from pathlib import Path

from cheiron.evaluation.evidence import (
    evaluate_evidence,
    load_evidence_cases,
    load_fixture_studies,
)

FIXTURES = (
    Path("tests/fixtures/clinical_trials/page_1.json"),
    Path("tests/fixtures/clinical_trials/page_2.json"),
)


def test_curated_evidence_dataset_passes_all_deterministic_checks() -> None:
    cases = load_evidence_cases(Path("evals/evidence_cases.json"))
    studies = load_fixture_studies(FIXTURES)

    report = evaluate_evidence(cases, studies)

    assert len(cases) == 8
    assert report.fixture_studies == 2
    assert report.normalized_records == 2
    assert report.normalization_excluded == 0
    assert report.pass_rate == 1
    assert report.check_pass_rate == 1
    assert report.total_checks >= 100


def test_wrong_expected_value_is_reported_without_hiding_actual_output() -> None:
    case = load_evidence_cases(Path("evals/evidence_cases.json"))[0]
    assert case.expected.tabular_values is not None
    case.expected.tabular_values[0]["trial_count"] = 99

    report = evaluate_evidence([case], load_fixture_studies(FIXTURES))

    assert report.pass_rate == 0
    failure = next(check for check in report.cases[0].checks if not check.passed)
    assert failure.name == "tabular_values"
    assert "99" in failure.expected
    assert "1" in failure.actual


def test_citation_control_case_proves_values_without_source_references() -> None:
    cases = load_evidence_cases(Path("evals/evidence_cases.json"))
    case = next(item for item in cases if item.id == "citations-disabled-value-invariance")

    report = evaluate_evidence([case], load_fixture_studies(FIXTURES))

    assert report.pass_rate == 1
    checks = {check.name: check for check in report.cases[0].checks}
    assert checks["citations_disabled_catalog"].passed is True
    assert checks["citations_disabled_references"].passed is True
