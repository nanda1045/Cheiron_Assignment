"""Build normalized citations that are shared across visualization data items."""

from hashlib import sha256

from cheiron.clinical_trials.models import TrialRecord
from cheiron.clinical_trials.normalizer import NCT_ID_PATH
from cheiron.domain.response import Citation, Evidence


class ProvenanceCatalog:
    """Accumulate stable citation objects and return references for each datum."""

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled
        self._citations: dict[str, Citation] = {}

    @property
    def citations(self) -> dict[str, Citation]:
        return dict(self._citations)

    def references_for(
        self,
        datum_id: str,
        contributors: tuple[TrialRecord, ...],
        evidence_paths: tuple[str, ...],
    ) -> list[str]:
        if not self._enabled:
            return []
        references: list[str] = []
        for record in contributors:
            evidence = self._evidence(record, evidence_paths)
            citation_id = self._citation_id(datum_id, record.nct_id, evidence_paths)
            self._citations[citation_id] = Citation(
                id=citation_id,
                nct_id=record.nct_id,
                study_url=f"https://clinicaltrials.gov/study/{record.nct_id}",
                evidence=evidence,
            )
            references.append(citation_id)
        return references

    @staticmethod
    def _evidence(record: TrialRecord, paths: tuple[str, ...]) -> list[Evidence]:
        evidence = [
            Evidence(field_path=path, value=record.source_values[path])
            for path in paths
            if path in record.source_values
        ]
        if not evidence:
            evidence.append(Evidence(field_path=NCT_ID_PATH, value=record.nct_id))
        return evidence

    @staticmethod
    def _citation_id(datum_id: str, nct_id: str, paths: tuple[str, ...]) -> str:
        digest_input = "|".join((datum_id, nct_id, *paths)).encode()
        digest = sha256(digest_input).hexdigest()[:12]
        return f"cit-{nct_id.casefold()}-{digest}"
