import type { FormEvent } from 'react'

const EXAMPLE_QUERIES = [
  'How have recruiting breast cancer trials changed each year since 2018?',
  'Compare trial phases for pembrolizumab and nivolumab in lung cancer.',
  "Which sponsors lead Phase 3 Alzheimer's disease trials?",
]

interface QueryComposerProps {
  query: string
  includeCitations: boolean
  maxStudies: number
  isLoading: boolean
  onQueryChange: (query: string) => void
  onIncludeCitationsChange: (includeCitations: boolean) => void
  onMaxStudiesChange: (maxStudies: number) => void
  onSubmit: () => void
}

export function QueryComposer({
  query,
  includeCitations,
  maxStudies,
  isLoading,
  onQueryChange,
  onIncludeCitationsChange,
  onMaxStudiesChange,
  onSubmit,
}: QueryComposerProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <section className="query-panel" aria-labelledby="query-heading">
      <div className="panel-kicker">
        <span>01</span>
        Ask the evidence
      </div>
      <h1 id="query-heading">Turn a clinical question into a sourced answer.</h1>
      <p className="query-intro">
        Ask about trial activity, phases, sponsors, locations, or change over time.
        Cheiron will choose the analysis and return a renderable specification.
      </p>

      <form onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="clinical-query">
          Clinical-trial question
        </label>
        <div className="query-field-shell">
          <textarea
            id="clinical-query"
            name="query"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            minLength={3}
            maxLength={2000}
            rows={6}
            placeholder="e.g. How many recruiting glioblastoma trials started each year since 2019?"
            disabled={isLoading}
            required
          />
          <span className="character-count" aria-hidden="true">
            {query.length} / 2,000
          </span>
        </div>

        <div className="example-block">
          <p>Try a starting point</p>
          <div className="example-list">
            {EXAMPLE_QUERIES.map((example, index) => (
              <button
                key={example}
                type="button"
                className="example-query"
                onClick={() => onQueryChange(example)}
                disabled={isLoading}
              >
                <span>0{index + 1}</span>
                {example}
              </button>
            ))}
          </div>
        </div>

        <fieldset className="query-options">
          <legend>Retrieval controls</legend>
          <label className="toggle-option">
            <input
              type="checkbox"
              checked={includeCitations}
              onChange={(event) => onIncludeCitationsChange(event.target.checked)}
              disabled={isLoading}
            />
            <span className="toggle-track" aria-hidden="true">
              <span />
            </span>
            <span>
              <strong>Include citations</strong>
              <small>Attach NCT evidence to every datum</small>
            </span>
          </label>

          <label className="study-limit" htmlFor="max-studies">
            <span>
              <strong>Study limit</strong>
              <small>Bound source retrieval</small>
            </span>
            <input
              id="max-studies"
              aria-label="Study limit"
              type="number"
              min={1}
              max={100000}
              value={maxStudies}
              onChange={(event) => onMaxStudiesChange(Number(event.target.value))}
              disabled={isLoading}
            />
          </label>
        </fieldset>

        <button
          className="submit-query"
          type="submit"
          disabled={isLoading || query.trim().length < 3 || maxStudies < 1}
        >
          <span>{isLoading ? 'Building evidence view' : 'Generate evidence view'}</span>
          {isLoading ? <span className="spinner" aria-hidden="true" /> : <ArrowIcon />}
        </button>
      </form>
    </section>
  )
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}
