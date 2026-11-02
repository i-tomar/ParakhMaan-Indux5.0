'use client';

import React, { useState } from 'react';
import { ModelVersion, learningApi } from '@/lib/industrial';
import { Banner, Button, Card, Empty, LoadState, PageHeader, Table, useLoad } from '@/components/ui';
import { formatDate } from '@/lib/formatters';

const STATUS: Record<string, string> = {
  PRODUCTION: 'bg-green-100 text-[#166534]',
  CANDIDATE: 'bg-blue-100 text-[#213183]',
  REFUSED: 'bg-red-100 text-[#991B1B]',
  ARCHIVED: 'bg-gray-100 text-gray-700',
};

export default function ModelVersionsPage() {
  const models = useLoad(() => learningApi.models());
  const [error, setError] = useState<string | null>(null);

  const act = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    }
    await models.reload();
  };

  const canRollback = (m: ModelVersion) =>
    m.status === 'PRODUCTION' && !!models.data?.some((o) => o.kind === m.kind && o.product_key === m.product_key && o.status === 'ARCHIVED' && o.promoted_at);

  return (
    <div>
      <PageHeader title="Model Versions" subtitle="A candidate reaches production only by clearing the gate on the fixed holdout. Any earlier production version can be restored." />
      {error && <div className="mb-3"><Banner tone="error">{error}</Banner></div>}
      <LoadState loading={models.loading} error={models.error} />
      {models.data && (models.data.length === 0 ? <Card><Empty>No models registered.</Empty></Card> : (
        <div className="space-y-3">
          {models.data.map((m) => (
            <Card key={m.id} title={m.version} subtitle={`${m.kind}${m.product_key ? ` · ${m.product_key}` : ''} · ${formatDate(m.created_at)}`}
              actions={<span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS[m.status] || ''}`}>{m.status}</span>}>
              {m.gate_result ? (
                <Table columns={['Check', 'Candidate', 'Production', 'Limit', 'Result']} rows={m.gate_result.checks.map((c) => [c.check, String(c.candidate ?? '—'), String(c.production ?? '—'), String(c.limit ?? '—'), c.passed ? 'Pass' : 'Fail'])} />
              ) : <p className="text-xs text-[#615d59]">{m.notes || 'No gate result recorded.'}</p>}
              <div className="flex gap-2 mt-3">
                {m.status === 'CANDIDATE' && <Button variant="primary" onClick={() => act(() => learningApi.promote(m.id))}>Promote</Button>}
                {canRollback(m) && <Button variant="danger" onClick={() => act(() => learningApi.rollback(m.kind, m.product_key))}>Roll back</Button>}
              </div>
            </Card>
          ))}
        </div>
      ))}
    </div>
  );
}
