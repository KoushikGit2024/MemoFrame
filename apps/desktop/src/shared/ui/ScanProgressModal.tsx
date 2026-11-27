import { useEffect, useRef } from "react";
import { Loader2, Pause, Play, X } from "lucide-react";
import { useApp } from "../context/AppContext";

export default function ScanProgressModal() {
  const { scan, scanLogs, togglePauseScan, cancelScan, inOnboarding } = useApp();
  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [scanLogs]);

  // Never pop over the onboarding wizard (which renders its own inline scan progress)
  if (!scan.running || inOnboarding) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-fade-in">
      <div className="w-full max-w-lg bg-card border border-hairline rounded-md shadow-2xl p-4 flex flex-col gap-3 animate-modal-in">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Loader2 className="w-4 h-4 animate-spin text-accent-secondary shrink-0" />
            <h2 className="text-sm font-semibold text-primary truncate">
              {scan.paused ? "Scan Paused" : "Processing Library..."}
            </h2>
          </div>
          <span className="text-xs font-mono text-accent-secondary tabular-nums shrink-0">
            {scan.percent}%
          </span>
        </div>

        <div className="w-full h-2 bg-input border border-subtle rounded-xs overflow-hidden">
          <div
            className={`h-full transition-all duration-200 ${
              scan.paused ? "bg-amber" : "bg-accent-secondary"
            }`}
            style={{ width: `${scan.percent}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-xs text-secondary gap-2">
          <span className="truncate">{scan.label || "Working..."}</span>
          {typeof scan.done === "number" && typeof scan.total === "number" && scan.total > 0 && (
            <span className="font-mono tabular-nums shrink-0">
              {scan.done} / {scan.total}
            </span>
          )}
        </div>

        <div className="bg-input border border-subtle rounded-md p-2.5 h-44 overflow-y-auto font-mono text-[11px] text-secondary flex flex-col gap-0.5">
          {scanLogs.length === 0 ? (
            <span className="opacity-60">Waiting for worker output...</span>
          ) : (
            scanLogs.map((line, i) => (
              <div
                key={i}
                className={line.startsWith("[ERROR]") ? "text-danger" : "text-secondary"}
              >
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={togglePauseScan}
            className={`${scan.paused ? "btn-warning" : "btn-neutral"} h-8 px-3 text-xs`}
          >
            {scan.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            <span>{scan.paused ? "Resume" : "Pause"}</span>
          </button>
          <button type="button" onClick={cancelScan} className="btn-danger h-8 px-3 text-xs">
            <X className="w-3.5 h-3.5" />
            <span>Cancel</span>
          </button>
        </div>
      </div>
    </div>
  );
}
