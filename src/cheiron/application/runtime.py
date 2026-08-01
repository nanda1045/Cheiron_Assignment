"""Construct and close concrete application dependencies from settings."""

from dataclasses import dataclass

from anthropic import AsyncAnthropic

from cheiron.application.query_service import QueryService
from cheiron.clinical_trials.client import ClinicalTrialsClient
from cheiron.config import Settings
from cheiron.domain.request import QueryRequest
from cheiron.planning.base import Planner
from cheiron.planning.claude_planner import ClaudePlanner
from cheiron.planning.errors import PlannerConfigurationError
from cheiron.planning.guarded import GuardedPlanner
from cheiron.planning.models import PlanningResult
from cheiron.planning.rules import RuleBasedPlanner


class UnavailableClaudePlanner:
    """Fail predictably when Anthropic-only mode has no configured credential."""

    async def plan(self, request: QueryRequest) -> PlanningResult:
        del request
        raise PlannerConfigurationError("Claude planning requires ANTHROPIC_API_KEY")


@dataclass(slots=True)
class ApplicationRuntime:
    """Owned long-lived clients and the service composed from them."""

    query_service: QueryService
    clinical_trials: ClinicalTrialsClient
    anthropic_client: AsyncAnthropic | None
    effective_planner: str

    async def aclose(self) -> None:
        await self.clinical_trials.aclose()
        if self.anthropic_client is not None:
            await self.anthropic_client.close()


def build_runtime(settings: Settings) -> ApplicationRuntime:
    """Build the configured provider graph without making network requests."""

    rules = RuleBasedPlanner()
    planner: Planner
    anthropic_client: AsyncAnthropic | None = None
    api_key = (
        settings.anthropic_api_key.get_secret_value()
        if settings.anthropic_api_key is not None
        else None
    )

    if settings.planner_provider == "rules":
        planner = rules
        effective_planner = "rules"
    elif api_key is None:
        if settings.planner_provider == "anthropic":
            planner = UnavailableClaudePlanner()
            effective_planner = "unavailable"
        else:
            planner = rules
            effective_planner = "rules"
    else:
        anthropic_client = AsyncAnthropic(
            api_key=api_key,
            timeout=settings.request_timeout_seconds,
        )
        claude_planner = ClaudePlanner(
            anthropic_client,
            model=settings.anthropic_model,
        )
        if settings.planner_provider == "anthropic":
            planner = claude_planner
            effective_planner = "claude"
        else:
            planner = GuardedPlanner(claude_planner, rules)
            effective_planner = "claude_with_rules_fallback"

    clinical_trials = ClinicalTrialsClient(
        base_url=settings.clinical_trials_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )
    service = QueryService(
        planner=planner,
        clinical_trials=clinical_trials,
        source_endpoint=settings.clinical_trials_base_url,
        max_studies=settings.max_studies,
    )
    return ApplicationRuntime(
        query_service=service,
        clinical_trials=clinical_trials,
        anthropic_client=anthropic_client,
        effective_planner=effective_planner,
    )
