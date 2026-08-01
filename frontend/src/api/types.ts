export type ScalarValue = string | number | boolean | null

export type VisualizationType =
  | 'bar_chart'
  | 'grouped_bar_chart'
  | 'time_series'
  | 'histogram'
  | 'scatter_plot'
  | 'network_graph'

export interface QueryRequest {
  schema_version: '1.0'
  query: string
  filters?: Record<string, unknown>
  options: {
    include_citations: boolean
    max_studies: number
  }
}

export interface ChannelEncoding {
  field: string
  data_type: 'nominal' | 'ordinal' | 'quantitative' | 'temporal'
  title: string
  unit: string | null
  sort: 'ascending' | 'descending' | ScalarValue[] | null
}

export interface CartesianEncoding {
  x: ChannelEncoding
  y: ChannelEncoding
  color: ChannelEncoding | null
  size: ChannelEncoding | null
}

export interface TabularDatum {
  id: string
  values: Record<string, ScalarValue>
  citation_ids: string[]
}

export interface NetworkNode {
  id: string
  label: string
  entity_type: string
  value: number
  citation_ids: string[]
}

export interface NetworkEdge {
  id: string
  source: string
  target: string
  weight: number
  citation_ids: string[]
}

export interface CartesianVisualization {
  type: Exclude<VisualizationType, 'network_graph'>
  title: string
  description: string
  encoding: CartesianEncoding
  data: {
    kind: 'tabular'
    records: TabularDatum[]
  }
}

export interface NetworkVisualization {
  type: 'network_graph'
  title: string
  description: string
  encoding: Record<string, string>
  data: {
    kind: 'network'
    nodes: NetworkNode[]
    edges: NetworkEdge[]
  }
}

export type Visualization = CartesianVisualization | NetworkVisualization

export interface Citation {
  id: string
  nct_id: string
  study_url: string
  evidence: Array<{
    field_path: string
    value: ScalarValue | ScalarValue[]
  }>
}

interface SuccessResponseBase {
  schema_version: '1.0'
  request_id: string
  status: 'ok'
  query: {
    original: string
    interpretation: string
    structured_filters_authoritative: boolean
    warnings: string[]
  }
  plan: Record<string, unknown>
  provenance: {
    source: {
      name: 'ClinicalTrials.gov'
      api_version: string
      data_timestamp: string
      retrieved_at: string
      endpoint: string
    }
    citations: Record<string, Citation>
  }
  meta: {
    planner: {
      mode: string
      model: string | null
      capability_limited: boolean
    }
    record_counts: {
      matched: number
      retrieved: number
      used: number
      excluded: number
    }
    completeness: {
      status: string
      is_complete: boolean
      pages_retrieved: number
      reason: string | null
    }
    duration_ms: number
    warnings: string[]
  }
}

export interface VisualizationSuccessResponse extends SuccessResponseBase {
  result_type: 'visualization'
  visualization: Visualization
  answer: null
}

export interface ScalarAnswerSuccessResponse extends SuccessResponseBase {
  result_type: 'scalar_answer'
  visualization: null
  answer: {
    kind: 'scalar'
    title: string
    text: string
    value: number | null
    unit: string | null
    citation_ids: string[]
  }
}

export type SuccessResponse = VisualizationSuccessResponse | ScalarAnswerSuccessResponse

export interface ClarificationResponse {
  schema_version: '1.0'
  request_id: string
  status: 'clarification_required'
  clarification: {
    question: string
    missing_fields: string[]
    suggestions: string[]
  }
}

export interface ErrorResponse {
  schema_version: '1.0'
  request_id: string
  status: 'error'
  error: {
    code: string
    message: string
    retryable: boolean
    context: Record<string, ScalarValue>
  }
}

export interface UnsupportedResponse {
  schema_version: '1.0'
  request_id: string
  status: 'unsupported'
  reason: string
  suggestions: string[]
}

export type QueryResponse =
  | SuccessResponse
  | ClarificationResponse
  | UnsupportedResponse
  | ErrorResponse
