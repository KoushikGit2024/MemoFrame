import {
  Calendar,
  ExternalLink,
  Eye,
  EyeOff,
  FolderOpen,
  Loader2,
  Play,
  RotateCcw,
  Sparkles,
  Star,
  Tag,
  ZoomIn,
} from "lucide-react";
import { formatDate, formatDims, formatQuality } from "../lib/utils";
import type { FaceRecord, PersonRecord, PhotoRecord, TagRecord } from "../types/memoframe";

export interface LightboxSidebarProps {
  photo: PhotoRecord;
  faces: FaceRecord[];
  tags: TagRecord[];
  marks: string[];
  liveVideo: { path: string } | null;
  activeFace: FaceRecord | null;
  faceNameInput: string;
  setFaceNameInput: (val: string) => void;
  persons: PersonRecord[];
  savingFaceName: boolean;
  assigningFace: boolean;
  togglingMark: "favourite" | "hidden" | null;
  restoringDate: boolean;
  openingDefaultApp: boolean;
  onZoomToFace: (face: FaceRecord) => void;
  onNameFace: () => void;
  onAssignFace: (personId: number | null) => void;
  onCloseActiveFace: () => void;
  onToggleMark: (mark: "favourite" | "hidden") => void;
  onShowDateModal: () => void;
  onRestoreDate: () => void;
  onShowSimilar: () => void;
  onShowLive: () => void;
  onOpenInDefaultApp: () => void;
  onRevealInFolder: (path: string) => void;
  onFilterByTag: (tag: string) => void;
}

export default function LightboxSidebar({
  photo,
  faces,
  tags,
  marks,
  liveVideo,
  activeFace,
  faceNameInput,
  setFaceNameInput,
  persons,
  savingFaceName,
  assigningFace,
  togglingMark,
  restoringDate,
  openingDefaultApp,
  onZoomToFace,
  onNameFace,
  onAssignFace,
  onCloseActiveFace,
  onToggleMark,
  onShowDateModal,
  onRestoreDate,
  onShowSimilar,
  onShowLive,
  onOpenInDefaultApp,
  onRevealInFolder,
  onFilterByTag,
}: LightboxSidebarProps) {
  const isFav = marks.includes("favourite");
  const isHidden = marks.includes("hidden");

  return (
    <aside className="w-[300px] shrink-0 border-l border-subtle bg-card p-3.5 flex flex-col gap-3 overflow-y-auto">
      <div className="flex flex-col gap-2.5 flex-1">
        {[
          ["Date Taken", formatDate(photo.effective_ts || photo.exif_ts)],
          ["Resolution", formatDims(photo.width, photo.height)],
          ["Format", String(photo.format || "Unknown").toUpperCase()],
          ["Faces Detected", String(faces.length)],
          ["Quality Score", formatQuality(photo.quality)],
          ["File Path", photo.path || "—"],
        ].map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-secondary">
              {k}
            </div>
            <div className="text-xs text-primary break-words mt-0.5 select-text">{v}</div>
          </div>
        ))}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-secondary">
            Scene Tags
          </div>
          {tags.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 mt-1">
              {tags.map(t => (
                <button
                  key={t.label}
                  type="button"
                  onClick={() => onFilterByTag(t.label)}
                  title={`Filter gallery by "${t.label}"`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-xs bg-amber-bg border border-amber/45 text-[11px] font-medium text-amber hover:border-amber hover:bg-amber/20 active:scale-[0.97] transition-all cursor-pointer"
                >
                  <Tag className="w-2.5 h-2.5 shrink-0" strokeWidth={1.8} />
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-xs text-primary mt-0.5">—</div>
          )}
        </div>
      </div>

      {activeFace && (
        <div className="p-2.5 bg-violet-bg/35 border border-violet/65 rounded-xs flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-violet">
              Manage Face #{activeFace.id}
            </span>
            <button
              type="button"
              onClick={() => onZoomToFace(activeFace)}
              className="text-[11px] text-accent-secondary hover:underline inline-flex items-center gap-1 cursor-pointer"
            >
              <ZoomIn className="w-3 h-3" />
              <span>Zoom to Face</span>
            </button>
          </div>
          <div className="flex gap-1">
            <input
              type="text"
              value={faceNameInput}
              disabled={savingFaceName}
              onChange={e => setFaceNameInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter") onNameFace();
              }}
              placeholder="Person name..."
              className="flex-1 h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-violet disabled:opacity-50"
            />
            <button
              type="button"
              disabled={savingFaceName || !faceNameInput.trim()}
              onClick={onNameFace}
              className="btn-primary h-7 px-2 text-xs"
            >
              {savingFaceName ? "Saving..." : "Save"}
            </button>
          </div>
          {persons.length > 0 && (
            <select
              defaultValue=""
              disabled={assigningFace}
              onChange={e => {
                if (e.target.value) onAssignFace(Number(e.target.value));
              }}
              className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-violet disabled:opacity-50"
            >
              <option value="">
                {assigningFace ? "Assigning..." : "Assign to existing person..."}
              </option>
              {persons.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.image_count || 0})
                </option>
              ))}
            </select>
          )}
          <div className="flex justify-between">
            <button
              type="button"
              disabled={assigningFace}
              onClick={() => onAssignFace(null)}
              className="text-xs text-danger hover:underline disabled:opacity-50 cursor-pointer"
            >
              {assigningFace ? "Updating..." : "Remove from person"}
            </button>
            <button
              type="button"
              onClick={onCloseActiveFace}
              className="text-xs text-secondary hover:text-primary cursor-pointer"
            >
              Done
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1.5 pt-2 border-t border-subtle">
        <button
          type="button"
          disabled={togglingMark !== null}
          onClick={() => onToggleMark("favourite")}
          className={`h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs border text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer ${
            isFav
              ? "bg-amber-bg border-amber text-amber font-semibold"
              : "bg-elevated border-hairline text-primary hover:border-amber/60 hover:text-amber"
          }`}
        >
          <Star className={`w-3.5 h-3.5 ${isFav ? "fill-current" : ""}`} strokeWidth={1.7} />
          <span>
            {togglingMark === "favourite"
              ? "Updating..."
              : isFav
                ? "Remove Favourite"
                : "Mark as Favourite"}
          </span>
        </button>
        <button
          type="button"
          disabled={togglingMark !== null}
          onClick={() => onToggleMark("hidden")}
          className="btn-neutral h-8 px-3 text-xs"
        >
          {isHidden ? (
            <Eye className="w-3.5 h-3.5" strokeWidth={1.6} />
          ) : (
            <EyeOff className="w-3.5 h-3.5" strokeWidth={1.6} />
          )}
          <span>
            {togglingMark === "hidden" ? "Updating..." : isHidden ? "Unhide Photo" : "Hide Photo"}
          </span>
        </button>
        <div className="grid grid-cols-2 gap-1.5">
          <button type="button" onClick={onShowDateModal} className="btn-neutral h-8 px-2 text-xs">
            <Calendar className="w-3.5 h-3.5 text-amber" strokeWidth={1.6} />
            <span>Correct Date</span>
          </button>
          <button
            type="button"
            disabled={restoringDate}
            onClick={onRestoreDate}
            className="btn-neutral h-8 px-2 text-xs"
          >
            <RotateCcw
              className={`w-3.5 h-3.5 ${restoringDate ? "animate-spin" : ""}`}
              strokeWidth={1.6}
            />
            <span>{restoringDate ? "Restoring..." : "Restore"}</span>
          </button>
        </div>
        <button type="button" onClick={onShowSimilar} className="btn-secondary h-8 px-3 text-xs">
          <Sparkles className="w-3.5 h-3.5" strokeWidth={1.6} />
          <span>Find Similar</span>
        </button>
        {liveVideo && (
          <button type="button" onClick={onShowLive} className="btn-primary h-8 px-3 text-xs">
            <Play className="w-3.5 h-3.5" strokeWidth={1.7} />
            <span>Play Live Photo</span>
          </button>
        )}
        {photo.path && (
          <div className="grid grid-cols-2 gap-1.5">
            <button
              type="button"
              disabled={openingDefaultApp}
              onClick={onOpenInDefaultApp}
              className="btn-neutral h-8 px-2 text-xs"
            >
              {openingDefaultApp ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />
              ) : (
                <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.6} />
              )}
              <span>Default App</span>
            </button>
            <button
              type="button"
              onClick={() => onRevealInFolder(photo.path as string)}
              className="btn-neutral h-8 px-2 text-xs text-secondary hover:text-primary"
            >
              <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.6} />
              <span>In Folder</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
