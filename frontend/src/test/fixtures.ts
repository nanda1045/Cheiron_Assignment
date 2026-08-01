import type {
  CartesianVisualization,
  ClarificationResponse,
  ErrorResponse,
  ScalarAnswerSuccessResponse,
  UnsupportedResponse,
  VisualizationSuccessResponse,
} from '../api/types.ts'

export const successResponse: VisualizationSuccessResponse = {
  schema_version: '1.0',
  request_id: '81cbeb65-b8cc-437f-a245-73cb734d10b9',
  status: 'ok',
  result_type: 'visualization',
  query: {
    original: 'How many breast cancer trials exist by phase?',
    interpretation: 'Count interventional breast cancer studies and group them by phase.',
    structured_filters_authoritative: true,
    warnings: [],
  },
  plan: {},
  answer: null,
  visualization: {
    type: 'bar_chart',
    title: 'Breast cancer trials by phase',
    description: 'Number of retrieved studies in each trial phase.',
    encoding: {
      x: {
        field: 'phase',
        data_type: 'ordinal',
        title: 'Trial phase',
        unit: null,
        sort: ['Phase 1', 'Phase 2', 'Phase 3'],
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
          id: 'phase-1',
          values: { phase: 'Phase 1', trial_count: 18 },
          citation_ids: ['cit-nct00000001'],
        },
        {
          id: 'phase-2',
          values: { phase: 'Phase 2', trial_count: 34 },
          citation_ids: ['cit-nct00000001'],
        },
      ],
    },
  },
  provenance: {
    source: {
      name: 'ClinicalTrials.gov',
      api_version: '2.0',
      data_timestamp: '2026-07-31T12:00:00Z',
      retrieved_at: '2026-07-31T12:01:00Z',
      endpoint: 'https://clinicaltrials.gov/api/v2/studies',
    },
    citations: {
      'cit-nct00000001': {
        id: 'cit-nct00000001',
        nct_id: 'NCT00000001',
        study_url: 'https://clinicaltrials.gov/study/NCT00000001',
        evidence: [{ field_path: 'protocolSection.identificationModule.nctId', value: 'NCT00000001' }],
      },
    },
  },
  meta: {
    planner: { mode: 'openai', model: 'gpt-5.4-mini', capability_limited: false },
    record_counts: { matched: 52, retrieved: 52, used: 52, excluded: 0 },
    completeness: { status: 'complete', is_complete: true, pages_retrieved: 1, reason: null },
    duration_ms: 417,
    warnings: [],
  },
}

export const scalarAnswerResponse: ScalarAnswerSuccessResponse = {
  ...successResponse,
  request_id: 'c141f21b-d7bb-4b52-9bf5-cf18e9268472',
  result_type: 'scalar_answer',
  query: {
    ...successResponse.query,
    original: 'How many recruiting breast cancer trials are there?',
    interpretation: 'Count distinct trials matching all requested filters.',
  },
  plan: { output_type: 'scalar_answer' },
  visualization: null,
  answer: {
    kind: 'scalar',
    title: 'Matching trial count',
    text: '18 matching clinical trials were found in the source snapshot.',
    value: 18,
    unit: 'trials',
    citation_ids: ['cit-nct00000001'],
  },
  meta: {
    ...successResponse.meta,
    record_counts: { matched: 18, retrieved: 18, used: 18, excluded: 0 },
  },
}

export const noResultsResponse: VisualizationSuccessResponse = {
  ...successResponse,
  request_id: 'f925e5b8-7128-4d76-81a7-55d07c16e895',
  visualization: {
    ...(successResponse.visualization as CartesianVisualization),
    data: { kind: 'tabular', records: [] },
  },
  provenance: {
    ...successResponse.provenance,
    citations: {},
  },
  meta: {
    ...successResponse.meta,
    record_counts: { matched: 0, retrieved: 0, used: 0, excluded: 0 },
  },
}

export const clarificationResponse: ClarificationResponse = {
  schema_version: '1.0',
  request_id: '7e6a8f7e-909d-4932-92fa-fc50b5a68ca3',
  status: 'clarification_required',
  clarification: {
    question: 'Which condition or intervention should the analysis focus on?',
    missing_fields: ['condition_or_intervention'],
    suggestions: ['Show trials by phase for glioblastoma.'],
  },
}

export const errorResponse: ErrorResponse = {
  schema_version: '1.0',
  request_id: '229d8f25-6c9e-4f02-b8a3-1265386cba4e',
  status: 'error',
  error: {
    code: 'source_unavailable',
    message: 'ClinicalTrials.gov is temporarily unavailable.',
    retryable: true,
    context: { provider: 'ClinicalTrials.gov' },
  },
}

export const plannerConfigurationErrorResponse: ErrorResponse = {
  schema_version: '1.0',
  request_id: '2ae72fb3-29c7-4177-afb5-62cf64d0743e',
  status: 'error',
  error: {
    code: 'planner_not_configured',
    message: 'The OpenAI planner is not configured with valid credentials.',
    retryable: false,
    context: { provider: 'OpenAI' },
  },
}

export const unsupportedResponse: UnsupportedResponse = {
  schema_version: '1.0',
  request_id: 'd50875f6-f2f8-4df3-b260-f4e0c74ff85f',
  status: 'unsupported',
  reason: 'Cheiron cannot infer treatment efficacy from registered trial metadata.',
  suggestions: ['Count recruiting melanoma trials.'],
}
