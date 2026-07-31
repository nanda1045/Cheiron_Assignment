"""Normalize nested ClinicalTrials.gov studies without hiding data quality issues."""

from collections.abc import Iterable, Mapping
from typing import Any

from cheiron.clinical_trials.errors import NormalizationError
from cheiron.clinical_trials.models import (
    DatePrecision,
    Intervention,
    NormalizationResult,
    NormalizationWarning,
    PartialDate,
    TrialRecord,
)
from cheiron.domain.response import EvidenceValue
from cheiron.domain.visualization import ScalarValue

NCT_ID_PATH = "protocolSection.identificationModule.nctId"
BRIEF_TITLE_PATH = "protocolSection.identificationModule.briefTitle"
STATUS_PATH = "protocolSection.statusModule.overallStatus"
START_DATE_PATH = "protocolSection.statusModule.startDateStruct.date"
START_DATE_TYPE_PATH = "protocolSection.statusModule.startDateStruct.type"
PHASES_PATH = "protocolSection.designModule.phases"
STUDY_TYPE_PATH = "protocolSection.designModule.studyType"
ENROLLMENT_COUNT_PATH = "protocolSection.designModule.enrollmentInfo.count"
ENROLLMENT_TYPE_PATH = "protocolSection.designModule.enrollmentInfo.type"
SPONSOR_NAME_PATH = "protocolSection.sponsorCollaboratorsModule.leadSponsor.name"
SPONSOR_CLASS_PATH = "protocolSection.sponsorCollaboratorsModule.leadSponsor.class"
CONDITIONS_PATH = "protocolSection.conditionsModule.conditions"
INTERVENTIONS_PATH = "protocolSection.armsInterventionsModule.interventions"
LOCATIONS_PATH = "protocolSection.contactsLocationsModule.locations"


class TrialNormalizer:
    """Create analysis-ready records while preserving exact evidence values."""

    def normalize_many(self, studies: Iterable[dict[str, Any]]) -> NormalizationResult:
        records: list[TrialRecord] = []
        warnings: list[NormalizationWarning] = []
        seen_nct_ids: set[str] = set()
        excluded_count = 0

        for study in studies:
            try:
                record = self.normalize(study)
            except NormalizationError as error:
                excluded_count += 1
                warnings.append(
                    NormalizationWarning(
                        nct_id=None,
                        field_path=NCT_ID_PATH,
                        message=str(error),
                    )
                )
                continue
            if record.nct_id in seen_nct_ids:
                excluded_count += 1
                warnings.append(
                    NormalizationWarning(
                        nct_id=record.nct_id,
                        field_path=NCT_ID_PATH,
                        message="duplicate study record excluded",
                    )
                )
                continue
            seen_nct_ids.add(record.nct_id)
            records.append(record)

        return NormalizationResult(
            records=tuple(records),
            excluded_count=excluded_count,
            warnings=tuple(warnings),
        )

    def normalize(self, study: dict[str, Any]) -> TrialRecord:
        nct_id = self._optional_string(self._get_path(study, NCT_ID_PATH))
        if nct_id is None or not self._is_valid_nct_id(nct_id):
            raise NormalizationError("study is missing a valid NCT identifier")

        start_date_value = self._optional_string(self._get_path(study, START_DATE_PATH))
        start_date_type = self._optional_string(self._get_path(study, START_DATE_TYPE_PATH))
        start_date = self._parse_partial_date(start_date_value, start_date_type)

        phases = self._unique_strings(self._get_path(study, PHASES_PATH))
        conditions = self._unique_strings(self._get_path(study, CONDITIONS_PATH))
        interventions = self._normalize_interventions(self._get_path(study, INTERVENTIONS_PATH))
        countries = self._normalize_countries(self._get_path(study, LOCATIONS_PATH))
        enrollment_count = self._optional_integer(self._get_path(study, ENROLLMENT_COUNT_PATH))

        source_values: dict[str, EvidenceValue] = {}
        for path in (
            NCT_ID_PATH,
            STATUS_PATH,
            START_DATE_PATH,
            START_DATE_TYPE_PATH,
            PHASES_PATH,
            STUDY_TYPE_PATH,
            ENROLLMENT_COUNT_PATH,
            ENROLLMENT_TYPE_PATH,
            SPONSOR_NAME_PATH,
            SPONSOR_CLASS_PATH,
            CONDITIONS_PATH,
        ):
            value = self._evidence_value(self._get_path(study, path))
            if value is not None:
                source_values[path] = value
        self._add_intervention_evidence(source_values, interventions)
        if countries:
            country_values: list[ScalarValue] = list(countries)
            source_values[f"{LOCATIONS_PATH}.country"] = country_values

        return TrialRecord(
            nct_id=nct_id,
            brief_title=self._optional_string(self._get_path(study, BRIEF_TITLE_PATH)),
            overall_status=self._optional_string(self._get_path(study, STATUS_PATH)),
            start_date=start_date,
            phases=phases,
            study_type=self._optional_string(self._get_path(study, STUDY_TYPE_PATH)),
            enrollment_count=enrollment_count,
            enrollment_type=self._optional_string(self._get_path(study, ENROLLMENT_TYPE_PATH)),
            lead_sponsor_name=self._optional_string(self._get_path(study, SPONSOR_NAME_PATH)),
            lead_sponsor_class=self._optional_string(self._get_path(study, SPONSOR_CLASS_PATH)),
            conditions=conditions,
            interventions=interventions,
            countries=countries,
            source_values=source_values,
        )

    @staticmethod
    def _get_path(value: Mapping[str, Any], path: str) -> Any:
        current: Any = value
        for segment in path.split("."):
            if not isinstance(current, Mapping):
                return None
            current = current.get(segment)
        return current

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _optional_integer(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return None

    @staticmethod
    def _unique_strings(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(
            dict.fromkeys(
                item.strip() for item in value if isinstance(item, str) and item.strip()
            )
        )

    @classmethod
    def _normalize_interventions(cls, value: Any) -> tuple[Intervention, ...]:
        if not isinstance(value, list):
            return ()
        interventions: list[Intervention] = []
        seen: set[tuple[str, str | None]] = set()
        for item in value:
            if not isinstance(item, Mapping):
                continue
            name = cls._optional_string(item.get("name"))
            if name is None:
                continue
            intervention_type = cls._optional_string(item.get("type"))
            key = (name.casefold(), intervention_type)
            if key in seen:
                continue
            seen.add(key)
            interventions.append(Intervention(name=name, type=intervention_type))
        return tuple(interventions)

    @classmethod
    def _normalize_countries(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        countries = {
            country
            for location in value
            if isinstance(location, Mapping)
            if (country := cls._optional_string(location.get("country"))) is not None
        }
        return tuple(sorted(countries))

    @staticmethod
    def _parse_partial_date(value: str | None, date_type: str | None) -> PartialDate | None:
        if value is None:
            return None
        parts = value.split("-")
        if len(parts) not in {1, 2, 3} or not all(part.isdigit() for part in parts):
            return None
        year = int(parts[0])
        month = int(parts[1]) if len(parts) >= 2 else None
        day = int(parts[2]) if len(parts) == 3 else None
        if not 1900 <= year <= 2100:
            return None
        if month is not None and not 1 <= month <= 12:
            return None
        if day is not None and not 1 <= day <= 31:
            return None
        precision = {
            1: DatePrecision.YEAR,
            2: DatePrecision.MONTH,
            3: DatePrecision.DAY,
        }[len(parts)]
        return PartialDate(
            original=value,
            year=year,
            month=month,
            day=day,
            precision=precision,
            date_type=date_type,
        )

    @staticmethod
    def _evidence_value(value: Any) -> EvidenceValue | None:
        if value is None or isinstance(value, Mapping):
            return None
        if isinstance(value, list):
            scalar_items: list[ScalarValue] = [
                item for item in value if isinstance(item, str | int | float | bool)
            ]
            return scalar_items or None
        if isinstance(value, str | int | float | bool):
            return value
        return None

    @staticmethod
    def _add_intervention_evidence(
        source_values: dict[str, EvidenceValue],
        interventions: tuple[Intervention, ...],
    ) -> None:
        if interventions:
            names: list[ScalarValue] = [
                intervention.name for intervention in interventions
            ]
            source_values[f"{INTERVENTIONS_PATH}.name"] = names
        intervention_types: list[ScalarValue] = list(
            dict.fromkeys(
                intervention.type
                for intervention in interventions
                if intervention.type is not None
            )
        )
        if intervention_types:
            source_values[f"{INTERVENTIONS_PATH}.type"] = intervention_types

    @staticmethod
    def _is_valid_nct_id(value: str) -> bool:
        return len(value) == 11 and value.startswith("NCT") and value[3:].isdigit()
