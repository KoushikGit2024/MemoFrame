import { useCallback, useEffect, useState } from "react";
import {
  FolderSearch,
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Loader2,
  Moon,
  Palette,
  ShieldCheck,
  Sun,
  Trash2,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { openFile, revealFile, rpc } from "../lib/api";
import { THEME_FAMILIES, THEME_MAP } from "../lib/themes";
import type { DoctorReport, WorkspaceStats } from "../types/memoframe";
import ModalShell from "../components/ModalShell";
import { SuspiciousDatesModal } from "../modals/DateModals";
import { FailedPhotosModal, ResetWorkspaceModal } from "../modals/UtilityModals";

const STAT_DEFS: ReadonlyArray<[keyof WorkspaceStats, string, string]> = [
  ["total_images", "Total Photos", "border-l-accent-secondary"],
  ["total_faces", "Faces Detected", "border-l-violet"],
  ["duplicate_clusters", "Duplicate Clusters", "border-l-amber"],
  ["groups", "Event Groups", "border-l-accent"],
  ["videos", "Videos Indexed", "border-l-success"],
];

export default function SettingsView() {
  const {
    connected,
    theme,
    applyTheme,
    toggleLightDark,
    config,
    dataVersion,
    invalidate,
    notify,
    setSelectedPersonId,
    startScanFolder,
    scan,
  } = useApp();
  const [stats, setStats] = useState<WorkspaceStats>({});
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [busyLabel, setBusyLabel] = useState("");
  const [maintNote, setMaintNote] = useState("");
  const [showDates, setShowDates] = useState(false);
  const [showFailed, setShowFailed] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [tagNote, setTagNote] = useState("");
  const [pendingMaint, setPendingMaint] = useState<{
    title: string;
    description: string;
    confirmLabel: string;
    onConfirm: () => void;
  } | null>(null);

  const refreshStats = useCallback(() => {
    if (!connected) return;
    rpc<WorkspaceStats>("system.stats")
      .then(res => setStats(res || {}))
      .catch(() => {});
  }, [connected]);

  useEffect(() => {
    refreshStats();
  }, [refreshStats, dataVersion]);

  const runTask = async (label: string, fn: () => Promise<void>) => {
    if (busyLabel) return;
    setBusyLabel(label);
    setMaintNote(`${label}...`);
    try {
      await fn();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMaintNote(`Failed: ${msg}`);
      notify(msg, "error");
    } finally {
      setBusyLabel("");
    }
  };

  const handleDoctor = () =>
    runTask("Running diagnostic health check", async () => {
      const report = await rpc<DoctorReport>("system.doctor");
      setDoctor(report || { checks: [] });
      setMaintNote("");
    });

  const handleClearCache = () =>
    runTask("Cleaning thumbnail cache", async () => {
      const res = await rpc<{ freed_mb?: number }>("system.clear_cache");
      setMaintNote(`Reclaimed about ${res.freed_mb || 0} MB of thumbnail cache.`);
      notify(`Reclaimed ~${res.freed_mb || 0} MB of cache.`, "success");
      refreshStats();
    });

  const handleVerifyFiles = () =>
    runTask("Checking indexed files", async () => {
      const res = await rpc<{ ok?: number; missing?: number; offline?: number }>(
        "system.check_files"
      );
      setMaintNote(
        `Files checked: ${res.ok || 0} present, ${res.missing || 0} missing, ${res.offline || 0} on unplugged drives.`
      );
      refreshStats();
    });

  const handlePruneMissing = () =>
    runTask("Checking missing records", async () => {
      const counts = await rpc<{ missing?: number }>("system.check_files");
      const n = Number(counts.missing || 0);
      if (!n) {
        setMaintNote("No missing photos found. Nothing to prune.");
        return;
      }
      if (
        !window.confirm(
          `${n} record(s) point to files that no longer exist. Remove them from the index? Original photos are never touched.`
        )
      ) {
        setMaintNote("");
        return;
      }
      const res = await rpc<{ removed?: number }>("system.forget_missing");
      setMaintNote(`Pruned ${res.removed || 0} missing record(s).`);
      notify(`Removed ${res.removed || 0} missing record(s).`, "success");
      invalidate();
      refreshStats();
    });

  const handleDetectMoves = () =>
    runTask("Detecting moved files", async () => {
      const res = await rpc<{ count?: number }>("system.moves");
      setMaintNote(
        res.count
          ? `${res.count} photo(s) moved or renamed. Favourite/keep marks followed them.`
          : "No moved files found. Scan the new location first, then run again."
      );
    });

  const handleRebuild = () =>
    runTask("Rebuilding groups and index", async () => {
      const res = await rpc<{ groups?: number; duplicate_clusters?: number; persons?: number }>(
        "system.rebuild"
      );
      setMaintNote(
        `Rebuilt: ${res.groups || 0} groups, ${res.duplicate_clusters || 0} duplicate clusters, ${res.persons || 0} people.`
      );
      invalidate();
      refreshStats();
    });

  const handleRepair = () =>
    runTask("Repairing database", async () => {
      const res = await rpc<{
        face_counts_fixed?: number;
        requeued?: number;
        orphan_faces_removed?: number;
      }>("system.repair");
      setMaintNote(
        `Repair finished: ${res.face_counts_fixed || 0} face counts fixed, ${res.requeued || 0} requeued, ${res.orphan_faces_removed || 0} orphan faces removed.`
      );
      refreshStats();
    });

  const handleTagExisting = () =>
    runTask("Tagging existing photos", async () => {
      setTagNote("Tagging existing photos...");
      const res = await rpc<{ tagged?: number }>("system.tag_existing");
      const msg = `Tagged ${res.tagged || 0} photo(s).`;
      setTagNote(msg);
      notify(msg, "success");
      invalidate();
    });

  const handleResetConfirm = (opts: { clear_sources: boolean; clear_saved_searches: boolean }) => {
    setShowReset(false);
    runTask("Resetting workspace", async () => {
      const res = await rpc<{ images_removed?: number }>("system.reset_workspace", opts);
      setSelectedPersonId(null);
      setMaintNote(`Reset complete: removed ${res.images_removed || 0} photo record(s).`);
      notify(`Workspace reset (${res.images_removed || 0} records removed).`, "success");
      invalidate();
      refreshStats();
    });
  };

  const doctorIssues = (doctor?.checks || []).filter(c => c.status !== "ok");

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="shrink-0 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">Workspace &amp; System Settings</h1>
          <p className="text-xs text-secondary mt-0.5">
            Configure studio palette, inspect workspace health, and run library maintenance.
          </p>
        </div>
        <button
          type="button"
          disabled={!connected || scan.running}
          onClick={startScanFolder}
          className="btn-secondary h-8 px-3 text-xs inline-flex items-center gap-1.5 rounded-md cursor-pointer disabled:opacity-50"
        >
          <FolderSearch className="w-3.5 h-3.5" strokeWidth={1.7} />
          <span>Scan Folder...</span>
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        <div className="w-full max-w-4xl mx-auto flex flex-col gap-4 pb-6">
          {/* Appearance & Color Palette - Compact & Minimal */}
          <section className="bg-card border border-subtle rounded-sm p-3.5 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <Palette className="w-4 h-4 text-accent shrink-0" strokeWidth={1.8} />
                <span className="text-xs font-semibold text-primary">Studio Color Palette</span>
                <span className="text-xs text-secondary">•</span>
                <span className="text-xs text-secondary">
                  Current: <strong className="text-primary font-medium">{theme}</strong>
                </span>
              </div>

              {/* Quick Global Light/Dark Toggle */}
              <button
                type="button"
                onClick={toggleLightDark}
                className="h-7 px-2.5 rounded-xs border border-subtle bg-elevated text-xs font-medium text-primary flex items-center gap-1.5 hover:border-hairline transition-colors"
              >
                {THEME_MAP[theme]?.isDark ? (
                  <>
                    <Sun className="w-3.5 h-3.5 text-amber" strokeWidth={1.8} />
                    <span>Switch to Light</span>
                  </>
                ) : (
                  <>
                    <Moon className="w-3.5 h-3.5 text-violet" strokeWidth={1.8} />
                    <span>Switch to Dark</span>
                  </>
                )}
              </button>
            </div>

            {/* Compact Family Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
              {THEME_FAMILIES.map(family => {
                const isDarkActive = theme === family.darkTheme;
                const isLightActive = theme === family.lightTheme;
                const isFamilyActive = isDarkActive || isLightActive;
                const currentIsDark = THEME_MAP[theme]?.isDark ?? true;

                return (
                  <button
                    key={family.id}
                    type="button"
                    onClick={() => applyTheme(currentIsDark ? family.darkTheme : family.lightTheme)}
                    className={`h-9 px-2.5 rounded-xs border flex items-center justify-between text-xs font-medium transition-all duration-150 active:scale-[0.98] ${
                      isFamilyActive
                        ? "border-accent bg-accent-light text-primary ring-1 ring-accent/30"
                        : "border-subtle bg-elevated/50 text-secondary hover:text-primary hover:border-hairline hover:bg-elevated"
                    }`}
                  >
                    <span className="truncate">{family.label}</span>
                    <span
                      className="w-3.5 h-3.5 rounded-full shrink-0 ml-1.5 border border-hairline"
                      style={{
                        background: `conic-gradient(${family.previewAccent} 0deg 180deg, ${family.previewSecondary} 180deg 360deg)`,
                      }}
                    />
                  </button>
                );
              })}
            </div>
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-semibold text-primary">Workspace Statistics</h2>
              <p className="text-xs text-secondary">
                Live overview of indexed media, detected faces, duplicates, and events.
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
              {STAT_DEFS.map(([k, label, accentBorder]) => (
                <div
                  key={k}
                  className={`bg-elevated border border-subtle border-l-2 ${accentBorder} rounded-xs px-3 py-2.5 transition-colors duration-150 hover:border-hairline`}
                >
                  <div className="font-mono text-lg font-semibold text-primary tabular-nums">
                    {stats[k] ?? 0}
                  </div>
                  <div className="text-[11px] text-secondary mt-0.5">{label}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-secondary font-mono">
              {stats.processed ?? 0} of {stats.total_images ?? 0} processed ·{" "}
              {stats.images_with_faces ?? 0} with faces · {stats.duplicate_images ?? 0} redundant
              copies
            </div>
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-semibold text-primary">Engine Health &amp; Cache</h2>
              <p className="text-xs text-secondary">
                Verify database integrity, inspect logs, export diagnostics, or reclaim thumbnail
                cache.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
              <button
                type="button"
                disabled={!connected || Boolean(busyLabel)}
                onClick={handleDoctor}
                className="btn-primary h-9 px-3 text-xs rounded-xs inline-flex items-center justify-center gap-1.5 border border-accent bg-accent text-accent-text font-medium transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
              >
                {busyLabel === "Running diagnostic health check" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-text" />
                ) : (
                  <ShieldCheck className="w-3.5 h-3.5" strokeWidth={1.6} />
                )}
                <span>
                  {busyLabel === "Running diagnostic health check"
                    ? "Checking..."
                    : "Run Doctor Check"}
                </span>
              </button>
              <button
                type="button"
                disabled={!connected || Boolean(busyLabel)}
                onClick={handleClearCache}
                className="btn-neutral h-9 px-3 text-xs rounded-xs inline-flex items-center justify-center gap-1.5 border border-hairline bg-elevated text-primary hover:border-amber/60 hover:bg-card transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
              >
                {busyLabel === "Cleaning thumbnail cache" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-amber" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5 text-amber" strokeWidth={1.6} />
                )}
                <span>
                  {busyLabel === "Cleaning thumbnail cache" ? "Cleaning..." : "Clean Stale Cache"}
                </span>
              </button>
              <button
                type="button"
                onClick={() => openFile(config.log_path)}
                className="btn-neutral h-9 px-3 text-xs rounded-xs inline-flex items-center justify-center gap-1.5 border border-hairline bg-elevated text-primary hover:border-accent-secondary/60 hover:bg-card transition-all duration-150 active:scale-[0.98]"
              >
                <FolderOpen className="w-3.5 h-3.5 text-accent-secondary" strokeWidth={1.6} />
                <span>Open Log File</span>
              </button>
              <button
                type="button"
                onClick={() => revealFile(config.log_path)}
                className="btn-neutral h-9 px-3 text-xs rounded-xs inline-flex items-center justify-center gap-1.5 border border-hairline bg-elevated text-primary hover:border-accent-secondary/60 hover:bg-card transition-all duration-150 active:scale-[0.98]"
              >
                <FolderOpen className="w-3.5 h-3.5 text-accent-secondary" strokeWidth={1.6} />
                <span>Reveal Log Folder</span>
              </button>
            </div>
            {doctor && (
              <div
                className={`p-2.5 rounded-xs border text-xs ${doctorIssues.length === 0 ? "bg-success-bg border-success/55 text-success" : "bg-danger-bg border-danger/55 text-danger"}`}
              >
                {doctorIssues.length === 0 ? (
                  <span className="inline-flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" strokeWidth={1.7} />
                    All checks passed. Workspace and models are healthy.
                  </span>
                ) : (
                  <ul className="list-disc pl-4 space-y-1">
                    {doctorIssues.map((c, idx) => (
                      <li key={idx}>
                        {c.name}: {c.detail}
                        {c.fix ? ` (fix: ${c.fix})` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-2.5">
            <div>
              <h2 className="text-sm font-semibold text-primary">
                Scene Tags &amp; Similar Photos
              </h2>
              <p className="text-xs text-secondary">
                Scene tagging and similarity embeddings run automatically during library scans.
              </p>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                disabled={!connected || Boolean(busyLabel)}
                onClick={handleTagExisting}
                className="btn-tertiary h-9 px-3.5 text-xs rounded-xs inline-flex items-center justify-center gap-1.5 border border-hairline bg-elevated text-primary hover:border-accent-secondary/60 hover:bg-card transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
              >
                {busyLabel === "Tagging existing photos" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                )}
                <span>
                  {busyLabel === "Tagging existing photos" ? "Tagging..." : "Tag Existing Photos"}
                </span>
              </button>
              {tagNote && (
                <span className="text-xs font-mono text-secondary">{tagNote}</span>
              )}
            </div>
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-semibold text-primary">
                Library &amp; Record Maintenance
              </h2>
              <p className="text-xs text-secondary">
                Verify source files on disk, purge stale missing records, and repair database
                anomalies.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {(
                [
                  [
                    "Verify Files",
                    "Checks all indexed file paths on disk and reports present, missing, or offline-drive files without modifying anything.",
                    "Run Verification",
                    handleVerifyFiles,
                  ],
                  [
                    "Prune Missing Records",
                    "Scans for indexed records whose source files no longer exist on disk and removes them from the database. Original files are never touched.",
                    "Check & Prune",
                    handlePruneMissing,
                  ],
                  [
                    "Detect Moved Files",
                    "Matches newly scanned files with missing records by content hash so your favourites and keep marks follow moved or renamed photos.",
                    "Detect Moves",
                    handleDetectMoves,
                  ],
                  ["Suspicious Dates...", "", "", () => setShowDates(true)],
                  [
                    "Rebuild Groups & Index",
                    "Recomputes event groups, duplicate clusters, and person clusters from the current database.",
                    "Rebuild Index",
                    handleRebuild,
                  ],
                  [
                    "Repair & Optimize DB",
                    "Fixes face counts, removes orphan face rows, requeues incomplete items, and runs SQLite optimization.",
                    "Repair & Optimize",
                    handleRepair,
                  ],
                  ["Failed Photos...", "", "", () => setShowFailed(true)],
                ] as const
              ).map(([label, desc, confirmLabel, handler]) => (
                <button
                  key={label}
                  type="button"
                  disabled={!connected || Boolean(busyLabel)}
                  onClick={() => {
                    if (!desc) {
                      handler();
                    } else {
                      setPendingMaint({
                        title: label,
                        description: desc,
                        confirmLabel,
                        onConfirm: () => {
                          setPendingMaint(null);
                          handler();
                        },
                      });
                    }
                  }}
                  className="btn-neutral h-9 px-3 text-xs rounded-xs inline-flex items-center justify-center border border-hairline bg-elevated text-primary hover:border-accent-secondary/60 hover:bg-card transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
                >
                  {label}
                </button>
              ))}
            </div>
            {(busyLabel || maintNote) && (
              <div
                className={`text-xs font-mono rounded-xs px-3 py-2 flex items-center gap-2 transition-all ${
                  busyLabel
                    ? "bg-accent-secondary-light border border-accent-secondary/50 text-accent-secondary"
                    : "bg-input border border-subtle text-secondary"
                }`}
              >
                {busyLabel ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />
                    <span>{busyLabel}...</span>
                  </>
                ) : (
                  <span>{maintNote}</span>
                )}
              </div>
            )}
          </section>

          <section className="bg-card border border-danger/45 rounded-sm p-4 flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-danger inline-flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" strokeWidth={1.7} />
                <span>Danger Zone: Reset Workspace</span>
              </h2>
              <p className="text-xs text-secondary mt-0.5">
                Clear all indexed photos, faces, duplicates, and events. Original files on disk are
                never touched.
              </p>
            </div>
            <button
              type="button"
              disabled={!connected || Boolean(busyLabel)}
              onClick={() => setShowReset(true)}
              className="btn-danger h-8 px-3 text-xs"
            >
              Reset Workspace Data...
            </button>
          </section>
        </div>
      </div>

      {showDates && (
        <SuspiciousDatesModal
          onClose={changed => {
            setShowDates(false);
            if (changed) handleRebuild();
          }}
        />
      )}
      {showFailed && <FailedPhotosModal onClose={() => setShowFailed(false)} />}
      {showReset && (
        <ResetWorkspaceModal onClose={() => setShowReset(false)} onConfirm={handleResetConfirm} />
      )}
      {pendingMaint && (
        <ModalShell
          title={pendingMaint.title}
          onClose={() => setPendingMaint(null)}
          className="w-[440px] max-w-[92vw]"
        >
          <div className="flex flex-col gap-4">
            <p className="text-xs text-secondary leading-relaxed">{pendingMaint.description}</p>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setPendingMaint(null)}
                className="btn-neutral h-8 px-3 text-xs rounded-xs border border-hairline bg-elevated text-primary hover:bg-card"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={pendingMaint.onConfirm}
                className="btn-primary h-8 px-3.5 text-xs rounded-xs border border-accent bg-accent text-accent-text font-medium"
              >
                {pendingMaint.confirmLabel}
              </button>
            </div>
          </div>
        </ModalShell>
      )}
    </div>
  );
}
