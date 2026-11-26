import React, { useState } from "react";
import { ImageOff, ScanFace, Star } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { basename, formatDate, formatQuality } from "../lib/utils";
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
  targetPersonId: _targetPersonId = null,
  onOpen,
  className = "",
}: PhotoCardProps) {
  // If thumbnail fails or is missing, fall back to photo.path
  const [useFallback, setUseFallback] = useState(false);
  const [imgErr, setImgErr] = useState(false);

  // In faceZoom mode, display the crisp backend square face crop directly (Felicity model).
  // In normal mode, use the lightweight whole-photo thumbnail.
  const faceCrop = photo.face_crop_path || photo.faces?.[0]?.crop_path;
  const srcPath =
    faceZoom && faceCrop
      ? faceCrop
      : !useFallback && photo.thumb_path
        ? photo.thumb_path
        : photo.path;

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
      className={`group bg-card border border-subtle hover:border-accent-secondary/75 rounded-sm overflow-hidden cursor-pointer flex flex-col transition-colors focus-visible:outline-none focus-visible:border-accent-secondary focus-visible:ring-1 focus-visible:ring-accent-secondary/40 ${className}`}
    >
      <div className="relative w-full aspect-[4/3] bg-input overflow-hidden flex items-center justify-center">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={basename(photo.path)}
            loading="lazy"
            onError={handleImageError}
            className="w-full h-full object-cover"
          />
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
