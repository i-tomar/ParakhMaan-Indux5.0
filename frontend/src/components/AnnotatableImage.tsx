'use client';

import React, { useRef, useState } from 'react';
import { DefectDetection } from '@/lib/types';
import { DefectBoxes } from '@/components/DefectOverlay';

interface AnnotatableImageProps {
  imageUrl: string;
  detections: DefectDetection[];
  selectedId?: string | null;
  onSelect?: (d: DefectDetection) => void;
  /** When set, dragging on the image draws a box (reported in original image pixels). */
  drawEnabled?: boolean;
  onDraw?: (bbox: [number, number, number, number]) => void;
  drawColor?: string;
}

type Point = { x: number; y: number };

/** Image with detection boxes and click-and-drag box drawing for reviewer annotations. */
export default function AnnotatableImage({
  imageUrl,
  detections,
  selectedId,
  onSelect,
  drawEnabled = false,
  onDraw,
  drawColor = '#16a34a',
}: AnnotatableImageProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const [start, setStart] = useState<Point | null>(null);
  const [current, setCurrent] = useState<Point | null>(null);

  const toImage = (clientX: number, clientY: number): Point | null => {
    const img = imgRef.current;
    if (!img || !natural) return null;
    const rect = img.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * natural.width;
    const y = ((clientY - rect.top) / rect.height) * natural.height;
    return { x: Math.max(0, Math.min(natural.width, x)), y: Math.max(0, Math.min(natural.height, y)) };
  };

  const finish = () => {
    if (start && current && onDraw) {
      const x1 = Math.min(start.x, current.x);
      const y1 = Math.min(start.y, current.y);
      const x2 = Math.max(start.x, current.x);
      const y2 = Math.max(start.y, current.y);
      if (x2 - x1 >= 4 && y2 - y1 >= 4) onDraw([Math.round(x1), Math.round(y1), Math.round(x2), Math.round(y2)]);
    }
    setStart(null);
    setCurrent(null);
  };

  return (
    <div className="bg-[#1b1b1b] flex items-center justify-center p-2 rounded-xl">
      <div className="relative inline-block max-w-full select-none">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imgRef}
          src={imageUrl}
          alt="Image under review"
          draggable={false}
          className="block max-w-full max-h-[560px] w-auto h-auto"
          onLoad={(e) => setNatural({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
        />
        {natural && (
          <DefectBoxes
            width={natural.width}
            height={natural.height}
            detections={detections}
            selectedId={selectedId}
            onSelect={drawEnabled ? undefined : onSelect}
          />
        )}
        {natural && drawEnabled && (
          <div
            className="absolute inset-0 cursor-crosshair"
            onPointerDown={(e) => {
              (e.target as HTMLElement).setPointerCapture(e.pointerId);
              const p = toImage(e.clientX, e.clientY);
              setStart(p);
              setCurrent(p);
            }}
            onPointerMove={(e) => start && setCurrent(toImage(e.clientX, e.clientY))}
            onPointerUp={finish}
            onPointerCancel={() => {
              setStart(null);
              setCurrent(null);
            }}
          >
            {start && current && (
              <svg viewBox={`0 0 ${natural.width} ${natural.height}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none">
                <rect
                  x={Math.min(start.x, current.x)}
                  y={Math.min(start.y, current.y)}
                  width={Math.abs(current.x - start.x)}
                  height={Math.abs(current.y - start.y)}
                  fill={drawColor}
                  fillOpacity={0.15}
                  stroke={drawColor}
                  strokeWidth={Math.max(2, Math.round(Math.min(natural.width, natural.height) / 250))}
                  strokeDasharray="8 4"
                />
              </svg>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
