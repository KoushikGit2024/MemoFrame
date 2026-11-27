import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, UserCheck, Users, X } from "lucide-react";
import { useApp } from "../context/AppContext";
import { rpc } from "../lib/api";
import { sortPersons } from "../lib/utils";
import type { PersonRecord, PersonSortMode } from "../types/memoframe";
import PersonAvatar from "./PersonAvatar";

const UNIDENTIFIED_RE = /^(person\s+\d+|unknown)$/i;
const COLLAPSED_LIMIT = 12;

interface PeopleStripProps {
  persons: PersonRecord[];
  loading?: boolean;
  selectedPersonIds: number[];
  onTogglePerson: (personId: number) => void;
  onSelectSinglePerson?: (personId: number) => void;
  onClearPersons: () => void;
  onlySelectedPersons: boolean;
  onToggleOnlySelected: () => void;
  anySelectedPersons?: boolean;
  onToggleAnySelected?: () => void;
}

export default function PeopleStrip({
  persons,
  loading = false,
  selectedPersonIds,
  onTogglePerson,
  onSelectSinglePerson,
  onClearPersons,
  onlySelectedPersons,
  onToggleOnlySelected,
  anySelectedPersons = false,
  onToggleAnySelected,
}: PeopleStripProps) {
  const { invalidate, notify } = useApp();
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<PersonSortMode>("most");
  const [expanded, setExpanded] = useState(false);
  const [multiSelect, setMultiSelect] = useState(false);
  const [renamingPerson, setRenamingPerson] = useState<PersonRecord | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [savingRename, setSavingRename] = useState(false);

  const handleRenameSubmit = async () => {
    if (!renamingPerson || !renameValue.trim() || savingRename) return;
    setSavingRename(true);
    try {
      await rpc("persons.rename", {
        person_id: renamingPerson.id,
        new_name: renameValue.trim(),
        confirm: true,
      });
      setRenamingPerson(null);
      invalidate();
      notify(`Renamed to "${renameValue.trim()}".`, "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setSavingRename(false);
    }
  };

  const selectedPersons = useMemo(
    () =>
      selectedPersonIds
        .map(id => persons.find(p => p.id === id))
        .filter((p): p is PersonRecord => Boolean(p)),
    [persons, selectedPersonIds]
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = (persons || []).filter(p =>
      String(p.name || "")
        .toLowerCase()
        .includes(q)
    );
    return sortPersons(filtered, sortMode);
  }, [persons, query, sortMode]);

  if (!persons || persons.length === 0) {
    if (!loading) return null;
    return (
      <div className="bg-card border border-subtle rounded-sm px-3 py-2 flex items-center gap-2 text-xs text-secondary shrink-0">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-violet" />
        <span>Loading people...</span>
      </div>
    );
  }

  const isSearching = query.trim().length > 0;
  const canCollapse = !isSearching && visible.length > COLLAPSED_LIMIT;
  const displayed = canCollapse && !expanded ? visible.slice(0, COLLAPSED_LIMIT) : visible;
  const hiddenCount = visible.length - displayed.length;

  return (
    <div className="bg-card border border-subtle rounded-sm px-3 py-2 flex flex-col gap-2 shrink-0">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary">
            <Users className="w-3.5 h-3.5 text-violet" strokeWidth={1.7} />
            <span>People ({persons.length})</span>
          </span>

          {selectedPersons.map(sp => (
            <div
              key={sp.id}
              className="h-7 inline-flex items-center gap-1.5 pl-0.5 pr-2 rounded-sm bg-violet-bg border border-violet text-xs font-semibold text-violet overflow-hidden"
            >
              <PersonAvatar person={sp} size="sm" accent="violet" />
              <span className="truncate max-w-[120px]">{sp.name}</span>
              <button
                type="button"
                aria-label={`Remove ${sp.name}`}
                onClick={() => onTogglePerson(sp.id)}
                className="ml-0.5 hover:text-primary transition-colors cursor-pointer shrink-0"
              >
                <X className="w-3 h-3" strokeWidth={2} />
              </button>
            </div>
          ))}

          {selectedPersons.length > 0 && (
            <>
              {selectedPersons.length > 1 && onToggleAnySelected && (
                <button
                  type="button"
                  onClick={onToggleAnySelected}
                  title="Match photos containing ANY of the selected people (OR)"
                  className={`h-7 px-2 inline-flex items-center gap-1 rounded-sm border text-xs font-medium transition-colors cursor-pointer ${
                    anySelectedPersons
                      ? "bg-accent-secondary text-white border-accent-secondary font-semibold"
                      : "bg-input border-hairline text-secondary hover:text-primary hover:border-accent-secondary/50"
                  }`}
                >
                  <span>Any</span>
                </button>
              )}
              <button
                type="button"
                onClick={onToggleOnlySelected}
                title="Show only photos containing exclusively the selected person(s) (ignores discarded/removed faces)"
                className={`h-7 px-2 inline-flex items-center gap-1 rounded-sm border text-xs font-medium transition-colors cursor-pointer ${
                  onlySelectedPersons
                    ? "bg-violet text-white border-violet font-semibold"
                    : "bg-input border-hairline text-secondary hover:text-primary hover:border-violet/50"
                }`}
              >
                <UserCheck className="w-3.5 h-3.5" strokeWidth={1.7} />
                <span>Only Selected</span>
              </button>
            </>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={() => {
              if (multiSelect) onClearPersons();
              setMultiSelect(m => !m);
            }}
            title="Toggle multi-person selection"
            className={`h-6 px-2 inline-flex items-center gap-1 rounded-xs border text-xs font-medium transition-colors cursor-pointer ${
              multiSelect
                ? "bg-violet-bg border-violet text-violet font-semibold"
                : "bg-input border-hairline text-secondary hover:text-primary hover:border-violet/50"
            }`}
          >
            <span>Multi</span>
          </button>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Find person..."
            className="h-6 w-32 sm:w-40 px-2 bg-input border border-hairline rounded-xs text-xs text-primary placeholder:text-secondary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30"
          />
          <select
            value={sortMode}
            onChange={e => setSortMode(e.target.value as PersonSortMode)}
            className="h-6 px-1.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-violet"
          >
            <option value="most">Most photos</option>
            <option value="name_asc">Name A to Z</option>
            <option value="name_desc">Name Z to A</option>
            <option value="newest">Newest</option>
          </select>
          {canCollapse && (
            <button
              type="button"
              onClick={() => setExpanded(e => !e)}
              className="h-6 px-2 inline-flex items-center gap-1 rounded-xs bg-input border border-hairline text-xs text-secondary hover:text-primary hover:border-violet/50 transition-colors cursor-pointer"
            >
              <span>{expanded ? "Less" : `All (${visible.length})`}</span>
              {expanded ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center flex-wrap gap-1.5 max-h-40 overflow-y-auto pr-0.5">
        <button
          type="button"
          onClick={onClearPersons}
          className={`h-8 px-2.5 inline-flex items-center gap-1.5 rounded-sm border text-xs font-medium transition-colors cursor-pointer ${
            selectedPersonIds.length === 0
              ? "bg-elevated border-hairline text-primary font-semibold"
              : "bg-card border-subtle text-secondary hover:text-primary hover:bg-elevated"
          }`}
        >
          All People
        </button>
        {displayed.map(p => {
          const active = selectedPersonIds.includes(p.id);
          const isUnidentified = !p.name || UNIDENTIFIED_RE.test(p.name.trim());
          return (
            <button
              key={p.id}
              type="button"
              title="Click to filter • Double-click to rename"
              onClick={() => {
                if (multiSelect || !onSelectSinglePerson) {
                  onTogglePerson(p.id);
                } else if (active && selectedPersonIds.length === 1) {
                  onClearPersons();
                } else {
                  onSelectSinglePerson(p.id);
                }
              }}
              onDoubleClick={e => {
                e.stopPropagation();
                setRenamingPerson(p);
                setRenameValue(p.name || "");
              }}
              className={`h-8 pl-1 pr-2.5 inline-flex items-center gap-2 rounded-sm border text-xs transition-all cursor-pointer overflow-hidden ${
                active
                  ? "bg-violet-bg border-violet text-violet font-semibold ring-1 ring-violet/40"
                  : isUnidentified
                    ? "bg-card border-subtle border-dashed text-secondary hover:border-amber/60 hover:text-primary hover:bg-elevated"
                    : "bg-card border-subtle text-primary hover:border-violet/55 hover:bg-elevated"
              }`}
            >
              <PersonAvatar
                person={p}
                size="sm"
                accent={active ? "violet" : isUnidentified ? "amber" : "default"}
              />
              <span className="max-w-[140px] truncate">{p.name}</span>
              <span
                className={`font-mono text-[10.5px] ${active ? "text-violet" : "text-secondary"}`}
              >
                {p.image_count || 0}
              </span>
            </button>
          );
        })}
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="h-8 px-2.5 inline-flex items-center gap-1 rounded-sm border border-dashed border-hairline text-xs text-secondary hover:text-primary hover:border-violet/50 transition-colors cursor-pointer"
          >
            +{hiddenCount} more
          </button>
        )}
      </div>

      {renamingPerson && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => !savingRename && setRenamingPerson(null)}
        >
          <div
            className="w-full max-w-xs bg-card border border-hairline rounded-md shadow-2xl p-3.5 flex flex-col gap-3"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <PersonAvatar person={renamingPerson} size="sm" accent="violet" />
                <span className="text-xs font-semibold text-primary truncate">
                  Rename {renamingPerson.name}
                </span>
              </div>
              <button
                type="button"
                disabled={savingRename}
                onClick={() => setRenamingPerson(null)}
                className="text-secondary hover:text-primary cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <input
              type="text"
              autoFocus
              disabled={savingRename}
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter") handleRenameSubmit();
                else if (e.key === "Escape" && !savingRename) setRenamingPerson(null);
              }}
              placeholder="Enter person name..."
              className="w-full h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-violet focus:ring-1 focus:ring-violet/30"
            />
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                disabled={savingRename}
                onClick={() => setRenamingPerson(null)}
                className="btn-neutral h-7 px-2.5 text-xs cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingRename || !renameValue.trim()}
                onClick={handleRenameSubmit}
                className="btn-primary h-7 px-3 text-xs cursor-pointer"
              >
                {savingRename ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
