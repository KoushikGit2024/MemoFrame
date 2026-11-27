import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Download,
  Gauge,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { rpc } from "../../shared/lib/api";
import type {
  AnalyticsActivity,
  AnalyticsErrors,
  AnalyticsOverview,
  AnalyticsPerformance,
  AnalyticsRange,
} from "../../shared/types/memoframe";
import {
  DonutChart,
  HistogramChart,
  HorizontalBarChart,
  TrendLineChart,
} from "./AnalyticsCharts";
import ErrorIntelligencePanel from "./ErrorIntelligencePanel";

type AnalyticsTab = "overview" | "activity" | "performance" | "errors";

const RANGES: ReadonlyArray<{ key: AnalyticsRange; label: string }> = [
  { key: "24h", label: "24h" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "90d", label: "90d" },
  { key: "all", label: "All Time" },
];

export default function AnalyticsView() {
  const { connected, dataVersion, notify, unresolvedErrors } = useApp();
  const [tab, setTab] = useState<AnalyticsTab>("overview");
  const [range, setRange] = useState<AnalyticsRange>("all");
  const [loading, setLoading] = useState(false);

  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [activity, setActivity] = useState<AnalyticsActivity | null>(null);
  const [errStats, setErrStats] = useState<AnalyticsErrors | null>(null);
  const [perf, setPerf] = useState<AnalyticsPerformance | null>(null);

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, act, errs, pf] = await Promise.all([
        rpc<AnalyticsOverview>("analytics.overview", { range }),
        rpc<AnalyticsActivity>("analytics.activity", { range }),
        rpc<AnalyticsErrors>("analytics.errors", { range }),
        rpc<AnalyticsPerformance>("analytics.performance", { range }),
      ]);
      setOverview(ov);
      setActivity(act);
      setErrStats(errs);
      setPerf(pf);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setLoading(false);
    }
  }, [range, notify]);

  useEffect(() => {
    void loadAnalytics();
  }, [loadAnalytics, dataVersion]);

  const handleExport = async (format: "json" | "csv") => {
    try {
      const res = await rpc<{ filename: string; content: string }>("analytics.export", {
        format,
        range,
      });
      const blob = new Blob([res.content], {
        type: format === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      URL.revokeObjectURL(url);
      notify(`Exported ${res.filename}`, "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  };

  const lib = overview?.library;
  const rpcInfo = overview?.rpc;
  const namedPct =
    lib && lib.total_faces > 0 ? Math.round((lib.named_faces / lib.total_faces) * 100) : 0;

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">
            Analytics &amp; Reliability Center
          </h1>
          <p className="text-xs text-secondary mt-0.5">
            Real-time library intelligence, RPC latency telemetry, error diagnostics, and recovery history.
          </p>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <div className="inline-flex bg-input border border-hairline rounded-xs p-0.5 gap-0.5">
            {RANGES.map(r => (
              <button
                key={r.key}
                type="button"
                onClick={() => setRange(r.key)}
                className={`h-6 px-2 text-xs rounded-xs cursor-pointer transition-colors ${
                  range === r.key
                    ? "bg-accent-secondary-light text-accent-secondary font-semibold"
                    : "text-secondary hover:text-primary"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void handleExport("csv")}
            className="btn-neutral h-7 px-2.5 text-xs"
          >
            <Download className="w-3.5 h-3.5" />
            <span>CSV</span>
          </button>
          <button
            type="button"
            onClick={() => void handleExport("json")}
            className="btn-neutral h-7 px-2.5 text-xs"
          >
            <Download className="w-3.5 h-3.5" />
            <span>JSON</span>
          </button>
          <button
            type="button"
            onClick={() => void loadAnalytics()}
            className="btn-neutral h-7 px-2.5 text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Sub-navigation */}
      <div className="shrink-0 flex items-center gap-1 border-b border-subtle pb-2 flex-wrap">
        {(
          [
            ["overview", "Overview", BarChart3],
            ["activity", "Library & Activity", Activity],
            ["performance", "Performance", Gauge],
            ["errors", `Error Intelligence${unresolvedErrors ? ` (${unresolvedErrors})` : ""}`, AlertTriangle],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`h-8 px-3 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium cursor-pointer transition-colors ${
              tab === key
                ? "bg-elevated border-accent-secondary/60 text-primary font-semibold"
                : "bg-transparent border-transparent text-secondary hover:text-primary hover:bg-elevated/50"
            }`}
          >
            <Icon className="w-3.5 h-3.5" strokeWidth={1.7} />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto pr-1 pb-4">
        {loading && !overview ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-20 bg-card border border-subtle rounded-sm animate-shimmer" />
            ))}
          </div>
        ) : tab === "overview" ? (
          <div className="flex flex-col gap-4">
            {/* KPI Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {[
                ["Indexed Photos", (lib?.total_images ?? 0).toLocaleString(), `${lib?.videos ?? 0} videos · ${lib?.total_size_mb ?? 0} MB`, "border-l-accent-secondary"],
                ["Faces Detected", (lib?.total_faces ?? 0).toLocaleString(), `${namedPct}% named across ${lib?.persons ?? 0} people`, "border-l-violet"],
                ["Events & Clusters", `${lib?.groups ?? 0} / ${lib?.duplicate_clusters ?? 0}`, `${lib?.bursts ?? 0} bursts · avg quality ${lib?.avg_quality ?? 0}%`, "border-l-amber"],
                ["RPC Requests", (rpcInfo?.total_requests ?? 0).toLocaleString(), `${rpcInfo?.success_rate ?? 100}% success · ${rpcInfo?.avg_latency_ms ?? 0}ms avg`, "border-l-accent"],
                ["Engine Status", connected ? "Connected" : "Offline", `Uptime ${Math.round(overview?.uptime_seconds ?? 0)}s`, connected ? "border-l-success" : "border-l-danger"],
                ["Unresolved Errors", String(overview?.errors.unresolved_count ?? 0), `${rpcInfo?.error_rate ?? 0}% RPC error rate`, (overview?.errors.unresolved_count ?? 0) > 0 ? "border-l-danger" : "border-l-success"],
                ["Recovery Rate", `${overview?.errors.recovery_rate ?? 0}%`, `${overview?.errors.recovery_succeeded ?? 0}/${overview?.errors.recovery_attempts ?? 0} attempts succeeded`, "border-l-success"],
                ["Failed Media", String(lib?.failed_images ?? 0), `${lib?.unassigned_faces ?? 0} unassigned faces`, (lib?.failed_images ?? 0) > 0 ? "border-l-amber" : "border-l-accent-secondary"],
              ].map(([label, value, sub, accent]) => (
                <div
                  key={label}
                  className={`bg-card border border-subtle border-l-2 ${accent} rounded-xs px-3 py-2.5`}
                >
                  <div className="text-[11px] text-secondary">{label}</div>
                  <div className="text-lg font-mono font-semibold text-primary tabular-nums mt-0.5">
                    {value}
                  </div>
                  <div className="text-[11px] text-secondary truncate mt-0.5">{sub}</div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
                <h2 className="text-xs font-semibold text-primary">Photos Captured Over Time</h2>
                <TrendLineChart
                  data={(activity?.photos_by_month || []).map(d => ({ label: d.label, value: d.count }))}
                  unit="photos"
                />
              </section>

              <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
                <h2 className="text-xs font-semibold text-primary">Media Format Distribution</h2>
                <DonutChart
                  data={(lib?.formats || []).map(f => ({ label: f.label, value: f.count }))}
                />
              </section>

              <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
                <h2 className="text-xs font-semibold text-primary">Errors by Severity</h2>
                <DonutChart
                  data={(errStats?.by_severity || []).map(s => ({
                    label: s.label,
                    value: s.count,
                    accent:
                      s.label === "critical" || s.label === "error"
                        ? "var(--danger)"
                        : s.label === "warning"
                          ? "var(--amber)"
                          : "var(--accent-secondary)",
                  }))}
                />
              </section>

              <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
                <h2 className="text-xs font-semibold text-primary">RPC Latency Distribution</h2>
                <HistogramChart
                  data={(perf?.latency_histogram || []).map(b => ({ label: b.bucket, value: b.count }))}
                  color="var(--accent-secondary)"
                />
              </section>
            </div>
          </div>
        ) : tab === "activity" ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2 lg:col-span-2">
              <h2 className="text-xs font-semibold text-primary">Monthly Capture Volume</h2>
              <TrendLineChart
                data={(activity?.photos_by_month || []).map(d => ({ label: d.label, value: d.count }))}
                color="var(--accent)"
                unit="photos"
              />
            </section>

            <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
              <h2 className="text-xs font-semibold text-primary">Capture Distribution by Hour (0–23)</h2>
              <HistogramChart
                data={Array.from({ length: 24 }, (_, hr) => ({
                  label: String(hr).padStart(2, "0"),
                  value: activity?.photos_by_hour.find(x => x.hour === hr)?.count || 0,
                }))}
                color="var(--amber)"
              />
            </section>

            <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
              <h2 className="text-xs font-semibold text-primary">App RPC Activity by Hour (UTC)</h2>
              <HistogramChart
                data={Array.from({ length: 24 }, (_, hr) => ({
                  label: String(hr).padStart(2, "0"),
                  value: activity?.rpc_by_hour.find(x => x.hour === hr)?.count || 0,
                }))}
                color="var(--accent-secondary)"
              />
            </section>

            <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
              <h2 className="text-xs font-semibold text-primary">Top People by Indexed Photos</h2>
              <HorizontalBarChart
                data={(activity?.top_people || []).map(p => ({ label: p.label, value: p.count }))}
                color="var(--violet)"
                unit="photos"
              />
            </section>

            <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
              <h2 className="text-xs font-semibold text-primary">Top Scene Tags</h2>
              <HorizontalBarChart
                data={(activity?.top_tags || []).map(t => ({ label: t.label, value: t.count }))}
                color="var(--success)"
              />
            </section>
          </div>
        ) : tab === "performance" ? (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
                <h2 className="text-xs font-semibold text-primary">RPC Latency Histogram</h2>
                <HistogramChart
                  data={(perf?.latency_histogram || []).map(b => ({ label: b.bucket, value: b.count }))}
                />
              </section>
              <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-2">
                <h2 className="text-xs font-semibold text-primary">Slowest RPC Methods (Avg ms)</h2>
                <HorizontalBarChart
                  data={(perf?.by_method || []).slice(0, 8).map(m => ({
                    label: `${m.method} (${m.count}×)`,
                    value: m.avg_ms,
                    accent: m.errors > 0 ? "var(--danger)" : "var(--accent-secondary)",
                  }))}
                  unit="ms"
                />
              </section>
            </div>

            <section className="bg-card border border-subtle rounded-sm overflow-auto">
              <div className="px-3.5 py-2.5 border-b border-subtle flex items-center justify-between">
                <h2 className="text-xs font-semibold text-primary">Recent Slow Operations</h2>
                <span className="text-[11px] font-mono text-secondary inline-flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-success" />
                  <span>Live RPC telemetry</span>
                </span>
              </div>
              {!perf?.slow_operations?.length ? (
                <div className="p-6 text-center text-xs text-secondary">
                  No RPC timings recorded yet.
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-elevated border-b border-hairline text-[11px] uppercase text-secondary">
                      <th className="py-2 px-3">Method</th>
                      <th className="py-2 px-3">Duration</th>
                      <th className="py-2 px-3">Status</th>
                      <th className="py-2 px-3">Correlation ID</th>
                      <th className="py-2 px-3">Timestamp (UTC)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-subtle">
                    {perf.slow_operations.map((op, idx) => (
                      <tr key={`${op.correlation_id}-${idx}`}>
                        <td className="py-1.5 px-3 font-mono text-primary">{op.method}</td>
                        <td className="py-1.5 px-3 font-mono text-amber">{op.duration_ms} ms</td>
                        <td className="py-1.5 px-3 font-mono">
                          <span className={op.status === "ok" ? "text-success" : "text-danger"}>
                            {op.status}
                            {op.error_code ? ` (${op.error_code})` : ""}
                          </span>
                        </td>
                        <td className="py-1.5 px-3 font-mono text-[11px] text-secondary">
                          {op.correlation_id}
                        </td>
                        <td className="py-1.5 px-3 font-mono text-[11px] text-secondary">
                          {op.created_at_utc}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>
        ) : (
          <ErrorIntelligencePanel range={range} />
        )}
      </div>
    </div>
  );
}
