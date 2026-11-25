import { useMemo, useState } from 'react';
import { sortPersons } from '../lib/utils';
import type { PersonRecord, PersonSortMode } from '../types/memoframe';
import PersonAvatar from './PersonAvatar';

interface PeopleStripProps {
  persons: PersonRecord[];
  selectedPersonId: number | null;
  onSelectPerson: (personId: number | null) => void;
}

export default function PeopleStrip({ persons, selectedPersonId, onSelectPerson }: PeopleStripProps) {
  const [query, setQuery] = useState('');
  const [sortMode, setSortMode] = useState<PersonSortMode>('most');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = (persons || []).filter((p) => String(p.name || '').toLowerCase().includes(q));
    return sortPersons(filtered, sortMode);
  }, [persons, query, sortMode]);

  if (!persons || persons.length === 0) return null;

  return (
    <div className="bg-card border border-subtle rounded-sm px-3 py-2 flex flex-col gap-2 shrink-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-primary">Identified People ({persons.length})</span>
        {selectedPersonId !== null && (
          <button type="button" onClick={() => onSelectPerson(null)} className="text-xs text-accent hover:underline">
            Clear filter
          </button>
        )}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find person..."
          className="h-6 w-36 px-2 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent"
        />
        <select
          value={sortMode}
          onChange={(e) => setSortMode(e.target.value as PersonSortMode)}
          className="h-6 px-1.5 bg-input border border-hairline rounded-xs text-xs text-primary"
        >
          <option value="most">Most photos</option>
          <option value="name_asc">Name A to Z</option>
          <option value="name_desc">Name Z to A</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
        <button
          type="button"
          onClick={() => onSelectPerson(null)}
          className={`h-8 px-2.5 shrink-0 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium ${
            selectedPersonId === null
              ? 'bg-accent-light border-accent text-primary'
              : 'bg-elevated border-subtle text-secondary hover:text-primary'
          }`}
        >
          All People
        </button>
        {visible.map((p) => {
          const active = selectedPersonId === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onSelectPerson(p.id)}
              className={`h-8 pl-1 pr-2.5 shrink-0 inline-flex items-center gap-2 rounded-xs border text-xs ${
                active
                  ? 'bg-accent-light border-accent text-primary font-medium'
                  : 'bg-elevated border-subtle text-primary hover:border-hairline'
              }`}
            >
              <PersonAvatar person={p} size="sm" />
              <span className="max-w-[110px] truncate">{p.name}</span>
              <span className="font-mono text-[10.5px] text-secondary">{p.image_count || 0}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
