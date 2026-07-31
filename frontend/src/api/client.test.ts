import { describe, expect, it, vi } from 'vitest'

import { queryClinicalTrials, QueryClientError } from './client.ts'
import type { QueryRequest } from './types.ts'
import { errorResponse, successResponse } from '../test/fixtures.ts'

const request: QueryRequest = {
  schema_version: '1.0',
  query: 'Count breast cancer trials by phase.',
  options: { include_citations: true, max_studies: 500 },
}

describe('queryClinicalTrials', () => {
  it('posts the versioned request and returns a success envelope', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(successResponse))

    await expect(queryClinicalTrials(request, { fetcher })).resolves.toEqual(successResponse)
    expect(fetcher).toHaveBeenCalledWith(
      '/v1/query',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      }),
    )
  })

  it('preserves a typed error envelope from a non-success HTTP response', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(errorResponse, { status: 503 }))

    await expect(queryClinicalTrials(request, { fetcher })).resolves.toEqual(errorResponse)
  })

  it('rejects an invalid response contract', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ detail: 'bad shape' }))

    await expect(queryClinicalTrials(request, { fetcher })).rejects.toMatchObject(
      expect.objectContaining<Partial<QueryClientError>>({
        name: 'QueryClientError',
        message: 'The API returned an unexpected response shape.',
        statusCode: 200,
      }),
    )
  })

  it('maps a network failure to a safe connection message', async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('connection refused'))

    await expect(queryClinicalTrials(request, { fetcher })).rejects.toThrow(
      'Could not reach the Cheiron API. Confirm that the backend is running.',
    )
  })
})

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}
