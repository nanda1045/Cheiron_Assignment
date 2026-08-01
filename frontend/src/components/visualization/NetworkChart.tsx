import type { NetworkVisualization } from '../../api/types.ts'
import type { KeyboardEvent } from 'react'
import {
  CHART_HEIGHT,
  CHART_WIDTH,
  formatNumber,
  numericExtent,
  scaleLinear,
  seriesColor,
  truncateLabel,
} from './chartMath.ts'
import {
  edgeEvidenceTarget,
  isEvidenceActivationKey,
  nodeEvidenceTarget,
  type EvidenceTarget,
} from './evidenceSelection.ts'

interface NetworkChartProps {
  visualization: NetworkVisualization
  selectedTargetKey?: string | null
  onSelectTarget?: (target: EvidenceTarget) => void
}

interface NodePosition {
  x: number
  y: number
}

export function NetworkChart({
  visualization,
  selectedTargetKey = null,
  onSelectTarget = () => undefined,
}: NetworkChartProps) {
  const { nodes, edges } = visualization.data
  if (nodes.length === 0) {
    return <div className="chart-empty">No network nodes were returned for this visualization.</div>
  }

  const center = { x: CHART_WIDTH / 2, y: CHART_HEIGHT / 2 }
  const radius = Math.min(CHART_WIDTH, CHART_HEIGHT) * 0.34
  const positions = new Map<string, NodePosition>(
    nodes.map((node, index) => {
      const angle = (index / nodes.length) * Math.PI * 2 - Math.PI / 2
      return [
        node.id,
        {
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius,
        },
      ]
    }),
  )
  const nodeDomain = numericExtent(nodes.map((node) => node.value))
  const maxWeight = Math.max(...edges.map((edge) => edge.weight), 1)
  const entityTypes = [...new Set(nodes.map((node) => node.entity_type))]
  const entityPositions = new Map(entityTypes.map((value, index) => [value, index]))
  const nodesById = new Map(nodes.map((node) => [node.id, node]))

  return (
    <figure className="chart-shell chart-shell--network">
      <svg
        className="evidence-chart network-chart"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="group"
        aria-label={`${visualization.title}. ${visualization.description}`}
      >
        <g className="network-edges">
          {edges.map((edge) => {
            const source = positions.get(edge.source)
            const target = positions.get(edge.target)
            if (!source || !target) {
              return null
            }
            const evidenceTarget = edgeEvidenceTarget(edge, nodesById)
            const label = `${evidenceTarget.title}: ${edge.weight} shared trials`
            const isSelected = evidenceTarget.key === selectedTargetKey
            return (
              <line
                key={edge.id}
                className={`chart-mark network-edge${isSelected ? ' chart-mark--selected' : ''}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                strokeWidth={1 + (edge.weight / maxWeight) * 6}
                tabIndex={0}
                role="button"
                aria-pressed={isSelected}
                aria-label={label}
                data-edge-id={edge.id}
                onClick={() => onSelectTarget(evidenceTarget)}
                onKeyDown={(event) =>
                  activateEvidenceTarget(event, evidenceTarget, onSelectTarget)
                }
              >
                <title>{label}</title>
              </line>
            )
          })}
        </g>
        <g className="network-nodes">
          {nodes.map((node) => {
            const position = positions.get(node.id) ?? center
            const typeIndex = entityPositions.get(node.entity_type) ?? 0
            const nodeRadius = scaleLinear(node.value, nodeDomain, [12, 24])
            const label = `${node.label}; ${node.entity_type}; ${formatNumber(node.value)} trials`
            const evidenceTarget = nodeEvidenceTarget(node)
            const isSelected = evidenceTarget.key === selectedTargetKey
            return (
              <g
                key={node.id}
                className={`chart-mark network-node${isSelected ? ' chart-mark--selected' : ''}`}
                tabIndex={0}
                role="button"
                aria-pressed={isSelected}
                aria-label={label}
                data-node-id={node.id}
                onClick={() => onSelectTarget(evidenceTarget)}
                onKeyDown={(event) =>
                  activateEvidenceTarget(event, evidenceTarget, onSelectTarget)
                }
              >
                <title>{label}</title>
                <circle
                  cx={position.x}
                  cy={position.y}
                  r={nodeRadius}
                  fill={seriesColor(typeIndex)}
                />
                <text x={position.x} y={position.y + nodeRadius + 15} textAnchor="middle">
                  {truncateLabel(node.label, 16)}
                </text>
              </g>
            )
          })}
        </g>
        <g className="chart-legend" transform="translate(24, 20)">
          {entityTypes.slice(0, 6).map((entityType, index) => (
            <g key={entityType} transform={`translate(0, ${index * 18})`}>
              <circle cx={0} cy={0} r={4} fill={seriesColor(index)} />
              <text x={10} y={3}>{truncateLabel(entityType, 18)}</text>
            </g>
          ))}
        </g>
      </svg>
      <figcaption>
        Interactive network. Select a node or connection to inspect its value and provenance.
      </figcaption>
    </figure>
  )
}

function activateEvidenceTarget(
  event: KeyboardEvent<SVGElement>,
  target: EvidenceTarget,
  onSelectTarget: (target: EvidenceTarget) => void,
) {
  if (isEvidenceActivationKey(event.key)) {
    event.preventDefault()
    onSelectTarget(target)
  }
}
