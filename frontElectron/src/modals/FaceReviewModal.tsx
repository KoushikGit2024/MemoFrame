import { useCallback, useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { rpc } from '../lib/api';
import type { FaceRecord, PersonRecord } from '../types/memoframe';
import ModalShell from '../components/ModalShell';

const PAGE = 60;

function FaceThumb({ face }: { face: FaceRecord }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    if (!face?.path) return undefined;
    rpc<{ data_url?: string | null }>('faces.crop', { path: face.path, x: face.x, y: face.y, w: face.w, h: face.h, size: 96 })
      .then((res) => { if (alive && res?.data_url) setSrc(res.data_url); })
      .catch(() => {});
    return () => { alive = false; };
  }, [face]);

  return (
    <div className="w-[88px] h-[88px] bg-input border border-subtle rounded-xs overflow-hidden flex items-center justify-center text-[11px] text-secondary">
      {src ? <img src={src} alt={`Face ${face.id}`} className="w-full h-full object-cover" /> : 'Offline'}
    </div>
  );
}

interface FaceReviewModalProps {
  personId: number | null;
  onClose?: (dirty: boolean) => void;
}

export default function FaceReviewModal({ personId, onClose }: FaceReviewModalProps) {
  const { notify } = useApp();
  const [person, setPerson] = useState<PersonRecord | null>(null);
  const [faces, setFaces] = useState<FaceRecord[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [persons, setPersons] = useState<PersonRecord[]>([]);
  const [editingFace, setEditingFace] = useState<FaceRecord | null>(null);
  const [editMode, setEditMode] = useState<'name' | 'assign'>('name');
  const [nameInput, setNameInput] = useState('');
  const [assignQuery, setAssignQuery] = useState('');
  const dirtyRef = useRef(false);

  const loadFaces = useCallback(async (offset = 0, append = false) => {
    try {
      const limit = append ? PAGE : Math.max(PAGE, faces.length || PAGE);
      const list = await rpc<FaceRecord[]>('faces.list', { person_id: personId, limit, offset });
      const rows = list || [];
      setFaces((prev) => (append ? [...prev, ...rows] : rows));
      setHasMore(rows.length >= limit);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  }, [personId, faces.length, notify]);

  useEffect(() => {
    if (personId !== null) {
      rpc<PersonRecord | null>('persons.get', { person_id: personId }).then((p) => setPerson(p)).catch(() => {});
    }
    rpc<PersonRecord[]>('persons.list').then((list) => setPersons(list || [])).catch(() => {});
    loadFaces(0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personId]);

  const handleConfirmAll = async () => {
    if (personId === null) return;
    try {
      const res = await rpc<{ confirmed?: number }>('persons.confirm', { person_id: personId });
      dirtyRef.current = true;
      notify(`${res.confirmed || 0} face(s) confirmed.`, 'success');
      loadFaces(0, false);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const handleNameSubmit = async () => {
    if (!editingFace || !nameInput.trim()) return;
    try {
      await rpc('faces.name', { face_id: editingFace.id, name: nameInput.trim() });
      dirtyRef.current = true;
      setEditingFace(null);
      loadFaces(0, false);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const handleAssign = async (faceId: number, targetPersonId: number | null) => {
    try {
      await rpc('faces.assign', { face_id: faceId, person_id: targetPersonId });
      dirtyRef.current = true;
      setEditingFace(null);
      loadFaces(0, false);
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  };

  const assignablePersons = persons.filter(
    (p) => p.id !== personId && String(p.name || '').toLowerCase().includes(assignQuery.trim().toLowerCase()),
  );

  return (
    <ModalShell
      title={person ? `Review Faces: ${person.name}` : 'Unassigned Faces'}
      subtitle={
        personId === null
          ? 'Faces removed from people or not yet grouped. Name them or assign to a person.'
          : 'Move misgrouped faces elsewhere or confirm to lock face box labels.'
      }
      size="lg"
      onClose={() => onClose?.(dirtyRef.current)}
      footer={
        <div className="w-full flex items-center justify-between">
          <div>
            {hasMore && (
              <button type="button" onClick={() => loadFaces(faces.length, true)} className="h-8 px-3 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                Load More
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {personId !== null && (
              <button type="button" onClick={handleConfirmAll} className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover">
                <Check className="w-3.5 h-3.5" strokeWidth={1.8} />
                <span>Confirm All Faces</span>
              </button>
            )}
            <button type="button" onClick={() => onClose?.(dirtyRef.current)} className="h-8 px-3 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
              Close
            </button>
          </div>
        </div>
      }
    >
      {editingFace && (
        <div className="p-3 bg-elevated border border-accent rounded-xs flex flex-col gap-2 shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-primary">
              {editMode === 'name' ? `Name Face #${editingFace.id}` : `Assign Face #${editingFace.id} to Person`}
            </span>
            <button type="button" onClick={() => setEditingFace(null)} className="text-xs text-secondary hover:text-primary">Cancel</button>
          </div>
          {editMode === 'name' ? (
            <div className="flex gap-2">
              <input
                type="text"
                autoFocus
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleNameSubmit(); }}
                placeholder="Enter person name..."
                className="flex-1 h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent"
              />
              <button type="button" onClick={handleNameSubmit} className="h-8 px-3 bg-accent text-accent-text rounded-xs text-xs font-medium">
                Save
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <input
                type="text"
                autoFocus
                value={assignQuery}
                onChange={(e) => setAssignQuery(e.target.value)}
                placeholder="Search person by name..."
                className="h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary focus:outline-none focus:border-accent"
              />
              <div className="max-h-36 overflow-y-auto flex flex-col gap-1">
                {assignablePersons.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleAssign(editingFace.id, p.id)}
                    className="px-2.5 py-1.5 rounded-xs text-left text-xs text-primary hover:bg-card flex items-center justify-between"
                  >
                    <span>{p.name}</span>
                    <span className="font-mono text-[11px] text-secondary">#{p.id} · {p.image_count || 0} photos</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {faces.length === 0 ? (
        <div className="py-12 text-center text-xs text-secondary">No faces here.</div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(124px,1fr))] gap-2.5">
          {faces.map((f) => (
            <div key={f.id} className="bg-elevated border border-subtle rounded-xs p-2 flex flex-col items-center gap-1.5">
              <FaceThumb face={f} />
              <div className="text-[11px] font-mono text-secondary flex items-center gap-1">
                <span>{Math.round(Number(f.confidence || 0) * 100)}%</span>
                {Boolean(f.locked) && <Check className="w-3 h-3 text-success" strokeWidth={2} />}
              </div>
              <button type="button" onClick={() => { setEditingFace(f); setEditMode('name'); setNameInput(''); }} className="w-full h-6 rounded-xs border border-hairline bg-card text-[11px] text-primary hover:border-accent">
                Name...
              </button>
              <button type="button" onClick={() => { setEditingFace(f); setEditMode('assign'); setAssignQuery(''); }} className="w-full h-6 rounded-xs border border-hairline bg-card text-[11px] text-primary hover:border-accent">
                {personId !== null ? 'Move to...' : 'Assign...'}
              </button>
              {personId !== null && (
                <button type="button" onClick={() => handleAssign(f.id, null)} className="w-full h-6 rounded-xs border border-transparent text-[11px] text-danger hover:bg-danger-bg">
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </ModalShell>
  );
}
