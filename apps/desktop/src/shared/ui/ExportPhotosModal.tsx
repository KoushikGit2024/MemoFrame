import { useState } from "react";
import { CheckCircle2, Download, FolderOpen, Loader2 } from "lucide-react";
import { useApp } from "../context/AppContext";
import { revealFile, rpc, selectFolder } from "../lib/api";
import ModalShell from "./ModalShell";

interface ExportResult {
  exported: number;
  failed: number;
  dest_dir: string;
  errors?: string[];
}

export default function ExportPhotosModal() {
  const { exportRequest, closeExportModal, notify } = useApp();
  const [destDir, setDestDir] = useState("");
  const [format, setFormat] = useState<"original" | "jpeg" | "webp" | "png">("original");
  const [quality, setQuality] = useState(92);
  const [maxSide, setMaxSide] = useState<string>("");
  const [stripMetadata, setStripMetadata] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);

  if (!exportRequest) return null;

  const count = exportRequest.photoIds.length;

  const handlePickFolder = async () => {
    const picked = await selectFolder();
    if (picked) {
      setDestDir(picked);
      setResult(null);
    }
  };

  const handleExport = async () => {
    if (!destDir || exporting || count === 0) return;
    setExporting(true);
    setResult(null);
    try {
      const res = await rpc<ExportResult>("photos.export", {
        image_ids: exportRequest.photoIds,
        dest_dir: destDir,
        format,
        quality,
        max_side: maxSide ? Number(maxSide) : null,
        strip_metadata: stripMetadata,
      });
      setResult(res);
      notify(
        `Exported ${res.exported} photo${res.exported === 1 ? "" : "s"}${res.failed ? ` (${res.failed} failed)` : ""}.`,
        res.failed > 0 && res.exported === 0 ? "error" : "success"
      );
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setExporting(false);
    }
  };

  const handleClose = () => {
    if (exporting) return;
    setResult(null);
    closeExportModal();
  };

  return (
    <ModalShell
      title={`Export ${exportRequest.label || `${count} Photo${count === 1 ? "" : "s"}`}`}
      subtitle="Original photos on disk are never modified or moved."
      size="sm"
      onClose={handleClose}
      footer={
        <>
          <button
            type="button"
            disabled={exporting}
            onClick={handleClose}
            className="btn-neutral h-8 px-3 text-xs"
          >
            {result ? "Done" : "Cancel"}
          </button>
          <button
            type="button"
            disabled={!destDir || exporting || count === 0}
            onClick={() => void handleExport()}
            className="btn-primary h-8 px-3.5 text-xs"
          >
            {exporting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" strokeWidth={1.7} />
            )}
            <span>{exporting ? "Exporting..." : `Export ${count} Photo${count === 1 ? "" : "s"}`}</span>
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-secondary">Destination Folder</span>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              readOnly
              value={destDir}
              placeholder="Choose an export folder..."
              className="flex-1 h-8 px-2.5 bg-input border border-hairline rounded-xs text-xs text-primary font-mono truncate"
            />
            <button
              type="button"
              disabled={exporting}
              onClick={() => void handlePickFolder()}
              className="btn-neutral h-8 px-2.5 text-xs shrink-0"
            >
              <FolderOpen className="w-3.5 h-3.5" />
              <span>Browse</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-secondary font-medium">Format</span>
            <select
              disabled={exporting}
              value={format}
              onChange={e => setFormat(e.target.value as "original" | "jpeg" | "webp" | "png")}
              className="h-8 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
            >
              <option value="original">Original Copy</option>
              <option value="jpeg">JPEG (.jpg)</option>
              <option value="webp">WebP (.webp)</option>
              <option value="png">PNG (.png)</option>
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-secondary font-medium">Max Resolution</span>
            <select
              disabled={exporting}
              value={maxSide}
              onChange={e => setMaxSide(e.target.value)}
              className="h-8 px-2 bg-input border border-hairline rounded-xs text-xs text-primary"
            >
              <option value="">Original Size</option>
              <option value="2048">2048 px (High)</option>
              <option value="1600">1600 px (Web)</option>
              <option value="1280">1280 px (Compact)</option>
            </select>
          </label>
        </div>

        {(format === "jpeg" || format === "webp") && (
          <label className="flex flex-col gap-1 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-secondary font-medium">Compression Quality</span>
              <span className="font-mono text-primary">{quality}%</span>
            </div>
            <input
              type="range"
              min={60}
              max={100}
              disabled={exporting}
              value={quality}
              onChange={e => setQuality(Number(e.target.value))}
              className="w-full accent-accent"
            />
          </label>
        )}

        <label className="inline-flex items-center gap-2 text-xs text-primary cursor-pointer">
          <input
            type="checkbox"
            disabled={exporting}
            checked={stripMetadata}
            onChange={e => setStripMetadata(e.target.checked)}
            className="accent-accent"
          />
          <span>Strip EXIF &amp; GPS metadata from exported copies</span>
        </label>

        {result && (
          <div className="p-2.5 bg-success-bg border border-success/50 rounded-xs flex items-center justify-between gap-2 text-xs">
            <span className="inline-flex items-center gap-1.5 text-primary min-w-0">
              <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
              <span className="truncate">
                Exported <strong>{result.exported}</strong> file{result.exported === 1 ? "" : "s"}
                {result.failed > 0 ? ` (${result.failed} failed)` : ""}
              </span>
            </span>
            <button
              type="button"
              onClick={() => void revealFile(result.dest_dir)}
              className="btn-neutral h-7 px-2 text-[11px] shrink-0"
            >
              Open Folder
            </button>
          </div>
        )}
      </div>
    </ModalShell>
  );
}
