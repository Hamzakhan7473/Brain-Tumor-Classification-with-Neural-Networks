import React from "react";

/** Persistent banner for Phase B shadow workflows. */
export default function ShadowModeBanner() {
  return (
    <div className="shadow-mode-banner" role="status" aria-live="polite">
      <span className="shadow-mode-banner__icon" aria-hidden>
        ⚠
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="shadow-mode-banner__title">Shadow mode active</div>
        <p className="shadow-mode-banner__body">
          Results are <strong>never</strong> sent to the clinical record. This workspace is for retrospective QA and
          pilot validation only. Do not use for patient care decisions.
        </p>
      </div>
    </div>
  );
}
