import { useState } from 'react'

import type { Citation, ScalarValue, SuccessResponse } from '../../api/types.ts'
import type { EvidenceTarget } from '../visualization/evidenceSelection.ts'

const CITATIONS_PER_PAGE = 8

interface EvidenceInspectorProps {
  target: EvidenceTarget | null
  citations: Record<string, Citation>
  source: SuccessResponse['provenance']['source']
}

export function EvidenceInspector({ target, citations, source }: EvidenceInspectorProps) {
  const [visibleCount, setVisibleCount] = useState(CITATIONS_PER_PAGE)

  if (target === null) {
    return (
      <section
        className="provenance-inspector provenance-inspector--empty"
        aria-labelledby="provenance-heading"
      >
        <ProvenanceHeading />
        <div className="provenance-empty-copy">
          <span aria-hidden="true">↗</span>
          <div>
            <strong>Select a data mark to trace its evidence.</strong>
            <p>Each mark links only to the studies and source fields that contributed to it.</p>
          </div>
        </div>
      </section>
    )
  }

  const uniqueCitationIds = [...new Set(target.citationIds)]
  const resolvedCitations = uniqueCitationIds.flatMap((citationId) => {
    const citation = citations[citationId]
    return citation ? [citation] : []
  })
  const missingCitationCount = uniqueCitationIds.length - resolvedCitations.length
  const visibleCitations = resolvedCitations.slice(0, visibleCount)
  const remainingCount = resolvedCitations.length - visibleCitations.length

  return (
    <section
      className="provenance-inspector"
      aria-labelledby="provenance-heading"
      aria-live="polite"
    >
      <ProvenanceHeading />

      <div className="selected-datum-summary">
        <div>
          <span>{formatKind(target.kind)}</span>
          <h4>{target.title}</h4>
        </div>
        <strong>{resolvedCitations.length} contributing studies</strong>
      </div>

      <dl className="datum-attributes">
        {target.attributes.map((attribute) => (
          <div key={attribute.label}>
            <dt>{attribute.label}</dt>
            <dd>{formatEvidenceValue(attribute.value)}</dd>
          </div>
        ))}
      </dl>

      {uniqueCitationIds.length === 0 ? (
        <div className="provenance-notice">
          No citations were attached to this mark. Rerun the query with “Include citations” enabled
          to inspect its contributing studies.
        </div>
      ) : resolvedCitations.length === 0 ? (
        <div className="provenance-notice provenance-notice--warning">
          The mark references citation IDs that are missing from the response catalog.
        </div>
      ) : (
        <div className="citation-list" aria-label="Contributing ClinicalTrials.gov studies">
          {visibleCitations.map((citation) => (
            <CitationCard key={citation.id} citation={citation} />
          ))}
          {remainingCount > 0 && (
            <button
              className="load-citations"
              type="button"
              onClick={() => setVisibleCount((count) => count + CITATIONS_PER_PAGE)}
            >
              Show {Math.min(CITATIONS_PER_PAGE, remainingCount)} more studies
              <span>{remainingCount} remaining</span>
            </button>
          )}
        </div>
      )}

      {missingCitationCount > 0 && resolvedCitations.length > 0 && (
        <p className="missing-citation-warning">
          {missingCitationCount} referenced citation {missingCitationCount === 1 ? 'is' : 'are'}
          missing from the response catalog.
        </p>
      )}

      <footer className="provenance-source-note">
        <span>Source snapshot</span>
        <strong>
          {source.name} API {source.api_version}
        </strong>
        <time dateTime={source.data_timestamp}>{formatDateTime(source.data_timestamp)}</time>
      </footer>
    </section>
  )
}

function ProvenanceHeading() {
  return (
    <div className="provenance-heading">
      <div>
        <span className="preview-icon" aria-hidden="true">
          ⌁
        </span>
        <h3 id="provenance-heading">Datum-level provenance</h3>
      </div>
      <span>Verified source trail</span>
    </div>
  )
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <article className="citation-card">
      <header>
        <a href={citation.study_url} target="_blank" rel="noreferrer">
          {citation.nct_id}
          <span aria-hidden="true">↗</span>
        </a>
        <span>{citation.evidence.length} source fields</span>
      </header>
      <dl>
        {citation.evidence.map((evidence, index) => (
          <div key={`${evidence.field_path}-${index}`}>
            <dt>
              <code>{evidence.field_path}</code>
            </dt>
            <dd>{formatEvidenceValue(evidence.value)}</dd>
          </div>
        ))}
      </dl>
    </article>
  )
}

function formatEvidenceValue(value: ScalarValue | ScalarValue[]): string {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.map(formatScalar).join(', ') : 'Empty list'
  }
  return formatScalar(value)
}

function formatScalar(value: ScalarValue): string {
  if (value === null) {
    return 'Not reported'
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  return String(value)
}

function formatKind(kind: EvidenceTarget['kind']): string {
  const labels = {
    answer: 'Scalar answer',
    datum: 'Chart datum',
    node: 'Network node',
    edge: 'Network edge',
  } as const
  return labels[kind]
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}
