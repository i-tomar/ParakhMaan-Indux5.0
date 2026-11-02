'use client';

import React, { useState } from 'react';
import { analyticsApi, edgeApi, pct, productionApi } from '@/lib/industrial';
import { Banner, Button, Card, Empty, Field, LoadState, PageHeader, Stat, Table, inputClass, useLoad } from '@/components/ui';

export default function LinePage() {
  const lines = useLoad(() => productionApi.lines());
  const overview = useLoad(() => analyticsApi.overview({ days: 1 }), [], 10000);
  const edge = useLoad(() => edgeApi.status(), [], 5000);
  const [form, setForm] = useState({ code: '', name: '', belt_speed_mm_s: 200, camera_to_diverter_mm: 600, pitch_mm: 300 });
  const [machine, setMachine] = useState({ code: '', name: '', line_id: '' });
  const [error, setError] = useState<string | null>(null);
  const [bench, setBench] = useState<{ p50_ms: number; p95_ms: number; fps: number } | null>(null);

  const guard = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      await lines.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  };

  const k = overview.data?.kpis;
  const sessions = edge.data?.sessions || [];
  return (
    <div>
      <PageHeader title="Line Monitoring" subtitle="Current day, active inspection sessions, and each line's latency budget." />
      {error && <div className="mb-4"><Banner tone="error">{error}</Banner></div>}
      <LoadState loading={lines.loading} error={lines.error} />
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat label="Units today" value={k?.units ?? '—'} />
          <Stat label="First-pass yield" value={pct(k?.first_pass_yield)} />
          <Stat label="Active sessions" value={sessions.length} />
          <Stat label="Peak memory" value={edge.data ? `${edge.data.process.peak_memory_mb} MB` : '—'} />
        </div>
        <Card title="Lines" subtitle="The maximum decision latency is the time a part takes to reach the diverter, less actuator time.">
          {lines.data?.length ? (
            <Table columns={['Line', 'Belt', 'Units/min', 'Time per unit', 'Max decision latency', 'Reject output', 'Machines']} rows={lines.data.map((l) => [
              <b key="c">{l.code}</b>, `${l.belt_speed_mm_s} mm/s`, l.budget.units_per_minute, `${l.budget.time_per_unit_ms} ms`, `${l.budget.max_decision_latency_ms} ms`,
              l.actuator_kind, l.machines.map((m) => m.code).join(', ') || '—',
            ])} />
          ) : <Empty>No lines defined yet.</Empty>}
          <div className="flex items-center gap-3 mt-3">
            <Button onClick={() => guard(async () => setBench(await edgeApi.benchmark()))}>Measure inference on this device</Button>
            {bench && <span className="text-xs tabular-nums">p50 {bench.p50_ms} ms · p95 {bench.p95_ms} ms · {bench.fps} fps</span>}
          </div>
        </Card>
        <div className="grid lg:grid-cols-2 gap-4">
          <Card title="Add line">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Code"><input className={inputClass} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></Field>
              <Field label="Name"><input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
              <Field label="Belt speed (mm/s)"><input type="number" className={inputClass} value={form.belt_speed_mm_s} onChange={(e) => setForm({ ...form, belt_speed_mm_s: Number(e.target.value) })} /></Field>
              <Field label="Camera to diverter (mm)"><input type="number" className={inputClass} value={form.camera_to_diverter_mm} onChange={(e) => setForm({ ...form, camera_to_diverter_mm: Number(e.target.value) })} /></Field>
              <Field label="Unit pitch (mm)"><input type="number" className={inputClass} value={form.pitch_mm} onChange={(e) => setForm({ ...form, pitch_mm: Number(e.target.value) })} /></Field>
            </div>
            <Button className="mt-3" disabled={!form.code || !form.name} onClick={() => guard(() => productionApi.createLine(form))}>Save line</Button>
          </Card>
          <Card title="Add machine">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Code"><input className={inputClass} value={machine.code} onChange={(e) => setMachine({ ...machine, code: e.target.value })} /></Field>
              <Field label="Name"><input className={inputClass} value={machine.name} onChange={(e) => setMachine({ ...machine, name: e.target.value })} /></Field>
              <Field label="Line">
                <select className={inputClass} value={machine.line_id} onChange={(e) => setMachine({ ...machine, line_id: e.target.value })}>
                  <option value="">None</option>
                  {(lines.data || []).map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
                </select>
              </Field>
            </div>
            <Button className="mt-3" disabled={!machine.code || !machine.name} onClick={() => guard(() => productionApi.createMachine({ ...machine, line_id: machine.line_id || null }))}>Save machine</Button>
          </Card>
        </div>
      </div>
    </div>
  );
}
