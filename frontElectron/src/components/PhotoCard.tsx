import { useState } from 'react';
import { ImageOff, ScanFace } from 'lucide-react';
import { mediaUrl } from '../lib/api';
import { basename, computeFaceZoomStyle, formatDate, formatQuality } from '../lib/utils';
import type { PhotoRecord } from '../types/memoframe';

interface PhotoCardProps {
  photo: PhotoRecord;
  compact?: boolean;
  faceZoom?: boolean;
  onOpen?: (photo: PhotoRecord) => void;
  className?: string;
}

export default function PhotoCard({ photo, compact = false, faceZoom = false, onOpen, className = '' }: PhotoCardProps) {
  const [imgErr, setImgErr] = useState(false);
  const srcPath = photo.thumb_path || photo.path;
  const imgSrc = !imgErr && srcPath ? mediaUrl(srcPath) : '';
  const zoomStyle = faceZoom ? computeFaceZoomStyle(photo) : null;
  const faceCount = photo.faces?.length ?? photo.face_count ?? 0;
  const dateText = formatDate(photo.effective_ts || photo.exif_ts).slice(0, 10);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen?.(photo)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen?.(photo); } }}
      className={`group bg-card border border-subtle hover:border-accent rounded-sm overflow-hidden cursor-pointer flex flex-col transition-colors focus:outline-none focus:border-accent ${className}`}
    >
      <div className="relative w-full aspect-[4/3] bg-input overflow-hidden flex items-center justify-center">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={basename(photo.path)}
            loading="lazy"
            onError={() => setImgErr(true)}
            style={zoomStyle || undefined}
            className="w-full h-full object-cover transition-transform duration-150"
          />
        ) : (
          <ImageOff className="w-6 h-6 text-secondary opacity-40" strokeWidth={1.5} />
        )}

        {faceCount > 0 && (
          <span className="absolute top-1.5 right-1.5 h-5 px-1.5 inline-flex items-center gap-1 rounded-xs bg-sidebar/90 border border-hairline text-[10.5px] font-mono text-primary">
            <ScanFace className="w-3 h-3 text-accent" strokeWidth={1.6} />
            <span>{faceCount}</span>
          </span>
        )}
      </div>

      <div className={`border-t border-subtle flex flex-col gap-0.5 ${compact ? 'px-2 py-1.5' : 'px-2.5 py-2'}`}>
        <div className="text-xs font-medium text-primary truncate" title={photo.path || ''}>
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
}
