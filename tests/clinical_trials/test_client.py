"""Tests for complete, guarded ClinicalTrials.gov pagination."""

from typing import Any

import httpx
import pytest
import respx

from cheiron.clinical_trials.client import ClinicalTrialsClient
from cheiron.clinical_trials.errors import PaginationError, QueryTooBroadError
from cheiron.clinical_trials.query_compiler import CompiledQuery

BASE_URL = "https://clinicaltrials.gov/api/v2"


def compiled_query() -> CompiledQuery:
    return CompiledQuery(
        cohort_id="melanoma",
        params={"query.cond": "Melanoma", "countTotal": "true", "pageSize": "1000"},
        post_filters=(),
    )


@respx.mock
async def test_client_retrieves_every_page(
    first_page: dict[str, Any], second_page: dict[str, Any]
) -> None:
    route = respx.get(f"{BASE_URL}/studies").mock(
        side_effect=[httpx.Response(200, json=first_page), httpx.Response(200, json=second_page)]
    )
    async with ClinicalTrialsClient(
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_wait_seconds=0,
    ) as client:
        result = await client.fetch_studies(compiled_query(), max_studies=10)

    assert result.matched_count == 2
    assert result.pages_retrieved == 2
    assert len(result.studies) == 2
    assert route.calls[1].request.url.params["pageToken"] == "token-2"


@respx.mock
async def test_client_does_not_override_httpx_user_agent(first_page: dict[str, Any]) -> None:
    """ClinicalTrials.gov rejects explicit custom user agents with HTTP 403."""

    single_page = {**first_page, "nextPageToken": None, "totalCount": 1}
    route = respx.get(f"{BASE_URL}/studies").mock(
        return_value=httpx.Response(200, json=single_page)
    )

    async with ClinicalTrialsClient(
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_wait_seconds=0,
    ) as client:
        await client.fetch_studies(compiled_query(), max_studies=10)

    assert route.calls[0].request.headers["user-agent"].startswith("python-httpx/")


@respx.mock
async def test_client_rejects_query_above_correctness_limit(first_page: dict[str, Any]) -> None:
    first_page["totalCount"] = 50_000
    respx.get(f"{BASE_URL}/studies").mock(return_value=httpx.Response(200, json=first_page))

    async with ClinicalTrialsClient(
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_wait_seconds=0,
    ) as client:
        with pytest.raises(QueryTooBroadError) as error:
            await client.fetch_studies(compiled_query(), max_studies=20_000)

    assert error.value.matched_count == 50_000


@respx.mock
async def test_client_rejects_repeated_page_token(first_page: dict[str, Any]) -> None:
    repeated_page = {**first_page, "totalCount": 3}
    respx.get(f"{BASE_URL}/studies").mock(
        side_effect=[
            httpx.Response(200, json=repeated_page),
            httpx.Response(200, json=repeated_page),
        ]
    )

    async with ClinicalTrialsClient(
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_wait_seconds=0,
    ) as client:
        with pytest.raises(PaginationError, match="repeated page token"):
            await client.fetch_studies(compiled_query(), max_studies=10)


@respx.mock
async def test_client_retries_transient_server_error(first_page: dict[str, Any]) -> None:
    single_page = {**first_page, "nextPageToken": None, "totalCount": 1}
    route = respx.get(f"{BASE_URL}/studies").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=single_page)]
    )

    async with ClinicalTrialsClient(
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_wait_seconds=0,
    ) as client:
        result = await client.fetch_studies(compiled_query(), max_studies=10)

    assert result.matched_count == 1
    assert route.call_count == 2


@respx.mock
async def test_client_parses_dataset_version() -> None:
    respx.get(f"{BASE_URL}/version").mock(
        return_value=httpx.Response(
            200,
            json={"apiVersion": "2.0.5", "dataTimestamp": "2026-07-31T09:00:04"},
        )
    )

    async with ClinicalTrialsClient(
        base_url=BASE_URL,
        timeout_seconds=5,
        retry_wait_seconds=0,
    ) as client:
        version = await client.get_version()

    assert version.api_version == "2.0.5"
    assert version.data_timestamp.year == 2026
