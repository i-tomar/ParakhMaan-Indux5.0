'use client';

import React, { useState } from 'react';
import { Calibration, metrologyApi, productionApi } from '@/lib/industrial';
import { Banner, Button, Card, Empty, Field, PageHeader, Table, inputClass, useLoad } from '@/components/ui';

export default function DimensionalPage() {
  const calibrations = useLoad(() => metrologyApi.calibrations());
  const products = useLoad(() => productionApi.products());
  const [name, setName] = useState('');
  const [knownMm, setKnownMm] = useState('');
  const [px, setPx] = useState('');
  const [board, setBoard] = useState<File | null>(null);
  const [cols, setCols] = useState(9);
  const [rows, setRows] = useState(6);
  const [square, setSquare] = useState(10);
  const [calibrationId, setCalibrationId] = useState('');
  const [productId, setProductId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const guard = async (work: () => Promise<void>) => {
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  };

  const selected: Calibration | undefined = calibrations.data?.find((c) => c.id === calibrationId);

  return (
    <div>
      <PageHeader title="Dimensional Inspection" subtitle="Calibrated measurement of length, width, diameter and outline, checked against product tolerances." />
      {error && <div className="mb-4"><Banner tone="error">{error}</Banner></div>}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="1. Calibrate">
          <div className="space-y-3">
            <Field label="Calibration name"><input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <p className="text-xs font-semibold">Known reference length</p>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Known length (mm)"><input type="number" className={inputClass} value={knownMm} onChange={(e) => setKnownMm(e.target.value)} /></Field>
              <Field label="Measured (pixels)"><input type="number" className={inputClass} value={px} onChange={(e) => setPx(e.target.value)} /></Field>
            </div>
            <Button disabled={!name || !knownMm || !px} onClick={() => guard(async () => {
              const c = await metrologyApi.referenceCalibration({ name, known_mm: Number(knownMm), measured_px: Number(px) });
              await calibrations.reload();
              setCalibrationId(c.id);
            })}>Save reference calibration</Button>
            <p className="text-xs font-semibold pt-2">Checkerboard (also corrects perspective)</p>
            <input type="file" accept="image/*" className="text-xs" onChange={(e) => setBoard(e.target.files?.[0] || null)} />
            <div className="grid grid-cols-3 gap-2">
              <Field label="Inner columns"><input type="number" className={inputClass} value={cols} onChange={(e) => setCols(Number(e.target.value))} /></Field>
              <Field label="Inner rows"><input type="number" className={inputClass} value={rows} onChange={(e) => setRows(Number(e.target.value))} /></Field>
              <Field label="Square (mm)"><input type="number" className={inputClass} value={square} onChange={(e) => setSquare(Number(e.target.value))} /></Field>
            </div>
            <Button disabled={!name || !board} onClick={() => guard(async () => {
              const c = await metrologyApi.checkerboard(board as File, name, cols, rows, square);
              await calibrations.reload();
              setCalibrationId(c.id);
            })}>Calibrate from board</Button>
          </div>
        </Card>
        <Card title="2. Measure a part">
          <div className="space-y-3">
            <Field label="Calibration">
              <select className={inputClass} value={calibrationId} onChange={(e) => setCalibrationId(e.target.value)}>
                <option value="">Select</option>
                {(calibrations.data || []).map((c) => <option key={c.id} value={c.id}>{c.name} ({c.mm_per_px.toFixed(4)} mm/px)</option>)}
              </select>
            </Field>
            <Field label="Product tolerance (optional)">
              <select className={inputClass} value={productId} onChange={(e) => setProductId(e.target.value)}>
                <option value="">None</option>
                {(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <input type="file" accept="image/*" className="text-xs" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <Button variant="primary" disabled={!file || !calibrationId} onClick={() => guard(async () => setResult(await metrologyApi.inspect(file as File, calibrationId, productId || undefined)))}>Measure</Button>
            {selected && (
              <div>
                <p className="text-[11px] font-semibold mt-2">Assumptions of this calibration</p>
                <ul className="text-[11px] text-[#615d59] list-disc pl-4">{selected.details.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
            )}
          </div>
        </Card>
        <Card title="Result" subtitle={result?.status} className="lg:col-span-2">
          {!result ? <Empty>No measurement yet.</Empty> : result.status === 'PART_NOT_FOUND' ? <Banner tone="warn">{result.note}</Banner> : (
            <div className="grid lg:grid-cols-2 gap-6">
              <Table columns={['Feature', 'Value']} rows={Object.entries(result.measurements as Record<string, number>).map(([k, v]) => [k.replace(/_/g, ' '), v])} />
              {result.tolerances.length ? (
                <Table columns={['Feature', 'Measured', 'Nominal', 'Deviation', 'Result']}
                  rows={result.tolerances.map((t: { feature: string; measured: number; nominal: number; deviation: number; status: string }) => [t.feature, t.measured, t.nominal, t.deviation, t.status])} />
              ) : <Empty>No tolerances defined for this product.</Empty>}
              <p className="lg:col-span-2 text-[11px] text-[#615d59]">Physical measurement accuracy has not been validated on this camera setup.</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
