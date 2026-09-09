/**
 * PACS workstation chrome — palette from global.css :root only.
 * No synthetic lesion markers on pixels; overlays = grid, crosshair, sweep, optional API saliency only.
 */

import React, { useEffect, useRef, useState } from "react";
import type { Phase, ScanFindings } from "../../types/scan";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

export type ViewportMode = "idle" | "scanning" | "complete";

function pipelineMode(phase: Phase): ViewportMode {
  if (phase === "idle") return "idle";
  if (phase === "complete") return "complete";
  if (phase === "error") return "idle";
  return "scanning";
}

type ScanViewportProps = {
  phase: Phase;
  file: File | null;
  sliceIndex: number;
  snrValue: number;
  progressPct: number;
  findings: ScanFindings | null;
  isSegmentationModel: boolean;
  /** Real study / file labels — never invent a patient ID. */
  studyLabel?: string;
  fileLabel?: string;
  /** From clinical context when complete, e.g. "M · 24y". */
  subjectLabel?: string;
};

/** Lightweight acquisition placeholder — path outline only (no ellipses / spot shapes). */
function PlaceholderBrain() {
  return (
    <svg
      width="38%"
      height="38%"
      viewBox="0 0 100 118"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      style={{ maxWidth: 200, opacity: 0.2 }}
    >
      <path
        d="M50 14c-22 8-34 28-34 52 0 18 14 38 34 42 20-4 34-24 34-42 0-24-12-44-34-52z"
        stroke="var(--ink-mute)"
        strokeWidth={1.2}
        strokeLinejoin="round"
      />
      <path
        d="M36 62c6-14 28-14 34 2M44 82c12-8 26-8 32 10"
        stroke="var(--ink-mute)"
        strokeWidth={0.85}
        strokeLinecap="round"
        opacity={0.7}
      />
    </svg>
  );
}

/** Alpha as color-mix on primary (no arbitrary RGB hex beyond letterbox below). */
function primaryMix(alpha: number): string {
  const pct = Math.round(Math.min(1, Math.max(0, alpha)) * 100);
  return `color-mix(in srgb, var(--green-600) ${pct}%, transparent)`;
}

export default function ScanViewport({
  phase,
  file,
  sliceIndex,
  snrValue,
  progressPct,
  findings,
  isSegmentationModel,
  studyLabel,
  fileLabel,
  subjectLabel,
}: ScanViewportProps) {
  const reduced = usePrefersReducedMotion();
  const mode = pipelineMode(phase);
  const isError = phase === "error";
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const prevUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!file) {
      if (prevUrlRef.current) {
        URL.revokeObjectURL(prevUrlRef.current);
        prevUrlRef.current = null;
      }
      setImageUrl(null);
      return;
    }
    if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current);
    prevUrlRef.current = URL.createObjectURL(file);
    setImageUrl(prevUrlRef.current);
  }, [file]);

  useEffect(() => {
    return () => {
      if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current);
      prevUrlRef.current = null;
    };
  }, []);

  const salMapB64 =
    findings?.salMapB64 && String(findings.salMapB64).trim() !== "" ? findings.salMapB64 : null;

  const showSaliencyOverlay = phase === "complete" && Boolean(salMapB64);

  const isScanning = mode === "scanning" && Boolean(imageUrl) && !isError;
  const showScanChrome = Boolean(imageUrl) && (mode === "scanning" || mode === "complete" || isError);

  const slicesTotal = isSegmentationModel ? 96 : 48;
  const safeSliceIdx = Math.min(sliceIndex, slicesTotal);
  const modalityLabel = isSegmentationModel ? "FLAIR · AX" : "T1 · AX";

  function cornerHud(c: "tl" | "tr" | "bl" | "br"): React.CSSProperties {
    const pad = 10;
    const base: React.CSSProperties = {
      position: "absolute",
      zIndex: 8,
      fontSize: "10.5px",
      lineHeight: 1.5,
      fontFamily: '"SF Mono", Menlo, Consolas, monospace',
      color: "var(--green-400)",
      textShadow: "0 0 4px rgba(0, 0, 0, 0.8)",
      letterSpacing: "0.3px",
      fontWeight: 500,
      pointerEvents: "none",
      maxWidth: "42%",
    };
    if (c === "tl") return { ...base, top: pad, left: pad, textAlign: "left" };
    if (c === "tr") return { ...base, top: pad, right: pad, textAlign: "right" };
    if (c === "bl") return { ...base, bottom: pad, left: pad, textAlign: "left" };
    return { ...base, bottom: pad, right: pad, textAlign: "right" };
  }

  const hudLabel: React.CSSProperties = {
    display: "block",
    fontSize: "9px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    color: primaryMix(0.7),
    marginBottom: 2,
  };

  const hudValue: React.CSSProperties = {
    fontSize: "10.5px",
    color: "var(--green-400)",
  };

  const gridOverlayStyle: React.CSSProperties = {
    position: "absolute",
    inset: 0,
    zIndex: 2,
    pointerEvents: "none",
    backgroundImage: `
      linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)
    `,
    backgroundSize: "32px 32px",
    opacity: isScanning ? 1 : 0,
    transition: "opacity 0.4s ease",
  };

  const sweepPackOuter = (moving: boolean): React.CSSProperties => ({
    position: "absolute",
    left: 0,
    right: 0,
    pointerEvents: "none",
    zIndex: 5,
    overflow: "visible",
    ...(moving && !reduced
      ? { animation: "ios-sweep 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite" }
      : { top: "42%", animation: "none" }),
  });

  const sweepGlowStyle: React.CSSProperties = {
    position: "absolute",
    left: 0,
    right: 0,
    top: "-40px",
    height: "80px",
    pointerEvents: "none",
    background: `linear-gradient(180deg,
      transparent 0%,
      ${primaryMix(0.14)} 45%,
      ${primaryMix(0.28)} 55%,
      ${primaryMix(0.14)} 65%,
      transparent 100%
    )`,
  };

  const sweepLineStyle: React.CSSProperties = {
    position: "relative",
    width: "100%",
    height: "2px",
    pointerEvents: "none",
    background: `linear-gradient(90deg,
      transparent 0%,
      var(--green-600) 15%,
      var(--green-400) 50%,
      var(--green-600) 85%,
      transparent 100%
    )`,
    boxShadow: `0 0 8px ${primaryMix(0.6)}`,
  };

  let statusLabel = "idle";
  if (isError) statusLabel = "error";
  else if (isScanning && imageUrl) statusLabel = "analyzing";
  else if (mode === "complete" && imageUrl) statusLabel = "complete";
  else if (imageUrl) statusLabel = "preview";

  const statusColor =
    isError ? "var(--green-900)" : isScanning ? "var(--green-400)" : "var(--green-400)";
  const dotBg = isError ? "var(--green-900)" : "var(--green-600)";

  const sequenceReadout = isSegmentationModel ? "FLAIR · TE 120 · TR 9000" : "T1 · SE · TR 500";

  let progressCaption = "Preview";
  if (!file) progressCaption = "No scan loaded";
  if (isScanning) progressCaption = "Pipeline active";
  if (mode === "complete") progressCaption = "Acquisition complete";
  if (isError) progressCaption = "Pipeline halted";

  const toolbarId = studyLabel || fileLabel || "No scan attached";

  return (
    <div className="scan-viewport-shell ns-bg-card-solid ns-card-frame rounded-ios-lg ios-soft-shadow overflow-hidden scan-pacs-root">
      <div
        className="rounded-t-ios-lg scan-toolbar"
        style={{
          padding: "10px 12px",
          borderBottom: "0.5px solid var(--line)",
          background: "color-mix(in srgb, var(--ink) 3.5%, var(--surface))",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", minWidth: 0 }}>
          {file ? (
            <span
              className="modality-pill"
              style={{
                fontSize: 10,
                fontWeight: 600,
                background: "var(--modern-primary, #09090b)",
                color: "#fff",
                padding: "2px 7px",
                borderRadius: 3,
                letterSpacing: "0.4px",
                flexShrink: 0,
              }}
            >
              {modalityLabel}
            </span>
          ) : null}
          <span
            className="patient-id"
            style={{
              fontSize: 11,
              color: "var(--ink-mute)",
              fontFamily: "Menlo, ui-monospace, SFMono-Regular, monospace",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {toolbarId}
          </span>
        </div>
      </div>

      <div
        className="viewport-wrap"
        style={{
          position: "relative",
          width: "100%",
          paddingBottom: "62%",
          overflow: "hidden",
          background: "#000",
        }}
      >
        <div style={{ position: "absolute", inset: 0 }}>
          {imageUrl ? (
            <img
              src={imageUrl}
              alt="Brain MRI"
              className="ios-animated"
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
                objectPosition: "center",
                display: "block",
                filter: "contrast(1.05) brightness(0.95)",
                zIndex: 1,
              }}
            />
          ) : (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
                padding: 24,
                textAlign: "center",
              }}
            >
              <PlaceholderBrain />
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: "rgba(255,255,255,0.72)",
                  letterSpacing: "-0.01em",
                }}
              >
                No scan loaded
              </div>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", maxWidth: 280, lineHeight: 1.45 }}>
                Attach a file in Step 2, then run inference. The viewer stays empty until a real image is chosen.
              </div>
            </div>
          )}

          {showSaliencyOverlay && salMapB64 ? (
            <img
              src={`data:image/png;base64,${salMapB64}`}
              alt="Grad-CAM saliency overlay"
              className="ios-animated"
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
                opacity: 0.55,
                mixBlendMode: "screen",
                zIndex: 5,
                transition: "opacity 0.6s ease",
                pointerEvents: "none",
              }}
            />
          ) : null}

          {showScanChrome ? (
            <>
              <div aria-hidden style={gridOverlayStyle} />
              <div
                aria-hidden
                className="scan-pacs-crosshair ios-animated"
                style={{
                  position: "absolute",
                  inset: 0,
                  zIndex: 3,
                  pointerEvents: "none",
                  opacity: isScanning ? 1 : 0,
                  transition: "opacity 0.4s ease",
                }}
              />
              {imageUrl && isScanning ? (
                    <div style={sweepPackOuter(!reduced)}>
                      <div style={{ position: "relative", minHeight: "42px" }}>
                        <div style={sweepGlowStyle} />
                        <div style={sweepLineStyle} />
                      </div>
                    </div>
                  ) : null}
            </>
          ) : null}

          {showScanChrome && imageUrl ? (
            <>
              {subjectLabel ? (
                <div style={cornerHud("tl")}>
                  <span style={hudLabel}>Subject</span>
                  <span style={hudValue}>{subjectLabel}</span>
                </div>
              ) : null}
              <div style={cornerHud("tr")}>
                <span style={hudLabel}>Slice</span>
                <span style={hudValue}>
                  {safeSliceIdx} / {slicesTotal}
                </span>
              </div>
              <div style={cornerHud("bl")}>
                <span style={hudLabel}>Sequence</span>
                <span style={hudValue}>{sequenceReadout}</span>
              </div>
              <div style={cornerHud("br")}>
                <span style={hudLabel}>SNR</span>
                <span style={hudValue}>{snrValue.toFixed(2)} dB</span>
              </div>
            </>
          ) : null}

          {imageUrl && (showScanChrome || isError) ? (
            <div
              role="status"
              style={{
                position: "absolute",
                bottom: 14,
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: 9,
                background: "rgba(0,0,0,0.55)",
                backdropFilter: "blur(8px)",
                WebkitBackdropFilter: "blur(8px)",
                padding: "5px 12px",
                borderRadius: 14,
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.6px",
                textTransform: "uppercase",
                color: statusColor,
                border: `0.5px solid ${primaryMix(0.3)}`,
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: dotBg,
                  animation: isScanning && !reduced ? "ios-pulse 1.4s ease infinite" : "none",
                }}
                className={isScanning && !reduced ? "ios-animated" : undefined}
                aria-hidden
              />
              <span>{statusLabel}</span>
            </div>
          ) : null}
        </div>
      </div>

      <div
        className="scan-footer"
        style={{
          padding: "10px 14px",
          background: "var(--surface)",
          borderTop: "0.5px solid var(--line)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: 11,
          color: "var(--ink-mute)",
        }}
      >
        <span>{progressCaption}</span>
        {file ? (
          <>
            <div
              style={{
                flex: 1,
                margin: "0 12px",
                height: 3,
                background: "var(--line)",
                borderRadius: 2,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  background: "var(--modern-primary, #09090b)",
                  width: `${Math.min(100, Math.max(0, progressPct))}%`,
                  transition: reduced ? "none" : "width 0.15s linear",
                  borderRadius: 2,
                }}
              />
            </div>
            <span
              style={{
                fontFeatureSettings: '"tnum"',
                fontWeight: 600,
                color: "var(--ink-mid)",
                minWidth: 36,
                textAlign: "right",
              }}
            >
              {Math.round(progressPct)}%
            </span>
          </>
        ) : (
          <span style={{ fontSize: 11, color: "var(--ink-mute)" }}>Waiting for file</span>
        )}
      </div>

      <style>{`
        .rounded-t-ios-lg.scan-toolbar {
          border-top-left-radius: var(--radius-ios-lg);
          border-top-right-radius: var(--radius-ios-lg);
        }
        .tb-btn {
          font-size: 11px;
          color: var(--ink-mute);
          background: transparent;
          border: 0.5px solid var(--line);
          padding: 4px 8px;
          border-radius: 5px;
          cursor: pointer;
          min-height: 28px;
        }
        .tb-btn:active {
          background: color-mix(in srgb, var(--green-600) 8%, transparent);
        }
        .scan-pacs-crosshair::before {
          content: '';
          position: absolute;
          left: 50%;
          top: 0;
          bottom: 0;
          width: 1px;
          transform: translateX(-0.5px);
          background: ${primaryMix(0.35)};
        }
        .scan-pacs-crosshair::after {
          content: '';
          position: absolute;
          left: 0;
          right: 0;
          top: 50%;
          height: 1px;
          transform: translateY(-0.5px);
          background: ${primaryMix(0.35)};
        }
      `}</style>
    </div>
  );
}
