import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type {
  CartesianVisualization,
  NetworkVisualization,
} from '../../api/types.ts'
import { successResponse } from '../../test/fixtures.ts'
import { VisualizationRenderer } from './VisualizationRenderer.tsx'

const barVisualization = successResponse.visualization as CartesianVisualization

describe('VisualizationRenderer', () => {
  it.each(['bar_chart', 'grouped_bar_chart', 'histogram'] as const)(
    'renders sorted, focusable marks for %s',
    (type) => {
      const visualization: CartesianVisualization = {
        ...barVisualization,
        type,
        data: {
          kind: 'tabular',
          records: [...barVisualization.data.records].reverse(),
        },
      }

      const { container } = render(<VisualizationRenderer visualization={visualization} />)

      expect(screen.getByRole('group', { name: /Breast cancer trials by phase/ })).toBeVisible()
      const marks = [...container.querySelectorAll<SVGRectElement>('.chart-bar')]
      expect(marks.map((mark) => mark.dataset.datumId)).toEqual(['phase-1', 'phase-2'])
      expect(marks.every((mark) => mark.getAttribute('tabindex') === '0')).toBe(true)
    },
  )

  it('renders a time-series path with one accessible point per datum', () => {
    const visualization = numericVisualization('time_series')
    const { container } = render(<VisualizationRenderer visualization={visualization} />)

    expect(container.querySelector('.chart-line')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-datum-id]')).toHaveLength(2)
    expect(screen.getByLabelText(/Start year: 2020; Studies: 4/)).toBeVisible()
  })

  it('renders quantitative scatter points', () => {
    const visualization = numericVisualization('scatter_plot')
    const { container } = render(<VisualizationRenderer visualization={visualization} />)

    expect(container.querySelectorAll('.chart-point')).toHaveLength(2)
    expect(screen.getByLabelText(/Start year: 2021; Studies: 7/)).toBeVisible()
  })

  it('renders traceable network nodes and weighted edges', () => {
    const visualization: NetworkVisualization = {
      type: 'network_graph',
      title: 'Sponsor to intervention network',
      description: 'Shared trial relationships.',
      encoding: {},
      data: {
        kind: 'network',
        nodes: [
          {
            id: 'sponsor-a',
            label: 'Sponsor A',
            entity_type: 'sponsor',
            value: 2,
            citation_ids: ['cit-1', 'cit-2'],
          },
          {
            id: 'drug-b',
            label: 'Drug B',
            entity_type: 'intervention',
            value: 2,
            citation_ids: ['cit-1', 'cit-2'],
          },
        ],
        edges: [
          {
            id: 'sponsor-a-drug-b',
            source: 'sponsor-a',
            target: 'drug-b',
            weight: 2,
            citation_ids: ['cit-1', 'cit-2'],
          },
        ],
      },
    }

    const { container } = render(<VisualizationRenderer visualization={visualization} />)

    expect(screen.getByRole('group', { name: /Sponsor to intervention network/ })).toBeVisible()
    expect(container.querySelectorAll('[data-node-id]')).toHaveLength(2)
    expect(container.querySelectorAll('[data-edge-id]')).toHaveLength(1)
    expect(screen.getByLabelText(/Sponsor A ↔ Drug B: 2 shared trials/)).toBeVisible()
  })

  it('shows a stable empty state when the renderer receives no records', () => {
    render(
      <VisualizationRenderer
        visualization={{
          ...barVisualization,
          data: { kind: 'tabular', records: [] },
        }}
      />,
    )

    expect(screen.getByText('No data points were returned for this visualization.')).toBeVisible()
  })

  it('selects the exact datum with pointer and keyboard activation', () => {
    const onSelectTarget = vi.fn()
    render(
      <VisualizationRenderer
        visualization={barVisualization}
        onSelectTarget={onSelectTarget}
      />,
    )
    const mark = screen.getByRole('button', {
      name: /Trial phase: Phase 1; Studies: 18/,
    })

    fireEvent.click(mark)
    fireEvent.keyDown(mark, { key: 'Enter' })
    fireEvent.keyDown(mark, { key: ' ' })

    expect(onSelectTarget).toHaveBeenCalledTimes(3)
    expect(onSelectTarget).toHaveBeenLastCalledWith(
      expect.objectContaining({
        key: 'datum:phase-1',
        citationIds: ['cit-nct00000001'],
      }),
    )
  })
})

function numericVisualization(
  type: 'time_series' | 'scatter_plot',
): CartesianVisualization {
  return {
    type,
    title: 'Trial starts over time',
    description: 'Studies by start year.',
    encoding: {
      x: {
        field: 'start_year',
        data_type: 'temporal',
        title: 'Start year',
        unit: null,
        sort: 'ascending',
      },
      y: {
        field: 'trial_count',
        data_type: 'quantitative',
        title: 'Studies',
        unit: 'studies',
        sort: null,
      },
      color: null,
      size: null,
    },
    data: {
      kind: 'tabular',
      records: [
        {
          id: 'year-2020',
          values: { start_year: 2020, trial_count: 4 },
          citation_ids: ['cit-1'],
        },
        {
          id: 'year-2021',
          values: { start_year: 2021, trial_count: 7 },
          citation_ids: ['cit-2'],
        },
      ],
    },
  }
}
