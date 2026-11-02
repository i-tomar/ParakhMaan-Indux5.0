'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Activity, AlertTriangle, BarChart3, Boxes, Cpu, Database, FileText, GitBranch, History, LayoutDashboard,
  Layers, LogOut, Menu, Radio, Ruler, ScanSearch, Scale, Settings, Star, X,
} from 'lucide-react';
import { SessionUser, clearSession, getSessionUser, getToken } from '@/lib/api';

const GROUPS = [
  {
    label: 'Operations',
    links: [
      { href: '/overview', label: 'Overview', icon: LayoutDashboard },
      { href: '/live', label: 'Live Inspection', icon: Radio },
      { href: '/defects', label: 'Defect Detection', icon: ScanSearch },
      { href: '/dimensional', label: 'Dimensional Inspection', icon: Ruler },
      { href: '/golden', label: 'Golden References', icon: Star },
    ],
  },
  {
    label: 'Production',
    links: [
      { href: '/line', label: 'Line Monitoring', icon: Activity },
      { href: '/batches', label: 'Products & Batches', icon: Boxes },
      { href: '/history', label: 'Inspection History', icon: History },
    ],
  },
  {
    label: 'Quality',
    links: [
      { href: '/analytics', label: 'Defect Analytics', icon: BarChart3 },
      { href: '/root-cause', label: 'Root-Cause Investigation', icon: AlertTriangle },
      { href: '/reports', label: 'Reports', icon: FileText },
    ],
  },
  {
    label: 'AI Models',
    links: [
      { href: '/models/performance', label: 'Model Performance', icon: Cpu },
      { href: '/feedback', label: 'Dataset & Feedback', icon: Database },
      { href: '/models', label: 'Model Versions', icon: GitBranch },
    ],
  },
  {
    label: 'Optional Modules',
    links: [{ href: '/rule-engine', label: 'Rule-Based Engine', icon: Scale }],
  },
];

const LEGAL_PREFIXES = ['/rule-engine', '/dashboard', '/inspections', '/rules'];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [open, setOpen] = useState(false);
  const isLogin = pathname === '/login';

  useEffect(() => {
    if (!isLogin && !getToken()) {
      router.replace('/login');
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUser(getSessionUser());
    setReady(true);
  }, [isLogin, pathname, router]);

  if (isLogin) return <>{children}</>;
  if (!ready) return null;

  const active = (href: string) => {
    if (href === '/rule-engine') return LEGAL_PREFIXES.some((p) => pathname.startsWith(p));
    if (href === '/models') return pathname === '/models';
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const sidebar = (
    <nav className="flex flex-col h-full">
      <div className="flex items-center gap-2.5 px-4 h-14 border-b border-[#e6e6e6]">
        <div className="w-8 h-8 rounded-lg bg-[#0075de] text-white flex items-center justify-center"><Layers className="w-4 h-4" /></div>
        <div>
          <p className="text-sm font-bold tracking-tight leading-none">ParakhMaan</p>
          <p className="text-[10px] text-[#615d59] mt-0.5">Industrial Visual Inspection</p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {GROUPS.map((g) => (
          <div key={g.label}>
            <p className="px-2 mb-1 text-[10px] font-semibold text-[#a39e98]">{g.label}</p>
            {g.links.map((l) => {
              const Icon = l.icon;
              return (
                <Link key={l.href} href={l.href} onClick={() => setOpen(false)}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-[13px] transition-colors ${
                    active(l.href) ? 'bg-[#f6f5f4] text-[#0075de] font-semibold' : 'text-[#31302e] hover:bg-[#f6f5f4]'
                  }`}>
                  <Icon className="w-4 h-4 shrink-0" />
                  <span className="truncate">{l.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </div>
      <div className="border-t border-[#e6e6e6] p-2">
        <Link href="/settings" className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-[13px] ${pathname === '/settings' ? 'bg-[#f6f5f4] text-[#0075de] font-semibold' : 'text-[#31302e] hover:bg-[#f6f5f4]'}`}>
          <Settings className="w-4 h-4" /> Settings
        </Link>
        <div className="flex items-center justify-between px-2 pt-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold truncate">{user?.full_name}</p>
            <p className="text-[10px] text-[#615d59]">{user?.role}</p>
          </div>
          <button aria-label="Sign out" title="Sign out" className="p-1.5 rounded-md hover:bg-[#f6f5f4]"
            onClick={() => { clearSession(); router.replace('/login'); }}>
            <LogOut className="w-4 h-4 text-[#615d59]" />
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen flex">
      <aside className="hidden lg:block w-60 shrink-0 bg-white border-r border-[#e6e6e6] sticky top-0 h-screen">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-64 bg-white">
            <button aria-label="Close menu" className="absolute right-2 top-3 p-1.5" onClick={() => setOpen(false)}><X className="w-4 h-4" /></button>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="lg:hidden flex items-center gap-2 h-12 px-4 bg-white border-b border-[#e6e6e6]">
          <button aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="w-5 h-5" /></button>
          <span className="text-sm font-bold">ParakhMaan</span>
        </div>
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
