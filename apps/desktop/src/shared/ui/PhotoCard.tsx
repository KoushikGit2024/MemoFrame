import React, { useEffect, useRef, useState } from "react";
import { ImageOff, ScanFace, Star, UserCheck } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { basename, computeFaceZoomStyle, formatDate, formatQuality } from "../lib/utils";
import type { PhotoRecord } from "../types/memoframe";

interface PhotoCardProps {
  photo: PhotoRecord;
  compact?: boolean;
  faceZoom?: boolean;
  targetPersonId?: number | null;
  unassignedOnly?: boolean;
  showInfo?: boolean;
  onOpen?: (photo: PhotoRecord) => void;
  onSetDefaultFace?: (personId: number, faceId: number) => void;
  dateOpts?: { timezone?: string; dateFormat?: "iso" | "locale" | "relative" };
  className?: string;
}

export default React.memo(function PhotoCard({
  photo,
  compact = false,
  faceZoom = false,
  targetPersonId = null,
  unassignedOnly = false,
  showInfo = true,
  onOpen,
  onSetDefaultFace,
  dateOpts,
  className = "",
}: PhotoCardProps) {
  // If thumbnail fails or is missing, fall back to photo.path
  const [useFallback, setUseFallback] = useState(false);
  const [imgErr, setImgErr] = useState(false);
  const [cropLoaded, setCropLoaded] = useState(false);
  const cropImgRef = useRef<HTMLImageElement | null>(null);

  const targetFace =
    targetPersonId != null ? photo.faces?.find(f => f.person_id === targetPersonId) : undefined;
  const zoomStyle = faceZoom ? computeFaceZoomStyle(photo, targetPersonId, unassignedOnly) : null;
  const faceCrop =
    photo.face_crop_path ||
    (targetPersonId != null ? targetFace?.crop_path : undefined) ||
    photo.faces?.[0]?.crop_path;
  const srcPath = !useFallback && photo.thumb_path ? photo.thumb_path : photo.path;
  const cropSrc = faceZoom && faceCrop ? mediaUrl(faceCrop) : "";

  useEffect(() => {
    if (cropImgRef.current?.complete && cropImgRef.current.naturalWidth > 0) {
      setCropLoaded(true);
    } else {
      setCropLoaded(false);
    }
  }, [faceZoom, cropSrc]);

  const imgSrc = !imgErr && srcPath ? mediaUrl(srcPath) : "";
  const faceCount = photo.faces?.length ?? photo.face_count ?? 0;
  const isSuggested = Boolean(photo.suggested || photo.suggested_keep);
  const isFavourite = Boolean(photo.is_favourite);
  const formattedFull = formatDate(photo.effective_ts || photo.exif_ts, dateOpts);
  const dateText =
    !dateOpts?.dateFormat || dateOpts.dateFormat === "iso"
      ? formattedFull.slice(0, 10)
      : formattedFull;

  const handleImageError = () => {
    if (!useFallback && photo.thumb_path && photo.path && photo.thumb_path !== photo.path) {
      setUseFallback(true);
    } else {
      setImgErr(true);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={e => e.currentTarget.focus()}
      onDoubleClick={() => onOpen?.(photo)}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen?.(photo);
        } else if (e.key === "ArrowRight") {
          const next = e.currentTarget.nextElementSibling as HTMLElement | null;
          if (next) {
            e.preventDefault();
            next.focus();
          }
        } else if (e.key === "ArrowLeft") {
          const prev = e.currentTarget.previousElementSibling as HTMLElement | null;
          if (prev) {
            e.preventDefault();
            prev.focus();
          }
        }
      }}
      className={`group relative box-border w-full aspect-square overflow-hidden rounded-md bg-input border border-subtle hover:border-accent-secondary/75 cursor-pointer transition-colors focus-visible:outline-none focus-visible:border-accent-secondary focus-visible:ring-1 focus-visible:ring-accent-secondary/40 ${className}`}
    >
      {imgSrc ? (
        <>
          <img
            src={imgSrc}
            alt={basename(photo.path)}
            loading="lazy"
            decoding="async"
            onError={handleImageError}
            style={zoomStyle ?? undefined}
            className="absolute inset-0 w-full h-full object-cover transition-transform duration-300 ease-out"
          />
          {cropSrc && (
            <img
              ref={cropImgRef}
              src={cropSrc}
              alt=""
              aria-hidden="true"
              loading="lazy"
              decoding="async"
              onLoad={() => setCropLoaded(true)}
              className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-200 pointer-events-none ${
                cropLoaded ? "opacity-100" : "opacity-0"
              }`}
            />
          )}
        </>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <ImageOff className="w-6 h-6 text-secondary opacity-40" strokeWidth={1.5} />
        </div>
      )}

      {showInfo && (isSuggested || isFavourite) && (
        <span
          title={isFavourite ? "Favourite" : "Recommended / Best quality"}
          className="absolute top-1.5 left-1.5 h-5 px-1.5 inline-flex items-center gap-1 rounded-xs bg-sidebar/90 border border-amber/45 text-[10.5px] font-mono text-amber"
        >
          <Star className="w-3 h-3 fill-current" strokeWidth={1.6} />
        </span>
      )}

      {showInfo && faceCount > 0 && (
        <span className="absolute top-1.5 right-1.5 h-5 px-1.5 inline-flex items-center gap-1 rounded-xs bg-sidebar/90 border border-violet/40 text-[10.5px] font-mono text-primary">
          <ScanFace className="w-3 h-3 text-violet" strokeWidth={1.6} />
          <span>{faceCount}</span>
        </span>
      )}

      {onSetDefaultFace && targetPersonId != null && targetFace && (
        <button
          type="button"
          title="Set as default face for this person"
          onClick={e => {
            e.stopPropagation();
            onSetDefaultFace(targetPersonId, targetFace.id);
          }}
          onDoubleClick={e => e.stopPropagation()}
          className={`absolute right-1.5 z-10 h-6 px-1.5 inline-flex items-center gap-1 rounded-xs bg-sidebar/90 border border-violet/60 text-[10.5px] font-medium text-violet opacity-0 group-hover:opacity-100 hover:bg-violet hover:text-white transition-all cursor-pointer ${
            showInfo ? (compact ? "bottom-8" : "bottom-12") : "bottom-1.5"
          }`}
        >
          <UserCheck className="w-3 h-3" strokeWidth={1.7} />
          <span>Default</span>
        </button>
      )}

      {showInfo && (
        <div
          className={`absolute inset-x-0 bottom-0 flex flex-col gap-0.5 bg-gradient-to-t from-black/80 via-black/50 to-transparent pt-6 ${
            compact ? "px-2 pb-1.5" : "px-2.5 pb-2"
          }`}
        >
          <div
            className="text-xs font-medium text-white truncate"
            title={photo.path || ""}
          >
            {basename(photo.path) || `Photo #${photo.id}`}
          </div>
          {!compact && (
            <div className="flex items-center justify-between text-[11px] text-white/80 font-mono tabular-nums">
              <span>{dateText}</span>
              <span>{formatQuality(photo.quality)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
