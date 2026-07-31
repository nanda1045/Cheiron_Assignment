"""Shared domain-model configuration."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base class for externally visible, strictly shaped domain objects."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )
