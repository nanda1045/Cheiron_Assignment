import type { QueryRequest, QueryResponse } from './types.ts'

type Fetcher = typeof fetch

interface QueryClientOptions {
  signal?: AbortSignal
  fetcher?: Fetcher
}

export class QueryClientError extends Error {
  constructor(
    message: string,
    readonly statusCode?: number,
  ) {
    super(message)
    this.name = 'QueryClientError'
  }
}

export async function queryClinicalTrials(
  request: QueryRequest,
  options: QueryClientOptions = {},
): Promise<QueryResponse> {
  const fetcher = options.fetcher ?? fetch
  let response: Response

  try {
    response = await fetcher('/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new QueryClientError(
      'Could not reach the Cheiron API. Confirm that the backend is running.',
    )
  }

  const payload = await parseResponse(response)
  if (!isQueryResponse(payload)) {
    throw new QueryClientError(
      'The API returned an unexpected response shape.',
      response.status,
    )
  }

  if (!response.ok && payload.status !== 'error') {
    throw new QueryClientError(`The API request failed with HTTP ${response.status}.`, response.status)
  }

  return payload
}

async function parseResponse(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw new QueryClientError('The API returned a response that was not valid JSON.', response.status)
  }
}

function isQueryResponse(payload: unknown): payload is QueryResponse {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }

  const envelope = payload as Record<string, unknown>
  return (
    envelope.schema_version === '1.0' &&
    typeof envelope.request_id === 'string' &&
    (envelope.status === 'ok' ||
      envelope.status === 'clarification_required' ||
      envelope.status === 'error')
  )
}
