import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent, PointerEvent } from 'react';
import {
  Calendar,
  ExternalLink,
  Eye,
  EyeOff,
  FolderOpen,
  Fullscreen,
  Loader2,
  Maximize,
  Minimize,
  Minimize2,
  Play,
  RotateCcw,
  ScanFace,
  Sparkles,
  Star,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { mediaUrl, openFile, revealFile, rpc } from '../lib/api';
import { basename, faceDisplayName, formatDate, formatDims, formatQuality, needsBackendDecode } from '../lib/utils';
import type { FaceRecord, PersonRecord, PhotoRecord, TagRecord } from '../types/memoframe';
import ModalShell from '../components/ModalShell';
import { DateOverrideModal } from './DateModals';
import { LivePhotoModal, SimilarPhotosModal } from './UtilityModals';

interface PhotoDetailResponse {
  photo: PhotoRecord;
  faces: FaceRecord[];
  tags: TagRecord[];
  marks: string[];
  live_video?: { path: string } | null;
  thumb_path?: string | null;
}

interface LightboxModalProps {
  photo: PhotoRecord;
  onClose?: () => void;
}

export default function LightboxModal({ photo: initialPhoto, onClose }: LightboxModalProps) {
  const { invalidate, notify, setLightboxPhoto } = useApp();
  const [photo, setPhoto] = useState<PhotoRecord>(initialPhoto);
  const [faces, setFaces] = useState<FaceRecord[]>(initialPhoto.faces || []);
  const [tags, setTags] = useState<TagRecord[]>([]);
  const [marks, setMarks] = useState<string[]>([]);
  const [liveVideo, setLiveVideo] = useState<{ path: string } | null>(null);
  const [imgSrc, setImgSrc] = useState<string>(mediaUrl(initialPhoto.thumb_path || initialPhoto.path));
  const [showFaces, setShowFaces] = useState(true);

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef({ active: false, moved: false, startX: 0, startY: 0, origX: 0, origY: 0 });
  const dirtyRef = useRef(false);

  const [activeFace, setActiveFace] = useState<FaceRecord | null>(null);
  const [faceNameInput, setFaceNameInput] = useState('');
  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [showDateModal, setShowDateModal] = useState(false);
  const [showSimilar, setShowSimilar] = useState(false);
  const [showLive, setShowLive] = useState(false);
  const [modalMode, setModalMode] = useState<'normal' | 'maximized' | 'fullscreen'>('normal');
  const [openingDefaultApp, setOpeningDefaultApp] = useState(false);

  const toggleMaximize = () => {
    setModalMode((prev) => (prev === 'maximized' ? 'normal' : 'maximized'));
  };

  const toggleFullscreen = () => {
    setModalMode((prev) => (prev === 'fullscreen' ? 'normal' : 'fullscreen'));
  };

  const handleOpenInDefaultApp = async () => {
    if (!photo.path || openingDefaultApp) return;
    setOpeningDefaultApp(true);
    try {
      const ok = await openFile(photo.path);
      if (!ok) {
        notify('Could not open file in default application.', 'error');
      } else {
        notify('Opened photo in default viewer.', 'success');
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setOpeningDefaultApp(false);
    }
  };

  const [savingFaceName, setSavingFaceName] = useState(false);
  const [assigningFace, setAssigningFace] = useState(false);
  const [togglingMark, setTogglingMark] = useState<'favourite' | 'hidden' | null>(null);
  const [restoringDate, setRestoringDate] = useState(false);

  const loadDetail = useCallback(async () => {
    try {
      const d = await rpc<PhotoDetailResponse>('photos.detail', { image_id: initialPhoto.id });
      if (d?.photo) setPhoto((prev) => ({ ...prev, ...d.photo }));
      setFaces(d?.faces || []);
      setTags(d?.tags || []);
      setMarks(d?.marks || []);
      setLiveVideo(d?.live_video || null);

      const fullPath = d?.photo?.path || initialPhoto.path;
      if (fullPath && needsBackendDecode(fullPath)) {
        const decoded = await rpc<{ data_url?: string | null }>('photos.decode', { path: fullPath, max_side: 2400 });
        if (decoded?.data_url) setImgSrc(decoded.data_url);
      } else if (fullPath) {
        setImgSrc(mediaUrl(fullPath));
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  }, [initialPhoto.id, initialPhoto.path, notify]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  const handleClose = () => {
    if (dirtyRef.current) invalidate();
    onClose?.();
  };

  const stepZoom = (factor: number) => setZoom((z) => Math.max(0.25, Math.min(8, Number((z * factor).toFixed(3)))));
  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    dragRef.current = { active: true, moved: false, startX: e.clientX, startY: e.clientY, origX: pan.x, origY: pan.y };
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    if (Math.hypot(dx, dy) > 4) dragRef.current.moved = true;
    setPan({ x: dragRef.current.origX + dx, y: dragRef.current.origY + dy });
  };

  const onPointerUp = () => { dragRef.current.active = false; };

  const onFaceClick = (e: MouseEvent<HTMLDivElement>, face: FaceRecord) => {
    e.stopPropagation();
    if (dragRef.current.moved) return;
    setActiveFace(face);
    setFaceNameInput(face.person_name || '');
    zoomToFace(face);
    rpc<PersonRecord[]>('persons.list').then((res) => setPersons(res || [])).catch(() => {});
  };

  const handleNameFace = async () => {
    if (!activeFace || !faceNameInput.trim() || savingFaceName) return;
    setSavingFaceName(true);
    try {
      await rpc('faces.name', { face_id: activeFace.id, name: faceNameInput.trim() });
      dirtyRef.current = true;
      setActiveFace(null);
      notify('Face named.', 'success');
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setSavingFaceName(false);
    }
  };

  const handleAssignFace = async (personId: number | null) => {
    if (!activeFace || assigningFace) return;
    setAssigningFace(true);
    try {
      await rpc('faces.assign', { face_id: activeFace.id, person_id: personId });
      dirtyRef.current = true;
      setActiveFace(null);
      notify(personId === null ? 'Removed face from person.' : 'Face assigned.', 'success');
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setAssigningFace(false);
    }
  };

  const toggleMark = async (kind: 'favourite' | 'hidden') => {
    if (togglingMark) return;
    setTogglingMark(kind);
    try {
      const res = await rpc<{ marks?: string[] }>('photos.toggle_mark', { image_id: photo.id, kind });
      setMarks(res.marks || []);
      dirtyRef.current = true;
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setTogglingMark(null);
    }
  };

  const handleDateSave = async (iso: string) => {
    try {
      await rpc('photos.set_date', { image_id: photo.id, iso, reason: 'manual (lightbox)' });
      setPhoto((p) => ({ ...p, effective_ts: iso }));
      dirtyRef.current = true;
      setShowDateModal(false);
      notify('Photo date updated.', 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const handleRestoreDate = async () => {
    if (restoringDate) return;
    setRestoringDate(true);
    try {
      const res = await rpc<{ effective_ts?: string | null }>('photos.clear_date', { image_id: photo.id });
      setPhoto((p) => ({ ...p, effective_ts: res.effective_ts }));
      dirtyRef.current = true;
      notify('Original date restored.', 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setRestoringDate(false);
    }
  };

  // Attach wheel listener as non-passive to allow e.preventDefault() for smooth zoom
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      stepZoom(e.deltaY < 0 ? 1.15 : 1 / 1.15);
    };
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', handleWheel);
    };
  }, [stepZoom]);

  const [renderedDims, setRenderedDims] = useState<{ width: number; height: number; naturalWidth: number; naturalHeight: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);

  // Observe viewportRef size so image naturally calculates fit and renderedDims without circular collapse
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;

    const updateDims = () => {
      const vw = vp.clientWidth - 16; // subtract padding
      const vh = vp.clientHeight - 16;
      const naturalW = imgRef.current?.naturalWidth || Number(photo.width || 1);
      const naturalH = imgRef.current?.naturalHeight || Number(photo.height || 1);

      if (vw > 0 && vh > 0 && naturalW > 0 && naturalH > 0) {
        // Fit within viewport preserving aspect ratio
        const scale = Math.min(vw / naturalW, vh / naturalH);
        const w = Math.round(naturalW * scale);
        const h = Math.round(naturalH * scale);
        setRenderedDims({
          width: Math.max(1, w),
          height: Math.max(1, h),
          naturalWidth: naturalW,
          naturalHeight: naturalH,
        });
      }
    };

    updateDims();
    const observer = new ResizeObserver(updateDims);
    observer.observe(vp);
    return () => observer.disconnect();
  }, [photo.width, photo.height, imgSrc, modalMode]);

  const zoomToFace = useCallback((face: FaceRecord) => {
    const origW = renderedDims?.naturalWidth || Number(photo.width || 1);
    const origH = renderedDims?.naturalHeight || Number(photo.height || 1);
    const faceW = Number(face.w || 0);
    const faceH = Number(face.h || 0);
    if (!origW || !origH || !faceW || !faceH) return;

    // Face center in normalized coordinates [-0.5 .. 0.5] from image center
    const faceCx = Number(face.x || 0) + faceW / 2;
    const faceCy = Number(face.y || 0) + faceH / 2;
    const normX = faceCx / origW - 0.5;
    const normY = faceCy / origH - 0.5;

    // Determine target zoom so that the face occupies a comfortable portion (~35-40%) of viewport
    const faceFraction = Math.max(faceW / origW, faceH / origH);
    const targetZoom = Math.max(1.8, Math.min(5, 0.4 / Math.max(0.05, faceFraction)));

    // Image rendered size
    const imgW = renderedDims?.width || 800;
    const imgH = renderedDims?.height || 600;

    // In a scale(targetZoom) around center, the point at normX*imgW moves to normX*imgW*targetZoom.
    // To bring this point to viewport center (0, 0), we pan by: -normX * imgW * targetZoom
    const panX = -normX * imgW * targetZoom;
    const panY = -normY * imgH * targetZoom;

    setZoom(Number(targetZoom.toFixed(2)));
    setPan({ x: Math.round(panX), y: Math.round(panY) });
  }, [renderedDims, photo.width, photo.height]);

  const isFav = marks.includes('favourite');
  const isHidden = marks.includes('hidden');
  const origW = renderedDims?.naturalWidth || Number(photo.width || 1);
  const origH = renderedDims?.naturalHeight || Number(photo.height || 1);

  // Dynamic styling based on modalMode
  const modalContainerClass =
    modalMode === 'fullscreen'
      ? 'w-screen h-screen max-w-none max-h-none rounded-none border-0'
      : modalMode === 'maximized'
      ? 'w-[98vw] h-[96vh] max-w-none max-h-none rounded-xs'
      : 'w-[1160px] h-[86vh] max-w-[96vw] max-h-[92vh] rounded-sm';

  const modalBackdropClass = modalMode === 'fullscreen' ? 'p-0' : 'p-3 md:p-5';

  return (
    <>
      <ModalShell
        title={basename(photo.path) || `Photo #${photo.id}`}
        subtitle={photo.path}
        noPadding
        className={modalContainerClass}
        backdropClassName={modalBackdropClass}
        onClose={handleClose}
        headerExtra={
          <div className="flex items-center gap-1 border-r border-subtle pr-1.5 mr-0.5">
            {photo.path && (
              <button
                type="button"
                title="Open in Default Application"
                disabled={openingDefaultApp}
                onClick={handleOpenInDefaultApp}
                className="w-7 h-7 flex items-center justify-center rounded-xs text-secondary hover:text-primary hover:bg-elevated transition-colors disabled:opacity-50"
              >
                {openingDefaultApp ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
                ) : (
                  <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.6} />
                )}
              </button>
            )}
            <button
              type="button"
              title={modalMode === 'maximized' ? 'Restore window size' : 'Maximize modal window'}
              onClick={toggleMaximize}
              className={`w-7 h-7 flex items-center justify-center rounded-xs transition-colors ${
                modalMode === 'maximized'
                  ? 'bg-accent-light text-accent border border-accent'
                  : 'text-secondary hover:text-primary hover:bg-elevated'
              }`}
            >
              {modalMode === 'maximized' ? (
                <Minimize className="w-3.5 h-3.5" strokeWidth={1.6} />
              ) : (
                <Maximize className="w-3.5 h-3.5" strokeWidth={1.6} />
              )}
            </button>
            <button
              type="button"
              title={modalMode === 'fullscreen' ? 'Exit fullscreen (Esc)' : 'Enter fullscreen view'}
              onClick={toggleFullscreen}
              className={`w-7 h-7 flex items-center justify-center rounded-xs transition-colors ${
                modalMode === 'fullscreen'
                  ? 'bg-accent-light text-accent border border-accent'
                  : 'text-secondary hover:text-primary hover:bg-elevated'
              }`}
            >
              {modalMode === 'fullscreen' ? (
                <Minimize2 className="w-3.5 h-3.5" strokeWidth={1.6} />
              ) : (
                <Fullscreen className="w-3.5 h-3.5" strokeWidth={1.6} />
              )}
            </button>
          </div>
        }
      >
        <div className="flex-1 min-h-0 flex overflow-hidden">
          <div className="flex-1 min-w-0 flex flex-col bg-app">
            <div className="px-3 py-2 bg-sidebar border-b border-subtle flex items-center justify-between gap-2 shrink-0">
              <div className="flex items-center gap-1.5">
                <button type="button" title="Zoom Out" onClick={() => stepZoom(1 / 1.2)} className="h-7 w-7 inline-flex items-center justify-center rounded-xs border border-hairline bg-card text-primary hover:bg-elevated">
                  <ZoomOut className="w-3.5 h-3.5" strokeWidth={1.6} />
                </button>
                <span className="font-mono text-xs text-secondary w-11 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
                <button type="button" title="Zoom In" onClick={() => stepZoom(1.2)} className="h-7 w-7 inline-flex items-center justify-center rounded-xs border border-hairline bg-card text-primary hover:bg-elevated">
                  <ZoomIn className="w-3.5 h-3.5" strokeWidth={1.6} />
                </button>
                <button type="button" onClick={resetView} className="h-7 px-2 inline-flex items-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                  <Maximize className="w-3 h-3" strokeWidth={1.6} />
                  <span>Fit</span>
                </button>
              </div>
              <button
                type="button"
                onClick={() => setShowFaces((v) => !v)}
                className={`h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs ${
                  showFaces ? 'bg-accent-light border-accent text-primary' : 'bg-card border-hairline text-secondary'
                }`}
              >
                <ScanFace className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>Face Boxes ({faces.length})</span>
              </button>
            </div>

            <div
              ref={viewportRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
              className="flex-1 min-h-0 relative overflow-hidden flex items-center justify-center cursor-grab active:cursor-grabbing p-2"
            >
              <div
                style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                  width: renderedDims ? `${renderedDims.width}px` : 'auto',
                  height: renderedDims ? `${renderedDims.height}px` : 'auto',
                }}
                className="relative inline-flex items-center justify-center origin-center shrink-0 transition-transform duration-200 ease-out"
              >
                <img
                  ref={imgRef}
                  src={imgSrc}
                  alt={basename(photo.path)}
                  draggable={false}
                  onLoad={() => {
                    const vp = viewportRef.current;
                    const img = imgRef.current;
                    if (!vp || !img) return;
                    const vw = vp.clientWidth - 16;
                    const vh = vp.clientHeight - 16;
                    const naturalW = img.naturalWidth || Number(photo.width || 1);
                    const naturalH = img.naturalHeight || Number(photo.height || 1);
                    if (vw > 0 && vh > 0 && naturalW > 0 && naturalH > 0) {
                      const scale = Math.min(vw / naturalW, vh / naturalH);
                      setRenderedDims({
                        width: Math.round(naturalW * scale),
                        height: Math.round(naturalH * scale),
                        naturalWidth: naturalW,
                        naturalHeight: naturalH,
                      });
                    }
                  }}
                  className="w-full h-full object-contain select-none pointer-events-none"
                />
                {showFaces && renderedDims && (
                  <div className="absolute inset-0 pointer-events-none">
                    {faces.map((f) => {
                      const label = faceDisplayName(f);
                      const style = {
                        left: `${(Number(f.x || 0) / origW) * 100}%`,
                        top: `${(Number(f.y || 0) / origH) * 100}%`,
                        width: `${(Number(f.w || 0) / origW) * 100}%`,
                        height: `${(Number(f.h || 0) / origH) * 100}%`,
                      };
                      return (
                        <div
                          key={f.id}
                          style={style}
                          title={label ? `${label} (Click to manage)` : 'Click to name this face'}
                          onClick={(e) => onFaceClick(e, f)}
                          className={`absolute pointer-events-auto cursor-pointer border-2 border-accent transition-colors ${
                            label ? 'bg-accent/20 border-solid shadow-sm' : 'border-dashed bg-transparent hover:bg-accent/10'
                          }`}
                        >
                          {label && (
                            <span className="absolute left-1/2 bottom-full mb-1 -translate-x-1/2 px-1.5 py-0.5 bg-sidebar/95 border border-hairline bg-[var(--border)] rounded-[2px] text-[10.5px] font-semibold text-primary whitespace-nowrap shadow-sm pointer-events-none">
                              {label}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>

          <aside className="w-[300px] shrink-0 border-l border-subtle bg-card p-3.5 flex flex-col gap-3 overflow-y-auto">
            <div className="flex flex-col gap-2.5 flex-1">
              {[
                ['Date Taken', formatDate(photo.effective_ts || photo.exif_ts)],
                ['Resolution', formatDims(photo.width, photo.height)],
                ['Format', String(photo.format || 'Unknown').toUpperCase()],
                ['Faces Detected', String(faces.length)],
                ['Quality Score', formatQuality(photo.quality)],
                ['Tags', tags.map((t) => t.label).join(', ') || '—'],
                ['File Path', photo.path || '—'],
              ].map(([k, v]) => (
                <div key={k}>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-secondary">{k}</div>
                  <div className="text-xs text-primary break-words mt-0.5 select-text">{v}</div>
                </div>
              ))}
            </div>

            {activeFace && (
              <div className="p-2.5 bg-elevated border border-accent rounded-xs flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-primary">Manage Face #{activeFace.id}</span>
                  <button
                    type="button"
                    onClick={() => zoomToFace(activeFace)}
                    className="text-[11px] text-accent hover:underline inline-flex items-center gap-1"
                  >
                    <ZoomIn className="w-3 h-3" />
                    <span>Zoom to Face</span>
                  </button>
                </div>
                <div className="flex gap-1">
                  <input
                    type="text"
                    value={faceNameInput}
                    disabled={savingFaceName}
                    onChange={(e) => setFaceNameInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleNameFace(); }}
                    placeholder="Person name..."
                    className="flex-1 h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary disabled:opacity-50"
                  />
                  <button
                    type="button"
                    disabled={savingFaceName || !faceNameInput.trim()}
                    onClick={handleNameFace}
                    className="h-7 px-2 bg-accent text-accent-text rounded-xs text-xs disabled:opacity-50"
                  >
                    {savingFaceName ? 'Saving...' : 'Save'}
                  </button>
                </div>
                {persons.length > 0 && (
                  <select
                    defaultValue=""
                    disabled={assigningFace}
                    onChange={(e) => { if (e.target.value) handleAssignFace(Number(e.target.value)); }}
                    className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary disabled:opacity-50"
                  >
                    <option value="">{assigningFace ? 'Assigning...' : 'Assign to existing person...'}</option>
                    {persons.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.image_count || 0})</option>)}
                  </select>
                )}
                <div className="flex justify-between">
                  <button
                    type="button"
                    disabled={assigningFace}
                    onClick={() => handleAssignFace(null)}
                    className="text-xs text-danger hover:underline disabled:opacity-50"
                  >
                    {assigningFace ? 'Updating...' : 'Remove from person'}
                  </button>
                  <button type="button" onClick={() => setActiveFace(null)} className="text-xs text-secondary hover:text-primary">
                    Done
                  </button>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5 pt-2 border-t border-subtle">
              <button
                type="button"
                disabled={togglingMark !== null}
                onClick={() => toggleMark('favourite')}
                className={`h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs text-xs font-medium disabled:opacity-50 ${
                  isFav ? 'bg-accent text-accent-text' : 'bg-elevated border border-hairline text-primary hover:border-accent'
                }`}
              >
                <Star className="w-3.5 h-3.5" strokeWidth={1.7} />
                <span>{togglingMark === 'favourite' ? 'Updating...' : isFav ? 'Remove Favourite' : 'Mark as Favourite'}</span>
              </button>
              <button
                type="button"
                disabled={togglingMark !== null}
                onClick={() => toggleMark('hidden')}
                className="h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-50"
              >
                {isHidden ? <Eye className="w-3.5 h-3.5" strokeWidth={1.6} /> : <EyeOff className="w-3.5 h-3.5" strokeWidth={1.6} />}
                <span>{togglingMark === 'hidden' ? 'Updating...' : isHidden ? 'Unhide Photo' : 'Hide Photo'}</span>
              </button>
              <div className="grid grid-cols-2 gap-1.5">
                <button type="button" onClick={() => setShowDateModal(true)} className="h-8 px-2 inline-flex items-center justify-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                  <Calendar className="w-3.5 h-3.5" strokeWidth={1.6} />
                  <span>Correct Date</span>
                </button>
                <button
                  type="button"
                  disabled={restoringDate}
                  onClick={handleRestoreDate}
                  className="h-8 px-2 inline-flex items-center justify-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-50"
                >
                  <RotateCcw className={`w-3.5 h-3.5 ${restoringDate ? 'animate-spin' : ''}`} strokeWidth={1.6} />
                  <span>{restoringDate ? 'Restoring...' : 'Restore'}</span>
                </button>
              </div>
              <button type="button" onClick={() => setShowSimilar(true)} className="h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                <Sparkles className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>Find Similar</span>
              </button>
              {liveVideo && (
                <button type="button" onClick={() => setShowLive(true)} className="h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover">
                  <Play className="w-3.5 h-3.5" strokeWidth={1.7} />
                  <span>Play Live Photo</span>
                </button>
              )}
              {photo.path && (
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    disabled={openingDefaultApp}
                    onClick={handleOpenInDefaultApp}
                    className="h-8 px-2 inline-flex items-center justify-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-50 transition-colors"
                  >
                    {openingDefaultApp ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
                    ) : (
                      <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.6} />
                    )}
                    <span>Default App</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => revealFile(photo.path as string)}
                    className="h-8 px-2 inline-flex items-center justify-center gap-1 rounded-xs border border-hairline bg-card text-xs text-secondary hover:text-primary hover:bg-elevated transition-colors"
                  >
                    <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.6} />
                    <span>In Folder</span>
                  </button>
                </div>
              )}
            </div>
          </aside>
        </div>
      </ModalShell>

      {showDateModal && (
        <DateOverrideModal currentIso={photo.effective_ts || photo.exif_ts} onClose={() => setShowDateModal(false)} onSave={handleDateSave} />
      )}
      {showSimilar && (
        <SimilarPhotosModal imageId={photo.id} onClose={() => setShowSimilar(false)} onOpenPhoto={(p) => { setShowSimilar(false); setLightboxPhoto(p); }} />
      )}
      {showLive && liveVideo && <LivePhotoModal videoPath={liveVideo.path} onClose={() => setShowLive(false)} />}
    </>
  );
}
