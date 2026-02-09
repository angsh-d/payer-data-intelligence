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
}

export interface PolicyVersion {
  version: string;
  cached_at: string;
  content_hash: string;
  id: string;
  source_filename?: string;
  upload_notes?: string;
}

export interface DiffSummaryResponse {
  diff: any;
  summary: string;
}

export interface AssistantResponse {
  answer: string;
  sources?: string[];
  follow_up_questions?: string[];
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

  queryAssistant: (question: string, payerFilter?: string, medicationFilter?: string) =>
    request<AssistantResponse>(`${BASE}/assistant/query`, {
      method: 'POST',
      body: JSON.stringify({
        question,
        payer_filter: payerFilter || undefined,
        medication_filter: medicationFilter || undefined,
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
