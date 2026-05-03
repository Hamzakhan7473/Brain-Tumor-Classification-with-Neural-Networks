import React, { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { diffWords } from "diff";
import "./ReportDraft.css";
import {
  fetchReportDraftPdfBlob,
  getReportDraft,
  patchReportDraftSection,
  regenerateReportDraftSection,
  signReportDraft,
  type ReportDraftDoc,
} from "../api/client";

type Section = {
  name: string;
  source?: string;
  text?: string | null;
  findings?: Array<{ region: string; text: string; measurements?: string[]; citations?: number[] }>;
  impressions?: Array<{ order: number; text: string; measurements?: string[]; citations?: number[] }>;
  history?: Array<{ version: number; snapshot: Record<string, unknown>; edited_by?: string; edited_at?: string }>;
  ai_snapshot?: Record<string, unknown> | null;
};

function sourcePillStyle(source: string | undefined): React.CSSProperties {
  const s = source || "";
  const color =
    s === "template"
      ? "var(--ink-mid)"
      : s === "ai"
        ? "var(--green-600)"
        : s === "measured"
          ? "var(--green-700)"
          : s === "edited"
            ? "var(--green-800)"
            : "var(--ink-soft)";
  return {
    fontSize: 11,
    fontWeight: 700,
    padding: "2px 8px",
    borderRadius: 999,
    border: "1px solid var(--line)",
    color,
  };
}

function WordDiff({ before, after }: { before: string; after: string }) {
  const parts = diffWords(before || "", after || "");
  return (
    <span>
      {parts.map((p, i) => (
        <span
          key={i}
          style={{
            textDecoration: p.removed ? "line-through" : undefined,
            background: p.added
              ? "color-mix(in srgb, var(--green-600) 22%, transparent)"
              : p.removed
                ? "color-mix(in srgb, var(--green-900) 18%, transparent)"
                : undefined,
          }}
        >
          {p.value}
        </span>
      ))}
    </span>
  );
}

export default function ReportDraft() {
  const { reportId } = useParams<{ reportId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const readOnly = location.pathname.endsWith("/signed");

  const [report, setReport] = useState<ReportDraftDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [lastSaved, setLastSaved] = useState<number | null>(null);
  const [regenBusy, setRegenBusy] = useState<string | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [signOpen, setSignOpen] = useState(false);
  const [signerName, setSignerName] = useState("");
  const [signerRole, setSignerRole] = useState("");
  const [signerNpi, setSignerNpi] = useState("");
  const [signAck, setSignAck] = useState(false);
  const [signResult, setSignResult] = useState<{ audit_id: string; text_hash: string } | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (!reportId) return;
    setErr(null);
    try {
      const d = await getReportDraft(reportId);
      setReport(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load report");
    }
  }, [reportId]);

  useEffect(() => {
    void load();
  }, [load]);

  const scheduleSave = useCallback(
    (sectionName: string, body: Record<string, unknown>) => {
      if (readOnly || !reportId) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setSaveState("idle");
      debounceRef.current = setTimeout(async () => {
        setSaveState("saving");
        try {
          await patchReportDraftSection(reportId, sectionName, body);
          setSaveState("saved");
          setLastSaved(Date.now());
          await load();
        } catch (e) {
          setErr(e instanceof Error ? e.message : "Save failed");
          setSaveState("idle");
        }
      }, 2000);
    },
    [load, readOnly, reportId],
  );

  const sections = (report?.sections as Section[] | undefined) || [];

  const snapText = (s: Section): string | undefined => {
    const snap = s.ai_snapshot;
    if (!snap) return undefined;
    return typeof snap.text === "string" ? snap.text : undefined;
  };

  const originalTextFor = (s: Section): string => snapText(s) || "";

  const handleRegenerate = async (name: string) => {
    if (!reportId || readOnly) return;
    setRegenBusy(name);
    setErr(null);
    try {
      await regenerateReportDraftSection(reportId, name);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Regenerate failed");
    } finally {
      setRegenBusy(null);
    }
  };

  const handleSign = async () => {
    if (!reportId) return;
    setErr(null);
    try {
      const out = await signReportDraft(reportId, {
        signer_name: signerName,
        signer_role: signerRole,
        npi_or_license: signerNpi || undefined,
        acknowledged_disclaimer: signAck,
      });
      setSignResult({ audit_id: out.audit_id, text_hash: out.text_hash });
      setSignOpen(false);
      await load();
      navigate(`/report-draft/${reportId}/signed`, { replace: true });
      try {
        const blob = await fetchReportDraftPdfBlob(reportId);
        const u = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = u;
        a.download = `report-${reportId}.pdf`;
        a.click();
        URL.revokeObjectURL(u);
      } catch {
        /* PDF optional if WeasyPrint missing */
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Sign failed");
    }
  };

  if (!reportId) {
    return <div className="page container">Missing report id in URL.</div>;
  }

  const status = String(report?.status || "");
  const effectiveReadOnly = readOnly || status === "signed";

  if (!report) {
    return (
      <div className="page container">
        {err ? (
          <p className="text-ios-body" style={{ color: "var(--green-900)" }}>
            {err}
          </p>
        ) : (
          <p className="text-ios-body">Loading report…</p>
        )}
      </div>
    );
  }

  return (
    <div className="page container" style={{ maxWidth: 1100 }}>
      <div className="report-draft-banner">
        Draft generated by NeuroSight AI. Not finalized until reviewed, edited as needed, and electronically signed by an
        authorized radiologist.
      </div>

      <div style={{ marginTop: 16 }}>
        <div className="report-draft-header">
          <h2 className="text-ios-title2" style={{ margin: 0 }}>
            Report draft
          </h2>
          <span className="report-draft-tag">{status === "signed" ? "signed" : "unsigned"}</span>
          <span className="text-ios-footnote" style={{ color: "var(--ink-mute)" }}>
            Study {String(report?.study_uid || reportId)} · Template {String(report?.template_id || "—")}
          </span>
        </div>

        {err && (
          <div className="card" style={{ borderColor: "var(--green-700)", color: "var(--green-900)", marginBottom: 12 }}>
            {err}
          </div>
        )}

        {signResult && (
          <div className="card" style={{ marginBottom: 12, fontSize: 13 }}>
            <div style={{ fontWeight: 800 }}>Signed</div>
            <div style={{ marginTop: 6, fontFamily: "ui-monospace, monospace" }}>Audit ID: {signResult.audit_id}</div>
            <div style={{ fontFamily: "ui-monospace, monospace" }}>Text SHA-256: {signResult.text_hash}</div>
          </div>
        )}

        <div className="report-draft-grid">
          <div className="report-draft-card">
            <div className="report-draft-toolbar">
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} disabled={effectiveReadOnly} />
                Show changes
              </label>
              <span style={{ marginLeft: "auto" }}>
                {saveState === "saving" ? "Saving…" : saveState === "saved" && lastSaved ? `Saved ${Math.round((Date.now() - lastSaved) / 1000)}s ago` : ""}
              </span>
            </div>

            {sections.map((s) => (
              <section key={s.name} className="report-draft-section" id={`sec-${s.name}`}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <div className="report-draft-section-title">{s.name}</div>
                  <span style={sourcePillStyle(s.source)}>{s.source || "—"}</span>
                  {!effectiveReadOnly && ["findings", "impression", "recommendations"].includes(s.name) && (
                    <button
                      type="button"
                      className="report-draft-btn-ghost"
                      style={{ fontSize: 12, padding: "4px 8px" }}
                      disabled={regenBusy === s.name}
                      onClick={() => void handleRegenerate(s.name)}
                    >
                      {regenBusy === s.name ? "Regenerating…" : "↻ Regenerate"}
                    </button>
                  )}
                  <button
                    type="button"
                    className="report-draft-btn-ghost"
                    style={{ fontSize: 12, padding: "4px 8px" }}
                    onClick={() => setHistoryFor(s.name)}
                  >
                    History
                  </button>
                </div>

                {s.text != null && s.text !== "" && (
                  <>
                    {showDiff && (s.source === "edited" || (s.history && s.history.length > 0)) ? (
                      <div className="report-draft-editable" style={{ whiteSpace: "pre-wrap" }}>
                        <WordDiff before={originalTextFor(s) || (snapText(s) ?? "")} after={s.text || ""} />
                      </div>
                    ) : (
                      <div
                        className="report-draft-editable"
                        contentEditable={!effectiveReadOnly}
                        suppressContentEditableWarning
                        data-section={s.name}
                        onBlur={(e) => {
                          if (effectiveReadOnly) return;
                          const next = e.currentTarget.textContent || "";
                          if (next !== (s.text || "")) scheduleSave(s.name, { text: next });
                        }}
                      >
                        {s.text}
                      </div>
                    )}
                  </>
                )}

                {s.findings && s.findings.length > 0 && (
                  <div>
                    {s.findings.map((row, idx) => (
                      <div key={`${row.region}-${idx}`} className="report-draft-finding-row">
                        <div style={{ fontWeight: 700, fontSize: 13, color: "var(--ink-mid)" }}>{row.region}</div>
                        <div
                          className="report-draft-editable"
                          contentEditable={!effectiveReadOnly}
                          suppressContentEditableWarning
                          onBlur={(e) => {
                            if (effectiveReadOnly) return;
                            const next = e.currentTarget.textContent || "";
                            const copy = s.findings!.map((r, j) =>
                              j === idx ? { ...r, text: next } : { ...r },
                            );
                            scheduleSave("findings", { findings: copy });
                          }}
                        >
                          {row.text}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {s.impressions && s.impressions.length > 0 && (
                  <div className="report-draft-impression">
                    <ol>
                      {s.impressions
                        .slice()
                        .sort((a, b) => a.order - b.order)
                        .map((im) => (
                          <li key={im.order}>
                            <div
                              className="report-draft-editable"
                              contentEditable={!effectiveReadOnly}
                              suppressContentEditableWarning
                              onBlur={(e) => {
                                if (effectiveReadOnly) return;
                                const next = e.currentTarget.textContent || "";
                                const copy = s.impressions!.map((x) =>
                                  x.order === im.order ? { ...x, text: next } : { ...x },
                                );
                                scheduleSave("impression", { impressions: copy });
                              }}
                            >
                              {im.text}
                            </div>
                          </li>
                        ))}
                    </ol>
                  </div>
                )}
              </section>
            ))}
          </div>

          <aside className="report-draft-card" id="evidence-panel">
            <div style={{ fontWeight: 800, marginBottom: 8 }}>Evidence &amp; metrics</div>
            <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 10 }}>
              Measurements are locked to the model run referenced by each pill&apos;s audit trail.
            </div>
            {(report?.measurements as Array<Record<string, unknown>> | undefined)?.map((m) => (
              <div
                key={String(m.id)}
                className="report-draft-pill"
                style={{
                  fontFamily: "ui-monospace, monospace",
                  display: "block",
                  marginBottom: 6,
                  borderColor: m.severity === "warn" || m.severity === "severe" ? "var(--green-700)" : "var(--line)",
                }}
              >
                {String(m.label)}: {String(m.value)} {m.unit != null ? String(m.unit) : ""}
              </div>
            ))}
            <div style={{ marginTop: 14, fontWeight: 700, fontSize: 13 }}>Citations</div>
            <ul style={{ marginTop: 6, paddingLeft: 18, fontSize: 12, color: "var(--ink-soft)" }}>
              {(report?.citations as Array<Record<string, unknown>> | undefined)?.map((c) => (
                <li key={String(c.id)} id={`cite-${String(c.id)}`} style={{ marginBottom: 6 }}>
                  [{String(c.id)}] {String(c.label)}
                </li>
              ))}
            </ul>
          </aside>
        </div>

        {!effectiveReadOnly && (
          <div className="report-draft-footer">
            <span className="text-ios-footnote" style={{ color: "var(--ink-mute)" }}>
              {String(report?.disclaimer || "").slice(0, 120)}…
            </span>
            <button type="button" className="report-draft-btn" onClick={() => setSignOpen(true)}>
              Approve &amp; sign
            </button>
          </div>
        )}
      </div>

      {historyFor && (
        <div className="report-draft-modal-back" role="presentation" onClick={() => setHistoryFor(null)}>
          <div className="report-draft-modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 10 }}>Section history: {historyFor}</h3>
            {sections
              .find((x) => x.name === historyFor)
              ?.history?.map((h) => (
                <div key={h.version} style={{ borderBottom: "1px solid var(--line)", padding: "8px 0", fontSize: 13 }}>
                  <div style={{ fontWeight: 700 }}>v{h.version}</div>
                  <div style={{ color: "var(--ink-mute)" }}>
                    {h.edited_at} · {h.edited_by}
                  </div>
                </div>
              ))}
            <button type="button" className="report-draft-btn report-draft-btn-ghost" style={{ marginTop: 12 }} onClick={() => setHistoryFor(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {signOpen && (
        <div className="report-draft-modal-back" role="presentation" onClick={() => setSignOpen(false)}>
          <div className="report-draft-modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 10 }}>Electronic sign-off</h3>
            <p className="text-ios-footnote" style={{ color: "var(--ink-soft)", marginBottom: 12 }}>
              The hashed payload reflects the current edited narrative in all sections. By signing you accept full clinical
              responsibility.
            </p>
            <label style={{ display: "block", marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>Name</div>
              <input value={signerName} onChange={(e) => setSignerName(e.target.value)} style={{ width: "100%", padding: 8 }} />
            </label>
            <label style={{ display: "block", marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>Role</div>
              <input value={signerRole} onChange={(e) => setSignerRole(e.target.value)} style={{ width: "100%", padding: 8 }} />
            </label>
            <label style={{ display: "block", marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>NPI / license (optional)</div>
              <input value={signerNpi} onChange={(e) => setSignerNpi(e.target.value)} style={{ width: "100%", padding: 8 }} />
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", margin: "12px 0" }}>
              <input type="checkbox" checked={signAck} onChange={(e) => setSignAck(e.target.checked)} />
              <span className="text-ios-footnote">I acknowledge the disclaimer and accept clinical responsibility for the final report.</span>
            </label>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" className="report-draft-btn report-draft-btn-ghost" onClick={() => setSignOpen(false)}>
                Cancel
              </button>
              <button type="button" className="report-draft-btn" disabled={!signerName || !signerRole || !signAck} onClick={() => void handleSign()}>
                Sign
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
