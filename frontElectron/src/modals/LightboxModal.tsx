import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent, PointerEvent } from 'react';
import {
  Calendar,
  Eye,
  EyeOff,
  FolderOpen,
  Maximize,
  Play,
  RotateCcw,
  ScanFace,
  Sparkles,
  Star,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { mediaUrl, revealFile, rpc } from '../lib/api';
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
    rpc<PersonRecord[]>('persons.list').then((res) => setPersons(res || [])).catch(() => {});
  };

  const handleNameFace = async () => {
    if (!activeFace || !faceNameInput.trim()) return;
    try {
      await rpc('faces.name', { face_id: activeFace.id, name: faceNameInput.trim() });
      dirtyRef.current = true;
      setActiveFace(null);
      notify('Face named.', 'success');
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const handleAssignFace = async (personId: number | null) => {
    if (!activeFace) return;
    try {
      await rpc('faces.assign', { face_id: activeFace.id, person_id: personId });
      dirtyRef.current = true;
      setActiveFace(null);
      notify(personId === null ? 'Removed face from person.' : 'Face assigned.', 'success');
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const toggleMark = async (kind: 'favourite' | 'hidden') => {
    try {
      const res = await rpc<{ marks?: string[] }>('photos.toggle_mark', { image_id: photo.id, kind });
      setMarks(res.marks || []);
      dirtyRef.current = true;
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
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
    try {
      const res = await rpc<{ effective_ts?: string | null }>('photos.clear_date', { image_id: photo.id });
      setPhoto((p) => ({ ...p, effective_ts: res.effective_ts }));
      dirtyRef.current = true;
      notify('Original date restored.', 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const isFav = marks.includes('favourite');
  const isHidden = marks.includes('hidden');
  const origW = Number(photo.width || 1);
  const origH = Number(photo.height || 1);

  return (
    <>
      <ModalShell
        title={basename(photo.path) || `Photo #${photo.id}`}
        subtitle={photo.path}
        size="xl"
        noPadding
        onClose={handleClose}
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
              onWheel={(e) => { e.preventDefault(); stepZoom(e.deltaY < 0 ? 1.15 : 1 / 1.15); }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
              className="flex-1 min-h-0 relative overflow-hidden flex items-center justify-center cursor-grab active:cursor-grabbing"
            >
              <div style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }} className="relative inline-block origin-center">
                <img src={imgSrc} alt={basename(photo.path)} draggable={false} className="block max-w-[74vw] max-h-[72vh] select-none pointer-events-none" />
                {showFaces && (
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
                          className={`absolute pointer-events-auto cursor-pointer border-2 border-accent ${
                            label ? 'bg-accent/15' : 'border-dashed bg-transparent'
                          }`}
                        >
                          {label && (
                            <span className="absolute left-1/2 top-full mt-1 -translate-x-1/2 px-1.5 py-0.5 bg-sidebar border border-hairline rounded-[2px] text-[10.5px] font-semibold text-primary whitespace-nowrap">
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
                <div className="text-[11px] font-semibold text-primary">Manage Face #{activeFace.id}</div>
                <div className="flex gap-1">
                  <input
                    type="text"
                    value={faceNameInput}
                    onChange={(e) => setFaceNameInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleNameFace(); }}
                    placeholder="Person name..."
                    className="flex-1 h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
                  />
                  <button type="button" onClick={handleNameFace} className="h-7 px-2 bg-accent text-accent-text rounded-xs text-xs">
                    Save
                  </button>
                </div>
                {persons.length > 0 && (
                  <select
                    defaultValue=""
                    onChange={(e) => { if (e.target.value) handleAssignFace(Number(e.target.value)); }}
                    className="h-7 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
                  >
                    <option value="">Assign to existing person...</option>
                    {persons.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.image_count || 0})</option>)}
                  </select>
                )}
                <div className="flex justify-between">
                  <button type="button" onClick={() => handleAssignFace(null)} className="text-xs text-danger hover:underline">
                    Remove from person
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
                onClick={() => toggleMark('favourite')}
                className={`h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs text-xs font-medium ${
                  isFav ? 'bg-accent text-accent-text' : 'bg-elevated border border-hairline text-primary hover:border-accent'
                }`}
              >
                <Star className="w-3.5 h-3.5" strokeWidth={1.7} />
                <span>{isFav ? 'Remove Favourite' : 'Mark as Favourite'}</span>
              </button>
              <button type="button" onClick={() => toggleMark('hidden')} className="h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                {isHidden ? <Eye className="w-3.5 h-3.5" strokeWidth={1.6} /> : <EyeOff className="w-3.5 h-3.5" strokeWidth={1.6} />}
                <span>{isHidden ? 'Unhide Photo' : 'Hide Photo'}</span>
              </button>
              <div className="grid grid-cols-2 gap-1.5">
                <button type="button" onClick={() => setShowDateModal(true)} className="h-8 px-2 inline-flex items-center justify-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                  <Calendar className="w-3.5 h-3.5" strokeWidth={1.6} />
                  <span>Correct Date</span>
                </button>
                <button type="button" onClick={handleRestoreDate} className="h-8 px-2 inline-flex items-center justify-center gap-1 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                  <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.6} />
                  <span>Restore</span>
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
                <button type="button" onClick={() => revealFile(photo.path as string)} className="h-8 px-3 inline-flex items-center justify-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-secondary hover:text-primary hover:bg-elevated">
                  <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.6} />
                  <span>Reveal in Folder</span>
                </button>
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
