import { useCallback, useEffect, useState } from "react";
import {
  Bell,
  CheckCircle2,
  Cpu,
  Database,
  FolderOpen,
  FolderSearch,
  Loader2,
  Moon,
  Palette,
  RotateCcw,
  ShieldCheck,
  Sliders,
  Sun,
  Terminal,
  Trash2,
} from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { openFile, revealFile, rpc } from "../../shared/lib/api";
import { getErrorMonitorHealth } from "../../shared/lib/errorMonitor";
import { THEME_FAMILIES, THEME_MAP } from "../../shared/lib/themes";
import { formatDate } from "../../shared/lib/utils";
import type {
  ConfigAuditRow,
  DateFormatMode,
  DoctorReport,
  UiDensity,
  ViewKey,
} from "../../shared/types/memoframe";
import ModalShell from "../../shared/ui/ModalShell";
import { SuspiciousDatesModal } from "./DateModals";
import { FailedPhotosModal, ResetWorkspaceModal } from "./UtilityModals";

type SettingsCategory =
  | "general"
  | "appearance"
  | "notifications"
  | "storage"
  | "performance"
  | "developer";

const CATEGORIES: ReadonlyArray<{
  key: SettingsCategory;
  label: string;
  icon: typeof Sliders;
}> = [
  { key: "general", label: "General", icon: Sliders },
  { key: "appearance", label: "Appearance", icon: Palette },
  { key: "notifications", label: "Notifications", icon: Bell },
  { key: "storage", label: "Data & Storage", icon: Database },
  { key: "performance", label: "Performance & AI", icon: Cpu },
  { key: "developer", label: "Developer & Diagnostics", icon: Terminal },
];

export default function SettingsView() {
  const {
    connected,
    theme,
    applyTheme,
    toggleLightDark,
    prefs,
    updatePref,
    resetPrefs,
    workspace,
    config,
    setConfig,
    invalidate,
    notify,
    setSelectedPersonId,
    startScanFolder,
    scan,
    notificationHistory,
    clearNotificationHistory,
  } = useApp();

  const [category, setCategory] = useState<SettingsCategory>("general");
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [auditRows, setAuditRows] = useState<ConfigAuditRow[]>([]);
  const [busyLabel, setBusyLabel] = useState("");
  const [maintNote, setMaintNote] = useState("");
  const [tagNote, setTagNote] = useState("");
  const [showDates, setShowDates] = useState(false);
  const [showFailed, setShowFailed] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [pendingMaint, setPendingMaint] = useState<{
    title: string;
    description: string;
    confirmLabel: string;
    onConfirm: () => void;
  } | null>(null);

  const [pageSizeDraft, setPageSizeDraft] = useState(String(prefs.defaultPageSize));
  const pageSizeNum = Number(pageSizeDraft);
  const pageSizeInvalid = !Number.isInteger(pageSizeNum) || pageSizeNum < 10 || pageSizeNum > 200;
  const pageSizeUnsaved = !pageSizeInvalid && pageSizeNum !== prefs.defaultPageSize;

  useEffect(() => {
    setPageSizeDraft(String(prefs.defaultPageSize));
  }, [prefs.defaultPageSize]);

  const loadAuditLog = useCallback(() => {
    rpc<{ items: ConfigAuditRow[] }>("system.audit_log", { limit: 40 })
      .then(res => setAuditRows(res?.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (category === "developer") loadAuditLog();
  }, [category, loadAuditLog]);

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

  const handleSavePref = async <K extends keyof typeof prefs>(key: K, val: (typeof prefs)[K]) => {
    try {
      await updatePref(key, val);
      notify("Setting saved.", "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  };

  const handleToggleEngineConfig = async (nextTagging: boolean, nextEmbeddings: boolean) => {
    await runTask("Updating AI engine configuration", async () => {
      const res = await rpc<{ tagging_enabled: boolean; store_embeddings: boolean }>(
        "system.update_config",
        { tagging_enabled: nextTagging, store_embeddings: nextEmbeddings }
      );
      setConfig(c => ({
        ...c,
        tagging_enabled: res.tagging_enabled,
        store_embeddings: res.store_embeddings,
      }));
      setMaintNote("AI engine configuration updated.");
      notify("Engine configuration saved.", "success");
    });
  };

  const handleDoctor = () =>
    runTask("Running diagnostic health check", async () => {
      const report = await rpc<DoctorReport>("system.doctor");
      setDoctor(report || { checks: [] });
      setMaintNote("");
    });

  const handleExportDiagnostics = () =>
    runTask("Exporting diagnostic bundle", async () => {
      const res = await rpc<{ path?: string | null }>("system.export_diagnostics");
      if (res?.path) {
        setMaintNote(`Diagnostics exported to ${res.path}`);
        notify("Diagnostics report exported.", "success");
        await revealFile(res.path);
      } else {
        setMaintNote("Diagnostics export did not produce a file.");
      }
    });

  const handleClearCache = () =>
    runTask("Cleaning thumbnail cache", async () => {
      const res = await rpc<{ freed_mb?: number }>("system.clear_cache");
      setMaintNote(`Reclaimed about ${res.freed_mb || 0} MB of cache.`);
      notify(`Reclaimed ~${res.freed_mb || 0} MB of cache.`, "success");
    });

  const handleVerifyFiles = () =>
    runTask("Checking indexed files", async () => {
      const res = await rpc<{ ok?: number; missing?: number; offline?: number }>(
        "system.check_files"
      );
      setMaintNote(
        `Files checked: ${res.ok || 0} present, ${res.missing || 0} missing, ${res.offline || 0} on unplugged drives.`
      );
    });

  const handlePruneMissing = () =>
    runTask("Checking missing records", async () => {
      const counts = await rpc<{ missing?: number }>("system.check_files");
      const n = Number(counts.missing || 0);
      if (!n) {
        setMaintNote("No missing photos found. Nothing to prune.");
        return;
      }
      setMaintNote("");
      setPendingMaint({
        title: "Prune Missing Photos",
        description: `${n} record(s) point to files that no longer exist on disk. Remove them from the index? Original photos are never touched.`,
        confirmLabel: `Prune ${n} Record${n === 1 ? "" : "s"}`,
        onConfirm: () => {
          setPendingMaint(null);
          void runTask("Pruning missing records", async () => {
            const res = await rpc<{ removed?: number }>("system.forget_missing");
            setMaintNote(`Pruned ${res.removed || 0} missing record(s).`);
            notify(`Removed ${res.removed || 0} missing record(s).`, "success");
            invalidate();
          });
        },
      });
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
    });

  const handleTagExisting = () =>
    runTask("Starting scene tagging", async () => {
      setTagNote("Starting background scene tagging...");
      await rpc<{ started?: boolean }>("system.tag_existing");
      const msg = "Scene tagging started in the background. Progress will appear in the scan dialog.";
      setTagNote(msg);
      notify(msg, "info");
    });

  const handleResetConfirm = (opts: { clear_sources: boolean; clear_saved_searches: boolean }) => {
    setShowReset(false);
    void runTask("Resetting workspace", async () => {
      const res = await rpc<{ images_removed?: number }>("system.reset_workspace", opts);
      setSelectedPersonId(null);
      setMaintNote(`Reset complete: removed ${res.images_removed || 0} photo record(s).`);
      notify(`Workspace reset (${res.images_removed || 0} records removed).`, "success");
      invalidate();
    });
  };

  const monitorHealth = getErrorMonitorHealth();
  const fmtOpts = { timezone: prefs.timezone, dateFormat: prefs.dateFormat };

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="shrink-0 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">Application Settings</h1>
          <p className="text-xs text-secondary mt-0.5">
            Centralized preferences, appearance, notifications, storage maintenance, and diagnostics.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() =>
              setPendingMaint({
                title: "Reset Preferences to Defaults",
                description:
                  "Restore General, Appearance, and Notification preferences to factory defaults? Your indexed photo library is not affected.",
                confirmLabel: "Reset Preferences",
                onConfirm: () => {
                  setPendingMaint(null);
                  void resetPrefs().then(() => notify("Preferences reset to defaults.", "success"));
                },
              })
            }
            className="btn-neutral h-8 px-2.5 text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>
          <button
            type="button"
            disabled={!connected || scan.running}
            onClick={() => void startScanFolder()}
            className="btn-primary h-9 px-3.5 text-xs font-semibold"
          >
            <FolderSearch className="w-3.5 h-3.5" strokeWidth={1.7} />
            <span>Scan Folder...</span>
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col md:flex-row gap-3 md:gap-4 overflow-hidden">
        {/* Responsive Category Rail */}
        <nav className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible md:w-48 shrink-0 border-b md:border-b-0 md:border-r border-subtle pb-2 md:pb-0 md:pr-3">
          {CATEGORIES.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setCategory(key)}
              className={`h-8 px-2.5 rounded-xs border text-xs flex items-center gap-2 text-left cursor-pointer transition-colors ${
                category === key
                  ? "bg-elevated border-accent-secondary/60 text-primary font-semibold"
                  : "bg-transparent border-transparent text-secondary hover:text-primary hover:bg-elevated/50"
              }`}
            >
              <Icon className="w-3.5 h-3.5 shrink-0" strokeWidth={1.7} />
              <span className="truncate">{label}</span>
            </button>
          ))}
        </nav>

        {/* Active Category Body */}
        <div className="flex-1 min-w-0 overflow-y-auto pr-1 pb-6 flex flex-col gap-4">
          {maintNote && (
            <div className="px-3 py-2 bg-elevated border border-hairline rounded-xs text-xs text-primary flex items-center gap-2">
              {busyLabel && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary shrink-0" />}
              <span>{maintNote}</span>
            </div>
          )}

          {category === "general" && (
            <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-4 max-w-2xl">
              <div>
                <h2 className="text-sm font-semibold text-primary">General Preferences</h2>
                <p className="text-xs text-secondary mt-0.5">
                  Control default landing view, timestamp display, and gallery pagination.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-xs">
                  <span className="text-secondary font-medium">Default Landing Page</span>
                  <select
                    value={prefs.defaultView}
                    onChange={e => void handleSavePref("defaultView", e.target.value as ViewKey)}
                    className="h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary"
                  >
                    <option value="photos">Photos Gallery</option>
                    <option value="people">People</option>
                    <option value="timeline">Timeline</option>
                    <option value="analytics">Analytics Center</option>
                    <option value="duplicates">Duplicates</option>
                    <option value="bursts">Bursts</option>
                  </select>
                </label>

                <label className="flex flex-col gap-1 text-xs">
                  <span className="text-secondary font-medium">Display Timezone</span>
                  <select
                    value={prefs.timezone}
                    onChange={e => void handleSavePref("timezone", e.target.value)}
                    className="h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary"
                  >
                    <option value="local">System Local Timezone</option>
                    <option value="UTC">UTC</option>
                    <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                    <option value="America/New_York">America/New_York (ET)</option>
                    <option value="America/Los_Angeles">America/Los_Angeles (PT)</option>
                    <option value="Europe/London">Europe/London (GMT/BST)</option>
                  </select>
                </label>

                <label className="flex flex-col gap-1 text-xs">
                  <span className="text-secondary font-medium">Date &amp; Time Format</span>
                  <select
                    value={prefs.dateFormat}
                    onChange={e =>
                      void handleSavePref("dateFormat", e.target.value as DateFormatMode)
                    }
                    className="h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary"
                  >
                    <option value="iso">ISO (2026-11-28 14:30:00)</option>
                    <option value="locale">Locale Friendly (Nov 28, 2026)</option>
                    <option value="relative">Relative (2h ago)</option>
                  </select>
                </label>

                <div className="flex flex-col gap-1 text-xs">
                  <span className="text-secondary font-medium">Default Photos Per Page (10–200)</span>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      min={10}
                      max={200}
                      value={pageSizeDraft}
                      onChange={e => setPageSizeDraft(e.target.value)}
                      className={`flex-1 h-8 px-2.5 bg-input border rounded-xs text-xs font-mono text-primary ${
                        pageSizeInvalid ? "border-danger" : "border-hairline"
                      }`}
                    />
                    <button
                      type="button"
                      disabled={pageSizeInvalid || !pageSizeUnsaved}
                      onClick={() => void handleSavePref("defaultPageSize", pageSizeNum)}
                      className="btn-primary h-8 px-3 text-xs"
                    >
                      Save
                    </button>
                  </div>
                  {pageSizeInvalid ? (
                    <span className="text-[11px] text-danger">Enter an integer between 10 and 200.</span>
                  ) : pageSizeUnsaved ? (
                    <span className="text-[11px] text-amber">Unsaved change</span>
                  ) : (
                    <span className="text-[11px] text-success">Saved</span>
                  )}
                </div>
              </div>
            </section>
          )}

          {category === "appearance" && (
            <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-4 max-w-3xl">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h2 className="text-sm font-semibold text-primary">Theme &amp; Visual Density</h2>
                  <p className="text-xs text-secondary mt-0.5">
                    Current theme: <strong className="text-primary">{theme}</strong>
                  </p>
                </div>
                <button
                  type="button"
                  onClick={toggleLightDark}
                  className="btn-neutral h-7 px-2.5 text-xs"
                >
                  {THEME_MAP[theme]?.isDark ? (
                    <>
                      <Sun className="w-3.5 h-3.5 text-amber" />
                      <span>Switch to Light</span>
                    </>
                  ) : (
                    <>
                      <Moon className="w-3.5 h-3.5 text-violet" />
                      <span>Switch to Dark</span>
                    </>
                  )}
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {THEME_FAMILIES.map(f => {
                  const isDark = THEME_MAP[theme]?.isDark ?? true;
                  const active = theme === f.darkTheme || theme === f.lightTheme;
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => applyTheme(isDark ? f.darkTheme : f.lightTheme)}
                      className={`p-2.5 rounded-xs border text-left flex items-center justify-between gap-2 cursor-pointer transition-colors ${
                        active
                          ? "bg-elevated border-accent text-primary font-semibold"
                          : "bg-input border-subtle text-secondary hover:text-primary"
                      }`}
                    >
                      <span className="text-xs truncate">{f.label}</span>
                      <span
                        className="w-4 h-4 rounded-full shrink-0 border border-hairline"
                        style={{
                          background: `conic-gradient(${f.previewAccent} 0deg 90deg, ${f.previewSecondary} 90deg 180deg, ${f.previewTertiary} 180deg 270deg, ${f.previewQuaternary} 270deg 360deg)`,
                        }}
                      />
                    </button>
                  );
                })}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 border-t border-subtle pt-3">
                <label className="flex flex-col gap-1 text-xs">
                  <span className="text-secondary font-medium">UI Density</span>
                  <select
                    value={prefs.density}
                    onChange={e => void handleSavePref("density", e.target.value as UiDensity)}
                    className="h-8 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
                  >
                    <option value="comfortable">Comfortable</option>
                    <option value="compact">Compact</option>
                  </select>
                </label>

                <label className="flex items-center gap-2 text-xs text-primary cursor-pointer pt-5">
                  <input
                    type="checkbox"
                    checked={prefs.reducedMotion}
                    onChange={e => void handleSavePref("reducedMotion", e.target.checked)}
                    className="accent-accent"
                  />
                  <span>Reduce animations</span>
                </label>

                <label className="flex items-center gap-2 text-xs text-primary cursor-pointer pt-5">
                  <input
                    type="checkbox"
                    checked={prefs.compactSidebar}
                    onChange={e => void handleSavePref("compactSidebar", e.target.checked)}
                    className="accent-accent"
                  />
                  <span>Start with compact sidebar</span>
                </label>
              </div>
            </section>
          )}

          {category === "notifications" && (
            <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-4 max-w-2xl">
              <div>
                <h2 className="text-sm font-semibold text-primary">Notification Preferences</h2>
                <p className="text-xs text-secondary mt-0.5">
                  Choose which in-app toast alerts appear and review recent notification history.
                </p>
              </div>

              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-2 text-xs text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={prefs.notifySuccess}
                    onChange={e => void handleSavePref("notifySuccess", e.target.checked)}
                    className="accent-success"
                  />
                  <span>Show success confirmations</span>
                </label>
                <label className="flex items-center gap-2 text-xs text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={prefs.notifyErrors}
                    onChange={e => void handleSavePref("notifyErrors", e.target.checked)}
                    className="accent-danger"
                  />
                  <span>Show error &amp; disconnection alerts</span>
                </label>
                <label className="flex items-center gap-2 text-xs text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    checked={prefs.notifyBackground}
                    onChange={e => void handleSavePref("notifyBackground", e.target.checked)}
                    className="accent-accent-secondary"
                  />
                  <span>Show background job &amp; recovery notices</span>
                </label>
              </div>

              <div className="border-t border-subtle pt-3 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-primary">
                    Recent Notifications ({notificationHistory.length})
                  </span>
                  {notificationHistory.length > 0 && (
                    <button
                      type="button"
                      onClick={clearNotificationHistory}
                      className="btn-neutral h-6 px-2 text-[11px]"
                    >
                      Clear
                    </button>
                  )}
                </div>
                {notificationHistory.length === 0 ? (
                  <div className="text-xs text-secondary">No notifications recorded this session.</div>
                ) : (
                  <div className="max-h-48 overflow-y-auto divide-y divide-subtle border border-subtle rounded-xs">
                    {notificationHistory.map(n => (
                      <div key={n.id} className="px-2.5 py-1.5 flex items-center justify-between gap-2 text-xs">
                        <span className="text-primary truncate">{n.message}</span>
                        <span className="font-mono text-[10.5px] text-secondary shrink-0">
                          {formatDate(n.timestamp, fmtOpts)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {category === "storage" && (
            <div className="flex flex-col gap-3 max-w-3xl">
              <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div>
                    <h2 className="text-sm font-semibold text-primary">Library Maintenance &amp; Storage</h2>
                    <p className="text-xs text-secondary mt-0.5 font-mono truncate">
                      Workspace: {workspace || "—"}
                    </p>
                  </div>
                  {workspace && (
                    <button
                      type="button"
                      onClick={() => void revealFile(workspace)}
                      className="btn-neutral h-7 px-2.5 text-xs"
                    >
                      <FolderOpen className="w-3.5 h-3.5" />
                      <span>Open Workspace Folder</span>
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleClearCache} className="btn-neutral h-8 px-3 text-xs">Clear Thumbnail Cache</button>
                  <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleVerifyFiles} className="btn-neutral h-8 px-3 text-xs">Verify Indexed Files</button>
                  <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleDetectMoves} className="btn-neutral h-8 px-3 text-xs">Detect Moved Files</button>
                  <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handlePruneMissing} className="btn-warning h-8 px-3 text-xs">Prune Missing Records</button>
                  <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleRebuild} className="btn-neutral h-8 px-3 text-xs">Rebuild Groups &amp; Index</button>
                  <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleRepair} className="btn-neutral h-8 px-3 text-xs">Repair Database</button>
                  <button type="button" disabled={!connected} onClick={() => setShowDates(true)} className="btn-neutral h-8 px-3 text-xs">Inspect Suspicious Dates</button>
                  <button type="button" disabled={!connected} onClick={() => setShowFailed(true)} className="btn-neutral h-8 px-3 text-xs">View Failed Files</button>
                </div>
              </section>

              <section className="bg-card border border-danger/45 rounded-sm p-4 flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="text-xs font-semibold text-danger">Danger Zone — Reset Workspace</h3>
                  <p className="text-xs text-secondary mt-0.5">
                    Clears indexed photos, faces, people, groups, and caches. Original photos on disk are never touched.
                  </p>
                </div>
                <button
                  type="button"
                  disabled={!connected || Boolean(busyLabel)}
                  onClick={() => setShowReset(true)}
                  className="btn-danger h-8 px-3 text-xs"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Reset Workspace Data...</span>
                </button>
              </section>
            </div>
          )}

          {category === "performance" && (
            <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-4 max-w-2xl">
              <div>
                <h2 className="text-sm font-semibold text-primary">On-Device AI &amp; Indexing</h2>
                <p className="text-xs text-secondary mt-0.5">
                  Configure offline scene classification and visual similarity embeddings.
                </p>
              </div>

              <div className="flex flex-col gap-2.5">
                <label className="flex items-center justify-between gap-3 p-2.5 bg-input border border-subtle rounded-xs cursor-pointer">
                  <div>
                    <div className="text-xs font-medium text-primary">Scene Tagging (MobileNetV2)</div>
                    <div className="text-[11px] text-secondary">Automatically classify scenes during scans.</div>
                  </div>
                  <input
                    type="checkbox"
                    disabled={!connected || Boolean(busyLabel)}
                    checked={config.tagging_enabled}
                    onChange={e =>
                      void handleToggleEngineConfig(e.target.checked, config.store_embeddings)
                    }
                    className="accent-accent"
                  />
                </label>

                <label className="flex items-center justify-between gap-3 p-2.5 bg-input border border-subtle rounded-xs cursor-pointer">
                  <div>
                    <div className="text-xs font-medium text-primary">Store Visual Embeddings</div>
                    <div className="text-[11px] text-secondary">Enables "Find Similar" visual search in the Lightbox.</div>
                  </div>
                  <input
                    type="checkbox"
                    disabled={!connected || Boolean(busyLabel)}
                    checked={config.store_embeddings}
                    onChange={e =>
                      void handleToggleEngineConfig(config.tagging_enabled, e.target.checked)
                    }
                    className="accent-accent"
                  />
                </label>
              </div>

              <div className="flex items-center gap-2 flex-wrap pt-1">
                <button
                  type="button"
                  disabled={!connected || Boolean(busyLabel) || scan.running}
                  onClick={handleTagExisting}
                  className="btn-tertiary h-8 px-3 text-xs"
                >
                  Run Scene Tagging on Existing Photos
                </button>
                {tagNote && <span className="text-xs text-secondary">{tagNote}</span>}
              </div>
            </section>
          )}

          {category === "developer" && (
            <div className="flex flex-col gap-3 max-w-3xl">
              <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div>
                    <h2 className="text-sm font-semibold text-primary">System Health &amp; Diagnostics</h2>
                    <p className="text-xs text-secondary mt-0.5 font-mono">
                      MemoFrame v1.0.0 · Platform: {window.memoframe?.platform || "desktop"} · Error Queue: {monitorHealth.queuedCount}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleDoctor} className="btn-secondary h-7 px-2.5 text-xs">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      <span>Run Doctor</span>
                    </button>
                    <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleExportDiagnostics} className="btn-neutral h-7 px-2.5 text-xs">
                      Export Diagnostics
                    </button>
                    {config.log_path && (
                      <button type="button" onClick={() => void openFile(config.log_path)} className="btn-neutral h-7 px-2.5 text-xs">
                        Open Log File
                      </button>
                    )}
                  </div>
                </div>

                {doctor && (
                  <div className="flex flex-col gap-1.5 border-t border-subtle pt-3">
                    {doctor.checks.map(c => (
                      <div key={c.name} className="flex items-start justify-between gap-2 text-xs px-2.5 py-1.5 bg-input border border-subtle rounded-xs">
                        <div className="min-w-0">
                          <span className="font-semibold text-primary">{c.name}:</span>{" "}
                          <span className="text-secondary">{c.detail}</span>
                        </div>
                        <span
                          className={`font-mono text-[11px] uppercase shrink-0 ${
                            c.status === "ok" ? "text-success" : "text-danger"
                          }`}
                        >
                          {c.status}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-primary">
                    Configuration Change Audit Log ({auditRows.length})
                  </h3>
                  <button type="button" onClick={loadAuditLog} className="btn-neutral h-6 px-2 text-[11px]">
                    Refresh
                  </button>
                </div>
                {auditRows.length === 0 ? (
                  <div className="text-xs text-secondary flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                    <span>No configuration changes logged yet.</span>
                  </div>
                ) : (
                  <div className="max-h-52 overflow-y-auto divide-y divide-subtle border border-subtle rounded-xs text-xs">
                    {auditRows.map(r => (
                      <div key={r.id} className="px-2.5 py-1.5 flex items-center justify-between gap-2">
                        <span className="font-mono text-primary truncate">
                          {r.key}: <span className="text-secondary">{r.old_value}</span> →{" "}
                          <span className="text-accent-secondary">{r.new_value}</span>
                        </span>
                        <span className="font-mono text-[10.5px] text-secondary shrink-0">
                          {formatDate(r.changed_at_utc, fmtOpts)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </div>

      {showDates && (
        <SuspiciousDatesModal
          onClose={changed => {
            setShowDates(false);
            if (changed) void handleRebuild();
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
              <button type="button" onClick={() => setPendingMaint(null)} className="btn-neutral h-8 px-3 text-xs">
                Cancel
              </button>
              <button type="button" onClick={pendingMaint.onConfirm} className="btn-primary h-8 px-3.5 text-xs">
                {pendingMaint.confirmLabel}
              </button>
            </div>
          </div>
        </ModalShell>
      )}
    </div>
  );
}
