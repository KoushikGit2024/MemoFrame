import React, { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Clock, Loader2, RefreshCw } from "lucide-react";
import { useApp } from "../context/AppContext";
import { rpc } from "../lib/api";
import { LatestTask } from "../lib/utils";
import type { TimelineGroup } from "../types/memoframe";
import EmptyState from "../components/EmptyState";
import PhotoCard from "../components/PhotoCard";

const PAGE_STEP = 20;

interface TimelineResult {
  groups: TimelineGroup[];
  total: number;
}

interface TimelineGroupRowProps {
  group: TimelineGroup;
  onOpenPhoto: (photo: TimelineGroup["photos"] extends (infer P)[] | undefined ? P : never) => void;
  onOpenGroup: (id: number, name: string) => void;
}

const TimelineGroupRow = React.memo(function TimelineGroupRow({
  group: g,
  onOpenPhoto,
  onOpenGroup,
}: TimelineGroupRowProps) {
  const name = g.name || `Event #${g.id}`;
  const start = (g.start_ts || "").slice(0, 10);
  const end = (g.end_ts || "").slice(0, 10);
  const dateText = !start ? "" : !end || start === end ? start : `${start} to ${end}`;
  const photos = g.photos || [];
  const extra = Math.max(0, Number(g.image_count || 0) - photos.length);

  return (
    <section
      style={{ contentVisibility: "auto", containIntrinsicSize: "260px" }}
      className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-3"
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="text-sm font-semibold text-primary">{name}</h2>
          {dateText && (
            <span className="h-5 px-2 inline-flex items-center rounded-xs bg-amber-bg border border-amber/35 font-mono text-[11px] text-amber">
              {dateText}
            </span>
          )}
          <span className="h-5 px-2 inline-flex items-center rounded-xs bg-accent-light border border-accent/40 font-mono text-[11px] text-accent">
            {g.image_count || 0} photos
          </span>
        </div>
        <button
          type="button"
          onClick={() => onOpenGroup(Number(g.id), name)}
          className="h-7 px-2.5 inline-flex items-center gap-1 rounded-xs text-xs font-medium text-accent-secondary hover:bg-accent-secondary-light transition-colors"
        >
          <span>View all {g.image_count || 0}</span>
          <ArrowRight className="w-3.5 h-3.5" strokeWidth={1.6} />
        </button>
      </div>

      <div className="flex items-center gap-2.5 overflow-x-auto pb-1">
        {photos.map(p => (
          <PhotoCard key={p.id} photo={p} onOpen={onOpenPhoto} className="w-[196px] shrink-0" />
        ))}
        {extra > 0 && (
          <button
            type="button"
            onClick={() => onOpenGroup(Number(g.id), name)}
            className="w-28 h-[148px] shrink-0 rounded-sm border border-dashed border-hairline bg-elevated/40 hover:border-accent-secondary hover:text-accent-secondary flex flex-col items-center justify-center text-xs text-secondary gap-1 transition-colors"
          >
            <span className="font-mono font-semibold text-primary">+{extra}</span>
            <span>more</span>
          </button>
        )}
      </div>
    </section>
  );
});

export default function TimelineView() {
  const { connected, dataVersion, notify, setLightboxPhoto, openGroupInGallery } = useApp();
  const [groups, setGroups] = useState<TimelineGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const loaderRef = useRef(new LatestTask());

  const loadPage = useCallback(
    (offset = 0, append = false) => {
      if (!connected) return;
      setLoading(true);
      loaderRef.current.run(
        () =>
          rpc<TimelineResult>("timeline.groups", { limit: PAGE_STEP, offset, preview_limit: 8 }),
        res => {
          setLoading(false);
          if (!res) return;
          setTotal(res.total || 0);
          setGroups(prev => (append ? [...prev, ...(res.groups || [])] : res.groups || []));
        },
        err => {
          setLoading(false);
          notify(err.message, "error");
        }
      );
    },
    [connected, notify]
  );

  useEffect(() => {
    loadPage(0, false);
  }, [loadPage, dataVersion]);

  const remaining = Math.max(0, total - groups.length);

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">
            Events &amp; Timeline Groups ({total})
          </h1>
          <p className="text-xs text-secondary mt-0.5">
            Chronological bursts and automatically clustered photo events.
          </p>
        </div>
        <button
          type="button"
          onClick={() => loadPage(0, false)}
          className="btn-neutral h-8 px-2.5 text-xs"
        >
          <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.6} />
          <span>Refresh</span>
        </button>
      </div>

      {groups.length === 0 && !loading ? (
        <EmptyState
          icon={Clock}
          title="No Timeline Events Yet"
          description="Event groups appear here once photos with timestamps are indexed."
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-3">
          {groups.map(g => (
            <TimelineGroupRow
              key={g.id}
              group={g}
              onOpenPhoto={setLightboxPhoto}
              onOpenGroup={openGroupInGallery}
            />
          ))}

          {remaining > 0 && (
            <button
              type="button"
              disabled={loading}
              onClick={() => loadPage(groups.length, true)}
              className="btn-neutral h-9 px-4 self-center text-xs mb-3"
            >
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />}
              <span>
                {loading
                  ? "Loading more events..."
                  : `Show ${Math.min(PAGE_STEP, remaining)} more (${remaining} remaining)`}
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
