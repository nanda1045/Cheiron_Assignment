"""Normalized trial fixtures shared by deterministic analysis tests."""

from typing import Any

import pytest

from cheiron.clinical_trials.models import TrialRecord
from cheiron.clinical_trials.normalizer import TrialNormalizer


@pytest.fixture
def normalized_trials(
    first_page: dict[str, Any],
    second_page: dict[str, Any],
) -> tuple[TrialRecord, ...]:
    studies = [*first_page["studies"], *second_page["studies"]]
    return TrialNormalizer().normalize_many(studies).records
