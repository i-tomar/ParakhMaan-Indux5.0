'use client';

import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { DefectDetection } from '@/lib/types';
import { defectColor, defectLabel } from '@/lib/defects';
import { ProtectedImg } from '@/components/ProtectedImg';

interface DefectBoxesProps {
  width: number;
  height: number;
  detections: DefectDetection[];
  selectedId?: string | null;
  onSelect?: (d: DefectDetection) => void;
  showLabels?: boolean;
  className?: string;
}

/**
 * SVG layer in image pixel coordinates. `xMidYMid meet` scales it exactly like
 * `object-contain`, so it lines up over both <img> and letterboxed <video> elements.
 */
export function DefectBoxes({
  width,
  height,
  detections,
  selectedId,
  onSelect,
  showLabels = true,
  className = '',
}: DefectBoxesProps) {
  const stroke = Math.max(2, Math.round(Math.min(width, height) / 250));
  const fontSize = Math.max(12, Math.round(Math.min(width, height) / 40));

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className={`absolute inset-0 w-full h-full ${onSelect ? '' : 'pointer-events-none'} ${className}`}
    >
      {detections.map((d, idx) => {
        if (!d.bbox || d.bbox.length !== 4) return null;
        const [x1, y1, x2, y2] = d.bbox;
        const color = defectColor(d.defect_type);
        const isSelected = !!selectedId && d.id === selectedId;
        const rejected = d.reviewer_status === 'REJECTED';
        const label = `${defectLabel(d.defect_type)} ${Math.round(d.confidence * 100)}%`;
        const labelY = y1 - fontSize * 0.4 > fontSize ? y1 - fontSize * 0.4 : y2 + fontSize * 1.1;
        return (
          <g
            key={d.id || idx}
            onClick={onSelect ? () => onSelect(d) : undefined}
            className={onSelect ? 'cursor-pointer' : undefined}
            opacity={rejected ? 0.35 : 1}
          >
            <rect
              x={x1}
              y={y1}
              width={x2 - x1}
              height={y2 - y1}
              fill={color}
              fillOpacity={isSelected ? 0.28 : 0.12}
              stroke={color}
              strokeWidth={isSelected ? stroke * 2 : stroke}
              strokeDasharray={rejected ? `${stroke * 3} ${stroke * 2}` : undefined}
              rx={stroke}
            />
            {showLabels && (
              <g>
                <rect
                  x={x1}
                  y={labelY - fontSize}
                  width={label.length * fontSize * 0.58 + fontSize * 0.6}
                  height={fontSize * 1.3}
                  fill={color}
                  rx={fontSize * 0.2}
                />
                <text
                  x={x1 + fontSize * 0.3}
                  y={labelY}
                  fill="#ffffff"
                  fontSize={fontSize}
                  fontWeight={700}
                  fontFamily="Inter, Segoe UI, sans-serif"
                >
                  {label}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

interface DefectOverlayProps {
  imageUrl: string;
  detections: DefectDetection[];
  selectedId?: string | null;
  onSelect?: (d: DefectDetection) => void;
  caption?: string;
}

export default function DefectOverlay({ imageUrl, detections, selectedId, onSelect, caption }: DefectOverlayProps) {
  const [dims, setDims] = useState<{ width: number; height: number } | null>(null);
  const [showBoxes, setShowBoxes] = useState(true);
  const [showLabels, setShowLabels] = useState(true);

  return (
    <div className="bg-white rounded-xl border border-[#e6e6e6] overflow-hidden elevation-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#e6e6e6] bg-[#f6f5f4]">
        <span className="text-xs font-semibold text-[#31302e] truncate">{caption || 'Defect Localisation'}</span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setShowLabels((v) => !v)}
            disabled={!showBoxes}
            className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-white border border-[#e6e6e6] text-[#31302e] hover:bg-[#f6f5f4] disabled:opacity-40"
          >
            {showLabels ? 'Hide labels' : 'Show labels'}
          </button>
          <button
            type="button"
            onClick={() => setShowBoxes((v) => !v)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-white border border-[#e6e6e6] text-[#31302e] hover:bg-[#f6f5f4]"
          >
            {showBoxes ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            {showBoxes ? 'Hide boxes' : 'Show boxes'}
          </button>
        </div>
      </div>

      <div className="bg-[#1b1b1b] flex items-center justify-center p-2">
        <div className="relative inline-block max-w-full">
          <ProtectedImg
            src={imageUrl}
            alt={caption || 'Inspected surface'}
            className="block max-w-full max-h-[520px] w-auto h-auto"
            onLoad={(e) =>
              setDims({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })
            }
          />
          {dims && showBoxes && (
            <DefectBoxes
              width={dims.width}
              height={dims.height}
              detections={detections}
              selectedId={selectedId}
              onSelect={onSelect}
              showLabels={showLabels}
            />
          )}
        </div>
      </div>
    </div>
  );
}
