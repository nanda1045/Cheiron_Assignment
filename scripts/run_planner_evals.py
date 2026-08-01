"""Run the curated planner benchmark against the configured OpenAI model."""

import argparse
import asyncio
from pathlib import Path

from openai import AsyncOpenAI

from cheiron.config import Settings
from cheiron.evaluation.planner import evaluate_planner, load_planner_cases
from cheiron.planning.openai_planner import OpenAIPlanner

DEFAULT_CASES = Path("evals/planner_cases.json")
DEFAULT_REPORT = Path("evals/reports/planner_eval_report.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model", help="Override CHEIRON_OPENAI_MODEL for this run")
    parser.add_argument("--limit", type=int, help="Run only the first N validated cases")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run a case by ID")
    parser.add_argument("--min-pass-rate", type=float, default=0.90)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.openai_api_key is None:
        raise SystemExit("OPENAI_API_KEY is required for live planner evaluations")
    if not 0 <= args.min_pass_rate <= 1:
        raise SystemExit("--min-pass-rate must be between 0 and 1")

    cases = load_planner_cases(args.cases)
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in cases if case.id in requested]
        missing = requested.difference(case.id for case in cases)
        if missing:
            raise SystemExit(f"unknown case IDs: {', '.join(sorted(missing))}")
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("no evaluation cases selected")

    model = args.model or settings.openai_model
    client = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.request_timeout_seconds,
        max_retries=1,
    )
    try:
        report = await evaluate_planner(OpenAIPlanner(client, model=model), cases, model=model)
    finally:
        await client.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"Planner eval: {report.passed_cases}/{report.total_cases} cases passed")
    print(f"Semantic checks: {report.passed_checks}/{report.total_checks} passed")
    print(f"Case pass rate: {report.pass_rate:.1%}")
    print(f"Report: {args.output}")
    for result in report.cases:
        marker = "PASS" if result.passed else "FAIL"
        print(f"[{marker}] {result.id} ({result.duration_ms}ms)")
        for check in result.checks:
            if not check.passed:
                print(
                    f"  {check.name}: expected {check.expected!r}, got {check.actual!r}"
                )
        if result.error:
            print(f"  {result.error}")
    return 0 if report.pass_rate >= args.min_pass_rate else 1


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
