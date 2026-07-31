"""Versioned frontend-renderable visualization specification."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from cheiron.domain.base import DomainModel
from cheiron.domain.enums import DataType, SortDirection, VisualizationType

type ScalarValue = str | int | float | bool | None


class ChannelEncoding(DomainModel):
    field: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    data_type: DataType
    title: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=40)
    sort: SortDirection | list[ScalarValue] | None = None


class CartesianEncoding(DomainModel):
    x: ChannelEncoding
    y: ChannelEncoding
    color: ChannelEncoding | None = None
    size: ChannelEncoding | None = None


class NetworkEncoding(DomainModel):
    node_id: str = "id"
    node_label: str = "label"
    node_group: str = "entity_type"
    node_size: str = "value"
    edge_source: str = "source"
    edge_target: str = "target"
    edge_weight: str = "weight"


class TabularDatum(DomainModel):
    id: str = Field(min_length=1, max_length=160)
    values: dict[str, ScalarValue]
    citation_ids: list[str] = Field(default_factory=list)


class TabularData(DomainModel):
    kind: Literal["tabular"] = "tabular"
    records: list[TabularDatum]


class NetworkNode(DomainModel):
    id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=40)
    value: int | float = Field(ge=0)
    citation_ids: list[str] = Field(default_factory=list)


class NetworkEdge(DomainModel):
    id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=160)
    target: str = Field(min_length=1, max_length=160)
    weight: int = Field(ge=1)
    citation_ids: list[str] = Field(default_factory=list)


class NetworkData(DomainModel):
    kind: Literal["network"] = "network"
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]

    @model_validator(mode="after")
    def validate_edge_endpoints(self) -> "NetworkData":
        node_ids = {node.id for node in self.nodes}
        invalid_edges = [
            edge.id
            for edge in self.edges
            if edge.source not in node_ids or edge.target not in node_ids
        ]
        if invalid_edges:
            raise ValueError(f"edges reference missing nodes: {', '.join(invalid_edges)}")
        return self


class CartesianVisualizationSpec(DomainModel):
    type: Literal[
        VisualizationType.BAR_CHART,
        VisualizationType.GROUPED_BAR_CHART,
        VisualizationType.TIME_SERIES,
        VisualizationType.HISTOGRAM,
        VisualizationType.SCATTER_PLOT,
    ]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    encoding: CartesianEncoding
    data: TabularData


class NetworkVisualizationSpec(DomainModel):
    type: Literal[VisualizationType.NETWORK_GRAPH]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    encoding: NetworkEncoding = Field(default_factory=NetworkEncoding)
    data: NetworkData


VisualizationSpec = Annotated[
    CartesianVisualizationSpec | NetworkVisualizationSpec,
    Field(discriminator="type"),
]
