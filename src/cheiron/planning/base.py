"""Shared interface implemented by all semantic planners."""

from typing import Protocol

from cheiron.domain.request import QueryRequest
from cheiron.planning.models import PlanningResult


class Planner(Protocol):
    """Convert a public query into a validated deterministic analysis plan."""

    async def plan(self, request: QueryRequest) -> PlanningResult:
        """Return a plan or raise a typed planning failure."""

        ...
