"""Typed failures raised at the ClinicalTrials.gov integration boundary."""


class ClinicalTrialsError(Exception):
    """Base class for recoverable upstream-integration failures."""


class ClinicalTrialsTransientError(ClinicalTrialsError):
    """A transport or upstream failure that can safely be retried."""


class ClinicalTrialsRequestError(ClinicalTrialsError):
    """The compiled query was rejected by the upstream API."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class ClinicalTrialsResponseError(ClinicalTrialsError):
    """The upstream response did not satisfy the documented response contract."""


class QueryTooBroadError(ClinicalTrialsError):
    """The matching population exceeds the configured correctness guard."""

    def __init__(self, matched_count: int, max_studies: int) -> None:
        self.matched_count = matched_count
        self.max_studies = max_studies
        super().__init__(
            f"query matched {matched_count} studies, exceeding the limit of {max_studies}"
        )


class PaginationError(ClinicalTrialsError):
    """Pagination could not prove that the entire result set was retrieved."""


class NormalizationError(ClinicalTrialsError):
    """A study cannot be safely identified or normalized."""
