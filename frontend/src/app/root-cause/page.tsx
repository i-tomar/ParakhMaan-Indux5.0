'use client';

import React, { useState } from 'react';
import { analyticsApi, pct } from '@/lib/industrial';
import { DEFECT_TYPES, defectLabel } from '@/lib/defects';
import { Banner, Button, Card, Empty, Field, LoadState, PageHeader, Table, inputClass, useLoad } from '@/components/ui';
import { Hotspot } from '@/components/charts';

export default function RootCausePage() {
  const [defect, setDefect] = useState('');
  const [days, setDays] = useState(30);
  const data = useLoad(() => analyticsApi.rootCause({ days, defect_type: defect }), [days, defect]);
  const alerts = useLoad(() => analyticsApi.alerts());
  const actions = useLoad(() => analyticsApi.actions());
  const [form, setForm] = useState({ group_name: '', finding: '', action: '', owner: '' });
  const [error, setError] = useState<string | null>(null);
  const r = data.data;

  const save = async () => {
    setError(null);
    try {
      await analyticsApi.addAction(form);
      setForm({ group_name: '', finding: '', action: '', owner: '' });
      await actions.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save');
    }
  };

  return (
    <div>
      <PageHeader title="Root-Cause Investigation" subtitle="Statistical evidence on where defects concentrate. It points to where to look, and the cause is confirmed on the shop floor." />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
        <Field label="Defect type">
          <select className={inputClass} value={defect} onChange={(e) => setDefect(e.target.value)}>
            <option value="">All flagged units (rejected or in review)</option>{DEFECT_TYPES.map((t) => <option key={t} value={t}>{defectLabel(t)}</option>)}
          </select>
        </Field>
        <Field label="Period">
          <select className={inputClass} value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}
          </select>
        </Field>
      </div>
      <LoadState loading={data.loading} error={data.error} />
      {r && (
        <div className="space-y-4">
          <Banner>{r.note}</Banner>
          <Card title="Open alerts">
            {alerts.data?.filter((a) => a.status !== 'RESOLVED').length ? (
              <Table columns={['Alert', 'Status', '']} rows={alerts.data.filter((a) => a.status !== 'RESOLVED').map((a) => [
                a.message, a.status,
                <span key="b" className="flex gap-1">
                  {a.status === 'OPEN' && <Button onClick={async () => { await analyticsApi.setAlert(a.id, 'ACKNOWLEDGED'); alerts.reload(); }}>Acknowledge</Button>}
                  <Button onClick={async () => { await analyticsApi.setAlert(a.id, 'RESOLVED'); alerts.reload(); }}>Resolve</Button>
                </span>,
              ])} />
            ) : <Empty>No open alerts.</Empty>}
          </Card>
          <Card title="Association with production factors" subtitle={`${r.flagged_units} flagged of ${r.units} units. q values are corrected for multiple comparisons.`}>
            {r.findings.length ? (
              <Table columns={['Factor', 'Group', 'Flagged', 'Rate', 'Elsewhere', 'Odds ratio', 'q', 'Reading']} rows={r.findings.map((f) => [
                f.dimension, <b key="g">{f.group}</b>, `${f.defective}/${f.units}`, pct(f.rate), pct(f.rate_elsewhere), f.odds_ratio, f.q_value,
                f.significant ? <span key="s" className="font-semibold text-[#991B1B]">Associated</span> : 'Not significant',
              ])} />
            ) : <Empty>Each group needs at least 10 units before testing.</Empty>}
          </Card>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card title="Hypotheses to check" subtitle="General process knowledge, not derived from this data.">
              {r.hypotheses.length ? r.hypotheses.map((h) => (
                <div key={h.defect_type} className="mb-3 text-xs">
                  <p className="font-semibold">{defectLabel(h.defect_type)} ({h.count})</p>
                  <ul className="list-disc pl-4 text-[#31302e]">{h.hypotheses.map((x) => <li key={x}>{x}</li>)}</ul>
                </div>
              )) : <Empty>No defects in this period.</Empty>}
            </Card>
            <Card title="Position on the part"><Hotspot grid={r.hotspot.grid} region={r.hotspot.dominant_region} share={r.hotspot.dominant_share} /></Card>
          </div>
          <Card title="Corrective actions" subtitle="Record what was confirmed on the shop floor and what changed.">
            {error && <div className="mb-2"><Banner tone="error">{error}</Banner></div>}
            <div className="grid lg:grid-cols-4 gap-2 mb-3">
              <Field label="Machine, batch or shift"><input className={inputClass} value={form.group_name} onChange={(e) => setForm({ ...form, group_name: e.target.value })} /></Field>
              <Field label="Confirmed finding"><input className={inputClass} value={form.finding} onChange={(e) => setForm({ ...form, finding: e.target.value })} /></Field>
              <Field label="Action taken"><input className={inputClass} value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })} /></Field>
              <Field label="Owner"><input className={inputClass} value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></Field>
            </div>
            <Button disabled={form.finding.length < 3 || form.action.length < 3} onClick={save}>Save action</Button>
            {!!actions.data?.length && <div className="mt-3"><Table columns={['Group', 'Finding', 'Action', 'Owner', 'Status']} rows={actions.data.map((a) => [a.group || '—', a.finding, a.action, a.owner || '—', a.status])} /></div>}
          </Card>
        </div>
      )}
    </div>
  );
}
