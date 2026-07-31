"""Narrow failover from model planning to deterministic rule planning."""

from dataclasses import replace

from cheiron.domain.request import QueryRequest
from cheiron.planning.base import Planner
from cheiron.planning.errors import OpenAIPlanningError
from cheiron.planning.models import PlanningResult


class GuardedPlanner:
    """Fallback only for expected model/API failures, never arbitrary code defects."""

    def __init__(self, primary: Planner, fallback: Planner) -> None:
        self._primary = primary
        self._fallback = fallback

    async def plan(self, request: QueryRequest) -> PlanningResult:
        try:
            return await self._primary.plan(request)
        except OpenAIPlanningError:
            result = await self._fallback.plan(request)
            return replace(
                result,
                warnings=(
                    "OpenAI planning was unavailable; the deterministic fallback was used.",
                    *result.warnings,
                ),
            )
