import { useEffect, useRef, useState } from 'react'

import { queryClinicalTrials } from './api/client.ts'
import type { QueryRequest, QueryResponse } from './api/types.ts'
import { QueryComposer } from './components/QueryComposer.tsx'
import { ResultStage } from './components/ResultStage.tsx'

const DEFAULT_STUDY_LIMIT = 500

export default function App() {
  const [query, setQuery] = useState('')
  const [includeCitations, setIncludeCitations] = useState(true)
  const [maxStudies, setMaxStudies] = useState(DEFAULT_STUDY_LIMIT)
  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [transportError, setTransportError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => activeRequest.current?.abort()
  }, [])

  async function handleSubmit() {
    const normalizedQuery = query.trim()
    if (normalizedQuery.length < 3 || maxStudies < 1) {
      return
    }

    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setIsLoading(true)
    setTransportError(null)
    setResponse(null)

    const request: QueryRequest = {
      schema_version: '1.0',
      query: normalizedQuery,
      options: {
        include_citations: includeCitations,
        max_studies: Math.min(maxStudies, 100000),
      },
    }

    try {
      setResponse(await queryClinicalTrials(request, { signal: controller.signal }))
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      setTransportError(
        error instanceof Error ? error.message : 'An unexpected connection error occurred.',
      )
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null
        setIsLoading(false)
      }
    }
  }

  function handleSuggestion(suggestion: string) {
    setQuery(suggestion)
    setResponse(null)
    requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('#clinical-query')?.focus())
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="Cheiron home">
          <span className="brand-mark" aria-hidden="true">
            C
          </span>
          <span>
            <strong>Cheiron</strong>
            <small>Clinical evidence explorer</small>
          </span>
        </a>
        <div className="header-meta">
          <span className="live-indicator">
            <span aria-hidden="true" />
            Live source data
          </span>
          <span>Schema 1.0</span>
        </div>
      </header>

      <main>
        <QueryComposer
          query={query}
          includeCitations={includeCitations}
          maxStudies={maxStudies}
          isLoading={isLoading}
          onQueryChange={setQuery}
          onIncludeCitationsChange={setIncludeCitations}
          onMaxStudiesChange={setMaxStudies}
          onSubmit={handleSubmit}
        />
        <ResultStage
          response={response}
          transportError={transportError}
          isLoading={isLoading}
          onSuggestion={handleSuggestion}
        />
      </main>

      <footer className="site-footer">
        <span>ClinicalTrials.gov is the authoritative data source.</span>
        <span>AI interprets questions; deterministic code computes results.</span>
      </footer>
    </div>
  )
}
