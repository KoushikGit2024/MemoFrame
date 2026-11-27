import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, GitMerge, Loader2, RefreshCw, ScanFace, Search, Users } from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { rpc } from "../../shared/lib/api";
import { LatestTask } from "../../shared/lib/utils";
import type { PersonRecord } from "../../shared/types/memoframe";
import EmptyState from "../../shared/ui/EmptyState";
import ModalShell from "../../shared/ui/ModalShell";
import PersonAvatar from "../../shared/ui/PersonAvatar";
import FaceReviewModal from "./FaceReviewModal";
import MergePeopleModal from "./MergePeopleModal";

const UNIDENTIFIED_RE = /^(person\s+\d+|unknown)$/i;

interface PersonCardProps {
  person: PersonRecord;
  isSelected: boolean;
  onOpen: (id: number) => void;
  onRename: (person: PersonRecord) => void;
  onReview: (id: number) => void;
}

const PersonCard = React.memo(function PersonCard({
  person: p,
  isSelected,
  onOpen,
  onRename,
  onReview,
}: PersonCardProps) {
  const isUnidentified = !p.name || UNIDENTIFIED_RE.test(p.name.trim());
  return (
    <div
      className={`bg-card border rounded-sm p-3 flex flex-col gap-3 transition-colors ${
        isSelected
          ? "border-violet bg-violet-bg/30"
          : isUnidentified
            ? "border-subtle border-dashed hover:border-amber/60"
            : "border-subtle hover:border-violet/60"
      }`}
    >
      <button
        type="button"
        onClick={() => onOpen(p.id)}
        className="flex items-center gap-3 text-left min-w-0"
      >
        <PersonAvatar
          person={p}
          size="md"
          accent={isSelected ? "violet" : isUnidentified ? "amber" : "violet"}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className={`text-[13px] font-semibold truncate ${isSelected ? "text-violet" : "text-primary"}`}
            >
              {p.name}
            </span>
            {!isUnidentified && (
              <CheckCircle2
                className="w-3.5 h-3.5 text-success shrink-0"
                strokeWidth={1.8}
                aria-label="Identified person"
              />
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs font-mono text-secondary tabular-nums">
              {p.image_count || 0} photos
            </span>
            {isSelected ? (
              <span className="px-1.5 py-px rounded-xs bg-violet-bg border border-violet/45 text-[10px] font-medium text-violet">
                Selected
              </span>
            ) : isUnidentified ? (
              <span className="px-1.5 py-px rounded-xs bg-amber-bg border border-amber/35 text-[10px] font-medium text-amber">
                Unidentified
              </span>
            ) : null}
          </div>
        </div>
      </button>
      <div className="grid grid-cols-3 gap-1.5">
        <button
          type="button"
          onClick={() => onRename(p)}
          className="h-7 rounded-xs border border-transparent text-xs text-secondary hover:text-violet hover:bg-violet-bg/60 transition-colors"
        >
          Rename
        </button>
        <button
          type="button"
          onClick={() => onReview(p.id)}
          className="h-7 rounded-xs border border-transparent text-xs text-secondary hover:text-primary hover:bg-elevated transition-colors"
        >
          Review
        </button>
        <button
          type="button"
          onClick={() => onOpen(p.id)}
          className="h-7 rounded-xs border border-violet/40 bg-violet-bg text-xs font-medium text-violet hover:bg-violet hover:text-violet-text transition-colors"
        >
          View
        </button>
      </div>
    </div>
  );
});

export default function PeopleView() {
  const {
    connected,
    dataVersion,
    invalidate,
    notify,
    openPersonInGallery,
    selectedPersonId,
    setSelectedPersonId,
  } = useApp();
  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const isFiltering = query !== debouncedQuery;

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQuery(query), 150);
    return () => window.clearTimeout(id);
  }, [query]);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [reviewPersonId, setReviewPersonId] = useState<number | null | undefined>(undefined);
  const [renaming, setRenaming] = useState<PersonRecord | null>(null);
  const [renameText, setRenameText] = useState("");
  const [renamingBusy, setRenamingBusy] = useState(false);
  const loaderRef = useRef(new LatestTask());

  const loadPersons = useCallback(() => {
    if (!connected) return;
    loaderRef.current.run(
      () => rpc<PersonRecord[]>("persons.list"),
      res => setPersons(res || []),
      err => notify(err.message, "error")
    );
  }, [connected, notify]);

  useEffect(() => {
    loadPersons();
  }, [loadPersons, dataVersion]);

  const filtered = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase();
    return persons.filter(p =>
      String(p.name || "")
        .toLowerCase()
        .includes(q)
    );
  }, [persons, debouncedQuery]);

  const submitRename = async () => {
    if (!renaming || !renameText.trim() || renamingBusy) return;
    setRenamingBusy(true);
    try {
      await rpc("persons.rename", {
        person_id: renaming.id,
        new_name: renameText.trim(),
        confirm: true,
      });
      setRenaming(null);
      notify("Person renamed and faces confirmed.", "success");
      loadPersons();
      invalidate();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setRenamingBusy(false);
    }
  };

  const handleRenameClick = useCallback((p: PersonRecord) => {
    setRenaming(p);
    setRenameText(p.name || "");
  }, []);

  const handleReviewClick = useCallback((id: number) => {
    setReviewPersonId(id);
  }, []);

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-3 shrink-0 flex-wrap">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">
            Identified People ({persons.length})
          </h1>
          <p className="text-xs text-secondary mt-0.5">
            Browse photos by person, rename clusters, review faces, or merge duplicates.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="group relative">
            <Search
              className="w-3.5 h-3.5 text-secondary group-focus-within:text-accent-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none transition-colors"
              strokeWidth={1.6}
            />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Filter by name..."
              className="h-8 w-48 pl-8 pr-7 bg-input border border-hairline rounded-xs text-xs text-primary placeholder:text-secondary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30 transition-colors"
            />
            {isFiltering && (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
            )}
          </div>
          <button
            type="button"
            disabled={persons.length < 2}
            onClick={() => setMergeOpen(true)}
            className="btn-primary h-8 px-3 text-xs"
          >
            <GitMerge className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Merge People</span>
          </button>
          <button
            type="button"
            onClick={() => setReviewPersonId(null)}
            className="btn-tertiary h-8 px-2.5 text-xs"
          >
            <ScanFace className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Unassigned Faces</span>
          </button>
          <button type="button" onClick={loadPersons} className="btn-neutral h-8 px-2.5 text-xs">
            <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No People Found"
          description={
            query
              ? "No people match that search query."
              : "No face clusters have been indexed in this workspace yet."
          }
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto pr-1">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(256px,1fr))] gap-3">
            {filtered.map(p => (
              <PersonCard
                key={p.id}
                person={p}
                isSelected={selectedPersonId === p.id}
                onOpen={openPersonInGallery}
                onRename={handleRenameClick}
                onReview={handleReviewClick}
              />
            ))}
          </div>
        </div>
      )}

      {renaming && (
        <ModalShell
          title="Rename Person"
          subtitle={`Confirming faces and auto-merging matching names for ${renaming.name}`}
          size="sm"
          onClose={() => setRenaming(null)}
          footer={
            <>
              <button
                type="button"
                disabled={renamingBusy}
                onClick={() => setRenaming(null)}
                className="btn-neutral h-8 px-3 text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={renamingBusy || !renameText.trim()}
                onClick={submitRename}
                className="btn-primary h-8 px-3 text-xs"
              >
                {renamingBusy && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-text" />}
                <span>{renamingBusy ? "Saving..." : "Save Name"}</span>
              </button>
            </>
          }
        >
          <input
            type="text"
            autoFocus
            value={renameText}
            onChange={e => setRenameText(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") submitRename();
            }}
            className="h-9 px-3 bg-input border border-hairline rounded-xs text-sm text-primary focus:outline-none focus:border-violet focus:ring-1 focus:ring-violet/30"
          />
        </ModalShell>
      )}

      {mergeOpen && (
        <MergePeopleModal
          persons={persons}
          onClose={() => setMergeOpen(false)}
          onMerged={(keepId, others) => {
            setMergeOpen(false);
            if (selectedPersonId !== null && others.includes(selectedPersonId))
              setSelectedPersonId(keepId);
            loadPersons();
            invalidate();
          }}
        />
      )}

      {reviewPersonId !== undefined && (
        <FaceReviewModal
          personId={reviewPersonId}
          onClose={dirty => {
            setReviewPersonId(undefined);
            if (dirty) {
              loadPersons();
              invalidate();
            }
          }}
        />
      )}
    </div>
  );
}
