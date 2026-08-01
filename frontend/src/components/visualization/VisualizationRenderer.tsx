import type { Visualization } from '../../api/types.ts'
import { CartesianChart } from './CartesianChart.tsx'
import { NetworkChart } from './NetworkChart.tsx'

interface VisualizationRendererProps {
  visualization: Visualization
}

export function VisualizationRenderer({ visualization }: VisualizationRendererProps) {
  if (visualization.type === 'network_graph') {
    return <NetworkChart visualization={visualization} />
  }
  return <CartesianChart visualization={visualization} />
}
