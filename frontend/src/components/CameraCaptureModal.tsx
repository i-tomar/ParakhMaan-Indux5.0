'use client';

import React, { useRef, useState, useEffect } from 'react';
import { Camera, RefreshCw, X, Check, FlipHorizontal, AlertTriangle, Radar } from 'lucide-react';
import { LiveFrameResult } from '@/lib/types';
import { DefectBoxes } from '@/components/DefectOverlay';

interface CameraCaptureModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCapture: (base64Data: string, surfaceType: string) => Promise<void>;
  defaultSurface?: string;
  title?: string;
  surfaceOptions?: string[];
  frameHint?: { label: string; hint: string };
  /** Enables continuous real-time detection over the live preview. */
  liveAnalyze?: (base64Data: string) => Promise<LiveFrameResult>;
}

const LIVE_FRAME_MAX_SIDE = 640;

export default function CameraCaptureModal({
  isOpen,
  onClose,
  onCapture,
  defaultSurface = 'FRONT',
  title = 'Live Package Camera Inspection',
  surfaceOptions = ['FRONT', 'BACK', 'SIDE', 'TOP', 'BOTTOM'],
  frameHint,
  liveAnalyze
}: CameraCaptureModalProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment');
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [surfaceType, setSurfaceType] = useState<string>(defaultSurface);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // Live detection loop state
  const liveAnalyzeRef = useRef(liveAnalyze);
  liveAnalyzeRef.current = liveAnalyze;
  const liveCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [liveOn, setLiveOn] = useState(!!liveAnalyze);
  const [liveResult, setLiveResult] = useState<LiveFrameResult | null>(null);
  const [liveFps, setLiveFps] = useState<number | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const hasLive = !!liveAnalyze;

  // Enumerate video devices and prefer physical camera over OBS/Virtual drivers
  const refreshDevices = async () => {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) return;
      const all = await navigator.mediaDevices.enumerateDevices();
      const cams = all.filter((d) => d.kind === 'videoinput');
      setVideoDevices(cams);
      if (cams.length > 0) {
        setSelectedDeviceId((curr) => {
          if (curr && cams.some((c) => c.deviceId === curr)) return curr;
          const physical = cams.find((c) => {
            const l = (c.label || '').toLowerCase();
            return !l.includes('obs') && !l.includes('virtual') && !l.includes('screen') && !l.includes('camo') && !l.includes('droid');
          });
          return (physical || cams[0]).deviceId;
        });
      }
    } catch {}
  };

  useEffect(() => {
    if (isOpen) {
      refreshDevices().then(() => startCamera());
    } else {
      stopCamera();
      setCapturedImage(null);
      setCameraError(null);
      setLiveResult(null);
      setLiveFps(null);
    }
    return () => {
      stopCamera();
    };
  }, [isOpen, facingMode, selectedDeviceId]);

  useEffect(() => {
    if (!hasLive || !liveOn || !isOpen || capturedImage || cameraError) return;
    let cancelled = false;
    let last = performance.now();
    let ema: number | null = null;
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

    const loop = async () => {
      while (!cancelled) {
        const video = videoRef.current;
        const analyze = liveAnalyzeRef.current;
        if (!video || !analyze || video.readyState < 2 || !video.videoWidth) {
          await wait(150);
          continue;
        }
        const scale = Math.min(1, LIVE_FRAME_MAX_SIDE / Math.max(video.videoWidth, video.videoHeight));
        const canvas = liveCanvasRef.current || (liveCanvasRef.current = document.createElement('canvas'));
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
        try {
          const res = await analyze(canvas.toDataURL('image/jpeg', 0.8));
          if (cancelled) break;
          const now = performance.now();
          const instant = 1000 / Math.max(1, now - last);
          last = now;
          ema = ema === null ? instant : ema * 0.8 + instant * 0.2;
          setLiveResult(res);
          setLiveFps(ema);
          setLiveError(null);
        } catch (err) {
          if (cancelled) break;
          setLiveError(err instanceof Error ? err.message : 'Live analysis failed');
          await wait(800);
        }
      }
    };
    loop();
    return () => {
      cancelled = true;
    };
  }, [hasLive, liveOn, isOpen, capturedImage, cameraError]);

  const startCamera = async () => {
    stopCamera();
    setCameraError(null);

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera access not supported on this browser/environment.');
      }

      const constraints: MediaStreamConstraints = {
        video: selectedDeviceId
          ? { deviceId: { exact: selectedDeviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
          : { facingMode: facingMode, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      };

      const mediaStream = await navigator.mediaDevices.getUserMedia(constraints);

      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (err: any) {
      console.error('Camera access error:', err);
      setCameraError(err.message || 'Unable to access camera device. Please ensure permissions are granted.');
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      setStream(null);
    }
  };

  const toggleFacingMode = () => {
    setFacingMode((prev) => (prev === 'environment' ? 'user' : 'environment'));
  };

  const takeSnapshot = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;

    canvas.width = video.videoWidth || 800;
    canvas.height = video.videoHeight || 600;

    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
      setCapturedImage(dataUrl);
    }
  };

  const handleRetake = () => {
    setCapturedImage(null);
  };

  const handleConfirm = async () => {
    if (!capturedImage) return;
    setLoading(true);
    try {
      await onCapture(capturedImage, surfaceType);
      onClose();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
      <div className="bg-white rounded-xl max-w-2xl w-full overflow-hidden elevation-2 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#e6e6e6] bg-[#f6f5f4]">
          <div className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-[#0075de]" />
            <h3 className="font-bold text-sm text-[#000000]">{title}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-[#615d59] hover:bg-[#e6e6e6] hover:text-[#000000] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Surface and Camera Device Selection */}
        <div className="px-5 py-2.5 bg-white border-b border-[#e6e6e6] flex items-center justify-between flex-wrap gap-2">
          {videoDevices.length > 1 && (
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-[#31302e]">Camera:</span>
              <select
                className="text-xs px-2 py-1 rounded border border-[#e6e6e6] bg-white outline-none max-w-[200px]"
                value={selectedDeviceId}
                onChange={(e) => setSelectedDeviceId(e.target.value)}
              >
                {videoDevices.map((d, i) => (
                  <option key={d.deviceId || i} value={d.deviceId}>
                    {d.label || `Camera ${i + 1}`}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="text-xs font-semibold text-[#31302e]">Surface:</span>
            {surfaceOptions.map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setSurfaceType(st)}
                className={`px-3 py-1 text-xs rounded-full font-medium transition-all ${
                  surfaceType === st
                    ? 'bg-[#0075de] text-white shadow-xs'
                    : 'bg-[#f6f5f4] text-[#31302e] hover:bg-[#e6e6e6]'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        {/* Viewport Area */}
        <div className="relative bg-[#000000] aspect-4/3 flex items-center justify-center overflow-hidden">
          {cameraError ? (
            <div className="p-6 text-center max-w-md text-white">
              <AlertTriangle className="w-10 h-10 text-[#dd5b00] mx-auto mb-3" />
              <p className="text-sm font-semibold mb-1">Camera Device Unavailable</p>
              <p className="text-xs text-[#a39e98] mb-4">{cameraError}</p>
              <button
                onClick={startCamera}
                className="px-4 py-2 bg-[#0075de] text-white text-xs font-semibold rounded-full"
              >
                Retry Connection
              </button>
            </div>
          ) : capturedImage ? (
            <img src={capturedImage} alt="Captured preview" className="w-full h-full object-contain" />
          ) : (
            <>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-contain"
              />
              {/* Overlay Alignment Grid */}
              <div className="absolute inset-8 border border-white/40 rounded-lg pointer-events-none flex flex-col justify-between p-3">
                <span className="text-[10px] text-white/80 font-mono tracking-widest bg-black/40 px-2 py-0.5 rounded-sm self-start">
                  {frameHint?.label ?? `${surfaceType} SURFACE PDP BOUNDARY`}
                </span>
                <span className="text-[10px] text-white/70 font-mono self-end">
                  {frameHint?.hint ?? 'Align MRP & Net Qty inside frame'}
                </span>
              </div>

              {/* Real-time detection overlay + HUD */}
              {hasLive && liveOn && liveResult && (
                <DefectBoxes
                  width={liveResult.image_size[0]}
                  height={liveResult.image_size[1]}
                  detections={liveResult.detections}
                />
              )}
              {hasLive && liveOn && (
                <div className="absolute top-2 right-2 flex flex-col items-end gap-1 pointer-events-none">
                  <span className="flex items-center gap-1.5 text-[10px] font-mono font-bold text-white bg-black/60 px-2 py-1 rounded-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                    LIVE {liveFps !== null ? `${liveFps.toFixed(1)} FPS` : '…'}
                    {liveResult ? ` · ${liveResult.latency_ms} ms` : ''}
                  </span>
                  {liveResult && (
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-1 rounded-sm ${
                        liveResult.detections.length === 0
                          ? 'bg-green-600/80 text-white'
                          : liveResult.outcome === 'DEFECTIVE'
                          ? 'bg-red-600/85 text-white'
                          : 'bg-amber-500/85 text-white'
                      }`}
                    >
                      {liveResult.detections.length === 0
                        ? 'NO DEFECTS'
                        : `${liveResult.detections.length} DEFECT${liveResult.detections.length > 1 ? 'S' : ''} · ${liveResult.outcome}`}
                    </span>
                  )}
                  {liveError && (
                    <span className="text-[10px] font-mono text-white bg-red-700/80 px-2 py-1 rounded-sm max-w-[220px] truncate">
                      {liveError}
                    </span>
                  )}
                </div>
              )}
            </>
          )}

          <canvas ref={canvasRef} className="hidden" />
        </div>

        {/* Footer Actions */}
        <div className="px-5 py-4 bg-[#f6f5f4] border-t border-[#e6e6e6] flex items-center justify-between">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={toggleFacingMode}
              disabled={!!capturedImage || !!cameraError}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-[#31302e] hover:bg-[#e6e6e6] disabled:opacity-40 transition-colors"
            >
              <FlipHorizontal className="w-4 h-4" />
              <span>Switch Camera ({facingMode === 'environment' ? 'Rear' : 'Front'})</span>
            </button>
            {hasLive && (
              <button
                type="button"
                onClick={() => {
                  setLiveOn((v) => !v);
                  setLiveResult(null);
                  setLiveFps(null);
                }}
                disabled={!!capturedImage || !!cameraError}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors disabled:opacity-40 ${
                  liveOn ? 'bg-red-50 text-[#991B1B] hover:bg-red-100' : 'text-[#31302e] hover:bg-[#e6e6e6]'
                }`}
              >
                <Radar className="w-4 h-4" />
                <span>{liveOn ? 'Stop Live Detection' : 'Start Live Detection'}</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {capturedImage ? (
              <>
                <button
                  type="button"
                  onClick={handleRetake}
                  className="px-4 py-2 rounded-full text-xs font-medium bg-white text-[#31302e] border border-[#e6e6e6] hover:bg-[#f6f5f4] transition-colors"
                >
                  Retake Photo
                </button>
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-5 py-2 rounded-full text-xs font-semibold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-sm"
                >
                  <Check className="w-4 h-4" />
                  <span>{loading ? 'Processing...' : `Attach as ${surfaceType}`}</span>
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={takeSnapshot}
                disabled={!!cameraError}
                className="flex items-center gap-2 px-6 py-2.5 rounded-full text-xs font-bold bg-[#0075de] text-white hover:bg-[#005bab] transition-all shadow-md active:scale-95 disabled:opacity-50"
              >
                <Camera className="w-4 h-4" />
                <span>Capture Snapshot</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
