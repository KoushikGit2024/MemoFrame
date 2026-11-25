import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CheckCircle2, Loader2, RefreshCw, Star } from "lucide-react";
import { useApp } from "../context/AppContext";
import { rpc } from "../lib/api";
import { formatDims, formatQuality, LatestTask } from "../lib/utils";
import type { DuplicateCluster } from "../types/memoframe";
import EmptyState from "../components/EmptyState";
import PhotoCard from "../components/PhotoCard";

export default function DuplicatesView() {
  const { connected, dataVersion, invalidate, notify, setLightboxPhoto } = useApp();
  const [clusters, setClusters] = useState<DuplicateCluster[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const loaderRef = useRef(new LatestTask());

  const loadClusters = useCallback(() => {
    if (!connected) return;
    loaderRef.current.run(
      () => rpc<DuplicateCluster[]>("duplicates.list"),
      res => {
        const list = res || [];
        setClusters(list);
        setSelectedIdx(idx => (list.length ? Math.min(idx, list.length - 1) : 0));
      },
      err => notify(err.message, "error")
    );
  }, [connected, notify]);

  useEffect(() => {
    loadClusters();
  }, [loadClusters, dataVersion]);

  const activeCluster = clusters[selectedIdx] || null;

  const keepSingle = async (keepId: number) => {
    if (!activeCluster || busy) return;
    setBusy(true);
    try {
      const hideIds = activeCluster.photos.filter(p => p.id !== keepId).map(p => p.id);
      await rpc("duplicates.resolve", { keep_id: keepId, hide_ids: hideIds });
      notify(`Kept photo #${keepId} and hid ${hideIds.length} duplicate(s).`, "success");
      invalidate();
      loadClusters();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">
            Duplicate Clusters ({clusters.length})
          </h1>
          <p className="text-xs text-secondary mt-0.5">
            Compare duplicate candidates side-by-side and keep the sharpest copy in one click.
          </p>
        </div>
        <button type="button" onClick={loadClusters} className="btn-neutral h-8 px-2.5 text-xs">
          <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.6} />
          <span>Refresh</span>
        </button>
      </div>

      {clusters.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title="No Duplicate Clusters Found"
          description="Your library has no unresolved duplicate photo clusters."
        />
      ) : (
        <div className="flex-1 min-h-0 flex gap-3 overflow-hidden">
          <div className="w-60 shrink-0 bg-card border border-subtle rounded-sm flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-subtle text-[10px] font-semibold uppercase tracking-[0.08em] text-secondary">
              Clusters
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 flex flex-col gap-0.5">
              {clusters.map((cl, idx) => (
                <button
                  key={cl.cluster_id}
                  type="button"
                  onClick={() => setSelectedIdx(idx)}
                  className={`w-full px-2.5 py-2 rounded-xs border text-left flex items-center justify-between text-xs transition-colors ${
                    idx === selectedIdx
                      ? "bg-amber-bg border-amber/55 text-amber font-semibold"
                      : "bg-transparent border-transparent text-primary hover:bg-elevated"
                  }`}
                >
                  <span>Cluster #{idx + 1}</span>
                  <span
                    className={`font-mono text-[11px] capitalize ${idx === selectedIdx ? "text-amber" : "text-secondary"}`}
                  >
                    {cl.photos.length} · {cl.kind}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 min-w-0 flex flex-col gap-2.5 overflow-hidden">
            {activeCluster && (
              <>
                <div className="flex items-center justify-between shrink-0">
                  <span className="text-xs font-semibold text-primary">
                    Comparing Cluster #{selectedIdx + 1} · {activeCluster.photos.length} Photos
                  </span>
                  <span className="text-xs text-secondary capitalize">
                    {activeCluster.kind} match
                  </span>
                </div>
                <div className="flex-1 min-h-0 flex items-start gap-3.5 overflow-x-auto overflow-y-auto pb-2">
                  {activeCluster.photos.map(photo => {
                    const isBest = photo.id === activeCluster.best_image_id;
                    return (
                      <div
                        key={photo.id}
                        className={`w-[300px] shrink-0 bg-card border rounded-sm p-3 flex flex-col gap-2.5 ${isBest ? "border-amber/60" : "border-subtle"}`}
                      >
                        <div className="flex items-center justify-between">
                          <span
                            className={`h-5 px-2 inline-flex items-center gap-1 rounded-xs border text-[11px] font-medium ${isBest ? "bg-amber-bg border-amber/45 text-amber" : "bg-badge border-hairline text-secondary"}`}
                          >
                            {isBest && (
                              <Star className="w-3 h-3 text-amber fill-current" strokeWidth={1.8} />
                            )}
                            <span>{isBest ? "Recommended Keeper" : "Duplicate Copy"}</span>
                          </span>
                          <span className="font-mono text-[11px] text-secondary">#{photo.id}</span>
                        </div>
                        <PhotoCard photo={photo} onOpen={setLightboxPhoto} />
                        <div className="flex items-center justify-between text-xs font-mono text-secondary px-0.5 tabular-nums">
                          <span>{formatDims(photo.width, photo.height)}</span>
                          <span>Quality {formatQuality(photo.quality)}</span>
                        </div>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => keepSingle(photo.id)}
                          className={`h-8 px-3 text-xs ${isBest ? "btn-success" : "btn-neutral hover:border-accent-secondary"}`}
                        >
                          {busy ? (
                            <Loader2
                              className={`w-3.5 h-3.5 animate-spin ${isBest ? "text-success-text" : "text-secondary"}`}
                            />
                          ) : (
                            <Check className="w-3.5 h-3.5" strokeWidth={1.8} />
                          )}
                          <span>{busy ? "Resolving..." : "Keep This Only"}</span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
