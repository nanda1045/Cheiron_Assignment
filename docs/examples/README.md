# Captured API examples

These files are complete responses returned by `POST /v1/query` against the live
ClinicalTrials.gov API. They were captured on 2026-08-01 UTC using the OpenAI
`gpt-5.4-mini` planner and ClinicalTrials.gov API version `2.0.5`.

The capture requests set `include_citations=false` so reviewers can inspect the
entire response without hundreds of repeated evidence objects. The analytical
values do not change when citations are disabled; that invariant is enforced by
the deterministic evidence evaluation suite. Citation-enabled UI runs of the
same queries produced the study and citation counts summarized in the root
README.

| File | Output |
| --- | --- |
| [`bar-chart.json`](bar-chart.json) | Bar chart: trials by phase |
| [`grouped-bar-chart.json`](grouped-bar-chart.json) | Grouped bar chart: intervention cohorts by phase |
| [`time-series.json`](time-series.json) | Time series: trial starts by year |
| [`histogram.json`](histogram.json) | Histogram: planned-enrollment distribution |
| [`scatter-plot.json`](scatter-plot.json) | Scatter plot: start year versus enrollment |
| [`network-graph.json`](network-graph.json) | Network: lead sponsors and interventions |
| [`scalar-answer.json`](scalar-answer.json) | Non-visual deterministic trial count |

Because ClinicalTrials.gov is live, rerunning a query later may produce different
counts. Each response therefore includes source and retrieval timestamps,
record-completeness metadata, the executed semantic plan and a request ID.
