'use client';

import React, { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { api, openAuthenticatedFile } from '@/lib/api';
import { can } from '@/lib/auth';
import { useAuthUser } from '@/lib/useAuth';
import { Inspection, ComplianceResult } from '@/lib/types';
import EvidenceViewer from '@/components/EvidenceViewer';
import ComplianceMatrix from '@/components/ComplianceMatrix';
import ImageQualityCard from '@/components/ImageQualityCard';
import ReviewModal from '@/components/ReviewModal';
import AuditTimeline from '@/components/AuditTimeline';
import { formatDateTime } from '@/lib/formatters';
import {
  ShieldCheck, AlertTriangle, XCircle, Download, FileText,
  CheckCircle2, ArrowLeft, RefreshCw, UserCheck, ShieldAlert,
  BrainCircuit, Sparkles, Bot, AlertOctagon, Check, Activity
} from 'lucide-react';

export default function InspectionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const id = resolvedParams.id;
  const user = useAuthUser();

  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);
  const [selectedResult, setSelectedResult] = useState<ComplianceResult | null>(null);
  
  // AI Deep Analysis State
  const [aiAnalysis, setAiAnalysis] = useState<any | null>(null);
  const [loadingAi, setLoadingAi] = useState(false);
  const [llmStatus, setLlmStatus] = useState<any | null>(null);

  // Review Modal State
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewTargetResult, setReviewTargetResult] = useState<ComplianceResult | null>(null);

  // Finalize state
  const [finalizing, setFinalizing] = useState(false);

  useEffect(() => {
    loadInspection();
    checkLlm();
  }, [id]);

  const loadInspection = async () => {
    setLoading(true);
    try {
      const data = await api.getInspection(id);
      setInspection(data);
      if (data.compliance_results && data.compliance_results.length > 0) {
        setSelectedResult(data.compliance_results[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const checkLlm = async () => {
    try {
      const status = await api.getLlmStatus();
      setLlmStatus(status);
    } catch (e) {
      console.error('LLM status check error:', e);
    }
  };

  const handleReprocess = async () => {
    if (!inspection) return;
    setReprocessing(true);
    try {
      const updated = await api.reprocessInspection(inspection.id);
      setInspection(updated);
      if (updated.compliance_results && updated.compliance_results.length > 0) {
        setSelectedResult(updated.compliance_results[0]);
      }
      // Also refresh AI analysis if open
      if (aiAnalysis) {
        handleRunAiAnalysis();
      }
    } catch (err) {
      console.error('Error reprocessing inspection:', err);
    } finally {
      setReprocessing(false);
    }
  };

  const handleRunAiAnalysis = async () => {
    if (!inspection) return;
    setLoadingAi(true);
    try {
      const res = await api.getDeepAiAnalysis(inspection.id);
      setAiAnalysis(res);
    } catch (err) {
      console.error('Error running AI analysis:', err);
    } finally {
      setLoadingAi(false);
    }
  };

  const handleOpenReview = (result: ComplianceResult) => {
    setReviewTargetResult(result);
    setReviewModalOpen(true);
  };

  const handleSubmitReviewAction = async (actionData: any) => {
    if (!inspection) return;
    await api.submitReviewAction(inspection.id, actionData);
    await loadInspection();
  };

  const handleFinalize = async () => {
    if (!inspection) return;
    setFinalizing(true);
    try {
      await api.finalizeInspection(inspection.id, {
        final_remarks: 'Statutory inspection finalized and digitally signed by Officer #LM-8821'
      });
      await loadInspection();
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
        <p className="text-sm font-semibold text-[#000000]">Loading Inspection Audit & Evidence...</p>
      </div>
    );
  }

  if (!inspection) {
    return (
      <div className="bg-white rounded-xl border border-[#e6e6e6] p-12 text-center">
        <AlertTriangle className="w-10 h-10 text-[#dd5b00] mx-auto mb-3" />
        <h2 className="text-sm font-bold text-[#000000]">Inspection Record Not Found</h2>
        <Link href="/inspections" className="text-xs text-[#0075de] underline mt-2 inline-block">
          Return to Inspections List
        </Link>
      </div>
    );
  }

  const outcome = inspection.overall_outcome || 'PENDING';
  const reportUrl = api.getReportUrl(inspection.id);

  return (
    <div className="space-y-6">
      {/* Top Back Nav & Quick Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <Link
          href="/inspections"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#615d59] hover:text-[#000000] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Inspections</span>
        </Link>

        <div className="flex items-center flex-wrap gap-2">
          {/* Reprocess Button */}
          <button
            onClick={handleReprocess}
            disabled={reprocessing}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold bg-white text-[#0075de] border border-[#0075de]/30 hover:bg-[#f0f7ff] transition-all shadow-xs disabled:opacity-50"
            title="Re-run WinOCR text localization and Rule Engine evaluation on uploaded package surfaces"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${reprocessing ? 'animate-spin' : ''}`} />
            <span>{reprocessing ? 'Reprocessing OCR...' : 'Reprocess with AI / OCR'}</span>
          </button>

          {/* Download Official PDF Report */}
          <button
            type="button"
            onClick={() => openAuthenticatedFile(reportUrl).catch((err) => console.error(err))}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold bg-white text-[#31302e] border border-[#e6e6e6] hover:bg-[#f6f5f4] transition-all shadow-xs"
          >
            <Download className="w-4 h-4 text-[#0075de]" />
            <span>Download Official PDF Report</span>
          </button>

          {/* Finalize Button */}
          {inspection.status !== 'FINALIZED' && can(user, 'inspection:finalize') && (
            <button
              onClick={handleFinalize}
              disabled={finalizing}
              className="flex items-center gap-1.5 px-5 py-2 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-xs disabled:opacity-50"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{finalizing ? 'Finalizing...' : 'Finalize & Sign Off'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Outcome Banner */}
      <div
        className={`rounded-xl p-5 border flex flex-col md:flex-row items-start md:items-center justify-between gap-4 ${
          outcome === 'PASS'
            ? 'bg-green-50 border-green-200 text-[#166534]'
            : outcome === 'REVIEW'
            ? 'bg-amber-50 border-amber-200 text-[#854D0E]'
            : outcome === 'POSSIBLE_NON_COMPLIANCE'
            ? 'bg-red-50 border-red-200 text-[#991B1B]'
            : 'bg-gray-50 border-gray-200 text-gray-800'
        }`}
      >
        <div className="flex items-center gap-3.5">
          <div className="p-2.5 rounded-lg bg-white shadow-2xs">
            {outcome === 'PASS' && <CheckCircle2 className="w-6 h-6 text-[#1aae39]" />}
            {outcome === 'REVIEW' && <AlertTriangle className="w-6 h-6 text-[#dd5b00]" />}
            {outcome === 'POSSIBLE_NON_COMPLIANCE' && <XCircle className="w-6 h-6 text-[#991B1B]" />}
            {outcome === 'PENDING' && <FileText className="w-6 h-6 text-gray-600" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-sm bg-white/70">
                {inspection.inspection_number}
              </span>
              <h2 className="font-bold text-sm tracking-tight">
                {outcome === 'PASS' && 'LEGAL METROLOGY COMPLIANT (PASS)'}
                {outcome === 'REVIEW' && 'INSPECTOR REVIEW REQUIRED'}
                {outcome === 'POSSIBLE_NON_COMPLIANCE' && 'POSSIBLE NON-COMPLIANCE DETECTED'}
                {outcome === 'PENDING' && 'INSPECTION PENDING'}
              </h2>
            </div>
            <p className="text-xs opacity-90 mt-0.5">
              {inspection.product_name || 'Packaged Commodity'} • Category: {inspection.category.replace('_', ' ')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div>
            <p className="text-[10px] opacity-75 uppercase font-semibold">Status</p>
            <p className="font-bold">{inspection.status}</p>
          </div>
          <div className="border-l border-current/20 pl-4">
            <p className="text-[10px] opacity-75 uppercase font-semibold">Sampling Date</p>
            <p className="font-mono">{formatDateTime(inspection.created_at)}</p>
          </div>
        </div>
      </div>

      {/* Main Grid: Evidence Locator + Quality & Declarations */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Evidence Locator with Heatmap Support */}
        <div className="lg:col-span-7 space-y-4">
          <EvidenceViewer
            inspectionId={inspection.id}
            images={inspection.images || []}
            selectedResult={selectedResult}
            declarations={inspection.declarations || []}
          />
        </div>

        {/* Right: Quality & Extracted Declarations */}
        <div className="lg:col-span-5 space-y-4">
          {/* OpenCV Quality Cards for Uploaded Surfaces */}
          <div className="space-y-3">
            <h3 className="font-bold text-xs text-[#000000] uppercase tracking-wider">
              OpenCV Image Quality Engine Results
            </h3>
            {(inspection.images || []).map((img) => (
              <ImageQualityCard key={img.id} image={img} />
            ))}
          </div>

          {/* Extracted Structured Declarations Table */}
          <div className="bg-white rounded-xl border border-[#e6e6e6] p-4 elevation-0">
            <h3 className="font-bold text-xs text-[#000000] uppercase tracking-wider mb-2.5 pb-2 border-b border-[#e6e6e6]">
              Extracted Legal Declarations
            </h3>
            <div className="space-y-2">
              {(inspection.declarations || []).length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-xs text-[#615d59]">No declarations parsed yet.</p>
                  <button
                    onClick={handleReprocess}
                    className="mt-2 text-xs text-[#0075de] font-semibold underline"
                  >
                    Click to extract via WinOCR
                  </button>
                </div>
              ) : (
                (inspection.declarations || []).map((d) => (
                  <div key={d.id} className="p-2.5 rounded-lg bg-[#f6f5f4] border border-[#e6e6e6] text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[#000000]">{(d.field_name || d.field || '').replace('_', ' ').toUpperCase()}</span>
                      <span className="text-[10px] text-[#0075de] font-mono">
                        {Math.round((d.confidence ?? 0.0) * 100)}% conf
                      </span>
                    </div>
                    <p className="font-mono text-[11px] text-[#31302e] mt-1 break-words">
                      {d.reviewer_value || d.normalized_value || d.detected_value}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* AI Deep Statutory Legal Analysis Card */}
      <div className="bg-gradient-to-br from-white to-[#f8faff] rounded-xl border border-[#c7dcfb] p-5 elevation-0 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#e2e8f0]">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#0075de]/10 text-[#0075de]">
              <BrainCircuit className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#000000]">AI Statutory Reasoning & LLM Intelligence</h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-[#0075de] border border-blue-200">
                  {llmStatus?.connected ? `Ollama (${llmStatus.active_model}) Active` : 'Deterministic Fallback Active'}
                </span>
              </div>
              <p className="text-xs text-[#615d59]">
                Automated legal synthesis across Legal Metrology (Packaged Commodities) Rules, 2011 & Gazette Amendments
              </p>
            </div>
          </div>

          <button
            onClick={handleRunAiAnalysis}
            disabled={loadingAi}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-xs disabled:opacity-50 shrink-0"
          >
            {loadingAi ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Synthesizing Legal Analysis...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                <span>{aiAnalysis ? 'Refresh AI Analysis' : 'Run Deep LLM Legal Analysis'}</span>
              </>
            )}
          </button>
        </div>

        {/* AI Analysis Content */}
        {aiAnalysis ? (
          <div className="mt-4 space-y-4 text-xs">
            {/* Executive Summary */}
            <div className="p-3.5 rounded-lg bg-white border border-[#e2e8f0] shadow-2xs">
              <p className="font-bold text-[#000000] mb-1 flex items-center gap-1.5">
                <Bot className="w-4 h-4 text-[#0075de]" />
                Executive Statutory Summary
              </p>
              <p className="text-[#334155] leading-relaxed">{aiAnalysis.executive_summary}</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Risk Level */}
              <div className="p-3.5 rounded-lg bg-white border border-[#e2e8f0] shadow-2xs">
                <p className="text-[11px] font-bold uppercase text-[#615d59] mb-1">Assessed Risk Level</p>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                      aiAnalysis.risk_level === 'LOW'
                        ? 'bg-green-100 text-green-800'
                        : aiAnalysis.risk_level === 'MEDIUM'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {aiAnalysis.risk_level} RISK
                  </span>
                  <span className="text-[11px] text-[#615d59]">under Section 36</span>
                </div>
              </div>

              {/* Applicable Legal Sections */}
              <div className="p-3.5 rounded-lg bg-white border border-[#e2e8f0] shadow-2xs md:col-span-2">
                <p className="text-[11px] font-bold uppercase text-[#615d59] mb-1">Applicable Legal Provisions</p>
                <div className="flex flex-wrap gap-1.5">
                  {(aiAnalysis.legal_sections || []).map((sec: string, idx: number) => (
                    <span key={idx} className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-mono text-[10px]">
                      {sec}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Officer Recommendations */}
            {aiAnalysis.recommendations && aiAnalysis.recommendations.length > 0 && (
              <div className="p-3.5 rounded-lg bg-amber-50/70 border border-amber-200/80">
                <p className="font-bold text-[#854D0E] mb-1.5 flex items-center gap-1.5">
                  <AlertOctagon className="w-4 h-4 text-[#dd5b00]" />
                  Inspector Actionable Recommendations
                </p>
                <ul className="space-y-1 pl-4 list-disc text-[#713f12]">
                  {aiAnalysis.recommendations.map((rec: string, idx: number) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="py-4 text-center text-xs text-[#615d59]">
            Click <b>"Run Deep LLM Legal Analysis"</b> to generate structured statutory explanations, risk assessments, and non-delegated officer guidance.
          </div>
        )}
      </div>

      {/* Compliance Matrix Table */}
      <div>
        <ComplianceMatrix
          results={inspection.compliance_results || []}
          onSelectResult={(r) => setSelectedResult(r)}
          selectedResultId={selectedResult?.id}
          onOpenReviewModal={handleOpenReview}
        />
      </div>

      {/* Audit Timeline */}
      <div>
        <AuditTimeline events={inspection.audit_events || []} />
      </div>

      {/* Manual Review Modal */}
      <ReviewModal
        isOpen={reviewModalOpen}
        onClose={() => setReviewModalOpen(false)}
        result={reviewTargetResult}
        onSubmitAction={handleSubmitReviewAction}
      />
    </div>
  );
}
