import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, PointerEvent } from "react";
import {
  ExternalLink,
  Fullscreen,
  Loader2,
  Maximize,
  Minimize,
  Minimize2,
  ScanFace,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { mediaUrl, openFile, revealFile, rpc } from "../lib/api";
import { basename, faceDisplayName, needsBackendDecode } from "../lib/utils";
import type { FaceRecord, PersonRecord, PhotoRecord, TagRecord } from "../types/memoframe";
import ModalShell from "../components/ModalShell";
import { DateOverrideModal } from "./DateModals";
import { LivePhotoModal, SimilarPhotosModal } from "./UtilityModals";
import LightboxSidebar from "./LightboxSidebar";

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
  const [imgSrc, setImgSrc] = useState<string>(
    mediaUrl(initialPhoto.thumb_path || initialPhoto.path)
  );
  const [showFaces, setShowFaces] = useState(true);

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef({ active: false, moved: false, startX: 0, startY: 0, origX: 0, origY: 0 });
  const dirtyRef = useRef(false);

  const [activeFace, setActiveFace] = useState<FaceRecord | null>(null);
  const [faceNameInput, setFaceNameInput] = useState("");
  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [showDateModal, setShowDateModal] = useState(false);
  const [showSimilar, setShowSimilar] = useState(false);
  const [showLive, setShowLive] = useState(false);
  const [modalMode, setModalMode] = useState<"normal" | "maximized" | "fullscreen">("normal");
  const [openingDefaultApp, setOpeningDefaultApp] = useState(false);

  const toggleMaximize = () => {
    setModalMode(prev => (prev === "maximized" ? "normal" : "maximized"));
  };

  const toggleFullscreen = () => {
    setModalMode(prev => (prev === "fullscreen" ? "normal" : "fullscreen"));
  };

  const handleOpenInDefaultApp = async () => {
    if (!photo.path || openingDefaultApp) return;
    setOpeningDefaultApp(true);
    try {
      const ok = await openFile(photo.path);
      if (!ok) {
        notify("Could not open file in default application.", "error");
      } else {
        notify("Opened photo in default viewer.", "success");
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setOpeningDefaultApp(false);
    }
  };

  const [savingFaceName, setSavingFaceName] = useState(false);
  const [assigningFace, setAssigningFace] = useState(false);
  const [togglingMark, setTogglingMark] = useState<"favourite" | "hidden" | null>(null);
  const [restoringDate, setRestoringDate] = useState(false);

  const loadDetail = useCallback(async () => {
    try {
      const d = await rpc<PhotoDetailResponse>("photos.detail", { image_id: initialPhoto.id });
      if (d?.photo) setPhoto(prev => ({ ...prev, ...d.photo }));
      setFaces(d?.faces || []);
      setTags(d?.tags || []);
      setMarks(d?.marks || []);
      setLiveVideo(d?.live_video || null);

      const fullPath = d?.photo?.path || initialPhoto.path;
      if (fullPath && needsBackendDecode(fullPath)) {
        const decoded = await rpc<{ data_url?: string | null }>("photos.decode", {
          path: fullPath,
          max_side: 2400,
        });
        if (decoded?.data_url) setImgSrc(decoded.data_url);
      } else if (fullPath) {
        setImgSrc(mediaUrl(fullPath));
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  }, [initialPhoto.id, initialPhoto.path, notify]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleClose = () => {
    if (dirtyRef.current) invalidate();
    onClose?.();
  };

  const stepZoom = (factor: number) =>
    setZoom(z => Math.max(0.25, Math.min(8, Number((z * factor).toFixed(3)))));
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    dragRef.current = {
      active: true,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      origX: pan.x,
      origY: pan.y,
    };
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    if (Math.hypot(dx, dy) > 4) dragRef.current.moved = true;
    setPan({ x: dragRef.current.origX + dx, y: dragRef.current.origY + dy });
  };

  const onPointerUp = () => {
    dragRef.current.active = false;
  };

  const onFaceClick = (e: MouseEvent<HTMLDivElement>, face: FaceRecord) => {
    e.stopPropagation();
    if (dragRef.current.moved) return;
    setActiveFace(face);
    setFaceNameInput(face.person_name || "");
    zoomToFace(face);
    rpc<PersonRecord[]>("persons.list")
      .then(res => setPersons(res || []))
      .catch(() => {});
  };

  const handleNameFace = async () => {
    if (!activeFace || !faceNameInput.trim() || savingFaceName) return;
    setSavingFaceName(true);
    try {
      await rpc("faces.name", { face_id: activeFace.id, name: faceNameInput.trim() });
      dirtyRef.current = true;
      setActiveFace(null);
      notify("Face named.", "success");
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setSavingFaceName(false);
    }
  };

  const handleAssignFace = async (personId: number | null) => {
    if (!activeFace || assigningFace) return;
    setAssigningFace(true);
    try {
      await rpc("faces.assign", { face_id: activeFace.id, person_id: personId });
      dirtyRef.current = true;
      setActiveFace(null);
      notify(personId === null ? "Removed face from person." : "Face assigned.", "success");
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setAssigningFace(false);
    }
  };

  const toggleMark = async (kind: "favourite" | "hidden") => {
    if (togglingMark) return;
    setTogglingMark(kind);
    try {
      const res = await rpc<{ marks?: string[] }>("photos.toggle_mark", {
        image_id: photo.id,
        kind,
      });
      setMarks(res.marks || []);
      dirtyRef.current = true;
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setTogglingMark(null);
    }
  };

  const handleDateSave = async (iso: string) => {
    try {
      await rpc("photos.set_date", { image_id: photo.id, iso, reason: "manual (lightbox)" });
      setPhoto(p => ({ ...p, effective_ts: iso }));
      dirtyRef.current = true;
      setShowDateModal(false);
      notify("Photo date updated.", "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  };

  const handleRestoreDate = async () => {
    if (restoringDate) return;
    setRestoringDate(true);
    try {
      const res = await rpc<{ effective_ts?: string | null }>("photos.clear_date", {
        image_id: photo.id,
      });
      setPhoto(p => ({ ...p, effective_ts: res.effective_ts }));
      dirtyRef.current = true;
      notify("Original date restored.", "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
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
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
    };
  }, [stepZoom]);

  const [renderedDims, setRenderedDims] = useState<{
    width: number;
    height: number;
    naturalWidth: number;
    naturalHeight: number;
  } | null>(null);
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

  const zoomToFace = useCallback(
    (face: FaceRecord) => {
      const origW = renderedDims?.naturalWidth || Number(photo.width || 1);
      const origH = renderedDims?.naturalHeight || Number(photo.height || 1);
      const faceW = Number(face.w || 0);
      const faceH = Number(face.h || 0);
      if (!origW || !origH || !faceW || !faceH) return;

      const faceCx = Number(face.x || 0) + faceW / 2;
      const faceCy = Number(face.y || 0) + faceH / 2;
      const normX = faceCx / origW - 0.5;
      const normY = faceCy / origH - 0.5;

      const faceFraction = Math.max(faceW / origW, faceH / origH);
      const targetZoom = Math.max(1.8, Math.min(5, 0.4 / Math.max(0.05, faceFraction)));

      const imgW = renderedDims?.width || 800;
      const imgH = renderedDims?.height || 600;

      const panX = -normX * imgW * targetZoom;
      const panY = -normY * imgH * targetZoom;

      setZoom(Number(targetZoom.toFixed(2)));
      setPan({ x: Math.round(panX), y: Math.round(panY) });
    },
    [renderedDims, photo.width, photo.height]
  );

  const origW = renderedDims?.naturalWidth || Number(photo.width || 1);
  const origH = renderedDims?.naturalHeight || Number(photo.height || 1);

  const modalContainerClass =
    modalMode === "fullscreen"
      ? "w-screen h-screen max-w-none max-h-none rounded-none border-0"
      : modalMode === "maximized"
        ? "w-[98vw] h-[96vh] max-w-none max-h-none rounded-xs"
        : "w-[1160px] h-[86vh] max-w-[96vw] max-h-[92vh] rounded-sm";

  const modalBackdropClass = modalMode === "fullscreen" ? "p-0" : "p-3 md:p-5";

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
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />
                ) : (
                  <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.6} />
                )}
              </button>
            )}
            <button
              type="button"
              title={modalMode === "maximized" ? "Restore window size" : "Maximize modal window"}
              onClick={toggleMaximize}
              className={`w-7 h-7 flex items-center justify-center rounded-xs transition-colors ${
                modalMode === "maximized"
                  ? "bg-accent-secondary-light text-accent-secondary border border-accent-secondary/55"
                  : "text-secondary hover:text-primary hover:bg-elevated"
              }`}
            >
              {modalMode === "maximized" ? (
                <Minimize className="w-3.5 h-3.5" strokeWidth={1.6} />
              ) : (
                <Maximize className="w-3.5 h-3.5" strokeWidth={1.6} />
              )}
            </button>
            <button
              type="button"
              title={modalMode === "fullscreen" ? "Exit fullscreen (Esc)" : "Enter fullscreen view"}
              onClick={toggleFullscreen}
              className={`w-7 h-7 flex items-center justify-center rounded-xs transition-colors ${
                modalMode === "fullscreen"
                  ? "bg-accent-secondary-light text-accent-secondary border border-accent-secondary/55"
                  : "text-secondary hover:text-primary hover:bg-elevated"
              }`}
            >
              {modalMode === "fullscreen" ? (
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
                <button
                  type="button"
                  title="Zoom Out"
                  onClick={() => stepZoom(1 / 1.2)}
                  className="btn-neutral h-7 w-7"
                >
                  <ZoomOut className="w-3.5 h-3.5" strokeWidth={1.6} />
                </button>
                <span className="font-mono text-xs text-secondary w-11 text-center tabular-nums">
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  type="button"
                  title="Zoom In"
                  onClick={() => stepZoom(1.2)}
                  className="btn-neutral h-7 w-7"
                >
                  <ZoomIn className="w-3.5 h-3.5" strokeWidth={1.6} />
                </button>
                <button type="button" onClick={resetView} className="btn-neutral h-7 px-2 text-xs">
                  <Maximize className="w-3 h-3" strokeWidth={1.6} />
                  <span>Fit</span>
                </button>
              </div>
              <button
                type="button"
                onClick={() => setShowFaces(v => !v)}
                className={`h-7 px-2.5 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors ${
                  showFaces
                    ? "bg-violet-bg border-violet text-violet"
                    : "bg-card border-hairline text-secondary hover:text-primary hover:bg-elevated"
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
                  width: renderedDims ? `${renderedDims.width}px` : "auto",
                  height: renderedDims ? `${renderedDims.height}px` : "auto",
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
                    {faces.map(f => {
                      const label = faceDisplayName(f);
                      const isLocked = Boolean(f.locked);
                      const style = {
                        left: `${(Number(f.x || 0) / origW) * 100}%`,
                        top: `${(Number(f.y || 0) / origH) * 100}%`,
                        width: `${(Number(f.w || 0) / origW) * 100}%`,
                        height: `${(Number(f.h || 0) / origH) * 100}%`,
                      };
                      const boxClass = isLocked
                        ? "border-solid border-success bg-success/10 hover:bg-success/15"
                        : label
                          ? "border-solid border-violet bg-violet/15 hover:bg-violet/20"
                          : "border-dashed border-amber/85 bg-transparent hover:bg-amber/15";

                      return (
                        <div
                          key={f.id}
                          style={style}
                          title={label ? `${label} (Click to manage)` : "Click to name this face"}
                          onClick={e => onFaceClick(e, f)}
                          className={`absolute pointer-events-auto cursor-pointer border-2 transition-colors ${boxClass}`}
                        >
                          {label && (
                            <span
                              className={`absolute left-1/2 bottom-full mb-1 -translate-x-1/2 px-1.5 py-0.5 bg-sidebar/95 border rounded-[2px] text-[10.5px] font-semibold text-primary whitespace-nowrap pointer-events-none ${
                                isLocked ? "border-success/75" : "border-violet/75"
                              }`}
                            >
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

          <LightboxSidebar
            photo={photo}
            faces={faces}
            tags={tags}
            marks={marks}
            liveVideo={liveVideo}
            activeFace={activeFace}
            faceNameInput={faceNameInput}
            setFaceNameInput={setFaceNameInput}
            persons={persons}
            savingFaceName={savingFaceName}
            assigningFace={assigningFace}
            togglingMark={togglingMark}
            restoringDate={restoringDate}
            openingDefaultApp={openingDefaultApp}
            onZoomToFace={zoomToFace}
            onNameFace={handleNameFace}
            onAssignFace={handleAssignFace}
            onCloseActiveFace={() => setActiveFace(null)}
            onToggleMark={toggleMark}
            onShowDateModal={() => setShowDateModal(true)}
            onRestoreDate={handleRestoreDate}
            onShowSimilar={() => setShowSimilar(true)}
            onShowLive={() => setShowLive(true)}
            onOpenInDefaultApp={handleOpenInDefaultApp}
            onRevealInFolder={p => revealFile(p)}
          />
        </div>
      </ModalShell>

      {showDateModal && (
        <DateOverrideModal
          currentIso={photo.effective_ts || photo.exif_ts}
          onClose={() => setShowDateModal(false)}
          onSave={handleDateSave}
        />
      )}
      {showSimilar && (
        <SimilarPhotosModal
          imageId={photo.id}
          onClose={() => setShowSimilar(false)}
          onOpenPhoto={p => {
            setShowSimilar(false);
            setLightboxPhoto(p);
          }}
        />
      )}
      {showLive && liveVideo && (
        <LivePhotoModal videoPath={liveVideo.path} onClose={() => setShowLive(false)} />
      )}
    </>
  );
}
