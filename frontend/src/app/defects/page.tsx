'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { defectApi } from '@/lib/api';
import { DefectDetectorStatus, DefectInspection } from '@/lib/types';
import { defectColor, defectLabel, outcomeStyle } from '@/lib/defects';
import { formatDate } from '@/lib/formatters';
import CameraCaptureModal from '@/components/CameraCaptureModal';
import {
  Upload, Camera, Video, Trash2, AlertCircle, FileText, ScanSearch, ArrowRight,
  RefreshCw, Layers, BarChart3, ShieldCheck, ChevronRight, Cpu, ImagePlus
} from 'lucide-react';

type SourceTab = 'IMAGES' | 'CAMERA' | 'VIDEO';

interface QueuedImage {
  key: string;
  previewUrl: string;
  file?: File;
  base64Data?: string;
  label: string;
}

const PRODUCT_LINES = [
  ['METAL_SHEET', 'Metal Sheet / Coil'],
  ['DIE_CASTING', 'Die Casting'],
  ['MACHINED_PART', 'Machined Part'],
  ['PLASTIC_MOULDING', 'Plastic Moulding'],
  ['CERAMIC_TILE', 'Ceramic / Tile'],
  ['GLASS', 'Glass / Panel'],
  ['PCB_ELECTRONICS', 'PCB / Electronics'],
  ['TEXTILE', 'Textile / Fabric'],
  ['GENERAL_MANUFACTURED', 'General Manufactured Product'],
];

export default function DefectInspectionPage() {
  const router = useRouter();

  const [productName, setProductName] = useState('');
  const [batch, setBatch] = useState('');
  const [category, setCategory] = useState('METAL_SHEET');
  const [station, setStation] = useState('Line 1 · Final QC');

  const [tab, setTab] = useState<SourceTab>('IMAGES');
  const [queue, setQueue] = useState<QueuedImage[]>([]);
  const [video, setVideo] = useState<File | null>(null);
  const [sampleFps, setSampleFps] = useState(2);
  const [maxFrames, setMaxFrames] = useState(40);
  const [reference, setReference] = useState<File | null>(null);
  const referenceUrl = useMemo(() => (reference ? URL.createObjectURL(reference) : null), [reference]);
  const [cameraOpen, setCameraOpen] = useState(false);

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState<string | null>(null);

  const [recent, setRecent] = useState<DefectInspection[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [status, setStatus] = useState<DefectDetectorStatus | null>(null);
  const [seeding, setSeeding] = useState(false);

  const loadRecent = async () => {
    setLoadingRecent(true);
    try {
      setRecent(await defectApi.listInspections());
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingRecent(false);
    }
  };

  useEffect(() => {
    loadRecent();
    defectApi.getStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const handleSeed = async () => {
    setSeeding(true);
    try {
      await defectApi.seedDemoData();
      await loadRecent();
    } catch (e) {
      console.error(e);
    } finally {
      setSeeding(false);
    }
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const items = Array.from(files).map((file) => ({
      key: `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 7)}`,
      previewUrl: URL.createObjectURL(file),
      file,
      label: file.name,
    }));
    setQueue((prev) => [...prev, ...items].slice(0, 12));
  };

  const handleCameraCapture = async (base64Data: string, surfaceType: string) => {
    setQueue((prev) => [
      ...prev,
      {
        key: `cam-${Date.now()}`,
        previewUrl: base64Data,
        base64Data,
        label: `Camera · ${surfaceType}`,
      },
    ]);
  };

  const canRun = queue.length > 0 || !!video;

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canRun) {
      setError('Add at least one image, camera snapshot, or video to analyse.');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      setProgress('Creating inspection…');
      const insp = await defectApi.createInspection({
        product_name: productName || 'Unnamed Product',
        brand_name: batch || undefined,
        category,
        location: station,
      });

      if (reference) {
        setProgress('Uploading golden reference sample…');
        await defectApi.uploadReference(insp.id, reference);
      }

      for (let i = 0; i < queue.length; i++) {
        const item = queue[i];
        setProgress(`Analysing image ${i + 1} of ${queue.length}…`);
        if (item.base64Data) {
          await defectApi.analyzeCapture(insp.id, item.base64Data, 'CAMERA');
        } else if (item.file) {
          await defectApi.analyzeImage(insp.id, item.file, 'SURFACE');
        }
      }

      if (video) {
        setProgress(`Sampling video at ${sampleFps} fps (up to ${maxFrames} frames)…`);
        await defectApi.analyzeVideo(insp.id, video, { sampleFps, maxFrames });
      }

      router.push(`/defects/${insp.id}`);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : 'Defect analysis failed.');
      setRunning(false);
      setProgress('');
    }
  };

  const tabs: Array<{ id: SourceTab; label: string; icon: React.ElementType }> = [
    { id: 'IMAGES', label: 'Images', icon: ImagePlus },
    { id: 'CAMERA', label: 'Live Camera', icon: Camera },
    { id: 'VIDEO', label: 'Video', icon: Video },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-[#000000]">Product Defect Inspection</h1>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-[#6b21a8] border border-purple-200">
              AI &amp; Computer Vision
            </span>
          </div>
          <p className="text-xs text-[#615d59] mt-0.5">
            Detect scratches, cracks, dents, discolouration and dimensional anomalies from images, live camera, or video
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 whitespace-nowrap">
          <button
            type="button"
            onClick={handleSeed}
            disabled={seeding}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold bg-white text-[#31302e] border border-[#e6e6e6] hover:bg-[#f6f5f4] transition-all shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 text-[#0075de] ${seeding ? 'animate-spin' : ''}`} />
            <span>{seeding ? 'Loading…' : 'Load Demo Samples'}</span>
          </button>
          <Link
            href="/defects/analytics"
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold bg-[#213183] text-white hover:bg-[#1a2768] transition-all shadow-xs"
          >
            <BarChart3 className="w-4 h-4" />
            <span>Defect Analytics</span>
          </Link>
        </div>
      </div>

      {/* Detector status */}
      {status && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-[#31302e]">
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white border border-[#e6e6e6]">
            <Cpu className="w-3.5 h-3.5 text-[#0075de]" />
            Engine: <b className="uppercase">{status.backend}</b>
          </span>
          <span className="px-2.5 py-1 rounded-full bg-white border border-[#e6e6e6]">OpenCV {status.opencv_version}</span>
          <span
            className={`px-2.5 py-1 rounded-full border ${
              status.model_loaded ? 'bg-green-50 border-green-200 text-[#166534]' : 'bg-[#f6f5f4] border-[#e6e6e6] text-[#615d59]'
            }`}
            title={status.model_error || status.model_path || 'Set DEFECT_MODEL_PATH to plug in a YOLOv8 ONNX model'}
          >
            {status.model_loaded
              ? `YOLOv8 ONNX model loaded · ${status.model_classes.join(', ')}${status.model_input_size ? ` · ${status.model_input_size}px` : ''}`
              : status.model_error
              ? `Deep-learning model error: ${status.model_error}`
              : 'Deep-learning model: not configured (classical CV active)'}
          </span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-center gap-3 text-xs text-[#991B1B]">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleRun} className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 space-y-6">
          {/* Step 1: product metadata */}
          <div className="bg-white rounded-xl border border-[#e6e6e6] p-5 elevation-0 space-y-4">
            <div className="flex items-center gap-2 pb-3 border-b border-[#e6e6e6]">
              <FileText className="w-4 h-4 text-[#0075de]" />
              <h2 className="font-bold text-xs text-[#000000] uppercase tracking-wider">1. Product &amp; Batch</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div>
                <label className="block font-semibold text-[#31302e] mb-1">Product / Part Name</label>
                <input
                  type="text"
                  placeholder="e.g. Cold-Rolled Steel Panel"
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  className="w-full px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4]"
                />
              </div>
              <div>
                <label className="block font-semibold text-[#31302e] mb-1">Batch / Lot</label>
                <input
                  type="text"
                  placeholder="e.g. LOT-A17"
                  value={batch}
                  onChange={(e) => setBatch(e.target.value)}
                  className="w-full px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4]"
                />
              </div>
              <div>
                <label className="block font-semibold text-[#31302e] mb-1">Product Line</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4]"
                >
                  {PRODUCT_LINES.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-semibold text-[#31302e] mb-1">Production Line / Station</label>
                <input
                  type="text"
                  value={station}
                  onChange={(e) => setStation(e.target.value)}
                  className="w-full px-3 py-2 border border-[#e6e6e6] rounded-md focus:outline-none focus:border-[#0075de] bg-[#f6f5f4]"
                />
              </div>
            </div>
          </div>

          {/* Step 2: input source */}
          <div className="bg-white rounded-xl border border-[#e6e6e6] p-5 elevation-0 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#e6e6e6]">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-[#0075de]" />
                <h2 className="font-bold text-xs text-[#000000] uppercase tracking-wider">2. Capture Source</h2>
              </div>
              <span className="text-[11px] text-[#615d59]">
                {queue.length} image{queue.length !== 1 ? 's' : ''}{video ? ' + 1 video' : ''} queued
              </span>
            </div>

            <div className="flex items-center gap-1.5">
              {tabs.map((t) => {
                const Icon = t.icon;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTab(t.id)}
                    className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
                      tab === t.id
                        ? 'bg-[#0075de] text-white shadow-xs'
                        : 'bg-[#f6f5f4] text-[#31302e] border border-[#e6e6e6] hover:bg-[#e6e6e6]'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {t.label}
                  </button>
                );
              })}
            </div>

            {tab === 'IMAGES' && (
              <label className="block cursor-pointer border-2 border-dashed border-[#e6e6e6] rounded-xl p-6 text-center bg-[#f6f5f4]/50 hover:bg-[#f6f5f4] transition-colors">
                <Upload className="w-6 h-6 text-[#0075de] mx-auto mb-2" />
                <p className="text-xs font-bold text-[#000000]">Upload product surface images</p>
                <p className="text-[11px] text-[#615d59] mt-0.5">
                  Multiple files allowed · even, diffuse lighting · surface filling most of the frame
                </p>
                <input type="file" accept="image/*" multiple className="hidden" onChange={(e) => addFiles(e.target.files)} />
              </label>
            )}

            {tab === 'CAMERA' && (
              <div className="border-2 border-dashed border-[#e6e6e6] rounded-xl p-6 text-center bg-[#f6f5f4]/50 space-y-3">
                <Camera className="w-6 h-6 text-[#0075de] mx-auto" />
                <div>
                  <p className="text-xs font-bold text-[#000000]">Real-time inspection from webcam or phone camera</p>
                  <p className="text-[11px] text-[#615d59] mt-0.5">
                    Live bounding boxes, FPS and latency are shown on the preview; snapshot any frame to add it to this inspection
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setCameraOpen(true)}
                  className="px-4 py-2 bg-[#0075de] text-white rounded-full text-xs font-bold hover:bg-[#005bab] transition-all shadow-xs inline-flex items-center gap-1.5"
                >
                  <ScanSearch className="w-3.5 h-3.5" />
                  Open Live Detection
                </button>
              </div>
            )}

            {tab === 'VIDEO' && (
              <div className="border-2 border-dashed border-[#e6e6e6] rounded-xl p-6 bg-[#f6f5f4]/50 space-y-3">
                <label className="block cursor-pointer text-center">
                  <Video className="w-6 h-6 text-[#0075de] mx-auto mb-2" />
                  <p className="text-xs font-bold text-[#000000]">{video ? video.name : 'Upload a production-line video'}</p>
                  <p className="text-[11px] text-[#615d59] mt-0.5">
                    MP4 / AVI / MOV · frames are sampled and analysed; frames with defects are kept as evidence
                  </p>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => setVideo(e.target.files?.[0] || null)}
                  />
                </label>
                <div className="flex flex-wrap items-center justify-center gap-4 text-xs">
                  <label className="flex items-center gap-2">
                    <span className="font-semibold text-[#31302e]">Sample rate</span>
                    <select
                      value={sampleFps}
                      onChange={(e) => setSampleFps(Number(e.target.value))}
                      className="px-2 py-1 border border-[#e6e6e6] rounded-md bg-white"
                    >
                      {[1, 2, 5, 10].map((v) => (
                        <option key={v} value={v}>{v} fps</option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center gap-2">
                    <span className="font-semibold text-[#31302e]">Max frames</span>
                    <select
                      value={maxFrames}
                      onChange={(e) => setMaxFrames(Number(e.target.value))}
                      className="px-2 py-1 border border-[#e6e6e6] rounded-md bg-white"
                    >
                      {[20, 40, 80, 120].map((v) => (
                        <option key={v} value={v}>{v}</option>
                      ))}
                    </select>
                  </label>
                  {video && (
                    <button type="button" onClick={() => setVideo(null)} className="text-[#991B1B] font-semibold underline">
                      Remove video
                    </button>
                  )}
                </div>
              </div>
            )}

            {queue.length > 0 && (
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
                {queue.map((q) => (
                  <div key={q.key} className="relative group rounded-lg overflow-hidden border border-[#e6e6e6] bg-[#f6f5f4]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={q.previewUrl} alt={q.label} className="w-full h-20 object-cover" />
                    <p className="text-[9px] text-[#615d59] px-1 py-0.5 truncate">{q.label}</p>
                    <button
                      type="button"
                      onClick={() => setQueue((prev) => prev.filter((p) => p.key !== q.key))}
                      className="absolute top-1 right-1 p-1 bg-red-600 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Remove"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right column: golden reference + run */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-white rounded-xl border border-[#e6e6e6] p-5 elevation-0 space-y-3">
            <div className="flex items-center gap-2 pb-3 border-b border-[#e6e6e6]">
              <ShieldCheck className="w-4 h-4 text-[#1aae39]" />
              <h2 className="font-bold text-xs text-[#000000] uppercase tracking-wider">3. Golden Reference (optional)</h2>
            </div>
            <p className="text-[11px] text-[#615d59] leading-relaxed">
              A defect-free sample of the same product, photographed with the same setup. Enables dimensional comparison,
              exact colour matching, and suppresses printed designs or logos that are not defects.
            </p>
            {reference ? (
              <div className="flex items-center gap-3 p-2 rounded-lg bg-green-50 border border-green-200">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={referenceUrl || ''} alt="Reference" className="w-14 h-14 object-cover rounded-md" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-[#166534] truncate">{reference.name}</p>
                  <button type="button" onClick={() => setReference(null)} className="text-[11px] text-[#991B1B] underline">
                    Remove
                  </button>
                </div>
              </div>
            ) : (
              <label className="cursor-pointer px-4 py-2 bg-white text-[#31302e] border border-[#e6e6e6] rounded-full text-xs font-semibold hover:bg-[#f6f5f4] transition-all shadow-xs inline-flex items-center gap-1.5">
                <Upload className="w-3.5 h-3.5 text-[#1aae39]" />
                Upload Golden Sample
                <input type="file" accept="image/*" className="hidden" onChange={(e) => setReference(e.target.files?.[0] || null)} />
              </label>
            )}
          </div>

          <button
            type="submit"
            disabled={running || !canRun}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-md active:scale-95 disabled:opacity-50"
          >
            {running ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>{progress || 'Running defect detection…'}</span>
              </>
            ) : (
              <>
                <ScanSearch className="w-4 h-4" />
                <span>Run Defect Detection</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </form>

      {/* Recent defect inspections */}
      <div className="bg-white rounded-xl border border-[#e6e6e6] overflow-hidden elevation-0">
        <div className="p-4 border-b border-[#e6e6e6] bg-[#f6f5f4] flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-[#000000]">Recent Defect Inspections</h3>
            <p className="text-xs text-[#615d59]">Every analysed product with its logged and categorised defects</p>
          </div>
          <button type="button" onClick={loadRecent} className="text-xs font-semibold text-[#0075de] hover:underline">
            Refresh
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[#f6f5f4] border-b border-[#e6e6e6] text-[11px] font-bold text-[#615d59] uppercase tracking-wider">
                <th className="py-3 px-4">Inspection #</th>
                <th className="py-3 px-4">Product</th>
                <th className="py-3 px-4">Batch</th>
                <th className="py-3 px-4">Defects</th>
                <th className="py-3 px-4">Top Defect</th>
                <th className="py-3 px-4">Outcome</th>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e6e6e6] text-xs">
              {loadingRecent ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-[#615d59]">Loading…</td>
                </tr>
              ) : recent.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-[#615d59]">
                    No defect inspections yet. Run one above or click &quot;Load Demo Samples&quot;.
                  </td>
                </tr>
              ) : (
                recent.map((insp) => {
                  const oc = outcomeStyle(insp.overall_outcome);
                  return (
                    <tr key={insp.id} className="hover:bg-[#f6f5f4]/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-bold text-[#213183]">{insp.inspection_number}</td>
                      <td className="py-3 px-4 font-semibold text-[#000000]">{insp.product_name || 'Unnamed Product'}</td>
                      <td className="py-3 px-4 text-[#615d59]">{insp.brand_name || '—'}</td>
                      <td className="py-3 px-4 font-bold text-[#000000]">{insp.defect_count ?? 0}</td>
                      <td className="py-3 px-4">
                        {insp.top_defect_type ? (
                          <span className="flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full" style={{ background: defectColor(insp.top_defect_type) }} />
                            {defectLabel(insp.top_defect_type)}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${oc.badge}`}>{insp.overall_outcome}</span>
                      </td>
                      <td className="py-3 px-4 text-[#615d59]">{formatDate(insp.created_at)}</td>
                      <td className="py-3 px-4 text-right">
                        <Link
                          href={`/defects/${insp.id}`}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#0075de] hover:underline"
                        >
                          View Results
                          <ChevronRight className="w-3.5 h-3.5" />
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <CameraCaptureModal
        isOpen={cameraOpen}
        onClose={() => setCameraOpen(false)}
        onCapture={handleCameraCapture}
        defaultSurface="SURFACE"
        title="Live Defect Detection"
        surfaceOptions={['SURFACE', 'TOP', 'SIDE', 'EDGE']}
        frameHint={{ label: 'INSPECTION ZONE', hint: 'Keep the surface evenly lit and inside the frame' }}
        liveAnalyze={(b64) => defectApi.analyzeLiveFrame(b64, { maxSide: 640 })}
      />
    </div>
  );
}
