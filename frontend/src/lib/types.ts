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
