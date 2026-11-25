import type { CSSProperties } from 'react';
import type { FaceRecord, PersonRecord, PersonSortMode, PhotoRecord } from '../types/memoframe';

const DEFAULT_PERSON_RE = /^Person \d+$/i;
const NON_NATIVE_EXTS = new Set([
  '.heic', '.heif', '.tif', '.tiff', '.dng', '.cr2', '.nef', '.arw', '.rw2', '.orf',
]);

export const SORTS: ReadonlyArray<{ label: string; key: string }> = [
  { label: 'Date (Newest)', key: 'date_desc' },
  { label: 'Date (Oldest)', key: 'date' },
  { label: 'Quality (Best)', key: 'quality' },
  { label: 'Name A to Z', key: 'path' },
  { label: 'Name Z to A', key: 'path_desc' },
  { label: 'Size (Largest)', key: 'size' },
  { label: 'Size (Smallest)', key: 'size_asc' },
  { label: 'Most Faces', key: 'faces' },
];

export function faceDisplayName(face?: FaceRecord | null): string | null {
  if (!face || !face.locked) return null;
  if (face.person_id === null || face.person_id === undefined) return null;
  const name = String(face.person_name || '').trim();
  if (!name || DEFAULT_PERSON_RE.test(name)) return null;
  return name;
}

export function basename(filePath?: string | null): string {
  if (!filePath) return '';
  const parts = String(filePath).split(/[\\/]/);
  return parts[parts.length - 1] || String(filePath);
}

export function needsBackendDecode(filePath?: string | null): boolean {
  if (!filePath) return false;
  const lower = String(filePath).toLowerCase();
  const dot = lower.lastIndexOf('.');
  return dot >= 0 && NON_NATIVE_EXTS.has(lower.slice(dot));
}

export function formatDate(ts?: string | null): string {
  if (!ts) return 'Unknown';
  return String(ts).slice(0, 19).replace('T', ' ');
}

export function formatQuality(q?: number | null): string {
  if (q === null || q === undefined || Number.isNaN(Number(q))) return '—';
  return `${Math.round(Number(q))}%`;
}

export function formatDims(w?: number | null, h?: number | null): string {
  if (!w && !h) return '—';
  return `${w || 0} x ${h || 0}`;
}

export function initials(name?: string | null): string {
  const parts = String(name || '?').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function sortPersons(persons: PersonRecord[], mode: PersonSortMode): PersonRecord[] {
  const copy = [...(persons || [])];
  if (mode === 'name_asc') {
    return copy.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));
  }
  if (mode === 'name_desc') {
    return copy.sort((a, b) => String(b.name || '').localeCompare(String(a.name || '')));
  }
  if (mode === 'newest') {
    return copy.sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
  }
  return copy.sort((a, b) => Number(b.image_count || 0) - Number(a.image_count || 0));
}

export class LatestTask {
  private _gen = 0;

  async run<T>(
    asyncFn: () => Promise<T>,
    onDone?: (res: T) => void,
    onError?: (err: Error) => void,
  ): Promise<T | null> {
    const gen = ++this._gen;
    try {
      const res = await asyncFn();
      if (gen === this._gen && onDone) onDone(res);
      return res;
    } catch (err) {
      if (gen === this._gen && onError) {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
      return null;
    }
  }

  cancel(): void {
    this._gen += 1;
  }
}

export function computeFaceZoomStyle(photo?: PhotoRecord | null): CSSProperties | null {
  const faces = photo?.faces;
  if (!faces?.length || !photo?.width || !photo?.height) return null;
  const largest = faces.reduce((best, f) => ((f.w * f.h) > (best.w * best.h) ? f : best), faces[0]);
  const cx = ((largest.x + largest.w / 2) / photo.width) * 100;
  const cy = ((largest.y + largest.h / 2) / photo.height) * 100;
  return {
    objectPosition: `${Math.max(0, Math.min(100, cx)).toFixed(1)}% ${Math.max(0, Math.min(100, cy)).toFixed(1)}%`,
    transform: 'scale(1.65)',
  };
}
