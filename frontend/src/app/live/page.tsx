'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Camera, Play, RefreshCw, ScanSearch, Sparkles, Square, Truck, Video } from 'lucide-react';
import { defectApi, getToken } from '@/lib/api';
import { LiveFrameResult } from '@/lib/types';
import { DefectBoxes } from '@/components/DefectOverlay';
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

  // Camera device selection
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [isObsCamera, setIsObsCamera] = useState<boolean>(false);

  // Live Frame AI Analysis (Stationary & Real-time Inspection)
  const [liveAIOverlay, setLiveAIOverlay] = useState<boolean>(false);
  const [liveAIResult, setLiveAIResult] = useState<LiveFrameResult | null>(null);
  const [liveAILoading, setLiveAILoading] = useState<boolean>(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const context = () => ({ product_id: productId || null, line_id: lineId || null, machine_id: machineId || null, batch_id: batchId || null });

  // Enumerate camera devices and intelligently select physical webcam over virtual drivers
  const refreshDevices = useCallback(async () => {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) return;
      const all = await navigator.mediaDevices.enumerateDevices();
      const cams = all.filter((d) => d.kind === 'videoinput');
      setVideoDevices(cams);

      if (cams.length > 0) {
        setSelectedDeviceId((current) => {
          if (current && cams.some((c) => c.deviceId === current)) return current;
          // Priority: Pick a physical camera (skip virtual, OBS, screen drivers)
          const physical = cams.find((c) => {
            const label = (c.label || '').toLowerCase();
            return !label.includes('obs') && !label.includes('virtual') && !label.includes('screen') && !label.includes('camo') && !label.includes('droid');
          });
          return (physical || cams[0]).deviceId;
        });
      }
    } catch (e) {
      console.warn('Could not list video devices:', e);
    }
  }, []);

  useEffect(() => {
    refreshDevices();
    if (navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', refreshDevices);
      return () => navigator.mediaDevices.removeEventListener('devicechange', refreshDevices);
    }
  }, [refreshDevices]);

  // Check if currently selected device is OBS
  useEffect(() => {
    const active = videoDevices.find((d) => d.deviceId === selectedDeviceId);
    const label = (active?.label || '').toLowerCase();
    setIsObsCamera(label.includes('obs') || label.includes('virtual'));
  }, [selectedDeviceId, videoDevices]);

  const cleanup = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);
    socketRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    socketRef.current = null;
    streamRef.current = null;
    setLiveAIResult(null);
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

  const getMediaStream = async (deviceId?: string) => {
    const id = deviceId || selectedDeviceId;
    const constraints: MediaStreamConstraints = {
      video: id
        ? { deviceId: { exact: id }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    };
    return navigator.mediaDevices.getUserMedia(constraints);
  };

  const startCamera = async () => {
    setError(null);
    try {
      const media = await getMediaStream();
      streamRef.current = media;
      if (videoRef.current) {
        videoRef.current.srcObject = media;
        await videoRef.current.play();
      }

      // Re-enumerate devices so labels populate now that camera permission is granted
      await refreshDevices();

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

  // Switch camera dynamically without restarting the whole session
  const switchCamera = async (newDeviceId: string) => {
    setSelectedDeviceId(newDeviceId);
    if (!streamRef.current) return;
    try {
      const newStream = await getMediaStream(newDeviceId);
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = newStream;
      if (videoRef.current) {
        videoRef.current.srcObject = newStream;
        await videoRef.current.play();
      }
      await refreshDevices();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to switch camera device');
    }
  };

  // Inspect the current frame immediately
  const inspectCurrentFrame = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError('Camera video feed is not active yet');
      return;
    }
    setLiveAILoading(true);
    try {
      const snapCanvas = document.createElement('canvas');
      const maxSide = 960;
      const scale = Math.min(1, maxSide / Math.max(video.videoWidth, video.videoHeight));
      snapCanvas.width = Math.round(video.videoWidth * scale);
      snapCanvas.height = Math.round(video.videoHeight * scale);
      const ctx = snapCanvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, snapCanvas.width, snapCanvas.height);
        const dataUrl = snapCanvas.toDataURL('image/jpeg', 0.85);
        const result = await defectApi.analyzeLiveFrame(dataUrl, { maxSide: 960 });
        setLiveAIResult(result);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Frame inspection failed');
    } finally {
      setLiveAILoading(false);
    }
  };

  // Continuous Live AI Overlay Loop (when enabled)
  useEffect(() => {
    if (!liveAIOverlay || !stats?.running || stats?.source !== 'BROWSER') {
      return;
    }
    let cancelled = false;
    const runLoop = async () => {
      while (!cancelled && liveAIOverlay) {
        const video = videoRef.current;
        if (video && video.readyState >= 2 && video.videoWidth) {
          try {
            const snapCanvas = document.createElement('canvas');
            const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
            snapCanvas.width = Math.round(video.videoWidth * scale);
            snapCanvas.height = Math.round(video.videoHeight * scale);
            const ctx = snapCanvas.getContext('2d');
            if (ctx) {
              ctx.drawImage(video, 0, 0, snapCanvas.width, snapCanvas.height);
              const dataUrl = snapCanvas.toDataURL('image/jpeg', 0.75);
              const res = await defectApi.analyzeLiveFrame(dataUrl, { maxSide: 640 });
              if (!cancelled) setLiveAIResult(res);
            }
          } catch {}
        }
        await new Promise((r) => setTimeout(r, 450));
      }
    };
    runLoop();
    return () => {
      cancelled = true;
    };
  }, [liveAIOverlay, stats?.running, stats?.source]);

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

          <Card title="Camera & Ingestion Source">
            <div className="space-y-3">
              {/* Camera Device Dropdown */}
              <Field label="Camera Device">
                <div className="flex gap-2">
                  <select
                    className={`${inputClass} flex-1`}
                    value={selectedDeviceId}
                    onChange={(e) => switchCamera(e.target.value)}
                  >
                    {videoDevices.length ? (
                      videoDevices.map((d, i) => (
                        <option key={d.deviceId || i} value={d.deviceId}>
                          {d.label || `Camera ${i + 1}`}
                        </option>
                      ))
                    ) : (
                      <option value="">Default System Camera</option>
                    )}
                  </select>
                  <Button variant="secondary" onClick={refreshDevices} title="Refresh camera devices" className="px-2.5">
                    <RefreshCw className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </Field>

              {isObsCamera && (
                <Banner tone="warn">
                  <strong>OBS Virtual Camera detected.</strong> If you see a crossed-out camera logo, select your laptop/USB camera from the dropdown above, or click "Start Virtual Camera" inside OBS Studio.
                </Banner>
              )}

              <Button variant="primary" disabled={running} onClick={startCamera} className="w-full justify-center">
                <Camera className="w-3.5 h-3.5" />
                Start camera
              </Button>

              {/* Instant Frame Inspection Controls */}
              {running && stats?.source === 'BROWSER' && (
                <div className="pt-2 border-t border-[#e6e6e6] space-y-2">
                  <Button
                    variant="secondary"
                    disabled={liveAILoading}
                    onClick={inspectCurrentFrame}
                    className="w-full justify-center border-sky-300 text-sky-800 hover:bg-sky-50"
                  >
                    <ScanSearch className="w-3.5 h-3.5 text-sky-600" />
                    {liveAILoading ? 'Analyzing frame...' : 'Inspect current frame'}
                  </Button>

                  <label className="flex items-center gap-2 text-xs text-[#31302e] cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      checked={liveAIOverlay}
                      onChange={(e) => setLiveAIOverlay(e.target.checked)}
                      className="rounded border-[#e6e6e6] text-[#0075de] focus:ring-0"
                    />
                    <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                    <span>Continuous live AI defect overlay</span>
                  </label>
                </div>
              )}

              <Field label="Conveyor simulation sample folder (inside storage)">
                <input className={inputClass} value={sampleFolder} onChange={(e) => setSampleFolder(e.target.value)} />
              </Field>
              <Button disabled={running} onClick={startSimulation} className="w-full justify-center">
                <Truck className="w-3.5 h-3.5" />
                Run conveyor simulation
              </Button>
              <Button variant="danger" disabled={!running} onClick={stop} className="w-full justify-center">
                <Square className="w-3.5 h-3.5" />
                Stop
              </Button>
              <p className="text-[11px] text-[#615d59]">The simulation moves real part photographs across a rendered belt. It tests tracking and timing, not optics or hardware.</p>
            </div>
          </Card>
        </div>

        <div className="space-y-4 min-w-0">
          {error && <Banner tone="error">{error}</Banner>}
          {stats?.errors?.map((e) => <Banner key={e} tone="error">{e}</Banner>)}

          {/* Live Video Preview with Overlays */}
          <div className={`relative bg-[#1b1b1b] rounded-xl overflow-hidden ${stats?.source === 'BROWSER' ? '' : 'hidden'}`}>
            <video ref={videoRef} muted playsInline className="w-full max-h-[420px] object-contain block mx-auto" />

            {/* Conveyor Trigger Line Guide */}
            <div className="absolute inset-y-0 left-[55%] pointer-events-none border-r-2 border-dashed border-sky-400/90 z-10 flex flex-col justify-start">
              <span className="bg-sky-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-br shadow">
                Trigger Line (55%)
              </span>
            </div>

            {/* Live AI Overlay Bounding Boxes */}
            {liveAIResult && liveAIResult.detections && liveAIResult.detections.length > 0 && videoRef.current && (
              <DefectBoxes
                width={videoRef.current.videoWidth || 960}
                height={videoRef.current.videoHeight || 540}
                detections={liveAIResult.detections}
                showLabels={true}
              />
            )}
          </div>

          {/* Instant Frame Inspection Result Banner */}
          {liveAIResult && (
            <Card title="Instant Frame AI Result" subtitle={`Latency: ${liveAIResult.latency_ms} ms`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-[#615d59]">Outcome:</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                    liveAIResult.outcome === 'PASS' ? 'bg-green-100 text-green-800' :
                    liveAIResult.outcome === 'DEFECTIVE' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800'
                  }`}>
                    {liveAIResult.outcome}
                  </span>
                  <span className="text-xs text-[#615d59]">({liveAIResult.detections.length} defect(s) detected)</span>
                </div>
                {liveAIResult.detections.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {liveAIResult.detections.map((d, i) => (
                      <span key={i} className="text-[11px] px-2 py-0.5 rounded bg-gray-100 font-medium">
                        {d.defect_type} ({Math.round(d.confidence * 100)}%)
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          )}

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
