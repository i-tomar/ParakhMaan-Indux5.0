'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { defectApi, imageSrc, openAuthenticatedFile, reviewApi } from '@/lib/api';
import { can } from '@/lib/auth';
import { useAuthUser } from '@/lib/useAuth';
import { DefectDetection, DefectInspection } from '@/lib/types';
import { defectColor, defectLabel, outcomeStyle } from '@/lib/defects';
import { formatDateTime } from '@/lib/formatters';
import DefectOverlay from '@/components/DefectOverlay';
import DefectTable from '@/components/DefectTable';
import AuditTimeline from '@/components/AuditTimeline';
import {
  ArrowLeft, Download, CheckCircle2, AlertTriangle, XCircle, FileText, RefreshCw,
  Upload, Gauge, Lightbulb, ShieldCheck, Film, Image as ImageIcon
} from 'lucide-react';

export default function DefectResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const user = useAuthUser();
  const router = useRouter();

  const [inspection, setInspection] = useState<DefectInspection | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeImageId, setActiveImageId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (keepSelection = false) => {
    if (!keepSelection) setLoading(true);
    try {
      const data = await defectApi.getInspection(id);
      setInspection(data);
      const analysed = (data.images || []).filter((i) => i.surface_type !== 'REFERENCE');
      if (!keepSelection || !analysed.some((i) => i.id === activeImageId)) {
        const firstWithDefects = analysed.find((img) =>
          (data.defect_detections || []).some((d) => d.image_id === img.id && d.reviewer_status !== 'REJECTED')
        );
        setActiveImageId((firstWithDefects || analysed[0])?.id || null);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  const analysedImages = useMemo(
    () => (inspection?.images || []).filter((i) => i.surface_type !== 'REFERENCE'),
    [inspection]
  );
  const referenceImage = (inspection?.images || []).find((i) => i.surface_type === 'REFERENCE');
  const detections = useMemo(() => inspection?.defect_detections || [], [inspection]);
  const activeImage = analysedImages.find((i) => i.id === activeImageId) || analysedImages[0];
  const activeDetections = detections.filter((d) => d.image_id === activeImage?.id);
  const scan = activeImage?.quality_metadata?.defect_scan;

  const typeSummary = useMemo(() => {
    const counts: Record<string, number> = {};
    detections
      .filter((d) => d.reviewer_status !== 'REJECTED')
      .forEach((d) => (counts[d.defect_type] = (counts[d.defect_type] || 0) + 1));
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [detections]);

  const handleSelect = (d: DefectDetection) => {
    setSelectedId(d.id || null);
    if (d.image_id && d.image_id !== activeImageId) setActiveImageId(d.image_id);
  };

  const handleFeedback = async (d: DefectDetection, action: 'CONFIRM' | 'REJECT' | 'RELABEL', defectType?: string) => {
    if (!d.id) return;
    await defectApi.submitFeedback(d.id, { action, defect_type: defectType });
    await load(true);
  };

  const handleAddImages = async (files: FileList | null) => {
    if (!files || !inspection) return;
    setUploading(true);
    setError(null);
    try {
      let lastImageId: string | null = null;
      for (const file of Array.from(files)) {
        const res = await defectApi.analyzeImage(inspection.id, file, 'SURFACE');
        lastImageId = res.image.id;
      }
      await load(true);
      if (lastImageId) setActiveImageId(lastImageId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleFinalize = async () => {
    if (!inspection) return;
    setFinalizing(true);
    try {
      await defectApi.finalizeInspection(inspection.id, {
        final_remarks: 'Defect inspection reviewed and signed off by quality inspector',
      });
      await load(true);
    } catch (err) {
      console.error(err);
    } finally {
      setFinalizing(false);
    }
  };

  if (loading && !inspection) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <RefreshCw className="w-8 h-8 text-[#0075de] animate-spin mb-3" />
        <p className="text-sm font-semibold text-[#000000]">Loading defect inspection…</p>
      </div>
    );
  }

  if (!inspection) {
    return (
      <div className="bg-white rounded-xl border border-[#e6e6e6] p-12 text-center">
        <AlertTriangle className="w-10 h-10 text-[#dd5b00] mx-auto mb-3" />
        <h2 className="text-sm font-bold text-[#000000]">Defect Inspection Not Found</h2>
        <Link href="/defects" className="text-xs text-[#0075de] underline mt-2 inline-block">
          Back to Defect Inspection
        </Link>
      </div>
    );
  }

  const outcome = inspection.overall_outcome || 'PENDING';
  const oc = outcomeStyle(outcome);

  return (
    <div className="space-y-6">
      {/* Top nav & actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <Link
          href="/defects"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#615d59] hover:text-[#000000] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Defect Inspection</span>
        </Link>
        <div className="flex items-center flex-wrap gap-2">
          {can(user, 'inspection:write') && inspection.status !== 'FINALIZED' && (
            <label className="cursor-pointer flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold bg-white text-[#0075de] border border-[#0075de]/30 hover:bg-[#f0f7ff] transition-all shadow-xs">
              {uploading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
              <span>{uploading ? 'Analysing…' : 'Analyse More Images'}</span>
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                disabled={uploading}
                onChange={(e) => handleAddImages(e.target.files)}
              />
            </label>
          )}
          <button
            type="button"
            onClick={() =>
              openAuthenticatedFile(defectApi.getReportUrl(inspection.id)).catch((err) =>
                setError(err instanceof Error ? err.message : 'Report download failed')
              )
            }
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold bg-white text-[#31302e] border border-[#e6e6e6] hover:bg-[#f6f5f4] transition-all shadow-xs"
          >
            <Download className="w-4 h-4 text-[#0075de]" />
            <span>Download Defect Report (PDF)</span>
          </button>
          {inspection.status !== 'FINALIZED' && can(user, 'inspection:finalize') && (
            <button
              onClick={handleFinalize}
              disabled={finalizing}
              className="flex items-center gap-1.5 px-5 py-2 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-xs disabled:opacity-50"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{finalizing ? 'Finalizing…' : 'Finalize & Sign Off'}</span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-[#991B1B]">{error}</div>
      )}

      {/* Outcome banner */}
      <div className={`rounded-xl p-5 border flex flex-col md:flex-row items-start md:items-center justify-between gap-4 ${oc.banner}`}>
        <div className="flex items-center gap-3.5">
          <div className="p-2.5 rounded-lg bg-white shadow-2xs">
            {outcome === 'PASS' && <CheckCircle2 className="w-6 h-6 text-[#1aae39]" />}
            {outcome === 'REVIEW' && <AlertTriangle className="w-6 h-6 text-[#dd5b00]" />}
            {outcome === 'DEFECTIVE' && <XCircle className="w-6 h-6 text-[#991B1B]" />}
            {outcome === 'PENDING' && <FileText className="w-6 h-6 text-gray-600" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-sm bg-white/70">{inspection.inspection_number}</span>
              <h2 className="font-bold text-sm tracking-tight">{oc.label}</h2>
            </div>
            <p className="text-xs opacity-90 mt-0.5">
              {inspection.product_name || 'Unnamed Product'}
              {(inspection.batch_code || inspection.brand_name) ? ` • Batch ${inspection.batch_code || inspection.brand_name}` : ''} • {inspection.category.replace(/_/g, ' ')}
              {(inspection.station_name || inspection.location) ? ` • ${inspection.station_name || inspection.location}` : ''}
              {inspection.shift ? ` • Shift ${inspection.shift}` : ''}
              {inspection.source === 'EDGE' ? ' • Edge device' : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div>
            <p className="text-[10px] opacity-75 uppercase font-semibold">Defects</p>
            <p className="font-bold">{typeSummary.reduce((s, [, n]) => s + n, 0)}</p>
          </div>
          <div className="border-l border-current/20 pl-4">
            <p className="text-[10px] opacity-75 uppercase font-semibold">Status</p>
            <p className="font-bold">{inspection.status}</p>
          </div>
          <div className="border-l border-current/20 pl-4">
            <p className="text-[10px] opacity-75 uppercase font-semibold">Inspected</p>
            <p className="font-mono">{formatDateTime(inspection.created_at)}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: visual evidence */}
        <div className="lg:col-span-7 space-y-3">
          {activeImage ? (
            <DefectOverlay
              imageUrl={imageSrc(activeImage)}
              detections={activeDetections}
              selectedId={selectedId}
              onSelect={handleSelect}
              caption={activeImage.original_filename}
            />
          ) : (
            <div className="bg-white rounded-xl border border-[#e6e6e6] p-12 text-center text-xs text-[#615d59]">
              No analysed images yet. Use &quot;Analyse More Images&quot; to add some.
            </div>
          )}

          {analysedImages.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {analysedImages.map((img) => {
                const n = detections.filter((d) => d.image_id === img.id && d.reviewer_status !== 'REJECTED').length;
                const isVideo = img.surface_type === 'VIDEO_FRAME';
                return (
                  <button
                    key={img.id}
                    type="button"
                    onClick={() => setActiveImageId(img.id)}
                    className={`relative shrink-0 w-24 rounded-lg overflow-hidden border-2 transition-all ${
                      img.id === activeImage?.id ? 'border-[#0075de]' : 'border-transparent opacity-80 hover:opacity-100'
                    }`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={imageSrc(img)} alt={img.original_filename} className="w-24 h-16 object-cover" />
                    <span className="absolute top-1 left-1 p-0.5 rounded bg-black/60 text-white">
                      {isVideo ? <Film className="w-3 h-3" /> : <ImageIcon className="w-3 h-3" />}
                    </span>
                    <span
                      className={`absolute bottom-1 right-1 px-1.5 rounded-full text-[9px] font-bold text-white ${
                        n ? 'bg-red-600' : 'bg-green-600'
                      }`}
                    >
                      {n}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: scan metrics, summary, root causes */}
        <div className="lg:col-span-5 space-y-4">
          {activeImage && (
            <div className="bg-white rounded-xl border border-[#e6e6e6] p-4 elevation-0 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-xs text-[#000000] uppercase tracking-wider">Training data</h3>
                {activeImage.review_status === 'VERIFIED' ? (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-[#166534]">
                    VERIFIED · {activeImage.dataset_split}
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-100 text-gray-600">UNREVIEWED</span>
                )}
              </div>
              <p className="text-[11px] text-[#615d59]">
                Verified images (every defect confirmed, corrected or drawn) become labels for the next model.
              </p>
              {can(user, 'review:write') && activeImage.review_status !== 'VERIFIED' && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await reviewApi.complete(activeImage.id, { accept_pending: true });
                        await load(true);
                      } catch (err) {
                        setError(err instanceof Error ? err.message : 'Verification failed');
                      }
                    }}
                    className="px-3 py-1.5 rounded-full font-bold bg-[#0075de] text-white hover:bg-[#005bab]"
                  >
                    Verify for training
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await reviewApi.request(activeImage.id);
                        setError(null);
                        router.push('/review');
                      } catch (err) {
                        setError(err instanceof Error ? err.message : 'Could not create review task');
                      }
                    }}
                    className="px-3 py-1.5 rounded-full font-semibold bg-white border border-[#e6e6e6]"
                  >
                    Send to review queue
                  </button>
                </div>
              )}
            </div>
          )}
          <div className="bg-white rounded-xl border border-[#e6e6e6] p-4 elevation-0">
            <h3 className="font-bold text-xs text-[#000000] uppercase tracking-wider mb-3 pb-2 border-b border-[#e6e6e6] flex items-center gap-1.5">
              <Gauge className="w-4 h-4 text-[#0075de]" />
              Scan Metrics (selected image)
            </h3>
            {scan ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ['Latency', scan.latency_ms !== undefined && scan.latency_ms !== null ? `${scan.latency_ms} ms` : '—'],
                  ['Throughput', scan.fps ? `${scan.fps} FPS` : '—'],
                  ['Engine', scan.backend || '—'],
                  ['Resolution', scan.image_size ? `${scan.image_size[0]}×${scan.image_size[1]}` : '—'],
                  ['Product segmented', scan.product_mask_used ? 'Yes' : 'No (full frame)'],
                  ['Golden reference', scan.reference_used ? 'Used' : 'Not used'],
                  ...(scan.frame_index !== undefined
                    ? [['Video frame', `#${scan.frame_index}${scan.timestamp_ms ? ` @ ${(scan.timestamp_ms / 1000).toFixed(1)}s` : ''}`]]
                    : []),
                  [
                    'Exposure',
                    scan.mean_brightness !== undefined
                      ? `${scan.exposure_ok ? 'OK' : 'Too dark / bright'} (${scan.mean_brightness})`
                      : '—',
                  ],
                ].map(([k, v]) => (
                  <div key={k} className="px-2.5 py-2 rounded-lg bg-[#f6f5f4] border border-[#e6e6e6]">
                    <p className="text-[10px] text-[#615d59] uppercase font-semibold">{k}</p>
                    <p className="font-bold text-[#000000] truncate">{v}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[#615d59]">No scan metadata for this image.</p>
            )}
            {activeImage?.quality_metadata?.issues && activeImage.quality_metadata.issues.length > 0 && (
              <ul className="mt-3 space-y-1 text-[11px] text-[#854D0E] list-disc pl-4">
                {activeImage.quality_metadata.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="bg-white rounded-xl border border-[#e6e6e6] p-4 elevation-0">
            <h3 className="font-bold text-xs text-[#000000] uppercase tracking-wider mb-3 pb-2 border-b border-[#e6e6e6]">
              Defect Categories
            </h3>
            {typeSummary.length === 0 ? (
              <p className="text-xs text-[#166534] font-semibold">No active defects on this product.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {typeSummary.map(([type, count]) => (
                  <span
                    key={type}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border"
                    style={{ borderColor: defectColor(type), color: defectColor(type) }}
                  >
                    <span className="w-2 h-2 rounded-full" style={{ background: defectColor(type) }} />
                    {defectLabel(type)} × {count}
                  </span>
                ))}
              </div>
            )}
          </div>

          {(inspection.root_causes || []).length > 0 && (
            <div className="bg-amber-50/60 rounded-xl border border-amber-200 p-4">
              <h3 className="font-bold text-xs text-[#854D0E] uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <Lightbulb className="w-4 h-4 text-[#dd5b00]" />
                Root-Cause Hints
              </h3>
              <div className="space-y-3">
                {(inspection.root_causes || []).map((rc) => (
                  <div key={rc.defect_type} className="text-xs">
                    <p className="font-bold text-[#000000]">{defectLabel(rc.defect_type)}</p>
                    <ul className="mt-1 space-y-0.5 text-[#713f12] list-disc pl-4">
                      {rc.likely_causes.slice(0, 2).map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                    <p className="mt-1 text-[11px] text-[#31302e]">→ {rc.recommended_actions[0]}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {referenceImage && (
            <div className="bg-white rounded-xl border border-[#e6e6e6] p-4 elevation-0 flex items-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageSrc(referenceImage)} alt="Golden reference" className="w-16 h-16 object-cover rounded-md border border-[#e6e6e6]" />
              <div>
                <p className="text-xs font-bold text-[#000000] flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-[#1aae39]" />
                  Golden Reference Sample
                </p>
                <p className="text-[11px] text-[#615d59]">{referenceImage.original_filename}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      <DefectTable
        detections={detections}
        selectedId={selectedId}
        onSelect={handleSelect}
        onFeedback={handleFeedback}
        readOnly={inspection.status === 'FINALIZED' || !can(user, 'review:write')}
        title="Defect Log & Inspector Feedback"
      />
      <p className="text-[11px] text-[#615d59] -mt-4">
        Confirmed, relabelled and rejected detections are saved as labelled samples for retraining the deep-learning model.
      </p>

      <AuditTimeline events={inspection.audit_events || []} />
    </div>
  );
}
