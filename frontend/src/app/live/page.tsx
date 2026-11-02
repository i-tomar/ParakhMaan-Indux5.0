'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Camera, Play, Square, Truck } from 'lucide-react';
import { getToken } from '@/lib/api';
import { LiveStats, liveApi, productionApi } from '@/lib/industrial';
import { Banner, Button, Card, DecisionBadge, Empty, Field, PageHeader, SimulatedBadge, Stat, Table, inputClass, useLoad } from '@/components/ui';

const FRAME_INTERVAL_MS = 66;

export default function LivePage() {
  const products = useLoad(() => productionApi.products());
  const lines = useLoad(() => productionApi.lines());
  const machines = useLoad(() => productionApi.machines());
  const batches = useLoad(() => productionApi.batches());
  const [productId, setProductId] = useState('');
  const [lineId, setLineId] = useState('');
  const [machineId, setMachineId] = useState('');
  const [batchId, setBatchId] = useState('');
  const [sampleFolder, setSampleFolder] = useState('demo_samples');
  const [stats, setStats] = useState<LiveStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const context = () => ({ product_id: productId || null, line_id: lineId || null, machine_id: machineId || null, batch_id: batchId || null });

  const cleanup = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);
    socketRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    socketRef.current = null;
    streamRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const poll = (id: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await liveApi.get(id);
        setStats(s);
        if (!s.running && pollRef.current) clearInterval(pollRef.current);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Lost the session');
      }
    }, 1000);
  };

  const startSimulation = async () => {
    setError(null);
    try {
      const s = await liveApi.start({ source_kind: 'CONVEYOR_SIM', source: sampleFolder, ...context() });
      setStats(s);
      poll(s.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the simulation');
    }
  };

  const startCamera = async () => {
    setError(null);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
      streamRef.current = media;
      if (videoRef.current) {
        videoRef.current.srcObject = media;
        await videoRef.current.play();
      }
      const s = await liveApi.start({ source_kind: 'BROWSER', ...context() });
      setStats(s);
      const socket = new WebSocket(liveApi.streamUrl(s.session_id, getToken() || ''));
      socketRef.current = socket;
      socket.onmessage = (m) => setStats((prev) => ({ ...(prev as LiveStats), ...JSON.parse(m.data) }));
      socket.onerror = () => setError('Live stream connection failed');
      const canvas = document.createElement('canvas');
      let waiting = false;
      socket.onopen = () => {
        timerRef.current = setInterval(() => {
          const video = videoRef.current;
          if (!video || socket.readyState !== WebSocket.OPEN || waiting || !video.videoWidth) return;
          canvas.width = 960;
          canvas.height = Math.round((960 * video.videoHeight) / video.videoWidth);
          canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
          waiting = true;
          canvas.toBlob((blob) => {
            waiting = false;
            if (blob && socket.readyState === WebSocket.OPEN) socket.send(blob);
          }, 'image/jpeg', 0.8);
        }, FRAME_INTERVAL_MS);
      };
    } catch (e) {
      cleanup();
      setError(e instanceof Error ? e.message : 'Camera could not be started');
    }
  };

  const stop = async () => {
    const id = stats?.session_id;
    cleanup();
    if (id) setStats(await liveApi.stop(id));
  };

  const running = !!stats?.running;

  return (
    <div>
      <PageHeader title="Live Inspection" subtitle="Continuous mode: every received frame goes through the unit tracker, and each physical unit gets one AI decision." />
      <div className="grid lg:grid-cols-[320px_1fr] gap-4">
        <div className="space-y-4">
          <Card title="Line context">
            <div className="space-y-3">
              <Field label="Product">
                <select className={inputClass} value={productId} onChange={(e) => setProductId(e.target.value)}>
                  <option value="">Identify automatically</option>
                  {(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Line">
                <select className={inputClass} value={lineId} onChange={(e) => setLineId(e.target.value)}>
                  <option value="">Not set</option>
                  {(lines.data || []).map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
                </select>
              </Field>
              <Field label="Machine">
                <select className={inputClass} value={machineId} onChange={(e) => setMachineId(e.target.value)}>
                  <option value="">Not set</option>
                  {(machines.data || []).map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}
                </select>
              </Field>
              <Field label="Batch">
                <select className={inputClass} value={batchId} onChange={(e) => setBatchId(e.target.value)}>
                  <option value="">Not set</option>
                  {(batches.data || []).filter((b) => b.status === 'OPEN').map((b) => <option key={b.id} value={b.id}>{b.code}</option>)}
                </select>
              </Field>
            </div>
          </Card>
          <Card title="Source">
            <div className="space-y-3">
              <Button variant="primary" disabled={running} onClick={startCamera} className="w-full justify-center"><Camera className="w-3.5 h-3.5" />Start camera</Button>
              <Field label="Conveyor simulation sample folder (inside storage)">
                <input className={inputClass} value={sampleFolder} onChange={(e) => setSampleFolder(e.target.value)} />
              </Field>
              <Button disabled={running} onClick={startSimulation} className="w-full justify-center"><Truck className="w-3.5 h-3.5" />Run conveyor simulation</Button>
              <Button variant="danger" disabled={!running} onClick={stop} className="w-full justify-center"><Square className="w-3.5 h-3.5" />Stop</Button>
              <p className="text-[11px] text-[#615d59]">The simulation moves real part photographs across a rendered belt. It tests tracking and timing, not optics or hardware.</p>
            </div>
          </Card>
        </div>

        <div className="space-y-4 min-w-0">
          {error && <Banner tone="error">{error}</Banner>}
          {stats?.errors?.map((e) => <Banner key={e} tone="error">{e}</Banner>)}
          <div className={`bg-[#1b1b1b] rounded-xl overflow-hidden ${stats?.source === 'BROWSER' ? '' : 'hidden'}`}>
            <video ref={videoRef} muted playsInline className="w-full max-h-[380px] object-contain" />
          </div>
          {stats ? (
            <>
              <div className="flex items-center gap-2 text-xs text-[#615d59]">
                <Play className="w-3.5 h-3.5" /> {stats.running ? 'Running' : 'Finished'} · {stats.source} · reject output {stats.actuator}
                {stats.simulation && <SimulatedBadge />}
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Stat label="Tracking rate" value={`${stats.tracking_fps} fps`} hint={`ingest ${stats.ingest_fps} fps`} />
                <Stat label="Frames dropped" value={stats.frames_dropped} hint={`${stats.frames_tracked} of ${stats.frames_received} tracked`} />
                <Stat label="Inference p95" value={stats.inspect_ms_p95 !== null ? `${stats.inspect_ms_p95} ms` : '—'} hint={stats.inspect_ms_p50 !== null ? `p50 ${stats.inspect_ms_p50} ms` : undefined} />
                <Stat label="Units decided" value={`${stats.units_inspected}/${stats.units_seen}`} hint={`${stats.throughput_units_min} units/min`} />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Stat label="Accepted" value={stats.decisions.ACCEPT || 0} />
                <Stat label="Rejected" value={stats.decisions.REJECT || 0} />
                <Stat label="Manual review" value={stats.decisions.MANUAL_REVIEW || 0} />
              </div>
              <Card title="Decisions">
                {stats.recent.length ? (
                  <Table columns={['Unit', 'Decision', 'Defects', 'Inference', 'Reject signal']} rows={stats.recent.map((r) => [
                    <Link key={r.unit_id} className="text-[#0075de] font-medium" href={`/units/${r.unit_id}`}>{r.unit_code}</Link>,
                    <DecisionBadge key="d" decision={r.decision} />,
                    r.defects.map((d) => d.type).join(', ') || 'None',
                    `${r.latency_ms} ms`, r.reject || '—',
                  ])} />
                ) : <Empty>Waiting for the first unit to reach the trigger line.</Empty>}
              </Card>
            </>
          ) : <Card><Empty>Choose a source to begin.</Empty></Card>}
        </div>
      </div>
    </div>
  );
}
