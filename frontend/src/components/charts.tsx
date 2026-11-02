'use client';

import React, { useState } from 'react';
import { defectColor, defectLabel } from '@/lib/defects';
import { GroupRow, ParetoRow, TrendPoint, pct } from '@/lib/industrial';
import { Empty } from '@/components/ui';

const INK = '#000000';
const MUTED = '#615d59';
const GRID = '#e6e6e6';
const SERIES = '#0075de';
const LIMIT = '#991B1B';

/** Pareto as ranked bars. Cumulative share is text, because a second axis would mislead. */
export function ParetoBars({ rows }: { rows: ParetoRow[] }) {
  if (!rows.length) return <Empty>No defects recorded in this period.</Empty>;
  const max = rows[0].count;
  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.defect_type} title={`${defectLabel(r.defect_type)}: ${r.count} defects, ${pct(r.share)} of total`}>
          <div className="flex items-baseline justify-between text-xs mb-1">
            <span className="flex items-center gap-2 font-medium text-[#000000]">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: defectColor(r.defect_type) }} />
              {defectLabel(r.defect_type)}
            </span>
            <span className="text-[#615d59] tabular-nums"><b className="text-[#000000]">{r.count}</b> · {pct(r.share, 0)} · cum. {pct(r.cumulative, 0)}</span>
          </div>
          <div className="h-2 bg-[#f6f5f4] rounded">
            <div className="h-full rounded" style={{ width: `${(r.count / max) * 100}%`, background: defectColor(r.defect_type) }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Flagged rate (rejected or awaiting review) per group, ordered by the API. One measure on one scale. */
export function GroupBars({ rows, empty }: { rows: GroupRow[]; empty?: string }) {
  if (!rows.length) return <Empty>{empty || 'No units recorded with this attribute.'}</Empty>;
  const max = Math.max(...rows.map((r) => r.flagged_rate ?? r.rejection_rate ?? 0), 0.01);
  return (
    <div className="space-y-2.5">
      {rows.slice(0, 10).map((r) => (
        <div key={r.group} title={`${r.group}: ${r.rejected} of ${r.units} rejected`}>
          <div className="flex items-baseline justify-between text-xs mb-1">
            <span className="font-medium text-[#000000] truncate">{r.group}</span>
            <span className="text-[#615d59] tabular-nums shrink-0 ml-2">
              <b className="text-[#000000]">{pct(r.flagged_rate ?? r.rejection_rate)}</b> · {r.units} units{r.top_defect ? ` · ${defectLabel(r.top_defect)}` : ''}
            </span>
          </div>
          <div className="h-2 bg-[#f6f5f4] rounded">
            <div className="h-full rounded" style={{ width: `${((r.flagged_rate ?? r.rejection_rate ?? 0) / max) * 100}%`, background: SERIES }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** p-chart: rejection rate over time with its upper control limit. */
export function ControlChart({ points }: { points: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return <Empty>At least two periods are needed to draw a trend.</Empty>;
  const W = 720, H = 220, L = 44, R = 12, T = 12, B = 26;
  const top = Math.max(0.05, ...points.map((p) => Math.max(p.rate, p.ucl ?? 0))) * 1.15;
  const x = (i: number) => L + (i / (points.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / top) * (H - T - B);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.rate)}`).join(' ');
  const limits = points.map((p, i) => ({ p, i })).filter(({ p }) => p.ucl !== null);
  const limitPath = limits.map(({ p, i }, k) => `${k ? 'L' : 'M'}${x(i)},${y(p.ucl as number)}`).join(' ');
  const ticks = [0, top / 2, top];
  const active = hover === null ? null : points[hover];
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Flagged rate by period with upper control limit">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
            <text x={L - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill={MUTED}>{(t * 100).toFixed(0)}%</text>
          </g>
        ))}
        {limitPath && <path d={limitPath} fill="none" stroke={LIMIT} strokeWidth={1.5} strokeDasharray="5 4" />}
        <path d={line} fill="none" stroke={SERIES} strokeWidth={2} strokeLinejoin="round" />
        {points.map((p, i) => (
          <g key={p.period}>
            {p.out_of_control && <circle cx={x(i)} cy={y(p.rate)} r={5} fill={LIMIT} stroke="#fff" strokeWidth={2} />}
            <rect x={x(i) - (W - L - R) / points.length / 2} y={T} width={(W - L - R) / points.length} height={H - T - B}
              fill="transparent" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
          </g>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke={INK} strokeOpacity={0.2} />}
        <text x={L} y={H - 8} fontSize={10} fill={MUTED}>{points[0].period}</text>
        <text x={W - R} y={H - 8} textAnchor="end" fontSize={10} fill={MUTED}>{points[points.length - 1].period}</text>
      </svg>
      <div className="flex items-center gap-4 text-[11px] text-[#615d59] mt-1">
        <span className="flex items-center gap-1.5"><span className="w-4 h-0.5" style={{ background: SERIES }} />Flagged rate</span>
        <span className="flex items-center gap-1.5"><span className="w-4 border-t-2 border-dashed" style={{ borderColor: LIMIT }} />Upper control limit</span>
        {active && <span className="ml-auto tabular-nums text-[#000000]">{active.period}: {pct(active.rate)} of {active.inspected}{active.ucl !== null ? `, limit ${pct(active.ucl)}` : ''}</span>}
      </div>
    </div>
  );
}

/** Where defects fall on the part, as a 3×3 single-hue grid. */
export function Hotspot({ grid, region, share }: { grid: number[][]; region: string | null; share: number }) {
  const max = Math.max(1, ...grid.flat());
  return (
    <div className="flex items-center gap-4">
      <div className="grid grid-cols-3 gap-0.5 w-32 shrink-0">
        {grid.flat().map((v, i) => (
          <div key={i} title={`${v} defects`} className="aspect-square flex items-center justify-center text-[11px] tabular-nums rounded-sm"
            style={{ background: `rgba(0,117,222,${0.06 + 0.8 * (v / max)})`, color: v / max > 0.55 ? '#fff' : '#31302e' }}>
            {v}
          </div>
        ))}
      </div>
      <p className="text-xs text-[#615d59]">
        {region ? <>Most defects fall in the <b className="text-[#000000]">{region}</b> region ({pct(share, 0)}). A repeated position can point to a fixed contact point.</> : 'No located defects yet.'}
      </p>
    </div>
  );
}
