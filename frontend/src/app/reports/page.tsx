'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { defectApi, openProtectedFile } from '@/lib/api';
import { pct, productionApi } from '@/lib/industrial';
import { Banner, Button, Card, Empty, LoadState, PageHeader, SimulatedBadge, Table, useLoad } from '@/components/ui';
import { formatDate } from '@/lib/formatters';

export default function ReportsPage() {
  const batches = useLoad(() => productionApi.batches());
  const inspections = useLoad(() => defectApi.listInspections());
  const [error, setError] = useState<string | null>(null);

  const open = async (url: string) => {
    setError(null);
    try {
      await openProtectedFile(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Report failed');
    }
  };

  return (
    <div>
      <PageHeader title="Reports" subtitle="PDF reports generated from the logged records." />
      {error && <div className="mb-3"><Banner tone="error">{error}</Banner></div>}
      <div className="space-y-4">
        <Card title="Batch quality reports">
          <LoadState loading={batches.loading} error={batches.error} />
          {batches.data?.length ? (
            <Table columns={['Batch', 'Product', 'Units', 'Yield', '']} rows={batches.data.map((b) => [
              <span key="c" className="flex items-center gap-1.5">{b.code}{b.is_synthetic && <SimulatedBadge />}</span>, b.product || '—', b.kpis.units, pct(b.kpis.first_pass_yield),
              <Button key="b" onClick={() => open(productionApi.batchReportUrl(b.id))}>Open PDF</Button>,
            ])} />
          ) : !batches.loading && <Empty>No batches yet.</Empty>}
        </Card>
        <Card title="Inspection reports">
          <LoadState loading={inspections.loading} error={inspections.error} />
          {inspections.data?.length ? (
            <Table columns={['Inspection', 'Product', 'Outcome', 'Date', '']} rows={inspections.data.slice(0, 30).map((i) => [
              <Link key={i.id} className="text-[#0075de] font-medium" href={`/defects/${i.id}`}>{i.inspection_number}</Link>, i.product_name || '—', i.overall_outcome, formatDate(i.created_at),
              <Button key="b" onClick={() => open(defectApi.getReportUrl(i.id))}>Open PDF</Button>,
            ])} />
          ) : !inspections.loading && <Empty>No inspections yet.</Empty>}
        </Card>
      </div>
    </div>
  );
}
