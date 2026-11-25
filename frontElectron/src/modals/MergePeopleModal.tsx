import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useApp } from "../context/AppContext";
import { rpc } from "../lib/api";
import type { PersonRecord } from "../types/memoframe";
import ModalShell from "../components/ModalShell";
import PersonAvatar from "../components/PersonAvatar";

interface MergePeopleModalProps {
  persons: PersonRecord[];
  onClose?: () => void;
  onMerged?: (keepId: number, others: number[]) => void;
}

export default function MergePeopleModal({ persons, onClose, onMerged }: MergePeopleModalProps) {
  const { notify } = useApp();
  const [query, setQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [busy, setBusy] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return persons.filter(p =>
      String(p.name || "")
        .toLowerCase()
        .includes(q)
    );
  }, [persons, query]);

  const toggle = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selection = useMemo(() => {
    const picked = persons.filter(p => selectedIds.has(p.id));
    if (picked.length < 2) return null;
    const keeper = picked.reduce(
      (best, p) => (Number(p.image_count || 0) > Number(best.image_count || 0) ? p : best),
      picked[0]
    );
    const others = picked.filter(p => p.id !== keeper.id).map(p => p.id);
    return { keeper, others };
  }, [persons, selectedIds]);

  const handleMerge = async () => {
    if (!selection || busy) return;
    setBusy(true);
    try {
      await rpc("persons.merge", { keep_id: selection.keeper.id, other_ids: selection.others });
      notify(
        `Merged ${selection.others.length} cluster(s) into ${selection.keeper.name}.`,
        "success"
      );
      onMerged?.(selection.keeper.id, selection.others);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title="Merge People"
      subtitle="Select clusters that are the same person. The one with the most photos is kept."
      size="md"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-neutral h-8 px-3 text-xs">
            Cancel
          </button>
          <button
            type="button"
            disabled={!selection || busy}
            onClick={handleMerge}
            className="btn-primary h-8 px-3 text-xs"
          >
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-text" />}
            <span>{busy ? "Merging..." : "Merge Selected"}</span>
          </button>
        </>
      }
    >
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Filter by name..."
        className="h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary placeholder:text-secondary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30"
      />
      <div className="max-h-80 overflow-y-auto border border-subtle rounded-xs divide-y divide-subtle">
        {filtered.map(p => {
          const checked = selectedIds.has(p.id);
          const isKeeper = selection?.keeper.id === p.id;
          return (
            <label
              key={p.id}
              className={`flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-colors ${
                checked ? "bg-violet-bg/45" : "hover:bg-elevated"
              }`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(p.id)}
                className="accent-violet"
              />
              <PersonAvatar person={p} size="sm" accent={checked ? "violet" : "default"} />
              <span
                className={`text-xs font-medium flex-1 truncate ${checked ? "text-violet" : "text-primary"}`}
              >
                {p.name}
              </span>
              {isKeeper && (
                <span className="px-1.5 py-px rounded-xs bg-success-bg border border-success/40 text-[10px] font-medium text-success">
                  Keeper
                </span>
              )}
              <span className="text-xs font-mono text-secondary">{p.image_count || 0} photos</span>
            </label>
          );
        })}
      </div>
      <div className="text-xs text-secondary">
        {selection
          ? `Keeping "${selection.keeper.name}"; merging ${selection.others.length} other cluster(s) into it.`
          : "Select at least two people to merge."}
      </div>
    </ModalShell>
  );
}
