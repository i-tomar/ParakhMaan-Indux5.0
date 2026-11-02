'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ClipboardCheck, PenSquare, CheckCircle2, SkipForward, RefreshCw, AlertCircle, ExternalLink, Inbox, Database
} from 'lucide-react';
import { defectApi, getStorageUrl, reviewApi } from '@/lib/api';
import { can } from '@/lib/auth';
import { useAuthUser } from '@/lib/useAuth';
import { DEFECT_TYPES, defectColor, defectLabel } from '@/lib/defects';
import { formatDateTime } from '@/lib/formatters';
import { DefectDetection, ReviewStats, ReviewTask, ReviewTaskDetail } from '@/lib/types';
import AnnotatableImage from '@/components/AnnotatableImage';
import DefectTable from '@/components/DefectTable';

const REASON_STYLES: Record<string, string> = {
  UNCERTAIN: 'bg-amber-100 text-[#854D0E]',
  DISAGREEMENT: 'bg-purple-100 text-[#6b21a8]',
  UNKNOWN_CLASS: 'bg-pink-100 text-[#9d174d]',
  QUALITY: 'bg-gray-100 text-gray-700',
  DRIFT: 'bg-red-100 text-[#991B1B]',
  AUDIT: 'bg-blue-100 text-[#0075de]',
  MANUAL: 'bg-teal-100 text-[#115e59]',
};

const REASON_LABELS: Record<string, string> = {
  UNCERTAIN: 'Uncertain',
  DISAGREEMENT: 'Engines disagree',
  UNKNOWN_CLASS: 'Unknown class',
  QUALITY: 'Image quality',
  DRIFT: 'Station drift',
  AUDIT: 'Random audit',
  MANUAL: 'Requested',
};

export default function ReviewQueuePage() {
  const user = useAuthUser();
  const canReview = can(user, 'review:write');
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [reason, setReason] = useState('');
  const [active, setActive] = useState<ReviewTaskDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [drawType, setDrawType] = useState<string>('SCRATCH');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    try {
      const [q, s] = await Promise.all([reviewApi.queue({ reason: reason || undefined }), reviewApi.stats()]);
      setTasks(q);
      setStats(s);
      return q;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the review queue');
      return [];
    } finally {
      setLoading(false);
    }
  }, [reason]);

  const openTask = async (id: string) => {
    setError(null);
    setDrawing(false);
    setSelectedId(null);
    try {
      setActive(await reviewApi.task(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to open task');
    }
  };

  useEffect(() => {
    loadQueue().then((q) => {
      if (q.length && !active) openTask(q[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadQueue]);

  const refreshActive = async () => {
    if (active) setActive(await reviewApi.task(active.id));
  };

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(false);
    }
  };

  const handleFeedback = async (d: DefectDetection, action: 'CONFIRM' | 'REJECT' | 'RELABEL', defectType?: string) => {
    if (!d.id) return;
    await run(async () => {
      if (d.detector === 'HUMAN' && action === 'REJECT') await reviewApi.deleteAnnotation(d.id!);
      else await defectApi.submitFeedback(d.id!, { action, defect_type: defectType });
      await refreshActive();
    });
  };

  const handleDraw = (bbox: [number, number, number, number]) =>
    run(async () => {
      if (!active) return;
      await reviewApi.annotate(active.image_id, { defect_type: drawType, bbox });
      await refreshActive();
    });

  const goNext = async (doneId: string) => {
    const q = await loadQueue();
    const next = q.find((t) => t.id !== doneId);
    if (next) await openTask(next.id);
    else setActive(null);
  };

  const handleComplete = () =>
    run(async () => {
      if (!active) return;
      const res = await reviewApi.complete(active.image_id, { accept_pending: true });
      setNotice(
        `Verified ${active.inspection_number} for training (${res.dataset_split} split)` +
          (res.accepted_pending ? ` — ${res.accepted_pending} pending detection(s) accepted` : '') +
          (res.auto_training_job_id ? ' — automatic retraining queued' : '')
      );
      await goNext(active.id);
    });

  const handleSkip = () =>
    run(async () => {
      if (!active) return;
      await reviewApi.skip(active.id);
      await goNext(active.id);
    });

  const visible = active?.detections || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#000000] flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5 text-[#6b21a8]" /> Review Queue
          </h1>
          <p className="text-xs text-[#615d59] mt-0.5">
            Images the smart sampler routed to you. Verified images become training labels for the next model.
          </p>
        </div>
        {can(user, 'model:read') && (
          <Link href="/models" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold bg-[#213183] text-white hover:bg-[#1a2768]">
            <Database className="w-4 h-4" /> Models &amp; Learning
          </Link>
        )}
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ['Open tasks', stats.open],
            ['Reviewed (24 h)', stats.done_last_24h],
            ['Verified images', stats.verified_images],
            ['New since last dataset', stats.new_verified_since_last_dataset],
          ].map(([label, value]) => (
            <div key={label as string} className="bg-white rounded-xl border border-[#e6e6e6] p-3.5">
              <p className="text-[11px] font-semibold text-[#615d59]">{label}</p>
              <p className="text-xl font-bold text-[#000000] mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <button
          type="button"
          onClick={() => setReason('')}
          className={`px-3 py-1 rounded-full font-semibold border ${!reason ? 'bg-[#0075de] text-white border-[#0075de]' : 'bg-white border-[#e6e6e6]'}`}
        >
          All
        </button>
        {Object.entries(stats?.by_reason || {}).map(([code, n]) => (
          <button
            key={code}
            type="button"
            onClick={() => setReason(code)}
            className={`px-3 py-1 rounded-full font-semibold border ${
              reason === code ? 'bg-[#0075de] text-white border-[#0075de]' : 'bg-white border-[#e6e6e6]'
            }`}
          >
            {REASON_LABELS[code] || code} · {n}
          </button>
        ))}
        <button type="button" onClick={() => loadQueue()} className="ml-auto p-1.5 rounded-full bg-white border border-[#e6e6e6]" title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 text-[#0075de] ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2 text-xs text-[#991B1B]">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}
      {notice && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-xl flex items-center gap-2 text-xs text-[#166534]">
          <CheckCircle2 className="w-4 h-4" /> {notice}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Queue */}
        <div className="lg:col-span-4 space-y-2 max-h-[780px] overflow-y-auto pr-1">
          {tasks.length === 0 && !loading && (
            <div className="bg-white rounded-xl border border-[#e6e6e6] p-8 text-center text-xs text-[#615d59]">
              <Inbox className="w-6 h-6 mx-auto mb-2 text-[#a39e98]" />
              Nothing to review. New tasks appear as images are inspected.
            </div>
          )}
          {tasks.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => openTask(t.id)}
              className={`w-full text-left flex gap-3 p-2.5 rounded-xl border transition-colors ${
                active?.id === t.id ? 'bg-[#f0f7ff] border-[#0075de]/40' : 'bg-white border-[#e6e6e6] hover:bg-[#f6f5f4]'
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={getStorageUrl(t.image_url)} alt="" className="w-20 h-16 object-cover rounded-md shrink-0 bg-[#e6e6e6]" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] font-bold text-[#213183] truncate">{t.inspection_number}</span>
                  <span className="text-[10px] font-bold text-[#615d59]">P{t.priority.toFixed(0)}</span>
                </div>
                <p className="text-[11px] text-[#31302e] truncate">{t.product_name || 'Unnamed'}{t.station ? ` · ${t.station}` : ''}</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {t.reasons.map((r, i) => (
                    <span key={i} className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${REASON_STYLES[r.code] || 'bg-gray-100'}`}>
                      {REASON_LABELS[r.code] || r.code}
                    </span>
                  ))}
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Workspace */}
        <div className="lg:col-span-8 space-y-3">
          {!active ? (
            <div className="bg-white rounded-xl border border-[#e6e6e6] p-12 text-center text-xs text-[#615d59]">
              Select a task to review.
            </div>
          ) : (
            <>
              <div className="bg-white rounded-xl border border-[#e6e6e6] p-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="font-mono font-bold text-[#213183]">{active.inspection_number}</span>
                <span className="text-[#615d59]">{formatDateTime(active.created_at)}</span>
                <span className="text-[#615d59]">· {active.batch_code ? `Batch ${active.batch_code}` : 'No batch'}</span>
                <Link href={`/defects/${active.inspection_id}`} className="inline-flex items-center gap-1 text-[#0075de] font-semibold hover:underline">
                  Open inspection <ExternalLink className="w-3 h-3" />
                </Link>
                <div className="w-full flex flex-wrap gap-1.5 pt-1">
                  {active.reasons.map((r, i) => (
                    <span key={i} className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${REASON_STYLES[r.code] || 'bg-gray-100'}`}>
                      {REASON_LABELS[r.code] || r.code}: {r.detail}
                    </span>
                  ))}
                </div>
              </div>

              {canReview && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => setDrawing((v) => !v)}
                    className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full font-semibold border ${
                      drawing ? 'bg-green-600 text-white border-green-600' : 'bg-white border-[#e6e6e6] text-[#31302e]'
                    }`}
                  >
                    <PenSquare className="w-3.5 h-3.5" />
                    {drawing ? 'Drawing: drag on the image' : 'Draw missed defect'}
                  </button>
                  {drawing && (
                    <div className="flex items-center gap-1">
                      {DEFECT_TYPES.filter((t) => t !== 'DIMENSIONAL_ANOMALY').map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => setDrawType(t)}
                          className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border ${drawType === t ? 'text-white' : 'bg-white'}`}
                          style={drawType === t ? { background: defectColor(t), borderColor: defectColor(t) } : { borderColor: defectColor(t), color: defectColor(t) }}
                        >
                          {defectLabel(t)}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="ml-auto flex items-center gap-2">
                    <button type="button" onClick={handleSkip} disabled={busy} className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full font-semibold bg-white border border-[#e6e6e6] disabled:opacity-50">
                      <SkipForward className="w-3.5 h-3.5" /> Skip
                    </button>
                    <button
                      type="button"
                      onClick={handleComplete}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full font-bold bg-[#0075de] text-white hover:bg-[#005bab] disabled:opacity-50"
                      title="Every defect on this image is now correct: confirm pending detections and use it for training"
                    >
                      {busy ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                      Verify for training
                    </button>
                  </div>
                </div>
              )}

              <AnnotatableImage
                imageUrl={getStorageUrl(active.image_url)}
                detections={visible}
                selectedId={selectedId}
                onSelect={(d) => setSelectedId(d.id || null)}
                drawEnabled={drawing && canReview}
                drawColor={defectColor(drawType)}
                onDraw={handleDraw}
              />

              <DefectTable
                detections={visible}
                selectedId={selectedId}
                onSelect={(d) => setSelectedId(d.id || null)}
                onFeedback={handleFeedback}
                readOnly={!canReview}
                title="Detections on this image"
              />
              <p className="text-[11px] text-[#615d59]">
                Confirm correct boxes, reject false alarms, relabel wrong classes and draw anything the detectors missed.
                &quot;Verify for training&quot; accepts the remaining pending detections; reviewer-drawn boxes are removed with ✕.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
