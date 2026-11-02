'use client';

import React, { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { productionApi } from '@/lib/industrial';
import { Button, Card, DecisionBadge, Empty, Field, LoadState, PageHeader, SimulatedBadge, Table, inputClass, useLoad } from '@/components/ui';
import { formatDate } from '@/lib/formatters';

const PAGE = 25;

function History() {
  const batch = useSearchParams().get('batch') || undefined;
  const [decision, setDecision] = useState('');
  const [shift, setShift] = useState('');
  const [machineId, setMachineId] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const machines = useLoad(() => productionApi.machines());
  const units = useLoad(
    () => productionApi.units({ decision, shift, machine_id: machineId, search, batch_id: batch, limit: PAGE, offset }),
    [decision, shift, machineId, search, batch, offset],
  );
  const reset = <T,>(set: (v: T) => void) => (v: T) => { setOffset(0); set(v); };

  return (
    <div>
      <PageHeader title="Inspection History" subtitle="Every inspected unit, across uploads, video and live lines." />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
        <Field label="Decision">
          <select className={inputClass} value={decision} onChange={(e) => reset(setDecision)(e.target.value)}>
            <option value="">All</option><option value="ACCEPT">Accept</option><option value="REJECT">Reject</option><option value="MANUAL_REVIEW">Manual review</option>
          </select>
        </Field>
        <Field label="Shift">
          <select className={inputClass} value={shift} onChange={(e) => reset(setShift)(e.target.value)}>
            <option value="">All</option><option>A</option><option>B</option><option>C</option>
          </select>
        </Field>
        <Field label="Machine">
          <select className={inputClass} value={machineId} onChange={(e) => reset(setMachineId)(e.target.value)}>
            <option value="">All</option>{(machines.data || []).map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
          </select>
        </Field>
        <Field label="Unit code"><input className={inputClass} value={search} onChange={(e) => reset(setSearch)(e.target.value)} /></Field>
      </div>
      <LoadState loading={units.loading} error={units.error} />
      {units.data && (
        <Card>
          {units.data.items.length ? (
            <>
              <Table columns={['Unit', 'Product', 'Batch', 'Machine', 'Shift', 'Source', 'Decision', 'Inspected']} rows={units.data.items.map((u) => [
                <Link key={u.id} className="text-[#0075de] font-medium" href={`/units/${u.id}`}>{u.unit_code}</Link>,
                u.product || '—', u.batch || '—', u.machine || '—', u.shift || '—', u.source,
                <span key="d" className="flex items-center gap-1.5"><DecisionBadge decision={u.final_decision || u.decision} />{u.is_synthetic && <SimulatedBadge />}</span>,
                formatDate(u.inspected_at),
              ])} />
              <div className="flex items-center justify-between mt-3 text-xs text-[#615d59]">
                <span>{offset + 1}–{Math.min(offset + PAGE, units.data.total)} of {units.data.total}</span>
                <span className="flex gap-2">
                  <Button disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Previous</Button>
                  <Button disabled={offset + PAGE >= units.data.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
                </span>
              </div>
            </>
          ) : <Empty>No units match these filters.</Empty>}
        </Card>
      )}
    </div>
  );
}

export default function HistoryPage() {
  return <Suspense><History /></Suspense>;
}
