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

```bash
uv sync --all-extras
uv run uvicorn cheiron.main:app --reload
```

The API is available at `http://localhost:8000`, with interactive documentation at
`http://localhost:8000/docs`.

Run the local quality gates with:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
