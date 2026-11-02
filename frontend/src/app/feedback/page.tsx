'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { learningApi, productionApi } from '@/lib/industrial';
import { Banner, Button, Card, DecisionBadge, Empty, Field, LoadState, PageHeader, Stat, Table, inputClass, useLoad } from '@/components/ui';
import { formatDate } from '@/lib/formatters';

export default function FeedbackPage() {
  const queue = useLoad(() => learningApi.reviewQueue());
  const products = useLoad(() => productionApi.products());
  const summary = useLoad(() => learningApi.sampleSummary());
  const datasets = useLoad(() => learningApi.datasets());
  const jobs = useLoad(() => learningApi.jobs(), [], 4000);
  const [productKey, setProductKey] = useState('');
  const [label, setLabel] = useState('GOOD');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const guard = async (work: () => Promise<void>) => {
    setError(null);
    setMessage(null);
    try {
      await work();
      await Promise.all([summary.reload(), datasets.reload(), jobs.reload()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  };

  return (
    <div>
      <PageHeader title="Dataset & Feedback" subtitle="Reviewed units become labelled samples. Every fifth sample per label goes to a permanent holdout used for independent validation." />
      {error && <div className="mb-3"><Banner tone="error">{error}</Banner></div>}
      {message && <div className="mb-3"><Banner>{message}</Banner></div>}
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <Stat label="Units awaiting review" value={queue.data?.units.length ?? '—'} />
          <Stat label="Detections awaiting feedback" value={queue.data?.pending_detections ?? '—'} />
          <Stat label="Samples collected" value={(summary.data || []).reduce((n, s) => n + s.count, 0)} />
        </div>
        <Card title="Review queue">
          <LoadState loading={queue.loading} error={queue.error} />
          {queue.data?.units.length ? (
            <Table columns={['Unit', 'Product', 'Reason', 'Decision', 'Time']} rows={queue.data.units.map((u) => [
              <Link key={u.id} className="text-[#0075de] font-medium" href={`/units/${u.id}`}>{u.unit_code}</Link>, u.product || '—', u.reasons[0] || '—', <DecisionBadge key="d" decision={u.decision} />, formatDate(u.inspected_at),
            ])} />
          ) : !queue.loading && <Empty>The review queue is empty.</Empty>}
        </Card>
        <div className="grid lg:grid-cols-2 gap-4">
          <Card title="Collect samples">
            <div className="space-y-3">
              <Field label="Product">
                <select className={inputClass} value={productKey} onChange={(e) => setProductKey(e.target.value)}>
                  <option value="">Select</option>
                  {(products.data || []).map((p) => <option key={p.id} value={p.key}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Label">
                <select className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)}>
                  {['GOOD', 'SCRATCH', 'CRACK', 'DENT', 'DISCOLOURATION', 'DIMENSIONAL_ANOMALY', 'OTHER_DEFECT'].map((x) => <option key={x}>{x}</option>)}
                </select>
              </Field>
              <input type="file" multiple accept="image/*" className="text-xs" disabled={!productKey}
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  if (files.length) guard(async () => {
                    const r = await learningApi.uploadSamples(productKey, label, files);
                    setMessage(`${r.added} added, ${r.duplicates} duplicates, ${r.unreadable} unreadable.`);
                  });
                }} />
              <div className="flex gap-2">
                <Button disabled={!productKey} onClick={() => guard(async () => { const d = await learningApi.snapshot(productKey); setMessage(`Dataset v${d.version}: ${d.sample_count} samples.`); })}>Snapshot dataset</Button>
                <Button variant="primary" disabled={!productKey} onClick={() => guard(async () => { await learningApi.train(productKey); setMessage('Training started. The candidate appears under Model Versions.'); })}>Train anomaly model</Button>
              </div>
            </div>
          </Card>
          <Card title="Training jobs">
            {jobs.data?.length ? (
              <Table columns={['Product', 'Status', 'Candidate', 'Started']} rows={jobs.data.slice(0, 8).map((j) => [j.product_key, j.error ? `FAILED: ${j.error}` : j.status, j.candidate_version || '—', formatDate(j.created_at)])} />
            ) : <Empty>No training jobs yet.</Empty>}
          </Card>
        </div>
        <Card title="Dataset versions">
          {datasets.data?.length ? (
            <Table columns={['Product', 'Version', 'Samples', 'Split / label', 'Hash']} rows={datasets.data.map((d) => [
              d.product_key, `v${d.version}`, d.sample_count, Object.entries(d.label_counts as Record<string, number>).map(([k, v]) => `${k}: ${v}`).join(', '), String(d.content_hash).slice(0, 12),
            ])} />
          ) : <Empty>No dataset snapshots yet.</Empty>}
        </Card>
      </div>
    </div>
  );
}
