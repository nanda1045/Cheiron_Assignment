"""Validation tests for frontend-renderable visualization contracts."""

import pytest
from pydantic import TypeAdapter, ValidationError

from cheiron.domain.enums import DataType, VisualizationType
from cheiron.domain.visualization import (
    CartesianEncoding,
    ChannelEncoding,
    NetworkData,
    NetworkEdge,
    NetworkNode,
    VisualizationSpec,
)


def test_visualization_union_rejects_network_payload_for_bar_chart() -> None:
    adapter = TypeAdapter(VisualizationSpec)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "type": "bar_chart",
                "title": "Trials by phase",
                "description": "Unique trials grouped by phase.",
                "encoding": {
                    "x": {"field": "phase", "data_type": "ordinal", "title": "Phase"},
                    "y": {
                        "field": "trial_count",
                        "data_type": "quantitative",
                        "title": "Trials",
                    },
                },
                "data": {"kind": "network", "nodes": [], "edges": []},
            }
        )


def test_network_rejects_missing_edge_endpoint() -> None:
    with pytest.raises(ValidationError, match="missing nodes"):
        NetworkData(
            nodes=[NetworkNode(id="sponsor-a", label="A", entity_type="sponsor", value=1)],
            edges=[NetworkEdge(id="a-b", source="sponsor-a", target="drug-b", weight=1)],
        )


def test_cartesian_encoding_is_explicit() -> None:
    encoding = CartesianEncoding(
        x=ChannelEncoding(field="phase", data_type=DataType.ORDINAL, title="Phase"),
        y=ChannelEncoding(
            field="trial_count",
            data_type=DataType.QUANTITATIVE,
            title="Trials",
            unit="trials",
        ),
    )

    assert encoding.y.unit == "trials"
    assert VisualizationType.BAR_CHART.value == "bar_chart"
