import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App.tsx'
import {
  clarificationResponse,
  errorResponse,
  successResponse,
} from './test/fixtures.ts'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts with an accessible query workspace', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: /turn a clinical question/i })).toBeVisible()
    expect(screen.getByLabelText('Clinical-trial question')).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Generate evidence view' })).toBeDisabled()
    expect(screen.getByText('Evidence will take shape here.')).toBeVisible()
  })

  it('submits the configured request and renders structured source metadata', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(successResponse))
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await user.type(screen.getByLabelText('Clinical-trial question'), successResponse.query.original)
    await user.clear(screen.getByLabelText('Study limit'))
    await user.type(screen.getByLabelText('Study limit'), '250')
    await user.click(screen.getByRole('button', { name: 'Generate evidence view' }))

    expect(await screen.findByText('Breast cancer trials by phase')).toBeVisible()
    expect(screen.getByText('52')).toBeVisible()
    expect(screen.getByText('ClinicalTrials.gov')).toBeVisible()
    expect(screen.getAllByText('Phase 1')).toHaveLength(2)

    await user.click(
      screen.getByRole('button', { name: /Trial phase: Phase 1; Studies: 18/ }),
    )
    expect(screen.getByRole('link', { name: /NCT00000001/ })).toHaveAttribute(
      'href',
      'https://clinicaltrials.gov/study/NCT00000001',
    )
    expect(
      screen.getByText('protocolSection.identificationModule.nctId'),
    ).toBeVisible()

    const requestInit = fetchMock.mock.calls[0]?.[1]
    expect(JSON.parse(String(requestInit?.body))).toEqual({
      schema_version: '1.0',
      query: successResponse.query.original,
      options: { include_citations: true, max_studies: 250 },
    })
  })

  it('uses a clarification suggestion to refine the query', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(clarificationResponse)),
    )
    render(<App />)

    await user.type(screen.getByLabelText('Clinical-trial question'), 'Show me some trials')
    await user.click(screen.getByRole('button', { name: 'Generate evidence view' }))
    await user.click(await screen.findByRole('button', { name: clarificationResponse.clarification.suggestions[0] }))

    expect(screen.getByLabelText('Clinical-trial question')).toHaveValue(
      clarificationResponse.clarification.suggestions[0],
    )
    expect(screen.getByText('Evidence will take shape here.')).toBeVisible()
  })

  it('shows typed service errors without discarding the request reference', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(errorResponse, { status: 503 })),
    )
    render(<App />)

    await user.type(screen.getByLabelText('Clinical-trial question'), 'Count recruiting trials')
    await user.click(screen.getByRole('button', { name: 'Generate evidence view' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'ClinicalTrials.gov is temporarily unavailable.',
    )
    await waitFor(() => expect(screen.getByText(/Request 229d8f25/)).toBeVisible())
  })
})

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}
