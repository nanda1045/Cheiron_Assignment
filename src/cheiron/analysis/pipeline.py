"""Application-facing deterministic analysis, visualization, and provenance pipeline."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cheiron.analysis.engine import AnalysisEngine
from cheiron.clinical_trials.models import TrialRecord
from cheiron.domain.plan import AnalysisPlan
from cheiron.domain.response import Citation
from cheiron.domain.visualization import VisualizationSpec
from cheiron.provenance.builder import ProvenanceCatalog
from cheiron.visualization.builder import VisualizationBuilder


@dataclass(frozen=True, slots=True)
class AnalysisArtifacts:
    visualization: VisualizationSpec
    citations: dict[str, Citation]
    used_nct_ids: frozenset[str]
    excluded_count: int


class AnalysisPipeline:
    """Execute a validated plan and return all public analysis artifacts."""

    def __init__(
        self,
        engine: AnalysisEngine | None = None,
        visualization_builder: VisualizationBuilder | None = None,
    ) -> None:
        self._engine = engine or AnalysisEngine()
        self._visualization_builder = visualization_builder or VisualizationBuilder()

    def run(
        self,
        plan: AnalysisPlan,
        cohort_records: Mapping[str, Iterable[TrialRecord]],
        *,
        include_citations: bool,
    ) -> AnalysisArtifacts:
        result, used_nct_ids, excluded_count = self._engine.execute(plan, cohort_records)
        provenance = ProvenanceCatalog(enabled=include_citations)
        visualization = self._visualization_builder.build(plan, result, provenance)
        return AnalysisArtifacts(
            visualization=visualization,
            citations=provenance.citations,
            used_nct_ids=used_nct_ids,
            excluded_count=excluded_count,
        )
