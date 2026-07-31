"""Failures raised when a validated plan cannot be executed safely."""


class AnalysisError(Exception):
    """Base class for deterministic analysis failures."""


class UnsupportedAnalysisError(AnalysisError):
    """The requested plan shape is outside the implemented analysis grammar."""


class MissingCohortError(AnalysisError):
    """The executor did not receive records for a planned cohort."""
