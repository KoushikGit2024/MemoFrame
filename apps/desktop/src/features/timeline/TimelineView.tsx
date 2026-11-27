import React, { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDownUp, ArrowRight, Clock, Download, Loader2, RefreshCw, Search, X } from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { rpc } from "../../shared/lib/api";
import { formatDate, LatestTask } from "../../shared/lib/utils";
import type { TimelineGroup } from "../../shared/types/memoframe";
import EmptyState from "../../shared/ui/EmptyState";
import PhotoCard from "../../shared/ui/PhotoCard";

const PAGE_STEP = 20;

interface TimelineResult {
  groups: TimelineGroup[];
  total: number;
}

interface TimelineGroupRowProps {
  group: TimelineGroup;
  timezone: string;
  dateFormat: "iso" | "locale" | "relative";
  onOpenPhoto: (photo: TimelineGroup["photos"] extends (infer P)[] | undefined ? P : never) => void;
  onOpenGroup: (id: number, name: string) => void;
  onExportGroup: (ids: number[], name: string) => void;
}

const TimelineGroupRow = React.memo(function TimelineGroupRow({
  group: g,
  timezone,
  dateFormat,
  onOpenPhoto,
  onOpenGroup,
  onExportGroup,
}: TimelineGroupRowProps) {
  const name = g.name || `Event #${g.id}`;
  const startRaw = g.start_ts_utc || g.start_ts;
  const endRaw = g.end_ts_utc || g.end_ts;
  const start = startRaw ? formatDate(startRaw, { timezone, dateFormat }) : "";
  const end = endRaw ? formatDate(endRaw, { timezone, dateFormat }) : "";
  const dateText = !start ? "Undated" : !end || start === end ? start : `${start} → ${end}`;
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
          <span
            className={`h-5 px-2 inline-flex items-center rounded-xs border font-mono text-[11px] ${
              g.timestamp_valid === false
                ? "bg-elevated border-hairline text-secondary"
                : "bg-amber-bg border-amber/35 text-amber"
            }`}
          >
            {dateText}
          </span>
          <span className="h-5 px-2 inline-flex items-center rounded-xs bg-accent-light border border-accent/40 font-mono text-[11px] text-accent">
            {g.image_count || 0} photos
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {photos.length > 0 && (
            <button
              type="button"
              onClick={() => onExportGroup(photos.map(p => p.id), name)}
              className="btn-neutral h-7 px-2 text-xs"
            >
              <Download className="w-3 h-3" strokeWidth={1.6} />
              <span>Export</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => onOpenGroup(Number(g.id), name)}
          className="h-7 px-2.5 inline-flex items-center gap-1 rounded-xs text-xs font-medium text-accent-secondary hover:bg-accent-secondary-light transition-colors cursor-pointer"
        >
          <span>View all {g.image_count || 0}</span>
          <ArrowRight className="w-3.5 h-3.5" strokeWidth={1.6} />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2.5 overflow-x-auto pb-1">
        {photos.map(p => (
          <div key={p.id} className="w-[148px] shrink-0">
            <PhotoCard photo={p} compact onOpen={onOpenPhoto} />
          </div>
        ))}
        {extra > 0 && (
          <button
            type="button"
            onClick={() => onOpenGroup(Number(g.id), name)}
            className="w-28 h-[148px] shrink-0 rounded-sm border border-dashed border-hairline bg-elevated/40 hover:border-accent-secondary hover:text-accent-secondary flex flex-col items-center justify-center text-xs text-secondary gap-1 transition-colors cursor-pointer"
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
  const { connected, dataVersion, notify, prefs, setLightboxPhoto, openGroupInGallery, openExportModal } = useApp();
  const [groups, setGroups] = useState<TimelineGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [order, setOrder] = useState<"desc" | "asc">("desc");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const loaderRef = useRef(new LatestTask());

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(t);
  }, [search]);

  const loadPage = useCallback(
    (offset = 0, append = false) => {
      if (!connected) return;
      setLoading(true);
      loaderRef.current.run(
        () =>
          rpc<TimelineResult>("timeline.groups", {
            limit: PAGE_STEP,
            offset,
            preview_limit: 8,
            order,
            date_from: dateFrom,
            date_to: dateTo,
            search: debouncedSearch,
          }),
        res => {
          setLoading(false);
          if (!res) return;
          setTotal(res.total || 0);
          setGroups(prev => {
            if (!append) return res.groups || [];
            // Deduplicate by group ID to prevent duplicate rows if a scan shifts offsets
            const seen = new Set(prev.map(g => g.id));
            const merged = [...prev];
            for (const item of res.groups || []) {
              if (!seen.has(item.id)) {
                seen.add(item.id);
                merged.push(item);
              }
            }
            return merged;
          });
        },
        err => {
          setLoading(false);
          notify(err.message, "error");
        }
      );
    },
    [connected, order, dateFrom, dateTo, debouncedSearch, notify]
  );

  useEffect(() => {
    loadPage(0, false);
  }, [loadPage, dataVersion]);

  const remaining = Math.max(0, total - groups.length);
  const hasFilters = Boolean(dateFrom || dateTo || search);

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-3 shrink-0 flex-wrap">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">
            Events &amp; Timeline Groups ({total})
          </h1>
          <p className="text-xs text-secondary mt-0.5">
            UTC-normalized chronological events converted to your configured timezone ({prefs.timezone}).
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={() => setOrder(o => (o === "desc" ? "asc" : "desc"))}
            className="btn-neutral h-8 px-2.5 text-xs"
          >
            <ArrowDownUp className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>{order === "desc" ? "Newest First" : "Oldest First"}</span>
          </button>
          <button
            type="button"
            onClick={() => loadPage(0, false)}
            className="btn-neutral h-8 px-2.5 text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} strokeWidth={1.6} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Date-range & search bar */}
      <div className="bg-card border border-subtle rounded-xs p-2 flex items-center gap-2 flex-wrap shrink-0">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="w-3.5 h-3.5 text-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter events by name..."
            className="w-full h-7 pl-8 pr-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent-secondary"
          />
        </div>
        <label className="inline-flex items-center gap-1.5 text-xs text-secondary">
          <span>From</span>
          <input
            type="date"
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
            className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary font-mono"
          />
        </label>
        <label className="inline-flex items-center gap-1.5 text-xs text-secondary">
          <span>To</span>
          <input
            type="date"
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
            className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary font-mono"
          />
        </label>
        {hasFilters && (
          <button
            type="button"
            onClick={() => {
              setDateFrom("");
              setDateTo("");
              setSearch("");
            }}
            className="btn-neutral h-7 px-2 text-xs"
          >
            <X className="w-3 h-3" />
            <span>Clear</span>
          </button>
        )}
      </div>

      {groups.length === 0 && !loading ? (
        <EmptyState
          icon={Clock}
          title="No Timeline Events Found"
          description={
            hasFilters
              ? "No events match your active date range or search query."
              : "Event groups appear here once photos with timestamps are indexed."
          }
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-3">
          {groups.map(g => (
            <TimelineGroupRow
              key={g.id}
              group={g}
              timezone={prefs.timezone}
              dateFormat={prefs.dateFormat}
              onOpenPhoto={setLightboxPhoto}
              onOpenGroup={openGroupInGallery}
              onExportGroup={(ids, label) => openExportModal(ids, label)}
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
