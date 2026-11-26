import React, { useEffect, useState } from "react";
import { ImageOff, ScanFace, Star } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { basename, computeFaceZoomStyle, formatDate, formatQuality } from "../lib/utils";
import type { PhotoRecord } from "../types/memoframe";

interface PhotoCardProps {
  photo: PhotoRecord;
  compact?: boolean;
  faceZoom?: boolean;
  targetPersonId?: number | null;
  onOpen?: (photo: PhotoRecord) => void;
  className?: string;
}

export default React.memo(function PhotoCard({
  photo,
  compact = false,
  faceZoom = false,
  targetPersonId = null,
  onOpen,
  className = "",
}: PhotoCardProps) {
  // If thumbnail fails or is missing, fall back to photo.path
  const [useFallback, setUseFallback] = useState(false);
  const [imgErr, setImgErr] = useState(false);
  const [cropLoaded, setCropLoaded] = useState(false);

  const zoomStyle = faceZoom ? computeFaceZoomStyle(photo, targetPersonId) : null;
  const faceCrop = photo.face_crop_path || photo.faces?.[0]?.crop_path;
  const srcPath = !useFallback && photo.thumb_path ? photo.thumb_path : photo.path;
  const cropSrc = faceZoom && faceCrop ? mediaUrl(faceCrop) : "";

  useEffect(() => {
    setCropLoaded(false);
  }, [faceZoom, faceCrop]);

  const imgSrc = !imgErr && srcPath ? mediaUrl(srcPath) : "";
  const faceCount = photo.faces?.length ?? photo.face_count ?? 0;
  const isSuggested = Boolean(photo.suggested || photo.suggested_keep);
  const dateText = formatDate(photo.effective_ts || photo.exif_ts).slice(0, 10);

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
      onClick={() => onOpen?.(photo)}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen?.(photo);
        }
      }}
      style={{ contentVisibility: "auto", containIntrinsicSize: "240px" }}
      className={`group bg-card border border-subtle hover:border-accent-secondary/75 rounded-sm overflow-hidden cursor-pointer flex flex-col transition-colors focus-visible:outline-none focus-visible:border-accent-secondary focus-visible:ring-1 focus-visible:ring-accent-secondary/40 ${className}`}
    >
      <div className="relative w-full aspect-[4/3] bg-input overflow-hidden flex items-center justify-center">
        {imgSrc ? (
          <>
            <img
              src={imgSrc}
              alt={basename(photo.path)}
              loading="lazy"
              decoding="async"
              onError={handleImageError}
              style={zoomStyle ?? undefined}
              className="w-full h-full object-cover transition-transform duration-300 ease-out"
            />
            {cropSrc && (
              <img
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
          <ImageOff className="w-6 h-6 text-secondary opacity-40" strokeWidth={1.5} />
        )}

        {isSuggested && (
          <span
            title="Recommended / Best quality"
            className="absolute top-1.5 left-1.5 h-5 px-1.5 inline-flex items-center gap-1 rounded-xs bg-sidebar/90 border border-amber/45 text-[10.5px] font-mono text-amber"
          >
            <Star className="w-3 h-3 fill-current" strokeWidth={1.6} />
          </span>
        )}

        {faceCount > 0 && (
          <span className="absolute top-1.5 right-1.5 h-5 px-1.5 inline-flex items-center gap-1 rounded-xs bg-sidebar/90 border border-violet/40 text-[10.5px] font-mono text-primary">
            <ScanFace className="w-3 h-3 text-violet" strokeWidth={1.6} />
            <span>{faceCount}</span>
          </span>
        )}
      </div>

      <div
        className={`border-t border-subtle flex flex-col gap-0.5 ${compact ? "px-2 py-1.5" : "px-2.5 py-2"}`}
      >
        <div
          className="text-xs font-medium text-primary truncate group-hover:text-accent-secondary transition-colors"
          title={photo.path || ""}
        >
          {basename(photo.path) || `Photo #${photo.id}`}
        </div>
        {!compact && (
          <div className="flex items-center justify-between text-[11px] text-secondary font-mono tabular-nums">
            <span>{dateText}</span>
            <span>{formatQuality(photo.quality)}</span>
          </div>
        )}
      </div>
    </div>
  );
});
