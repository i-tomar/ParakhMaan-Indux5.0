'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { DECISION_STYLES, decisionLabel } from '@/lib/defects';

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
      <div>
        <h1 className="text-[22px] font-bold tracking-tight text-[#000000]">{title}</h1>
        {subtitle && <p className="text-[13px] text-[#615d59] mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, subtitle, children, actions, className = '' }: {
  title?: string; subtitle?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <section className={`bg-white rounded-xl elevation-0 ${className}`}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-[#000000]">{title}</h2>}
            {subtitle && <p className="text-xs text-[#615d59] mt-0.5">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="bg-white rounded-xl elevation-0 px-4 py-3">
      <p className="text-[11px] font-medium text-[#615d59]">{label}</p>
      <p className="text-2xl font-bold tracking-tight text-[#000000] mt-1 tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-[#615d59] mt-0.5">{hint}</p>}
    </div>
  );
}

export function Button({ variant = 'secondary', className = '', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }) {
  const styles = {
    primary: 'bg-[#0075de] text-white hover:bg-[#005bab]',
    secondary: 'bg-white text-[#31302e] border border-[#e6e6e6] hover:bg-[#f6f5f4]',
    danger: 'bg-white text-[#991B1B] border border-red-200 hover:bg-red-50',
  }[variant];
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${styles} ${className}`}
    />
  );
}

export const inputClass = 'w-full px-3 py-2 rounded-lg border border-[#e6e6e6] bg-white text-[13px] outline-none focus:border-[#0075de]';

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-[#615d59] mb-1">{label}</span>
      {children}
    </label>
  );
}

export function Banner({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'error'; children: React.ReactNode }) {
  const style = {
    info: 'bg-blue-50 border-blue-200 text-[#213183]',
    warn: 'bg-amber-50 border-amber-200 text-[#854D0E]',
    error: 'bg-red-50 border-red-200 text-[#991B1B]',
  }[tone];
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${style}`}>
      <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function SimulatedBadge() {
  return <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[#f3e8ff] text-[#6b21a8]">SIMULATED</span>;
}

export function DecisionBadge({ decision }: { decision?: string | null }) {
  return (
    <span className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full ${DECISION_STYLES[decision || ''] || 'bg-gray-100 text-gray-700'}`}>
      {decisionLabel(decision)}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-[#615d59] py-8 text-center">{children}</p>;
}

export function Table({ columns, rows }: { columns: React.ReactNode[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[#615d59] border-b border-[#e6e6e6]">
            {columns.map((c, i) => <th key={i} className="py-2 pr-4 font-medium whitespace-nowrap">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-[#f1f0ee] last:border-0">
              {row.map((cell, j) => <td key={j} className="py-2 pr-4 text-[#31302e] tabular-nums">{cell}</td>)}
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
      <div className="flex items-center gap-2 text-xs text-[#615d59] py-8 justify-center">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading
      </div>
    );
  }
  return null;
}
