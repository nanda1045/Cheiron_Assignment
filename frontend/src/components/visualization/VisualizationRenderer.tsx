import type { Visualization } from '../../api/types.ts'
import { CartesianChart } from './CartesianChart.tsx'
import type { EvidenceTarget } from './evidenceSelection.ts'
import { NetworkChart } from './NetworkChart.tsx'

interface VisualizationRendererProps {
  visualization: Visualization
  selectedTargetKey?: string | null
  onSelectTarget?: (target: EvidenceTarget) => void
}

export function VisualizationRenderer({
  visualization,
  selectedTargetKey = null,
  onSelectTarget = () => undefined,
}: VisualizationRendererProps) {
  if (visualization.type === 'network_graph') {
    return (
      <NetworkChart
        visualization={visualization}
        selectedTargetKey={selectedTargetKey}
        onSelectTarget={onSelectTarget}
      />
    )
  }
  return (
    <CartesianChart
      visualization={visualization}
      selectedTargetKey={selectedTargetKey}
      onSelectTarget={onSelectTarget}
    />
  )
}
