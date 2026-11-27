import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { rpc } from "../../shared/lib/api";
import type { SuspiciousDateRow } from "../../shared/types/memoframe";
import ModalShell from "../../shared/ui/ModalShell";

function toInputValue(iso?: string | null): string {
  if (iso && String(iso).length >= 16) {
    return String(iso).slice(0, 19).replace(" ", "T");
  }
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:00`;
}

interface DateOverrideModalProps {
  currentIso?: string | null;
  onClose?: () => void;
  onSave?: (iso: string) => void;
}

export function DateOverrideModal({ currentIso, onClose, onSave }: DateOverrideModalProps) {
  const [val, setVal] = useState<string>(() => toInputValue(currentIso));

  const submit = () => {
    if (!val) return;
    const iso = val.length === 16 ? `${val}:00` : val.slice(0, 19);
    onSave?.(iso);
  };

  return (
    <ModalShell
      title="Correct Date"
      subtitle="Only the database changes; the original photo file is never modified."
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-neutral h-8 px-3 text-xs">
            Cancel
          </button>
          <button type="button" onClick={submit} className="btn-primary h-8 px-3 text-xs">
            Apply Date
          </button>
        </>
      }
    >
      <input
        type="datetime-local"
        step="1"
        value={val}
        onChange={e => setVal(e.target.value)}
        className="h-9 px-3 bg-input border border-hairline rounded-xs text-sm font-mono text-primary focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber/30"
      />
    </ModalShell>
  );
}

export function SuspiciousDatesModal({ onClose }: { onClose?: (changed: boolean) => void }) {
  const { notify } = useApp();
  const [rows, setRows] = useState<SuspiciousDateRow[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [changed, setChanged] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  useEffect(() => {
    rpc<SuspiciousDateRow[]>("dates.suspicious", { limit: 500 })
      .then(res => setRows(res || []))
      .catch(err => notify(err instanceof Error ? err.message : String(err), "error"));
  }, [notify]);

  const toggleRow = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const applyBulkDate = async (iso: string) => {
    setShowPicker(false);
    const ids = [...selectedIds];
    setBusyAction("apply");
    try {
      for (const id of ids) {
        try {
          await rpc("photos.set_date", { image_id: id, iso, reason: "manual (bulk)" });
        } catch (err) {
          notify(err instanceof Error ? err.message : String(err), "error");
        }
      }
      setRows(prev => prev.map(r => (selectedIds.has(r.id) ? { ...r, override_ts: iso } : r)));
      setChanged(true);
      notify(`Updated ${ids.length} photo date(s).`, "success");
    } finally {
      setBusyAction(null);
    }
  };

  const clearSelected = async () => {
    const ids = [...selectedIds];
    setBusyAction("clear");
    try {
      for (const id of ids) {
        try {
          await rpc("photos.clear_date", { image_id: id });
        } catch (err) {
          notify(err instanceof Error ? err.message : String(err), "error");
        }
      }
      setRows(prev => prev.map(r => (selectedIds.has(r.id) ? { ...r, override_ts: null } : r)));
      setChanged(true);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <>
      <ModalShell
        title="Suspicious Dates"
        subtitle={`${rows.length} photo(s) have a missing, future, or implausible date.`}
        size="lg"
        onClose={() => onClose?.(changed)}
        footer={
          <div className="w-full flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={selectedIds.size === 0 || busyAction !== null}
                onClick={() => setShowPicker(true)}
                className="btn-primary h-8 px-3 text-xs"
              >
                {busyAction === "apply" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-text" />
                )}
                <span>
                  {busyAction === "apply" ? "Setting..." : `Set Date (${selectedIds.size})`}
                </span>
              </button>
              <button
                type="button"
                disabled={selectedIds.size === 0 || busyAction !== null}
                onClick={clearSelected}
                className="btn-neutral h-8 px-3 text-xs"
              >
                {busyAction === "clear" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-secondary" />
                )}
                <span>{busyAction === "clear" ? "Clearing..." : "Clear Correction"}</span>
              </button>
            </div>
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => onClose?.(changed)}
              className="btn-neutral h-8 px-3 text-xs"
            >
              Close
            </button>
          </div>
        }
      >
        <div className="max-h-[420px] overflow-auto border border-subtle rounded-xs">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="sticky top-0 z-10 bg-elevated border-b border-hairline text-[11px] uppercase text-secondary">
                <th className="py-2 px-2.5 w-8" />
                <th className="py-2 px-2.5 text-left">Path</th>
                <th className="py-2 px-2.5 text-left w-40">Recorded</th>
                <th className="py-2 px-2.5 text-left w-28">Problem</th>
                <th className="py-2 px-2.5 text-left w-40">Corrected To</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const selected = selectedIds.has(r.id);
                return (
                  <tr
                    key={r.id}
                    onClick={() => toggleRow(r.id)}
                    className={`border-b border-subtle cursor-pointer transition-colors ${
                      selected ? "bg-amber-bg/40" : "hover:bg-elevated"
                    }`}
                  >
                    <td className="py-1.5 px-2.5 text-center">
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => {}}
                        className="accent-amber"
                      />
                    </td>
                    <td
                      className="py-1.5 px-2.5 font-mono text-[11px] max-w-[340px] truncate"
                      title={r.path}
                    >
                      {r.path}
                    </td>
                    <td className="py-1.5 px-2.5 font-mono text-secondary">{r.exif_ts || "—"}</td>
                    <td className="py-1.5 px-2.5 text-danger">{r.date_flag || "—"}</td>
                    <td className="py-1.5 px-2.5 font-mono text-success">{r.override_ts || ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ModalShell>

      {showPicker && (
        <DateOverrideModal
          currentIso={rows.find(r => selectedIds.has(r.id))?.override_ts}
          onClose={() => setShowPicker(false)}
          onSave={applyBulkDate}
        />
      )}
    </>
  );
}
