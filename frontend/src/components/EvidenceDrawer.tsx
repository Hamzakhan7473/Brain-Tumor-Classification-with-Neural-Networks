import React from "react";

export type EvidenceCitation = {
  id: string;
  title?: string;
  source?: string;
  snippet: string;
  score?: number;
};

export default function EvidenceDrawer(props: {
  open: boolean;
  title?: string;
  citations: EvidenceCitation[];
  onClose: () => void;
}) {
  if (!props.open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        background: "rgba(2, 6, 23, 0.35)",
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={props.onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        style={{
          width: "min(520px, 92vw)",
          height: "100%",
          background: "rgba(255,255,255,0.96)",
          borderLeft: "1px solid var(--line)",
          boxShadow: "-20px 0 60px rgba(5,46,28,0.18)",
          padding: 18,
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.1, color: "var(--ink-mute)" }}>
              Evidence
            </div>
            <div style={{ fontFamily: "var(--serif)", fontSize: 20, letterSpacing: "-0.01em" }}>
              {props.title || "Retrieved citations"}
            </div>
          </div>
          <button className="btn" type="button" onClick={props.onClose}>
            Close
          </button>
        </div>

        <p style={{ marginTop: 10, color: "var(--ink-mute)", fontSize: 13 }}>
          These citations are designed to be PageIndex-ready: section-style titles, sources, and traceable snippets.
        </p>

        <div style={{ marginTop: 14, display: "grid", gap: 10 }}>
          {props.citations.map((c, idx) => (
            <div key={c.id} className="card" style={{ padding: "12px 14px" }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                <div style={{ fontWeight: 800 }}>
                  [{idx + 1}] {c.title || "Section"}
                </div>
                {typeof c.score === "number" ? (
                  <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>{c.score.toFixed(3)}</div>
                ) : null}
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-mute)", marginTop: 2 }}>{c.source || c.id}</div>
              <pre
                style={{
                  marginTop: 10,
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.5,
                  fontSize: 13,
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                  background: "rgba(240,250,246,0.9)",
                  border: "1px solid var(--line)",
                  borderRadius: 12,
                  padding: 10,
                }}
              >
                {c.snippet}
              </pre>
            </div>
          ))}
          {!props.citations.length ? (
            <div className="card" style={{ padding: "12px 14px", color: "var(--ink-mute)" }}>
              No citations yet. Ask a question to retrieve evidence.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

