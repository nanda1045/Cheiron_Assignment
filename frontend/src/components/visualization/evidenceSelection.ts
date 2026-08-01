import type {
  CartesianVisualization,
  NetworkEdge,
  NetworkNode,
  ScalarValue,
  TabularDatum,
} from '../../api/types.ts'

export type EvidenceTargetKind = 'answer' | 'datum' | 'node' | 'edge'

export interface EvidenceAttribute {
  label: string
  value: ScalarValue
}

export interface EvidenceTarget {
  key: string
  kind: EvidenceTargetKind
  title: string
  attributes: EvidenceAttribute[]
  citationIds: string[]
}

export function datumEvidenceTarget(
  record: TabularDatum,
  visualization: CartesianVisualization,
): EvidenceTarget {
  const encodings = [
    visualization.encoding.x,
    visualization.encoding.y,
    visualization.encoding.color,
    visualization.encoding.size,
  ].filter((encoding) => encoding !== null)
  const attributes = encodings.map((encoding) => ({
    label: encoding.title,
    value: record.values[encoding.field] ?? null,
  }))
  const primary = attributes[0]

  return {
    key: `datum:${record.id}`,
    kind: 'datum',
    title: primary ? `${primary.label}: ${formatTargetValue(primary.value)}` : record.id,
    attributes,
    citationIds: record.citation_ids,
  }
}

export function nodeEvidenceTarget(node: NetworkNode): EvidenceTarget {
  return {
    key: `node:${node.id}`,
    kind: 'node',
    title: node.label,
    attributes: [
      { label: 'Entity type', value: node.entity_type },
      { label: 'Connected trials', value: node.value },
    ],
    citationIds: node.citation_ids,
  }
}

export function edgeEvidenceTarget(
  edge: NetworkEdge,
  nodes: Map<string, NetworkNode>,
): EvidenceTarget {
  const source = nodes.get(edge.source)?.label ?? edge.source
  const target = nodes.get(edge.target)?.label ?? edge.target
  return {
    key: `edge:${edge.id}`,
    kind: 'edge',
    title: `${source} ↔ ${target}`,
    attributes: [{ label: 'Shared trials', value: edge.weight }],
    citationIds: edge.citation_ids,
  }
}

export function isEvidenceActivationKey(key: string): boolean {
  return key === 'Enter' || key === ' '
}

function formatTargetValue(value: ScalarValue): string {
  if (value === null) {
    return 'Unknown'
  }
  return String(value)
}
