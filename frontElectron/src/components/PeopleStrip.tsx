import { useMemo, useState } from 'react';
import { sortPersons } from '../lib/utils';
import type { PersonRecord, PersonSortMode } from '../types/memoframe';
import PersonAvatar from './PersonAvatar';

const UNIDENTIFIED_RE = /^(person\s+\d+|unknown)$/i;

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
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary">
          <span className="w-1.5 h-1.5 rounded-full bg-violet" />
          <span>Identified People ({persons.length})</span>
        </span>
        {selectedPersonId !== null && (
          <button type="button" onClick={() => onSelectPerson(null)} className="text-xs text-violet hover:underline">
            Clear filter
          </button>
        )}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find person..."
          className="h-6 w-36 px-2 bg-input border border-hairline rounded-xs text-xs text-primary placeholder:text-secondary focus:outline-none focus:border-accent-secondary focus:ring-1 focus:ring-accent-secondary/30"
        />
        <select
          value={sortMode}
          onChange={(e) => setSortMode(e.target.value as PersonSortMode)}
          className="h-6 px-1.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-violet"
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
          className={`h-8 px-2.5 shrink-0 inline-flex items-center gap-1.5 rounded-xs border text-xs font-medium transition-colors ${
            selectedPersonId === null
              ? 'bg-elevated border-hairline text-primary font-semibold'
              : 'bg-card border-subtle text-secondary hover:text-primary hover:bg-elevated'
          }`}
        >
          All People
        </button>
        {visible.map((p) => {
          const active = selectedPersonId === p.id;
          const isUnidentified = !p.name || UNIDENTIFIED_RE.test(p.name.trim());
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onSelectPerson(active ? null : p.id)}
              className={`h-8 pl-1 pr-2.5 shrink-0 inline-flex items-center gap-2 rounded-xs border text-xs transition-colors ${
                active
                  ? 'bg-violet-bg border-violet text-violet font-semibold'
                  : isUnidentified
                  ? 'bg-card border-subtle border-dashed text-secondary hover:border-amber/60 hover:text-primary hover:bg-elevated'
                  : 'bg-card border-subtle text-primary hover:border-violet/55 hover:bg-elevated'
              }`}
            >
              <PersonAvatar
                person={p}
                size="sm"
                accent={active ? 'violet' : isUnidentified ? 'amber' : 'default'}
              />
              <span className="max-w-[110px] truncate">{p.name}</span>
              <span className={`font-mono text-[10.5px] ${active ? 'text-violet' : 'text-secondary'}`}>
                {p.image_count || 0}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
