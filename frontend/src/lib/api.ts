import {
  DashboardSummary,
  Inspection,
  PackageImage,
  ComplianceResult,
  DefectInspection,
  DefectAnalyzeResult,
  DefectDetection,
  DefectAnalytics,
  DefectLogItem,
  DefectDetectorStatus,
  LiveFrameResult,
  AuthUser,
  Job,
  PlantNode,
  Product,
  ManagedUser,
  EdgeDevice,
  ReviewTask,
  ReviewTaskDetail,
  ReviewStats,
  ModelVersionInfo,
  ModelEventInfo,
  DatasetVersionInfo,
  DriftStation,
  LearningOverview
} from './types';
import { clearSession, getToken } from './auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080/api/v1';
const BACKEND_BASE = API_BASE.replace(/\/api\/v1\/?$/, '');

/** Resolves a signed file link returned by the API (e.g. image.file_url) to an absolute URL. */
export function getStorageUrl(fileUrl?: string | null): string {
  if (!fileUrl) return '';
  if (fileUrl.startsWith('http') || fileUrl.startsWith('data:') || fileUrl.startsWith('blob:')) return fileUrl;
  return fileUrl.startsWith('/') ? `${BACKEND_BASE}${fileUrl}` : fileUrl;
}

export function imageSrc(image?: { file_url?: string | null } | null): string {
  return getStorageUrl(image?.file_url);
}

async function postForm<T>(url: string, formData: FormData): Promise<T> {
  return fetchJson<T>(url, { method: 'POST', body: formData });
}

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getToken();
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 401 && typeof window !== 'undefined' && !url.endsWith('/auth/login')) {
    clearSession();
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
  }
  return res;
}

/** Downloads an authenticated file (e.g. a PDF report) and opens it in a new tab. */
export async function openAuthenticatedFile(url: string): Promise<void> {
  const tab = window.open('', '_blank');
  const res = await authFetch(url, { headers: { Accept: '*/*' } });
  if (!res.ok) {
    tab?.close();
    throw new Error(`Download failed (HTTP ${res.status})`);
  }
  const blobUrl = URL.createObjectURL(await res.blob());
  if (tab) tab.location.href = blobUrl;
  else window.location.href = blobUrl;
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(url, init);

  if (!res.ok) {
    let errorDetail = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const errorJson = await res.json();
      if (errorJson.detail) {
        errorDetail = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return res.json() as Promise<T>;
}

export const api = {
  // Demo Seeding
  async seedDemoData(): Promise<any> {
    return fetchJson(`${API_BASE}/demo/seed`, {
      method: 'POST',
    });
  },

  // RAG Question Answering
  async askRuleBook(query: string): Promise<{
    answer: string;
    citations: Array<{ source: string; page: number; text_snippet: string }>;
  }> {
    return fetchJson(`${API_BASE}/rag/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
  },

  // Dashboard
  async getDashboardSummary(): Promise<DashboardSummary> {
    return fetchJson<DashboardSummary>(`${API_BASE}/dashboard/summary`);
  },

  // Inspections CRUD & Lifecycle
  async listInspections(params?: { outcome?: string; search?: string }): Promise<Inspection[]> {
    const url = new URL(`${API_BASE}/inspections`);
    if (params?.outcome) url.searchParams.set('outcome', params.outcome);
    if (params?.search) url.searchParams.set('search', params.search);
    return fetchJson<Inspection[]>(url.toString());
  },

  async createInspection(data: {
    product_name?: string;
    brand_name?: string;
    category?: string;
    location?: string;
    notes?: string;
  }): Promise<Inspection> {
    return fetchJson<Inspection>(`${API_BASE}/inspections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async getInspection(id: string): Promise<Inspection> {
    return fetchJson<Inspection>(`${API_BASE}/inspections/${id}`);
  },

  async uploadImage(inspectionId: string, file: File, surfaceType: string): Promise<PackageImage> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('surface_type', surfaceType);

    const res = await authFetch(`${API_BASE}/inspections/${inspectionId}/images`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Upload failed: ${err}`);
    }

    return res.json();
  },

  async captureCameraImage(
    inspectionId: string,
    base64Data: string,
    surfaceType: string
  ): Promise<PackageImage> {
    return fetchJson<PackageImage>(`${API_BASE}/inspections/${inspectionId}/images/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_base64: base64Data,
        surface_type: surfaceType,
      }),
    });
  },

  async processInspection(id: string): Promise<Inspection> {
    return fetchJson<Inspection>(`${API_BASE}/inspections/${id}/process`, {
      method: 'POST',
    });
  },

  async reprocessInspection(id: string): Promise<Inspection> {
    return fetchJson<Inspection>(`${API_BASE}/inspections/${id}/reprocess`, {
      method: 'POST',
    });
  },

  async finalizeInspection(
    id: string,
    data: { final_remarks?: string; override_status?: string }
  ): Promise<Inspection> {
    return fetchJson<Inspection>(`${API_BASE}/inspections/${id}/finalize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  // Heatmap & Evidence
  async getImageHeatmap(
    inspectionId: string,
    imageId: string
  ): Promise<{ heatmap_data_url: string }> {
    return fetchJson<{ heatmap_data_url: string }>(
      `${API_BASE}/inspections/${inspectionId}/heatmap/${imageId}`
    );
  },

  // AI Deep Analysis & LLM Status
  async getDeepAiAnalysis(id: string): Promise<any> {
    return fetchJson(`${API_BASE}/inspections/${id}/ai-analysis`, {
      method: 'POST',
    });
  },

  async getLlmStatus(): Promise<any> {
    return fetchJson(`${API_BASE}/llm/status`);
  },

  // Review Actions
  async submitReviewAction(
    inspectionId: string,
    actionData: {
      target_field: string;
      action_type: string;
      previous_value?: string;
      new_value?: string;
      reason?: string;
    }
  ): Promise<any> {
    return fetchJson(`${API_BASE}/reviews/${inspectionId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(actionData),
    });
  },

  // PDF Report URL helper
  getReportUrl(id: string): string {
    return `${API_BASE}/reports/${id}/report`;
  },

  // Inspector Statutory Tools
  async getRulesDatabase(): Promise<any> {
    return fetchJson(`${API_BASE}/tools/rules-database`);
  },

  async getSchedules(): Promise<any> {
    return fetchJson(`${API_BASE}/tools/schedules`);
  },

  async calculateMPE(quantity: number, unit: string): Promise<any> {
    return fetchJson(`${API_BASE}/tools/mpe-calculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity, unit }),
    });
  },

  async evaluateLotSampling(data: {
    lot_size: number;
    declared_quantity: number;
    unit: string;
    measured_weights: number[];
  }): Promise<any> {
    return fetchJson(`${API_BASE}/tools/lot-sample-evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async calculatePDPFont(data: {
    package_shape: string;
    height_cm: number;
    width_cm: number;
    depth_or_diameter_cm: number;
  }): Promise<any> {
    return fetchJson(`${API_BASE}/tools/pdp-font-check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },
};

export const defectApi = {
  async getStatus(): Promise<DefectDetectorStatus> {
    return fetchJson<DefectDetectorStatus>(`${API_BASE}/defects/status`);
  },

  async seedDemoData(): Promise<any> {
    return fetchJson(`${API_BASE}/defects/demo/seed`, { method: 'POST' });
  },

  async createInspection(data: {
    product_name?: string;
    brand_name?: string;
    category?: string;
    location?: string;
    notes?: string;
    product_id?: string;
    station_id?: string;
    shift?: string;
    batch_code?: string;
  }): Promise<DefectInspection> {
    return fetchJson<DefectInspection>(`${API_BASE}/defects/inspections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async listInspections(params?: { outcome?: string; search?: string }): Promise<DefectInspection[]> {
    const url = new URL(`${API_BASE}/defects/inspections`);
    if (params?.outcome) url.searchParams.set('outcome', params.outcome);
    if (params?.search) url.searchParams.set('search', params.search);
    return fetchJson<DefectInspection[]>(url.toString());
  },

  async getInspection(id: string): Promise<DefectInspection> {
    return fetchJson<DefectInspection>(`${API_BASE}/defects/inspections/${id}`);
  },

  async uploadReference(inspectionId: string, file: File): Promise<PackageImage> {
    const formData = new FormData();
    formData.append('file', file);
    return postForm<PackageImage>(`${API_BASE}/defects/inspections/${inspectionId}/reference`, formData);
  },

  async analyzeImage(inspectionId: string, file: File, surfaceType = 'SURFACE'): Promise<DefectAnalyzeResult> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('surface_type', surfaceType);
    return postForm<DefectAnalyzeResult>(`${API_BASE}/defects/inspections/${inspectionId}/analyze`, formData);
  },

  async analyzeCapture(inspectionId: string, base64Data: string, surfaceType = 'SURFACE'): Promise<DefectAnalyzeResult> {
    return fetchJson<DefectAnalyzeResult>(`${API_BASE}/defects/inspections/${inspectionId}/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_base64: base64Data, surface_type: surfaceType }),
    });
  },

  /** Queues video analysis as a background job; use jobsApi.waitFor() to follow progress. */
  async analyzeVideo(
    inspectionId: string,
    file: File,
    options?: { sampleFps?: number; maxFrames?: number }
  ): Promise<Job> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('sample_fps', String(options?.sampleFps ?? 2));
    formData.append('max_frames', String(options?.maxFrames ?? 40));
    return postForm<Job>(`${API_BASE}/defects/inspections/${inspectionId}/video`, formData);
  },

  async analyzeLiveFrame(base64Data: string, options?: { maxSide?: number; inspectionId?: string }): Promise<LiveFrameResult> {
    return fetchJson<LiveFrameResult>(`${API_BASE}/defects/analyze-frame`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_base64: base64Data,
        max_side: options?.maxSide ?? 640,
        inspection_id: options?.inspectionId,
      }),
    });
  },

  async deleteImage(inspectionId: string, imageId: string): Promise<any> {
    return fetchJson(`${API_BASE}/defects/inspections/${inspectionId}/images/${imageId}`, { method: 'DELETE' });
  },

  async submitFeedback(
    detectionId: string,
    data: { action: 'CONFIRM' | 'REJECT' | 'RELABEL'; defect_type?: string; note?: string }
  ): Promise<{ detection: DefectDetection; overall_outcome: string; training_sample_saved: boolean }> {
    return fetchJson(`${API_BASE}/defects/detections/${detectionId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async finalizeInspection(
    id: string,
    data: { final_remarks?: string; override_outcome?: string }
  ): Promise<DefectInspection> {
    return fetchJson<DefectInspection>(`${API_BASE}/defects/inspections/${id}/finalize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async getOverlay(inspectionId: string, imageId: string): Promise<{ overlay_data_url: string }> {
    return fetchJson(`${API_BASE}/defects/inspections/${inspectionId}/overlay/${imageId}`);
  },

  getReportUrl(id: string): string {
    return `${API_BASE}/defects/inspections/${id}/report`;
  },

  async getAnalytics(params?: { days?: number; product?: string }): Promise<DefectAnalytics> {
    const url = new URL(`${API_BASE}/defects/analytics`);
    if (params?.days) url.searchParams.set('days', String(params.days));
    if (params?.product) url.searchParams.set('product', params.product);
    return fetchJson<DefectAnalytics>(url.toString());
  },

  async getLog(params?: {
    defect_type?: string;
    severity?: string;
    reviewer_status?: string;
    product?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ total: number; items: DefectLogItem[] }> {
    const url = new URL(`${API_BASE}/defects/log`);
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v));
    });
    return fetchJson(url.toString());
  },
};

export const authApi = {
  async login(email: string, password: string): Promise<{ access_token: string; user: AuthUser }> {
    return fetchJson(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
  },

  async me(): Promise<AuthUser> {
    return fetchJson<AuthUser>(`${API_BASE}/auth/me`);
  },

  async config(): Promise<{ environment: string; demo_accounts: Array<{ email: string; role: string; password: string }> }> {
    return fetchJson(`${API_BASE}/auth/config`);
  },
};

export const jobsApi = {
  async get(id: string): Promise<Job> {
    return fetchJson<Job>(`${API_BASE}/jobs/${id}`);
  },

  /** Polls a background job until it finishes; resolves with the final job or throws on failure. */
  async waitFor(id: string, onProgress?: (job: Job) => void, intervalMs = 1000): Promise<Job> {
    for (;;) {
      const job = await jobsApi.get(id);
      onProgress?.(job);
      if (job.status === 'SUCCEEDED') return job;
      if (job.status === 'FAILED') throw new Error(job.error || 'Background job failed');
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  },
};

export const orgApi = {
  async tree(): Promise<PlantNode[]> {
    return fetchJson<PlantNode[]>(`${API_BASE}/org/tree`);
  },
  async products(includeInactive = false): Promise<Product[]> {
    return fetchJson<Product[]>(`${API_BASE}/org/products${includeInactive ? '?include_inactive=true' : ''}`);
  },
  async createPlant(data: { name: string; location?: string }): Promise<PlantNode> {
    return fetchJson(`${API_BASE}/org/plants`, jsonBody('POST', data));
  },
  async createLine(data: { plant_id: string; name: string }): Promise<any> {
    return fetchJson(`${API_BASE}/org/lines`, jsonBody('POST', data));
  },
  async createStation(data: { line_id: string; name: string; camera_info?: string }): Promise<any> {
    return fetchJson(`${API_BASE}/org/stations`, jsonBody('POST', data));
  },
  async updateStation(id: string, data: { name?: string; is_active?: boolean }): Promise<any> {
    return fetchJson(`${API_BASE}/org/stations/${id}`, jsonBody('PATCH', data));
  },
  async createProduct(data: { sku: string; name: string; family?: string; material?: string }): Promise<Product> {
    return fetchJson(`${API_BASE}/org/products`, jsonBody('POST', data));
  },
  async updateProduct(id: string, data: Partial<Product>): Promise<Product> {
    return fetchJson(`${API_BASE}/org/products/${id}`, jsonBody('PATCH', data));
  },
};

export const adminApi = {
  async users(): Promise<ManagedUser[]> {
    return fetchJson<ManagedUser[]>(`${API_BASE}/admin/users`);
  },
  async createUser(data: { email: string; full_name: string; password: string; role: string }): Promise<ManagedUser> {
    return fetchJson(`${API_BASE}/admin/users`, jsonBody('POST', data));
  },
  async updateUser(id: string, data: { role?: string; is_active?: boolean; password?: string }): Promise<ManagedUser> {
    return fetchJson(`${API_BASE}/admin/users/${id}`, jsonBody('PATCH', data));
  },
  async devices(): Promise<EdgeDevice[]> {
    return fetchJson<EdgeDevice[]>(`${API_BASE}/admin/devices`);
  },
  async createDevice(data: { name: string; station_id?: string }): Promise<{ device: EdgeDevice; device_key: string }> {
    return fetchJson(`${API_BASE}/admin/devices`, jsonBody('POST', data));
  },
  async rotateDeviceKey(id: string): Promise<{ device: EdgeDevice; device_key: string }> {
    return fetchJson(`${API_BASE}/admin/devices/${id}/rotate-key`, { method: 'POST' });
  },
  async updateDevice(id: string, data: { is_active?: boolean; name?: string }): Promise<EdgeDevice> {
    return fetchJson(`${API_BASE}/admin/devices/${id}`, jsonBody('PATCH', data));
  },
};

export const reviewApi = {
  async queue(params?: { status?: string; reason?: string; limit?: number }): Promise<ReviewTask[]> {
    const url = new URL(`${API_BASE}/review/queue`);
    Object.entries(params || {}).forEach(([k, v]) => v !== undefined && v !== '' && url.searchParams.set(k, String(v)));
    return fetchJson<ReviewTask[]>(url.toString());
  },
  async stats(): Promise<ReviewStats> {
    return fetchJson<ReviewStats>(`${API_BASE}/review/stats`);
  },
  async task(id: string): Promise<ReviewTaskDetail> {
    return fetchJson<ReviewTaskDetail>(`${API_BASE}/review/tasks/${id}`);
  },
  async annotate(imageId: string, data: { defect_type: string; bbox: number[]; note?: string }): Promise<DefectDetection> {
    return fetchJson(`${API_BASE}/review/images/${imageId}/annotations`, jsonBody('POST', data));
  },
  async deleteAnnotation(detectionId: string): Promise<void> {
    const res = await authFetch(`${API_BASE}/review/annotations/${detectionId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Delete failed (HTTP ${res.status})`);
  },
  async complete(imageId: string, data?: { accept_pending?: boolean; note?: string }): Promise<any> {
    return fetchJson(`${API_BASE}/review/images/${imageId}/complete`, jsonBody('POST', data || {}));
  },
  async request(imageId: string, reason?: string): Promise<ReviewTask> {
    return fetchJson(`${API_BASE}/review/images/${imageId}/request`, jsonBody('POST', { reason }));
  },
  async skip(taskId: string): Promise<any> {
    return fetchJson(`${API_BASE}/review/tasks/${taskId}/skip`, { method: 'POST' });
  },
};

export const learningApi = {
  async overview(): Promise<LearningOverview> {
    return fetchJson<LearningOverview>(`${API_BASE}/learning/overview`);
  },
  async models(): Promise<ModelVersionInfo[]> {
    return fetchJson<ModelVersionInfo[]>(`${API_BASE}/learning/models`);
  },
  async model(id: string): Promise<ModelVersionInfo & { events: ModelEventInfo[] }> {
    return fetchJson(`${API_BASE}/learning/models/${id}`);
  },
  async datasets(): Promise<DatasetVersionInfo[]> {
    return fetchJson<DatasetVersionInfo[]>(`${API_BASE}/learning/datasets`);
  },
  async buildDataset(): Promise<Job> {
    return fetchJson<Job>(`${API_BASE}/learning/datasets`, { method: 'POST' });
  },
  async train(data?: { dataset_version_id?: string; notes?: string }): Promise<Job> {
    return fetchJson<Job>(`${API_BASE}/learning/models/train`, jsonBody('POST', data || {}));
  },
  async evaluate(id: string): Promise<Job> {
    return fetchJson<Job>(`${API_BASE}/learning/models/${id}/evaluate`, { method: 'POST' });
  },
  async startShadow(id: string, override_reason?: string): Promise<ModelVersionInfo> {
    return fetchJson(`${API_BASE}/learning/models/${id}/shadow`, jsonBody('POST', { override_reason }));
  },
  async stopShadow(id: string): Promise<ModelVersionInfo> {
    return fetchJson(`${API_BASE}/learning/models/${id}/shadow`, { method: 'DELETE' });
  },
  async promote(id: string, override_reason?: string): Promise<ModelVersionInfo> {
    return fetchJson(`${API_BASE}/learning/models/${id}/promote`, jsonBody('POST', { override_reason }));
  },
  async rollback(id: string): Promise<ModelVersionInfo> {
    return fetchJson(`${API_BASE}/learning/models/${id}/rollback`, { method: 'POST' });
  },
  async drift(): Promise<{ stations: DriftStation[]; thresholds: { watch: number; alert: number } }> {
    return fetchJson(`${API_BASE}/learning/drift`);
  },
  async events(): Promise<ModelEventInfo[]> {
    return fetchJson<ModelEventInfo[]>(`${API_BASE}/learning/events`);
  },
  async seedReviewed(count = 60): Promise<{ created: number }> {
    return fetchJson(`${API_BASE}/learning/demo/seed-reviewed`, jsonBody('POST', { count }));
  },
  datasetDownloadUrl(id: string): string {
    return `${API_BASE}/learning/datasets/${id}/download`;
  },
  modelDownloadUrl(id: string): string {
    return `${API_BASE}/learning/models/${id}/download`;
  },
};

function jsonBody(method: string, data: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) };
}
