import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { rpc } from "../../shared/lib/api";
import { flushErrorQueue, getErrorMonitorHealth } from "../../shared/lib/errorMonitor";
import { formatDate } from "../../shared/lib/utils";
import type {
  AnalyticsRange,
  ErrorDetailPayload,
  ErrorRecord,
  RecoveryAttempt,
} from "../../shared/types/memoframe";

interface ErrorIntelligencePanelProps {
  range: AnalyticsRange;
}

const SEV_BADGE: Record<string, string> = {
  critical: "bg-danger-bg border-danger text-danger",
  error: "bg-danger-bg border-danger/60 text-danger",
  warning: "bg-amber-bg border-amber/60 text-amber",
  info: "bg-accent-secondary-light border-accent-secondary/50 text-accent-secondary",
};

const RECOVERY_LABEL: Record<string, string> = {
  auto_recoverable: "Auto-recoverable",
  user_action: "User action",
  dev_action: "Developer action",
  never_auto: "Never auto-repair",
};

export default function ErrorIntelligencePanel({ range }: ErrorIntelligencePanelProps) {
  const { notify, prefs, refreshErrorCount } = useApp();
  const [subTab, setSubTab] = useState<"errors" | "recoveries">("errors");
  const [errors, setErrors] = useState<ErrorRecord[]>([]);
  const [recoveries, setRecoveries] = useState<RecoveryAttempt[]>([]);
  const [loading, setLoading] = useState(false);

  const [sevFilter, setSevFilter] = useState("");
  const [originFilter, setOriginFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ErrorDetailPayload | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [notesInput, setNotesInput] = useState("");
  const [busyAction, setBusyAction] = useState(false);

  const monitorHealth = getErrorMonitorHealth();

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const [errRes, recRes] = await Promise.all([
        rpc<{ items: ErrorRecord[] }>("errors.list", {
          severity: sevFilter,
          origin: originFilter,
          status: statusFilter,
          query,
          range,
          limit: 150,
        }),
        rpc<{ items: RecoveryAttempt[] }>("recoveries.list", { limit: 100 }),
      ]);
      setErrors(errRes?.items || []);
      setRecoveries(recRes?.items || []);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setLoading(false);
    }
  }, [sevFilter, originFilter, statusFilter, query, range, notify]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const loadDetail = useCallback(
    async (id: number) => {
      setSelectedId(id);
      setLoadingDetail(true);
      try {
        const res = await rpc<ErrorDetailPayload>("errors.detail", { error_id: id });
        setDetail(res);
        setNotesInput(res?.error?.notes || "");
      } catch (err) {
        notify(err instanceof Error ? err.message : String(err), "error");
      } finally {
        setLoadingDetail(false);
      }
    },
    [notify]
  );

  const handleStatusUpdate = async (status: ErrorRecord["status"]) => {
    if (!selectedId) return;
    setBusyAction(true);
    try {
      await rpc("errors.update_status", { error_id: selectedId, status, notes: notesInput });
      notify(`Error #${selectedId} marked as ${status}.`, "success");
      refreshErrorCount();
      await Promise.all([loadList(), loadDetail(selectedId)]);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusyAction(false);
    }
  };

  const handleTriggerRecovery = async (strategy: string) => {
    if (!selectedId) return;
    setBusyAction(true);
    try {
      const res = await rpc<{ attempt: RecoveryAttempt }>("errors.recover", {
        error_id: selectedId,
        strategy,
      });
      const out = res?.attempt?.outcome || "failed";
      notify(
        `Recovery (${strategy}) ${out}: ${res?.attempt?.detail || ""}`,
        out === "succeeded" ? "success" : "error"
      );
      refreshErrorCount();
      await Promise.all([loadList(), loadDetail(selectedId)]);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusyAction(false);
    }
  };

  const handleFlushQueue = async () => {
    const flushed = await flushErrorQueue();
    notify(`Flushed ${flushed} locally queued error(s).`, "info");
    await loadList();
  };

  const fmtOpts = { timezone: prefs.timezone, dateFormat: prefs.dateFormat };

  return (
    <div className="flex flex-col gap-3">
      {/* Monitoring self-health bar */}
      <div className="bg-card border border-subtle rounded-sm px-3 py-2 flex items-center justify-between gap-3 flex-wrap text-xs">
        <div className="flex items-center gap-2 flex-wrap">
          <ShieldAlert className="w-3.5 h-3.5 text-accent-secondary shrink-0" strokeWidth={1.7} />
          <span className="font-semibold text-primary">Error Monitor Self-Check:</span>
          <span className="font-mono text-success">
            {monitorHealth.installed ? "Active" : "Inactive"}
          </span>
          <span className="text-secondary">•</span>
          <span className="text-secondary">
            Local Fallback Queue:{" "}
            <strong className="font-mono text-primary">{monitorHealth.queuedCount}</strong>
          </span>
          {monitorHealth.droppedCount > 0 && (
            <span className="font-mono text-amber">
              ({monitorHealth.droppedCount} dropped by cap)
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {monitorHealth.queuedCount > 0 && (
            <button type="button" onClick={handleFlushQueue} className="btn-secondary h-7 px-2.5 text-xs">
              Flush Local Queue
            </button>
          )}
          <div className="inline-flex bg-input border border-hairline rounded-xs p-0.5 gap-0.5">
            <button
              type="button"
              onClick={() => setSubTab("errors")}
              className={`h-6 px-2.5 text-xs rounded-xs cursor-pointer ${
                subTab === "errors"
                  ? "bg-elevated text-primary font-semibold"
                  : "text-secondary hover:text-primary"
              }`}
            >
              Errors ({errors.length})
            </button>
            <button
              type="button"
              onClick={() => setSubTab("recoveries")}
              className={`h-6 px-2.5 text-xs rounded-xs cursor-pointer ${
                subTab === "recoveries"
                  ? "bg-elevated text-primary font-semibold"
                  : "text-secondary hover:text-primary"
              }`}
            >
              Recovery History ({recoveries.length})
            </button>
          </div>
        </div>
      </div>

      {subTab === "errors" ? (
        <>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="w-3.5 h-3.5 text-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search message, module, category, code..."
                className="w-full h-8 pl-8 pr-2.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent-secondary"
              />
            </div>
            <select
              value={sevFilter}
              onChange={e => setSevFilter(e.target.value)}
              className="h-8 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="error">Error</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
            <select
              value={originFilter}
              onChange={e => setOriginFilter(e.target.value)}
              className="h-8 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
            >
              <option value="">All Origins</option>
              <option value="frontend">Frontend</option>
              <option value="backend">Backend</option>
              <option value="bridge">Bridge</option>
            </select>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="h-8 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
            >
              <option value="">All Statuses</option>
              <option value="detected">Detected</option>
              <option value="investigating">Investigating</option>
              <option value="recovered">Recovered</option>
              <option value="resolved">Resolved</option>
            </select>
            <button type="button" onClick={() => void loadList()} className="btn-neutral h-8 px-2.5 text-xs">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <div className="lg:col-span-7 bg-card border border-subtle rounded-sm overflow-hidden">
              {errors.length === 0 ? (
                <div className="p-8 text-center text-xs text-secondary flex flex-col items-center gap-2">
                  <CheckCircle2 className="w-6 h-6 text-success" strokeWidth={1.6} />
                  <span>No errors recorded for the active filter.</span>
                </div>
              ) : (
                <div className="max-h-[460px] overflow-y-auto divide-y divide-subtle">
                  {errors.map(err => (
                    <button
                      key={err.id}
                      type="button"
                      onClick={() => void loadDetail(err.id)}
                      className={`w-full text-left p-3 flex flex-col gap-1 transition-colors cursor-pointer ${
                        selectedId === err.id ? "bg-elevated" : "hover:bg-elevated/50"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span
                            className={`px-1.5 py-0.5 rounded-xs border text-[10px] font-mono uppercase ${
                              SEV_BADGE[err.severity] || SEV_BADGE.error
                            }`}
                          >
                            {err.severity}
                          </span>
                          <span className="font-mono text-[11px] text-secondary truncate">
                            {err.origin}:{err.module}
                          </span>
                        </div>
                        <span className="font-mono text-[11px] text-primary shrink-0">
                          ×{err.occurrence_count}
                        </span>
                      </div>
                      <div className="text-xs text-primary line-clamp-2">{err.message}</div>
                      <div className="flex items-center justify-between gap-2 text-[10.5px] font-mono text-secondary">
                        <span>
                          {err.status} · {RECOVERY_LABEL[err.recovery_class] || err.recovery_class}
                        </span>
                        <span>{formatDate(err.last_seen_utc, fmtOpts)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="lg:col-span-5 bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-3">
              {!selectedId ? (
                <div className="h-full min-h-[260px] flex flex-col items-center justify-center text-xs text-secondary text-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-secondary/70" />
                  <span>Select an error record to inspect stack trace, correlation chain, and recovery options.</span>
                </div>
              ) : loadingDetail || !detail ? (
                <div className="h-full min-h-[260px] flex items-center justify-center gap-2 text-xs text-secondary">
                  <Loader2 className="w-4 h-4 animate-spin text-accent-secondary" />
                  <span>Loading diagnostic details...</span>
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2 border-b border-subtle pb-2">
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-primary">
                        Error #{detail.error.id} · {detail.error.category}
                      </div>
                      <div className="text-[11px] font-mono text-secondary mt-0.5 break-all">
                        fp:{detail.error.fingerprint}
                        {detail.error.correlation_id ? ` · corr:${detail.error.correlation_id}` : ""}
                      </div>
                    </div>
                    <span
                      className={`px-1.5 py-0.5 rounded-xs border text-[10px] font-mono uppercase shrink-0 ${
                        SEV_BADGE[detail.error.severity] || SEV_BADGE.error
                      }`}
                    >
                      {detail.error.status}
                    </span>
                  </div>

                  <div className="text-xs text-primary break-words">{detail.error.message}</div>

                  {detail.error.stack_trace && (
                    <pre className="p-2 bg-input border border-subtle rounded-xs text-[10.5px] font-mono text-secondary overflow-auto max-h-36 whitespace-pre-wrap select-text">
                      {detail.error.stack_trace}
                    </pre>
                  )}

                  {detail.related.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <div className="text-[11px] font-semibold text-secondary">
                        Correlated Failure Chain ({detail.related.length})
                      </div>
                      {detail.related.map(rel => (
                        <button
                          key={rel.id}
                          type="button"
                          onClick={() => void loadDetail(rel.id)}
                          className="text-left px-2 py-1 rounded-xs bg-input border border-subtle text-[11px] text-primary hover:border-accent-secondary cursor-pointer"
                        >
                          <span className="font-mono text-accent-secondary">
                            #{rel.id} [{rel.origin}:{rel.module}]
                          </span>{" "}
                          {rel.message}
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-col gap-1.5">
                    <label className="text-[11px] font-semibold text-secondary">
                      Investigation Notes
                    </label>
                    <textarea
                      rows={2}
                      value={notesInput}
                      onChange={e => setNotesInput(e.target.value)}
                      placeholder="Add root cause or triage notes..."
                      className="w-full p-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent-secondary"
                    />
                  </div>

                  <div className="flex items-center gap-1.5 flex-wrap">
                    <button
                      type="button"
                      disabled={busyAction}
                      onClick={() => void handleTriggerRecovery("auto")}
                      className="btn-secondary h-7 px-2.5 text-xs"
                    >
                      <Wrench className="w-3 h-3" />
                      <span>Safe Recovery</span>
                    </button>
                    <button
                      type="button"
                      disabled={busyAction}
                      onClick={() => void handleStatusUpdate("investigating")}
                      className="btn-warning h-7 px-2.5 text-xs"
                    >
                      Investigating
                    </button>
                    <button
                      type="button"
                      disabled={busyAction}
                      onClick={() => void handleStatusUpdate("resolved")}
                      className="btn-success h-7 px-2.5 text-xs"
                    >
                      Mark Resolved
                    </button>
                  </div>

                  {detail.recoveries.length > 0 && (
                    <div className="border-t border-subtle pt-2 flex flex-col gap-1">
                      <div className="text-[11px] font-semibold text-secondary">
                        Recovery Attempts ({detail.recoveries.length})
                      </div>
                      {detail.recoveries.slice(0, 5).map(r => (
                        <div
                          key={r.id}
                          className="text-[11px] font-mono text-secondary flex items-center justify-between gap-2"
                        >
                          <span className="truncate">
                            #{r.attempt_no} {r.strategy} ({r.outcome}) — {r.detail}
                          </span>
                          <span className="shrink-0">{r.duration_ms}ms</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="bg-card border border-subtle rounded-sm overflow-auto max-h-[460px]">
          {recoveries.length === 0 ? (
            <div className="p-8 text-center text-xs text-secondary">
              No recovery attempts have been recorded yet.
            </div>
          ) : (
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="sticky top-0 bg-elevated border-b border-hairline text-[11px] uppercase text-secondary">
                  <th className="py-2 px-3">Timestamp</th>
                  <th className="py-2 px-3">Error</th>
                  <th className="py-2 px-3">Strategy</th>
                  <th className="py-2 px-3">Trigger</th>
                  <th className="py-2 px-3">Outcome</th>
                  <th className="py-2 px-3">Duration</th>
                  <th className="py-2 px-3">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-subtle">
                {recoveries.map(r => (
                  <tr key={r.id} className="hover:bg-elevated/40">
                    <td className="py-2 px-3 font-mono text-[11px] text-secondary whitespace-nowrap">
                      {formatDate(r.started_at_utc, fmtOpts)}
                    </td>
                    <td className="py-2 px-3 font-mono text-[11px] text-primary">
                      #{r.error_id} {r.module || ""}
                    </td>
                    <td className="py-2 px-3 font-mono text-[11px] text-primary">{r.strategy}</td>
                    <td className="py-2 px-3 text-secondary">{r.trigger_source}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`font-mono text-[11px] ${
                          r.outcome === "succeeded"
                            ? "text-success"
                            : r.outcome === "skipped"
                              ? "text-amber"
                              : "text-danger"
                        }`}
                      >
                        {r.outcome}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono text-[11px] text-secondary">
                      {r.duration_ms}ms
                    </td>
                    <td className="py-2 px-3 text-secondary max-w-[260px] truncate" title={r.detail}>
                      {r.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
