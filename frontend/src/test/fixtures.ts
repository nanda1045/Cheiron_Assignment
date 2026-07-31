import type {
  ClarificationResponse,
  ErrorResponse,
  SuccessResponse,
} from '../api/types.ts'

export const successResponse: SuccessResponse = {
  schema_version: '1.0',
  request_id: '81cbeb65-b8cc-437f-a245-73cb734d10b9',
  status: 'ok',
  query: {
    original: 'How many breast cancer trials exist by phase?',
    interpretation: 'Count interventional breast cancer studies and group them by phase.',
    structured_filters_authoritative: true,
    warnings: [],
  },
  plan: {},
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
    planner: { mode: 'claude', model: 'claude-test', capability_limited: false },
    record_counts: { matched: 52, retrieved: 52, used: 52, excluded: 0 },
    completeness: { status: 'complete', is_complete: true, pages_retrieved: 1, reason: null },
    duration_ms: 417,
    warnings: [],
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
    context: {},
  },
}
