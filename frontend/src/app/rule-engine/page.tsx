'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { BookOpen, FileText, LayoutDashboard, PlusCircle, Scale } from 'lucide-react';
import AskRuleBookDrawer from '@/components/AskRuleBookDrawer';
import { Button, PageHeader } from '@/components/ui';

const LINKS = [
  { href: '/dashboard', label: 'Compliance Dashboard', text: 'Inspection counts and common issues', icon: LayoutDashboard },
  { href: '/inspections', label: 'All Inspections', text: 'Registry with status filters', icon: FileText },
  { href: '/inspections/new', label: 'New Inspection', text: 'Upload package surfaces for a rule check', icon: PlusCircle },
  { href: '/rules', label: 'Rules & Tools', text: 'Rule catalogue, MPE, lot sampling and PDP calculators', icon: Scale },
];

export default function RuleEnginePage() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <PageHeader title="Rule-Based Engine" subtitle="The deterministic Legal Metrology module from SIH26034. It is separate from defect inspection and shares no decisions with it."
        actions={<Button onClick={() => setOpen(true)}><BookOpen className="w-3.5 h-3.5" />Ask Rule Book</Button>} />
      <div className="grid sm:grid-cols-2 gap-3">
        {LINKS.map((l) => {
          const Icon = l.icon;
          return (
            <Link key={l.href} href={l.href} className="bg-white rounded-xl elevation-0 p-4 hover:bg-[#fbfbfa]">
              <Icon className="w-4 h-4 text-[#0075de] mb-2" />
              <p className="text-sm font-semibold">{l.label}</p>
              <p className="text-xs text-[#615d59] mt-0.5">{l.text}</p>
            </Link>
          );
        })}
      </div>
      <AskRuleBookDrawer isOpen={open} onClose={() => setOpen(false)} />
    </div>
  );
}
