import React from "react";

/**
 * Persistent, non-dismissible banner for Phase B shadow workflows.
 * Uses existing global.css tokens only.
 */
export default function ShadowModeBanner() {
  return (
    <div
      className="shadow-mode-banner"
      role="status"
      aria-live="polite"
      style={{
        marginBottom: 16,
        padding: "12px 16px",
        borderRadius: 12,
        border: "1px solid rgba(13, 21, 18, 0.22)",
        background: "rgba(13, 21, 18, 0.07)",
        color: "var(--ink)",
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
      }}
    >
      <span aria-hidden style={{ fontSize: 18, lineHeight: 1, color: "var(--green-800)" }}>
        ⚠
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 14, color: "var(--ink)" }}>Shadow mode active</div>
        <p style={{ marginTop: 4, fontSize: 13, lineHeight: 1.55, color: "var(--ink-mid)" }}>
          Results are <strong>never</strong> sent to the clinical record. This workspace is for retrospective QA and
          pilot validation only. Do not use for patient care decisions.
        </p>
      </div>
    </div>
  );
}
