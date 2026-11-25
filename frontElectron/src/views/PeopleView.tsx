import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GitMerge, Loader2, RefreshCw, ScanFace, Search, Users } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { rpc } from '../lib/api';
import { LatestTask } from '../lib/utils';
import type { PersonRecord } from '../types/memoframe';
import EmptyState from '../components/EmptyState';
import ModalShell from '../components/ModalShell';
import PersonAvatar from '../components/PersonAvatar';
import FaceReviewModal from '../modals/FaceReviewModal';
import MergePeopleModal from '../modals/MergePeopleModal';

export default function PeopleView() {
  const { connected, dataVersion, invalidate, notify, openPersonInGallery, selectedPersonId, setSelectedPersonId } = useApp();
  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [query, setQuery] = useState('');
  const [mergeOpen, setMergeOpen] = useState(false);
  const [reviewPersonId, setReviewPersonId] = useState<number | null | undefined>(undefined);
  const [renaming, setRenaming] = useState<PersonRecord | null>(null);
  const [renameText, setRenameText] = useState('');
  const [renamingBusy, setRenamingBusy] = useState(false);
  const loaderRef = useRef(new LatestTask());

  const loadPersons = useCallback(() => {
    if (!connected) return;
    loaderRef.current.run(
      () => rpc<PersonRecord[]>('persons.list'),
      (res) => setPersons(res || []),
      (err) => notify(err.message, 'error'),
    );
  }, [connected, notify]);

  useEffect(() => { loadPersons(); }, [loadPersons, dataVersion]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return persons.filter((p) => String(p.name || '').toLowerCase().includes(q));
  }, [persons, query]);

  const submitRename = async () => {
    if (!renaming || !renameText.trim() || renamingBusy) return;
    setRenamingBusy(true);
    try {
      await rpc('persons.rename', { person_id: renaming.id, new_name: renameText.trim(), confirm: true });
      setRenaming(null);
      notify('Person renamed and faces confirmed.', 'success');
      loadPersons();
      invalidate();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setRenamingBusy(false);
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-3 shrink-0 flex-wrap">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">Identified People ({persons.length})</h1>
          <p className="text-xs text-secondary mt-0.5">Browse photos by person, rename clusters, review faces, or merge duplicates.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" strokeWidth={1.6} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by name..."
              className="h-8 w-48 pl-8 pr-2.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent"
            />
          </div>
          <button
            type="button"
            disabled={persons.length < 2}
            onClick={() => setMergeOpen(true)}
            className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover disabled:opacity-40"
          >
            <GitMerge className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Merge People</span>
          </button>
          <button
            type="button"
            onClick={() => setReviewPersonId(null)}
            className="h-8 px-2.5 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated"
          >
            <ScanFace className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Unassigned Faces</span>
          </button>
          <button
            type="button"
            onClick={loadPersons}
            className="h-8 px-2.5 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated"
          >
            <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No People Found"
          description={query ? 'No people match that search query.' : 'No face clusters have been indexed in this workspace yet.'}
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto pr-1">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(256px,1fr))] gap-3">
            {filtered.map((p) => (
              <div key={p.id} className="bg-card border border-subtle hover:border-hairline rounded-sm p-3 flex flex-col gap-3">
                <button type="button" onClick={() => openPersonInGallery(p.id)} className="flex items-center gap-3 text-left min-w-0">
                  <PersonAvatar person={p} size="md" />
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-primary truncate">{p.name}</div>
                    <div className="text-xs font-mono text-secondary tabular-nums">{p.image_count || 0} photos</div>
                  </div>
                </button>
                <div className="grid grid-cols-3 gap-1.5">
                  <button type="button" onClick={() => { setRenaming(p); setRenameText(p.name || ''); }} className="h-7 rounded-xs border border-transparent text-xs text-secondary hover:text-primary hover:bg-elevated">
                    Rename
                  </button>
                  <button type="button" onClick={() => setReviewPersonId(p.id)} className="h-7 rounded-xs border border-transparent text-xs text-secondary hover:text-primary hover:bg-elevated">
                    Review
                  </button>
                  <button type="button" onClick={() => openPersonInGallery(p.id)} className="h-7 rounded-xs border border-hairline bg-elevated text-xs text-primary hover:border-accent">
                    View
                  </button>
                </div>
              </div>
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
                className="h-8 px-3 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={renamingBusy || !renameText.trim()}
                onClick={submitRename}
                className="h-8 px-3 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover disabled:opacity-50 inline-flex items-center gap-1.5 transition-colors"
              >
                {renamingBusy && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-text" />}
                <span>{renamingBusy ? 'Saving...' : 'Save Name'}</span>
              </button>
            </>
          }
        >
          <input
            type="text"
            autoFocus
            value={renameText}
            onChange={(e) => setRenameText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submitRename(); }}
            className="h-9 px-3 bg-input border border-hairline rounded-xs text-sm text-primary focus:outline-none focus:border-accent"
          />
        </ModalShell>
      )}

      {mergeOpen && (
        <MergePeopleModal
          persons={persons}
          onClose={() => setMergeOpen(false)}
          onMerged={(keepId, others) => {
            setMergeOpen(false);
            if (selectedPersonId !== null && others.includes(selectedPersonId)) setSelectedPersonId(keepId);
            loadPersons();
            invalidate();
          }}
        />
      )}

      {reviewPersonId !== undefined && (
        <FaceReviewModal
          personId={reviewPersonId}
          onClose={(dirty) => {
            setReviewPersonId(undefined);
            if (dirty) { loadPersons(); invalidate(); }
          }}
        />
      )}
    </div>
  );
}
