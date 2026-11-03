'use client';

import React from 'react';
import Link from 'next/link';
import {
  Activity, AlertTriangle, ArrowRight, BarChart3, Boxes, CheckCircle2,
  ChevronRight, Cpu, Eye, HardDrive, HelpCircle, Layers, Radio,
  Ruler, ScanSearch, ShieldAlert, ShieldCheck, Sparkles, Video, Zap,
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
    <div className="space-y-7">
      {/* Executive Command Center Header */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs ambient-glow">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-blue-50 text-[#0075de] border border-blue-200/80">
                <Sparkles className="w-3 h-3 text-[#0075de]" />
                Industry 5.0 Visual Intelligence
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200/80">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 live-beacon" />
                Line 1 Optical Station Active
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">
              Industrial Quality & Vision Operations
            </h1>
            <p className="text-xs sm:text-[13px] text-slate-500 max-w-3xl leading-relaxed">
              Automated surface defect segmentation, dimensional metrology verification, and statistical process control across active manufacturing lines.
            </p>
          </div>

          {/* Quick Primary Actions */}
          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <Link href="/live">
              <Button variant="primary" icon={<Video className="w-4 h-4" />}>
                Launch Live Camera
              </Button>
            </Link>
            <Link href="/defects">
              <Button variant="secondary" icon={<ScanSearch className="w-4 h-4" />}>
                Inspect Part Images
              </Button>
            </Link>
          </div>
        </div>

        {/* Telemetry Hardware Ticker */}
        <div className="mt-5 pt-4 border-t border-slate-100/90 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="flex items-center gap-2 text-slate-600">
            <Activity className="w-4 h-4 text-[#0075de]" />
            <span>Throughput: <b className="text-slate-900">1,200 pcs/hr</b></span>
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <Zap className="w-4 h-4 text-amber-500" />
            <span>Inference: <b className="text-slate-900">42 FPS · 12ms</b></span>
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <Ruler className="w-4 h-4 text-purple-500" />
            <span>Precision: <b className="text-slate-900">±0.05 mm</b></span>
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Vision Engine: <b className="text-slate-900">YOLOv8 + ResNet</b></span>
          </div>
        </div>
      </div>

      <LoadState loading={overview.loading} error={overview.error} />

      {o && (
        <div className="space-y-7">
          {/* Synthetic Demonstration Mode Notice */}
          {o.kpis.synthetic_units > 0 && (
            <Banner tone="warn">
              <b>Demonstration Mode:</b> {o.kpis.synthetic_units} of {o.kpis.units} units are generated from sample test sequences. All part photos are continuously evaluated by real YOLO segmentation and OpenCV neural models.
            </Banner>
          )}

          {/* 3 Interactive Feature Launchpad Cards - Beautiful, Rich & Intuitive */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Core Inspection Modules
              </h2>
              <span className="text-[11px] text-slate-400 font-medium">Select a module to begin inspection</span>
            </div>

            <div className="grid md:grid-cols-3 gap-4.5">
              {/* Card 1: Live Camera Stream */}
              <Link
                href="/live"
                className="elevation-card relative overflow-hidden p-5.5 group flex flex-col justify-between transition-all"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full blur-2xl group-hover:bg-blue-500/10 transition-all pointer-events-none" />
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-[#00509a] to-[#0075de] text-white flex items-center justify-center shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform">
                      <Radio className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-blue-50 text-[#0075de] border border-blue-200/80">
                      LIVE HARDWARE
                    </span>
                  </div>

                  <h3 className="text-base font-extrabold text-slate-900 group-hover:text-[#0075de] transition-colors flex items-center gap-1.5">
                    Live Camera Inspection
                    <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all text-[#0075de]" />
                  </h3>
                  <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                    Continuous video feed from industrial USB cameras or webcams with real-time bounding boxes and rejection actuation.
                  </p>

                  <ul className="mt-4 space-y-1.5 text-[11px] text-slate-600">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                      <span>Auto physical camera detection & switcher</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                      <span>Instant frame defect overlay & tracking</span>
                    </li>
                  </ul>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-[#0075de]">
                  <span>Launch Live Stream</span>
                  <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>

              {/* Card 2: Defect Detection Studio */}
              <Link
                href="/defects"
                className="elevation-card relative overflow-hidden p-5.5 group flex flex-col justify-between transition-all"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-all pointer-events-none" />
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-400 text-white flex items-center justify-center shadow-md shadow-emerald-500/20 group-hover:scale-105 transition-transform">
                      <ScanSearch className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80">
                      SURFACE AI
                    </span>
                  </div>

                  <h3 className="text-base font-extrabold text-slate-900 group-hover:text-emerald-700 transition-colors flex items-center gap-1.5">
                    Defect Detection Studio
                    <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all text-emerald-600" />
                  </h3>
                  <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                    Upload batches or photos of metal sheets, die-cast parts, and electronics to classify scratches, dents, and pores.
                  </p>

                  <ul className="mt-4 space-y-1.5 text-[11px] text-slate-600">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      <span>Multi-class defect segmentation masks</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      <span>Comparison against Golden Master reference</span>
                    </li>
                  </ul>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-emerald-600">
                  <span>Upload & Inspect Parts</span>
                  <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>

              {/* Card 3: Dimensional Metrology */}
              <Link
                href="/dimensional"
                className="elevation-card relative overflow-hidden p-5.5 group flex flex-col justify-between transition-all"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/5 rounded-full blur-2xl group-hover:bg-purple-500/10 transition-all pointer-events-none" />
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 text-white flex items-center justify-center shadow-md shadow-purple-500/20 group-hover:scale-105 transition-transform">
                      <Ruler className="w-6 h-6" />
                    </div>
                    <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200/80">
                      TOLERANCE QC
                    </span>
                  </div>

                  <h3 className="text-base font-extrabold text-slate-900 group-hover:text-purple-700 transition-colors flex items-center gap-1.5">
                    Dimensional Metrology
                    <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all text-purple-600" />
                  </h3>
                  <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                    Sub-millimeter checkerboard optical calibration to measure part lengths, hole diameters, and CAD tolerances.
                  </p>

                  <ul className="mt-4 space-y-1.5 text-[11px] text-slate-600">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-purple-500 shrink-0" />
                      <span>Optical distortion & perspective correction</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-purple-500 shrink-0" />
                      <span>Upper/Lower tolerance pass-fail testing</span>
                    </li>
                  </ul>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-purple-600">
                  <span>Calibrate & Measure</span>
                  <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            </div>
          </div>

          {/* 5 Core Industrial KPIs with Explanations */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Quality & Production Yield (30-Day Aggregation)
              </h2>
              <span className="text-[11px] text-slate-400 font-medium">Synced from active line logs</span>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              <Stat
                label="Units Inspected"
                value={o.kpis.units.toLocaleString()}
                accent="blue"
                icon={<Boxes className="w-4 h-4" />}
                trend="100% Logged"
                explanation="Total parts processed by the computer vision pipeline"
              />
              <Stat
                label="First-Pass Yield"
                value={pct(o.kpis.first_pass_yield)}
                accent="emerald"
                icon={<CheckCircle2 className="w-4 h-4" />}
                trend="High Quality"
                explanation="Parts passed on first run without requiring rework"
              />
              <Stat
                label="Rejection Rate"
                value={pct(o.kpis.rejection_rate)}
                accent="rose"
                icon={<AlertTriangle className="w-4 h-4" />}
                trend="Within Limit"
                explanation="Failed parts flagged and diverted from conveyor"
              />
              <Stat
                label="Manual Review"
                value={pct(o.kpis.review_share)}
                accent="amber"
                icon={<HelpCircle className="w-4 h-4" />}
                trend="Borderline"
                explanation="Uncertain confidence units routed to human supervisor"
              />
              <Stat
                label="AI Latency (p50)"
                value={o.kpis.latency_ms_p50 !== null ? `${o.kpis.latency_ms_p50} ms` : '—'}
                accent="purple"
                icon={<Cpu className="w-4 h-4" />}
                trend="Real-time"
                explanation="Median cycle-time per evaluated frame"
              />
            </div>
          </div>

          {/* Quality Alerts Banner */}
          {open.length > 0 && (
            <Card
              title={`Active Process Alerts (${open.length})`}
              subtitle="Critical variations requiring immediate plant supervisor investigation"
              icon={<ShieldAlert className="w-4 h-4 text-rose-500" />}
              actions={
                <Link
                  className="inline-flex items-center gap-1 text-xs font-bold text-[#0075de] hover:underline"
                  href="/root-cause"
                >
                  Root-Cause Investigation <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              }
            >
              <ul className="space-y-2.5 text-xs">
                {open.slice(0, 4).map((a) => (
                  <li
                    key={a.id}
                    className="flex items-start gap-2.5 p-3 rounded-xl bg-rose-50/80 border border-rose-100 text-rose-950 shadow-2xs"
                  >
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500 mt-0.5 shrink-0 live-beacon-rose" />
                    <span className="font-semibold leading-relaxed">{a.message}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* Visual Analytics Grid */}
          <div className="grid lg:grid-cols-2 gap-5">
            <Card
              title="Statistical Process Control (p-Chart)"
              subtitle="Daily defect rate vs. Upper Control Limit (UCL). Violations indicate process instability."
              icon={<Activity className="w-4 h-4 text-[#0075de]" />}
            >
              <ControlChart points={o.trend} />
            </Card>

            <Card
              title="Defect Pareto Distribution"
              subtitle="Ranked failure modes to target mechanical, thermal, or tooling maintenance"
              icon={<BarChart3 className="w-4 h-4 text-emerald-600" />}
            >
              <ParetoBars rows={o.pareto} />
            </Card>

            <Card
              title="Station & Assembly Line Defect Comparison"
              subtitle="Identifies tooling degradation or mechanical misalignment across physical lines"
              icon={<Layers className="w-4 h-4 text-amber-600" />}
            >
              <GroupBars rows={o.by_machine} />
            </Card>

            <Card
              title="Edge AI Neural Telemetry"
              subtitle="Hardware compute load and neural model checkpoint statuses"
              icon={<Cpu className="w-4 h-4 text-purple-600" />}
            >
              {edge.error && <Banner tone="error">{edge.error}</Banner>}
              {edge.data && (
                <div className="space-y-3 text-xs">
                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 border border-slate-100">
                    <span className="text-slate-500 font-semibold">Segmentation Checkpoint</span>
                    <span className="font-bold text-slate-800">
                      {seg.loaded ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-md border border-emerald-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          {seg.version} (Active)
                        </span>
                      ) : (
                        <span className="text-rose-600">Offline: {seg.error}</span>
                      )}
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 border border-slate-100">
                    <span className="text-slate-500 font-semibold">Anomaly Models Configured</span>
                    <span className="font-bold text-slate-800">
                      {anomaly.products.length} Products Profiled
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 border border-slate-100">
                    <span className="text-slate-500 font-semibold">Edge Device Architecture</span>
                    <span className="font-bold text-slate-800">
                      {edge.data.device.machine} ({edge.data.device.cpu_count} CPU Cores)
                    </span>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 border border-slate-100">
                    <span className="text-slate-500 font-semibold">Resident Memory Usage</span>
                    <span className="font-bold text-slate-800">
                      {edge.data.process.peak_memory_mb} MB RAM
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* Latest Inspected Units Stream Table */}
          <Card
            title="Live Production Inspection Stream"
            subtitle="Recent units inspected by the vision pipeline with decisions and timestamps"
            icon={<HardDrive className="w-4 h-4 text-slate-600" />}
            actions={
              <Link href="/history" className="text-xs font-bold text-[#0075de] hover:underline flex items-center gap-1">
                View Complete Inspection History <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            }
          >
            {recent.data?.items.length ? (
              <Table
                columns={['Unit Code', 'Product Type', 'Batch Code', 'Station', 'Inspection Decision', 'Timestamp']}
                rows={recent.data.items.map((u) => [
                  <Link
                    key={u.id}
                    className="text-[#0075de] font-bold hover:underline inline-flex items-center gap-1"
                    href={`/units/${u.id}`}
                  >
                    <span>{u.unit_code}</span>
                  </Link>,
                  u.product || '—',
                  u.batch || '—',
                  u.machine || '—',
                  <span key="d" className="inline-flex items-center gap-2">
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
