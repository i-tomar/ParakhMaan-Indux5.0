export const DEFECT_TYPES = ['SCRATCH', 'CRACK', 'DENT', 'DISCOLOURATION', 'DIMENSIONAL_ANOMALY', 'UNKNOWN_ANOMALY'] as const;

// Keep in sync with HeatmapService.DEFECT_COLOURS_BGR so server overlays and UI match.
const DEFECT_META: Record<string, { label: string; color: string }> = {
  SCRATCH: { label: 'Scratch', color: '#0075de' },
  CRACK: { label: 'Crack', color: '#c0186b' },
  DENT: { label: 'Dent', color: '#e07a00' },
  DISCOLOURATION: { label: 'Discolouration', color: '#0a9a8f' },
  DIMENSIONAL_ANOMALY: { label: 'Dimensional Anomaly', color: '#7a3fd0' },
  UNKNOWN_ANOMALY: { label: 'Unknown Anomaly', color: '#6d7a12' },
};

export function defectColor(type?: string | null): string {
  return (type && DEFECT_META[type]?.color) || '#615d59';
}

export function defectLabel(type?: string | null): string {
  if (!type) return '—';
  return DEFECT_META[type]?.label || type.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

export const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: 'bg-red-100 text-[#991B1B] border-red-200',
  HIGH: 'bg-orange-100 text-[#9a3412] border-orange-200',
  MEDIUM: 'bg-amber-100 text-[#854D0E] border-amber-200',
  LOW: 'bg-green-100 text-[#166534] border-green-200',
};

export const OUTCOME_STYLES: Record<string, { badge: string; banner: string; label: string }> = {
  PASS: {
    badge: 'bg-green-100 text-[#166534]',
    banner: 'bg-green-50 border-green-200 text-[#166534]',
    label: 'NO DEFECTS (PASS)',
  },
  REVIEW: {
    badge: 'bg-amber-100 text-[#854D0E]',
    banner: 'bg-amber-50 border-amber-200 text-[#854D0E]',
    label: 'INSPECTOR REVIEW REQUIRED',
  },
  DEFECTIVE: {
    badge: 'bg-red-100 text-[#991B1B]',
    banner: 'bg-red-50 border-red-200 text-[#991B1B]',
    label: 'DEFECTIVE — REJECT / REWORK',
  },
  PENDING: {
    badge: 'bg-gray-100 text-gray-700',
    banner: 'bg-gray-50 border-gray-200 text-gray-800',
    label: 'AWAITING ANALYSIS',
  },
};

export function outcomeStyle(outcome?: string) {
  return OUTCOME_STYLES[outcome || 'PENDING'] || OUTCOME_STYLES.PENDING;
}

export const DECISION_STYLES: Record<string, string> = {
  ACCEPT: 'bg-green-100 text-[#166534]',
  REJECT: 'bg-red-100 text-[#991B1B]',
  MANUAL_REVIEW: 'bg-amber-100 text-[#854D0E]',
};

export function decisionLabel(decision?: string | null): string {
  return { ACCEPT: 'Accept', REJECT: 'Reject', MANUAL_REVIEW: 'Manual review' }[decision || ''] || decision || '—';
}
