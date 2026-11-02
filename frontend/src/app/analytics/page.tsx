'use client';

import React, { useState } from 'react';
import { analyticsApi, pct, productionApi } from '@/lib/industrial';
import { Card, Field, LoadState, PageHeader, Stat, inputClass, useLoad } from '@/components/ui';
import { ControlChart, GroupBars, Hotspot, ParetoBars } from '@/components/charts';

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [productId, setProductId] = useState('');
  const [machineId, setMachineId] = useState('');
  const [shift, setShift] = useState('');
  const [realOnly, setRealOnly] = useState(false);
  const products = useLoad(() => productionApi.products());
  const machines = useLoad(() => productionApi.machines());
  const data = useLoad(
    () => analyticsApi.overview({ days, product_id: productId, machine_id: machineId, shift, include_synthetic: !realOnly }),
    [days, productId, machineId, shift, realOnly],
  );
  const o = data.data;
  return (
    <div>
      <PageHeader title="Defect Analytics" subtitle="Which defects occur most, and where." />
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 mb-4 items-end">
        <Field label="Period">
          <select className={inputClass} value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[1, 7, 30, 90].map((d) => <option key={d} value={d}>Last {d} day{d > 1 ? 's' : ''}</option>)}
          </select>
        </Field>
        <Field label="Product">
          <select className={inputClass} value={productId} onChange={(e) => setProductId(e.target.value)}>
            <option value="">All</option>{(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Machine">
          <select className={inputClass} value={machineId} onChange={(e) => setMachineId(e.target.value)}>
            <option value="">All</option>{(machines.data || []).map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
          </select>
        </Field>
        <Field label="Shift">
          <select className={inputClass} value={shift} onChange={(e) => setShift(e.target.value)}>
            <option value="">All</option><option>A</option><option>B</option><option>C</option>
          </select>
        </Field>
        <label className="flex items-center gap-2 text-xs pb-2"><input type="checkbox" checked={realOnly} onChange={(e) => setRealOnly(e.target.checked)} />Exclude simulated units</label>
      </div>
      <LoadState loading={data.loading} error={data.error} />
      {o && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="Units" value={o.kpis.units.toLocaleString()} />
            <Stat label="First-pass yield" value={pct(o.kpis.first_pass_yield)} />
            <Stat label="Rejection rate" value={pct(o.kpis.rejection_rate)} />
            <Stat label="Manual review" value={pct(o.kpis.review_share)} />
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card title="Defect Pareto"><ParetoBars rows={o.pareto} /></Card>
            <Card title="Rejection trend" subtitle="Dashed line is the 3σ limit from earlier periods. Red points exceeded it."><ControlChart points={o.trend} /></Card>
            <Card title="By machine"><GroupBars rows={o.by_machine} /></Card>
            <Card title="By shift"><GroupBars rows={o.by_shift} /></Card>
            <Card title="By batch"><GroupBars rows={o.by_batch} /></Card>
            <Card title="By product"><GroupBars rows={o.by_product} /></Card>
            <Card title="Position on the part"><Hotspot grid={o.hotspot.grid} region={o.hotspot.dominant_region} share={o.hotspot.dominant_share} /></Card>
          </div>
        </div>
      )}
    </div>
  );
}
