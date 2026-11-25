import { useCallback, useEffect, useRef, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Grid2x2,
  Grid3x3,
  Images,
  Loader2,
  ScanFace,
  Search,
  Table2,
  Trash2,
  X,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { rpc } from '../lib/api';
import { LatestTask, SORTS } from '../lib/utils';
import type {
  LayoutMode,
  PersonRecord,
  PhotoRecord,
  SavedSearchRecord,
  TagRecord,
} from '../types/memoframe';
import EmptyState from '../components/EmptyState';
import PeopleStrip from '../components/PeopleStrip';
import PhotoCard from '../components/PhotoCard';
import PhotoTable from '../components/PhotoTable';

const PAGE_SIZE = 40;

interface PhotosQueryResult {
  items: PhotoRecord[];
  total: number;
  pages: number;
  page: number;
  person_gone: boolean;
}

const LAYOUT_BUTTONS: ReadonlyArray<{ id: LayoutMode; label: string; icon: LucideIcon }> = [
  { id: 'grid', label: 'Grid', icon: Grid2x2 },
  { id: 'compact', label: 'Compact', icon: Grid3x3 },
  { id: 'table', label: 'Table', icon: Table2 },
];

export default function GalleryView() {
  const {
    connected, dataVersion, notify,
    selectedPersonId, setSelectedPersonId,
    galleryExtraFilters, setGalleryExtraFilters,
    setLightboxPhoto,
  } = useApp();

  const [searchText, setSearchText] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [minFaces, setMinFaces] = useState(0);
  const [dupFilter, setDupFilter] = useState<'all' | 'unique' | 'duplicates' | 'hidden'>('all');
  const [sortKey, setSortKey] = useState('date_desc');
  const [tagFilter, setTagFilter] = useState('');
  const [faceZoom, setFaceZoom] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('grid');
  const [page, setPage] = useState(0);

  const [items, setItems] = useState<PhotoRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);

  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [tags, setTags] = useState<TagRecord[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearchRecord[]>([]);
  const [savedMenuOpen, setSavedMenuOpen] = useState(false);
  const [savingName, setSavingName] = useState('');

  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const loaderRef = useRef(new LatestTask());

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchText.trim()), 300);
    return () => clearTimeout(t);
  }, [searchText]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const buildFilters = useCallback((): Record<string, unknown> => {
    const f: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(galleryExtraFilters || {})) {
      if (!k.startsWith('_')) f[k] = v;
    }
    if (debouncedSearch) f.text = debouncedSearch;
    if (minFaces > 0) f.min_faces = minFaces;
    if (selectedPersonId !== null) f.person_id = selectedPersonId;
    if (tagFilter) f.tag = tagFilter;
    if (dupFilter === 'unique') f.duplicate = 'none';
    else if (dupFilter === 'duplicates') f.duplicate = 'any';
    else if (dupFilter === 'hidden') f.mark = 'hidden';
    return f;
  }, [galleryExtraFilters, debouncedSearch, minFaces, selectedPersonId, tagFilter, dupFilter]);

  useEffect(() => {
    setPage(0);
  }, [debouncedSearch, minFaces, dupFilter, sortKey, tagFilter, selectedPersonId, galleryExtraFilters]);

  useEffect(() => {
    if (!connected) return;
    rpc<PersonRecord[]>('persons.list').then((res) => setPersons(res || [])).catch(() => {});
    rpc<TagRecord[]>('tags.list', { limit: 80 }).then((res) => setTags(res || [])).catch(() => {});
  }, [connected, dataVersion]);

  useEffect(() => {
    if (!connected) return;
    setLoading(true);
    const filters = buildFilters();
    loaderRef.current.run(
      () => rpc<PhotosQueryResult>('photos.query', { filters, sort: sortKey, page, page_size: PAGE_SIZE }),
      (res) => {
        setLoading(false);
        if (!res) return;
        if (res.person_gone) setSelectedPersonId(null);
        setItems(res.items || []);
        setTotal(res.total || 0);
        setPages(res.pages || 1);
        if (res.page !== page) setPage(res.page || 0);
      },
      (err) => {
        setLoading(false);
        notify(`Load failed: ${err.message}`, 'error');
      },
    );
  }, [connected, buildFilters, sortKey, page, dataVersion, notify, setSelectedPersonId]);

  const openSavedMenu = () => {
    const next = !savedMenuOpen;
    setSavedMenuOpen(next);
    if (next && connected) {
      rpc<SavedSearchRecord[]>('saved_searches.list').then((res) => setSavedSearches(res || [])).catch(() => {});
    }
  };

  const applySavedFilters = (saved: Record<string, unknown>) => {
    const f: Record<string, unknown> = { ...(saved || {}) };
    const nextSort = typeof f.sort === 'string' ? f.sort : 'date_desc';
    delete f.sort;
    let nextDup: 'all' | 'unique' | 'duplicates' | 'hidden' = 'all';
    if (f.mark === 'hidden') { delete f.mark; nextDup = 'hidden'; }
    else if (f.duplicate === 'none') { delete f.duplicate; nextDup = 'unique'; }
    else if (f.duplicate === 'any') { delete f.duplicate; nextDup = 'duplicates'; }

    const nextTag = typeof f.tag === 'string' ? f.tag : '';
    delete f.tag;
    const nextPid = typeof f.person_id === 'number' ? f.person_id : null;
    delete f.person_id;
    const nextText = String(f.text || f.path_contains || '');
    delete f.text;
    delete f.path_contains;
    const nextMinFaces = Number(f.min_faces || 0);
    delete f.min_faces;

    setSearchText(nextText);
    setDebouncedSearch(nextText);
    setMinFaces(nextMinFaces);
    setDupFilter(nextDup);
    setSortKey(nextSort);
    setTagFilter(nextTag);
    setSelectedPersonId(nextPid);
    setGalleryExtraFilters(f);
    setSavedMenuOpen(false);
  };

  const handleSaveCurrent = async () => {
    const name = savingName.trim();
    if (!name) return;
    try {
      await rpc('saved_searches.save', { name, filters: { ...buildFilters(), sort: sortKey } });
      setSavingName('');
      const list = await rpc<SavedSearchRecord[]>('saved_searches.list');
      setSavedSearches(list || []);
      notify(`Saved search "${name}".`, 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const handleDeleteSaved = async (name: string) => {
    try {
      await rpc('saved_searches.delete', { name });
      setSavedSearches((prev) => prev.filter((s) => s.name !== name));
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const extraChipEntries = Object.entries(galleryExtraFilters || {}).filter(([k]) => !k.startsWith('_'));
  const offset = page * PAGE_SIZE;

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="bg-card border border-subtle rounded-sm p-2.5 flex flex-col gap-2 shrink-0">
        <div className="flex items-center flex-wrap gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" strokeWidth={1.6} />
            <input
              ref={searchInputRef}
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Search filename, person, place, date... (Ctrl+K)"
              className="w-full h-8 pl-8 pr-7 bg-input border border-hairline rounded-xs text-xs text-primary placeholder:text-secondary focus:outline-none focus:border-accent"
            />
            {searchText && (
              <button type="button" onClick={() => setSearchText('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-secondary hover:text-primary">
                <X className="w-3.5 h-3.5" strokeWidth={1.6} />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={() => setFaceZoom((z) => !z)}
            title="Crop each card to the largest detected face"
            className={`h-8 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors ${
              faceZoom ? 'bg-accent-light border-accent text-primary' : 'bg-card border-hairline text-secondary hover:text-primary hover:bg-elevated'
            }`}
          >
            <ScanFace className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Face Zoom</span>
          </button>

          <div className="inline-flex bg-input border border-hairline rounded-xs p-0.5 gap-0.5">
            {LAYOUT_BUTTONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setLayoutMode(id)}
                className={`h-6 px-2 inline-flex items-center gap-1 rounded-[2px] text-xs font-medium transition-colors ${
                  layoutMode === id ? 'bg-elevated text-primary border border-hairline' : 'text-secondary hover:text-primary border border-transparent'
                }`}
              >
                <Icon className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center flex-wrap gap-2">
          <label className="inline-flex items-center gap-1.5 text-xs text-secondary">
            <span>Min Faces</span>
            <input
              type="number"
              min={0}
              max={20}
              value={minFaces}
              onChange={(e) => setMinFaces(Math.max(0, Math.min(20, Number(e.target.value) || 0)))}
              className="w-14 h-7 px-2 bg-input border border-hairline rounded-xs text-xs font-mono text-primary focus:outline-none focus:border-accent"
            />
          </label>

          <select
            value={dupFilter}
            onChange={(e) => setDupFilter(e.target.value as 'all' | 'unique' | 'duplicates' | 'hidden')}
            className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent"
          >
            <option value="all">All Photos</option>
            <option value="unique">Unique Only</option>
            <option value="duplicates">Duplicates Only</option>
            <option value="hidden">Hidden Only</option>
          </select>

          <select value={sortKey} onChange={(e) => setSortKey(e.target.value)} className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent">
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>

          {tags.length > 0 && (
            <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent">
              <option value="">Any Tag</option>
              {tags.map((t) => <option key={t.label} value={t.label}>{t.label} ({t.count ?? 0})</option>)}
            </select>
          )}

          <div className="relative">
            <button type="button" onClick={openSavedMenu} className="h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
              <Bookmark className="w-3.5 h-3.5 text-secondary" strokeWidth={1.6} />
              <span>Saved</span>
            </button>
            {savedMenuOpen && (
              <div className="absolute left-0 top-8 z-30 w-64 bg-card border border-hairline rounded-sm p-2 flex flex-col gap-1.5">
                {savedSearches.map((s) => (
                  <div key={s.name} className="flex items-center justify-between gap-1">
                    <button type="button" onClick={() => applySavedFilters(s.filters)} className="flex-1 text-left px-2 py-1 text-xs text-primary hover:bg-elevated rounded-xs truncate">
                      {s.name}
                    </button>
                    <button type="button" title="Delete saved search" onClick={() => handleDeleteSaved(s.name)} className="p-1 text-secondary hover:text-danger">
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.6} />
                    </button>
                  </div>
                ))}
                {savedSearches.length > 0 && <div className="h-px bg-subtle my-0.5" />}
                <div className="flex gap-1">
                  <input
                    type="text"
                    value={savingName}
                    onChange={(e) => setSavingName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveCurrent(); }}
                    placeholder="Save current as..."
                    className="flex-1 h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent"
                  />
                  <button type="button" onClick={handleSaveCurrent} className="h-7 px-2 bg-accent text-accent-text rounded-xs text-xs font-medium hover:bg-accent-hover">
                    Save
                  </button>
                </div>
                <button type="button" onClick={() => applySavedFilters({})} className="text-left px-2 py-1 text-xs text-secondary hover:text-primary hover:bg-elevated rounded-xs">
                  Reset all filters
                </button>
              </div>
            )}
          </div>

          {extraChipEntries.map(([k, v]) => (
            <span key={k} className="h-6 px-2 inline-flex items-center gap-1.5 rounded-xs bg-accent-light border border-accent text-xs text-primary">
              <span>{k === 'group_id' ? String(galleryExtraFilters._group_label || `Event #${v}`) : `${k}: ${String(v)}`}</span>
              <button
                type="button"
                onClick={() => {
                  const next = { ...galleryExtraFilters };
                  delete next[k];
                  if (k === 'group_id') delete next._group_label;
                  setGalleryExtraFilters(next);
                }}
                className="text-primary hover:text-accent"
              >
                <X className="w-3 h-3" strokeWidth={1.8} />
              </button>
            </span>
          ))}
        </div>
      </div>

      <PeopleStrip persons={persons} selectedPersonId={selectedPersonId} onSelectPerson={setSelectedPersonId} />

      {items.length === 0 && !loading ? (
        <EmptyState
          icon={Images}
          title="No Photos Found"
          description={connected ? 'Adjust your search query, person filter, or scan a photo folder to index media.' : 'Connect your Python backend to browse indexed photos.'}
        />
      ) : layoutMode === 'table' ? (
        <PhotoTable photos={items} onOpen={setLightboxPhoto} />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto pr-1">
          <div className={`grid ${layoutMode === 'compact' ? 'grid-cols-[repeat(auto-fill,minmax(154px,1fr))] gap-2' : 'grid-cols-[repeat(auto-fill,minmax(204px,1fr))] gap-3'}`}>
            {items.map((item) => (
              <PhotoCard
                key={item.id}
                photo={item}
                compact={layoutMode === 'compact'}
                faceZoom={faceZoom}
                targetPersonId={selectedPersonId}
                onOpen={setLightboxPhoto}
              />
            ))}
          </div>
        </div>
      )}

      <div className="bg-card border border-subtle rounded-sm px-3 py-1.5 flex items-center justify-between shrink-0">
        <span className="text-xs text-secondary font-mono tabular-nums inline-flex items-center gap-1.5">
          {loading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
              <span className="text-accent font-medium animate-pulse">Loading photos...</span>
            </>
          ) : items.length ? (
            `Showing ${offset + 1}-${offset + items.length} of ${total.toLocaleString()} photos`
          ) : (
            'No photos matched'
          )}
        </span>
        <div className="flex items-center gap-1.5">
          <button type="button" disabled={page <= 0} onClick={() => setPage((p) => Math.max(0, p - 1))} className="h-7 px-2 inline-flex items-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-40">
            <ChevronLeft className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Prev</span>
          </button>
          <span className="text-xs font-mono text-secondary px-2 tabular-nums">Page {page + 1} / {pages}</span>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((p) => Math.min(pages - 1, p + 1))} className="h-7 px-2 inline-flex items-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-40">
            <span>Next</span>
            <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.6} />
          </button>
        </div>
      </div>
    </div>
  );
}
