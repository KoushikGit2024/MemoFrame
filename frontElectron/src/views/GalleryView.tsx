import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Columns3,
  FileText,
  Grid2x2,
  Grid3x3,
  Images,
  Loader2,
  ScanFace,
  Search,
  Shuffle,
  SlidersHorizontal,
  Star,
  Table2,
  Tag,
  UserRoundSearch,
  X,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { rpc } from "../lib/api";
import { LatestTask, SORTS } from "../lib/utils";
import type {
  LayoutMode,
  PersonRecord,
  PhotoRecord,
  TagRecord,
} from "../types/memoframe";
import EmptyState from "../components/EmptyState";
import PeopleStrip from "../components/PeopleStrip";
import PhotoCard from "../components/PhotoCard";
import PhotoTable from "../components/PhotoTable";



interface PhotosQueryResult {
  items: PhotoRecord[];
  total: number;
  pages: number;
  page: number;
  person_gone: boolean;
}

const LAYOUT_BUTTONS: ReadonlyArray<{ id: LayoutMode; label: string; icon: LucideIcon }> = [
  { id: "grid", label: "Grid", icon: Grid2x2 },
  { id: "compact", label: "Compact", icon: Grid3x3 },
  { id: "table", label: "Table", icon: Table2 },
];

export default function GalleryView() {
  const {
    connected,
    dataVersion,
    invalidate,
    notify,
    selectedPersonId,
    setSelectedPersonId,
    galleryExtraFilters,
    setGalleryExtraFilters,
    setLightboxPhoto,
    setLightboxList,
  } = useApp();

  const [searchText, setSearchText] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [minFaces, setMinFaces] = useState(0);
  const [dupFilter, setDupFilter] = useState<"all" | "unique" | "duplicates" | "hidden">("all");
  const [sortKey, setSortKey] = useState("date_desc");
  const [tagFilter, setTagFilter] = useState("");
  const [unusedFacesOnly, setUnusedFacesOnly] = useState(false);
  const [faceZoom, setFaceZoom] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("grid");
  const [page, setPage] = useState(0);
  const [showInfo, setShowInfo] = useState(true);
  const [customCols, setCustomCols] = useState<number | null>(null);
  const [customPageSize, setCustomPageSize] = useState(40);
  const [controlsCollapsed, setControlsCollapsed] = useState(false);
  const [shuffleSeed, setShuffleSeed] = useState<number | null>(null);
  const [selectedPersonIds, setSelectedPersonIds] = useState<number[]>(
    selectedPersonId !== null ? [selectedPersonId] : []
  );
  const [onlySelectedPersons, setOnlySelectedPersons] = useState(false);
  const [anySelectedPersons, setAnySelectedPersons] = useState(false);
  const [favouritesOnly, setFavouritesOnly] = useState(false);

  useEffect(() => {
    if (selectedPersonId !== null) {
      setSelectedPersonIds([selectedPersonId]);
    }
  }, [selectedPersonId]);

  const [items, setItems] = useState<PhotoRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);

  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [loadingPersons, setLoadingPersons] = useState(false);
  const [tags, setTags] = useState<TagRecord[]>([]);

  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const loaderRef = useRef(new LatestTask());
  const lastMetaVersionRef = useRef<number>(-1);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchText.trim()), 300);
    return () => clearTimeout(t);
  }, [searchText]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const buildFilters = useCallback((): Record<string, unknown> => {
    const f: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(galleryExtraFilters || {})) {
      if (!k.startsWith("_")) f[k] = v;
    }
    if (debouncedSearch) f.text = debouncedSearch;
    if (minFaces > 0) f.min_faces = minFaces;
    if (selectedPersonIds.length === 1) f.person_id = selectedPersonIds[0];
    else if (selectedPersonIds.length > 1) f.person_ids = selectedPersonIds;
    if (selectedPersonIds.length > 0 && onlySelectedPersons) {
      f.only_selected_persons = true;
    }
    if (selectedPersonIds.length > 1 && anySelectedPersons) {
      f.any_selected_persons = true;
    }
    if (unusedFacesOnly) f.unassigned_faces = true;
    if (tagFilter) f.tag = tagFilter;
    if (dupFilter === "unique") f.duplicate = "none";
    else if (dupFilter === "duplicates") f.duplicate = "any";
    else if (dupFilter === "hidden") f.mark = "hidden";
    if (favouritesOnly) f.mark = "favourite";
    return f;
  }, [
    galleryExtraFilters,
    debouncedSearch,
    minFaces,
    selectedPersonIds,
    onlySelectedPersons,
    anySelectedPersons,
    unusedFacesOnly,
    tagFilter,
    dupFilter,
    favouritesOnly,
  ]);

  const filtersKey = useMemo(
    () =>
      JSON.stringify({
        debouncedSearch,
        minFaces,
        selectedPersonIds,
        onlySelectedPersons,
        anySelectedPersons,
        unusedFacesOnly,
        tagFilter,
        dupFilter,
        favouritesOnly,
        galleryExtraFilters,
      }),
    [
      debouncedSearch,
      minFaces,
      selectedPersonIds,
      onlySelectedPersons,
      anySelectedPersons,
      unusedFacesOnly,
      tagFilter,
      dupFilter,
      favouritesOnly,
      galleryExtraFilters,
    ]
  );

  useEffect(() => {
    setPage(0);
  }, [filtersKey, sortKey]);

  useEffect(() => {
    setPage(0);
  }, [customPageSize]);

  useEffect(() => {
    if (!connected || lastMetaVersionRef.current === dataVersion) return;
    lastMetaVersionRef.current = dataVersion;
    setLoadingPersons(true);
    rpc<PersonRecord[]>("persons.list")
      .then(res => setPersons(res || []))
      .catch(() => {})
      .finally(() => setLoadingPersons(false));
    rpc<TagRecord[]>("tags.list", { limit: 80 })
      .then(res => setTags(res || []))
      .catch(() => {});
  }, [connected, dataVersion]);

  useEffect(() => {
    if (!connected) return;
    setLoading(true);
    const filters = buildFilters();
    loaderRef.current.run(
      () =>
        rpc<PhotosQueryResult>("photos.query", {
          filters,
          sort: sortKey,
          page,
          page_size: customPageSize,
        }),
      res => {
        setLoading(false);
        if (!res) return;
        if (res.person_gone) setSelectedPersonId(null);
        setItems(res.items || []);
        setTotal(res.total || 0);
        setPages(res.pages || 1);
        if (res.page !== page) setPage(res.page || 0);
      },
      err => {
        setLoading(false);
        notify(`Load failed: ${err.message}`, "error");
      }
    );
  }, [connected, filtersKey, sortKey, page, customPageSize, dataVersion, notify, setSelectedPersonId]);

  const handleSetDefaultFace = async (personId: number, faceId: number) => {
    try {
      await rpc("persons.set_cover", { person_id: personId, face_id: faceId });
      invalidate();
      notify("Updated person's default face.", "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  };

  const extraChipEntries = Object.entries(galleryExtraFilters || {}).filter(
    ([k]) => !k.startsWith("_")
  );
  const displayedItems = useMemo(() => {
    if (shuffleSeed === null || items.length <= 1) return items;
    const arr = [...items];
    let s = Math.floor(shuffleSeed * 2147483647) || 1;
    for (let i = arr.length - 1; i > 0; i--) {
      s = (s * 16807) % 2147483647;
      const j = s % (i + 1);
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }, [items, shuffleSeed]);

  const offset = page * customPageSize;

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="bg-card border border-subtle rounded-[6px] p-2.5 flex flex-col gap-2 shrink-0">
        {/* Row 1: Search + Primary Mode + Layout */}
        <div className="flex items-center flex-wrap gap-2">
          <div className="group relative flex-1 min-w-[180px]">
            <Search
              className="w-3.5 h-3.5 text-secondary group-focus-within:text-accent-secondary absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none transition-colors"
              strokeWidth={1.6}
            />
            <input
              ref={searchInputRef}
              type="text"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder="Search filename, person, place, date... (Ctrl+K)"
              className="w-full h-8 pl-8 pr-7 bg-input border border-hairline rounded-lg text-xs text-primary placeholder:text-secondary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30 transition-colors"
            />
            {searchText && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => setSearchText("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-secondary hover:text-accent-secondary transition-colors"
              >
                <X className="w-3.5 h-3.5" strokeWidth={1.6} />
              </button>
            )}
          </div>

          <div
            role="tablist"
            aria-label="Gallery view mode"
            className="inline-flex items-center bg-input border border-hairline h-8 rounded-lg px-0.5 gap-0.5 shrink-0"
          >
            <button
              type="button"
              role="tab"
              aria-selected={!unusedFacesOnly}
              onClick={() => setUnusedFacesOnly(false)}
              className={`h-6 px-2.5 inline-flex items-center gap-1 text-xs transition-colors cursor-pointer ${
                !unusedFacesOnly
                  ? "bg-accent-secondary-light text-accent-secondary rounded-l-md border border-accent-secondary/55 font-semibold"
                  : "text-secondary hover:text-primary hover:bg-elevated/60 border border-transparent font-medium"
              }`}
            >
              <span>All Photos</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={unusedFacesOnly}
              onClick={() => {
                setUnusedFacesOnly(true);
                setSelectedPersonId(null);
                setSelectedPersonIds([]);
                setOnlySelectedPersons(false);
                setTagFilter("");
                setGalleryExtraFilters({});
              }}
              title="Show photos with unassigned / unidentified faces"
              className={`h-6 px-2.5 inline-flex items-center gap-1 text-xs transition-colors cursor-pointer ${
                unusedFacesOnly
                  ? "bg-violet-bg text-violet border border-violet/60 font-semibold rounded-r-md"
                  : "text-secondary hover:text-primary hover:bg-elevated/60 border border-transparent font-medium"
              }`}
            >
              <UserRoundSearch className="w-3.5 h-3.5" strokeWidth={unusedFacesOnly ? 1.8 : 1.6} />
              <span>Unused Faces</span>
            </button>
          </div>

          <div
            role="group"
            aria-label="Gallery layout"
            className="inline-flex items-center bg-input border border-hairline rounded-lg h-8 px-0.5 gap-0.5 shrink-0"
          >
            {LAYOUT_BUTTONS.map(({ id, label, icon: Icon }) => {
              const active = layoutMode === id && customCols == null;
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => { setLayoutMode(id); setCustomCols(null); }}
                  className={`h-6 px-2 inline-flex items-center gap-1 rounded-[2px] text-xs transition-colors 
                    ${
                      (active
                      ? "bg-accent-secondary-light text-accent-secondary border border-accent-secondary/55 font-semibold"
                      : "text-secondary hover:text-primary hover:bg-elevated/60 border border-transparent font-medium")
                      + (layoutMode== "grid" ? " rounded-l-md" : layoutMode=="compact"? " rounded-none" : " rounded-r-md")     
                    }
                  `}
                >
                  <Icon className="w-3.5 h-3.5" strokeWidth={active ? 1.8 : 1.6} />
                  <span className="hidden sm:inline">{label}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => setControlsCollapsed(c => !c)}
            title={controlsCollapsed ? "Show filters, display & people controls" : "Collapse controls for more grid space"}
            className={`h-8 px-2.5 inline-flex items-center gap-1 rounded-lg border text-xs font-medium transition-colors shrink-0 cursor-pointer ${
              controlsCollapsed
                ? "bg-input border-hairline text-secondary hover:text-primary"
                : "bg-accent-secondary-light border-accent-secondary/55 text-accent-secondary"
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" strokeWidth={1.6} />
            {controlsCollapsed ? (
              <ChevronDown className="w-3.5 h-3.5" strokeWidth={1.6} />
            ) : (
              <ChevronUp className="w-3.5 h-3.5" strokeWidth={1.6} />
            )}
          </button>
        </div>

        {/* Row 2: Filters (left) + Display Controls (right) */}
        {!controlsCollapsed && (
        <div className="flex items-center justify-between flex-wrap gap-x-3 gap-y-2 pt-1.5 border-t border-subtle/60">
          <div className="flex items-center flex-wrap gap-1.5">
            <select
              value={dupFilter}
              onChange={e =>
                setDupFilter(e.target.value as "all" | "unique" | "duplicates" | "hidden")
              }
              className={`h-7 px-2 bg-input border rounded-xs text-xs text-primary focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber/30 ${
                dupFilter !== "all" ? "border-amber/70 text-amber" : "border-hairline"
              }`}
            >
              <option value="all">All Photos</option>
              <option value="unique">Unique Only</option>
              <option value="duplicates">Duplicates Only</option>
              <option value="hidden">Hidden Only</option>
            </select>

            <select
              value={sortKey}
              onChange={e => {
                setSortKey(e.target.value);
                setShuffleSeed(null);
              }}
              className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30"
            >
              {SORTS.map(s => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>

            {tags.length > 0 && (
              <select
                value={tagFilter}
                onChange={e => setTagFilter(e.target.value)}
                className={`h-7 px-2 bg-input border rounded-xs text-xs text-primary focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber/30 max-w-[150px] ${
                  tagFilter ? "border-amber/70 text-amber font-medium" : "border-hairline"
                }`}
              >
                <option value="">Any Tag</option>
                {tags.map(t => (
                  <option key={t.label} value={t.label}>
                    {t.label} ({t.count ?? 0})
                  </option>
                ))}
              </select>
            )}

            <label className="inline-flex items-center gap-1.5 text-xs text-secondary pl-1">
              <span>Faces ≥</span>
              <input
                type="number"
                min={0}
                max={20}
                value={minFaces}
                onChange={e => setMinFaces(Math.max(0, Math.min(20, Number(e.target.value) || 0)))}
                className={`w-12 h-7 px-1.5 bg-input border rounded-xs text-xs font-mono text-primary focus:outline-none focus:border-violet focus:ring-1 focus:ring-violet/30 ${
                  minFaces > 0 ? "border-violet/70 bg-violet-bg/40" : "border-hairline"
                }`}
              />
            </label>
          </div>

          <div className="flex items-center flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setFavouritesOnly(v => !v)}
              title="Show favourite photos only"
              className={`h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors cursor-pointer ${
                favouritesOnly
                  ? "bg-amber-bg border-amber text-amber font-semibold"
                  : "bg-input border-hairline text-secondary hover:text-primary hover:border-amber/50"
              }`}
            >
              <Star className={`w-3.5 h-3.5 ${favouritesOnly ? "fill-current" : ""}`} strokeWidth={1.6} />
              <span>Favourites</span>
            </button>

            <button
              type="button"
              onClick={() => setShuffleSeed(Math.random())}
              title="Shuffle photos on this page (change sort to restore order)"
              className={`h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors cursor-pointer ${
                shuffleSeed !== null
                  ? "bg-accent-secondary-light border-accent-secondary/55 text-accent-secondary"
                  : "bg-input border-hairline text-secondary hover:text-primary hover:border-accent-secondary/40"
              }`}
            >
              <Shuffle className="w-3.5 h-3.5" strokeWidth={1.6} />
              <span>Shuffle</span>
            </button>

            <button
              type="button"
              onClick={() => setFaceZoom(z => !z)}
              title="Crop each card to the largest detected face"
              className={`h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors ${
                faceZoom
                  ? "bg-violet-bg border-violet text-violet font-semibold"
                  : "bg-input border-hairline text-secondary hover:text-primary hover:border-violet/50"
              }`}
            >
              <ScanFace
                className={`w-3.5 h-3.5 ${faceZoom ? "text-violet" : ""}`}
                strokeWidth={1.6}
              />
              <span>Face Zoom</span>
            </button>

            <button
              type="button"
              title={showInfo ? "Hide file info" : "Show file info"}
              onClick={() => setShowInfo(v => !v)}
              className={`h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors ${
                showInfo
                  ? "bg-accent-secondary-light border-accent-secondary/55 text-accent-secondary"
                  : "bg-input border-hairline text-secondary hover:text-primary hover:border-accent-secondary/40"
              }`}
            >
              <FileText className="w-3.5 h-3.5" strokeWidth={1.6} />
              <span>Info</span>
            </button>

            <div className="h-4 w-px bg-subtle mx-0.5 hidden sm:block" />

            <div
              className="inline-flex items-center h-7 bg-input border border-hairline rounded-xs overflow-hidden text-xs"
              title="Columns per row (overrides Grid/Compact)"
            >
              <span className="px-1.5 text-secondary inline-flex items-center">
                <Columns3 className="w-3.5 h-3.5" strokeWidth={1.6} />
              </span>
              <button
                type="button"
                aria-label="Fewer columns"
                onClick={() => {
                  const cur = customCols ?? (layoutMode === "compact" ? 7 : 4);
                  setCustomCols(Math.max(2, cur - 1));
                }}
                className="w-6 h-full flex items-center justify-center text-secondary hover:text-primary hover:bg-elevated transition-colors cursor-pointer"
              >
                −
              </button>
              <span
                className={`px-1.5 font-mono text-[11px] tabular-nums select-none ${
                  customCols != null ? "text-accent-secondary font-semibold" : "text-secondary"
                }`}
              >
                {customCols != null ? `${customCols} col` : "Auto"}
              </span>
              <button
                type="button"
                aria-label="More columns"
                onClick={() => {
                  const cur = customCols ?? (layoutMode === "compact" ? 7 : 4);
                  setCustomCols(Math.min(12, cur + 1));
                }}
                className="w-6 h-full flex items-center justify-center text-secondary hover:text-primary hover:bg-elevated transition-colors cursor-pointer"
              >
                +
              </button>
              {customCols != null && (
                <button
                  type="button"
                  title="Reset to auto"
                  onClick={() => setCustomCols(null)}
                  className="w-6 h-full flex items-center justify-center text-secondary hover:text-accent-secondary border-l border-subtle hover:bg-elevated transition-colors cursor-pointer"
                >
                  <X className="w-3 h-3" strokeWidth={1.8} />
                </button>
              )}
            </div>

            <label className="inline-flex items-center gap-1 text-xs text-secondary" title="Photos per page">
              <span className="hidden md:inline">Per page</span>
              <input
                type="number"
                min={10}
                max={200}
                step={10}
                value={customPageSize}
                onChange={e => {
                  const v = Math.max(10, Math.min(200, Number(e.target.value) || 40));
                  setCustomPageSize(v);
                }}
                className="w-14 h-7 px-1.5 bg-input border border-hairline rounded-xs text-xs font-mono text-primary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30"
              />
            </label>
          </div>
        </div>
        )}

        {/* Row 3: Active Filter Chips (only shown when active) */}
        {(tagFilter || extraChipEntries.length > 0) && (
          <div className="flex items-center flex-wrap gap-1.5 pt-1 border-t border-subtle/40">
            {tagFilter && (
              <span className="h-6 px-2 inline-flex items-center gap-1.5 rounded-xs bg-amber-bg border border-amber/50 text-xs text-amber font-medium">
                <Tag className="w-3 h-3 shrink-0" strokeWidth={1.8} />
                <span>tag: {tagFilter}</span>
                <button
                  type="button"
                  aria-label="Clear tag filter"
                  onClick={() => setTagFilter("")}
                  className="text-amber hover:text-primary transition-colors cursor-pointer"
                >
                  <X className="w-3 h-3" strokeWidth={1.8} />
                </button>
              </span>
            )}

            {extraChipEntries.map(([k, v]) => (
              <span
                key={k}
                className={`h-6 px-2 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium ${
                  k === "tag"
                    ? "bg-amber-bg border-amber/50 text-amber"
                    : "bg-accent-light border-accent/50 text-accent"
                }`}
              >
                {k === "tag" && <Tag className="w-3 h-3 shrink-0" strokeWidth={1.8} />}
                <span>
                  {k === "group_id"
                    ? String(galleryExtraFilters._group_label || `Event #${v}`)
                    : `${k}: ${String(v)}`}
                </span>
                <button
                  type="button"
                  aria-label="Remove filter"
                  onClick={() => {
                    const next = { ...galleryExtraFilters };
                    delete next[k];
                    if (k === "group_id") delete next._group_label;
                    setGalleryExtraFilters(next);
                  }}
                  className={`${k === "tag" ? "text-amber" : "text-accent"} hover:text-primary transition-colors cursor-pointer`}
                >
                  <X className="w-3 h-3" strokeWidth={1.8} />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {!controlsCollapsed && !unusedFacesOnly && (
        <PeopleStrip
          persons={persons}
          loading={loadingPersons}
          selectedPersonIds={selectedPersonIds}
          onTogglePerson={pid => {
            const next = selectedPersonIds.includes(pid)
              ? selectedPersonIds.filter(id => id !== pid)
              : [...selectedPersonIds, pid];
            setSelectedPersonIds(next);
            setSelectedPersonId(next.length === 1 ? next[0] : null);
          }}
          onSelectSinglePerson={pid => {
            setSelectedPersonIds([pid]);
            setSelectedPersonId(pid);
          }}
          onClearPersons={() => {
            setSelectedPersonIds([]);
            setSelectedPersonId(null);
            setOnlySelectedPersons(false);
          }}
          onlySelectedPersons={onlySelectedPersons}
          onToggleOnlySelected={() => setOnlySelectedPersons(v => !v)}
          anySelectedPersons={anySelectedPersons}
          onToggleAnySelected={() => setAnySelectedPersons(v => !v)}
        />
      )}

      {items.length === 0 && !loading ? (
        <EmptyState
          icon={Images}
          title="No Photos Found"
          description={
            connected
              ? "Adjust your search query, person filter, or scan a photo folder to index media."
              : "Connect your Python backend to browse indexed photos."
          }
        />
      ) : layoutMode === "table" ? (
        <PhotoTable
          photos={displayedItems}
          onOpen={p => {
            setLightboxList(displayedItems);
            setLightboxPhoto(p);
          }}
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 [scrollbar-gutter:stable]">
          <div
            className={`grid items-start ${
              customCols != null
                ? "gap-2"
                : layoutMode === "compact"
                  ? "grid-cols-[repeat(auto-fill,minmax(154px,1fr))] gap-2"
                  : "grid-cols-[repeat(auto-fill,minmax(204px,1fr))] gap-3"
            }`}
            style={customCols != null ? { gridTemplateColumns: `repeat(${customCols}, minmax(0, 1fr))` } : undefined}
          >
            {displayedItems.map(item => (
              <PhotoCard
                key={item.id}
                photo={item}
                compact={customCols != null ? false : layoutMode === "compact"}
                faceZoom={faceZoom}
                targetPersonId={selectedPersonIds.length === 1 ? selectedPersonIds[0] : null}
                unassignedOnly={unusedFacesOnly}
                showInfo={showInfo}
                onOpen={p => {
                  setLightboxList(displayedItems);
                  setLightboxPhoto(p);
                }}
                onSetDefaultFace={
                  selectedPersonIds.length === 1 && !unusedFacesOnly ? handleSetDefaultFace : undefined
                }
              />
            ))}
          </div>
        </div>
      )}

      <div className="bg-card border border-subtle rounded-sm px-3 py-1.5 flex items-center justify-between shrink-0">
        <span className="text-xs text-secondary font-mono tabular-nums inline-flex items-center gap-1.5">
          {loading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />
              <span className="text-accent-secondary font-medium">Loading photos...</span>
            </>
          ) : items.length ? (
            `Showing ${offset + 1}-${offset + items.length} of ${total.toLocaleString()} photos`
          ) : (
            "No photos matched"
          )}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={page <= 0}
            onClick={() => setPage(p => Math.max(0, p - 1))}
            className="btn-neutral h-7 px-2 text-xs"
          >
            <ChevronLeft className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Prev</span>
          </button>
          <span className="text-xs font-mono text-secondary px-2 tabular-nums">
            Page {page + 1} / {pages}
          </span>
          <button
            type="button"
            disabled={page + 1 >= pages}
            onClick={() => setPage(p => Math.min(pages - 1, p + 1))}
            className="btn-neutral h-7 px-2 text-xs"
          >
            <span>Next</span>
            <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.6} />
          </button>
        </div>
      </div>
    </div>
  );
}
