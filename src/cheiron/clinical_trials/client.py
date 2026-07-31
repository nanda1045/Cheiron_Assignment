"""Resilient asynchronous client for the ClinicalTrials.gov v2 API."""

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt
from tenacity.wait import wait_exponential

from cheiron.clinical_trials.errors import (
    ClinicalTrialsRequestError,
    ClinicalTrialsResponseError,
    ClinicalTrialsTransientError,
    PaginationError,
    QueryTooBroadError,
)
from cheiron.clinical_trials.models import CohortRetrieval, DatasetVersion, StudyPage
from cheiron.clinical_trials.query_compiler import CompiledQuery


class ClinicalTrialsClient:
    """Retrieve complete study populations while making partial data explicit."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        retry_attempts: int = 3,
        retry_wait_seconds: float = 0.25,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._retry_attempts = retry_attempts
        self._retry_wait_seconds = retry_wait_seconds

    async def __aenter__(self) -> "ClinicalTrialsClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_version(self) -> DatasetVersion:
        payload = await self._get_json("/version")
        try:
            return DatasetVersion.model_validate(payload)
        except ValidationError as error:
            raise ClinicalTrialsResponseError("invalid /version response") from error

    async def fetch_studies(
        self,
        query: CompiledQuery,
        *,
        max_studies: int,
    ) -> CohortRetrieval:
        studies: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        pages_retrieved = 0
        matched_count: int | None = None

        while True:
            params = dict(query.params)
            if page_token is not None:
                params["pageToken"] = page_token

            payload = await self._get_json("/studies", params=params)
            try:
                page = StudyPage.model_validate(payload)
            except ValidationError as error:
                raise ClinicalTrialsResponseError("invalid /studies response") from error

            pages_retrieved += 1
            if matched_count is None:
                matched_count = page.total_count
                if matched_count is None:
                    raise ClinicalTrialsResponseError(
                        "first /studies page omitted totalCount despite countTotal=true"
                    )
                if matched_count > max_studies:
                    raise QueryTooBroadError(matched_count, max_studies)

            studies.extend(page.studies)
            if len(studies) > max_studies:
                raise PaginationError("retrieved study count exceeded the configured limit")

            page_token = page.next_page_token
            if page_token is None:
                break
            if page_token in seen_tokens:
                raise PaginationError(f"ClinicalTrials.gov repeated page token {page_token!r}")
            seen_tokens.add(page_token)

        if matched_count != len(studies):
            raise PaginationError(
                f"ClinicalTrials.gov reported {matched_count} matches but returned {len(studies)}"
            )

        return CohortRetrieval(
            cohort_id=query.cohort_id,
            studies=tuple(studies),
            matched_count=matched_count,
            pages_retrieved=pages_retrieved,
            retrieved_at=datetime.now(UTC),
            query_params=dict(query.params),
        )

    async def _get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._retry_attempts),
            wait=wait_exponential(
                multiplier=self._retry_wait_seconds,
                min=self._retry_wait_seconds,
                max=max(self._retry_wait_seconds, 2.0),
            ),
            retry=retry_if_exception_type(ClinicalTrialsTransientError),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                return await self._request_once(path, params=params)
        raise AssertionError("retry loop completed without returning or raising")

    async def _request_once(
        self,
        path: str,
        *,
        params: dict[str, str] | None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.TransportError as error:
            raise ClinicalTrialsTransientError("ClinicalTrials.gov transport failure") from error

        if response.status_code == 429 or response.status_code >= 500:
            raise ClinicalTrialsTransientError(
                f"ClinicalTrials.gov returned transient status {response.status_code}"
            )
        if response.is_error:
            raise ClinicalTrialsRequestError(
                response.status_code,
                f"ClinicalTrials.gov rejected the request with status {response.status_code}",
            )
        try:
            payload: object = response.json()
        except ValueError as error:
            raise ClinicalTrialsResponseError("ClinicalTrials.gov returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise ClinicalTrialsResponseError("ClinicalTrials.gov returned a non-object response")
        return payload
