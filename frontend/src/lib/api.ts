const BASE = '/api/v1/policies';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

export interface PolicyBankItem {
  payer: string;
  medication: string;
  latest_version: string;
  version_count: number;
  last_updated: string;
  extraction_quality: string;
  source_filenames?: string[];
}

export interface PolicyVersion {
  version: string;
  cached_at: string;
  content_hash: string;
  id: string;
  source_filename?: string;
  upload_notes?: string;
  effective_date?: string;
  effective_year?: number;
}

export interface DiffSummaryResponse {
  diff: any;
  summary: string;
}

export interface AssistantResponse {
  answer: string;
  sources?: string[];
  follow_up_questions?: string[];
  citations?: Array<{ policy?: string; criteria_id?: string; text?: string }>;
  confidence?: number;
  session_id?: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
  platform: string;
  components: Record<string, boolean>;
}

export interface UploadResponse {
  status: string;
  version: string;
  cache_id: string;
  extraction_quality: string;
  criteria_count: number;
  indications_count: number;
}

export interface InferMetadataResponse {
  payer_name: string;
  medication_name: string;
  effective_date: string;
}

export interface CrossPayerResponse {
  medication: string;
  payers_compared: string[];
  executive_summary?: string;
  restrictiveness_ranking?: Array<{ payer: string; rank: number; rationale: string; key_criteria?: string[] }>;
  criteria_comparison?: Array<{ dimension: string; differences: any[] }>;
  unique_requirements?: Array<{ payer: string; requirement: string; clinical_impact: string; criterion_id?: string; rationale?: string }>;
  coverage_gaps?: Array<{ indication: string; covered_by: string[]; not_covered_by: string[]; impact: string }>;
  prescriber_requirements?: Array<{ payer: string; indications_requiring_specialist: string[]; specialist_types: string[]; criterion_ids?: string[] }>;
  recommended_actions?: Array<string | { action: string; payer?: string; criterion_id?: string; rationale?: string }>;
  data_quality_notes?: string[];
  confidence?: number;
  error?: string;
}

export interface LLMMetricsResponse {
  by_provider: Array<{
    provider: string;
    total_calls: number;
    total_input_tokens: number;
    total_output_tokens: number;
    avg_latency_ms: number;
  }>;
  by_task: Array<{
    task_category: string;
    total_calls: number;
    total_input_tokens: number;
    total_output_tokens: number;
  }>;
  total_calls: number;
}

export interface AppealStrategyResponse {
  denial_analysis?: {
    denial_reason: string;
    denial_category: string;
    policy_gaps_exploited: string[];
    weaknesses_in_denial: string[];
  };
  appeal_strategy?: {
    primary_argument: string;
    supporting_arguments: string[];
    clinical_evidence: Array<{ source: string; relevance: string; strength: string }>;
    policy_citations: Array<{ section: string; text: string; argument: string }>;
  };
  peer_to_peer_talking_points?: string[];
  documentation_to_gather?: Array<{ document_type: string; purpose: string; priority: string }>;
  recommended_appeal_level?: string;
  success_likelihood?: number;
  confidence?: number;
  payer?: string;
  medication?: string;
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  getPolicyBank: () =>
    request<{ policies: PolicyBankItem[] }>(`${BASE}/bank`).then(r => r.policies || []),

  getAvailablePolicies: () =>
    request<{ policies: any[] }>(`${BASE}/available`).then(r => r.policies || []),

  getPolicyVersions: (payer: string, medication: string) =>
    request<{ versions: PolicyVersion[] }>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/versions`).then(r => r.versions || []),

  getPolicyContent: (payer: string, medication: string) =>
    request<{ content: string; payer: string; medication: string }>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}`),

  getDigitizedPolicy: (payer: string, medication: string) =>
    request<any>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/digitized`),

  getDiffSummary: (payer: string, medication: string, oldVersion: string, newVersion: string) =>
    request<DiffSummaryResponse>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/diff-summary`, {
      method: 'POST',
      body: JSON.stringify({ old_version: oldVersion, new_version: newVersion }),
    }),

  getDiff: (payer: string, medication: string, oldVersion: string, newVersion: string) =>
    request<any>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/diff`, {
      method: 'POST',
      body: JSON.stringify({ old_version: oldVersion, new_version: newVersion }),
    }),

  getImpact: (payer: string, medication: string, oldVersion?: string, newVersion?: string) =>
    request<any>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/impact`, {
      method: 'POST',
      body: JSON.stringify({ old_version: oldVersion, new_version: newVersion }),
    }),

  inferMetadata: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${BASE}/infer-metadata`, { method: 'POST', body: formData })
      .then(r => { if (!r.ok) throw new Error('Metadata inference failed'); return r.json() as Promise<InferMetadataResponse>; });
  },

  uploadPolicy: (file: File, payerName: string, medicationName: string, amendmentNotes?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('payer_name', payerName);
    formData.append('medication_name', medicationName);
    if (amendmentNotes) formData.append('amendment_notes', amendmentNotes);
    return fetch(`${BASE}/upload`, { method: 'POST', body: formData })
      .then(r => { if (!r.ok) throw new Error('Upload failed'); return r.json() as Promise<UploadResponse>; });
  },

  queryAssistant: (question: string, payerFilter?: string, medicationFilter?: string, sessionId?: string) =>
    request<AssistantResponse>(`${BASE}/assistant/query`, {
      method: 'POST',
      body: JSON.stringify({
        question,
        payer_filter: payerFilter || undefined,
        medication_filter: medicationFilter || undefined,
        session_id: sessionId || undefined,
      }),
    }),

  streamAssistant: async function* (
    question: string,
    payerFilter?: string,
    medicationFilter?: string,
    sessionId?: string,
  ): AsyncGenerator<string, void, undefined> {
    const res = await fetch(`${BASE}/assistant/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        payer_filter: payerFilter || undefined,
        medication_filter: medicationFilter || undefined,
        session_id: sessionId || undefined,
      }),
    });

    if (!res.ok) throw new Error('Stream request failed');

    const reader = res.body?.getReader();
    if (!reader) throw new Error('No reader available');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.done) return;
            if (data.error) throw new Error(data.error);
            if (data.token) yield data.token;
          } catch (e) {
            // Skip malformed SSE events
          }
        }
      }
    }
  },

  crossPayerAnalysis: (medication: string, payers?: string[]) =>
    request<CrossPayerResponse>(`${BASE}/cross-payer-analysis`, {
      method: 'POST',
      body: JSON.stringify({ medication, payers: payers || undefined }),
    }),

  getLLMMetrics: () =>
    request<LLMMetricsResponse>(`${BASE}/metrics/llm`),

  getDiffCsvUrl: (payer: string, medication: string, oldVersion: string, newVersion: string) =>
    `${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/export/csv?old_version=${encodeURIComponent(oldVersion)}&new_version=${encodeURIComponent(newVersion)}`,

  generateAppealStrategy: (payer: string, medication: string, denialReason: string, patientInfo?: any) =>
    request<AppealStrategyResponse>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/appeal/strategy`, {
      method: 'POST',
      body: JSON.stringify({
        denial_reason: denialReason,
        patient_info: patientInfo || {},
      }),
    }),

  draftAppealLetter: (payer: string, medication: string, appealStrategy: any, patientInfo?: any, denialContext?: any) =>
    request<{ letter: string }>(`${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/appeal/letter`, {
      method: 'POST',
      body: JSON.stringify({
        appeal_strategy: appealStrategy,
        patient_info: patientInfo || {},
        denial_context: denialContext || {},
      }),
    }),

  getPdfUrl: (payer: string, medication: string) =>
    `${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/pdf`,

  checkPdfExists: async (payer: string, medication: string): Promise<boolean> => {
    try {
      const url = `${BASE}/${encodeURIComponent(payer)}/${encodeURIComponent(medication)}/pdf`;
      let res = await fetch(url, { method: 'HEAD' });
      if (res.status === 405) {
        res = await fetch(url, { method: 'GET', headers: { Range: 'bytes=0-0' } });
      }
      return res.ok || res.status === 206;
    } catch { return false; }
  },
};
