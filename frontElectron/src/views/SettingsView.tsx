import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileText, FolderOpen, ShieldCheck, Trash2 } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { revealFile, rpc } from '../lib/api';
import { THEMES } from '../lib/themes';
import type { DoctorReport, WorkspaceStats } from '../types/memoframe';
import { SuspiciousDatesModal } from '../modals/DateModals';
import { FailedPhotosModal, ResetWorkspaceModal } from '../modals/UtilityModals';

const STAT_DEFS: ReadonlyArray<[keyof WorkspaceStats, string]> = [
  ['total_images', 'Total Photos'],
  ['total_faces', 'Faces Detected'],
  ['duplicate_clusters', 'Duplicate Clusters'],
  ['groups', 'Event Groups'],
  ['videos', 'Videos Indexed'],
];

export default function SettingsView() {
  const { connected, theme, applyTheme, toggleLightDark, config, setConfig, dataVersion, invalidate, notify, setSelectedPersonId } = useApp();
  const [stats, setStats] = useState<WorkspaceStats>({});
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [busyLabel, setBusyLabel] = useState('');
  const [maintNote, setMaintNote] = useState('');
  const [showDates, setShowDates] = useState(false);
  const [showFailed, setShowFailed] = useState(false);
  const [showReset, setShowReset] = useState(false);

  const refreshStats = useCallback(() => {
    if (!connected) return;
    rpc<WorkspaceStats>('system.stats').then((res) => setStats(res || {})).catch(() => {});
  }, [connected]);

  useEffect(() => { refreshStats(); }, [refreshStats, dataVersion]);

  const runTask = async (label: string, fn: () => Promise<void>) => {
    if (busyLabel) return;
    setBusyLabel(label);
    setMaintNote(`${label}...`);
    try {
      await fn();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMaintNote(`Failed: ${msg}`);
      notify(msg, 'error');
    } finally {
      setBusyLabel('');
    }
  };

  const handleDoctor = () => runTask('Running diagnostic health check', async () => {
    const report = await rpc<DoctorReport>('system.doctor');
    setDoctor(report || { checks: [] });
    setMaintNote('');
  });

  const handleClearCache = () => runTask('Cleaning thumbnail cache', async () => {
    const res = await rpc<{ freed_mb?: number }>('system.clear_cache');
    setMaintNote(`Reclaimed about ${res.freed_mb || 0} MB of thumbnail cache.`);
    notify(`Reclaimed ~${res.freed_mb || 0} MB of cache.`, 'success');
    refreshStats();
  });

  const handleExportDiag = () => runTask('Exporting diagnostics', async () => {
    const res = await rpc<{ path?: string | null }>('system.export_diagnostics');
    if (res?.path) {
      setMaintNote(`Diagnostics saved to ${res.path}`);
      notify('Diagnostics exported.', 'success');
    }
  });

  const handleFlagToggle = async (field: 'tagging_enabled' | 'store_embeddings', checked: boolean) => {
    const prev = { ...config };
    const next = { ...config, [field]: checked };
    setConfig(next);
    try {
      await rpc('system.update_config', {
        tagging_enabled: next.tagging_enabled,
        store_embeddings: next.store_embeddings,
      });
      setMaintNote('Saved. Restart MemoFrame for model changes to take effect (workspace/models/tags/).');
    } catch (err) {
      setConfig(prev);
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const handleVerifyFiles = () => runTask('Checking indexed files', async () => {
    const res = await rpc<{ ok?: number; missing?: number; offline?: number }>('system.check_files');
    setMaintNote(`Files checked: ${res.ok || 0} present, ${res.missing || 0} missing, ${res.offline || 0} on unplugged drives.`);
    refreshStats();
  });

  const handlePruneMissing = () => runTask('Checking missing records', async () => {
    const counts = await rpc<{ missing?: number }>('system.check_files');
    const n = Number(counts.missing || 0);
    if (!n) { setMaintNote('No missing photos found. Nothing to prune.'); return; }
    if (!window.confirm(`${n} record(s) point to files that no longer exist. Remove them from the index? Original photos are never touched.`)) {
      setMaintNote('');
      return;
    }
    const res = await rpc<{ removed?: number }>('system.forget_missing');
    setMaintNote(`Pruned ${res.removed || 0} missing record(s).`);
    notify(`Removed ${res.removed || 0} missing record(s).`, 'success');
    invalidate();
    refreshStats();
  });

  const handleDetectMoves = () => runTask('Detecting moved files', async () => {
    const res = await rpc<{ count?: number }>('system.moves');
    setMaintNote(
      res.count
        ? `${res.count} photo(s) moved or renamed. Favourite/keep marks followed them.`
        : 'No moved files found. Scan the new location first, then run again.',
    );
  });

  const handleRebuild = () => runTask('Rebuilding groups and index', async () => {
    const res = await rpc<{ groups?: number; duplicate_clusters?: number; persons?: number }>('system.rebuild');
    setMaintNote(`Rebuilt: ${res.groups || 0} groups, ${res.duplicate_clusters || 0} duplicate clusters, ${res.persons || 0} people.`);
    invalidate();
    refreshStats();
  });

  const handleRepair = () => runTask('Repairing database', async () => {
    const res = await rpc<{ face_counts_fixed?: number; requeued?: number; orphan_faces_removed?: number }>('system.repair');
    setMaintNote(
      `Repair finished: ${res.face_counts_fixed || 0} face counts fixed, ${res.requeued || 0} requeued, ${res.orphan_faces_removed || 0} orphan faces removed.`,
    );
    refreshStats();
  });

  const handleTagExisting = () => runTask('Tagging existing photos', async () => {
    const res = await rpc<{ tagged?: number }>('system.tag_existing');
    setMaintNote(`Tagged ${res.tagged || 0} photo(s).`);
    invalidate();
  });

  const handleResetConfirm = (opts: { clear_sources: boolean; clear_saved_searches: boolean }) => {
    setShowReset(false);
    runTask('Resetting workspace', async () => {
      const res = await rpc<{ images_removed?: number }>('system.reset_workspace', opts);
      setSelectedPersonId(null);
      setMaintNote(`Reset complete: removed ${res.images_removed || 0} photo record(s).`);
      notify(`Workspace reset (${res.images_removed || 0} records removed).`, 'success');
      invalidate();
      refreshStats();
    });
  };

  const doctorIssues = (doctor?.checks || []).filter((c) => c.status !== 'ok');

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="shrink-0">
        <h1 className="text-[17px] font-semibold text-primary">Workspace &amp; System Settings</h1>
        <p className="text-xs text-secondary mt-0.5">Configure studio palette, inspect workspace health, and run library maintenance.</p>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        <div className="max-w-[860px] flex flex-col gap-3.5 pb-6">
          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div>
                <h2 className="text-sm font-semibold text-primary">Appearance &amp; Color Theme</h2>
                <p className="text-xs text-secondary">Switch instantly between dark studio palettes and Light Canvas.</p>
              </div>
              <button type="button" onClick={toggleLightDark} className="h-8 px-3 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent">
                Toggle Light / Dark
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {THEMES.map((t) => {
                const active = t.name === theme;
                return (
                  <button key={t.name} type="button" onClick={() => applyTheme(t.name)} className={`p-2.5 rounded-xs border text-left flex flex-col gap-2 transition-colors ${active ? 'border-accent bg-accent-light' : 'border-subtle bg-elevated hover:border-hairline'}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1">
                        <span className="w-3.5 h-3.5 rounded-[2px] border border-hairline" style={{ backgroundColor: t.bg }} />
                        <span className="w-3.5 h-3.5 rounded-[2px] border border-hairline" style={{ backgroundColor: t.card }} />
                        <span className="w-3.5 h-3.5 rounded-[2px] border border-hairline" style={{ backgroundColor: t.accent }} />
                      </div>
                      <span className="text-[10px] text-secondary">{t.isDark ? 'Dark' : 'Light'}</span>
                    </div>
                    <span className="text-xs font-medium text-primary truncate">{t.name}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-semibold text-primary">Workspace Statistics</h2>
              <p className="text-xs text-secondary">Live overview of indexed media, detected faces, duplicates, and events.</p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {STAT_DEFS.map(([k, label]) => (
                <div key={k} className="bg-elevated border border-subtle rounded-xs px-3 py-2.5">
                  <div className="font-mono text-lg font-semibold text-primary tabular-nums">{stats[k] ?? 0}</div>
                  <div className="text-[11px] text-secondary mt-0.5">{label}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-secondary font-mono">
              {stats.processed ?? 0} of {stats.total_images ?? 0} processed · {stats.images_with_faces ?? 0} with faces · {stats.duplicate_images ?? 0} redundant copies
            </div>
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-semibold text-primary">Engine Health &amp; Cache</h2>
              <p className="text-xs text-secondary">Verify database integrity, inspect logs, export diagnostics, or reclaim thumbnail cache.</p>
            </div>
            <div className="flex items-center flex-wrap gap-2">
              <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleDoctor} className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover disabled:opacity-45">
                <ShieldCheck className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>Run Doctor Check</span>
              </button>
              <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleClearCache} className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent disabled:opacity-45">
                <Trash2 className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>Clean Stale Cache</span>
              </button>
              <button type="button" onClick={() => revealFile(config.log_path)} className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent">
                <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>Show Log File</span>
              </button>
              <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleExportDiag} className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent disabled:opacity-45">
                <FileText className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>Export Diagnostics</span>
              </button>
            </div>
            {doctor && (
              <div className={`p-2.5 rounded-xs border text-xs ${doctorIssues.length === 0 ? 'bg-success-bg border-success text-success' : 'bg-danger-bg border-danger text-danger'}`}>
                {doctorIssues.length === 0 ? (
                  <span className="inline-flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" strokeWidth={1.7} />
                    All checks passed. Workspace and models are healthy.
                  </span>
                ) : (
                  <ul className="list-disc pl-4 space-y-1">
                    {doctorIssues.map((c, idx) => (
                      <li key={idx}>{c.name}: {c.detail}{c.fix ? ` (fix: ${c.fix})` : ''}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-2.5">
            <div>
              <h2 className="text-sm font-semibold text-primary">Scene Tags &amp; Similar Photos</h2>
              <p className="text-xs text-secondary">Requires model files placed inside workspace/models/tags/.</p>
            </div>
            <label className="inline-flex items-center gap-2 text-xs text-primary cursor-pointer">
              <input type="checkbox" checked={Boolean(config.tagging_enabled)} onChange={(e) => handleFlagToggle('tagging_enabled', e.target.checked)} className="accent-accent" />
              <span>Enable scene tagging</span>
            </label>
            <label className="inline-flex items-center gap-2 text-xs text-primary cursor-pointer">
              <input type="checkbox" checked={Boolean(config.store_embeddings)} onChange={(e) => handleFlagToggle('store_embeddings', e.target.checked)} className="accent-accent" />
              <span>Store embeddings (required for Find Similar)</span>
            </label>
            <div>
              <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={handleTagExisting} className="h-8 px-3 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent disabled:opacity-45">
                Tag Existing Photos
              </button>
            </div>
          </section>

          <section className="bg-card border border-subtle rounded-sm p-4 flex flex-col gap-3">
            <div>
              <h2 className="text-sm font-semibold text-primary">Library &amp; Record Maintenance</h2>
              <p className="text-xs text-secondary">Verify source files on disk, purge stale missing records, and repair database anomalies.</p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {([
                ['Verify Files', handleVerifyFiles],
                ['Prune Missing Records', handlePruneMissing],
                ['Detect Moved Files', handleDetectMoves],
                ['Suspicious Dates...', () => setShowDates(true)],
                ['Rebuild Groups & Index', handleRebuild],
                ['Repair & Optimize DB', handleRepair],
                ['Failed Photos...', () => setShowFailed(true)],
              ] as const).map(([label, handler]) => (
                <button key={label} type="button" disabled={!connected || Boolean(busyLabel)} onClick={handler} className="h-8 px-2.5 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent disabled:opacity-45 truncate">
                  {label}
                </button>
              ))}
            </div>
            {(busyLabel || maintNote) && (
              <div className="text-xs text-secondary font-mono bg-input border border-subtle rounded-xs px-3 py-2">
                {busyLabel ? `${busyLabel}...` : maintNote}
              </div>
            )}
          </section>

          <section className="bg-card border border-danger/50 rounded-sm p-4 flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-danger inline-flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" strokeWidth={1.7} />
                <span>Danger Zone: Reset Workspace</span>
              </h2>
              <p className="text-xs text-secondary mt-0.5">Clear all indexed photos, faces, duplicates, and events. Original files on disk are never touched.</p>
            </div>
            <button type="button" disabled={!connected || Boolean(busyLabel)} onClick={() => setShowReset(true)} className="h-8 px-3 rounded-xs border border-danger bg-danger-bg text-danger text-xs font-medium hover:bg-danger hover:text-white disabled:opacity-45">
              Reset Workspace Data...
            </button>
          </section>
        </div>
      </div>

      {showDates && <SuspiciousDatesModal onClose={(changed) => { setShowDates(false); if (changed) handleRebuild(); }} />}
      {showFailed && <FailedPhotosModal onClose={() => setShowFailed(false)} />}
      {showReset && <ResetWorkspaceModal onClose={() => setShowReset(false)} onConfirm={handleResetConfirm} />}
    </div>
  );
}
