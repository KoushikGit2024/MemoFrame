import { FolderSearch, Pause, Play, X } from "lucide-react";
import { useApp } from "../context/AppContext";

export default function StatusBar() {
  const { scan, startScanFolder, togglePauseScan, cancelScan, workspace, connected } = useApp();

  return (
    <footer className="h-9 shrink-0 bg-sidebar border-t border-subtle px-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          disabled={scan.running || !connected}
          onClick={startScanFolder}
          className="btn-secondary h-6 px-2.5 text-[11.5px]"
        >
          <FolderSearch className="w-3.5 h-3.5" strokeWidth={1.6} />
          <span>Scan Folder</span>
        </button>

        {scan.running && (
          <>
            <button
              type="button"
              onClick={togglePauseScan}
              className={`${scan.paused ? "btn-warning" : "btn-neutral"} h-6 px-2 text-[11.5px]`}
            >
              {scan.paused ? (
                <Play className="w-3 h-3" strokeWidth={1.6} />
              ) : (
                <Pause className="w-3 h-3" strokeWidth={1.6} />
              )}
              <span>{scan.paused ? "Resume" : "Pause"}</span>
            </button>
            <button
              type="button"
              onClick={cancelScan}
              className="btn-danger h-6 px-2 text-[11.5px]"
            >
              <X className="w-3 h-3" strokeWidth={1.6} />
              <span>Cancel</span>
            </button>
            <div className="flex items-center gap-2">
              <div className="w-36 h-1.5 bg-elevated border border-subtle rounded-[1px] overflow-hidden">
                <div
                  className={`h-full transition-all duration-150 ${
                    scan.percent >= 100
                      ? "bg-success"
                      : scan.paused
                        ? "bg-amber"
                        : "bg-accent-secondary"
                  }`}
                  style={{ width: `${scan.percent}%` }}
                />
              </div>
              <span className="font-mono text-[11px] text-secondary tabular-nums">
                {scan.percent}%
              </span>
            </div>
          </>
        )}

        <span className="text-xs text-secondary truncate">{scan.label}</span>
      </div>

      <div className="flex items-center gap-2.5 shrink-0">
        <span className="inline-flex items-center gap-1.5 text-[11px] text-secondary">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-success" : "bg-danger"}`} />
          <span>{connected ? "Engine Ready" : "Backend Disconnected"}</span>
        </span>
        {workspace && (
          <span
            title={workspace}
            className="font-mono text-[11px] text-secondary max-w-[260px] truncate hidden md:inline"
          >
            {workspace}
          </span>
        )}
      </div>
    </footer>
  );
}
