"""Internal immutable analysis results before public response serialization."""

from dataclasses import dataclass

from cheiron.clinical_trials.models import TrialRecord
from cheiron.domain.visualization import ScalarValue


@dataclass(frozen=True, slots=True)
class AnalysisDatum:
    id: str
    values: dict[str, ScalarValue]
    contributors: tuple[TrialRecord, ...]
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TabularAnalysis:
    records: tuple[AnalysisDatum, ...]
    measure_field: str
    dimension_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NetworkNodeAnalysis:
    id: str
    label: str
    entity_type: str
    value: int
    contributors: tuple[TrialRecord, ...]
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NetworkEdgeAnalysis:
    id: str
    source: str
    target: str
    weight: int
    contributors: tuple[TrialRecord, ...]
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NetworkAnalysis:
    nodes: tuple[NetworkNodeAnalysis, ...]
    edges: tuple[NetworkEdgeAnalysis, ...]


type AnalysisResult = TabularAnalysis | NetworkAnalysis
