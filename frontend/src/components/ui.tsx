'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronRight, HelpCircle, Info, Loader2 } from 'lucide-react';
import { DECISION_STYLES, decisionLabel } from '@/lib/defects';

export function PageHeader({
  title,
  subtitle,
  actions,
  badge,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  badge?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6 pb-4 border-b border-slate-200/80">
      <div>
        {badge && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold tracking-wider uppercase bg-blue-50 text-[#0075de] border border-blue-200/70 mb-2">
            {badge}
          </span>
        )}
        <h1 className="text-2xl sm:text-[26px] font-extrabold tracking-tight text-slate-900 leading-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="text-[13px] text-slate-500 mt-1 max-w-3xl leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  children,
  actions,
  className = '',
  icon,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}) {
  return (
    <section className={`elevation-card ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3 min-w-0">
            {icon && (
              <div className="w-8 h-8 rounded-xl bg-slate-100/90 text-slate-600 flex items-center justify-center shrink-0 shadow-xs">
                {icon}
              </div>
            )}
            <div className="min-w-0">
              {title && <h2 className="text-[14px] font-bold text-slate-900 tracking-tight truncate">{title}</h2>}
              {subtitle && <p className="text-[11px] text-slate-500 mt-0.5 truncate">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  explanation,
  accent = 'blue',
  icon,
  trend,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  explanation?: string;
  accent?: 'blue' | 'emerald' | 'amber' | 'rose' | 'purple' | 'slate';
  icon?: React.ReactNode;
  trend?: string;
}) {
  const accentGradient = {
    blue: 'from-[#0075de] to-cyan-500',
    emerald: 'from-emerald-500 to-teal-400',
    amber: 'from-amber-500 to-yellow-400',
    rose: 'from-rose-500 to-red-400',
    purple: 'from-purple-600 to-indigo-500',
    slate: 'from-slate-600 to-slate-400',
  }[accent];

  const iconTint = {
    blue: 'bg-blue-50 text-[#0075de]',
    emerald: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    rose: 'bg-rose-50 text-rose-600',
    purple: 'bg-purple-50 text-purple-600',
    slate: 'bg-slate-50 text-slate-600',
  }[accent];

  return (
    <div className="elevation-card relative overflow-hidden p-4.5 flex flex-col justify-between group">
      {/* Top Gradient Stripe */}
      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${accentGradient}`} />

      {/* Watermarked Icon in background */}
      {icon && (
        <div className="absolute right-2 -bottom-2 w-16 h-16 opacity-5 group-hover:opacity-10 group-hover:scale-110 transition-all pointer-events-none flex items-center justify-center text-slate-900">
          {icon}
        </div>
      )}

      <div>
        <div className="flex items-center justify-between gap-2 mb-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
          {icon && (
            <div className={`w-7 h-7 rounded-lg ${iconTint} flex items-center justify-center transition-transform group-hover:scale-105`}>
              {icon}
            </div>
          )}
        </div>
        <div className="flex items-baseline gap-2">
          <p className="text-3xl font-extrabold tracking-tight text-slate-900 tabular-nums">{value}</p>
          {trend && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
              {trend}
            </span>
          )}
        </div>
      </div>

      {(hint || explanation) && (
        <div className="mt-3 pt-2.5 border-t border-slate-100/80 flex items-start gap-1.5">
          <p className="text-[11px] text-slate-500 leading-tight">
            {explanation || hint}
          </p>
        </div>
      )}
    </div>
  );
}

export function Button({
  variant = 'secondary',
  className = '',
  icon,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger';
  icon?: React.ReactNode;
}) {
  const styles = {
    primary:
      'bg-gradient-to-r from-[#0075de] to-[#0060b8] text-white shadow-xs hover:shadow-md hover:brightness-105 border border-[#0060b8]',
    secondary:
      'bg-white text-slate-700 border border-slate-200/90 hover:bg-slate-50 hover:border-slate-300 shadow-xs',
    danger:
      'bg-white text-rose-700 border border-rose-200 hover:bg-rose-50 shadow-xs',
  }[variant];

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition-all active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
    </button>
  );
}

export const inputClass =
  'w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-[13px] text-slate-800 placeholder-slate-400 outline-none transition-all focus:border-[#0075de] focus:ring-3 focus:ring-[#0075de]/15 shadow-2xs';

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="block text-[11px] font-bold text-slate-700 tracking-tight">{label}</span>
        {hint && <span className="text-[10px] text-slate-400 font-medium">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

export function Banner({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'error'; children: React.ReactNode }) {
  const style = {
    info: 'bg-blue-50/90 border-blue-200/90 text-blue-900',
    warn: 'bg-amber-50/90 border-amber-200/90 text-amber-950',
    error: 'bg-rose-50/90 border-rose-200/90 text-rose-950',
  }[tone];

  const icon = {
    info: <Info className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />,
    warn: <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />,
    error: <AlertCircle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />,
  }[tone];

  return (
    <div className={`flex items-start gap-3 rounded-2xl border p-4 text-xs shadow-xs ${style}`}>
      {icon}
      <div className="leading-relaxed font-medium">{children}</div>
    </div>
  );
}

export function SimulatedBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md bg-purple-50 text-purple-700 border border-purple-200/70">
      SIMULATED
    </span>
  );
}

export function DecisionBadge({ decision }: { decision?: string | null }) {
  const dec = (decision || '').toUpperCase();

  if (dec === 'PASS') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-extrabold px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/90 shadow-2xs">
        <span className="w-2 h-2 rounded-full bg-emerald-500 live-beacon" />
        PASS
      </span>
    );
  }
  if (dec === 'REJECT') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-extrabold px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200/90 shadow-2xs">
        <span className="w-2 h-2 rounded-full bg-rose-500 live-beacon-rose" />
        REJECT
      </span>
    );
  }
  if (dec === 'REVIEW' || dec === 'FLAGGED') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-extrabold px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200/90 shadow-2xs">
        <span className="w-2 h-2 rounded-full bg-amber-500 live-beacon-amber" />
        REVIEW
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${DECISION_STYLES[decision || ''] || 'bg-slate-50 text-slate-700 border-slate-200'}`}>
      {decisionLabel(decision)}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-12 text-center flex flex-col items-center justify-center">
      <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 mb-3 shadow-xs">
        <Info className="w-6 h-6" />
      </div>
      <p className="text-xs font-medium text-slate-500 max-w-sm">{children}</p>
    </div>
  );
}

export function Table({ columns, rows }: { columns: React.ReactNode[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto border border-slate-200/80 rounded-2xl bg-white shadow-2xs">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-slate-500 bg-slate-50/90 border-b border-slate-200/80">
            {columns.map((c, i) => (
              <th key={i} className="py-3 px-4 font-bold tracking-wider whitespace-nowrap text-[10px] uppercase text-slate-600">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={i} className="hover:bg-blue-50/40 transition-colors group">
              {row.map((cell, j) => (
                <td key={j} className="py-3 px-4 text-slate-700 tabular-nums">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Loads data with visible loading and error states, so a failed API call never looks like empty data. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const depsKey = JSON.stringify(deps);
  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    reload();
    if (!pollMs) return;
    const timer = setInterval(reload, pollMs);
    return () => clearInterval(timer);
  }, [reload, pollMs, depsKey]);
  return { data, error, loading, reload };
}

export function LoadState({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <Banner tone="error">{error}</Banner>;
  if (loading) {
    return (
      <div className="flex items-center gap-2.5 text-xs text-slate-500 py-10 justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-[#0075de]" /> Loading operational data...
      </div>
    );
  }
  return null;
}
