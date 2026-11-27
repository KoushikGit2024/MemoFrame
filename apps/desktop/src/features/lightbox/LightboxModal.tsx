import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, PointerEvent } from "react";
import {
  AppWindow,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  Maximize,
  Minimize2,
  ScanFace,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useApp } from "../../shared/context/AppContext";
import { mediaUrl, openFile, revealFile, rpc } from "../../shared/lib/api";
import { basename, faceDisplayName, needsBackendDecode } from "../../shared/lib/utils";
import type { FaceRecord, PersonRecord, PhotoRecord, TagRecord } from "../../shared/types/memoframe";
import ModalShell from "../../shared/ui/ModalShell";
import { DateOverrideModal } from "../settings/DateModals";
import { LivePhotoModal, SimilarPhotosModal } from "../settings/UtilityModals";
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

interface RenderedDims {
  /** On-screen size of the image box (fit to viewport, aspect from the displayed image). */
  width: number;
  height: number;
  /** Coordinate space that face x/y/w/h are expressed in (original photo pixels). */
  faceW: number;
  faceH: number;
}

export default function LightboxModal({ photo: initialPhoto, onClose }: LightboxModalProps) {
  const {
    invalidate,
    notify,
    lightboxList,
    setLightboxPhoto,
    setGalleryExtraFilters,
    setActiveView,
    openExportModal
  } = useApp();
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
  const dragRef = useRef({
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    origX: 0,
    origY: 0,
    lastX: 0,
    lastY: 0,
  });
  const transformContainerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dirtyRef = useRef(false);

  const [renderedDims, setRenderedDims] = useState<RenderedDims | null>(null);

  const [activeFace, setActiveFace] = useState<FaceRecord | null>(null);
  const [faceNameInput, setFaceNameInput] = useState("");
  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const personsCacheRef = useRef<PersonRecord[] | null>(null);
  const [showDateModal, setShowDateModal] = useState(false);
  const [showSimilar, setShowSimilar] = useState(false);
  const [showLive, setShowLive] = useState(false);
  const isStandaloneWindow = Boolean(new URLSearchParams(window.location.search).get("lightbox"));
  const [modalMode, setModalMode] = useState<"normal" | "maximized" | "fullscreen">(
    isStandaloneWindow ? "fullscreen" : "normal"
  );
  const [openingDefaultApp, setOpeningDefaultApp] = useState(false);

  const currentIndex = lightboxList.findIndex(p => p.id === photo.id);
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex >= 0 && currentIndex < lightboxList.length - 1;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName || "").toUpperCase();
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowLeft" && hasPrev) {
        e.preventDefault();
        setLightboxPhoto(lightboxList[currentIndex - 1]);
      } else if (e.key === "ArrowRight" && hasNext) {
        e.preventDefault();
        setLightboxPhoto(lightboxList[currentIndex + 1]);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [currentIndex, hasPrev, hasNext, lightboxList, setLightboxPhoto]);

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
  const [discardingFace, setDiscardingFace] = useState(false);
  const [settingDefaultFace, setSettingDefaultFace] = useState(false);
  const [togglingMark, setTogglingMark] = useState<"favourite" | "hidden" | null>(null);
  const [restoringDate, setRestoringDate] = useState(false);

  const loadDetail = useCallback(async () => {
    try {
      const initialPath = initialPhoto.path;
      const shouldPreDecode = Boolean(initialPath && needsBackendDecode(initialPath));
      const [d, preDecoded] = await Promise.all([
        rpc<PhotoDetailResponse>("photos.detail", { image_id: initialPhoto.id }),
        shouldPreDecode && initialPath
          ? rpc<{ data_url?: string | null }>("photos.decode", {
              path: initialPath,
              max_side: 2400,
            })
          : Promise.resolve(null),
      ]);
      if (d?.photo) setPhoto(prev => ({ ...prev, ...d.photo }));
      setFaces(d?.faces || []);
      setTags(d?.tags || []);
      setMarks(d?.marks || []);
      setLiveVideo(d?.live_video || null);

      const fullPath = d?.photo?.path || initialPath;
      if (preDecoded?.data_url) {
        setImgSrc(preDecoded.data_url);
      } else if (fullPath && needsBackendDecode(fullPath)) {
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

  const stepZoom = useCallback(
    (factor: number) =>
      setZoom(z => Math.max(0.25, Math.min(8, Number((z * factor).toFixed(3))))),
    []
  );
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Single source of truth for sizing. The on-screen box takes its aspect ratio from the
  // image actually displayed (thumbnail or decoded), so object-fill never distorts it.
  // Face coordinates live in the original photo's pixel space (photo.width/height),
  // swapped if the displayed image is rotated relative to the DB dimensions.
  const computeDims = useCallback(() => {
    const vp = viewportRef.current;
    const img = imgRef.current;
    if (!vp) return;
    const vw = vp.clientWidth - 16; // subtract padding
    const vh = vp.clientHeight - 16;

    const iw = img?.naturalWidth || 0;
    const ih = img?.naturalHeight || 0;
    let fw = Number(photo.width || 0);
    let fh = Number(photo.height || 0);

    const boxW = iw || fw || 1;
    const boxH = ih || fh || 1;

    if (fw && fh && iw && ih) {
      const dbRatio = fw / fh;
      // If the displayed image is rotated vs. the DB dims, swap the face space.
      if (Math.abs(dbRatio - ih / iw) < Math.abs(dbRatio - iw / ih)) {
        [fw, fh] = [fh, fw];
      }
    } else if (!fw || !fh) {
      fw = boxW;
      fh = boxH;
    }

    if (vw > 0 && vh > 0) {
      const scale = Math.min(vw / boxW, vh / boxH);
      setRenderedDims({
        width: Math.max(1, Math.round(boxW * scale)),
        height: Math.max(1, Math.round(boxH * scale)),
        faceW: fw,
        faceH: fh,
      });
    }
  }, [photo.width, photo.height]);

  // Observe viewport size so the image fits without circular collapse.
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    computeDims();
    const observer = new ResizeObserver(computeDims);
    observer.observe(vp);
    return () => observer.disconnect();
  }, [computeDims, imgSrc, modalMode]);

  const zoomToFace = useCallback(
    (face: FaceRecord) => {
      const origW = renderedDims?.faceW || Number(photo.width || 1);
      const origH = renderedDims?.faceH || Number(photo.height || 1);
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

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    dragRef.current = {
      active: true,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      origX: pan.x,
      origY: pan.y,
      lastX: pan.x,
      lastY: pan.y,
    };
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    if (!dragRef.current.moved && Math.hypot(dx, dy) <= 4) return;
    dragRef.current.moved = true;
    const nextX = dragRef.current.origX + dx;
    const nextY = dragRef.current.origY + dy;
    dragRef.current.lastX = nextX;
    dragRef.current.lastY = nextY;
    if (transformContainerRef.current) {
      transformContainerRef.current.style.transition = "none";
      transformContainerRef.current.style.transform = `translate(${nextX}px, ${nextY}px) scale(${zoom})`;
    }
  };

  const onPointerUp = () => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    if (transformContainerRef.current) {
      transformContainerRef.current.style.transition = "";
    }
    if (dragRef.current.moved) {
      setPan({ x: dragRef.current.lastX, y: dragRef.current.lastY });
    }
  };

  const onFaceClick = (e: MouseEvent<HTMLDivElement>, face: FaceRecord) => {
    e.stopPropagation();
    if (dragRef.current.moved) return;
    setActiveFace(face);
    setFaceNameInput(face.person_name || "");
    zoomToFace(face);
    if (personsCacheRef.current) {
      setPersons(personsCacheRef.current);
    } else {
      rpc<PersonRecord[]>("persons.list")
        .then(res => {
          const list = res || [];
          personsCacheRef.current = list;
          setPersons(list);
        })
        .catch(() => {});
    }
  };

  const handleNameFace = async () => {
    if (!activeFace || !faceNameInput.trim() || savingFaceName) return;
    setSavingFaceName(true);
    try {
      await rpc("faces.name", { face_id: activeFace.id, name: faceNameInput.trim() });
      personsCacheRef.current = null;
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
      personsCacheRef.current = null;
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

  const handleDiscardFace = async (faceId: number) => {
    if (discardingFace) return;
    setDiscardingFace(true);
    try {
      await rpc("faces.discard", { face_id: faceId });
      personsCacheRef.current = null;
      dirtyRef.current = true;
      setActiveFace(null);
      notify("Discarded false face detection.", "success");
      loadDetail();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setDiscardingFace(false);
    }
  };

  const handleSetDefaultFace = async (personId: number, faceId: number) => {
    if (settingDefaultFace) return;
    setSettingDefaultFace(true);
    try {
      await rpc("persons.set_cover", { person_id: personId, face_id: faceId });
      personsCacheRef.current = null;
      dirtyRef.current = true;
      notify("Updated person's default face.", "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setSettingDefaultFace(false);
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

  // Face boxes are expressed in this coordinate space; percentages are relative to the box.
  const origW = renderedDims?.faceW || Number(photo.width || 1);
  const origH = renderedDims?.faceH || Number(photo.height || 1);

  const modalContainerClass =
    modalMode === "fullscreen"
      ? "w-screen h-screen max-w-none max-h-none rounded-none border-0"
      : modalMode === "maximized"
        ? "w-[98vw] h-[96vh] max-w-none max-h-none rounded-xs"
        : "w-[1160px] h-[86vh] max-w-[96vw] max-h-[92vh] rounded-sm";

  const modalBackdropClass = modalMode === "fullscreen" ? "p-0" : "p-3 md:p-5";

  const bodyContent = (
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
          {lightboxList.length > 1 && (
            <>
              <button
                type="button"
                title="Previous photo (Left Arrow)"
                disabled={!hasPrev}
                onPointerDown={e => e.stopPropagation()}
                onClick={e => {
                  e.stopPropagation();
                  if (hasPrev) setLightboxPhoto(lightboxList[currentIndex - 1]);
                }}
                className="absolute left-3 top-1/2 -translate-y-1/2 z-20 w-9 h-9 rounded-full bg-sidebar/80 border border-subtle text-primary hover:bg-elevated hover:border-accent-secondary/60 flex items-center justify-center transition-all disabled:opacity-20 cursor-pointer"
              >
                <ChevronLeft className="w-5 h-5" strokeWidth={1.8} />
              </button>
              <button
                type="button"
                title="Next photo (Right Arrow)"
                disabled={!hasNext}
                onPointerDown={e => e.stopPropagation()}
                onClick={e => {
                  e.stopPropagation();
                  if (hasNext) setLightboxPhoto(lightboxList[currentIndex + 1]);
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 z-20 w-9 h-9 rounded-full bg-sidebar/80 border border-subtle text-primary hover:bg-elevated hover:border-accent-secondary/60 flex items-center justify-center transition-all disabled:opacity-20 cursor-pointer"
              >
                <ChevronRight className="w-5 h-5" strokeWidth={1.8} />
              </button>
            </>
          )}
          <div
            ref={transformContainerRef}
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
              onLoad={computeDims}
              style={{ width: "100%", height: "100%" }}
              className="w-full h-full object-fill select-none pointer-events-none"
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
                  const boxClass =
                    isLocked && label
                      ? "border-solid border-success bg-success/10 hover:bg-success/15"
                      : label
                        ? "border-solid border-violet bg-violet/15 hover:bg-violet/20"
                        : isLocked
                          ? "border-dashed border-subtle/60 bg-transparent hover:border-amber/60"
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
                          className={`absolute left-1/2 -translate-x-1/2 px-1.5 py-0.5 bg-sidebar/95 border rounded-[2px] text-[10.5px] font-semibold text-primary whitespace-nowrap pointer-events-none ${
                            Number(f.y || 0) / origH < 0.12 ? "top-full mt-1" : "bottom-full mb-1"
                          } ${isLocked ? "border-success/75" : "border-violet/75"}`}
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
        discardingFace={discardingFace}
        settingDefaultFace={settingDefaultFace}
        togglingMark={togglingMark}
        restoringDate={restoringDate}
        openingDefaultApp={openingDefaultApp}
        onZoomToFace={zoomToFace}
        onNameFace={handleNameFace}
        onAssignFace={handleAssignFace}
        onDiscardFace={handleDiscardFace}
        onSetDefaultFace={handleSetDefaultFace}
        onCloseActiveFace={() => setActiveFace(null)}
        onToggleMark={toggleMark}
        onShowDateModal={() => setShowDateModal(true)}
        onRestoreDate={handleRestoreDate}
        onShowSimilar={() => setShowSimilar(true)}
        onShowLive={() => setShowLive(true)}
        onOpenInDefaultApp={handleOpenInDefaultApp}
        onRevealInFolder={p => revealFile(p)}
        onExportPhoto={() => openExportModal([photo.id], basename(photo.path) || `Photo #${photo.id}`)}
        onFilterByTag={tag => {
          if (isStandaloneWindow) {
            notify(`Tag "${tag}" — filter in the main gallery window.`, "info");
            return;
          }
          setGalleryExtraFilters(prev => ({ ...prev, tag }));
          setActiveView("photos");
          setLightboxPhoto(null);
        }}
      />
    </div>
  );

  return (
    <>
      {isStandaloneWindow ? (
        <div className="h-screen w-screen flex flex-col bg-app text-primary overflow-hidden">
          <div className="h-10 px-3.5 border-b border-subtle bg-card flex items-center justify-between shrink-0">
            <span className="text-xs font-semibold text-primary truncate">
              {basename(photo.path) || `Photo #${photo.id}`}
            </span>
            {photo.path && (
              <button
                type="button"
                title="Open in Default Application"
                disabled={openingDefaultApp}
                onClick={handleOpenInDefaultApp}
                className="w-7 h-7 flex items-center justify-center rounded-xs text-secondary hover:text-primary hover:bg-elevated transition-colors disabled:opacity-50 cursor-pointer"
              >
                {openingDefaultApp ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />
                ) : (
                  <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.6} />
                )}
              </button>
            )}
          </div>
          {bodyContent}
        </div>
      ) : (
        <ModalShell
          title={basename(photo.path) || `Photo #${photo.id}`}
          subtitle={photo.path}
          noPadding
          className={modalContainerClass}
          backdropClassName={modalBackdropClass}
          onClose={handleClose}
          headerExtra={
            <div className="flex items-center gap-1 border-r border-subtle pr-1.5 mr-0.5">
              {(window as unknown as { memoframe?: { openLightboxWindow?: (id: number) => void } })
                .memoframe?.openLightboxWindow && (
                <button
                  type="button"
                  title="Open in New Window"
                  onClick={() => {
                    try {
                      localStorage.setItem(
                        "memoframe_lightbox_ids",
                        JSON.stringify(lightboxList.map(p => p.id))
                      );
                    } catch {
                      /* ignore storage errors */
                    }
                    (
                      window as unknown as {
                        memoframe?: { openLightboxWindow?: (id: number) => void };
                      }
                    ).memoframe?.openLightboxWindow?.(photo.id);
                    onClose?.();
                  }}
                  className="w-7 h-7 flex items-center justify-center rounded-xs text-secondary hover:text-primary hover:bg-elevated transition-colors cursor-pointer"
                >
                  <AppWindow className="w-3.5 h-3.5" strokeWidth={1.6} />
                </button>
              )}
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
                title={modalMode === "fullscreen" ? "Restore window size" : "Maximize"}
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
                  <Maximize className="w-3.5 h-3.5" strokeWidth={1.6} />
                )}
              </button>
            </div>
          }
        >
          {bodyContent}
        </ModalShell>
      )}

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