/* Explicit Domain Contracts for MemoFrame Frontend & Python Engine Bridge */

export type ViewKey =
  | "photos"
  | "people"
  | "duplicates"
  | "bursts"
  | "timeline"
  | "analytics"
  | "settings";
export type LayoutMode = "grid" | "compact" | "table";
export type ToastKind = "info" | "success" | "error";
export type PersonSortMode = "most" | "name_asc" | "name_desc" | "newest";
export type AnalyticsRange = "24h" | "7d" | "30d" | "90d" | "all";
export type UiDensity = "comfortable" | "compact";
export type DateFormatMode = "iso" | "locale" | "relative";

export interface AppPreferences {
  theme?: string;
  defaultView?: ViewKey;
  timezone?: string;
  dateFormat?: DateFormatMode;
  density?: UiDensity;
  reducedMotion?: boolean;
  compactSidebar?: boolean;
  notifySuccess?: boolean;
  notifyErrors?: boolean;
  notifyBackground?: boolean;
  defaultPageSize?: number;
  onboardingCompleted?: boolean;
}

export interface NotificationHistoryItem {
  id: number;
  message: string;
  kind: ToastKind;
  timestamp: string;
}

export interface ThemeMeta {
  name: string;
  isDark: boolean;
  bg: string;
  card: string;
  accent: string;
}

export interface FaceRecord {
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  locked?: number | boolean;
  ignored?: number;
  confidence?: number;
  person_id?: number | null;
  person_name?: string | null;
  crop_path?: string | null;
  path?: string;
}

export interface PhotoRecord {
  id: number;
  path?: string;
  thumb_path?: string | null;
  face_crop_path?: string | null;
  width?: number;
  height?: number;
  format?: string;
  quality?: number | null;
  effective_ts?: string | null;
  exif_ts?: string | null;
  face_count?: number;
  faces?: FaceRecord[];
  suggested?: boolean;
  suggested_keep?: boolean;
  is_favourite?: boolean | number;
  similarity?: number;
  error?: string;
  kind?: string;
  state?: string;
  size?: number;
  place?: string | null;
  gps_lat?: number | null;
  gps_lon?: number | null;
  ts_source?: string | null;
  sharpness?: number | null;
  brightness?: number | null;
  sha256?: string | null;
  duration_s?: number | null;
}

export interface PersonRecord {
  id: number;
  name: string;
  image_count?: number;
  cover_crop_path?: string | null;
}

export interface TagRecord {
  label: string;
  count?: number;
}

export interface SavedSearchRecord {
  name: string;
  filters: Record<string, unknown>;
}

export interface DuplicateCluster {
  cluster_id: string;
  kind: string;
  best_image_id: number;
  photos: PhotoRecord[];
}

export interface BurstRecord {
  id: number;
  image_count: number;
  best_image_id: number;
}

export interface TimelineGroup {
  id: number;
  name?: string | null;
  start_ts?: string | null;
  end_ts?: string | null;
  start_ts_utc?: string | null;
  end_ts_utc?: string | null;
  timestamp_valid?: boolean;
  image_count: number;
  photos: PhotoRecord[];
}

export interface SuspiciousDateRow {
  id: number;
  path: string;
  exif_ts?: string | null;
  date_flag?: string | null;
  override_ts?: string | null;
}

export interface EngineConfig {
  tagging_enabled: boolean;
  store_embeddings: boolean;
  log_path: string;
}

export interface SystemInitPayload {
  connected: boolean;
  workspace: string;
  backend_error?: string | null;
  config_warnings?: string[];
  prefs?: AppPreferences;
  config?: EngineConfig;
}

export interface WorkspaceStats {
  total_images?: number;
  total_faces?: number;
  duplicate_clusters?: number;
  groups?: number;
  videos?: number;
  processed?: number;
  images_with_faces?: number;
  duplicate_images?: number;
}

export interface DoctorCheck {
  name: string;
  status: string;
  detail: string;
  fix?: string;
}

export interface DoctorReport {
  checks: DoctorCheck[];
}

export interface ScanState {
  running: boolean;
  paused: boolean;
  percent: number;
  label: string;
  stage?: string;
  done?: number;
  total?: number;
}

export interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

export interface BackendEventPayload {
  event: string;
  data: Record<string, unknown>;
}

export interface RpcResponse<T = unknown> {
  ok: boolean;
  result?: T;
  error?: {
    code?: string;
    message?: string;
    hint?: string;
  };
}

export interface LabelCount {
  label: string;
  count: number;
}

export interface AnalyticsOverview {
  range: string;
  connected: boolean;
  uptime_seconds: number;
  library: {
    total_images: number;
    videos: number;
    total_faces: number;
    named_faces: number;
    unassigned_faces: number;
    persons: number;
    groups: number;
    duplicate_clusters: number;
    bursts: number;
    failed_images: number;
    avg_quality: number;
    total_size_mb: number;
    formats: LabelCount[];
  };
  rpc: {
    total_requests: number;
    success_count: number;
    error_count: number;
    success_rate: number;
    error_rate: number;
    avg_latency_ms: number;
    max_latency_ms: number;
  };
  errors: {
    unresolved_count: number;
    recovery_attempts: number;
    recovery_succeeded: number;
    recovery_rate: number;
    by_origin: LabelCount[];
    by_severity: LabelCount[];
  };
}

export interface AnalyticsActivity {
  range: string;
  photos_by_month: LabelCount[];
  photos_by_hour: Array<{ hour: number; count: number }>;
  top_people: LabelCount[];
  top_tags: LabelCount[];
  rpc_by_hour: Array<{ hour: number; count: number }>;
}

export interface ErrorRecord {
  id: number;
  fingerprint: string;
  severity: "critical" | "error" | "warning" | "info";
  category: string;
  origin: "frontend" | "backend" | "bridge";
  module: string;
  code: string;
  message: string;
  stack_trace: string;
  correlation_id: string;
  status: "detected" | "investigating" | "recovered" | "resolved";
  recovery_class: "auto_recoverable" | "user_action" | "dev_action" | "never_auto";
  occurrence_count: number;
  first_seen_utc: string;
  last_seen_utc: string;
  notes: string;
  context_json: string;
  app_version: string;
}

export interface ErrorOccurrence {
  id: number;
  error_id: number;
  correlation_id: string;
  occurred_at_utc: string;
  message: string;
  context_json: string;
}

export interface RecoveryAttempt {
  id: number;
  error_id: number;
  strategy: string;
  trigger_source: "automatic" | "manual";
  attempt_no: number;
  started_at_utc: string;
  duration_ms: number;
  outcome: "succeeded" | "failed" | "skipped";
  final_state: string;
  detail: string;
  module?: string;
  category?: string;
  error_message?: string;
}

export interface ErrorDetailPayload {
  error: ErrorRecord;
  occurrences: ErrorOccurrence[];
  recoveries: RecoveryAttempt[];
  related: Array<{
    id: number;
    origin: string;
    module: string;
    severity: string;
    message: string;
    status: string;
    last_seen_utc: string;
  }>;
}

export interface AnalyticsErrors {
  unresolved_count: number;
  by_severity: LabelCount[];
  by_origin: LabelCount[];
  over_time: Array<{ date: string; count: number }>;
  top_errors: ErrorRecord[];
  recovery_attempts: number;
  recovery_succeeded: number;
  recovery_rate: number;
}

export interface AnalyticsPerformance {
  by_method: Array<{
    method: string;
    count: number;
    avg_ms: number;
    max_ms: number;
    errors: number;
  }>;
  latency_histogram: Array<{ bucket: string; count: number }>;
  slow_operations: Array<{
    correlation_id: string;
    method: string;
    status: string;
    duration_ms: number;
    error_code: string;
    created_at_utc: string;
  }>;
  rpc_by_hour: Array<{ hour: number; count: number }>;
}

export interface ConfigAuditRow {
  id: number;
  key: string;
  old_value: string;
  new_value: string;
  changed_at_utc: string;
}
