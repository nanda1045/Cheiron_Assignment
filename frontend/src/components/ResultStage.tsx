import { useState } from 'react'

import type {
  ClarificationResponse,
  ErrorResponse,
  QueryResponse,
  ScalarValue,
  ScalarAnswerSuccessResponse,
  SuccessResponse,
  UnsupportedResponse,
  VisualizationSuccessResponse,
} from '../api/types.ts'
import { EvidenceInspector } from './provenance/EvidenceInspector.tsx'
import {
  datumEvidenceTarget,
  nodeEvidenceTarget,
  type EvidenceTarget,
} from './visualization/evidenceSelection.ts'
import { VisualizationRenderer } from './visualization/VisualizationRenderer.tsx'

interface ResultStageProps {
  response: QueryResponse | null
  transportError: string | null
  isLoading: boolean
  onSuggestion: (suggestion: string) => void
}

export function ResultStage({
  response,
  transportError,
  isLoading,
  onSuggestion,
}: ResultStageProps) {
  return (
    <section className="result-stage" aria-labelledby="result-heading" aria-live="polite">
      <div className="stage-header">
        <div>
          <span className="panel-kicker panel-kicker--dark">
            <span>02</span>
            Evidence view
          </span>
          <h2 id="result-heading">Analysis workspace</h2>
        </div>
        <SourceBadge isActive={response?.status === 'ok'} />
      </div>

      {isLoading ? (
        <LoadingState />
      ) : transportError ? (
        <TransportError message={transportError} />
      ) : response?.status === 'ok' ? (
        <SuccessResult key={response.request_id} response={response} />
      ) : response?.status === 'clarification_required' ? (
        <ClarificationResult response={response} onSuggestion={onSuggestion} />
      ) : response?.status === 'unsupported' ? (
        <UnsupportedResult response={response} onSuggestion={onSuggestion} />
      ) : response?.status === 'error' ? (
        <ErrorResult response={response} />
      ) : (
        <EmptyState />
      )}
    </section>
  )
}

function SourceBadge({ isActive }: { isActive: boolean }) {
  return (
    <span className={`source-badge${isActive ? ' source-badge--active' : ''}`}>
      <span aria-hidden="true" />
      ClinicalTrials.gov
    </span>
  )
}

function EmptyState() {
  return (
    <div className="empty-state">
      <div className="orbital-mark" aria-hidden="true">
        <span className="orbit orbit--one" />
        <span className="orbit orbit--two" />
        <span className="orbit-center">C</span>
      </div>
      <div>
        <p className="eyebrow">Ready for a question</p>
        <h3>Evidence will take shape here.</h3>
        <p>
          The agent interprets your question, retrieves authoritative records, and
          produces a visualization contract with traceable data.
        </p>
      </div>
      <ol className="workflow-list">
        <li>
          <span>01</span>
          Interpret intent
        </li>
        <li>
          <span>02</span>
          Retrieve studies
        </li>
        <li>
          <span>03</span>
          Analyze evidence
        </li>
        <li>
          <span>04</span>
          Structure the view
        </li>
      </ol>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="loading-state" role="status">
      <div className="loading-visual" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <p className="eyebrow">Analysis in progress</p>
      <h3>Following the evidence trail…</h3>
      <p>Planning the query, retrieving studies, and validating every output datum.</p>
    </div>
  )
}

function SuccessResult({ response }: { response: SuccessResponse }) {
  if (response.result_type === 'scalar_answer') {
    return <ScalarAnswerResult response={response} />
  }
  return <VisualizationResult response={response} />
}

function VisualizationResult({ response }: { response: VisualizationSuccessResponse }) {
  const visualization = response.visualization
  const citationCount = Object.keys(response.provenance.citations).length
  const hasData = response.meta.record_counts.used > 0
  const [selectedTarget, setSelectedTarget] = useState<EvidenceTarget | null>(null)

  return (
    <div className="success-result">
      <div className="result-title-row">
        <div>
          <p className="eyebrow">{formatToken(visualization.type)}</p>
          <h3>{visualization.title}</h3>
          <p>{visualization.description}</p>
        </div>
        <ResultStatusBadge response={response} />
      </div>

      <blockquote>{response.query.interpretation}</blockquote>

      <div className="metric-strip" aria-label="Result metadata">
        <Metric value={response.meta.record_counts.used} label="Studies used" />
        <Metric value={citationCount} label="Citations" />
        <Metric value={response.meta.completeness.pages_retrieved} label="Pages read" />
        <Metric value={`${response.meta.duration_ms}ms`} label="Duration" />
      </div>

      {hasData ? (
        <>
          <VisualizationRenderer
            visualization={visualization}
            selectedTargetKey={selectedTarget?.key}
            onSelectTarget={setSelectedTarget}
          />

          <EvidenceInspector
            key={selectedTarget?.key ?? 'no-selection'}
            target={selectedTarget}
            citations={response.provenance.citations}
            source={response.provenance.source}
          />

          <DataPreview
            response={response}
            selectedTargetKey={selectedTarget?.key}
            onSelectTarget={setSelectedTarget}
          />
        </>
      ) : (
        <NoResultsNotice response={response} />
      )}

      <ResultFooter response={response} />
    </div>
  )
}

function ScalarAnswerResult({ response }: { response: ScalarAnswerSuccessResponse }) {
  const answer = response.answer
  const citationCount = Object.keys(response.provenance.citations).length
  const hasEvidence = response.meta.record_counts.used > 0
  const target: EvidenceTarget = {
    key: 'answer:scalar',
    kind: 'answer',
    title: answer.title,
    attributes: [
      {
        label: answer.unit ? `Value (${answer.unit})` : 'Value',
        value: answer.value,
      },
    ],
    citationIds: answer.citation_ids,
  }

  return (
    <div className="success-result">
      <div className="result-title-row">
        <div>
          <p className="eyebrow">Sourced answer</p>
          <h3>{answer.title}</h3>
          <p>One deterministic aggregate from the matching source records.</p>
        </div>
        <ResultStatusBadge response={response} />
      </div>

      <blockquote>{response.query.interpretation}</blockquote>

      <div className="metric-strip" aria-label="Result metadata">
        <Metric value={response.meta.record_counts.used} label="Studies used" />
        <Metric value={citationCount} label="Citations" />
        <Metric value={response.meta.completeness.pages_retrieved} label="Pages read" />
        <Metric value={`${response.meta.duration_ms}ms`} label="Duration" />
      </div>

      <section className="answer-card" aria-label={answer.title}>
        <span>Computed result</span>
        <strong>
          {formatValue(answer.value)}
          {answer.unit ? <small>{answer.unit}</small> : null}
        </strong>
        <p>{answer.text}</p>
      </section>

      {hasEvidence ? (
        <EvidenceInspector
          target={target}
          citations={response.provenance.citations}
          source={response.provenance.source}
        />
      ) : null}

      <ResultFooter response={response} />
    </div>
  )
}

function ResultFooter({ response }: { response: SuccessResponse }) {
  return (
    <footer className="result-footer">
      <div>
        <span>Source snapshot</span>
        <strong>{formatDate(response.provenance.source.data_timestamp)}</strong>
      </div>
      <div>
        <span>Planner</span>
        <strong>{formatToken(response.meta.planner.mode)}</strong>
      </div>
      <div>
        <span>Request</span>
        <strong>{response.request_id.slice(0, 8)}</strong>
      </div>
    </footer>
  )
}

function ResultStatusBadge({ response }: { response: SuccessResponse }) {
  const used = response.meta.record_counts.used
  let label = 'Complete'
  if (response.result_type === 'scalar_answer' && response.answer.value === null) {
    label = 'No reported data'
  } else if (used === 0 && response.meta.record_counts.matched === 0) {
    label = 'No matches'
  } else if (used === 0) {
    label = 'No usable data'
  }
  const isEmpty = used === 0

  return (
    <span className={`complete-badge${isEmpty ? ' complete-badge--empty' : ''}`}>
      {isEmpty ? <span aria-hidden="true">—</span> : <CheckIcon />}
      {label}
    </span>
  )
}

function NoResultsNotice({ response }: { response: VisualizationSuccessResponse }) {
  const sourceMatchedNothing = response.meta.record_counts.matched === 0
  return (
    <section className="no-results-notice" role="status">
      <span aria-hidden="true">∅</span>
      <div>
        <p className="eyebrow">
          {sourceMatchedNothing ? 'No source matches' : 'No usable data points'}
        </p>
        <h4>
          {sourceMatchedNothing
            ? 'No ClinicalTrials.gov studies matched every requested filter.'
            : 'Retrieved studies could not produce the requested visualization.'}
        </h4>
        <p>
          {sourceMatchedNothing
            ? 'The source query completed successfully with zero matches. Try broadening a condition, phase, status, or date filter.'
            : `${response.meta.record_counts.retrieved} studies were retrieved, but none retained all required filters and analysis fields.`}
        </p>
      </div>
    </section>
  )
}

function Metric({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  )
}

function DataPreview({
  response,
  selectedTargetKey,
  onSelectTarget,
}: {
  response: VisualizationSuccessResponse
  selectedTargetKey?: string
  onSelectTarget: (target: EvidenceTarget) => void
}) {
  const visualization = response.visualization

  if (visualization.type === 'network_graph') {
    return (
      <div className="data-preview">
        <PreviewHeader count={visualization.data.nodes.length} label="nodes" />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Entity</th>
                <th>Type</th>
                <th>Connections</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {visualization.data.nodes.slice(0, 6).map((node) => {
                const target = nodeEvidenceTarget(node)
                return (
                  <tr key={node.id}>
                    <td>{node.label}</td>
                    <td>{formatToken(node.entity_type)}</td>
                    <td>{node.value}</td>
                    <td>
                      <EvidenceButton
                        target={target}
                        isSelected={target.key === selectedTargetKey}
                        onSelectTarget={onSelectTarget}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const records = visualization.data.records
  const fields = [
    visualization.encoding.x.field,
    visualization.encoding.y.field,
    visualization.encoding.color?.field,
    visualization.encoding.size?.field,
  ].filter((field): field is string => Boolean(field))
  const columns = [...new Set(fields)]

  return (
    <div className="data-preview">
      <PreviewHeader count={records.length} label="data points" />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{formatToken(column)}</th>
              ))}
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {records.slice(0, 6).map((record) => {
              const target = datumEvidenceTarget(record, visualization)
              return (
                <tr key={record.id}>
                  {columns.map((column) => (
                    <td key={column}>{formatValue(record.values[column])}</td>
                  ))}
                  <td>
                    <EvidenceButton
                      target={target}
                      isSelected={target.key === selectedTargetKey}
                      onSelectTarget={onSelectTarget}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EvidenceButton({
  target,
  isSelected,
  onSelectTarget,
}: {
  target: EvidenceTarget
  isSelected: boolean
  onSelectTarget: (target: EvidenceTarget) => void
}) {
  return (
    <button
      className={`inspect-evidence${isSelected ? ' inspect-evidence--selected' : ''}`}
      type="button"
      aria-pressed={isSelected}
      aria-label={`Inspect evidence for ${target.title}`}
      onClick={() => onSelectTarget(target)}
    >
      {target.citationIds.length} refs
      <span aria-hidden="true">→</span>
    </button>
  )
}

function PreviewHeader({ count, label }: { count: number; label: string }) {
  return (
    <div className="preview-header">
      <div>
        <span className="preview-icon" aria-hidden="true">⌁</span>
        <strong>Structured data preview</strong>
      </div>
      <span>
        {count} {label}
      </span>
    </div>
  )
}

function ClarificationResult({
  response,
  onSuggestion,
}: {
  response: ClarificationResponse
  onSuggestion: (suggestion: string) => void
}) {
  return (
    <div className="message-state clarification-state">
      <span className="message-symbol" aria-hidden="true">?</span>
      <p className="eyebrow">One detail needed</p>
      <h3>{response.clarification.question}</h3>
      {response.clarification.missing_fields.length > 0 && (
        <p>
          Missing: {response.clarification.missing_fields.map(formatToken).join(', ')}
        </p>
      )}
      {response.clarification.suggestions.length > 0 && (
        <div className="suggestion-list" aria-label="Suggested questions">
          {response.clarification.suggestions.map((suggestion) => (
            <button key={suggestion} type="button" onClick={() => onSuggestion(suggestion)}>
              {suggestion}
              <span aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ErrorResult({ response }: { response: ErrorResponse }) {
  const presentation = errorPresentation(response.error.code)
  const provider = response.error.context.provider
  return (
    <div className="message-state error-state" role="alert">
      <span className="message-symbol" aria-hidden="true">!</span>
      <p className="eyebrow">{presentation.label}</p>
      <h3>{presentation.heading}</h3>
      <p>{response.error.message}</p>
      <small>
        {typeof provider === 'string' ? `${provider} · ` : ''}Request{' '}
        {response.request_id.slice(0, 8)}
        {response.error.retryable ? ' · This request can be retried.' : ''}
      </small>
    </div>
  )
}

function UnsupportedResult({
  response,
  onSuggestion,
}: {
  response: UnsupportedResponse
  onSuggestion: (suggestion: string) => void
}) {
  return (
    <div className="message-state unsupported-state">
      <span className="message-symbol" aria-hidden="true">×</span>
      <p className="eyebrow">Outside supported analysis</p>
      <h3>This question needs a different kind of evidence.</h3>
      <p>{response.reason}</p>
      {response.suggestions.length > 0 && (
        <div className="suggestion-list" aria-label="Supported question examples">
          {response.suggestions.map((suggestion) => (
            <button key={suggestion} type="button" onClick={() => onSuggestion(suggestion)}>
              {suggestion}
              <span aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function TransportError({ message }: { message: string }) {
  return (
    <div className="message-state error-state" role="alert">
      <span className="message-symbol" aria-hidden="true">!</span>
      <p className="eyebrow">Connection error</p>
      <h3>Cheiron could not reach the analysis service.</h3>
      <p>{message}</p>
    </div>
  )
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="m5 10 3 3 7-7" />
    </svg>
  )
}

function errorPresentation(code: string): { label: string; heading: string } {
  const presentations: Record<string, { label: string; heading: string }> = {
    planner_not_configured: {
      label: 'Planner configuration required',
      heading: 'Anthropic Claude needs a valid API credential.',
    },
    planner_unavailable: {
      label: 'Planner provider unavailable',
      heading: 'Anthropic Claude could not be reached.',
    },
    planner_request_rejected: {
      label: 'Planner request rejected',
      heading: 'Anthropic Claude rejected the planning contract.',
    },
    planner_invalid_response: {
      label: 'Planner response invalid',
      heading: 'Anthropic Claude returned no usable decision.',
    },
    source_unavailable: {
      label: 'Source provider unavailable',
      heading: 'ClinicalTrials.gov could not be reached.',
    },
    source_rejected_query: {
      label: 'Source query rejected',
      heading: 'ClinicalTrials.gov rejected the compiled query.',
    },
    source_contract_error: {
      label: 'Source response invalid',
      heading: 'ClinicalTrials.gov returned an incomplete response.',
    },
  }
  return presentations[code] ?? {
    label: formatToken(code),
    heading: 'The evidence view could not be completed.',
  }
}

function formatToken(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

function formatValue(value: ScalarValue | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return String(value)
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value))
}
