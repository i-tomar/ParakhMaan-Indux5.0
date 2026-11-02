'use client';

import React from 'react';
import Link from 'next/link';
import { analyticsApi, edgeApi, pct, productionApi } from '@/lib/industrial';
import { Banner, Card, DecisionBadge, Empty, LoadState, PageHeader, SimulatedBadge, Stat, Table, useLoad } from '@/components/ui';
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
    <div>
      <PageHeader title="Industrial Overview" subtitle="Quality, throughput and model status for the last 30 days. Every figure comes from logged units." />
      <LoadState loading={overview.loading} error={overview.error} />
      {o && (
        <div className="space-y-4">
          {o.kpis.synthetic_units > 0 && (
            <Banner tone="warn">{o.kpis.synthetic_units} of {o.kpis.units} units come from a simulated run. Real part images were inspected by the real models, but machine, shift and belt context is simulated.</Banner>
          )}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <Stat label="Units inspected" value={o.kpis.units.toLocaleString()} />
            <Stat label="First-pass yield" value={pct(o.kpis.first_pass_yield)} />
            <Stat label="Rejection rate" value={pct(o.kpis.rejection_rate)} />
            <Stat label="Sent to manual review" value={pct(o.kpis.review_share)} />
            <Stat label="Inference latency p50" value={o.kpis.latency_ms_p50 !== null ? `${o.kpis.latency_ms_p50} ms` : '—'} />
          </div>
          {open.length > 0 && (
            <Card title={`Open quality alerts (${open.length})`} actions={<Link className="text-xs font-semibold text-[#0075de]" href="/root-cause">Investigate</Link>}>
              <ul className="space-y-1.5 text-xs text-[#31302e]">{open.slice(0, 4).map((a) => <li key={a.id}>{a.message}</li>)}</ul>
            </Card>
          )}
          <div className="grid lg:grid-cols-2 gap-4">
            <Card title="Flagged rate with control limit" subtitle="Flagged = rejected or awaiting review"><ControlChart points={o.trend} /></Card>
            <Card title="Defect types by frequency"><ParetoBars rows={o.pareto} /></Card>
            <Card title="Flagged rate by machine" subtitle="Flagged = rejected or awaiting review"><GroupBars rows={o.by_machine} /></Card>
            <Card title="Model status">
              {edge.error && <Banner tone="error">{edge.error}</Banner>}
              {edge.data && (
                <dl className="text-xs space-y-2">
                  <div className="flex justify-between gap-4"><dt className="text-[#615d59]">Segmentation model</dt><dd className="font-medium text-right">{seg.loaded ? seg.version : `Not loaded: ${seg.error}`}</dd></div>
                  <div className="flex justify-between gap-4"><dt className="text-[#615d59]">Anomaly models</dt><dd className="font-medium text-right">{anomaly.products.length} products</dd></div>
                  <div className="flex justify-between gap-4"><dt className="text-[#615d59]">Device</dt><dd className="font-medium text-right">{edge.data.device.machine}, {edge.data.device.cpu_count} cores</dd></div>
                  <div className="flex justify-between gap-4"><dt className="text-[#615d59]">Peak memory</dt><dd className="font-medium text-right">{edge.data.process.peak_memory_mb} MB</dd></div>
                </dl>
              )}
            </Card>
          </div>
          <Card title="Latest units">
            {recent.data?.items.length ? (
              <Table columns={['Unit', 'Product', 'Batch', 'Machine', 'Decision', 'Inspected']} rows={recent.data.items.map((u) => [
                <Link key={u.id} className="text-[#0075de] font-medium" href={`/units/${u.id}`}>{u.unit_code}</Link>,
                u.product || '—', u.batch || '—', u.machine || '—',
                <span key="d" className="flex items-center gap-1.5"><DecisionBadge decision={u.final_decision || u.decision} />{u.is_synthetic && <SimulatedBadge />}</span>,
                formatDate(u.inspected_at),
              ])} />
            ) : <Empty>No units yet. Start with Live Inspection or Defect Detection.</Empty>}
          </Card>
        </div>
      )}
    </div>
  );
}
