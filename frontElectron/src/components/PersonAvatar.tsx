import { useState } from 'react';
import { mediaUrl } from '../lib/api';
import { initials } from '../lib/utils';
import type { PersonRecord } from '../types/memoframe';

interface PersonAvatarProps {
  person?: PersonRecord | null;
  size?: 'sm' | 'md';
}

export default function PersonAvatar({ person, size = 'sm' }: PersonAvatarProps) {
  const [err, setErr] = useState(false);
  const src = !err && person?.cover_crop_path ? mediaUrl(person.cover_crop_path) : '';
  const dims = size === 'md' ? 'w-10 h-10 text-xs' : 'w-7 h-7 text-[11px]';

  return (
    <span className={`${dims} shrink-0 rounded-xs bg-input border border-subtle overflow-hidden inline-flex items-center justify-center font-semibold text-secondary`}>
      {src ? (
        <img src={src} alt={person?.name || ''} onError={() => setErr(true)} className="w-full h-full object-cover" />
      ) : (
        initials(person?.name)
      )}
    </span>
  );
}
