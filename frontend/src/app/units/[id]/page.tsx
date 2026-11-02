'use client';

import React, { use, useState } from 'react';
import Link from 'next/link';
import { getStorageUrl } from '@/lib/api';
import { ProtectedImg } from '@/components/ProtectedImg';
import { UnitDetection, learningApi, productionApi } from '@/lib/industrial';
import { defectColor, defectLabel } from '@/lib/defects';
import { Banner, Button, Card, DecisionBadge, Empty, LoadState, PageHeader, SimulatedBadge, Table, useLoad } from '@/components/ui';
import { formatDate } from '@/lib/formatters';

function Annotated({ src, detections, masks }: { src: string; detections: UnitDetection[]; masks: boolean }) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  return (
    <div className="bg-[#1b1b1b] rounded-lg flex justify-center p-2">
      <div className="relative inline-block">
        <ProtectedImg src={src} alt="Inspected unit" className="block max-h-[440px] w-auto" onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
        {size && (
          <svg viewBox={`0 0 ${size.w} ${size.h}`} className="absolute inset-0 w-full h-full pointer-events-none">
            {detections.map((d) => {
              const [x1, y1, x2, y2] = d.bbox;
              const colour = defectColor(d.defect_type);
              const polygon = d.metrics?.mask_polygon as number[][] | undefined;
              const stroke = Math.max(2, size.w / 300);
              return (
                <g key={d.id}>
                  {masks && polygon?.length ? <polygon points={polygon.map((p) => p.join(',')).join(' ')} fill={colour} fillOpacity={0.4} stroke={colour} strokeWidth={stroke} /> : null}
                  <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill="none" stroke={colour} strokeWidth={stroke} />
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}

export default function UnitPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const unit = useLoad(() => productionApi.unit(id), [id]);
  const [view, setView] = useState<'overlay' | 'original' | 'heatmap'>('overlay');
  const [message, setMessage] = useState<string | null>(null);
  const u = unit.data;
  if (!u) return <LoadState loading={unit.loading} error={unit.error} />;

  const finalise = async (decision: string) => {
    await productionApi.overrideUnit(id, decision);
    const label = decision === 'ACCEPT' ? 'GOOD' : u.detections?.[0]?.defect_type || null;
    if (label) {
      const res = await learningApi.labelUnit(id, label);
      setMessage(res.added ? `Decision saved. Image added to the ${res.split} set as ${label}.` : 'Decision saved. This image was already in the dataset.');
    }
    unit.reload();
  };

  const d = u.dimensional;
  return (
    <div>
      <PageHeader title={u.unit_code} subtitle={`${u.product || 'Unknown product'} · ${formatDate(u.inspected_at)}`}
        actions={<><DecisionBadge decision={u.final_decision || u.decision} />{u.is_synthetic && <SimulatedBadge />}</>} />
      {message && <div className="mb-4"><Banner>{message}</Banner></div>}
      <div className="grid lg:grid-cols-[1fr_320px] gap-4">
        <div className="space-y-4 min-w-0">
          <Card title="Evidence" actions={
            <div className="flex gap-1">
              {(['overlay', 'original', ...(u.heatmap_path ? ['heatmap'] : [])] as ('overlay' | 'original' | 'heatmap')[]).map((v) => (
                <Button key={v} variant={view === v ? 'primary' : 'secondary'} onClick={() => setView(v)}>{{ overlay: 'Boxes & masks', original: 'Original', heatmap: 'Anomaly heatmap' }[v]}</Button>
              ))}
            </div>
          }>
            {u.image_path ? (
              view === 'heatmap' ? (
                <div className="bg-[#1b1b1b] rounded-lg flex justify-center p-2"><ProtectedImg src={getStorageUrl(u.heatmap_path || '')} alt="Anomaly heatmap" className="max-h-[440px]" /></div>
              ) : <Annotated src={getStorageUrl(u.image_path)} detections={view === 'overlay' ? u.detections || [] : []} masks />
            ) : <Empty>No image stored for this unit.</Empty>}
          </Card>
          <Card title={`Defects (${u.detections?.length || 0})`}>
            {u.detections?.length ? (
              <Table columns={['Type', 'Severity', 'Confidence', 'Size', 'Evidence', 'Model']} rows={u.detections.map((x) => [
                <span key="t" className="flex items-center gap-1.5 font-medium"><span className="w-2 h-2 rounded-sm" style={{ background: defectColor(x.defect_type) }} />{defectLabel(x.defect_type)}</span>,
                x.severity, `${Math.round(x.confidence * 100)}%`,
                x.length_mm !== null ? `${x.length_mm} × ${x.width_mm} mm` : `${(x.area_ratio * 100).toFixed(2)}% of image`,
                x.detector, x.model_version || '—',
              ])} />
            ) : <Empty>No defects found.</Empty>}
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Decision">
            {u.reasons.length ? <ul className="text-xs text-[#31302e] space-y-1 list-disc pl-4">{u.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : <p className="text-xs text-[#615d59]">No rule triggered.</p>}
            {!u.final_decision && u.decision === 'MANUAL_REVIEW' && (
              <div className="flex gap-2 mt-3">
                <Button variant="primary" onClick={() => finalise('ACCEPT')}>Accept as good</Button>
                <Button variant="danger" onClick={() => finalise('REJECT')}>Reject</Button>
              </div>
            )}
            {u.reject_events?.map((r) => <p key={String(r.at)} className="text-xs text-[#615d59] mt-2">Reject signal: {r.status} via {r.actuator}{r.fire_after_ms !== null ? `, after ${r.fire_after_ms} ms` : ''}</p>)}
          </Card>
          <Card title="Traceability">
            <dl className="text-xs space-y-1.5">
              {[['Batch', u.batch], ['Machine', u.machine], ['Line', u.line], ['Shift', u.shift], ['Source', u.source],
                ['Anomaly score', u.anomaly_score !== null ? `${u.anomaly_score} × threshold` : null], ['Inference', u.latency_ms ? `${u.latency_ms} ms` : null],
                ['Evidence streams', u.streams.join(', ')]].map(([k, v]) => (
                <div key={k as string} className="flex justify-between gap-3"><dt className="text-[#615d59]">{k}</dt><dd className="font-medium text-right">{v || '—'}</dd></div>
              ))}
            </dl>
            {u.inspection_id && <Link className="block mt-3 text-xs font-semibold text-[#0075de]" href={`/defects/${u.inspection_id}`}>Open inspection record</Link>}
          </Card>
          {d && (
            <Card title="Dimensions" subtitle={d.status}>
              {d.tolerances?.length > 0 && (
                <Table columns={['Feature', 'Measured', 'Nominal', 'Result']} rows={d.tolerances.map((t: { feature: string; measured: number; nominal: number; status: string }) => [t.feature, t.measured, t.nominal, t.status])} />
              )}
              <p className="text-[11px] text-[#615d59] mt-2">{d.calibration?.method}. Physical accuracy not validated.</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
