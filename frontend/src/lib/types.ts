export interface DashboardSummary {
  total_inspections: number;
  compliant_count: number;
  needs_review_count: number;
  non_compliance_count: number;
  draft_count: number;
  recent_inspections: Inspection[];
  common_violations: Array<{
    rule_id: string;
    field: string;
    description?: string;
    count: number;
  }>;
  category_distribution: Array<{
    category: string;
    count: number;
  }>;
}

export interface PackageImage {
  id: string;
  inspection_id?: string;
  surface_type: string;
  file_path: string;
  /** Short-lived signed link to the stored image (use with getStorageUrl / imageSrc). */
  file_url?: string | null;
  review_status?: 'UNREVIEWED' | 'VERIFIED' | string;
  dataset_split?: 'train' | 'val' | 'test' | null;
  original_filename: string;
  quality_score: number;
  quality_metadata?: {
    quality_score: number;
    blur: boolean;
    glare: boolean;
    resolution_ok: boolean;
    perspective_ok: boolean;
    occlusion_detected: boolean;
    surface_visible: boolean;
    sharpness_score?: number;
    is_empty?: boolean;
    issues: string[];
    defect_scan?: DefectScanMeta & { frame_index?: number; timestamp_ms?: number };
  };
  ocr_raw_data?: Array<{
    text: string;
    confidence: number;
    bbox?: [number, number, number, number];
    surface_type?: string;
  }>;
  created_at?: string;
}

export interface Declaration {
  id: string;
  inspection_id: string;
  image_id?: string;
  field_name?: string;
  field?: string;
  raw_text?: string;
  detected_value?: string;
  normalized_value?: string;
  confidence: number;
  bbox?: number[];
  unit?: string;
  surface_type?: string;
  extraction_method?: string;
  is_verified?: boolean;
  reviewer_value?: string;
  created_at?: string;
}

export interface ComplianceResult {
  id: string;
  inspection_id: string;
  rule_id: string;
  field: string;
  detected_value?: string;
  normalized_value?: string;
  confidence: number;
  outcome: 'PASS' | 'REVIEW' | 'POSSIBLE_NON_COMPLIANCE' | string;
  severity?: string;
  evidence?: {
    image_id?: string;
    surface_type?: string;
    bbox?: [number, number, number, number];
    detected_text?: string;
    [key: string]: any;
  };
  legal_reference?: string;
  statutory_reference?: string;
  requirement?: string;
  statutory_requirement?: string;
  explanation?: string;
  reasoning?: string;
  surface_type?: string;
  bbox?: number[];
  manual_override?: boolean;
  override_action?: string;
  override_reason?: string;
  override_by?: string;
  override_at?: string;
  reviewer_status?: string;
  created_at?: string;
}

export interface ReviewAction {
  id: string;
  inspection_id: string;
  reviewer_id?: string;
  action_type: 'CONFIRM' | 'CORRECT' | 'REJECT' | 'REQUEST_NEW_IMAGE' | string;
  target_field: string;
  previous_value?: string;
  new_value?: string;
  reason?: string;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  inspection_id: string;
  user_id?: string;
  event_type: string;
  description?: string;
  details?: any;
  performed_by?: string;
  state_before?: any;
  state_after?: any;
  created_at: string;
}

export interface Inspection {
  id: string;
  inspection_number: string;
  inspection_mode?: 'LEGAL_METROLOGY' | 'DEFECT' | string;
  product_name?: string;
  brand_name?: string;
  category: string;
  status: string;
  overall_outcome: 'COMPLIANT' | 'NEEDS_MANUAL_REVIEW' | 'POSSIBLE_NON_COMPLIANCE' | 'REVIEW' | 'PASS' | string;
  created_by_id?: string;
  location?: string;
  notes?: string;
  final_remarks?: string;
  report_path?: string;
  image_count?: number;
  images?: PackageImage[];
  declarations?: Declaration[];
  compliance_results?: ComplianceResult[];
  reviewer_actions?: ReviewAction[];
  audit_events?: AuditEvent[];
  created_at: string;
  updated_at?: string;
}

// --- Defect Inspection mode ---
export type DefectSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type DefectOutcome = 'PASS' | 'REVIEW' | 'DEFECTIVE' | 'PENDING';

export interface DefectDetection {
  id?: string;
  inspection_id?: string;
  image_id?: string | null;
  defect_type: string;
  severity: DefectSeverity | string;
  confidence: number;
  bbox: number[];
  area_ratio?: number;
  detector: string;
  model_version?: string | null;
  metrics?: Record<string, any>;
  frame_index?: number | null;
  frame_timestamp_ms?: number | null;
  reviewer_status?: 'PENDING' | 'CONFIRMED' | 'REJECTED' | 'RELABELED' | string;
  reviewer_note?: string | null;
  created_at?: string;
}

export interface DefectScanMeta {
  latency_ms: number;
  fps: number | null;
  backend: string;
  image_size: [number, number];
  product_mask_used: boolean;
  reference_used: boolean;
  mean_brightness?: number;
  exposure_ok?: boolean;
  detection_count: number;
  outcome: DefectOutcome | string;
}

export interface LiveFrameResult extends DefectScanMeta {
  detections: DefectDetection[];
}

export interface DefectAnalyzeResult {
  image: PackageImage;
  detections: DefectDetection[];
  scan: DefectScanMeta;
  overall_outcome: DefectOutcome | string;
}

export interface DefectVideoSummary {
  video: string;
  source_fps: number;
  total_frames: number;
  frames_sampled: number;
  frames_with_defects: number;
  keyframes_saved: number;
  avg_latency_ms: number | null;
  processing_fps: number | null;
  detections_by_type: Record<string, number>;
  overall_outcome: DefectOutcome | string;
}

export interface RootCauseHint {
  defect_type: string;
  count: number;
  high_severity_count: number;
  priority: 'HIGH' | 'MEDIUM' | string;
  likely_causes: string[];
  recommended_actions: string[];
  evidence: string[];
}

export interface DefectInspection {
  id: string;
  inspection_number: string;
  inspection_mode?: string;
  product_id?: string | null;
  station_id?: string | null;
  station_name?: string | null;
  shift?: string | null;
  batch_code?: string | null;
  source?: string | null;
  product_name?: string;
  brand_name?: string;
  category: string;
  status: string;
  overall_outcome: DefectOutcome | string;
  location?: string;
  notes?: string;
  final_remarks?: string;
  report_path?: string;
  image_count?: number;
  defect_count?: number;
  top_defect_type?: string | null;
  images?: PackageImage[];
  defect_detections?: DefectDetection[];
  reviewer_actions?: ReviewAction[];
  audit_events?: AuditEvent[];
  root_causes?: RootCauseHint[];
  created_at: string;
  updated_at?: string;
}

export interface DefectAnalytics {
  window_days: number;
  totals: {
    inspections: number;
    defective: number;
    review: number;
    pass: number;
    pending: number;
    defect_rate: number;
    detections: number;
  };
  most_frequent_type: string | null;
  by_type: Array<{
    defect_type: string;
    count: number;
    share: number;
    avg_confidence: number;
    severities: Record<string, number>;
  }>;
  by_severity: Record<string, number>;
  trend: Array<{ date: string; total: number; by_type: Record<string, number> }>;
  by_product: Array<{
    product_name: string;
    inspections: number;
    defective: number;
    defect_rate: number;
    detections: number;
    top_defect_type: string | null;
  }>;
  hotspots: Record<string, { grid: number[][]; dominant_region: string | null; dominant_share: number }>;
  feedback: {
    confirmed: number;
    relabeled: number;
    rejected: number;
    pending: number;
    precision_estimate: number | null;
  };
  performance: {
    frames_analyzed: number;
    avg_latency_ms: number | null;
    throughput_fps: number | null;
  };
  root_causes: RootCauseHint[];
  known_defect_types: string[];
}

export interface DefectLogItem extends DefectDetection {
  inspection_number: string;
  product_name?: string;
  batch?: string;
  station?: string | null;
  shift?: string | null;
}

// --- Auth, organisation structure, jobs ---
export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: 'OPERATOR' | 'QUALITY_MANAGER' | 'ADMIN' | 'AUDITOR' | string;
  permissions: string[];
  badge_number?: string | null;
  organization_id?: string | null;
  organization_name?: string | null;
}

export interface StationNode {
  id: string;
  line_id: string;
  name: string;
  camera_info?: string | null;
  is_active: boolean;
}

export interface LineNode {
  id: string;
  plant_id: string;
  name: string;
  stations: StationNode[];
}

export interface PlantNode {
  id: string;
  name: string;
  location?: string | null;
  lines: LineNode[];
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  family?: string | null;
  material?: string | null;
  is_active: boolean;
}

export interface ManagedUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface EdgeDevice {
  id: string;
  name: string;
  station_id?: string | null;
  key_prefix: string;
  is_active: boolean;
  last_seen_at?: string | null;
  created_at: string;
}

// --- Learning loop (Phase B) ---
export interface ReviewReason {
  code: 'UNCERTAIN' | 'DISAGREEMENT' | 'UNKNOWN_CLASS' | 'QUALITY' | 'DRIFT' | 'AUDIT' | 'MANUAL' | string;
  detail: string;
}

export interface ReviewTask {
  id: string;
  status: 'OPEN' | 'DONE' | 'SKIPPED' | string;
  priority: number;
  reasons: ReviewReason[];
  source: string;
  created_at: string;
  completed_at?: string | null;
  image_id: string;
  image_url?: string | null;
  image_review_status: string;
  inspection_id: string;
  inspection_number: string;
  product_name?: string | null;
  station?: string | null;
  batch_code?: string | null;
  detection_count: number;
  pending_count: number;
}

export interface ReviewTaskDetail extends ReviewTask {
  detections: DefectDetection[];
  image_size?: [number, number] | null;
  defect_types: string[];
}

export interface ReviewStats {
  open: number;
  by_reason: Record<string, number>;
  done_last_24h: number;
  verified_images: number;
  verified_by_split: Record<string, number>;
  new_verified_since_last_dataset: number;
  auto_train_threshold: number;
  classes: string[];
}

export interface GateCheck {
  name: string;
  passed: boolean;
  detail: string;
  value?: number | null;
  threshold?: number | null;
}

export interface GateReport {
  passed: boolean;
  checks: GateCheck[];
  test_images: number;
  dataset_version?: number;
  champion_name?: string | null;
  candidate?: { map50: number; precision: number; recall: number; avg_latency_ms: number; per_class: Record<string, any> };
  champion?: { map50: number; precision: number; recall: number; avg_latency_ms: number; per_class: Record<string, any> } | null;
  evaluated_at?: string;
}

export interface ShadowStats {
  images: number;
  agreement: number | null;
  avg_latency_ms?: number | null;
  verified_images: number;
  shadow: { precision: number; recall: number; f1: number; tp: number; fp: number; fn: number } | null;
  champion: { precision: number; recall: number; f1: number; tp: number; fp: number; fn: number } | null;
}

export interface ModelVersionInfo {
  id: string;
  version: number;
  name: string;
  status: 'TRAINING' | 'CANDIDATE' | 'GATE_FAILED' | 'GATE_PASSED' | 'SHADOW' | 'ACTIVE' | 'RETIRED' | 'FAILED' | string;
  source: string;
  parent_id?: string | null;
  dataset_version?: number | null;
  classes: string[];
  input_size?: number | null;
  sha256?: string | null;
  train_metrics?: Record<string, any> | null;
  gate_report?: GateReport | null;
  model_card?: Record<string, any> | null;
  job_id?: string | null;
  created_at: string;
  approved_at?: string | null;
  activated_at?: string | null;
  notes?: string | null;
  shadow_stats?: ShadowStats;
}

export interface DatasetVersionInfo {
  id: string;
  version: number;
  status: string;
  classes: string[];
  image_count: number;
  label_count: number;
  class_counts: Record<string, number>;
  split_counts: Record<string, number>;
  manifest_sha256?: string | null;
  created_at: string;
  notes?: string | null;
}

export interface DriftStation {
  station_id: string | null;
  station: string;
  baseline_images: number;
  recent_images: number;
  status: 'OK' | 'WATCH' | 'ALERT' | 'INSUFFICIENT_DATA' | string;
  psi: number | null;
  features: Record<string, { psi: number; status: string }>;
}

export interface LearningOverview {
  active_model: ModelVersionInfo | null;
  shadow_model: (ModelVersionInfo & { shadow_stats: ShadowStats }) | null;
  latest_dataset: DatasetVersionInfo | null;
  new_verified_since_last_dataset: number;
  running_jobs: Job[];
  policy: Record<string, any>;
}

export interface ModelEventInfo {
  id: string;
  event_type: string;
  description: string;
  created_at: string;
  model?: string | null;
}

export interface Job {
  id: string;
  job_type: string;
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | string;
  progress: number;
  message?: string | null;
  result?: Record<string, any> | null;
  error?: string | null;
  inspection_id?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface DefectDetectorStatus {
  backend: string;
  opencv_version: string;
  model_loaded: boolean;
  model_path: string | null;
  model_input_size?: number | null;
  model_classes: string[];
  model_error: string | null;
  defect_types: string[];
}
