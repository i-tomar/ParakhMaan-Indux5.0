'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Shield, PlusCircle, LayoutDashboard, FileText, RefreshCw, BookOpen, Scale, ScanSearch, BarChart3,
  Settings, LogOut, ClipboardCheck, BrainCircuit
} from 'lucide-react';
import { api, defectApi } from '@/lib/api';
import { can, clearSession, ROLE_LABELS } from '@/lib/auth';
import { useAuthUser } from '@/lib/useAuth';
import AskRuleBookDrawer from '@/components/AskRuleBookDrawer';

type NavLink = { href: string; label: string; icon: React.ElementType; permission?: string };

const LEGAL_LINKS: NavLink[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/inspections', label: 'All Inspections', icon: FileText },
  { href: '/inspections/new', label: 'New Inspection', icon: PlusCircle, permission: 'inspection:write' },
  { href: '/rules', label: 'Rules & Tools', icon: Scale },
];

const DEFECT_LINKS: NavLink[] = [
  { href: '/defects', label: 'Inspection', icon: ScanSearch },
  { href: '/review', label: 'Review', icon: ClipboardCheck, permission: 'review:write' },
  { href: '/defects/analytics', label: 'Analytics', icon: BarChart3, permission: 'analytics:read' },
  { href: '/models', label: 'Models', icon: BrainCircuit, permission: 'model:read' },
  { href: '/admin', label: 'Admin', icon: Settings, permission: 'org:manage' },
];

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthUser();
  const [seeding, setSeeding] = useState(false);
  const [seedSuccess, setSeedSuccess] = useState(false);
  const [ragOpen, setRagOpen] = useState(false);

  if (pathname === '/login') return null;

  const isDefectMode = ['/defects', '/admin', '/review', '/models'].some((p) => pathname.startsWith(p));
  const navLinks = (isDefectMode ? DEFECT_LINKS : LEGAL_LINKS).filter((l) => !l.permission || can(user, l.permission));

  const isActive = (href: string) => {
    if (isDefectMode) {
      if (href === '/defects') return pathname === '/defects' || (pathname.startsWith('/defects/') && !pathname.startsWith('/defects/analytics'));
      return pathname.startsWith(href);
    }
    return pathname === href || (href !== '/dashboard' && pathname.startsWith(href) && href !== '/inspections');
  };

  const handleSeed = async () => {
    setSeeding(true);
    try {
      await (isDefectMode ? defectApi.seedDemoData() : api.seedDemoData());
      setSeedSuccess(true);
      setTimeout(() => setSeedSuccess(false), 3000);
      window.location.reload();
    } catch (e) {
      console.error(e);
    } finally {
      setSeeding(false);
    }
  };

  const handleLogout = () => {
    clearSession();
    router.replace('/login');
  };

  const initials = (user?.full_name || 'User')
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <>
      <header className="sticky top-0 z-40 bg-white border-b border-[#e6e6e6]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16 gap-3">
            {/* Brand / Logo */}
            <div className="flex items-center gap-3">
              <div
                className={`flex items-center justify-center w-10 h-10 rounded-lg text-white shadow-sm ${
                  isDefectMode ? 'bg-[#6b21a8]' : 'bg-[#0075de]'
                }`}
              >
                {isDefectMode ? <ScanSearch className="w-5 h-5" /> : <Shield className="w-5 h-5" />}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm text-[#000000] tracking-tight">
                    {isDefectMode ? 'ParakhMaan' : 'Legal Metrology'}
                  </span>
                  <span
                    className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-[#f6f5f4] border border-[#e6e6e6] ${
                      isDefectMode ? 'text-[#6b21a8]' : 'text-[#0075de]'
                    }`}
                  >
                    {isDefectMode ? 'Defect AI' : 'Compliance'}
                  </span>
                </div>
                <p className="text-xs text-[#615d59] truncate max-w-[220px]">
                  {user?.organization_name || (isDefectMode ? 'Surface & Product QC' : 'Packaged Commodities Rules')}
                </p>
              </div>
            </div>

            {/* Navigation Items */}
            <nav className="hidden md:flex items-center gap-1">
              {navLinks.map((link) => {
                const Icon = link.icon;
                const active = isActive(link.href);
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                      active
                        ? `bg-[#f6f5f4] font-semibold border border-[#e6e6e6] ${isDefectMode ? 'text-[#6b21a8]' : 'text-[#0075de]'}`
                        : 'text-[#31302e] hover:bg-[#f6f5f4] hover:text-[#000000]'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {link.label}
                  </Link>
                );
              })}
            </nav>

            {/* Action Tools & User */}
            <div className="flex items-center gap-2.5">
              <div className="hidden sm:flex items-center rounded-full border border-[#e6e6e6] bg-[#f6f5f4] p-0.5 text-[11px] font-semibold">
                <Link
                  href="/defects"
                  className={`px-2.5 py-1 rounded-full transition-colors ${
                    isDefectMode ? 'bg-white text-[#6b21a8] shadow-xs' : 'text-[#615d59] hover:text-[#000000]'
                  }`}
                >
                  Defect Inspection
                </Link>
                <Link
                  href="/dashboard"
                  className={`px-2.5 py-1 rounded-full transition-colors ${
                    !isDefectMode ? 'bg-white text-[#0075de] shadow-xs' : 'text-[#615d59] hover:text-[#000000]'
                  }`}
                >
                  Legal Metrology
                </Link>
              </div>

              {!isDefectMode && (
                <button
                  onClick={() => setRagOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-blue-50 text-[#0075de] border border-blue-200 hover:bg-blue-100 transition-all shadow-xs"
                  title="Ask the Legal Metrology Rule Book AI"
                >
                  <BookOpen className="w-3.5 h-3.5 text-[#0075de]" />
                  <span className="hidden xl:inline">Ask Rule Book</span>
                </button>
              )}

              {can(user, 'system:configure') && (
                <button
                  onClick={handleSeed}
                  disabled={seeding}
                  className="hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-[#f6f5f4] text-[#31302e] border border-[#e6e6e6] hover:bg-white transition-all shadow-xs"
                  title={isDefectMode ? 'Load synthetic defect samples' : 'Load demo test packages'}
                >
                  <RefreshCw className={`w-3.5 h-3.5 text-[#0075de] ${seeding ? 'animate-spin' : ''}`} />
                  <span>{seeding ? 'Seeding...' : seedSuccess ? 'Seeded!' : 'Load Demo Data'}</span>
                </button>
              )}

              {user && (
                <div className="flex items-center gap-2 pl-2 border-l border-[#e6e6e6]">
                  <div className="w-8 h-8 rounded-full bg-[#213183] text-white flex items-center justify-center font-bold text-xs">
                    {initials}
                  </div>
                  <div className="hidden xl:block text-left">
                    <p className="text-xs font-semibold text-[#000000] leading-none">{user.full_name}</p>
                    <p className="text-[10px] text-[#615d59] leading-tight">{ROLE_LABELS[user.role] || user.role}</p>
                  </div>
                  <button
                    onClick={handleLogout}
                    title="Sign out"
                    className="p-1.5 rounded-md text-[#615d59] hover:bg-[#f6f5f4] hover:text-[#991B1B] transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* RAG Rule Book Drawer */}
      <AskRuleBookDrawer isOpen={ragOpen} onClose={() => setRagOpen(false)} />
    </>
  );
}
