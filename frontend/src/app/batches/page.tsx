'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { openProtectedFile } from '@/lib/api';
import { pct, productionApi } from '@/lib/industrial';
import { defectLabel } from '@/lib/defects';
import { Banner, Button, Card, Empty, Field, LoadState, PageHeader, SimulatedBadge, Table, inputClass, useLoad } from '@/components/ui';

export default function BatchesPage() {
  const products = useLoad(() => productionApi.products());
  const batches = useLoad(() => productionApi.batches());
  const [name, setName] = useState('');
  const [spec, setSpec] = useState('');
  const [code, setCode] = useState('');
  const [productId, setProductId] = useState('');
  const [planned, setPlanned] = useState('');
  const [error, setError] = useState<string | null>(null);

  const guard = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      await Promise.all([products.reload(), batches.reload()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  };

  const parseSpec = () => spec.split('\n').filter((l) => l.trim()).map((l) => {
    const [feature, nominal, minus, plus] = l.split(',').map((x) => x.trim());
    return { feature, nominal: Number(nominal), minus: Number(minus), plus: Number(plus ?? minus) };
  });

  return (
    <div>
      <PageHeader title="Products & Batches" subtitle="Each batch ties units to a product so yield and defects trace back to production." />
      {error && <div className="mb-4"><Banner tone="error">{error}</Banner></div>}
      <LoadState loading={batches.loading} error={batches.error} />
      <div className="space-y-4">
        <Card title="Batches">
          {batches.data?.length ? (
            <Table columns={['Batch', 'Product', 'Status', 'Units', 'Yield', 'Rejected', 'Top defect', '']} rows={batches.data.map((b) => [
              <span key="c" className="flex items-center gap-1.5"><Link className="text-[#0075de] font-medium" href={`/history?batch=${b.id}`}>{b.code}</Link>{b.is_synthetic && <SimulatedBadge />}</span>,
              b.product || '—', b.status, b.kpis.units, pct(b.kpis.first_pass_yield), pct(b.kpis.rejection_rate), b.top_defect ? defectLabel(b.top_defect) : '—',
              <span key="a" className="flex gap-1">
                <Button onClick={() => guard(() => openProtectedFile(productionApi.batchReportUrl(b.id)))}>PDF</Button>
                {b.status === 'OPEN' && <Button onClick={() => guard(() => productionApi.closeBatch(b.id))}>Close</Button>}
              </span>,
            ])} />
          ) : <Empty>No batches yet.</Empty>}
        </Card>
        <div className="grid lg:grid-cols-2 gap-4">
          <Card title="New batch">
            <div className="space-y-3">
              <Field label="Batch code"><input className={inputClass} value={code} onChange={(e) => setCode(e.target.value)} /></Field>
              <Field label="Product">
                <select className={inputClass} value={productId} onChange={(e) => setProductId(e.target.value)}>
                  <option value="">Select</option>
                  {(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Planned quantity"><input type="number" className={inputClass} value={planned} onChange={(e) => setPlanned(e.target.value)} /></Field>
              <Button disabled={!code || !productId} onClick={() => guard(async () => { await productionApi.createBatch({ code, product_id: productId, planned_quantity: planned ? Number(planned) : null }); setCode(''); })}>Create batch</Button>
            </div>
          </Card>
          <Card title="New product" subtitle="Then add good images under Dataset & Feedback and train its anomaly model.">
            <div className="space-y-3">
              <Field label="Name"><input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Tolerances, one per line: feature, nominal, minus, plus">
                <textarea className={inputClass} rows={3} placeholder="length_mm, 100, 0.5, 0.5" value={spec} onChange={(e) => setSpec(e.target.value)} />
              </Field>
              <Button disabled={!name} onClick={() => guard(async () => { await productionApi.createProduct({ name, dimension_spec: parseSpec() }); setName(''); setSpec(''); })}>Create product</Button>
            </div>
          </Card>
        </div>
        <Card title={`Products (${products.data?.length || 0})`}>
          {products.data?.length ? (
            <Table columns={['Product', 'Key', 'Anomaly model', 'Golden', 'Tolerances']} rows={products.data.map((p) => [p.name, p.key, p.anomaly_model || 'Not trained', p.golden_references.length, p.dimension_spec.length])} />
          ) : <Empty>No products yet.</Empty>}
        </Card>
      </div>
    </div>
  );
}
