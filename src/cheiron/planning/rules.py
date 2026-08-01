"""Deterministic fallback planner for common clinical-trial questions."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from cheiron.domain.answer import ScalarAnswerPlan
from cheiron.domain.enums import (
    Aggregation,
    AnalysisIntent,
    DimensionField,
    FilterField,
    FilterOperator,
    MeasureField,
    PlannerMode,
    RelationshipEntity,
    SortDirection,
    VisualizationType,
)
from cheiron.domain.plan import (
    AnalysisPlan,
    CohortSpec,
    DimensionSpec,
    FilterClause,
    MeasureSpec,
    RelationshipSpec,
    SortSpec,
)
from cheiron.domain.request import QueryFilters, QueryRequest
from cheiron.planning.errors import ClarificationNeeded, UnsupportedQuestion
from cheiron.planning.models import PlanningResult

TRIAL_COUNT_MEASURE = MeasureSpec(
    field=MeasureField.NCT_ID,
    aggregation=Aggregation.COUNT_DISTINCT,
    label="Unique trial count",
    unit="trials",
)
ENROLLMENT_POINT_MEASURE = MeasureSpec(
    field=MeasureField.ENROLLMENT,
    aggregation=Aggregation.NONE,
    label="Enrollment",
    unit="participants",
)
TOTAL_ENROLLMENT_MEASURE = MeasureSpec(
    field=MeasureField.ENROLLMENT,
    aggregation=Aggregation.SUM,
    label="Total planned enrollment",
    unit="participants",
)
AVERAGE_ENROLLMENT_MEASURE = MeasureSpec(
    field=MeasureField.ENROLLMENT,
    aggregation=Aggregation.AVERAGE,
    label="Average planned enrollment",
    unit="participants",
)

_PHRASE_FILTERS: dict[FilterField, tuple[tuple[str, str], ...]] = {
    FilterField.PHASE: (
        ("early phase 1", "EARLY_PHASE1"),
        ("phase 1", "PHASE1"),
        ("phase 2", "PHASE2"),
        ("phase 3", "PHASE3"),
        ("phase 4", "PHASE4"),
        ("not applicable phase", "NA"),
    ),
    FilterField.STATUS: (
        ("active not recruiting", "ACTIVE_NOT_RECRUITING"),
        ("enrolling by invitation", "ENROLLING_BY_INVITATION"),
        ("not yet recruiting", "NOT_YET_RECRUITING"),
        ("recruiting", "RECRUITING"),
        ("completed", "COMPLETED"),
        ("suspended", "SUSPENDED"),
        ("terminated", "TERMINATED"),
        ("withdrawn", "WITHDRAWN"),
    ),
    FilterField.STUDY_TYPE: (
        ("interventional", "INTERVENTIONAL"),
        ("observational", "OBSERVATIONAL"),
        ("expanded access", "EXPANDED_ACCESS"),
    ),
    FilterField.SPONSOR_CLASS: (
        ("industry sponsored", "INDUSTRY"),
        ("industry-sponsored", "INDUSTRY"),
        ("nih sponsored", "NIH"),
        ("nih-sponsored", "NIH"),
    ),
}

_RELATIONSHIP_TERMS: dict[RelationshipEntity, tuple[str, ...]] = {
    RelationshipEntity.SPONSOR: ("sponsors", "sponsor"),
    RelationshipEntity.INTERVENTION: (
        "interventions",
        "intervention",
        "treatments",
        "treatment",
        "drugs",
        "drug",
    ),
    RelationshipEntity.CONDITION: ("conditions", "condition", "diseases", "disease"),
    RelationshipEntity.COUNTRY: ("countries", "country", "locations", "location"),
}


@dataclass(frozen=True, slots=True)
class _PlanShape:
    intent: AnalysisIntent
    dimensions: tuple[DimensionField, ...]
    visualization: VisualizationType
    measure: MeasureSpec
    relationship: RelationshipSpec | None = None


class RuleBasedPlanner:
    """Parse a deliberately small, documented grammar without guessing clinical facts."""

    async def plan(self, request: QueryRequest) -> PlanningResult:
        query = self._normalize(request.query)
        unsupported_reason = self._unsupported_reason(query)
        if unsupported_reason is not None:
            raise UnsupportedQuestion(
                reason=unsupported_reason,
                suggestions=(
                    "Count recruiting trials for a condition.",
                    "Show trials grouped by phase.",
                ),
            )

        scalar_measure = self._scalar_measure(query)
        if scalar_measure is not None:
            return self._scalar_answer(request, query, scalar_measure)

        intent = self._detect_intent(query)
        shape = self._shape(intent, query)
        shape = self._apply_visualization_preference(shape, request)

        global_filters = self._global_filters(request.filters, query)
        cohorts = self._cohorts(intent, query, request.filters, global_filters)
        requested_limit = self._extract_limit(query)
        if requested_limit is not None and intent not in {
            AnalysisIntent.DISTRIBUTION,
            AnalysisIntent.GEOGRAPHIC,
            AnalysisIntent.RELATIONSHIP,
        }:
            raise ClarificationNeeded(
                question=(
                    f"Top-N ranking is not well-defined for {intent.value} analysis. "
                    "Remove the top-N limit or choose a ranked bar chart."
                ),
                missing_fields=("limit",),
                suggestions=("Remove the top-N phrase", "Rank trials by country"),
            )
        limit = requested_limit
        if intent is AnalysisIntent.RELATIONSHIP and requested_limit is not None:
            if requested_limit < 2:
                raise ClarificationNeeded(
                    question="A relationship graph needs at least two nodes. Use top 2 or more.",
                    missing_fields=("relationship.max_nodes",),
                    suggestions=("top 10", "top 20"),
                )
            assert shape.relationship is not None
            shape = replace(
                shape,
                relationship=RelationshipSpec(
                    source=shape.relationship.source,
                    target=shape.relationship.target,
                    minimum_weight=shape.relationship.minimum_weight,
                    max_nodes=requested_limit,
                ),
            )
            limit = None
        sort = (
            SortSpec(field="trial_count", direction=SortDirection.DESCENDING)
            if limit is not None and intent is not AnalysisIntent.RELATIONSHIP
            else None
        )

        plan = AnalysisPlan(
            intent=shape.intent,
            interpretation=self._interpretation(shape, cohorts),
            cohorts=cohorts,
            dimensions=[DimensionSpec(field=field) for field in shape.dimensions],
            measure=shape.measure,
            visualization=shape.visualization,
            sort=sort,
            limit=limit,
            relationship=shape.relationship,
        )
        return PlanningResult(
            plan=plan,
            mode=PlannerMode.RULES,
            capability_limited=True,
            warnings=(
                "The deterministic fallback planner supports common chart patterns and explicit "
                "filters; nuanced clinical language may require clarification.",
            ),
        )

    def _scalar_answer(
        self,
        request: QueryRequest,
        query: str,
        measure: MeasureSpec,
    ) -> PlanningResult:
        if request.options.preferred_visualization is not None:
            raise ClarificationNeeded(
                question=(
                    "This question asks for one number, but a preferred chart was also selected. "
                    "Should I return the number or should the question include a grouping?"
                ),
                missing_fields=("dimension",),
                suggestions=("Return one number", "Group the result by phase"),
            )
        global_filters = self._global_filters(request.filters, query)
        cohorts = self._cohorts(
            AnalysisIntent.DISTRIBUTION,
            query,
            request.filters,
            global_filters,
        )
        plan = ScalarAnswerPlan(
            interpretation=self._scalar_interpretation(measure),
            cohorts=cohorts,
            measure=measure,
        )
        return PlanningResult(
            plan=plan,
            mode=PlannerMode.RULES,
            capability_limited=True,
            warnings=(
                "The deterministic fallback planner supports explicit scalar counts, totals, "
                "and averages over ClinicalTrials.gov metadata.",
            ),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().replace("\N{EN DASH}", "-").split())

    @staticmethod
    def _detect_intent(query: str) -> AnalysisIntent:
        if any(term in query for term in ("network", "relationship", "connect")):
            return AnalysisIntent.RELATIONSHIP
        if "histogram" in query or (
            "distribution" in query and any(term in query for term in ("enrollment", "sample size"))
        ):
            return AnalysisIntent.HISTOGRAM
        if any(term in query for term in ("scatter", "correlation")) or (
            any(term in query for term in ("enrollment", "sample size"))
            and any(term in query for term in ("start year", "starting year"))
            and any(term in query for term in (" vs ", " versus ", "against"))
        ):
            return AnalysisIntent.SCATTER
        if any(term in query for term in ("compare", "comparison", " vs ", " versus ")):
            return AnalysisIntent.COMPARISON
        if any(term in query for term in ("trend", "over time", "by year", "yearly", "annual")):
            return AnalysisIntent.TREND
        if any(term in query for term in ("geographic", "geography", "by country", "countries")):
            return AnalysisIntent.GEOGRAPHIC
        return AnalysisIntent.DISTRIBUTION

    @staticmethod
    def _scalar_measure(query: str) -> MeasureSpec | None:
        visualization_terms = (
            "compare",
            "comparison",
            " vs ",
            " versus ",
            "trend",
            "over time",
            "each year",
            "yearly",
            "distribution",
            "histogram",
            "scatter",
            "relationship",
            "network",
            "plot",
            "chart",
            "graph",
            "top ",
        )
        grouped = re.search(
            r"\bby\s+(?:trial\s+)?(?:phase|year|country|sponsor|intervention|treatment|status)\b",
            query,
        )
        if grouped is not None or any(term in query for term in visualization_terms):
            return None
        if re.search(r"\b(?:average|mean)\s+(?:planned\s+)?enrollment\b", query):
            return AVERAGE_ENROLLMENT_MEASURE
        if re.search(r"\b(?:total|sum(?:med)?)\s+(?:planned\s+)?enrollment\b", query):
            return TOTAL_ENROLLMENT_MEASURE
        if re.search(r"\bhow many\b|\bnumber of\b|\bcount(?: of)?\b", query):
            return TRIAL_COUNT_MEASURE
        return None

    @staticmethod
    def _unsupported_reason(query: str) -> str | None:
        unsupported_terms = (
            "best treatment",
            "most effective",
            "least effective",
            "recommend a treatment",
            "treatment recommendation",
            "should i take",
            "should i use",
            "diagnose",
            "prognosis",
            "prove that",
            "causes ",
        )
        if any(term in query for term in unsupported_terms):
            return (
                "Cheiron can analyze registered trial metadata, but it cannot provide medical "
                "advice or infer treatment efficacy, safety, causality, or prognosis."
            )
        return None

    @staticmethod
    def _scalar_interpretation(measure: MeasureSpec) -> str:
        if measure.field is MeasureField.NCT_ID:
            return "Count distinct clinical trials matching all requested filters."
        if measure.aggregation is Aggregation.AVERAGE:
            return "Calculate average planned enrollment for matching trials that report it."
        return "Sum planned enrollment for matching trials that report it."

    def _shape(self, intent: AnalysisIntent, query: str) -> _PlanShape:
        if intent is AnalysisIntent.RELATIONSHIP:
            source, target = self._relationship_entities(query)
            return _PlanShape(
                intent=intent,
                dimensions=(),
                visualization=VisualizationType.NETWORK_GRAPH,
                measure=TRIAL_COUNT_MEASURE,
                relationship=RelationshipSpec(source=source, target=target),
            )
        if intent is AnalysisIntent.HISTOGRAM:
            return _PlanShape(
                intent=intent,
                dimensions=(DimensionField.ENROLLMENT,),
                visualization=VisualizationType.HISTOGRAM,
                measure=TRIAL_COUNT_MEASURE,
            )
        if intent is AnalysisIntent.SCATTER:
            return _PlanShape(
                intent=intent,
                dimensions=(DimensionField.START_YEAR,),
                visualization=VisualizationType.SCATTER_PLOT,
                measure=ENROLLMENT_POINT_MEASURE,
            )
        if intent is AnalysisIntent.TREND:
            return _PlanShape(
                intent=intent,
                dimensions=(DimensionField.START_YEAR,),
                visualization=VisualizationType.TIME_SERIES,
                measure=TRIAL_COUNT_MEASURE,
            )
        if intent is AnalysisIntent.GEOGRAPHIC:
            return _PlanShape(
                intent=intent,
                dimensions=(DimensionField.COUNTRY,),
                visualization=VisualizationType.BAR_CHART,
                measure=TRIAL_COUNT_MEASURE,
            )

        is_time_comparison = intent is AnalysisIntent.COMPARISON and any(
            term in query for term in ("trend", "over time", "by year", "yearly", "annual")
        )
        dimension = (
            DimensionField.START_YEAR if is_time_comparison else self._categorical_dimension(query)
        )
        if is_time_comparison:
            visualization = VisualizationType.TIME_SERIES
        elif intent is AnalysisIntent.COMPARISON:
            visualization = VisualizationType.GROUPED_BAR_CHART
        else:
            visualization = VisualizationType.BAR_CHART
        return _PlanShape(
            intent=intent,
            dimensions=(dimension,),
            visualization=visualization,
            measure=TRIAL_COUNT_MEASURE,
        )

    @staticmethod
    def _categorical_dimension(query: str) -> DimensionField:
        terms = (
            ("intervention type", DimensionField.INTERVENTION_TYPE),
            ("treatment type", DimensionField.INTERVENTION_TYPE),
            ("sponsor class", DimensionField.SPONSOR_CLASS),
            ("sponsor type", DimensionField.SPONSOR_CLASS),
            ("country", DimensionField.COUNTRY),
            ("countries", DimensionField.COUNTRY),
            ("sponsor", DimensionField.SPONSOR),
            ("intervention", DimensionField.INTERVENTION),
            ("treatment", DimensionField.INTERVENTION),
            ("phase", DimensionField.PHASE),
        )
        for term, dimension in terms:
            if re.search(rf"\bby\s+(?:trial\s+)?{re.escape(term)}\b", query):
                return dimension
        if "phase" in query:
            return DimensionField.PHASE
        raise ClarificationNeeded(
            question="What should the trials be grouped by?",
            missing_fields=("dimension",),
            suggestions=("phase", "country", "sponsor class", "intervention type"),
        )

    @staticmethod
    def _relationship_entities(
        query: str,
    ) -> tuple[RelationshipEntity, RelationshipEntity]:
        found: list[tuple[int, RelationshipEntity]] = []
        for entity, terms in _RELATIONSHIP_TERMS.items():
            positions = [query.find(term) for term in terms if term in query]
            if positions:
                found.append((min(position for position in positions if position >= 0), entity))
        entities = [entity for _, entity in sorted(found)]
        if len(entities) < 2:
            raise ClarificationNeeded(
                question="Which two entity types should the relationship graph connect?",
                missing_fields=("relationship.source", "relationship.target"),
                suggestions=(
                    "sponsors and interventions",
                    "conditions and interventions",
                    "countries and sponsors",
                ),
            )
        return entities[0], entities[1]

    def _apply_visualization_preference(
        self,
        shape: _PlanShape,
        request: QueryRequest,
    ) -> _PlanShape:
        preferred = request.options.preferred_visualization
        if preferred is None or preferred is shape.visualization:
            return shape
        raise ClarificationNeeded(
            question=(
                f"The requested {preferred.value} is incompatible with {shape.intent.value} "
                f"analysis. Should I use {shape.visualization.value}?"
            ),
            missing_fields=("options.preferred_visualization",),
            suggestions=(shape.visualization.value,),
        )

    def _global_filters(self, filters: QueryFilters, query: str) -> list[FilterClause]:
        clauses: list[FilterClause] = []
        self._append_text_filter(
            clauses,
            FilterField.CONDITION,
            filters.conditions or self._extract_conditions(query),
        )
        self._append_text_filter(clauses, FilterField.SPONSOR, filters.sponsors)
        self._append_text_filter(clauses, FilterField.COUNTRY, filters.countries)
        self._append_enum_filter(
            clauses,
            FilterField.PHASE,
            [phase.value for phase in filters.phases]
            or self._phrase_values(query, FilterField.PHASE),
        )
        self._append_enum_filter(
            clauses,
            FilterField.STATUS,
            [status.value for status in filters.statuses]
            or self._phrase_values(query, FilterField.STATUS),
        )
        self._append_enum_filter(
            clauses,
            FilterField.SPONSOR_CLASS,
            [sponsor_class.value for sponsor_class in filters.sponsor_classes]
            or self._phrase_values(query, FilterField.SPONSOR_CLASS),
        )
        self._append_enum_filter(
            clauses,
            FilterField.STUDY_TYPE,
            [study_type.value for study_type in filters.study_types]
            or self._phrase_values(query, FilterField.STUDY_TYPE),
        )
        clauses.extend(self._year_filters(filters, query))
        return clauses

    def _cohorts(
        self,
        intent: AnalysisIntent,
        query: str,
        filters: QueryFilters,
        global_filters: list[FilterClause],
    ) -> list[CohortSpec]:
        if intent is AnalysisIntent.COMPARISON:
            comparison_terms = list(filters.interventions) or self._comparison_terms(query)
            if len(comparison_terms) < 2:
                raise ClarificationNeeded(
                    question="Which two or more interventions should be compared?",
                    missing_fields=("filters.interventions",),
                    suggestions=(
                        "Compare pembrolizumab versus nivolumab by phase",
                        "Provide two interventions in structured filters",
                    ),
                )
            if len(comparison_terms) > 5:
                raise ClarificationNeeded(
                    question="Please limit the comparison to at most five interventions.",
                    missing_fields=("filters.interventions",),
                )
            return [
                CohortSpec(
                    id=f"intervention-{index + 1}-{self._slug(term)}",
                    label=self._label(term),
                    filters=[
                        *global_filters,
                        FilterClause(
                            field=FilterField.INTERVENTION,
                            operator=FilterOperator.CONTAINS,
                            values=[term],
                        ),
                    ],
                )
                for index, term in enumerate(comparison_terms)
            ]

        cohort_filters = list(global_filters)
        self._append_text_filter(
            cohort_filters,
            FilterField.INTERVENTION,
            filters.interventions or self._extract_interventions(query),
        )
        return [CohortSpec(id="all-matching", label="All matching trials", filters=cohort_filters)]

    @staticmethod
    def _append_text_filter(
        clauses: list[FilterClause],
        field: FilterField,
        values: Sequence[str],
    ) -> None:
        normalized = RuleBasedPlanner._unique(values)
        if not normalized:
            return
        clauses.append(
            FilterClause(
                field=field,
                operator=(FilterOperator.CONTAINS if len(normalized) == 1 else FilterOperator.IN),
                values=list(normalized),
            )
        )

    @staticmethod
    def _append_enum_filter(
        clauses: list[FilterClause],
        field: FilterField,
        values: Sequence[str],
    ) -> None:
        normalized = RuleBasedPlanner._unique(values)
        if normalized:
            clauses.append(
                FilterClause(
                    field=field,
                    operator=(FilterOperator.EQUALS if len(normalized) == 1 else FilterOperator.IN),
                    values=list(normalized),
                )
            )

    @staticmethod
    def _phrase_values(query: str, field: FilterField) -> list[str]:
        matches: list[str] = []
        occupied: list[tuple[int, int]] = []
        for phrase, value in _PHRASE_FILTERS[field]:
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", query):
                span = match.span()
                if any(span[0] < end and span[1] > start for start, end in occupied):
                    continue
                occupied.append(span)
                matches.append(value)
        return matches

    @staticmethod
    def _extract_conditions(query: str) -> list[str]:
        patterns = (
            r"\b(?:trials?|studies?)\s+(?:for|in|on)\s+(.+?)"
            r"(?=\s+(?:by|from|between|since|before|over)\b|[,.?]|$)",
            r"\bfor\s+(?:patients?\s+with\s+)?(.+?)"
            r"(?=\s+(?:by|from|between|since|before|over)\b|[,.?]|$)",
            r"\bof\s+(.+?)\s+(?:clinical\s+)?(?:trials?|studies?)\b",
            r"\b(?:show|display|plot|chart|count|summarize|list)\s+"
            r"(?:me\s+)?(?:the\s+)?(.+?)\s+(?:clinical\s+)?(?:trials?|studies?)\b",
            r"\b(?:how many|number of|count of)\s+(.+?)\s+"
            r"(?:clinical\s+)?(?:trials?|studies?)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                candidate = RuleBasedPlanner._clean_condition_term(match.group(1))
                if candidate and not candidate.isdigit():
                    return [candidate]
        return []

    @staticmethod
    def _comparison_terms(query: str) -> list[str]:
        separator = re.search(r"\s+(?:vs\.?|versus)\s+", query)
        if separator is not None:
            left = query[: separator.start()]
            right = query[separator.end() :]
            left = re.sub(r"^.*?\bcompare\s+", "", left)
            left = re.sub(
                r"^(?:clinical\s+)?(?:trials?|studies?)\s+(?:of|for|using|with)\s+",
                "",
                left,
            )
        else:
            pair = re.search(
                r"\bbetween\s+(.+?)\s+and\s+(.+?)"
                r"(?=\s+(?:by|for|in|among|over)\b|[,.?]|$)",
                query,
            )
            if pair is None:
                pair = re.search(
                    r"\bcompare\s+(.+?)\s+and\s+(.+?)"
                    r"(?=\s+(?:by|for|in|among|over)\b|[,.?]|$)",
                    query,
                )
            if pair is None:
                return []
            left, right = pair.group(1), pair.group(2)
        right = re.split(
            r"\s+(?:clinical\s+)?(?:trials?|studies?)\b|"
            r"\s+by\b|\s+for\b|\s+in\b|\s+among\b|[,.?]",
            right,
            maxsplit=1,
        )[0]
        terms = [RuleBasedPlanner._clean_term(left), RuleBasedPlanner._clean_term(right)]
        return [term for term in terms if term]

    @staticmethod
    def _extract_interventions(query: str) -> list[str]:
        pattern = (
            r"\b(?:trials?|studies?)\s+(?:involving|using)\s+(.+?)"
            r"(?=\s+(?:by|for|in|among|from|since|before|over)\b|[,.?]|$)"
        )
        match = re.search(pattern, query)
        if match is None:
            match = re.search(
                r"\btreated\s+with\s+(.+?)"
                r"(?=\s+(?:by|for|in|among|from|since|before|over)\b|[,.?]|$)",
                query,
            )
        if match is None:
            return []
        term = RuleBasedPlanner._clean_term(match.group(1))
        return [term] if term else []

    @staticmethod
    def _year_filters(filters: QueryFilters, query: str) -> list[FilterClause]:
        lower = filters.start_year_from
        upper = filters.start_year_to
        if lower is None and upper is None:
            between = re.search(
                r"\b(?:between|from)\s+(19\d{2}|20\d{2})"
                r"\s+(?:and|to)\s+(19\d{2}|20\d{2})\b",
                query,
            )
            if between:
                lower, upper = int(between.group(1)), int(between.group(2))
            else:
                lower_match = re.search(r"\b(?:since|after|from)\s+(19\d{2}|20\d{2})\b", query)
                upper_match = re.search(r"\b(?:before|through|until)\s+(19\d{2}|20\d{2})\b", query)
                lower = int(lower_match.group(1)) if lower_match else None
                upper = int(upper_match.group(1)) if upper_match else None
        if lower is not None and upper is not None:
            if lower > upper:
                raise ClarificationNeeded(
                    question=(
                        "The requested start-year range is reversed. Which range should I use?"
                    ),
                    missing_fields=("filters.start_year_from", "filters.start_year_to"),
                )
            return [
                FilterClause(
                    field=FilterField.START_YEAR,
                    operator=FilterOperator.BETWEEN,
                    values=[lower, upper],
                )
            ]
        if lower is not None:
            return [
                FilterClause(
                    field=FilterField.START_YEAR,
                    operator=FilterOperator.GREATER_THAN_OR_EQUAL,
                    values=[lower],
                )
            ]
        if upper is not None:
            return [
                FilterClause(
                    field=FilterField.START_YEAR,
                    operator=FilterOperator.LESS_THAN_OR_EQUAL,
                    values=[upper],
                )
            ]
        return []

    @staticmethod
    def _extract_limit(query: str) -> int | None:
        match = re.search(r"\btop\s+(\d{1,4})\b", query)
        if match is None:
            return None
        limit = int(match.group(1))
        if not 1 <= limit <= 100:
            raise ClarificationNeeded(
                question="Please choose a top-N limit between 1 and 100.",
                missing_fields=("limit",),
                suggestions=("top 10", "top 20"),
            )
        return limit

    @staticmethod
    def _interpretation(shape: _PlanShape, cohorts: Sequence[CohortSpec]) -> str:
        if shape.intent is AnalysisIntent.RELATIONSHIP:
            assert shape.relationship is not None
            source = shape.relationship.source.value.replace("_", " ")
            target = shape.relationship.target.value.replace("_", " ")
            return f"Connect {source} and {target} using distinct shared trials."
        if shape.intent is AnalysisIntent.HISTOGRAM:
            return "Count distinct trials in deterministic enrollment-size bins."
        if shape.intent is AnalysisIntent.SCATTER:
            return "Plot each trial's enrollment against its start year."
        dimension = shape.dimensions[0].value.replace("_", " ")
        if len(cohorts) > 1:
            labels = " versus ".join(cohort.label for cohort in cohorts)
            return f"Compare {labels} using distinct trial counts by {dimension}."
        return f"Count distinct matching trials by {dimension}."

    @staticmethod
    def _unique(values: Iterable[str]) -> tuple[str, ...]:
        unique: dict[str, str] = {}
        for value in values:
            normalized = " ".join(value.split())
            if normalized:
                unique.setdefault(normalized.casefold(), normalized)
        return tuple(unique.values())

    @staticmethod
    def _clean_term(value: str) -> str:
        cleaned = value.strip(" -:;,.?")
        cleaned = re.sub(
            r"^(?:the\s+)?(?:clinical\s+)?(?:trials?|studies?)\s+(?:of|for)\s+",
            "",
            cleaned,
        )
        cleaned = re.sub(r"\s+(?:clinical\s+)?(?:trials?|studies?)$", "", cleaned)
        return " ".join(cleaned.split())

    @staticmethod
    def _clean_condition_term(value: str) -> str:
        cleaned = RuleBasedPlanner._clean_term(value)
        phrases = sorted(
            {phrase for phrase_filters in _PHRASE_FILTERS.values() for phrase, _ in phrase_filters},
            key=len,
            reverse=True,
        )
        for phrase in phrases:
            cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned)
        cleaned = re.sub(
            r"^(?:(?:a|an|the|all)\s+)*(?:(?:bar|grouped bar)\s+graph\s+of\s+)?",
            "",
            cleaned,
        )
        return " ".join(cleaned.split())

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return slug[:40] or "cohort"

    @staticmethod
    def _label(value: str) -> str:
        normalized = " ".join(value.split())
        return normalized[:1].upper() + normalized[1:]
