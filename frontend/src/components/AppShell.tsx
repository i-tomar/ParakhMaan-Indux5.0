'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Activity, AlertTriangle, BarChart3, Boxes, ChevronRight, Cpu, Database,
  FileText, GitBranch, History, LayoutDashboard, Layers, LogOut, Menu,
  Radio, Ruler, ScanSearch, Scale, Settings, ShieldCheck, Sparkles, Star, User, Video, X,
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

  // Find current active link label for breadcrumb
  let activeSection = 'Operations';
  let activePage = 'Overview';
  for (const g of GROUPS) {
    for (const l of g.links) {
      if (active(l.href)) {
        activeSection = g.label;
        activePage = l.label;
        break;
      }
    }
  }
  if (pathname === '/settings') {
    activeSection = 'System';
    activePage = 'Settings';
  }

  const sidebar = (
    <nav className="flex flex-col h-full bg-white text-slate-800">
      {/* Brand Header */}
      <div className="flex items-center gap-3 px-5 h-16 border-b border-slate-200/80">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#00509a] to-[#0075de] text-white flex items-center justify-center shadow-sm">
          <Layers className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[15px] font-bold tracking-tight text-slate-900">ParakhMaan</span>
            <span className="px-1.5 py-0.2 rounded text-[9px] font-extrabold bg-blue-50 text-[#0075de] border border-blue-100">
              2.0
            </span>
          </div>
          <p className="text-[10px] text-slate-400 font-medium truncate">Industrial AI Inspection</p>
        </div>
      </div>

      {/* Navigation Groups */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {GROUPS.map((g) => (
          <div key={g.label}>
            <p className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {g.label}
            </p>
            <div className="space-y-0.5">
              {g.links.map((l) => {
                const Icon = l.icon;
                const isCurrent = active(l.href);
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-all ${
                      isCurrent
                        ? 'bg-blue-50/80 text-[#0075de] font-semibold border-l-3 border-[#0075de]'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                  >
                    <Icon className={`w-4 h-4 shrink-0 ${isCurrent ? 'text-[#0075de]' : 'text-slate-400'}`} />
                    <span className="truncate">{l.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Footer / User Profile & Settings */}
      <div className="border-t border-slate-200/80 p-3 bg-slate-50/50">
        <Link
          href="/settings"
          className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors ${
            pathname === '/settings' ? 'bg-blue-50 text-[#0075de] font-semibold' : 'text-slate-600 hover:bg-slate-100/70'
          }`}
        >
          <Settings className="w-4 h-4 text-slate-400" />
          <span>System Settings</span>
        </Link>

        <div className="mt-2 pt-2 border-t border-slate-200/60 flex items-center justify-between px-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center font-bold text-xs uppercase shrink-0">
              {user?.full_name?.charAt(0) || user?.email?.charAt(0) || 'U'}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-800 truncate">{user?.full_name || user?.email || 'Operator'}</p>
              <span className="inline-block px-1.5 py-0.2 rounded text-[9px] font-medium bg-slate-200/80 text-slate-600 uppercase tracking-wider">
                {user?.role || 'Inspector'}
              </span>
            </div>
          </div>
          <button
            aria-label="Sign out"
            title="Sign out"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
            onClick={() => {
              clearSession();
              router.replace('/login');
            }}
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen flex bg-[#f8fafc]">
      {/* Desktop Sticky Sidebar */}
      <aside className="hidden lg:block w-64 shrink-0 bg-white border-r border-slate-200 sticky top-0 h-screen z-20 shadow-[1px_0_4px_rgba(0,0,0,0.02)]">
        {sidebar}
      </aside>

      {/* Mobile Drawer */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-72 bg-white shadow-2xl">
            <button
              aria-label="Close menu"
              className="absolute right-3 top-4 p-1.5 rounded-lg text-slate-500 hover:bg-slate-100"
              onClick={() => setOpen(false)}
            >
              <X className="w-5 h-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top Industrial Telemetry & Header Bar */}
        <header className="sticky top-0 z-10 bg-white/95 backdrop-blur-md border-b border-slate-200/80 h-14 px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-4">
          {/* Mobile hamburger + Breadcrumbs */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              aria-label="Open menu"
              onClick={() => setOpen(true)}
              className="lg:hidden p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
            >
              <Menu className="w-5 h-5" />
            </button>

            <nav className="flex items-center gap-1.5 text-xs text-slate-500">
              <span className="font-medium text-slate-400 hidden sm:inline">{activeSection}</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-300 hidden sm:inline" />
              <span className="font-bold text-slate-800 text-[13px]">{activePage}</span>
            </nav>
          </div>

          {/* Right Status Badges & Quick Action */}
          <div className="flex items-center gap-2.5 sm:gap-3 shrink-0">
            {/* Live Operational Beacon */}
            <div className="hidden md:flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200/70 text-emerald-800 text-[11px] font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-500 live-beacon shrink-0" />
              <span>System Operational</span>
            </div>

            {/* Production Line Badge */}
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-[11px] font-medium border border-slate-200/60">
              <Activity className="w-3.5 h-3.5 text-slate-500" />
              <span>Line 1 · Optical QC</span>
            </div>

            {/* Quick Live Stream Action */}
            <Link
              href="/live"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 text-[#0075de] hover:bg-blue-100/80 border border-blue-200/60 text-xs font-semibold transition-colors"
            >
              <Video className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Live Camera</span>
            </Link>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
