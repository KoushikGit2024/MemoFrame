import type { CSSProperties } from "react";
import type { FaceRecord, PersonRecord, PersonSortMode, PhotoRecord } from "../types/memoframe";

const DEFAULT_PERSON_RE = /^Person \d+$/i;
const NON_NATIVE_EXTS = new Set([
  ".heic",
  ".heif",
  ".tif",
  ".tiff",
  ".dng",
  ".cr2",
  ".nef",
  ".arw",
  ".rw2",
  ".orf",
]);

export const SORTS: ReadonlyArray<{ label: string; key: string }> = [
  { label: "Date (Newest)", key: "date_desc" },
  { label: "Date (Oldest)", key: "date" },
  { label: "Quality (Best)", key: "quality" },
  { label: "Name A to Z", key: "path" },
  { label: "Name Z to A", key: "path_desc" },
  { label: "Size (Largest)", key: "size" },
  { label: "Size (Smallest)", key: "size_asc" },
  { label: "Most Faces", key: "faces" },
];

export function faceDisplayName(face?: FaceRecord | null): string | null {
  if (!face) return null;
  if (face.person_id === null || face.person_id === undefined) return null;
  const name = String(face.person_name || "").trim();
  if (!name || DEFAULT_PERSON_RE.test(name) || name.toLowerCase() === "unknown") return null;
  return name;
}

export function basename(filePath?: string | null): string {
  if (!filePath) return "";
  const parts = String(filePath).split(/[\\/]/);
  return parts[parts.length - 1] || String(filePath);
}

export function needsBackendDecode(filePath?: string | null): boolean {
  if (!filePath) return false;
  const lower = String(filePath).toLowerCase();
  const dot = lower.lastIndexOf(".");
  return dot >= 0 && NON_NATIVE_EXTS.has(lower.slice(dot));
}

export function formatDate(ts?: string | null): string {
  if (!ts) return "Unknown";
  return String(ts).slice(0, 19).replace("T", " ");
}

export function formatQuality(q?: number | null): string {
  if (q === null || q === undefined || Number.isNaN(Number(q))) return "—";
  return `${Math.round(Number(q))}%`;
}

export function formatDims(w?: number | null, h?: number | null): string {
  if (!w && !h) return "—";
  return `${w || 0} x ${h || 0}`;
}

export function initials(name?: string | null): string {
  const parts = String(name || "?")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function sortPersons(persons: PersonRecord[], mode: PersonSortMode): PersonRecord[] {
  const copy = [...(persons || [])];
  if (mode === "name_asc") {
    return copy.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }
  if (mode === "name_desc") {
    return copy.sort((a, b) => String(b.name || "").localeCompare(String(a.name || "")));
  }
  if (mode === "newest") {
    return copy.sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
  }
  return copy.sort((a, b) => Number(b.image_count || 0) - Number(a.image_count || 0));
}

export class LatestTask {
  private _gen = 0;

  async run<T>(
    asyncFn: () => Promise<T>,
    onDone?: (res: T) => void,
    onError?: (err: Error) => void
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

export function computeFaceZoomStyle(
  photo?: PhotoRecord | null,
  targetPersonId?: number | null
): CSSProperties | null {
  const faces = photo?.faces;
  if (!faces?.length || !photo?.width || !photo?.height) return null;

  // If a specific person is selected/filtered, prioritize that person's face.
  // Otherwise, zoom to the primary (largest) face.
  let targetFace: FaceRecord | undefined;
  if (targetPersonId !== null && targetPersonId !== undefined) {
    targetFace = faces.find(f => f.person_id === targetPersonId);
  }
  if (!targetFace) {
    targetFace = faces.reduce((best, f) => (f.w * f.h > best.w * best.h ? f : best), faces[0]);
  }
  if (!targetFace || !targetFace.w || !targetFace.h) return null;

  const origW = Number(photo.width);
  const origH = Number(photo.height);
  const faceCx = Number(targetFace.x) + Number(targetFace.w) / 2;
  const faceCy = Number(targetFace.y) + Number(targetFace.h) / 2;

  // Normalized face center in image space [0..1]
  const cxNorm = faceCx / origW;
  const cyNorm = faceCy / origH;

  // Percentage coordinates [0..100]
  const cx = Math.max(0, Math.min(100, cxNorm * 100));
  const cy = Math.max(0, Math.min(100, cyNorm * 100));

  // Determine scale so the face bounding box comfortably fills the card viewport (~75-80% coverage)
  // instead of leaving excess surrounding scene/background:
  const faceFraction = Math.max(Number(targetFace.w) / origW, Number(targetFace.h) / origH);
  const scale = Math.max(1.8, Math.min(8.0, 0.78 / Math.max(0.04, faceFraction)));

  // Crucial: In CSS object-fit: cover, if an image has an extreme aspect ratio (such as a
  // 21:9 panorama or a 9:16 portrait), the browser centers the image by default (50% 50%)
  // and clips off anything past the card boundary.
  // By specifying `objectPosition: cx% cy%`, the CSS specification guarantees that the intrinsic
  // face coordinate (cx%, cy%) aligns with (cx%, cy%) of the container box across ALL aspect ratios.
  //
  // Then, with transformOrigin at (cx%, cy%), scaling leaves the face stationary.
  // To move the face to the container's center (50%, 50%), we translate by (50 - cx, 50 - cy),
  // clamped to ensure the image boundaries never retract into the card viewport.
  const minTx = (cx - 100) * (scale - 1);
  const maxTx = cx * (scale - 1);
  const tx = Math.max(minTx, Math.min(maxTx, 50 - cx));

  const minTy = (cy - 100) * (scale - 1);
  const maxTy = cy * (scale - 1);
  const ty = Math.max(minTy, Math.min(maxTy, 50 - cy));

  return {
    objectPosition: `${cx.toFixed(1)}% ${cy.toFixed(1)}%`,
    transformOrigin: `${cx.toFixed(1)}% ${cy.toFixed(1)}%`,
    transform: `translate(${tx.toFixed(1)}%, ${ty.toFixed(1)}%) scale(${scale.toFixed(2)})`,
  };
}
