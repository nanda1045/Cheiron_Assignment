import type {
  ClarificationResponse,
  ErrorResponse,
  QueryResponse,
  ScalarValue,
  SuccessResponse,
} from '../api/types.ts'

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
        <SuccessResult response={response} />
      ) : response?.status === 'clarification_required' ? (
        <ClarificationResult response={response} onSuggestion={onSuggestion} />
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
  const visualization = response.visualization
  const citationCount = Object.keys(response.provenance.citations).length

  return (
    <div className="success-result">
      <div className="result-title-row">
        <div>
          <p className="eyebrow">{formatToken(visualization.type)}</p>
          <h3>{visualization.title}</h3>
          <p>{visualization.description}</p>
        </div>
        <span className="complete-badge">
          <CheckIcon />
          Complete
        </span>
      </div>

      <blockquote>{response.query.interpretation}</blockquote>

      <div className="metric-strip" aria-label="Result metadata">
        <Metric value={response.meta.record_counts.used} label="Studies used" />
        <Metric value={citationCount} label="Citations" />
        <Metric value={response.meta.completeness.pages_retrieved} label="Pages read" />
        <Metric value={`${response.meta.duration_ms}ms`} label="Duration" />
      </div>

      <DataPreview response={response} />

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
    </div>
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

function DataPreview({ response }: { response: SuccessResponse }) {
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
              </tr>
            </thead>
            <tbody>
              {visualization.data.nodes.slice(0, 6).map((node) => (
                <tr key={node.id}>
                  <td>{node.label}</td>
                  <td>{formatToken(node.entity_type)}</td>
                  <td>{node.value}</td>
                </tr>
              ))}
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
            {records.slice(0, 6).map((record) => (
              <tr key={record.id}>
                {columns.map((column) => (
                  <td key={column}>{formatValue(record.values[column])}</td>
                ))}
                <td>{record.citation_ids.length} refs</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
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
  return (
    <div className="message-state error-state" role="alert">
      <span className="message-symbol" aria-hidden="true">!</span>
      <p className="eyebrow">{formatToken(response.error.code)}</p>
      <h3>The evidence view could not be completed.</h3>
      <p>{response.error.message}</p>
      <small>
        Request {response.request_id.slice(0, 8)}
        {response.error.retryable ? ' · This request can be retried.' : ''}
      </small>
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
