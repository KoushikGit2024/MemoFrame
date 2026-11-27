import { useEffect, useRef, useState } from "react";
import {
  Calendar,
  ChevronDown,
  Download,
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
import { useApp } from "../../shared/context/AppContext";
import { formatDate, formatDims, formatQuality } from "../../shared/lib/utils";
import PersonAvatar from "../../shared/ui/PersonAvatar";
import type { FaceRecord, PersonRecord, PhotoRecord, TagRecord } from "../../shared/types/memoframe";

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
  discardingFace: boolean;
  settingDefaultFace?: boolean;
  togglingMark: "favourite" | "hidden" | null;
  restoringDate: boolean;
  openingDefaultApp: boolean;
  onZoomToFace: (face: FaceRecord) => void;
  onNameFace: () => void;
  onAssignFace: (personId: number | null) => void;
  onDiscardFace: (faceId: number) => void;
  onSetDefaultFace?: (personId: number, faceId: number) => void;
  onCloseActiveFace: () => void;
  onToggleMark: (mark: "favourite" | "hidden") => void;
  onShowDateModal: () => void;
  onRestoreDate: () => void;
  onShowSimilar: () => void;
  onShowLive: () => void;
  onOpenInDefaultApp: () => void;
  onRevealInFolder: (path: string) => void;
  onFilterByTag: (tag: string) => void;
  onExportPhoto?: () => void;
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
  discardingFace,
  settingDefaultFace = false,
  togglingMark,
  restoringDate,
  openingDefaultApp,
  onZoomToFace,
  onNameFace,
  onAssignFace,
  onDiscardFace,
  onSetDefaultFace,
  onCloseActiveFace,
  onToggleMark,
  onShowDateModal,
  onRestoreDate,
  onShowSimilar,
  onShowLive,
  onOpenInDefaultApp,
  onRevealInFolder,
  onFilterByTag,
  onExportPhoto,
}: LightboxSidebarProps) {
  const { prefs } = useApp();
  const isFav = marks.includes("favourite");
  const isHidden = marks.includes("hidden");
  const [personMenuOpen, setPersonMenuOpen] = useState(false);
  const personMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!personMenuOpen) return;
    const onOutside = (e: MouseEvent) => {
      if (personMenuRef.current && !personMenuRef.current.contains(e.target as Node)) {
        setPersonMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [personMenuOpen]);

  return (
    <aside className="w-[300px] shrink-0 border-l border-subtle bg-card p-3.5 flex flex-col gap-3 overflow-hidden">
      <div className="flex flex-col gap-2.5 flex-1 min-h-0 overflow-y-auto pr-1 pb-1">
        {[
          ["Date Taken", formatDate(photo.effective_ts || photo.exif_ts, { timezone: prefs.timezone, dateFormat: prefs.dateFormat })],
          ["Date Source", photo.ts_source || "—"],
          ["Resolution", formatDims(photo.width, photo.height)],
          [
            "File Size",
            photo.size != null
              ? photo.size >= 1024 * 1024
                ? `${(photo.size / (1024 * 1024)).toFixed(2)} MB`
                : `${(photo.size / 1024).toFixed(1)} KB`
              : "—",
          ],
          ["Format", String(photo.format || "Unknown").toUpperCase()],
          ["Faces Detected", String(faces.length)],
          ["Quality Score", formatQuality(photo.quality)],
          ...(photo.sharpness != null ? [["Sharpness", photo.sharpness.toFixed(1)]] : []),
          ...(photo.brightness != null ? [["Brightness", photo.brightness.toFixed(1)]] : []),
          ...(photo.duration_s != null ? [["Duration", `${photo.duration_s.toFixed(1)}s`]] : []),
          ...(photo.place ? [["Place", photo.place]] : []),
          ...(photo.gps_lat != null && photo.gps_lon != null
            ? [["GPS", `${photo.gps_lat.toFixed(5)}, ${photo.gps_lon.toFixed(5)}`]]
            : []),
          ...(photo.sha256 ? [["SHA-256", `${photo.sha256.slice(0, 16)}…`]] : []),
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
        <div className="p-2.5 bg-violet-bg/35 border border-violet/65 rounded-xs flex flex-col gap-2 shrink-0">
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
            <div className="relative" ref={personMenuRef}>
              <button
                type="button"
                disabled={assigningFace}
                onClick={() => setPersonMenuOpen(o => !o)}
                className="w-full h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary flex items-center justify-between gap-1.5 hover:border-violet/60 focus:outline-none focus:border-violet disabled:opacity-50 cursor-pointer"
              >
                <span className="truncate">
                  {assigningFace ? "Assigning..." : "Assign to existing person..."}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-secondary shrink-0" />
              </button>
              {personMenuOpen && (
                <div className="absolute left-0 right-0 bottom-full mb-1 z-30 max-h-72 overflow-y-auto bg-card border border-hairline rounded-sm shadow-xl py-1.5 flex flex-col gap-0.5">
                  {persons.map(p => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => {
                        setPersonMenuOpen(false);
                        onAssignFace(p.id);
                      }}
                      className="w-full px-2.5 py-1.5 text-left text-xs text-primary hover:bg-elevated flex items-center gap-2.5 cursor-pointer"
                    >
                      <PersonAvatar person={p} size="md" />
                      <span className="truncate flex-1 font-medium">{p.name}</span>
                      <span className="text-[11px] font-mono text-secondary shrink-0">
                        {p.image_count || 0}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {activeFace.person_id != null && onSetDefaultFace && (
            <button
              type="button"
              disabled={settingDefaultFace}
              onClick={() => onSetDefaultFace(activeFace.person_id as number, activeFace.id)}
              className="w-full h-7 px-2 inline-flex items-center justify-center gap-1.5 rounded-xs border border-violet/50 bg-violet/10 text-xs font-medium text-violet hover:bg-violet/20 disabled:opacity-50 cursor-pointer"
            >
              <span>{settingDefaultFace ? "Setting default..." : "Set as Default Face"}</span>
            </button>
          )}
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              disabled={assigningFace || discardingFace}
              onClick={() => onAssignFace(null)}
              className="text-xs text-danger hover:underline disabled:opacity-50 cursor-pointer"
            >
              {assigningFace ? "Updating..." : "Remove from person"}
            </button>
            <button
              type="button"
              disabled={assigningFace || discardingFace}
              onClick={() => onDiscardFace(activeFace.id)}
              title="Discard this detection completely (not a face)"
              className="text-xs text-danger font-medium hover:underline disabled:opacity-50 cursor-pointer"
            >
              {discardingFace ? "Discarding..." : "Not a Face"}
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
          className={`h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs border text-xs font-medium transition-all duration-150 active:scale-[0.98] disabled:opacity-50 cursor-pointer ${
            isFav
              ? "bg-amber-bg border-amber text-amber font-semibold hover:bg-amber/20"
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
          className="btn-neutral h-8 px-3 text-xs inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:bg-elevated hover:border-accent-secondary/50 active:scale-[0.98] cursor-pointer"
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
          <button
            type="button"
            onClick={onShowDateModal}
            className="btn-neutral h-8 px-2 text-xs inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:bg-elevated hover:border-amber/50 active:scale-[0.98] cursor-pointer"
          >
            <Calendar className="w-3.5 h-3.5 text-amber shrink-0" strokeWidth={1.6} />
            <span>Correct Date</span>
          </button>
          <button
            type="button"
            disabled={restoringDate}
            onClick={onRestoreDate}
            className="btn-neutral h-8 px-2 text-xs inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:bg-elevated hover:border-accent-secondary/50 active:scale-[0.98] cursor-pointer"
          >
            <RotateCcw
              className={`w-3.5 h-3.5 shrink-0 ${restoringDate ? "animate-spin" : ""}`}
              strokeWidth={1.6}
            />
            <span>{restoringDate ? "Restoring..." : "Restore"}</span>
          </button>
        </div>
        <button
          type="button"
          onClick={onShowSimilar}
          className="btn-secondary h-8 px-3 text-xs inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:bg-elevated hover:border-accent-secondary/70 hover:text-accent-secondary active:scale-[0.98] cursor-pointer"
        >
          <Sparkles className="w-3.5 h-3.5 shrink-0" strokeWidth={1.6} />
          <span>Find Similar</span>
        </button>
        {liveVideo && (
          <button
            type="button"
            onClick={onShowLive}
            className="btn-primary h-8 px-3 text-xs inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:brightness-110 active:scale-[0.98] cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 shrink-0" strokeWidth={1.7} />
            <span>Play Live Photo</span>
          </button>
        )}
        {onExportPhoto && (
          <button
            type="button"
            onClick={onExportPhoto}
            className="btn-primary h-8 px-3 text-xs"
          >
            <Download className="w-3.5 h-3.5 shrink-0" strokeWidth={1.7} />
            <span>Export Photo...</span>
          </button>
        )}
        {photo.path && (
          <div className="grid grid-cols-2 gap-1.5">
            <button
              type="button"
              disabled={openingDefaultApp}
              onClick={onOpenInDefaultApp}
              className="btn-neutral h-8 px-2 text-xs inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:bg-elevated hover:border-accent-secondary/50 active:scale-[0.98] cursor-pointer"
            >
              {openingDefaultApp ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary shrink-0" />
              ) : (
                <ExternalLink className="w-3.5 h-3.5 shrink-0" strokeWidth={1.6} />
              )}
              <span>Default App</span>
            </button>
            <button
              type="button"
              onClick={() => onRevealInFolder(photo.path as string)}
              className="btn-neutral h-8 px-2 text-xs text-secondary hover:text-primary inline-flex items-center justify-center gap-1.5 transition-all duration-150 hover:bg-elevated hover:border-accent-secondary/50 active:scale-[0.98] cursor-pointer"
            >
              <FolderOpen className="w-3.5 h-3.5 shrink-0" strokeWidth={1.6} />
              <span>In Folder</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
