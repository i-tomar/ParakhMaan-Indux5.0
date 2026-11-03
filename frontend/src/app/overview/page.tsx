'use client';

import React from 'react';
import Link from 'next/link';
import {
  Activity, AlertTriangle, ArrowRight, BarChart3, Boxes, CheckCircle2,
  Cpu, HardDrive, HelpCircle, Layers, Radio, Ruler, ScanSearch, ShieldAlert,
  Sparkles, Video,
} from 'lucide-react';
import { analyticsApi, edgeApi, pct, productionApi } from '@/lib/industrial';
import { Banner, Button, Card, DecisionBadge, Empty, LoadState, PageHeader, SimulatedBadge, Stat, Table, useLoad } from '@/components/ui';
import { ControlChart, GroupBars, ParetoBars } from '@/components/charts';
import { formatDate } from '@/lib/formatters';

export default function OverviewPage() {
  const overview = useLoad(() => analyticsApi.overview({ days: 30 }), [], 15000);
  const alerts = useLoad(() => analyticsApi.alerts(), [], 30000);
  const recent = useLoad(() => productionApi.units({ limit: 8 }), [], 15000);
  const edge = useLoad(() => edgeApi.status(), [], 15000);

  const o = overview.data;
  const open = (alerts.data || []).filter((a) => a.status === 'OPEN');
  const seg = edge.data?.models?.segmentation;
  const anomaly = edge.data?.models?.anomaly;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Industrial Quality Overview"
        subtitle="Real-time visual inspection telemetry, defect analytics, and edge inference status over the last 30 days."
        actions={
          <div className="flex items-center gap-2">
            <Link href="/live">
              <Button variant="primary" icon={<Video className="w-3.5 h-3.5" />}>
                Launch Live Camera
              </Button>
            </Link>
            <Link href="/defects">
              <Button variant="secondary" icon={<ScanSearch className="w-3.5 h-3.5" />}>
                Inspect Part Images
              </Button>
            </Link>
          </div>
        }
      />

      <LoadState loading={overview.loading} error={overview.error} />

      {o && (
        <div className="space-y-6">
          {/* Synthetic Run Advisory Banner if applicable */}
          {o.kpis.synthetic_units > 0 && (
            <Banner tone="warn">
              <b>Demonstration Mode Active:</b> {o.kpis.synthetic_units} of {o.kpis.units} units are generated from sample test sequences. Real part images are continuously evaluated through genuine OpenCV & YOLO neural models.
            </Banner>
          )}

          {/* Quick Start Feature Launchpad - Friendly & Intuitive */}
          <div className="grid sm:grid-cols-3 gap-4">
            <Link
              href="/live"
              className="elevation-card p-4.5 group hover:border-[#0075de]/50 flex flex-col justify-between transition-all"
            >
              <div>
                <div className="w-9 h-9 rounded-xl bg-blue-50 text-[#0075de] flex items-center justify-center mb-3 group-hover:scale-105 transition-transform">
                  <Radio className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-slate-900 group-hover:text-[#0075de] transition-colors flex items-center gap-1.5">
                  Live Camera Inspection
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[#0075de]" />
                </h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  Stream connected webcam or factory camera with live bounding boxes and instant AI defect classification.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center text-[11px] font-semibold text-[#0075de]">
                <span>Start inspection stream →</span>
              </div>
            </Link>

            <Link
              href="/defects"
              className="elevation-card p-4.5 group hover:border-emerald-500/50 flex flex-col justify-between transition-all"
            >
              <div>
                <div className="w-9 h-9 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform">
                  <ScanSearch className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-slate-900 group-hover:text-emerald-700 transition-colors flex items-center gap-1.5">
                  Defect Detection Studio
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-emerald-600" />
                </h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  Upload batch photos of metal sheets, die-cast parts, or electronics to detect surface scratches and dents.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center text-[11px] font-semibold text-emerald-600">
                <span>Upload & run batch test →</span>
              </div>
            </Link>

            <Link
              href="/dimensional"
              className="elevation-card p-4.5 group hover:border-purple-500/50 flex flex-col justify-between transition-all"
            >
              <div>
                <div className="w-9 h-9 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform">
                  <Ruler className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-slate-900 group-hover:text-purple-700 transition-colors flex items-center gap-1.5">
                  Dimensional Metrology
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-purple-600" />
                </h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  Calibrate sub-millimeter pixel ratios, measure part dimensions, and verify CAD tolerance compliance.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center text-[11px] font-semibold text-purple-600">
                <span>Calibrate & verify →</span>
              </div>
            </Link>
          </div>

          {/* 5 Core Industrial KPIs with Explanations */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Key Performance Indicators (30-Day Window)
              </h2>
              <span className="text-[11px] text-slate-400">All data synced from factory logs</span>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3.5">
              <Stat
                label="Units Inspected"
                value={o.kpis.units.toLocaleString()}
                accent="blue"
                icon={<Boxes className="w-4 h-4" />}
                explanation="Total parts evaluated by the vision pipeline"
              />
              <Stat
                label="First-Pass Yield"
                value={pct(o.kpis.first_pass_yield)}
                accent="emerald"
                icon={<CheckCircle2 className="w-4 h-4" />}
                explanation="Parts passed on first run without defects"
              />
              <Stat
                label="Rejection Rate"
                value={pct(o.kpis.rejection_rate)}
                accent="rose"
                icon={<AlertTriangle className="w-4 h-4" />}
                explanation="Failed parts safely diverted from line"
              />
              <Stat
                label="Manual Review"
                value={pct(o.kpis.review_share)}
                accent="amber"
                icon={<HelpCircle className="w-4 h-4" />}
                explanation="Borderline cases routed to supervisor"
              />
              <Stat
                label="AI Latency (p50)"
                value={o.kpis.latency_ms_p50 !== null ? `${o.kpis.latency_ms_p50} ms` : '—'}
                accent="purple"
                icon={<Cpu className="w-4 h-4" />}
                explanation="Ultra-fast median edge inference time"
              />
            </div>
          </div>

          {/* Quality Alerts Banner */}
          {open.length > 0 && (
            <Card
              title={`Active Process Alerts (${open.length})`}
              subtitle="Critical quality variations requiring immediate plant supervisor review"
              icon={<ShieldAlert className="w-4 h-4 text-rose-500" />}
              actions={
                <Link
                  className="inline-flex items-center gap-1 text-xs font-bold text-[#0075de] hover:underline"
                  href="/root-cause"
                >
                  Investigate in Root-Cause <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              }
            >
              <ul className="space-y-2 text-xs">
                {open.slice(0, 4).map((a) => (
                  <li
                    key={a.id}
                    className="flex items-start gap-2 p-2.5 rounded-lg bg-rose-50/70 border border-rose-100 text-rose-900"
                  >
                    <span className="w-2 h-2 rounded-full bg-rose-500 mt-1 shrink-0 live-beacon-rose" />
                    <span className="font-medium leading-relaxed">{a.message}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* Visual Analytics Grid */}
          <div className="grid lg:grid-cols-2 gap-5">
            <Card
              title="Statistical Process Control (p-Chart)"
              subtitle="Daily defect rate vs. Upper Control Limit (UCL). Points crossing the red line trigger alerts."
              icon={<Activity className="w-4 h-4" />}
            >
              <ControlChart points={o.trend} />
            </Card>

            <Card
              title="Defect Pareto Distribution"
              subtitle="Ranked failure modes to prioritize mechanical and process maintenance"
              icon={<BarChart3 className="w-4 h-4" />}
            >
              <ParetoBars rows={o.pareto} />
            </Card>

            <Card
              title="Station & Machine Defect Comparison"
              subtitle="Identifies tooling degradation or mechanical misalignment per station"
              icon={<Layers className="w-4 h-4" />}
            >
              <GroupBars rows={o.by_machine} />
            </Card>

            <Card
              title="Edge Neural Network Telemetry"
              subtitle="Active model checkpoints and hardware resource consumption"
              icon={<Cpu className="w-4 h-4" />}
            >
              {edge.error && <Banner tone="error">{edge.error}</Banner>}
              {edge.data && (
                <div className="space-y-3 text-xs">
                  <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-500 font-medium">Segmentation Model</span>
                    <span className="font-bold text-slate-800">
                      {seg.loaded ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          {seg.version} (Active)
                        </span>
                      ) : (
                        <span className="text-rose-600">Offline: {seg.error}</span>
                      )}
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-500 font-medium">Anomaly Models Loaded</span>
                    <span className="font-bold text-slate-800">
                      {anomaly.products.length} Products Profiled
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-500 font-medium">Edge Compute Hardware</span>
                    <span className="font-bold text-slate-800">
                      {edge.data.device.machine} ({edge.data.device.cpu_count} CPU Cores)
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-500 font-medium">Peak Memory Usage</span>
                    <span className="font-bold text-slate-800">
                      {edge.data.process.peak_memory_mb} MB RAM
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* Latest Inspected Units Table */}
          <Card
            title="Live Inspection Stream"
            subtitle="Recent units inspected by the vision pipeline with decisions and timestamps"
            icon={<HardDrive className="w-4 h-4" />}
            actions={
              <Link href="/history" className="text-xs font-bold text-[#0075de] hover:underline">
                View All History →
              </Link>
            }
          >
            {recent.data?.items.length ? (
              <Table
                columns={['Unit Code', 'Product Type', 'Batch ID', 'Machine Station', 'QC Outcome', 'Inspection Time']}
                rows={recent.data.items.map((u) => [
                  <Link
                    key={u.id}
                    className="text-[#0075de] font-bold hover:underline"
                    href={`/units/${u.id}`}
                  >
                    {u.unit_code}
                  </Link>,
                  u.product || '—',
                  u.batch || '—',
                  u.machine || '—',
                  <span key="d" className="inline-flex items-center gap-1.5">
                    <DecisionBadge decision={u.final_decision || u.decision} />
                    {u.is_synthetic && <SimulatedBadge />}
                  </span>,
                  formatDate(u.inspected_at),
                ])}
              />
            ) : (
              <Empty>No inspection records logged yet. Run Live Inspection or upload parts in Defect Detection.</Empty>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
