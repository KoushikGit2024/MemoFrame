import { useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { mediaUrl, rpc } from "../../shared/lib/api";
import type { PhotoRecord } from "../../shared/types/memoframe";
import ModalShell from "../../shared/ui/ModalShell";
import PhotoCard from "../../shared/ui/PhotoCard";

interface SimilarPhotosModalProps {
  imageId: number;
  onClose?: () => void;
  onOpenPhoto?: (photo: PhotoRecord) => void;
}

export function SimilarPhotosModal({ imageId, onClose, onOpenPhoto }: SimilarPhotosModalProps) {
  const [items, setItems] = useState<PhotoRecord[]>([]);
  const [status, setStatus] = useState("Searching...");

  useEffect(() => {
    let alive = true;
    rpc<PhotoRecord[]>("photos.similar", { image_id: imageId, limit: 24 })
      .then(res => {
        if (!alive) return;
        const list = res || [];
        setItems(list);
        setStatus(
          list.length
            ? `${list.length} similar photo(s), best match first.`
            : "No similar photos found."
        );
      })
      .catch(err => {
        if (alive) setStatus(err instanceof Error ? err.message : String(err));
      });
    return () => {
      alive = false;
    };
  }, [imageId]);

  return (
    <ModalShell
      title="Similar Photos"
      subtitle={status}
      size="lg"
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose} className="btn-neutral h-8 px-3 text-xs">
          Close
        </button>
      }
    >
      <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-3">
        {items.map(it => {
          const pct = Math.round(Number(it.similarity || 0) * 100);
          return (
            <div key={it.id} className="flex flex-col gap-1">
              <PhotoCard photo={it} onOpen={onOpenPhoto} />
              <div
                className={`text-center font-mono text-[11px] ${pct >= 80 ? "text-accent-secondary font-medium" : "text-secondary"}`}
              >
                {pct}% similar
              </div>
            </div>
          );
        })}
      </div>
    </ModalShell>
  );
}

export function FailedPhotosModal({ onClose }: { onClose?: () => void }) {
  const [items, setItems] = useState<PhotoRecord[]>([]);

  useEffect(() => {
    rpc<PhotoRecord[]>("photos.failed", { limit: 500 })
      .then(res => setItems(res || []))
      .catch(() => {});
  }, []);

  return (
    <ModalShell
      title="Failed Photos"
      subtitle="Images that encountered errors during indexing or processing."
      size="lg"
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose} className="btn-neutral h-8 px-3 text-xs">
          Close
        </button>
      }
    >
      <div className="max-h-[420px] overflow-auto border border-subtle rounded-xs">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="sticky top-0 z-10 bg-elevated border-b border-hairline text-[11px] uppercase text-secondary">
              <th className="py-2 px-2.5 text-left w-16">ID</th>
              <th className="py-2 px-2.5 text-left">File Path</th>
              <th className="py-2 px-2.5 text-left">Error</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-8 text-center text-secondary">
                  No failed photos.
                </td>
              </tr>
            ) : (
              items.map(it => (
                <tr key={it.id} className="border-b border-subtle">
                  <td className="py-1.5 px-2.5 font-mono text-secondary">{it.id}</td>
                  <td
                    className="py-1.5 px-2.5 font-mono text-[11px] max-w-[300px] truncate"
                    title={it.path}
                  >
                    {it.path}
                  </td>
                  <td className="py-1.5 px-2.5 text-danger">{it.error || "Unknown error"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </ModalShell>
  );
}

interface ResetWorkspaceModalProps {
  onClose?: () => void;
  onConfirm?: (opts: { clear_sources: boolean; clear_saved_searches: boolean }) => void;
}

export function ResetWorkspaceModal({ onClose, onConfirm }: ResetWorkspaceModalProps) {
  const [clearSources, setClearSources] = useState(false);
  const [clearSaved, setClearSaved] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  return (
    <ModalShell
      title="Reset Workspace Data"
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-neutral h-8 px-3 text-xs">
            Cancel
          </button>
          <button
            type="button"
            disabled={confirmText.trim() !== "RESET"}
            onClick={() =>
              onConfirm?.({ clear_sources: clearSources, clear_saved_searches: clearSaved })
            }
            className="h-8 px-3 inline-flex items-center justify-center rounded-xs bg-danger text-danger-text text-xs font-medium hover:bg-danger-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Reset Workspace
          </button>
        </>
      }
    >
      <p className="text-xs text-secondary leading-relaxed">
        This deletes the photo index, detected faces, all person names, groups, and cached
        thumbnails. Your original photos stay untouched on disk.
      </p>
      <label className="inline-flex items-center gap-2 text-xs text-primary cursor-pointer">
        <input
          type="checkbox"
          checked={clearSources}
          onChange={e => setClearSources(e.target.checked)}
          className="accent-danger"
        />
        <span>Also forget scanned folders</span>
      </label>
      <label className="inline-flex items-center gap-2 text-xs text-primary cursor-pointer">
        <input
          type="checkbox"
          checked={clearSaved}
          onChange={e => setClearSaved(e.target.checked)}
          className="accent-danger"
        />
        <span>Also delete saved searches</span>
      </label>
      <input
        type="text"
        value={confirmText}
        onChange={e => setConfirmText(e.target.value)}
        placeholder="Type RESET to confirm"
        className="h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs font-mono text-primary focus:outline-none focus:border-danger focus:ring-1 focus:ring-danger/30"
      />
    </ModalShell>
  );
}

export function LivePhotoModal({
  videoPath,
  onClose,
}: {
  videoPath: string;
  onClose?: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  return (
    <ModalShell
      title="Live Photo"
      size="md"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={() => {
              if (videoRef.current) {
                videoRef.current.currentTime = 0;
                videoRef.current.play();
              }
            }}
            className="btn-primary h-8 px-3 text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Replay</span>
          </button>
          <button type="button" onClick={onClose} className="btn-neutral h-8 px-3 text-xs">
            Close
          </button>
        </>
      }
    >
      <video
        ref={videoRef}
        src={mediaUrl(videoPath)}
        autoPlay
        controls
        className="w-full max-h-[65vh] bg-black rounded-xs"
      />
    </ModalShell>
  );
}
