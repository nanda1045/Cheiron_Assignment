"""Run deterministic analysis and provenance evals over frozen source fixtures."""

import argparse
from pathlib import Path

from cheiron.evaluation.evidence import (
    evaluate_evidence,
    load_evidence_cases,
    load_fixture_studies,
)

DEFAULT_CASES = Path("evals/evidence_cases.json")
DEFAULT_FIXTURES = (
    Path("tests/fixtures/clinical_trials/page_1.json"),
    Path("tests/fixtures/clinical_trials/page_2.json"),
)
DEFAULT_REPORT = Path("evals/reports/evidence_eval_report.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--case", action="append", dest="case_ids", help="Run a case by ID")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_evidence_cases(args.cases)
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in cases if case.id in requested]
        missing = requested.difference(case.id for case in cases)
        if missing:
            raise SystemExit(f"unknown case IDs: {', '.join(sorted(missing))}")
    if not cases:
        raise SystemExit("no evidence evaluation cases selected")

    report = evaluate_evidence(cases, load_fixture_studies(DEFAULT_FIXTURES))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"Evidence eval: {report.passed_cases}/{report.total_cases} cases passed")
    print(f"Correctness checks: {report.passed_checks}/{report.total_checks} passed")
    print(f"Case pass rate: {report.pass_rate:.1%}")
    print(f"Report: {args.output}")
    for result in report.cases:
        marker = "PASS" if result.passed else "FAIL"
        print(f"[{marker}] {result.id} ({result.duration_ms}ms)")
        for check in result.checks:
            if not check.passed:
                print(f"  {check.name}: expected {check.expected}, got {check.actual}")
        if result.error:
            print(f"  {result.error}")
    raise SystemExit(0 if report.pass_rate == 1 else 1)


if __name__ == "__main__":
    main()
