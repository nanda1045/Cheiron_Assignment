"""Recorded ClinicalTrials.gov response fixtures shared across test packages."""

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "clinical_trials"


def load_json_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


@pytest.fixture
def first_page() -> dict[str, Any]:
    return load_json_fixture("page_1.json")


@pytest.fixture
def second_page() -> dict[str, Any]:
    return load_json_fixture("page_2.json")
