import { API_BASE, fetchJson } from './api';

/* eslint-disable @typescript-eslint/no-explicit-any */
export interface Kpis {
  units: number;
  accepted: number;
  rejected: number;
  manual_review: number;
  first_pass_yield: number | null;
  rejection_rate: number | null;
  review_share: number | null;
  flagged_rate?: number | null;
  latency_ms_p50: number | null;
  synthetic_units: number;
}
export interface GroupRow extends Kpis {
  group: string;
  defects: number;
  top_defect: string | null;
}
export interface ParetoRow {
  defect_type: string;
  count: number;
  share: number;
  cumulative: number;
}
export interface TrendPoint {
  period: string;
  inspected: number;
  defective: number;
  rate: number;
  centre: number | null;
  ucl: number | null;
  out_of_control: boolean;
  first_pass_yield: number | null;
}
export interface Overview {
  window_days: number;
  kpis: Kpis;
  pareto: ParetoRow[];
  trend: TrendPoint[];
  by_machine: GroupRow[];
  by_shift: GroupRow[];
  by_batch: GroupRow[];
  by_product: GroupRow[];
  by_line: GroupRow[];
  severity: Record<string, number>;
  hotspot: { grid: number[][]; dominant_region: string | null; dominant_share: number };
}
export interface Finding {
  dimension: string;
  group: string;
  units: number;
  defective: number;
  rate: number;
  rate_elsewhere: number;
  odds_ratio: number;
  p_value: number;
  q_value: number;
  significant: boolean;
  interpretation: string;
}
export interface RootCause {
  note: string;
  units: number;
  flagged_units: number;
  findings: Finding[];
  significant: Finding[];
  hypotheses: { defect_type: string; count: number; hypotheses: string[]; checks: string[]; source: string }[];
  hotspot: Overview['hotspot'];
}
export interface Alert {
  id: string;
  kind: string;
  dimension: string | null;
  group: string | null;
  message: string;
  value: number | null;
  limit: number | null;
  status: string;
  created_at: string;
}
export interface Product {
  id: string;
  key: string;
  name: string;
  category: string;
  description: string | null;
  dimension_spec: { feature: string; nominal: number; minus: number; plus: number }[];
  decision_policy: Record<string, any>;
  calibration_id: string | null;
  anomaly_model: string | null;
  golden_references: { id: string; file_path: string; label: string | null; is_active: boolean }[];
}
export interface Line {
  id: string;
  code: string;
  name: string;
  belt_speed_mm_s: number;
  camera_to_diverter_mm: number;
  pitch_mm: number;
  actuator_kind: string;
  actuator_target: string | null;
  budget: Record<string, number>;
  machines: { id: string; code: string; name: string }[];
}
export interface Machine {
  id: string;
  code: string;
  name: string;
  line: string | null;
}
export interface Batch {
  id: string;
  code: string;
  product: string | null;
  product_id: string;
  status: string;
  planned_quantity: number | null;
  is_synthetic: boolean;
  started_at: string;
  closed_at: string | null;
  kpis: Kpis;
  top_defect: string | null;
}
export interface UnitDetection {
  id: string;
  defect_type: string;
  severity: string;
  confidence: number;
  bbox: number[];
  area_ratio: number;
  detector: string;
  metrics: Record<string, any>;
  reviewer_status: string;
  model_version: string | null;
  length_mm: number | null;
  width_mm: number | null;
  area_mm2: number | null;
}
export interface Unit {
  id: string;
  unit_code: string;
  product: string | null;
  batch: string | null;
  machine: string | null;
  line: string | null;
  shift: string | null;
  source: string;
  is_synthetic: boolean;
  decision: string;
  final_decision: string | null;
  reasons: string[];
  anomaly_score: number | null;
  dimensional: Record<string, any> | null;
  model_versions: Record<string, string | null>;
  streams: string[];
  latency_ms: number | null;
  inspected_at: string;
  image_path: string | null;
  heatmap_path: string | null;
  inspection_id: string | null;
  detections?: UnitDetection[];
  reject_events?: { actuator: string; status: string; fire_after_ms: number | null; at: string }[];
}
export interface Calibration {
  id: string;
  name: string;
  method: string;
  mm_per_px: number;
  created_at: string;
  details: { assumptions: string[]; reprojection_error_mm: number | null; points_used: number };
}
export interface ModelVersion {
  id: string;
  kind: string;
  product_key: string | null;
  version: string;
  status: string;
  metrics: Record<string, any> | null;
  gate_result: { passed: boolean; checks: { check: string; candidate: any; production?: any; limit?: number; passed: boolean; note?: string }[] } | null;
  parent_version: string | null;
  notes: string | null;
  created_at: string;
  promoted_at: string | null;
}
export interface LiveStats {
  session_id: string;
  mode: string;
  source: string;
  simulation: boolean;
  running: boolean;
  elapsed_s: number;
  frames_received: number;
  frames_tracked: number;
  frames_dropped: number;
  ingest_fps: number;
  tracking_fps: number;
  tracker_ms_p50: number | null;
  inspect_ms_p50: number | null;
  inspect_ms_p95: number | null;
  units_seen: number;
  units_inspected: number;
  units_overflowed: number;
  decisions: Record<string, number>;
  throughput_units_min: number;
  actuator: string;
  budget: Record<string, number> | null;
  recent: {
    unit_code: string;
    unit_id: string;
    track_id: number;
    decision: string;
    reasons: string[];
    latency_ms: number;
    reject: string | null;
    defects: { type: string; severity: string; confidence: number }[];
  }[];
  errors: string[];
}

const json = (body: unknown, method = 'POST'): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') s.set(k, String(v));
  });
  const text = s.toString();
  return text ? `?${text}` : '';
}

const P = `${API_BASE}/production`;
const A = `${API_BASE}/analytics`;
const L = `${API_BASE}/learning`;
const M = `${API_BASE}/metrology`;

export const analyticsApi = {
  overview: (params: Record<string, string | number | boolean | undefined> = {}) => fetchJson<Overview>(`${A}/overview${query(params)}`),
  rootCause: (params: Record<string, string | number | boolean | undefined> = {}) => fetchJson<RootCause>(`${A}/root-cause${query(params)}`),
  alerts: () => fetchJson<Alert[]>(`${A}/alerts`),
  setAlert: (id: string, status: string) => fetchJson(`${A}/alerts/${id}`, json({ status })),
  actions: () => fetchJson<any[]>(`${A}/corrective-actions`),
  addAction: (body: Record<string, string | undefined>) => fetchJson(`${A}/corrective-actions`, json(body)),
};

export const productionApi = {
  products: () => fetchJson<Product[]>(`${P}/products`),
  createProduct: (body: unknown) => fetchJson<Product>(`${P}/products`, json(body)),
  updateProduct: (id: string, body: unknown) => fetchJson<Product>(`${P}/products/${id}`, json(body, 'PUT')),
  addGolden: (id: string, file: File, label: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('label', label);
    return fetchJson<Product>(`${P}/products/${id}/golden`, { method: 'POST', body: form });
  },
  activateGolden: (id: string) => fetchJson<Product>(`${P}/golden/${id}/activate`, { method: 'POST' }),
  lines: () => fetchJson<Line[]>(`${P}/lines`),
  createLine: (body: unknown) => fetchJson(`${P}/lines`, json(body)),
  machines: () => fetchJson<Machine[]>(`${P}/machines`),
  createMachine: (body: unknown) => fetchJson(`${P}/machines`, json(body)),
  batches: () => fetchJson<Batch[]>(`${P}/batches`),
  createBatch: (body: unknown) => fetchJson(`${P}/batches`, json(body)),
  closeBatch: (id: string) => fetchJson(`${P}/batches/${id}/close`, { method: 'POST' }),
  batchReportUrl: (id: string) => `${P}/batches/${id}/report`,
  units: (params: Record<string, string | number | undefined> = {}) =>
    fetchJson<{ total: number; items: Unit[] }>(`${P}/units${query(params)}`),
  unit: (id: string) => fetchJson<Unit>(`${P}/units/${id}`),
  overrideUnit: (id: string, final_decision: string) => fetchJson(`${P}/units/${id}/decision`, json({ final_decision })),
};

export const metrologyApi = {
  calibrations: () => fetchJson<Calibration[]>(`${M}/calibrations`),
  referenceCalibration: (body: unknown) => fetchJson<Calibration>(`${M}/calibrations/reference`, json(body)),
  checkerboard: (file: File, name: string, columns: number, rows: number, square_mm: number) => {
    const form = new FormData();
    form.append('file', file);
    form.append('name', name);
    form.append('columns', String(columns));
    form.append('rows', String(rows));
    form.append('square_mm', String(square_mm));
    return fetchJson<Calibration>(`${M}/calibrations/checkerboard`, { method: 'POST', body: form });
  },
  inspect: (file: File, calibrationId: string, productId?: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('calibration_id', calibrationId);
    if (productId) form.append('product_id', productId);
    return fetchJson<any>(`${M}/inspect`, { method: 'POST', body: form });
  },
};

export const learningApi = {
  reviewQueue: () => fetchJson<{ pending_detections: number; units: Unit[] }>(`${L}/review-queue`),
  labelUnit: (id: string, label: string) => fetchJson<{ added: boolean; split: string | null }>(`${L}/units/${id}/label`, json({ label })),
  uploadSamples: (productKey: string, label: string, files: File[]) => {
    const form = new FormData();
    form.append('product_key', productKey);
    form.append('label', label);
    files.forEach((f) => form.append('files', f));
    return fetchJson<{ added: number; duplicates: number; unreadable: number }>(`${L}/samples`, { method: 'POST', body: form });
  },
  sampleSummary: () => fetchJson<{ product_key: string; label: string; split: string; count: number }[]>(`${L}/samples/summary`),
  datasets: () => fetchJson<any[]>(`${L}/datasets`),
  snapshot: (key: string) => fetchJson<any>(`${L}/datasets/${key}`, { method: 'POST' }),
  train: (product_key: string) => fetchJson<any>(`${L}/train`, json({ product_key })),
  jobs: () => fetchJson<any[]>(`${L}/jobs`),
  models: () => fetchJson<ModelVersion[]>(`${L}/models`),
  promote: (id: string) => fetchJson<ModelVersion>(`${L}/models/${id}/promote`, { method: 'POST' }),
  rollback: (kind: string, product_key: string | null) => fetchJson<ModelVersion>(`${L}/models/rollback`, json({ kind, product_key })),
};

export const edgeApi = {
  status: () => fetchJson<any>(`${API_BASE}/edge/status`),
  benchmark: (productKey?: string) => fetchJson<any>(`${API_BASE}/edge/benchmark${query({ product_key: productKey })}`, { method: 'POST' }),
};

export const liveApi = {
  start: (body: unknown) => fetchJson<LiveStats>(`${API_BASE}/live/sessions`, json(body)),
  get: (id: string) => fetchJson<LiveStats>(`${API_BASE}/live/sessions/${id}`),
  stop: (id: string) => fetchJson<LiveStats>(`${API_BASE}/live/sessions/${id}/stop`, { method: 'POST' }),
  streamUrl: (id: string, token: string) =>
    `${API_BASE.replace(/^http/, 'ws')}/live/sessions/${id}/stream?token=${encodeURIComponent(token)}`,
};

export const pct = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`;
