'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Layers } from 'lucide-react';
import { API_BASE, SessionUser, fetchJson, setSession } from '@/lib/api';
import { Banner, Button, Field, inputClass } from '@/components/ui';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetchJson<{ access_token: string; user: SessionUser }>(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      setSession(res.access_token, res.user);
      router.replace('/overview');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-xl elevation-1 p-6 space-y-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[#0075de] text-white flex items-center justify-center"><Layers className="w-5 h-5" /></div>
          <div>
            <h1 className="text-base font-bold tracking-tight">ParakhMaan</h1>
            <p className="text-xs text-[#615d59]">Industrial Visual Inspection</p>
          </div>
        </div>
        {error && <Banner tone="error">{error}</Banner>}
        <Field label="Email"><input className={inputClass} type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password"><input className={inputClass} type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <Button type="submit" variant="primary" disabled={busy} className="w-full justify-center">{busy ? 'Signing in' : 'Sign in'}</Button>
      </form>
    </div>
  );
}
