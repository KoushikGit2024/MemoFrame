import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Layers, Loader2, Maximize2, RefreshCw, Star } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { mediaUrl, rpc } from '../lib/api';
import { formatQuality, LatestTask } from '../lib/utils';
import type { BurstRecord, PhotoRecord } from '../types/memoframe';
import EmptyState from '../components/EmptyState';

export default function BurstsView() {
  const { connected, dataVersion, invalidate, notify, setLightboxPhoto } = useApp();
  const [bursts, setBursts] = useState<BurstRecord[]>([]);
  const [burstIdx, setBurstIdx] = useState(0);
  const [frames, setFrames] = useState<PhotoRecord[]>([]);
  const [frameIdx, setFrameIdx] = useState(0);
  const [busy, setBusy] = useState(false);

  const listLoader = useRef(new LatestTask());
  const frameLoader = useRef(new LatestTask());

  const loadBursts = useCallback(() => {
    if (!connected) return;
    listLoader.current.run(
      () => rpc<BurstRecord[]>('bursts.list'),
      (res) => {
        const list = res || [];
        setBursts(list);
        setBurstIdx((idx) => (list.length ? Math.min(idx, list.length - 1) : 0));
        if (!list.length) setFrames([]);
      },
      (err) => notify(err.message, 'error'),
    );
  }, [connected, notify]);

  useEffect(() => { loadBursts(); }, [loadBursts, dataVersion]);

  const activeBurst = bursts[burstIdx] || null;

  useEffect(() => {
    if (!connected || !activeBurst) return;
    frameLoader.current.run(
      () => rpc<PhotoRecord[]>('bursts.frames', { burst_id: activeBurst.id, best_image_id: activeBurst.best_image_id }),
      (res) => {
        const list = res || [];
        setFrames(list);
        const best = list.findIndex((f) => f.suggested);
        setFrameIdx(best >= 0 ? best : 0);
      },
      (err) => notify(err.message, 'error'),
    );
  }, [connected, activeBurst, notify]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!frames.length) return;
      if (e.key === 'ArrowLeft') setFrameIdx((i) => Math.max(0, i - 1));
      if (e.key === 'ArrowRight') setFrameIdx((i) => Math.min(frames.length - 1, i + 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [frames.length]);

  const currentFrame = frames[frameIdx] || null;

  const handleKeepCurrent = async () => {
    if (!currentFrame || busy) return;
    setBusy(true);
    try {
      const hideIds = frames.filter((f) => f.id !== currentFrame.id).map((f) => f.id);
      await rpc('bursts.keep_one', { keep_id: currentFrame.id, hide_ids: hideIds });
      notify(`Kept frame #${frameIdx + 1} and hid ${hideIds.length} other frame(s).`, 'success');
      invalidate();
      loadBursts();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleKeepAll = async () => {
    if (!activeBurst || busy) return;
    setBusy(true);
    try {
      await rpc('bursts.keep_all', { best_image_id: activeBurst.best_image_id });
      notify('Marked burst as reviewed (all frames kept).', 'success');
      invalidate();
      loadBursts();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col px-5 pt-4 pb-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-[17px] font-semibold text-primary">Burst Sequences ({bursts.length})</h1>
          <p className="text-xs text-secondary mt-0.5">Scrub frames with Left/Right arrow keys, keep the sharpest frame, and hide the rest.</p>
        </div>
        <button type="button" onClick={loadBursts} className="h-8 px-2.5 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
          <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.6} />
          <span>Refresh</span>
        </button>
      </div>

      {bursts.length === 0 ? (
        <EmptyState icon={Layers} title="No Bursts to Review" description="All detected burst sequences have been resolved or none exist yet." />
      ) : (
        <div className="flex-1 min-h-0 flex gap-3 overflow-hidden">
          <div className="w-56 shrink-0 bg-card border border-subtle rounded-sm flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-subtle text-[10px] font-semibold uppercase tracking-[0.08em] text-secondary">
              Sequences
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 flex flex-col gap-0.5">
              {bursts.map((b, idx) => (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => setBurstIdx(idx)}
                  className={`w-full px-2.5 py-2 rounded-xs border text-left flex items-center justify-between text-xs ${
                    idx === burstIdx
                      ? 'bg-accent-light border-accent text-primary font-medium'
                      : 'bg-transparent border-transparent text-primary hover:bg-elevated'
                  }`}
                >
                  <span>Burst #{idx + 1}</span>
                  <span className="font-mono text-[11px] text-secondary">{b.image_count} frames</span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 min-w-0 flex flex-col gap-2.5 overflow-hidden">
            <div className="flex-1 min-h-0 bg-input border border-subtle rounded-sm flex items-center justify-center overflow-hidden p-2">
              {currentFrame ? (
                <img src={mediaUrl(currentFrame.path || currentFrame.thumb_path)} alt={`Frame ${frameIdx + 1}`} className="max-w-full max-h-full object-contain" />
              ) : (
                <span className="text-xs text-accent inline-flex items-center gap-1.5 animate-pulse">
                  <Loader2 className="w-4 h-4 animate-spin text-accent" />
                  <span>Loading frames...</span>
                </span>
              )}
            </div>

            <div className="flex items-center justify-between text-xs text-secondary shrink-0">
              <span className="font-mono tabular-nums">
                {currentFrame ? `Frame ${frameIdx + 1} of ${frames.length} · Quality ${formatQuality(currentFrame.quality)}` : ''}
              </span>
              {currentFrame?.suggested && (
                <span className="inline-flex items-center gap-1 text-accent font-medium">
                  <Star className="w-3.5 h-3.5" strokeWidth={1.7} />
                  <span>Suggested (sharpest)</span>
                </span>
              )}
            </div>

            <input
              type="range"
              min={0}
              max={Math.max(0, frames.length - 1)}
              value={frameIdx}
              onChange={(e) => setFrameIdx(Number(e.target.value))}
              className="w-full accent-accent cursor-pointer"
            />

            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 shrink-0">
              {frames.map((f, idx) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFrameIdx(idx)}
                  className={`w-[84px] shrink-0 p-1 rounded-xs border flex flex-col items-center gap-1 ${
                    idx === frameIdx ? 'border-accent bg-accent-light' : 'border-subtle bg-card hover:border-hairline'
                  }`}
                >
                  <img src={mediaUrl(f.thumb_path || f.path)} alt={`Thumb ${idx + 1}`} className="w-[74px] h-[52px] object-cover bg-input" />
                  <span className="text-[10.5px] font-mono text-primary inline-flex items-center gap-0.5">
                    {f.suggested && <Star className="w-2.5 h-2.5 text-accent" strokeWidth={2} />}
                    <span>{idx + 1}</span>
                  </span>
                </button>
              ))}
            </div>

            <div className="flex items-center justify-between gap-2 flex-wrap shrink-0">
              <div className="flex items-center gap-1.5">
                <button type="button" disabled={frameIdx <= 0} onClick={() => setFrameIdx((i) => Math.max(0, i - 1))} className="h-8 w-8 inline-flex items-center justify-center rounded-xs border border-hairline bg-card text-primary hover:bg-elevated disabled:opacity-40">
                  <ChevronLeft className="w-4 h-4" strokeWidth={1.6} />
                </button>
                <button type="button" disabled={frameIdx >= frames.length - 1} onClick={() => setFrameIdx((i) => Math.min(frames.length - 1, i + 1))} className="h-8 w-8 inline-flex items-center justify-center rounded-xs border border-hairline bg-card text-primary hover:bg-elevated disabled:opacity-40">
                  <ChevronRight className="w-4 h-4" strokeWidth={1.6} />
                </button>
                <button
                  type="button"
                  onClick={() => { const best = frames.findIndex((f) => f.suggested); if (best >= 0) setFrameIdx(best); }}
                  className="h-8 px-2.5 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated"
                >
                  <Star className="w-3.5 h-3.5 text-accent" strokeWidth={1.6} />
                  <span>Suggested</span>
                </button>
                <button type="button" disabled={!currentFrame} onClick={() => currentFrame && setLightboxPhoto(currentFrame)} className="h-8 px-2.5 inline-flex items-center gap-1.5 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated">
                  <Maximize2 className="w-3.5 h-3.5" strokeWidth={1.6} />
                  <span>Open Full Size</span>
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={handleKeepAll}
                  className="h-8 px-3 rounded-xs border border-hairline bg-card text-xs text-primary hover:bg-elevated disabled:opacity-50 inline-flex items-center gap-1.5 transition-colors"
                >
                  {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-secondary" />}
                  <span>{busy ? 'Processing...' : 'Keep All'}</span>
                </button>
                <button
                  type="button"
                  disabled={busy || !currentFrame}
                  onClick={handleKeepCurrent}
                  className="h-8 px-3 inline-flex items-center gap-1.5 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover disabled:opacity-50 transition-colors"
                >
                  {busy ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-text" />
                  ) : (
                    <Check className="w-3.5 h-3.5" strokeWidth={1.8} />
                  )}
                  <span>{busy ? 'Updating...' : 'Keep This Frame, Hide Rest'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
