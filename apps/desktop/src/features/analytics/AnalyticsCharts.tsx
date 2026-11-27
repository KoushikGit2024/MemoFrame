import { useState } from "react";

export interface ChartPoint {
  label: string;
  value: number;
  accent?: string;
}

const PALETTE = [
  "var(--accent)",
  "var(--accent-secondary)",
  "var(--violet)",
  "var(--amber)",
  "var(--success)",
  "var(--danger)",
];

export function EmptyChart({ message = "No recorded data for this range yet." }: { message?: string }) {
  return (
    <div className="h-44 flex items-center justify-center border border-dashed border-subtle rounded-xs text-xs text-secondary px-4 text-center">
      {message}
    </div>
  );
}

export function TrendLineChart({
  data,
  color = "var(--accent-secondary)",
  unit = "",
}: {
  data: ChartPoint[];
  color?: string;
  unit?: string;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  if (!data.length) return <EmptyChart />;

  const w = 560;
  const h = 180;
  const padL = 40;
  const padR = 16;
  const padT = 16;
  const padB = 30;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const maxVal = Math.max(1, ...data.map(d => d.value));

  const coords = data.map((d, i) => {
    const x = padL + (data.length === 1 ? plotW / 2 : (i / (data.length - 1)) * plotW);
    const y = padT + plotH - (d.value / maxVal) * plotH;
    return { x, y, ...d };
  });

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const areaPath =
    `${linePath} L${coords[coords.length - 1].x.toFixed(1)},${(padT + plotH).toFixed(1)} ` +
    `L${coords[0].x.toFixed(1)},${(padT + plotH).toFixed(1)} Z`;

  const step = Math.max(1, Math.ceil(data.length / 6));
  const active = hoverIdx !== null ? coords[hoverIdx] : null;

  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-44 select-none">
        {[0, 0.5, 1].map(frac => {
          const y = padT + plotH * (1 - frac);
          const val = Math.round(maxVal * frac);
          return (
            <g key={frac}>
              <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="var(--border-subtle)" strokeWidth="1" />
              <text
                x={padL - 6}
                y={y + 4}
                textAnchor="end"
                fontSize="10"
                fill="var(--text-secondary)"
                fontFamily="monospace"
              >
                {val}
              </text>
            </g>
          );
        })}

        <path d={areaPath} fill={color} fillOpacity="0.12" />
        <path d={linePath} fill="none" stroke={color} strokeWidth="2" />

        {coords.map((c, i) => (
          <g key={`${c.label}-${i}`}>
            <circle
              cx={c.x}
              cy={c.y}
              r={hoverIdx === i ? 4.5 : 2.5}
              fill={color}
              className="cursor-pointer"
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => setHoverIdx(null)}
            />
            {(i % step === 0 || i === coords.length - 1) && (
              <text
                x={c.x}
                y={h - 8}
                textAnchor="middle"
                fontSize="10"
                fill="var(--text-secondary)"
                fontFamily="monospace"
              >
                {c.label.slice(-7)}
              </text>
            )}
          </g>
        ))}
      </svg>
      {active && (
        <div className="absolute top-1 right-2 px-2 py-1 rounded-xs bg-elevated border border-hairline text-[11px] font-mono text-primary pointer-events-none">
          {active.label}: <strong>{active.value.toLocaleString()}</strong>
          {unit ? ` ${unit}` : ""}
        </div>
      )}
    </div>
  );
}

export function HorizontalBarChart({
  data,
  color = "var(--accent)",
  unit = "",
}: {
  data: ChartPoint[];
  color?: string;
  unit?: string;
}) {
  if (!data.length) return <EmptyChart />;
  const maxVal = Math.max(1, ...data.map(d => d.value));

  return (
    <div className="flex flex-col gap-2">
      {data.map((d, i) => {
        const pct = Math.max(2, (d.value / maxVal) * 100);
        return (
          <div key={`${d.label}-${i}`} className="flex flex-col gap-0.5">
            <div className="flex items-center justify-between text-xs gap-2">
              <span className="text-primary truncate">{d.label}</span>
              <span className="font-mono text-[11px] text-secondary shrink-0 tabular-nums">
                {d.value.toLocaleString()}
                {unit ? ` ${unit}` : ""}
              </span>
            </div>
            <div className="w-full h-2 bg-input border border-subtle rounded-xs overflow-hidden">
              <div
                className="h-full transition-all duration-200"
                style={{ width: `${pct}%`, backgroundColor: d.accent || color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function HistogramChart({
  data,
  color = "var(--violet)",
}: {
  data: ChartPoint[];
  color?: string;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  if (!data.length || data.every(d => d.value === 0)) return <EmptyChart />;

  const maxVal = Math.max(1, ...data.map(d => d.value));
  const active = hoverIdx !== null ? data[hoverIdx] : null;

  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-36 flex items-end gap-1.5 pt-5 border-b border-subtle px-1">
        {active && (
          <div className="absolute top-0 right-1 px-2 py-0.5 rounded-xs bg-elevated border border-hairline text-[11px] font-mono text-primary">
            {active.label}: <strong>{active.value.toLocaleString()}</strong>
          </div>
        )}
        {data.map((d, i) => {
          const pct = d.value > 0 ? Math.max(4, (d.value / maxVal) * 100) : 0;
          return (
            <div
              key={`${d.label}-${i}`}
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => setHoverIdx(null)}
              className="flex-1 h-full flex flex-col justify-end items-center group cursor-pointer"
            >
              <div
                className="w-full rounded-t-[2px] transition-opacity duration-150 group-hover:opacity-85"
                style={{ height: `${pct}%`, backgroundColor: d.accent || color }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between gap-1 px-1">
        {data.map((d, i) => (
          <span
            key={`lbl-${d.label}-${i}`}
            className="flex-1 text-center text-[10px] font-mono text-secondary truncate"
            title={d.label}
          >
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DonutChart({ data }: { data: ChartPoint[] }) {
  const filtered = data.filter(d => d.value > 0);
  if (!filtered.length) return <EmptyChart />;

  const total = filtered.reduce((acc, d) => acc + d.value, 0);
  const r = 46;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="flex items-center gap-5 flex-wrap">
      <svg viewBox="0 0 120 120" className="w-28 h-28 shrink-0">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--bg-input)" strokeWidth="14" />
        {filtered.map((d, i) => {
          const frac = d.value / total;
          const dash = frac * circ;
          const seg = (
            <circle
              key={`${d.label}-${i}`}
              cx="60"
              cy="60"
              r={r}
              fill="none"
              stroke={d.accent || PALETTE[i % PALETTE.length]}
              strokeWidth="14"
              strokeDasharray={`${dash} ${circ - dash}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 60 60)"
            />
          );
          offset += dash;
          return seg;
        })}
        <text
          x="60"
          y="64"
          textAnchor="middle"
          fontSize="14"
          fontWeight="700"
          fill="var(--text-primary)"
          fontFamily="monospace"
        >
          {total}
        </text>
      </svg>

      <div className="flex-1 min-w-[140px] flex flex-col gap-1.5">
        {filtered.map((d, i) => (
          <div key={`leg-${d.label}-${i}`} className="flex items-center justify-between gap-2 text-xs">
            <span className="inline-flex items-center gap-2 min-w-0">
              <span
                className="w-2.5 h-2.5 rounded-xs shrink-0"
                style={{ backgroundColor: d.accent || PALETTE[i % PALETTE.length] }}
              />
              <span className="text-primary truncate">{d.label}</span>
            </span>
            <span className="font-mono text-[11px] text-secondary shrink-0 tabular-nums">
              {d.value} ({Math.round((d.value / total) * 100)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
