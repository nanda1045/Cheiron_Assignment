"""Shared source-field paths used to prove filters and aggregate measures."""

from collections.abc import Iterable

from cheiron.clinical_trials.normalizer import (
    CONDITIONS_PATH,
    ENROLLMENT_COUNT_PATH,
    INTERVENTIONS_PATH,
    LOCATIONS_PATH,
    PHASES_PATH,
    SPONSOR_CLASS_PATH,
    SPONSOR_NAME_PATH,
    START_DATE_PATH,
)
from cheiron.domain.enums import FilterField
from cheiron.domain.plan import CohortSpec

FILTER_EVIDENCE_PATHS = {
    FilterField.CONDITION: (CONDITIONS_PATH,),
    FilterField.INTERVENTION: (f"{INTERVENTIONS_PATH}.name",),
    FilterField.PHASE: (PHASES_PATH,),
    FilterField.SPONSOR: (SPONSOR_NAME_PATH,),
    FilterField.SPONSOR_CLASS: (SPONSOR_CLASS_PATH,),
    FilterField.COUNTRY: (f"{LOCATIONS_PATH}.country",),
    FilterField.STATUS: ("protocolSection.statusModule.overallStatus",),
    FilterField.STUDY_TYPE: ("protocolSection.designModule.studyType",),
    FilterField.START_YEAR: (START_DATE_PATH,),
    FilterField.ENROLLMENT: (ENROLLMENT_COUNT_PATH,),
}


def cohort_filter_evidence_paths(cohorts: Iterable[CohortSpec]) -> tuple[str, ...]:
    """Return de-duplicated source paths for every cohort predicate."""

    paths: list[str] = []
    for cohort in cohorts:
        for clause in cohort.filters:
            paths.extend(FILTER_EVIDENCE_PATHS.get(clause.field, ()))
    return tuple(dict.fromkeys(paths))
