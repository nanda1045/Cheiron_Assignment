"""Canonical ClinicalTrials.gov vocabulary for categorical plan filters."""

from typing import Final

from cheiron.domain.enums import (
    FilterField,
    RecruitmentStatus,
    SponsorClass,
    StudyType,
    TrialPhase,
)

_CategoricalVocabulary = dict[str, str]


def _normalized_token(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _enum_vocabulary(
    values: list[str],
    aliases: dict[str, str] | None = None,
) -> _CategoricalVocabulary:
    vocabulary = {_normalized_token(value): value for value in values}
    for alias, canonical in (aliases or {}).items():
        vocabulary[_normalized_token(alias)] = canonical
    return vocabulary


_PHASES: Final = _enum_vocabulary(
    [phase.value for phase in TrialPhase],
    {
        "Early Phase 1": TrialPhase.EARLY_PHASE1.value,
        "Phase 1": TrialPhase.PHASE1.value,
        "Phase I": TrialPhase.PHASE1.value,
        "Phase 2": TrialPhase.PHASE2.value,
        "Phase II": TrialPhase.PHASE2.value,
        "Phase 3": TrialPhase.PHASE3.value,
        "Phase III": TrialPhase.PHASE3.value,
        "Phase 4": TrialPhase.PHASE4.value,
        "Phase IV": TrialPhase.PHASE4.value,
        "Not Applicable": TrialPhase.NOT_APPLICABLE.value,
        "N/A": TrialPhase.NOT_APPLICABLE.value,
    },
)
_STATUSES: Final = _enum_vocabulary([status.value for status in RecruitmentStatus])
_STUDY_TYPES: Final = _enum_vocabulary([study_type.value for study_type in StudyType])
_SPONSOR_CLASSES: Final = _enum_vocabulary(
    [sponsor_class.value for sponsor_class in SponsorClass],
    {
        "Federal": SponsorClass.FEDERAL.value,
        "Other Government": SponsorClass.OTHER_GOVERNMENT.value,
        "Individual": SponsorClass.INDIVIDUAL.value,
    },
)

CATEGORICAL_FILTER_VOCABULARIES: Final[dict[FilterField, _CategoricalVocabulary]] = {
    FilterField.PHASE: _PHASES,
    FilterField.STATUS: _STATUSES,
    FilterField.STUDY_TYPE: _STUDY_TYPES,
    FilterField.SPONSOR_CLASS: _SPONSOR_CLASSES,
}


def canonicalize_categorical_value(field: FilterField, value: str | int) -> str | int:
    """Return the source API code for a categorical value, rejecting unknown labels."""

    vocabulary = CATEGORICAL_FILTER_VOCABULARIES.get(field)
    if vocabulary is None:
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field.value} filter values must be strings")

    canonical = vocabulary.get(_normalized_token(value))
    if canonical is None:
        allowed = sorted(set(vocabulary.values()))
        raise ValueError(
            f"unsupported {field.value} value {value!r}; expected one of {', '.join(allowed)}"
        )
    return canonical
