import type { ChannelEncoding, ScalarValue, TabularDatum } from '../../api/types.ts'

export const CHART_WIDTH = 720
export const CHART_HEIGHT = 360
export const PLOT = { left: 64, right: 24, top: 20, bottom: 72 } as const
export const PLOT_WIDTH = CHART_WIDTH - PLOT.left - PLOT.right
export const PLOT_HEIGHT = CHART_HEIGHT - PLOT.top - PLOT.bottom

export const SERIES_COLORS = ['#e7ff84', '#ff8f70', '#79cdb0', '#9fb8ff', '#f5c27a', '#d3a6ff']

export function numeric(value: ScalarValue | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

export function category(value: ScalarValue | undefined): string {
  if (value === null || value === undefined || value === '') {
    return 'Unknown'
  }
  return String(value)
}

export function uniqueCategories(records: TabularDatum[], field: string): string[] {
  return [...new Set(records.map((record) => category(record.values[field])))]
}

export function sortRecords(records: TabularDatum[], encoding: ChannelEncoding): TabularDatum[] {
  const sorted = [...records]
  const configuredSort = encoding.sort

  if (Array.isArray(configuredSort)) {
    const positions = new Map(
      configuredSort.map((value, index) => [category(value), index]),
    )
    return sorted.sort((left, right) => {
      const leftPosition = positions.get(category(left.values[encoding.field]))
      const rightPosition = positions.get(category(right.values[encoding.field]))
      return (leftPosition ?? Number.MAX_SAFE_INTEGER) - (rightPosition ?? Number.MAX_SAFE_INTEGER)
    })
  }

  if (configuredSort === 'ascending' || configuredSort === 'descending') {
    const direction = configuredSort === 'ascending' ? 1 : -1
    return sorted.sort(
      (left, right) =>
        compareValues(left.values[encoding.field], right.values[encoding.field]) * direction,
    )
  }

  return sorted
}

export function numericExtent(values: number[], includeZero = false): [number, number] {
  if (values.length === 0) {
    return [0, 1]
  }

  let minimum = Math.min(...values)
  let maximum = Math.max(...values)
  if (includeZero) {
    minimum = Math.min(0, minimum)
    maximum = Math.max(0, maximum)
  }
  if (minimum === maximum) {
    const padding = Math.max(Math.abs(minimum) * 0.1, 1)
    minimum -= padding
    maximum += padding
  }
  return [minimum, maximum]
}

export function scaleLinear(
  value: number,
  domain: [number, number],
  range: [number, number],
): number {
  const ratio = (value - domain[0]) / (domain[1] - domain[0])
  return range[0] + ratio * (range[1] - range[0])
}

export function tickValues(domain: [number, number], count = 5): number[] {
  return Array.from(
    { length: count },
    (_, index) => domain[0] + ((domain[1] - domain[0]) * index) / (count - 1),
  )
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en', {
    notation: Math.abs(value) >= 10_000 ? 'compact' : 'standard',
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value)
}

export function truncateLabel(value: string, maxLength = 18): string {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength - 1)}…`
}

export function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length] ?? SERIES_COLORS[0]!
}

function compareValues(left: ScalarValue | undefined, right: ScalarValue | undefined): number {
  const leftNumber = numeric(left)
  const rightNumber = numeric(right)
  if (leftNumber !== null && rightNumber !== null) {
    return leftNumber - rightNumber
  }
  return category(left).localeCompare(category(right))
}
