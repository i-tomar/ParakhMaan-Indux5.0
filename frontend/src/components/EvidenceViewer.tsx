'use client';

import React, { useState, useEffect } from 'react';
import { PackageImage, ComplianceResult, Declaration } from '@/lib/types';
import { Eye, Layers, Flame, Image as ImageIcon, Loader2, Sparkles } from 'lucide-react';
import { api, getStorageUrl } from '@/lib/api';
import { ProtectedImg } from '@/components/ProtectedImg';

interface EvidenceViewerProps {
  inspectionId?: string;
  images: PackageImage[];
  selectedResult?: ComplianceResult | null;
  declarations?: Declaration[];
}

export default function EvidenceViewer({ inspectionId, images, selectedResult, declarations = [] }: EvidenceViewerProps) {
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [viewMode, setViewMode] = useState<'boxes' | 'heatmap' | 'original'>('boxes');
  const [heatmapUrl, setHeatmapUrl] = useState<string | null>(null);
  const [loadingHeatmap, setLoadingHeatmap] = useState(false);
  const [naturalDims, setNaturalDims] = useState<{ width: number; height: number }>({ width: 800, height: 600 });
  const [hoveredSpan, setHoveredSpan] = useState<{ text: string; confidence: number; x: number; y: number } | null>(null);

  const activeImage = images?.[activeImageIndex] || images?.[0];
  
  // Format image source URL
  const imageUrl = getStorageUrl(activeImage?.file_path || '');

  // Load heatmap when switching to heatmap view mode
  useEffect(() => {
    if (viewMode === 'heatmap' && inspectionId && activeImage?.id) {
      setLoadingHeatmap(true);
      api.getImageHeatmap(inspectionId, activeImage.id)
        .then((res) => {
          setHeatmapUrl(res.heatmap_data_url);
        })
        .catch((err) => {
          console.error('Error fetching heatmap:', err);
        })
        .finally(() => {
          setLoadingHeatmap(false);
        });
    }
  }, [viewMode, inspectionId, activeImage?.id]);

  if (!images || images.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-[#e6e6e6] p-8 text-center text-[#615d59]">
        <Layers className="w-10 h-10 mx-auto mb-2 text-[#a39e98]" />
        <p className="text-sm font-medium">No surface images uploaded yet</p>
        <p className="text-xs text-[#a39e98] mt-1">Upload or capture package surfaces to inspect evidence overlays.</p>
      </div>
    );
  }

  // Active highlights
  const highlightedBbox = selectedResult?.evidence?.bbox;
  const ocrSpans = activeImage?.ocr_raw_data || [];

  return (
    <div className="bg-white rounded-xl border border-[#e6e6e6] overflow-hidden elevation-0 flex flex-col">
      {/* Header & Surface Switcher */}
      <div className="px-5 py-3 border-b border-[#e6e6e6] bg-[#f6f5f4] flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Eye className="w-4 h-4 text-[#0075de]" />
          <h3 className="text-xs font-bold text-[#000000] uppercase tracking-wider">
            Package Evidence & Attention Locator
          </h3>
        </div>

        {/* View Mode Controls */}
        <div className="flex items-center bg-[#e6e6e6] p-0.5 rounded-lg text-xs font-semibold">
          <button
            onClick={() => setViewMode('original')}
            className={`px-2.5 py-1 rounded-md flex items-center gap-1 transition-all ${
              viewMode === 'original' ? 'bg-white text-black shadow-xs' : 'text-[#615d59] hover:text-black'
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5" />
            <span>Photo</span>
          </button>
          <button
            onClick={() => setViewMode('boxes')}
            className={`px-2.5 py-1 rounded-md flex items-center gap-1 transition-all ${
              viewMode === 'boxes' ? 'bg-white text-[#0075de] shadow-xs' : 'text-[#615d59] hover:text-black'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>OCR Mesh</span>
          </button>
          <button
            onClick={() => setViewMode('heatmap')}
            className={`px-2.5 py-1 rounded-md flex items-center gap-1 transition-all ${
              viewMode === 'heatmap' ? 'bg-white text-[#d9381e] shadow-xs' : 'text-[#615d59] hover:text-black'
            }`}
          >
            <Flame className="w-3.5 h-3.5 text-[#d9381e]" />
            <span>Thermal Heatmap</span>
          </button>
        </div>

        {/* Surface Tabs */}
        <div className="flex items-center gap-1">
          {images.map((img, idx) => (
            <button
              key={img.id || idx}
              onClick={() => {
                setActiveImageIndex(idx);
                setHeatmapUrl(null);
              }}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                activeImageIndex === idx
                  ? 'bg-white text-[#0075de] shadow-xs border border-[#e6e6e6]'
                  : 'text-[#615d59] hover:bg-[#e6e6e6] hover:text-[#000000]'
              }`}
            >
              {img.surface_type}
            </button>
          ))}
        </div>
      </div>

      {/* Main Image Stage with Pixel-Perfect SVG & Heatmap Overlays */}
      <div className="relative bg-[#0f172a] min-h-[380px] max-h-[460px] flex items-center justify-center p-4 select-none overflow-hidden">
        <div className="relative inline-block max-w-full max-h-[400px]">
          {/* Base / Heatmap Image */}
          {viewMode === 'heatmap' && heatmapUrl ? (
            <img
              src={heatmapUrl}
              alt="Thermal Attention Heatmap"
              onLoad={(e) => {
                const nw = e.currentTarget.naturalWidth || 800;
                const nh = e.currentTarget.naturalHeight || 600;
                setNaturalDims({ width: nw, height: nh });
              }}
              className="max-h-[400px] w-auto object-contain rounded-lg border border-red-500/30 shadow-lg block"
            />
          ) : (
            <ProtectedImg
              src={imageUrl}
              alt={`${activeImage?.surface_type} Package Surface`}
              onLoad={(e) => {
                const nw = e.currentTarget.naturalWidth || 800;
                const nh = e.currentTarget.naturalHeight || 600;
                setNaturalDims({ width: nw, height: nh });
              }}
              className="max-h-[400px] w-auto object-contain rounded-lg border border-white/10 block"
            />
          )}

          {/* Loading spinner for heatmap */}
          {viewMode === 'heatmap' && loadingHeatmap && (
            <div className="absolute inset-0 bg-black/60 backdrop-blur-xs flex flex-col items-center justify-center rounded-lg text-white">
              <Loader2 className="w-7 h-7 animate-spin text-[#d9381e] mb-2" />
              <p className="text-xs font-semibold">Computing OpenCV Thermal Heatmap...</p>
            </div>
          )}

          {/* Pixel-Perfect Dynamic SVG Bounding Boxes Overlay */}
          {viewMode === 'boxes' && (
            <svg
              className="absolute inset-0 w-full h-full pointer-events-auto"
              viewBox={`0 0 ${naturalDims.width} ${naturalDims.height}`}
              preserveAspectRatio="none"
            >
              {/* 1. Show all detected OCR spans aligned to exact native image resolution */}
              {ocrSpans.map((span, sIdx) => {
                if (!span.bbox || span.bbox.length < 4) return null;
                const [x1, y1, x2, y2] = span.bbox;
                const w = Math.max(x2 - x1, 4);
                const h = Math.max(y2 - y1, 4);
                return (
                  <g
                    key={`span-${sIdx}`}
                    className="cursor-pointer group"
                    onMouseEnter={() => setHoveredSpan({ text: span.text, confidence: span.confidence, x: x1, y: y1 })}
                    onMouseLeave={() => setHoveredSpan(null)}
                  >
                    <rect
                      x={x1}
                      y={y1}
                      width={w}
                      height={h}
                      fill="rgba(0, 117, 222, 0.12)"
                      stroke="#0075de"
                      strokeWidth={Math.max(1.5, naturalDims.width / 700)}
                      strokeDasharray="4 2"
                      rx="3"
                    />
                  </g>
                );
              })}

              {/* 2. Highlight selected compliance rule evidence */}
              {highlightedBbox && highlightedBbox.length >= 4 && (
                <g>
                  <rect
                    x={highlightedBbox[0] - 4}
                    y={highlightedBbox[1] - 4}
                    width={Math.max(highlightedBbox[2] - highlightedBbox[0] + 8, 8)}
                    height={Math.max(highlightedBbox[3] - highlightedBbox[1] + 8, 8)}
                    fill="rgba(26, 174, 57, 0.25)"
                    stroke="#1aae39"
                    strokeWidth={Math.max(3, naturalDims.width / 400)}
                    rx="5"
                    className="animate-pulse"
                  />
                  <rect
                    x={highlightedBbox[0]}
                    y={Math.max(highlightedBbox[1] - 26, 0)}
                    width={Math.max(160, naturalDims.width / 6)}
                    height={22}
                    fill="#1aae39"
                    rx="3"
                  />
                  <text
                    x={highlightedBbox[0] + 6}
                    y={Math.max(highlightedBbox[1] - 10, 14)}
                    fill="#ffffff"
                    fontSize="11"
                    fontWeight="bold"
                    fontFamily="sans-serif"
                  >
                    {selectedResult?.field?.toUpperCase()}
                  </text>
                </g>
              )}
            </svg>
          )}

          {/* Interactive Span Hover Tooltip */}
          {hoveredSpan && (
            <div className="absolute top-2 left-2 z-30 bg-black/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-blue-400/40 text-white text-xs shadow-xl pointer-events-none max-w-xs">
              <p className="font-semibold text-blue-300 text-[11px] truncate">{hoveredSpan.text}</p>
              <p className="text-[10px] text-white/70">OCR Confidence: {Math.round(hoveredSpan.confidence * 100)}%</p>
            </div>
          )}
        </div>

        {/* Heatmap Color Scale Legend */}
        {viewMode === 'heatmap' && (
          <div className="absolute bottom-3 left-3 bg-black/75 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 text-white text-[10px] flex items-center gap-2">
            <span className="text-blue-300 font-semibold">Low Density</span>
            <div className="w-24 h-2 rounded-full bg-gradient-to-r from-blue-600 via-yellow-400 to-red-600 border border-white/20" />
            <span className="text-red-400 font-semibold">High Attention</span>
          </div>
        )}

        {/* Floating Span Counter */}
        <div className="absolute bottom-3 right-3 flex items-center gap-2 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/10 text-white text-[11px]">
          <span className="text-white/80 font-medium">
            {ocrSpans.length} Text Blocks Localized
          </span>
        </div>
      </div>

      {/* Selected Evidence Inspector Strip */}
      {selectedResult ? (
        <div className="p-4 bg-[#f6f5f4] border-t border-[#e6e6e6] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[#000000]">{selectedResult.rule_id}</span>
              <span className="text-xs text-[#615d59]">({selectedResult.field.replace('_', ' ').toUpperCase()})</span>
              <span
                className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                  selectedResult.outcome === 'PASS'
                    ? 'bg-green-100 text-[#166534]'
                    : selectedResult.outcome === 'REVIEW'
                    ? 'bg-amber-100 text-[#854D0E]'
                    : 'bg-red-100 text-[#991B1B]'
                }`}
              >
                {selectedResult.outcome}
              </span>
            </div>
            <p className="text-xs text-[#31302e] mt-1 font-medium">
              {selectedResult.explanation || 'Statutory verification recorded.'}
            </p>
          </div>

          <div className="text-left sm:text-right shrink-0">
            <p className="text-[10px] text-[#615d59]">Confidence</p>
            <p className="text-xs font-bold text-[#0075de]">
              {Math.round((selectedResult.confidence !== undefined && selectedResult.confidence !== null ? selectedResult.confidence : 0.0) * 100)}% Match
            </p>
          </div>
        </div>
      ) : (
        <div className="p-3 bg-[#f6f5f4] border-t border-[#e6e6e6] text-center text-xs text-[#615d59]">
          Click any row in the Compliance Matrix below to highlight its bounding box or switch to <b>Thermal Heatmap</b> for attention saliency.
        </div>
      )}
    </div>
  );
}
