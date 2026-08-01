"""Construct and close concrete application dependencies from settings."""

from dataclasses import dataclass

from openai import AsyncOpenAI

from cheiron.application.query_service import QueryService
from cheiron.clinical_trials.client import ClinicalTrialsClient
from cheiron.config import Settings
from cheiron.domain.request import QueryRequest
from cheiron.planning.base import Planner
from cheiron.planning.errors import PlannerConfigurationError
from cheiron.planning.guarded import GuardedPlanner
from cheiron.planning.models import PlanningResult
from cheiron.planning.openai_planner import OpenAIPlanner
from cheiron.planning.rules import RuleBasedPlanner


class UnavailableOpenAIPlanner:
    """Fail predictably when OpenAI-only mode has no configured credential."""

    async def plan(self, request: QueryRequest) -> PlanningResult:
        del request
        raise PlannerConfigurationError("OpenAI planning requires OPENAI_API_KEY")


@dataclass(slots=True)
class ApplicationRuntime:
    """Owned long-lived clients and the service composed from them."""

    query_service: QueryService
    clinical_trials: ClinicalTrialsClient
    openai_client: AsyncOpenAI | None
    effective_planner: str

    async def aclose(self) -> None:
        await self.clinical_trials.aclose()
        if self.openai_client is not None:
            await self.openai_client.close()


def build_runtime(settings: Settings) -> ApplicationRuntime:
    """Build the configured provider graph without making network requests."""

    rules = RuleBasedPlanner()
    planner: Planner
    openai_client: AsyncOpenAI | None = None
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )

    if settings.planner_provider == "rules":
        planner = rules
        effective_planner = "rules"
    elif api_key is None:
        if settings.planner_provider == "openai":
            planner = UnavailableOpenAIPlanner()
            effective_planner = "unavailable"
        else:
            planner = rules
            effective_planner = "rules"
    else:
        openai_client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.request_timeout_seconds,
        )
        openai_planner = OpenAIPlanner(
            openai_client,
            model=settings.openai_model,
        )
        if settings.planner_provider == "openai":
            planner = openai_planner
            effective_planner = "openai"
        else:
            planner = GuardedPlanner(openai_planner, rules)
            effective_planner = "openai_with_rules_fallback"

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
        openai_client=openai_client,
        effective_planner=effective_planner,
    )
