# Cheiron

Cheiron is an AI-assisted backend that converts natural-language questions about
clinical trials into validated, frontend-renderable visualization specifications
backed by the ClinicalTrials.gov API.

The project is under active development. Full setup instructions, API contracts,
example runs, design decisions, and limitations will be added as features land.

## Development

Requirements:

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 LTS for the optional demo frontend

Copy `.env.example` to `.env` and add an OpenAI API key. The key is used only by
the semantic planner; retrieved ClinicalTrials.gov study records are processed
deterministically inside Cheiron and are not sent to OpenAI.

```dotenv
CHEIRON_PLANNER_PROVIDER=openai
CHEIRON_OPENAI_MODEL=gpt-5.4-mini
OPENAI_API_KEY=your-key-here
```

```bash
uv sync --all-extras
uv run uvicorn cheiron.main:app --reload
```

The API is available at `http://localhost:8000`, with interactive documentation at
`http://localhost:8000/docs`.

In a second terminal, start the demo frontend. Its development server proxies API
requests to the backend at `http://127.0.0.1:8000`.

```bash
cd frontend
nvm use
npm ci
npm run dev
```

The demo is available at `http://localhost:5173`.

Run the local quality gates with:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Run the live semantic planner benchmark separately because it consumes OpenAI
API credits:

```bash
uv run python scripts/run_planner_evals.py --min-pass-rate 0.90
```

The curated benchmark checks route selection, analysis intent, visualization,
dimensions, measures, cohorts, relationships, and required or forbidden filters.
The reviewed `gpt-5.4-mini` baseline passed 16/16 cases and 130/130 semantic
assertions; see [`evals/README.md`](evals/README.md) for scope and limitations.

Run exact-value and datum-level provenance checks over frozen source fixtures:

```bash
uv run python scripts/run_evidence_evals.py
```

Run the frontend quality gates with:

```bash
cd frontend
npm run lint
npm test
npm run build
```
