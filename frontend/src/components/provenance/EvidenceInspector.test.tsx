import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Citation, SuccessResponse } from '../../api/types.ts'
import type { EvidenceTarget } from '../visualization/evidenceSelection.ts'
import { EvidenceInspector } from './EvidenceInspector.tsx'

const source: SuccessResponse['provenance']['source'] = {
  name: 'ClinicalTrials.gov',
  api_version: '2.0',
  data_timestamp: '2026-07-31T12:00:00Z',
  retrieved_at: '2026-07-31T12:01:00Z',
  endpoint: 'https://clinicaltrials.gov/api/v2/studies',
}

describe('EvidenceInspector', () => {
  it('explains how to inspect provenance before a mark is selected', () => {
    render(<EvidenceInspector target={null} citations={{}} source={source} />)

    expect(screen.getByText('Datum-level provenance')).toBeVisible()
    expect(screen.getByText(/Select a data mark/)).toBeVisible()
  })

  it('handles a selected mark without attached citations', () => {
    render(
      <EvidenceInspector
        target={target([])}
        citations={{}}
        source={source}
      />,
    )

    expect(screen.getByText(/No citations were attached/)).toBeVisible()
    expect(screen.getByText('0 contributing studies')).toBeVisible()
  })

  it('pages large citation sets and preserves exact source fields', async () => {
    const user = userEvent.setup()
    const citations = Object.fromEntries(
      Array.from({ length: 9 }, (_, index) => {
        const number = String(index + 1).padStart(8, '0')
        const id = `cit-${number}`
        return [id, citation(id, `NCT${number}`)]
      }),
    )
    render(
      <EvidenceInspector
        target={target(Object.keys(citations))}
        citations={citations}
        source={source}
      />,
    )

    expect(screen.getByText('9 contributing studies')).toBeVisible()
    expect(screen.queryByRole('link', { name: /NCT00000009/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('protocolSection.designModule.phases')).toHaveLength(8)

    await user.click(screen.getByRole('button', { name: /Show 1 more studies/ }))

    expect(screen.getByRole('link', { name: /NCT00000009/ })).toBeVisible()
    expect(screen.getAllByText('protocolSection.designModule.phases')).toHaveLength(9)
  })
})

function target(citationIds: string[]): EvidenceTarget {
  return {
    key: 'datum:phase-2',
    kind: 'datum',
    title: 'Trial phase: Phase 2',
    attributes: [
      { label: 'Trial phase', value: 'Phase 2' },
      { label: 'Studies', value: citationIds.length },
    ],
    citationIds,
  }
}

function citation(id: string, nctId: string): Citation {
  return {
    id,
    nct_id: nctId,
    study_url: `https://clinicaltrials.gov/study/${nctId}`,
    evidence: [
      {
        field_path: 'protocolSection.designModule.phases',
        value: ['PHASE2'],
      },
    ],
  }
}
