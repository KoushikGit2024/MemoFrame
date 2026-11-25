/* Explicit Domain Contracts for MemoFrame Frontend & Python Engine Bridge */

export type ViewKey = 'photos' | 'people' | 'duplicates' | 'bursts' | 'timeline' | 'settings';
export type LayoutMode = 'grid' | 'compact' | 'table';
export type ToastKind = 'info' | 'success' | 'error';
export type PersonSortMode = 'most' | 'name_asc' | 'name_desc' | 'newest';

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
  similarity?: number;
  error?: string;
  kind?: string;
  state?: string;
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
  prefs?: Record<string, unknown>;
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
