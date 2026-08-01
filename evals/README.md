# Planner evaluation

`planner_cases.json` is a curated semantic benchmark for the bounded planning
contract. Each case asserts only stable properties that affect retrieval and
analysis—route, intent, chart, dimensions, measure, cohorts, relationships, and
filters. Generated titles, explanations, and IDs are deliberately not graded.

Run a cheap smoke test before the complete benchmark:

```bash
uv run python scripts/run_planner_evals.py --limit 3
```

Run all cases and require at least 90% case accuracy:

```bash
uv run python scripts/run_planner_evals.py --min-pass-rate 0.90
```

Select individual regression cases with repeated `--case` flags:

```bash
uv run python scripts/run_planner_evals.py \
  --case annual-phase-three-trend \
  --case structured-filters-authoritative
```

Reports are written to `evals/reports/` and excluded from Git because they
contain timestamps, latency, and model-dependent observations. The runner exits
nonzero when the requested accuracy threshold is missed, so it can also serve as
an explicitly invoked release gate. Live evals incur API usage and are kept
separate from the deterministic unit-test suite.

`baselines/gpt-5.4-mini.json` records a reviewed full-suite run together with the
dataset SHA-256 fingerprint. It is evidence from one live run, not a guarantee
that a nondeterministic provider will reproduce the same result indefinitely.
