'use client';

import React, { useState } from 'react';
import { defectColor, defectLabel } from '@/lib/defects';
import { GroupRow, ParetoRow, TrendPoint, pct } from '@/lib/industrial';
import { Empty } from '@/components/ui';

const INK = '#0f172a';
const MUTED = '#64748b';
const GRID = '#e2e8f0';
const SERIES = '#0075de';
const LIMIT = '#ef4444';

/** Pareto as ranked bars. Cumulative share is text, because a second axis would mislead. */
export function ParetoBars({ rows }: { rows: ParetoRow[] }) {
  if (!rows.length) return <Empty>No defects recorded in this period.</Empty>;
  const max = rows[0].count;

  return (
    <div className="space-y-3">
      {rows.map((r, idx) => (
        <div key={r.defect_type} title={`${defectLabel(r.defect_type)}: ${r.count} defects, ${pct(r.share)} of total`}>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="flex items-center gap-2 font-semibold text-slate-800">
              <span className="w-5 h-5 rounded-md text-[10px] font-bold bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                #{idx + 1}
              </span>
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: defectColor(r.defect_type) }} />
              <span className="truncate">{defectLabel(r.defect_type)}</span>
            </span>
            <span className="text-slate-500 tabular-nums shrink-0 ml-2">
              <b className="text-slate-900 font-bold">{r.count}</b> units <span className="text-slate-300">·</span> {pct(r.share, 0)} <span className="text-slate-300">·</span> <span className="text-slate-400">cum. {pct(r.cumulative, 0)}</span>
            </span>
          </div>
          <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.max(4, (r.count / max) * 100)}%`,
                background: defectColor(r.defect_type),
              }}
            />
          </div>
        </div>
      ))}
      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
        <span>Principle: 80% of quality yield loss typically stems from the top 20% of defect types.</span>
      </div>
    </div>
  );
}

/** Flagged rate (rejected or awaiting review) per group, ordered by the API. One measure on one scale. */
export function GroupBars({ rows, empty }: { rows: GroupRow[]; empty?: string }) {
  if (!rows.length) return <Empty>{empty || 'No units recorded with this attribute.'}</Empty>;
  const max = Math.max(...rows.map((r) => r.flagged_rate ?? r.rejection_rate ?? 0), 0.01);

  return (
    <div className="space-y-3">
      {rows.slice(0, 10).map((r) => {
        const rate = r.flagged_rate ?? r.rejection_rate ?? 0;
        return (
          <div key={r.group} title={`${r.group}: ${r.rejected} of ${r.units} rejected`}>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="font-semibold text-slate-800 truncate">{r.group}</span>
              <span className="text-slate-500 tabular-nums shrink-0 ml-2">
                <b className="text-slate-900 font-bold">{pct(rate)}</b> flagged <span className="text-slate-300">·</span> {r.units} units
                {r.top_defect ? (
                  <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600 font-medium">
                    {defectLabel(r.top_defect)}
                  </span>
                ) : ''}
              </span>
            </div>
            <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-[#0075de] transition-all duration-500"
                style={{ width: `${Math.max(4, (rate / max) * 100)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** p-chart: rejection rate over time with its upper control limit and area fill. */
export function ControlChart({ points }: { points: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return <Empty>At least two periods are needed to draw a trend.</Empty>;

  const W = 720, H = 220, L = 44, R = 16, T = 16, B = 28;
  const top = Math.max(0.05, ...points.map((p) => Math.max(p.rate, p.ucl ?? 0))) * 1.18;
  const x = (i: number) => L + (i / (points.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / top) * (H - T - B);

  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.rate)}`).join(' ');
  const area = `${line} L ${x(points.length - 1)},${H - B} L ${x(0)},${H - B} Z`;
  const limits = points.map((p, i) => ({ p, i })).filter(({ p }) => p.ucl !== null);
  const limitPath = limits.map(({ p, i }, k) => `${k ? 'L' : 'M'}${x(i)},${y(p.ucl as number)}`).join(' ');
  const ticks = [0, top / 2, top];
  const active = hover === null ? null : points[hover];

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto overflow-visible"
        role="img"
        aria-label="Flagged rate by period with upper control limit"
      >
        <defs>
          <linearGradient id="controlGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0075de" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#0075de" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Horizontal gridlines */}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} strokeDasharray="3 3" />
            <text x={L - 8} y={y(t) + 3} textAnchor="end" fontSize={10} fill={MUTED} fontFamily="Inter, sans-serif">
              {(t * 100).toFixed(0)}%
            </text>
          </g>
        ))}

        {/* Shaded Area */}
        <path d={area} fill="url(#controlGradient)" />

        {/* Upper Control Limit Line */}
        {limitPath && (
          <path d={limitPath} fill="none" stroke={LIMIT} strokeWidth={1.75} strokeDasharray="6 4" />
        )}

        {/* Main Trend Line */}
        <path d={line} fill="none" stroke={SERIES} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

        {/* Interactive Points */}
        {points.map((p, i) => (
          <g key={p.period}>
            {/* Out-of-control pulsing indicator */}
            {p.out_of_control && (
              <g>
                <circle cx={x(i)} cy={y(p.rate)} r={8} fill={LIMIT} fillOpacity={0.25} />
                <circle cx={x(i)} cy={y(p.rate)} r={5} fill={LIMIT} stroke="#ffffff" strokeWidth={2} />
              </g>
            )}
            {!p.out_of_control && (
              <circle
                cx={x(i)}
                cy={y(p.rate)}
                r={hover === i ? 5 : 3.5}
                fill="#ffffff"
                stroke={SERIES}
                strokeWidth={2}
                className="transition-all"
              />
            )}
            <rect
              x={x(i) - (W - L - R) / points.length / 2}
              y={T}
              width={(W - L - R) / points.length}
              height={H - T - B}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              className="cursor-pointer"
            />
          </g>
        ))}

        {/* Hover vertical crosshair */}
        {hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke={INK} strokeOpacity={0.25} strokeDasharray="2 2" />
        )}

        {/* X-axis date labels */}
        <text x={L} y={H - 6} fontSize={10} fill={MUTED} fontFamily="Inter, sans-serif">
          {points[0].period}
        </text>
        <text x={W - R} y={H - 6} textAnchor="end" fontSize={10} fill={MUTED} fontFamily="Inter, sans-serif">
          {points[points.length - 1].period}
        </text>
      </svg>

      {/* Chart Legend & Interactive Active Value */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-500 mt-2 pt-2 border-t border-slate-100">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 font-medium text-slate-700">
            <span className="w-3 h-0.5 rounded bg-[#0075de]" />
            Defect / Flagged Rate
          </span>
          <span className="flex items-center gap-1.5 font-medium text-slate-700">
            <span className="w-3 border-t-2 border-dashed border-rose-500" />
            Control Limit (UCL)
          </span>
        </div>
        {active ? (
          <span className="tabular-nums font-semibold text-slate-900 bg-slate-100 px-2 py-0.5 rounded-md">
            {active.period}: <span className="text-[#0075de]">{pct(active.rate)}</span> flagged ({active.inspected} units)
            {active.ucl !== null && ` · limit: ${pct(active.ucl)}`}
          </span>
        ) : (
          <span className="text-slate-400 text-[10px]">Hover points to inspect exact dates</span>
        )}
      </div>
    </div>
  );
}

/** Where defects fall on the part, as a 3×3 single-hue grid. */
export function Hotspot({ grid, region, share }: { grid: number[][]; region: string | null; share: number }) {
  const max = Math.max(1, ...grid.flat());

  return (
    <div className="flex items-center gap-5">
      <div className="grid grid-cols-3 gap-1.5 w-36 shrink-0 p-1.5 bg-slate-50 rounded-xl border border-slate-200/80">
        {grid.flat().map((v, i) => (
          <div
            key={i}
            title={`Cell ${i + 1}: ${v} defects recorded`}
            className="aspect-square flex items-center justify-center text-xs font-bold tabular-nums rounded-lg transition-transform hover:scale-105"
            style={{
              background: `rgba(0,117,222,${0.08 + 0.82 * (v / max)})`,
              color: v / max > 0.5 ? '#ffffff' : '#0f172a',
            }}
          >
            {v}
          </div>
        ))}
      </div>
      <div className="text-xs text-slate-600 leading-relaxed">
        {region ? (
          <>
            Spatial clustering shows most defects concentrated in the{' '}
            <b className="text-slate-900 font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-100">
              {region}
            </b>{' '}
            zone ({pct(share, 0)} of all defects).
            <span className="block text-[11px] text-slate-400 mt-1">
              Repetitive coordinates indicate mechanical fixture alignment or guide-rail contact friction.
            </span>
          </>
        ) : (
          'No spatially located defects yet.'
        )}
      </div>
    </div>
  );
}
