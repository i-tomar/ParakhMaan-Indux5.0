'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronRight, HelpCircle, Info, Loader2 } from 'lucide-react';
import { DECISION_STYLES, decisionLabel } from '@/lib/defects';

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6 pb-2 border-b border-slate-200/60">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="text-[13px] text-slate-500 mt-1 max-w-2xl leading-relaxed">{subtitle}</p>}
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
          <div className="flex items-center gap-2.5 min-w-0">
            {icon && <div className="text-slate-400 shrink-0">{icon}</div>}
            <div className="min-w-0">
              {title && <h2 className="text-[14px] font-semibold text-slate-900 tracking-tight truncate">{title}</h2>}
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
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  explanation?: string;
  accent?: 'blue' | 'emerald' | 'amber' | 'rose' | 'purple' | 'slate';
  icon?: React.ReactNode;
}) {
  const accentBarColor = {
    blue: 'bg-[#0075de]',
    emerald: 'bg-emerald-500',
    amber: 'bg-amber-500',
    rose: 'bg-rose-500',
    purple: 'bg-purple-500',
    slate: 'bg-slate-400',
  }[accent];

  const accentBadgeBg = {
    blue: 'text-blue-700 bg-blue-50 border-blue-100',
    emerald: 'text-emerald-700 bg-emerald-50 border-emerald-100',
    amber: 'text-amber-700 bg-amber-50 border-amber-100',
    rose: 'text-rose-700 bg-rose-50 border-rose-100',
    purple: 'text-purple-700 bg-purple-50 border-purple-100',
    slate: 'text-slate-700 bg-slate-50 border-slate-100',
  }[accent];

  return (
    <div className="elevation-card relative overflow-hidden p-4 flex flex-col justify-between group">
      {/* Top visual accent stripe */}
      <div className={`absolute top-0 left-0 right-0 h-1 ${accentBarColor}`} />

      <div>
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
          {icon && <div className="text-slate-400 group-hover:text-slate-600 transition-colors">{icon}</div>}
        </div>
        <p className="text-2xl font-bold tracking-tight text-slate-900 tabular-nums">{value}</p>
      </div>

      {(hint || explanation) && (
        <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-start gap-1.5">
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
    primary: 'bg-[#0075de] text-white hover:bg-[#0060b8] border border-[#0060b8] shadow-sm',
    secondary: 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 hover:border-slate-300 shadow-sm',
    danger: 'bg-white text-rose-700 border border-rose-200 hover:bg-rose-50 shadow-sm',
  }[variant];

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
    </button>
  );
}

export const inputClass = 'w-full px-3 py-2 rounded-lg border border-slate-200 bg-white text-[13px] text-slate-800 placeholder-slate-400 outline-none transition-colors focus:border-[#0075de] focus:ring-2 focus:ring-[#0075de]/10';

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1">
        <span className="block text-[11px] font-semibold text-slate-600">{label}</span>
        {hint && <span className="text-[10px] text-slate-400">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

export function Banner({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'error'; children: React.ReactNode }) {
  const style = {
    info: 'bg-blue-50/80 border-blue-200/80 text-blue-900',
    warn: 'bg-amber-50/80 border-amber-200/80 text-amber-900',
    error: 'bg-rose-50/80 border-rose-200/80 text-rose-900',
  }[tone];

  const icon = {
    info: <Info className="w-4 h-4 text-blue-600 mt-0.5 shrink-0" />,
    warn: <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />,
    error: <AlertCircle className="w-4 h-4 text-rose-600 mt-0.5 shrink-0" />,
  }[tone];

  return (
    <div className={`flex items-start gap-2.5 rounded-xl border p-3.5 text-xs shadow-sm ${style}`}>
      {icon}
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

export function SimulatedBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-md bg-purple-50 text-purple-700 border border-purple-200/70">
      SIMULATED
    </span>
  );
}

export function DecisionBadge({ decision }: { decision?: string | null }) {
  const dec = (decision || '').toUpperCase();
  
  if (dec === 'PASS') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
        PASS
      </span>
    );
  }
  if (dec === 'REJECT') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
        REJECT
      </span>
    );
  }
  if (dec === 'REVIEW' || dec === 'FLAGGED') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
        REVIEW
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-md border ${DECISION_STYLES[decision || ''] || 'bg-slate-50 text-slate-700 border-slate-200'}`}>
      {decisionLabel(decision)}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-10 text-center flex flex-col items-center justify-center">
      <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-2">
        <Info className="w-5 h-5" />
      </div>
      <p className="text-xs text-slate-500 max-w-sm">{children}</p>
    </div>
  );
}

export function Table({ columns, rows }: { columns: React.ReactNode[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto border border-slate-100 rounded-xl">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-slate-500 bg-slate-50/80 border-b border-slate-200/80">
            {columns.map((c, i) => (
              <th key={i} className="py-2.5 px-3.5 font-semibold tracking-wider whitespace-nowrap text-[11px] uppercase">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={i} className="hover:bg-slate-50/60 transition-colors">
              {row.map((cell, j) => (
                <td key={j} className="py-2.5 px-3.5 text-slate-700 tabular-nums">
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
  // Always call the latest loader; refetch when the caller's dependency values change.
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
      <div className="flex items-center gap-2 text-xs text-slate-500 py-8 justify-center">
        <Loader2 className="w-4 h-4 animate-spin text-[#0075de]" /> Loading operational data...
      </div>
    );
  }
  return null;
}
