"""Convert deterministic analysis results into Cheiron Visualization Specification v1."""

from cheiron.analysis.models import NetworkAnalysis, TabularAnalysis
from cheiron.domain.enums import DataType, DimensionField, VisualizationType
from cheiron.domain.plan import AnalysisPlan
from cheiron.domain.visualization import (
    CartesianEncoding,
    CartesianVisualizationSpec,
    ChannelEncoding,
    NetworkData,
    NetworkEdge,
    NetworkNode,
    NetworkVisualizationSpec,
    TabularData,
    TabularDatum,
    VisualizationSpec,
)
from cheiron.provenance.builder import ProvenanceCatalog


class VisualizationBuilder:
    """Build a fully explicit renderer contract and attach per-datum evidence references."""

    def build(
        self,
        plan: AnalysisPlan,
        result: TabularAnalysis | NetworkAnalysis,
        provenance: ProvenanceCatalog,
    ) -> VisualizationSpec:
        if isinstance(result, NetworkAnalysis):
            return self._network(plan, result, provenance)
        return self._cartesian(plan, result, provenance)

    def _cartesian(
        self,
        plan: AnalysisPlan,
        result: TabularAnalysis,
        provenance: ProvenanceCatalog,
    ) -> CartesianVisualizationSpec:
        x_field = result.dimension_fields[0]
        y_field = result.measure_field
        if plan.visualization is VisualizationType.SCATTER_PLOT:
            x_field = "start_year"
            y_field = "enrollment"

        color_field = "cohort" if "cohort" in result.dimension_fields else None
        if color_field is None and len(result.dimension_fields) > 1:
            color_field = result.dimension_fields[1]

        encoding = CartesianEncoding(
            x=self._channel(x_field),
            y=self._channel(y_field, plan.measure.unit),
            color=self._channel(color_field) if color_field else None,
        )
        data = TabularData(
            records=[
                TabularDatum(
                    id=datum.id,
                    values=datum.values,
                    citation_ids=provenance.references_for(
                        datum.id,
                        datum.contributors,
                        datum.evidence_paths,
                    ),
                )
                for datum in result.records
            ]
        )
        return CartesianVisualizationSpec(
            type=plan.visualization,
            title=self._title(plan, result.dimension_fields, result.measure_field),
            description=plan.interpretation,
            encoding=encoding,
            data=data,
        )

    def _network(
        self,
        plan: AnalysisPlan,
        result: NetworkAnalysis,
        provenance: ProvenanceCatalog,
    ) -> NetworkVisualizationSpec:
        nodes = [
            NetworkNode(
                id=node.id,
                label=node.label,
                entity_type=node.entity_type,
                value=node.value,
                citation_ids=provenance.references_for(
                    f"node-{node.id}",
                    node.contributors,
                    node.evidence_paths,
                ),
            )
            for node in result.nodes
        ]
        edges = [
            NetworkEdge(
                id=edge.id,
                source=edge.source,
                target=edge.target,
                weight=edge.weight,
                citation_ids=provenance.references_for(
                    f"edge-{edge.id}",
                    edge.contributors,
                    edge.evidence_paths,
                ),
            )
            for edge in result.edges
        ]
        return NetworkVisualizationSpec(
            type=VisualizationType.NETWORK_GRAPH,
            title=self._network_title(plan),
            description=plan.interpretation,
            data=NetworkData(nodes=nodes, edges=edges),
        )

    @staticmethod
    def _channel(field: str, unit: str | None = None) -> ChannelEncoding:
        data_types = {
            "start_year": DataType.TEMPORAL,
            "phase": DataType.ORDINAL,
            "bin": DataType.ORDINAL,
            "trial_count": DataType.QUANTITATIVE,
            "enrollment": DataType.QUANTITATIVE,
            "enrollment_sum": DataType.QUANTITATIVE,
            "average_enrollment": DataType.QUANTITATIVE,
        }
        titles = {
            "start_year": "Start year",
            "phase": "Phase",
            "intervention_type": "Intervention type",
            "sponsor_class": "Sponsor class",
            "country": "Country",
            "cohort": "Cohort",
            "bin": "Enrollment range",
            "trial_count": "Unique trials",
            "enrollment": "Enrollment",
            "enrollment_sum": "Total enrollment",
            "average_enrollment": "Average enrollment",
        }
        return ChannelEncoding(
            field=field,
            data_type=data_types.get(field, DataType.NOMINAL),
            title=titles.get(field, field.replace("_", " ").title()),
            unit=unit,
        )

    @staticmethod
    def _title(
        plan: AnalysisPlan,
        dimensions: tuple[str, ...],
        measure_field: str,
    ) -> str:
        measure = VisualizationBuilder._channel(measure_field).title
        dimension_names = [
            VisualizationBuilder._channel(dimension).title
            for dimension in dimensions
            if dimension != DimensionField.COHORT.value
        ]
        title = f"{measure} by {' and '.join(dimension_names)}"
        if len(plan.cohorts) > 1:
            title += f": {' vs '.join(cohort.label for cohort in plan.cohorts)}"
        return title

    @staticmethod
    def _network_title(plan: AnalysisPlan) -> str:
        assert plan.relationship is not None
        source = plan.relationship.source.value.replace("_", " ").title()
        target = plan.relationship.target.value.replace("_", " ").title()
        return f"{source} ↔ {target} trial relationships"
