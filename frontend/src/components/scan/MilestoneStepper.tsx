/**
 * Stepper colors — global.css :root:
 * Pending: surface + line + ink-mute
 * Active: --green-600 (pulse uses currentColor)
 * Done/success accents: --green-700 (+ check stroke green-700)
 * Connector line: --line
 */

import React from "react";
import type { ScanStep } from "../../types/scan";

type MilestoneStepperProps = {
  steps: ScanStep[];
  /** Pass-through — labels come from hooks only. */
  is3D?: boolean;
};

function CheckIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden>
      <path
        d="M2.5 6.2L4.8 8.5L9.5 3.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function MilestoneStepper({ steps, is3D: _is3D }: MilestoneStepperProps) {
  return (
    <div className="ns-card-frame ns-bg-card-soft ios-soft-shadow rounded-ios-lg font-ios" style={{ marginBottom: 16, padding: 0 }}>
      <div className="ios-pad-card">
        <div className="text-ios-footnote font-semibold font-ios text-ns-muted" style={{ marginBottom: 12 }}>
          Pipeline
        </div>
        <div style={{ position: "relative", paddingLeft: 34 }}>
          <div
            aria-hidden
            style={{
              position: "absolute",
              left: 10,
              top: 14,
              bottom: 14,
              width: 1,
              background: "var(--line)",
            }}
          />
          <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 14 }}>
            {steps.map((step, index) => {
              const dotPending = step.state === "pending";
              const dotActive = step.state === "active";
              const dotDone = step.state === "done";
              let dotClass = "milestone-dot ";
              if (dotPending) dotClass += "milestone-dot--pending";
              if (dotActive) dotClass += "milestone-dot--active ios-animated milestone-dot--active-pulse";
              if (dotDone) dotClass += "milestone-dot--done";

              const nameMuted = dotPending ? "text-ns-muted" : dotActive ? "text-ns-primary-strong" : "text-ns-success";
              return (
                <li key={step.id} style={{ position: "relative", display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <div style={{ width: 22, flexShrink: 0, display: "flex", justifyContent: "center", paddingTop: 2 }}>
                    <span className={dotClass}>{dotDone ? <CheckIcon /> : null}</span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0, paddingRight: 4 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        gap: 8,
                      }}
                    >
                      <div className={`text-ios-footnote font-semibold font-ios ios-animated ${nameMuted}`}>
                        {index + 1}. {step.name}
                      </div>
                      {dotDone && step.elapsedMs !== undefined ? (
                        <div className="text-ios-caption2 font-medium font-ios text-ns-success" style={{ flexShrink: 0, paddingTop: 2, fontVariantNumeric: "tabular-nums" }}>
                          {(step.elapsedMs / 1000).toFixed(1)}s
                        </div>
                      ) : null}
                    </div>
                    <div className="text-ios-caption2 font-ios text-ns-muted" style={{ marginTop: 2, lineHeight: 1.35 }}>
                      {step.subtitle}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
