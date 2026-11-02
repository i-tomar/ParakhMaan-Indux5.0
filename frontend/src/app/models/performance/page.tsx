'use client';

import React from 'react';
import { API_BASE, fetchJson } from '@/lib/api';
import { Banner, Card, Empty, LoadState, PageHeader, Stat, Table, useLoad } from '@/components/ui';

/* eslint-disable @typescript-eslint/no-explicit-any */
const num = (v: unknown) => (typeof v === 'number' ? v.toFixed(3) : '—');

// Benchmark reports carry a device object; render it as text (objects cannot be React children).
const deviceLabel = (b: any): string => {
  if (b?.label) return String(b.label);
  const d = b?.device || {};
  return [d.cpu, d.system, d.machine, d.in_container ? '(container)' : ''].filter(Boolean).join(' ') || String(b?.file ?? 'unknown');
};

export default function ModelPerformancePage() {
  const report = useLoad(() => fetchJson<any>(`${API_BASE}/edge/evaluation`));
  const r = report.data;
  const a = r?.anomaly;
  const s = r?.segmentation;
  return (
    <div>
      <PageHeader title="Model Performance" subtitle="Results from the held-out test split that training never saw. Numbers are read from the stored evaluation reports." />
      <LoadState loading={report.loading} error={report.error} />
      {r && (
        <div className="space-y-4">
          {!a && !s && <Banner tone="warn">No evaluation report has been generated yet.</Banner>}
          {s && (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                <Stat label="Segmentation mAP@50" value={num(s.box?.map50)} hint="boxes" />
                <Stat label="mAP@50-95" value={num(s.box?.map50_95)} />
                <Stat label="Mask mAP@50" value={num(s.mask?.map50)} />
                <Stat label="Miss rate" value={num(s.image_level?.miss_rate)} hint="defective image passed" />
                <Stat label="False-reject rate" value={num(s.image_level?.false_reject_rate)} hint="good image flagged" />
              </div>
              <Card title="Per-class results" subtitle={s.data}>
                <Table columns={['Class', 'Instances', 'Precision', 'Recall', 'F1', 'AP@50', 'AP@50-95']} rows={(s.per_class || []).map((c: any) => [c.name, c.instances, num(c.precision), num(c.recall), num(c.f1), num(c.ap50), num(c.ap50_95)])} />
              </Card>
            </>
          )}
          {a && (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Stat label="Anomaly image AUROC" value={num(a.mean_image_auroc)} hint={`${a.categories} product types`} />
                <Stat label="Pixel AUROC" value={num(a.mean_pixel_auroc)} />
                <Stat label="Unknown-defect recall" value={num(a.withheld_unknown_defects?.recall_at_val_threshold)} hint="kinds never given to the detector" />
                <Stat label="Latency p50" value={`${a.latency_ms_p50} ms`} hint={`p95 ${a.latency_ms_p95} ms`} />
              </div>
              <Card title="Anomaly model by product" subtitle={a.data}>
                <Table columns={['Product', 'Test images', 'Image AUROC', 'Pixel AUROC', 'F1', 'Miss rate', 'False-reject rate']} rows={Object.entries(a.per_category as Record<string, any>).map(([k, v]) => [
                  k, v.test_images, num(v.image_auroc), num(v.pixel_auroc), num(v.at_val_threshold.f1), num(v.at_val_threshold.miss_rate), num(v.at_val_threshold.false_reject_rate),
                ])} />
              </Card>
            </>
          )}
          {(r.benchmarks || []).length > 0 && (
            <Card title="Measured pipeline latency" subtitle="Full pipeline (segmentation + anomaly + fusion) on real images. Each row is the device it was measured on; no other hardware is claimed.">
              <Table
                columns={['Measured on', 'p50 ms', 'p95 ms', 'p99 ms', 'Sequential FPS', 'Segmentation p50', 'Anomaly p50', 'Runs']}
                rows={(r.benchmarks as any[]).map((b) => [
                  deviceLabel(b),
                  b.latency_ms?.p50 ?? '—',
                  b.latency_ms?.p95 ?? '—',
                  b.latency_ms?.p99 ?? '—',
                  b.throughput_fps_sequential ?? '—',
                  b.stage_ms_p50?.segmentation_ms ?? '—',
                  b.stage_ms_p50?.anomaly_ms ?? '—',
                  b.runs ?? '—',
                ])}
              />
              {r.benchmarks[0]?.not_measured && <p className="mt-3 text-xs text-[#615d59]">{r.benchmarks[0].not_measured}</p>}
            </Card>
          )}
          {!a && !s && <Card><Empty>Run the evaluation scripts in ml/ to populate this page.</Empty></Card>}
        </div>
      )}
    </div>
  );
}
