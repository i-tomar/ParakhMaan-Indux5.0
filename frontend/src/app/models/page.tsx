'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  BrainCircuit, Database, PlayCircle, Ghost, Rocket, Undo2, RefreshCw, Download, CheckCircle2, XCircle,
  AlertCircle, Activity, ClipboardCheck, ChevronDown, ChevronRight, FlaskConical, History
} from 'lucide-react';
import { jobsApi, learningApi, openAuthenticatedFile } from '@/lib/api';
import { can } from '@/lib/auth';
import { useAuthUser } from '@/lib/useAuth';
import { formatDateTime } from '@/lib/formatters';
import { DatasetVersionInfo, DriftStation, Job, LearningOverview, ModelEventInfo, ModelVersionInfo } from '@/lib/types';

const STATUS_STYLES: Record<string, string> = {
  ACTIVE: 'bg-green-100 text-[#166534] border-green-200',
  SHADOW: 'bg-purple-100 text-[#6b21a8] border-purple-200',
  GATE_PASSED: 'bg-blue-100 text-[#0075de] border-blue-200',
  GATE_FAILED: 'bg-red-100 text-[#991B1B] border-red-200',
  CANDIDATE: 'bg-amber-100 text-[#854D0E] border-amber-200',
  TRAINING: 'bg-amber-100 text-[#854D0E] border-amber-200',
  RETIRED: 'bg-gray-100 text-gray-600 border-gray-200',
  FAILED: 'bg-red-100 text-[#991B1B] border-red-200',
};

const DRIFT_STYLES: Record<string, string> = {
  OK: 'bg-green-100 text-[#166534]',
  WATCH: 'bg-amber-100 text-[#854D0E]',
  ALERT: 'bg-red-100 text-[#991B1B]',
  INSUFFICIENT_DATA: 'bg-gray-100 text-gray-600',
};

const card = 'bg-white rounded-xl border border-[#e6e6e6] p-4';
const pill = 'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold border disabled:opacity-40';
const fmt = (v?: number | null, digits = 3) => (typeof v === 'number' ? v.toFixed(digits) : '—');

export default function ModelsPage() {
  const user = useAuthUser();
  const manage = can(user, 'model:manage');
  const [overview, setOverview] = useState<LearningOverview | null>(null);
  const [models, setModels] = useState<ModelVersionInfo[]>([]);
  const [datasetsList, setDatasets] = useState<DatasetVersionInfo[]>([]);
  const [drift, setDrift] = useState<DriftStation[]>([]);
  const [events, setEvents] = useState<ModelEventInfo[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, m, d, dr, ev] = await Promise.all([
        learningApi.overview(), learningApi.models(), learningApi.datasets(), learningApi.drift(), learningApi.events(),
      ]);
      setOverview(o);
      setModels(m);
      setDatasets(d);
      setDrift(dr.stations);
      setEvents(ev);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the learning loop');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    }
  };

  const follow = async (start: () => Promise<Job>, label: string) => {
    setError(null);
    setNotice(null);
    try {
      const queued = await start();
      setJob(queued);
      const final = await jobsApi.waitFor(queued.id, setJob, 1500);
      setNotice(`${label} finished`);
      setJob(final);
    } catch (e) {
      setError(e instanceof Error ? e.message : `${label} failed`);
    } finally {
      await load();
    }
  };

  const withOverride = (mv: ModelVersionInfo, action: (reason?: string) => Promise<unknown>, verb: string) => {
    const gated = mv.status === 'GATE_PASSED' || mv.status === 'SHADOW';
    if (gated) return act(() => action(), `${mv.name}: ${verb}`);
    if (!can(user, 'model:override')) {
      setError(`${mv.name} has not passed the evaluation gate; only an administrator can ${verb} it with a recorded reason.`);
      return;
    }
    const reason = window.prompt(`${mv.name} did not pass the evaluation gate. Reason for override (recorded in the audit log):`);
    if (reason) act(() => action(reason), `${mv.name}: ${verb} (override recorded)`);
  };

  const active = overview?.active_model;
  const shadow = overview?.shadow_model;
  const jobRunning = job && (job.status === 'QUEUED' || job.status === 'RUNNING');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#000000] flex items-center gap-2">
            <BrainCircuit className="w-5 h-5 text-[#6b21a8]" /> Models &amp; Learning Loop
          </h1>
          <p className="text-xs text-[#615d59] mt-0.5">
            Reviewed data → versioned dataset → training → evaluation gate → shadow test → approved promotion, with rollback.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/review" className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold bg-white border border-[#e6e6e6]">
            <ClipboardCheck className="w-4 h-4 text-[#0075de]" /> Review queue
          </Link>
          {manage && (
            <>
              <button
                type="button"
                disabled={!!jobRunning}
                onClick={() => follow(() => learningApi.buildDataset(), 'Dataset build')}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold bg-white border border-[#e6e6e6] disabled:opacity-50"
              >
                <Database className="w-4 h-4 text-[#0075de]" /> Build dataset
              </button>
              <button
                type="button"
                disabled={!!jobRunning}
                onClick={() => follow(() => learningApi.train(), 'Training')}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold bg-[#6b21a8] text-white hover:bg-[#581c87] disabled:opacity-50"
              >
                <PlayCircle className="w-4 h-4" /> Train candidate
              </button>
            </>
          )}
          {can(user, 'system:configure') && (
            <button
              type="button"
              onClick={() => act(() => learningApi.seedReviewed(60), 'Added 60 synthetic verified images (demo data)')}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold bg-amber-50 text-[#854D0E] border border-amber-200"
              title="Development helper: synthetic images with known defect boxes, already verified"
            >
              <FlaskConical className="w-4 h-4" /> Seed demo data
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2 text-xs text-[#991B1B]">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}
      {notice && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-xl flex items-center gap-2 text-xs text-[#166534]">
          <CheckCircle2 className="w-4 h-4" /> {notice}
        </div>
      )}
      {job && (
        <div className={card}>
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-[#000000]">
              {job.job_type.replace('_', ' ')} · {job.status}
            </span>
            <span className="text-[#615d59]">{job.message}</span>
          </div>
          <div className="mt-2 w-full h-2 rounded-full bg-[#f6f5f4] border border-[#e6e6e6] overflow-hidden">
            <div
              className={`h-full transition-all ${job.status === 'FAILED' ? 'bg-red-500' : 'bg-[#6b21a8]'}`}
              style={{ width: `${Math.round((job.progress || 0) * 100)}%` }}
            />
          </div>
          {job.error && <p className="text-[11px] text-[#991B1B] mt-1">{job.error}</p>}
        </div>
      )}

      {/* Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className={card}>
          <p className="text-[11px] font-bold uppercase text-[#615d59]">Active model</p>
          {active ? (
            <>
              <p className="text-lg font-bold text-[#000000] mt-1">{active.name} <span className="text-xs font-medium text-[#615d59]">({active.source.toLowerCase()})</span></p>
              <p className="text-[11px] text-[#615d59]">val mAP@0.5 {fmt(active.train_metrics?.mAP50)} · activated {formatDateTime(active.activated_at || active.created_at)}</p>
              {active.gate_report?.candidate && (
                <p className="text-[11px] text-[#615d59]">golden mAP@0.5 {fmt(active.gate_report.candidate.map50)}</p>
              )}
            </>
          ) : (
            <p className="text-xs text-[#615d59] mt-1">No registered model — the configured file / OpenCV is used.</p>
          )}
        </div>
        <div className={card}>
          <p className="text-[11px] font-bold uppercase text-[#615d59]">Shadow test</p>
          {shadow ? (
            <>
              <p className="text-lg font-bold text-[#6b21a8] mt-1">{shadow.name}</p>
              <p className="text-[11px] text-[#615d59]">
                {shadow.shadow_stats.images} live images · agreement {fmt(shadow.shadow_stats.agreement, 2)}
              </p>
              {shadow.shadow_stats.shadow && shadow.shadow_stats.champion ? (
                <p className="text-[11px] text-[#31302e]">
                  On {shadow.shadow_stats.verified_images} verified: F1 {fmt(shadow.shadow_stats.shadow.f1, 2)} vs active {fmt(shadow.shadow_stats.champion.f1, 2)}
                </p>
              ) : (
                <p className="text-[11px] text-[#615d59]">Verified-label comparison appears as shadowed images are reviewed.</p>
              )}
            </>
          ) : (
            <p className="text-xs text-[#615d59] mt-1">No model in shadow mode.</p>
          )}
        </div>
        <div className={card}>
          <p className="text-[11px] font-bold uppercase text-[#615d59]">Latest dataset</p>
          {overview?.latest_dataset ? (
            <>
              <p className="text-lg font-bold text-[#000000] mt-1">v{overview.latest_dataset.version} <span className="text-xs font-medium text-[#615d59]">{overview.latest_dataset.status}</span></p>
              <p className="text-[11px] text-[#615d59]">
                {overview.latest_dataset.image_count} images · {overview.latest_dataset.label_count} labels · train {overview.latest_dataset.split_counts?.train ?? 0} / val {overview.latest_dataset.split_counts?.val ?? 0} / golden test {overview.latest_dataset.split_counts?.test ?? 0}
              </p>
            </>
          ) : (
            <p className="text-xs text-[#615d59] mt-1">No dataset built yet.</p>
          )}
        </div>
        <div className={card}>
          <p className="text-[11px] font-bold uppercase text-[#615d59]">Feedback flowing in</p>
          <p className="text-lg font-bold text-[#000000] mt-1">{overview?.new_verified_since_last_dataset ?? 0}</p>
          <p className="text-[11px] text-[#615d59]">
            newly verified images since the last dataset ·{' '}
            {overview?.policy?.auto_train_min_new_verified
              ? `auto-train at ${overview.policy.auto_train_min_new_verified}`
              : 'manual training'}
          </p>
        </div>
      </div>

      {/* Registry */}
      <div className={`${card} p-0 overflow-hidden`}>
        <div className="px-4 py-3 border-b border-[#e6e6e6] bg-[#f6f5f4] flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-[#6b21a8]" />
          <h3 className="font-bold text-xs uppercase tracking-wider">Model registry</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#e6e6e6] text-[10px] font-bold text-[#615d59] uppercase tracking-wider">
                <th className="py-2.5 px-4" />
                <th className="py-2.5 px-2">Version</th>
                <th className="py-2.5 px-2">Status</th>
                <th className="py-2.5 px-2">Dataset</th>
                <th className="py-2.5 px-2">Val mAP@0.5</th>
                <th className="py-2.5 px-2">Golden mAP@0.5</th>
                <th className="py-2.5 px-2">Gate</th>
                <th className="py-2.5 px-2">Created</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e6e6e6]">
              {models.length === 0 && (
                <tr><td colSpan={9} className="py-6 text-center text-[#615d59]">No models registered.</td></tr>
              )}
              {models.map((m) => {
                const open = expanded === m.id;
                const gate = m.gate_report;
                return (
                  <React.Fragment key={m.id}>
                    <tr className="hover:bg-[#f6f5f4]/70">
                      <td className="py-2.5 px-4">
                        <button type="button" onClick={() => setExpanded(open ? null : m.id)} className="text-[#615d59]">
                          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </button>
                      </td>
                      <td className="py-2.5 px-2 font-bold text-[#000000]">{m.name} <span className="font-normal text-[#615d59]">{m.source.toLowerCase()}</span></td>
                      <td className="py-2.5 px-2">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_STYLES[m.status] || ''}`}>{m.status.replace('_', ' ')}</span>
                      </td>
                      <td className="py-2.5 px-2 text-[#615d59]">{m.dataset_version ? `v${m.dataset_version}` : '—'}</td>
                      <td className="py-2.5 px-2 font-mono">{fmt(m.train_metrics?.mAP50)}</td>
                      <td className="py-2.5 px-2 font-mono">{fmt(gate?.candidate?.map50)}</td>
                      <td className="py-2.5 px-2">
                        {gate ? (
                          gate.passed ? (
                            <span className="inline-flex items-center gap-1 text-[#166534] font-semibold"><CheckCircle2 className="w-3.5 h-3.5" /> passed</span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[#991B1B] font-semibold"><XCircle className="w-3.5 h-3.5" /> failed</span>
                          )
                        ) : (
                          <span className="text-[#615d59]">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-[#615d59]">{formatDateTime(m.created_at)}</td>
                      <td className="py-2.5 px-4 text-right whitespace-nowrap space-x-1">
                        {manage && ['GATE_PASSED', 'GATE_FAILED', 'CANDIDATE'].includes(m.status) && (
                          <button type="button" className={`${pill} bg-white border-purple-200 text-[#6b21a8]`}
                            onClick={() => withOverride(m, (r) => learningApi.startShadow(m.id, r), 'start shadow testing')}>
                            <Ghost className="w-3 h-3" /> Shadow
                          </button>
                        )}
                        {manage && m.status === 'SHADOW' && (
                          <button type="button" className={`${pill} bg-white border-[#e6e6e6]`}
                            onClick={() => act(() => learningApi.stopShadow(m.id), `${m.name} left shadow mode`)}>
                            Stop shadow
                          </button>
                        )}
                        {manage && ['GATE_PASSED', 'SHADOW', 'GATE_FAILED', 'CANDIDATE'].includes(m.status) && (
                          <button type="button" className={`${pill} bg-[#0075de] text-white border-[#0075de]`}
                            onClick={() => withOverride(m, (r) => learningApi.promote(m.id, r), 'promote')}>
                            <Rocket className="w-3 h-3" /> Promote
                          </button>
                        )}
                        {manage && m.status === 'RETIRED' && (
                          <button type="button" className={`${pill} bg-white border-amber-300 text-[#854D0E]`}
                            onClick={() => {
                              if (window.confirm(`Roll back production inference to ${m.name}?`)) {
                                act(() => learningApi.rollback(m.id), `Rolled back to ${m.name}`);
                              }
                            }}>
                            <Undo2 className="w-3 h-3" /> Roll back
                          </button>
                        )}
                        {manage && !['TRAINING', 'FAILED'].includes(m.status) && (
                          <button type="button" className={`${pill} bg-white border-[#e6e6e6]`} disabled={!!jobRunning}
                            onClick={() => follow(() => learningApi.evaluate(m.id), `Evaluation of ${m.name}`)}>
                            <Activity className="w-3 h-3" /> Evaluate
                          </button>
                        )}
                        {manage && m.sha256 && (
                          <button type="button" className={`${pill} bg-white border-[#e6e6e6]`}
                            onClick={() => openAuthenticatedFile(learningApi.modelDownloadUrl(m.id)).catch((e) => setError(e.message))}>
                            <Download className="w-3 h-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                    {open && (
                      <tr className="bg-[#f6f5f4]/60">
                        <td colSpan={9} className="px-6 py-4">
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
                            <div>
                              <p className="font-bold text-[#000000] mb-1.5">Evaluation gate</p>
                              {gate ? (
                                <>
                                  <p className="text-[11px] text-[#615d59] mb-2">
                                    {gate.test_images} golden test images · dataset v{gate.dataset_version}
                                    {gate.champion_name ? ` · compared with ${gate.champion_name}` : ''}
                                  </p>
                                  <ul className="space-y-1">
                                    {gate.checks.map((c) => (
                                      <li key={c.name} className="flex items-start gap-1.5">
                                        {c.passed ? <CheckCircle2 className="w-3.5 h-3.5 text-[#1aae39] mt-0.5" /> : <XCircle className="w-3.5 h-3.5 text-[#991B1B] mt-0.5" />}
                                        <span><b>{c.name.replace(/_/g, ' ')}</b> — {c.detail}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </>
                              ) : (
                                <p className="text-[#615d59]">Not evaluated yet.</p>
                              )}
                            </div>
                            <div>
                              <p className="font-bold text-[#000000] mb-1.5">Model card</p>
                              {m.model_card ? (
                                <ul className="space-y-0.5 text-[#31302e]">
                                  <li>Classes: {(m.classes || []).join(', ')} · input {m.input_size}px</li>
                                  {m.model_card.warm_start_from && <li>Warm start: {m.model_card.warm_start_from}</li>}
                                  {m.model_card.dataset_version && <li>Dataset v{m.model_card.dataset_version} · splits {JSON.stringify(m.model_card.dataset_split_counts)}</li>}
                                  {m.model_card.training_data && <li>Training data: {m.model_card.training_data}</li>}
                                  {m.train_metrics && <li>Validation: {Object.entries(m.train_metrics).filter(([k]) => typeof m.train_metrics?.[k] === 'number').map(([k, v]) => `${k} ${v}`).join(' · ')}</li>}
                                  {(m.model_card.limitations || []).map((l: string) => <li key={l} className="text-[#854D0E]">⚠ {l}</li>)}
                                </ul>
                              ) : (
                                <p className="text-[#615d59]">No model card.</p>
                              )}
                              {m.sha256 && <p className="font-mono text-[10px] text-[#615d59] mt-2">sha256 {m.sha256}</p>}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Datasets */}
        <div className={`${card} p-0 overflow-hidden`}>
          <div className="px-4 py-3 border-b border-[#e6e6e6] bg-[#f6f5f4] flex items-center gap-2">
            <Database className="w-4 h-4 text-[#0075de]" />
            <h3 className="font-bold text-xs uppercase tracking-wider">Dataset versions</h3>
          </div>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#e6e6e6] text-[10px] font-bold text-[#615d59] uppercase tracking-wider">
                <th className="py-2 px-4">Version</th>
                <th className="py-2 px-2">Images</th>
                <th className="py-2 px-2">Train / Val / Golden</th>
                <th className="py-2 px-2">Labels by class</th>
                <th className="py-2 px-4 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e6e6e6]">
              {datasetsList.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-[#615d59]">No datasets yet.</td></tr>}
              {datasetsList.map((d) => (
                <tr key={d.id}>
                  <td className="py-2 px-4 font-bold">v{d.version} <span className="font-normal text-[#615d59]">{d.status}</span></td>
                  <td className="py-2 px-2">{d.image_count}</td>
                  <td className="py-2 px-2 font-mono">{d.split_counts?.train ?? 0} / {d.split_counts?.val ?? 0} / {d.split_counts?.test ?? 0}</td>
                  <td className="py-2 px-2 text-[11px] text-[#615d59]">{Object.entries(d.class_counts || {}).map(([k, v]) => `${k} ${v}`).join(' · ')}</td>
                  <td className="py-2 px-4 text-right">
                    {manage && d.status === 'READY' && (
                      <button type="button" className={`${pill} bg-white border-[#e6e6e6]`}
                        onClick={() => openAuthenticatedFile(learningApi.datasetDownloadUrl(d.id)).catch((e) => setError(e.message))}>
                        <Download className="w-3 h-3" /> YOLO zip
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Drift */}
        <div className={`${card} p-0 overflow-hidden`}>
          <div className="px-4 py-3 border-b border-[#e6e6e6] bg-[#f6f5f4] flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#dd5b00]" />
            <h3 className="font-bold text-xs uppercase tracking-wider">Input drift by station (PSI, last 24 h vs 14 days)</h3>
          </div>
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#e6e6e6] text-[10px] font-bold text-[#615d59] uppercase tracking-wider">
                <th className="py-2 px-4">Station</th>
                <th className="py-2 px-2">Status</th>
                <th className="py-2 px-2">Brightness</th>
                <th className="py-2 px-2">Confidence</th>
                <th className="py-2 px-2">Detections</th>
                <th className="py-2 px-4">Images (base / recent)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e6e6e6]">
              {drift.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-[#615d59]">No inspections yet.</td></tr>}
              {drift.map((s) => (
                <tr key={s.station_id || 'none'}>
                  <td className="py-2 px-4 font-semibold">{s.station}</td>
                  <td className="py-2 px-2"><span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${DRIFT_STYLES[s.status] || ''}`}>{s.status.replace('_', ' ')}</span></td>
                  <td className="py-2 px-2 font-mono">{fmt(s.features.brightness?.psi, 2)}</td>
                  <td className="py-2 px-2 font-mono">{fmt(s.features.confidence?.psi, 2)}</td>
                  <td className="py-2 px-2 font-mono">{fmt(s.features.count?.psi, 2)}</td>
                  <td className="py-2 px-4 text-[#615d59]">{s.baseline_images} / {s.recent_images}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Audit trail */}
      <div className={card}>
        <div className="flex items-center gap-2 mb-3">
          <History className="w-4 h-4 text-[#0075de]" />
          <h3 className="font-bold text-xs uppercase tracking-wider">Model & dataset audit trail</h3>
          <button type="button" onClick={load} className="ml-auto p-1.5 rounded-full bg-white border border-[#e6e6e6]" title="Refresh">
            <RefreshCw className="w-3.5 h-3.5 text-[#0075de]" />
          </button>
        </div>
        {events.length === 0 ? (
          <p className="text-xs text-[#615d59]">No events yet.</p>
        ) : (
          <ul className="space-y-1.5 text-xs">
            {events.map((e) => (
              <li key={e.id} className="flex gap-3">
                <span className="font-mono text-[10px] text-[#615d59] w-36 shrink-0">{formatDateTime(e.created_at)}</span>
                <span className="font-semibold text-[#213183] w-40 shrink-0">{e.event_type.replace(/_/g, ' ')}</span>
                <span className="text-[#31302e]">{e.description}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
