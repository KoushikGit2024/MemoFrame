import { useApp } from "../context/AppContext";
import { basename, formatDate, formatDims, formatQuality } from "../lib/utils";
import type { PhotoRecord } from "../types/memoframe";

interface PhotoTableProps {
  photos: PhotoRecord[];
  onOpen?: (photo: PhotoRecord) => void;
}

export default function PhotoTable({ photos, onOpen }: PhotoTableProps) {
  const { prefs } = useApp();
  const dateOpts = { timezone: prefs.timezone, dateFormat: prefs.dateFormat };
  return (
    <div className="flex-1 min-h-0 overflow-auto border border-subtle rounded-sm bg-card">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="sticky top-0 z-10 bg-elevated border-b border-hairline text-[11px] uppercase tracking-wider text-secondary">
            <th className="py-2 px-2.5 text-center font-semibold w-14">ID</th>
            <th className="py-2 px-2.5 text-left font-semibold">Filename</th>
            <th className="py-2 px-2.5 text-left font-semibold w-40">Date</th>
            <th className="py-2 px-2.5 text-center font-semibold w-16">Faces</th>
            <th className="py-2 px-2.5 text-center font-semibold w-20">Quality</th>
            <th className="py-2 px-2.5 text-left font-semibold w-28">Dimensions</th>
            <th className="py-2 px-2.5 text-center font-semibold w-20">Format</th>
            <th className="py-2 px-2.5 text-left font-semibold">Path</th>
          </tr>
        </thead>
        <tbody>
          {photos.map(p => {
            const faceCount = p.faces?.length ?? p.face_count ?? 0;
            const q = p.quality !== null && p.quality !== undefined ? Number(p.quality) : null;
            const qualityColor =
              q === null || Number.isNaN(q)
                ? "text-secondary"
                : q >= 80
                  ? "text-success"
                  : q < 40
                    ? "text-amber"
                    : "text-primary";

            return (
              <tr
                key={p.id}
                onDoubleClick={() => onOpen?.(p)}
                onClick={() => onOpen?.(p)}
                className="border-b border-subtle hover:bg-elevated/80 cursor-pointer transition-colors"
              >
                <td className="py-2 px-2.5 text-center font-mono text-secondary tabular-nums">
                  {p.id}
                </td>
                <td
                  className="py-2 px-2.5 font-medium text-primary max-w-[220px] truncate"
                  title={p.path}
                >
                  {basename(p.path)}
                </td>
                <td className="py-2 px-2.5 font-mono text-secondary tabular-nums">
                  {formatDate(p.effective_ts || p.exif_ts, dateOpts)}
                </td>
                <td
                  className={`py-2 px-2.5 text-center font-mono tabular-nums ${faceCount > 0 ? "text-violet font-medium" : "text-secondary"}`}
                >
                  {faceCount}
                </td>
                <td className={`py-2 px-2.5 text-center font-mono tabular-nums ${qualityColor}`}>
                  {formatQuality(p.quality)}
                </td>
                <td className="py-2 px-2.5 font-mono text-secondary tabular-nums">
                  {formatDims(p.width, p.height)}
                </td>
                <td className="py-2 px-2.5 text-center font-mono uppercase text-secondary">
                  {p.format || "—"}
                </td>
                <td
                  className="py-2 px-2.5 text-secondary max-w-[300px] truncate font-mono text-[11px]"
                  title={p.path}
                >
                  {p.path || "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
