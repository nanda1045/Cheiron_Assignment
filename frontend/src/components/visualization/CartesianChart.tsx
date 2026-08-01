import type {
  CartesianVisualization,
  ChannelEncoding,
  TabularDatum,
} from '../../api/types.ts'
import {
  CHART_HEIGHT,
  CHART_WIDTH,
  PLOT,
  PLOT_HEIGHT,
  PLOT_WIDTH,
  category,
  formatNumber,
  numeric,
  numericExtent,
  scaleLinear,
  seriesColor,
  sortRecords,
  tickValues,
  truncateLabel,
  uniqueCategories,
} from './chartMath.ts'

interface CartesianChartProps {
  visualization: CartesianVisualization
}

interface NumericPoint {
  record: TabularDatum
  x: number
  y: number
  series: string
}

export function CartesianChart({ visualization }: CartesianChartProps) {
  const records = sortRecords(visualization.data.records, visualization.encoding.x)
  if (records.length === 0) {
    return <ChartEmpty />
  }

  const chart = (() => {
    switch (visualization.type) {
      case 'bar_chart':
      case 'grouped_bar_chart':
      case 'histogram':
        return <BarChart visualization={visualization} records={records} />
      case 'time_series':
        return <LineChart visualization={visualization} records={records} />
      case 'scatter_plot':
        return <ScatterChart visualization={visualization} records={records} />
    }
  })()

  return (
    <figure className="chart-shell">
      <svg
        className="evidence-chart"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="img"
        aria-label={`${visualization.title}. ${visualization.description}`}
      >
        {chart}
      </svg>
      <figcaption>Interactive visualization. Focus a data mark to inspect its value.</figcaption>
    </figure>
  )
}

function BarChart({
  visualization,
  records,
}: CartesianChartProps & { records: TabularDatum[] }) {
  const { x, y, color } = visualization.encoding
  const categories = uniqueCategories(records, x.field)
  const series = color ? uniqueCategories(records, color.field) : ['Value']
  const values = records.map((record) => numeric(record.values[y.field]) ?? 0)
  const yDomain: [number, number] = [0, Math.max(...values, 1)]
  const groupWidth = PLOT_WIDTH / Math.max(categories.length, 1)
  const barSlot = (groupWidth * 0.76) / Math.max(series.length, 1)
  const barWidth = Math.max(2, barSlot * 0.82)
  const categoryPositions = new Map(categories.map((value, index) => [value, index]))
  const seriesPositions = new Map(series.map((value, index) => [value, index]))

  return (
    <>
      <NumericYAxis encoding={y} domain={yDomain} />
      <CategoryXAxis encoding={x} categories={categories} />
      {records.map((record) => {
        const xValue = category(record.values[x.field])
        const seriesValue = color ? category(record.values[color.field]) : 'Value'
        const categoryIndex = categoryPositions.get(xValue) ?? 0
        const seriesIndex = seriesPositions.get(seriesValue) ?? 0
        const value = numeric(record.values[y.field]) ?? 0
        const height = Math.max(0, scaleLinear(value, yDomain, [0, PLOT_HEIGHT]))
        const barX =
          PLOT.left +
          categoryIndex * groupWidth +
          groupWidth * 0.12 +
          seriesIndex * barSlot +
          (barSlot - barWidth) / 2
        const barY = PLOT.top + PLOT_HEIGHT - height
        const label = `${x.title}: ${xValue}; ${y.title}: ${formatNumber(value)}${
          color ? `; ${color.title}: ${seriesValue}` : ''
        }`

        return (
          <rect
            key={record.id}
            className="chart-mark chart-bar"
            x={barX}
            y={barY}
            width={barWidth}
            height={height}
            rx={3}
            fill={seriesColor(seriesIndex)}
            tabIndex={0}
            aria-label={label}
            data-datum-id={record.id}
          >
            <title>{label}</title>
          </rect>
        )
      })}
      {color && <Legend title={color.title} values={series} />}
    </>
  )
}

function LineChart({
  visualization,
  records,
}: CartesianChartProps & { records: TabularDatum[] }) {
  const { x, y, color } = visualization.encoding
  const points = numericPoints(records, x.field, y.field, color?.field)
  if (points.length === 0) {
    return <ChartEmptyGraphic />
  }
  const xDomain = numericExtent(points.map((point) => point.x))
  const yDomain = numericExtent(points.map((point) => point.y), true)
  const series = [...new Set(points.map((point) => point.series))]

  return (
    <>
      <NumericYAxis encoding={y} domain={yDomain} />
      <NumericXAxis encoding={x} domain={xDomain} integerTicks />
      {series.map((seriesName, seriesIndex) => {
        const seriesPoints = points
          .filter((point) => point.series === seriesName)
          .sort((left, right) => left.x - right.x)
        const coordinates = seriesPoints.map((point) => pointCoordinates(point, xDomain, yDomain))
        const path = coordinates
          .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
          .join(' ')

        return (
          <g key={seriesName}>
            <path
              className="chart-line"
              d={path}
              fill="none"
              stroke={seriesColor(seriesIndex)}
            />
            {seriesPoints.map((point) => {
              const coordinates = pointCoordinates(point, xDomain, yDomain)
              const label = `${x.title}: ${formatChannelNumber(point.x, x)}; ${y.title}: ${formatNumber(point.y)}${
                color ? `; ${color.title}: ${seriesName}` : ''
              }`
              return (
                <circle
                  key={point.record.id}
                  className="chart-mark chart-point"
                  cx={coordinates.x}
                  cy={coordinates.y}
                  r={5}
                  fill={seriesColor(seriesIndex)}
                  tabIndex={0}
                  aria-label={label}
                  data-datum-id={point.record.id}
                >
                  <title>{label}</title>
                </circle>
              )
            })}
          </g>
        )
      })}
      {color && <Legend title={color.title} values={series} />}
    </>
  )
}

function ScatterChart({
  visualization,
  records,
}: CartesianChartProps & { records: TabularDatum[] }) {
  const { x, y, color, size } = visualization.encoding
  const points = numericPoints(records, x.field, y.field, color?.field)
  if (points.length === 0) {
    return <ChartEmptyGraphic />
  }
  const xDomain = paddedExtent(points.map((point) => point.x))
  const yDomain = paddedExtent(points.map((point) => point.y))
  const series = [...new Set(points.map((point) => point.series))]
  const seriesPositions = new Map(series.map((value, index) => [value, index]))
  const sizeValues = size
    ? points.map((point) => numeric(point.record.values[size.field]) ?? 0)
    : []
  const sizeDomain = numericExtent(sizeValues)

  return (
    <>
      <NumericYAxis encoding={y} domain={yDomain} />
      <NumericXAxis encoding={x} domain={xDomain} integerTicks={x.data_type === 'temporal'} />
      {points.map((point) => {
        const coordinates = pointCoordinates(point, xDomain, yDomain)
        const seriesIndex = seriesPositions.get(point.series) ?? 0
        const sizeValue = size ? numeric(point.record.values[size.field]) : null
        const radius = sizeValue === null ? 6 : scaleLinear(sizeValue, sizeDomain, [5, 14])
        const label = `${x.title}: ${formatChannelNumber(point.x, x)}; ${y.title}: ${formatNumber(point.y)}${
          color ? `; ${color.title}: ${point.series}` : ''
        }`
        return (
          <circle
            key={point.record.id}
            className="chart-mark chart-point"
            cx={coordinates.x}
            cy={coordinates.y}
            r={radius}
            fill={seriesColor(seriesIndex)}
            tabIndex={0}
            aria-label={label}
            data-datum-id={point.record.id}
          >
            <title>{label}</title>
          </circle>
        )
      })}
      {color && <Legend title={color.title} values={series} />}
    </>
  )
}

function NumericYAxis({
  encoding,
  domain,
}: {
  encoding: ChannelEncoding
  domain: [number, number]
}) {
  return (
    <g className="chart-axis">
      {tickValues(domain).map((tick) => {
        const y = scaleLinear(tick, domain, [PLOT.top + PLOT_HEIGHT, PLOT.top])
        return (
          <g key={tick}>
            <line className="chart-grid-line" x1={PLOT.left} x2={PLOT.left + PLOT_WIDTH} y1={y} y2={y} />
            <text x={PLOT.left - 10} y={y + 4} textAnchor="end">
              {formatNumber(tick)}
            </text>
          </g>
        )
      })}
      <text
        className="chart-axis-title"
        x={-(PLOT.top + PLOT_HEIGHT / 2)}
        y={15}
        textAnchor="middle"
        transform="rotate(-90)"
      >
        {encoding.title}{encoding.unit ? ` (${encoding.unit})` : ''}
      </text>
    </g>
  )
}

function CategoryXAxis({
  encoding,
  categories,
}: {
  encoding: ChannelEncoding
  categories: string[]
}) {
  const groupWidth = PLOT_WIDTH / Math.max(categories.length, 1)
  const labelStep = Math.max(1, Math.ceil(categories.length / 10))

  return (
    <g className="chart-axis">
      {categories.map((value, index) =>
        index % labelStep === 0 ? (
          <text
            key={value}
            x={PLOT.left + index * groupWidth + groupWidth / 2}
            y={PLOT.top + PLOT_HEIGHT + 24}
            textAnchor="middle"
          >
            {truncateLabel(value, categories.length > 7 ? 10 : 18)}
          </text>
        ) : null,
      )}
      <text
        className="chart-axis-title"
        x={PLOT.left + PLOT_WIDTH / 2}
        y={CHART_HEIGHT - 12}
        textAnchor="middle"
      >
        {encoding.title}
      </text>
    </g>
  )
}

function NumericXAxis({
  encoding,
  domain,
  integerTicks = false,
}: {
  encoding: ChannelEncoding
  domain: [number, number]
  integerTicks?: boolean
}) {
  const ticks = tickValues(domain).map((tick) => (integerTicks ? Math.round(tick) : tick))
  return (
    <g className="chart-axis">
      {[...new Set(ticks)].map((tick) => {
        const x = scaleLinear(tick, domain, [PLOT.left, PLOT.left + PLOT_WIDTH])
        return (
          <text key={tick} x={x} y={PLOT.top + PLOT_HEIGHT + 24} textAnchor="middle">
            {formatChannelNumber(tick, encoding)}
          </text>
        )
      })}
      <text
        className="chart-axis-title"
        x={PLOT.left + PLOT_WIDTH / 2}
        y={CHART_HEIGHT - 12}
        textAnchor="middle"
      >
        {encoding.title}{encoding.unit ? ` (${encoding.unit})` : ''}
      </text>
    </g>
  )
}

function Legend({ title, values }: { title: string; values: string[] }) {
  return (
    <g className="chart-legend" transform={`translate(${PLOT.left}, 4)`}>
      <text x={0} y={7}>{title}</text>
      {values.slice(0, 6).map((value, index) => (
        <g key={value} transform={`translate(${92 + index * 94}, 0)`}>
          <circle cx={0} cy={4} r={4} fill={seriesColor(index)} />
          <text x={9} y={7}>{truncateLabel(value, 11)}</text>
        </g>
      ))}
    </g>
  )
}

function numericPoints(
  records: TabularDatum[],
  xField: string,
  yField: string,
  seriesField?: string,
): NumericPoint[] {
  return records.flatMap((record) => {
    const x = numeric(record.values[xField])
    const y = numeric(record.values[yField])
    if (x === null || y === null) {
      return []
    }
    return [{ record, x, y, series: seriesField ? category(record.values[seriesField]) : 'Value' }]
  })
}

function pointCoordinates(
  point: NumericPoint,
  xDomain: [number, number],
  yDomain: [number, number],
) {
  return {
    x: scaleLinear(point.x, xDomain, [PLOT.left, PLOT.left + PLOT_WIDTH]),
    y: scaleLinear(point.y, yDomain, [PLOT.top + PLOT_HEIGHT, PLOT.top]),
  }
}

function paddedExtent(values: number[]): [number, number] {
  const domain = numericExtent(values)
  const padding = (domain[1] - domain[0]) * 0.06
  return [domain[0] - padding, domain[1] + padding]
}

function formatChannelNumber(value: number, encoding: ChannelEncoding): string {
  return encoding.data_type === 'temporal' ? String(Math.round(value)) : formatNumber(value)
}

function ChartEmptyGraphic() {
  return (
    <text className="chart-empty-label" x={CHART_WIDTH / 2} y={CHART_HEIGHT / 2} textAnchor="middle">
      No numeric data points to display
    </text>
  )
}

function ChartEmpty() {
  return <div className="chart-empty">No data points were returned for this visualization.</div>
}
