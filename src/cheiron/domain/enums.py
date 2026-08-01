"""Closed vocabularies used by requests, plans, and visualizations."""

from enum import StrEnum


class TrialPhase(StrEnum):
    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1 = "PHASE1"
    PHASE2 = "PHASE2"
    PHASE3 = "PHASE3"
    PHASE4 = "PHASE4"
    NOT_APPLICABLE = "NA"


class RecruitmentStatus(StrEnum):
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    COMPLETED = "COMPLETED"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    RECRUITING = "RECRUITING"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class StudyType(StrEnum):
    INTERVENTIONAL = "INTERVENTIONAL"
    OBSERVATIONAL = "OBSERVATIONAL"
    EXPANDED_ACCESS = "EXPANDED_ACCESS"


class SponsorClass(StrEnum):
    NIH = "NIH"
    FEDERAL = "FED"
    OTHER_GOVERNMENT = "OTHER_GOV"
    INDIVIDUAL = "INDIV"
    INDUSTRY = "INDUSTRY"
    NETWORK = "NETWORK"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class AnalysisIntent(StrEnum):
    TREND = "trend"
    DISTRIBUTION = "distribution"
    COMPARISON = "comparison"
    GEOGRAPHIC = "geographic"
    RELATIONSHIP = "relationship"
    HISTOGRAM = "histogram"
    SCATTER = "scatter"


class FilterField(StrEnum):
    CONDITION = "condition"
    INTERVENTION = "intervention"
    PHASE = "phase"
    SPONSOR = "sponsor"
    SPONSOR_CLASS = "sponsor_class"
    COUNTRY = "country"
    STATUS = "status"
    STUDY_TYPE = "study_type"
    START_YEAR = "start_year"
    ENROLLMENT = "enrollment"


class FilterOperator(StrEnum):
    CONTAINS = "contains"
    EQUALS = "equals"
    IN = "in"
    BETWEEN = "between"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"


class DimensionField(StrEnum):
    START_YEAR = "start_year"
    PHASE = "phase"
    INTERVENTION_TYPE = "intervention_type"
    SPONSOR_CLASS = "sponsor_class"
    COUNTRY = "country"
    COHORT = "cohort"
    ENROLLMENT = "enrollment"
    SPONSOR = "sponsor"
    INTERVENTION = "intervention"


class MeasureField(StrEnum):
    NCT_ID = "nct_id"
    ENROLLMENT = "enrollment"


class Aggregation(StrEnum):
    COUNT_DISTINCT = "count_distinct"
    COUNT = "count"
    SUM = "sum"
    AVERAGE = "average"
    NONE = "none"


class TimeGranularity(StrEnum):
    YEAR = "year"
    MONTH = "month"


class RelationshipEntity(StrEnum):
    SPONSOR = "sponsor"
    INTERVENTION = "intervention"
    CONDITION = "condition"
    COUNTRY = "country"


class VisualizationType(StrEnum):
    BAR_CHART = "bar_chart"
    GROUPED_BAR_CHART = "grouped_bar_chart"
    TIME_SERIES = "time_series"
    HISTOGRAM = "histogram"
    SCATTER_PLOT = "scatter_plot"
    NETWORK_GRAPH = "network_graph"


class DataType(StrEnum):
    NOMINAL = "nominal"
    ORDINAL = "ordinal"
    QUANTITATIVE = "quantitative"
    TEMPORAL = "temporal"


class SortDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class CompletenessStatus(StrEnum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"


class PlannerMode(StrEnum):
    OPENAI = "openai"
    RULES = "rules"
