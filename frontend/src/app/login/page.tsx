'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ScanSearch, LogIn, AlertCircle, RefreshCw, KeyRound } from 'lucide-react';
import { authApi } from '@/lib/api';
import { ROLE_LABELS, setSession } from '@/lib/auth';

type DemoAccount = { email: string; role: string; password: string };

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);

  useEffect(() => {
    authApi.config().then((cfg) => setDemoAccounts(cfg.demo_accounts || [])).catch(() => setDemoAccounts([]));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await authApi.login(email.trim(), password);
      setSession(res.access_token, res.user);
      const next = new URLSearchParams(window.location.search).get('next');
      router.replace(next && next.startsWith('/') && !next.startsWith('//') ? next : '/defects');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="w-full max-w-md space-y-5">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[#6b21a8] text-white shadow-sm mb-3">
            <ScanSearch className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-[#000000]">Sign in to ParakhMaan</h1>
          <p className="text-xs text-[#615d59] mt-1">AI quality inspection · Legal Metrology compliance module</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-[#e6e6e6] p-6 elevation-1 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-xs text-[#991B1B]">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <div className="text-xs">
            <label className="block font-semibold text-[#31302e] mb-1" htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4]"
            />
          </div>
          <div className="text-xs">
            <label className="block font-semibold text-[#31302e] mb-1" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4]"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-sm disabled:opacity-50"
          >
            {submitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {demoAccounts.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs space-y-2">
            <p className="font-bold text-[#854D0E] flex items-center gap-1.5">
              <KeyRound className="w-4 h-4" />
              Development demo accounts
            </p>
            <div className="grid grid-cols-2 gap-2">
              {demoAccounts.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  onClick={() => {
                    setEmail(a.email);
                    setPassword(a.password);
                  }}
                  className="text-left px-2.5 py-2 rounded-lg bg-white border border-amber-200 hover:border-amber-400 transition-colors"
                >
                  <span className="block font-semibold text-[#000000]">{ROLE_LABELS[a.role] || a.role}</span>
                  <span className="block text-[10px] text-[#615d59] truncate">{a.email}</span>
                </button>
              ))}
            </div>
            <p className="text-[10px] text-[#854D0E]">Shown only when the API runs in development mode.</p>
          </div>
        )}
      </div>
    </div>
  );
}
