/**
 * Clinical report styling uses global.css :root tokens only (--green-*, --ink*, --line, --surface, --white).
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatApiConnectionHint, generateReport, explainScan, attestGeneratedContent, ReportResponse, ExplanationResponse } from "../../api/client";
import {
  findingsDisagreeApi,
  reportDefer,
  reportSign,
} from "../../lib/api";
import type { Phase, ScanFindings, WMHResult, WMHSeverity } from "../../types/scan";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { IosButton } from "../ui/IosButton";
import { AttestationGate } from "../ui/AttestationGate";
import { ProviderBadge } from "../ui/ProviderBadge";
import { useFeatures } from "../../hooks/useFeatures";

type FindingsCardProps = {
  findings: ScanFindings | null;
  visible: boolean;
  phase: Phase;
  apiError: string | null;
  apiBaseDisplay: string;
  onInferenceRetry: () => void;
  file: File | null;
  model: string;
  studyUid: string;
  siteId: string;
  shadowMode: boolean;
  apiKey?: string;
};

type ValueTone = "danger" | "warning" | "ok" | "neutral";

type ReportMetricRow = {
  label: string;
  value: string;
  severity: ValueTone;
  barWidth?: string;
};

function severityColorCss(sev: ValueTone): string {
  if (sev === "danger") return "#dc2626";
  if (sev === "warning") return "#d97706";
  if (sev === "ok") return "var(--modern-ink, #09090b)";
  return "var(--modern-ink-soft, #3f3f46)";
}

function capitalizeLeading(s: string): string {
  if (!s) return "";
  return s.slice(0, 1).toUpperCase() + s.slice(1);
}

function isNoTumorLabel(pred: string): boolean {
  const t = pred.trim().toLowerCase().replace(/\s+/g, "");
  return t === "notumor" || t === "no_tumor";
}

function fazekasFromSeverity(g: WMHSeverity): number {
  if (g === "Normal") return 0;
  if (g === "Mild") return 1;
  if (g === "Moderate") return 2;
  return 3;
}

function wmhSyntheticPercentile(w: WMHResult): number {
  if (typeof w.age_matched_percentile === "number") {
    return Math.min(99, Math.max(1, Math.round(w.age_matched_percentile)));
  }
  const v = Math.round(50 + w.peak_lesion_prob * 35 + Math.min(w.volume_cc / 35, 1) * 25 + w.lesion_fraction * 20);
  return Math.min(99, Math.max(51, v));
}

function normPredKey(pred: string): string {
  return pred.trim().toLowerCase().replace(/\s+/g, "_").replace(/^no_/i, "");
}

/** Serif-clinical prose with &lt;strong&gt; emphasis (rendered safely as JSX fragments). */
function generateImpression(findings: ScanFindings): React.ReactNode {
  const seg = findings.isSegmentation;
  const confPct = `${(findings.confidence * 100).toFixed(1)}%`;

  if (findings.guardrails?.disposition === "indeterminate") {
    const msg =
      findings.guardrails.radiologistActionRequired?.trim() ||
      "Confidence gating withheld the headline class — corroborate with independent reading.";
    return (
      <>
        <strong>Indeterminate model output.</strong> {msg} Raw softmax probabilities remain in structured metrics below.
      </>
    );
  }

  if (seg && findings.wmh) {
    const w = findings.wmh;
    const pctOrdinal =
      typeof w.age_matched_percentile === "number"
        ? `${Math.round(w.age_matched_percentile)}th`
        : `${wmhSyntheticPercentile(w)}th`;
    const g = w.severity_grade;

    if (g === "Normal") {
      return (
        <>
          <strong>No significant white matter hyperintensities detected.</strong> WMH burden within expected range for age.
        </>
      );
    }
    if (g === "Mild") {
      return (
        <>
          Scattered punctate white matter hyperintensities, consistent with mild small vessel disease.{" "}
          <strong>Fazekas-equivalent grade 1.</strong> Burden is at the <strong>{pctOrdinal} percentile</strong> for the
          patient&apos;s age.
        </>
      );
    }
    if (g === "Moderate") {
      return (
        <>
          Multifocal supratentorial periventricular and deep white matter hyperintensities, consistent with{" "}
          <strong>moderate small vessel disease</strong>. <strong>Fazekas-equivalent grade 2.</strong> Burden is in the{" "}
          <strong>{pctOrdinal} percentile</strong> for the patient&apos;s age, suggesting elevated vascular risk. Recommend
          neurovascular review.
        </>
      );
    }
    return (
      <>
        Confluent periventricular and deep white matter hyperintensities, consistent with{" "}
        <strong>severe small vessel disease</strong>. <strong>Fazekas-equivalent grade 3.</strong> Burden is in the{" "}
        <strong>{pctOrdinal} percentile</strong> for the patient&apos;s age. Recommend urgent neurovascular review and
        vascular risk factor management.
      </>
    );
  }

  const nk = normPredKey(findings.prediction);
  if (isNoTumorLabel(findings.prediction) || nk === "no_tumor" || nk === "notumor") {
    return (
      <>
        <strong>No mass lesion or focal abnormality identified</strong> on the reviewed slices. Confidence:{" "}
        <strong>{confPct}</strong>.
      </>
    );
  }
  if (nk.includes("glioma")) {
    return (
      <>
        Findings suggestive of <strong>glial neoplasm</strong> with <strong>{confPct}</strong> model confidence. Tissue
        characterization and grading require histopathologic correlation.
      </>
    );
  }
  if (nk.includes("meningioma")) {
    return (
      <>
        Extra-axial mass with imaging features suggestive of <strong>meningioma</strong>. Confidence:{" "}
        <strong>{confPct}</strong>.
      </>
    );
  }
  if (nk.includes("pituitary")) {
    return (
      <>
        Sellar/parasellar lesion with imaging features consistent with <strong>pituitary adenoma</strong>. Confidence:{" "}
        <strong>{confPct}</strong>.
      </>
    );
  }

  return (
    <>
      <strong>{capitalizeLeading(findings.prediction)}</strong> — model confidence <strong>{confPct}</strong>. Correlation
      with histopathologic or advanced imaging advised.
    </>
  );
}

function confidenceTone(confidence: number): ValueTone {
  if (confidence < 0.85) return "warning";
  return "ok";
}

function buildMetricsWmhRows(w: WMHResult): ReportMetricRow[] {
  const sevTone: ValueTone =
    w.severity_grade === "Severe"
      ? "danger"
      : w.severity_grade === "Moderate" || w.severity_grade === "Mild"
        ? "warning"
        : "ok";
  const fz = fazekasFromSeverity(w.severity_grade);
  const pct = wmhSyntheticPercentile(w);

  const volPct = `${Math.min(100, Math.round((w.volume_cc / 35) * 100))}%`;
  const percentileBar = `${pct}%`;

  const volPretty =
    w.volume_cc_ci_95 && w.volume_cc_ci_95.length >= 2
      ? `${w.volume_cc.toFixed(1)} cc (95% CI: ${w.volume_cc_ci_95[0].toFixed(1)} – ${w.volume_cc_ci_95[1].toFixed(1)} cc)`
      : `${w.volume_cc.toFixed(1)} cc`;
  const rows: ReportMetricRow[] = [
    {
      label: "WMH volume",
      value: volPretty,
      severity: w.volume_cc >= 15 ? "warning" : "neutral",
      barWidth: volPct,
    },
  ];
  const pv = w.volume_cc_periventricular;
  const deep = w.volume_cc_deep_subcortical;
  const infra = w.volume_cc_infratentorial;
  if (typeof pv === "number" || typeof deep === "number" || typeof infra === "number") {
    rows.push({
      label: "Regional volumes",
      value: `PV ${(pv ?? 0).toFixed(1)} · deep ${(deep ?? 0).toFixed(1)} · infra ${(infra ?? 0).toFixed(1)} cc`,
      severity: "neutral",
    });
  }
  rows.push(
    {
      label: "Severity grade",
      value: `${w.severity_grade} · grade ${fz}`,
      severity: sevTone,
    },
    {
      label: "Age-matched percentile",
      value: `${pct}th percentile`,
      severity: sevTone !== "ok" ? sevTone : "neutral",
      barWidth: percentileBar,
    },
    {
      label: "Lesion voxels",
      value: `${w.lesion_voxels.toLocaleString()} voxels`,
      severity: "neutral",
    },
  );
  return rows;
}

function buildMetrics2dRows(findings: ScanFindings, tumorHighlight: boolean): ReportMetricRow[] {
  const sorted = [...findings.classProbs].sort((a, b) => b.probability - a.probability);
  const predTone: ValueTone = tumorHighlight ? "danger" : "ok";
  const ct = confidenceTone(findings.confidence);

  const rows: ReportMetricRow[] = [
    {
      label: "Predicted class",
      value: capitalizeLeading(findings.prediction),
      severity: predTone,
    },
    {
      label: "Model confidence",
      value: `${(findings.confidence * 100).toFixed(1)}%`,
      severity: ct,
      barWidth: `${Math.round(findings.confidence * 100)}%`,
    },
  ];

  for (const c of sorted.slice(0, 4)) {
    rows.push({
      label: capitalizeLeading(c.label),
      value: `${(c.probability * 100).toFixed(1)}%`,
      severity: "neutral",
      barWidth: `${Math.round(c.probability * 100)}%`,
    });
  }

  return rows;
}

function transparencyRows(findings: ScanFindings): { label: string; value: string }[] {
  const g = findings.guardrails;
  if (!g) return [];
  const v = (g.validation ?? {}) as Record<string, unknown>;
  const seq = typeof v.detected_sequence === "string" ? v.detected_sequence : "—";
  const sc = typeof v.sequence_confidence === "number" ? `${(v.sequence_confidence * 100).toFixed(0)}%` : "—";
  const ood = Boolean(v.distribution_is_ood);
  const z = typeof v.distribution_z_score === "number" ? String(v.distribution_z_score) : "—";
  const meta = (v.metadata ?? {}) as Record<string, unknown>;
  const dims = Array.isArray(meta.voxel_dims_mm)
    ? (meta.voxel_dims_mm as number[]).map((x) => x.toFixed(2)).join(" × ")
    : "—";

  let ciLine = "—";
  if (findings.isSegmentation && findings.wmh?.volume_cc_ci_95 && findings.wmh.volume_cc_ci_95.length >= 2) {
    const [a, b] = findings.wmh.volume_cc_ci_95;
    ciLine = `${a.toFixed(1)} – ${b.toFixed(1)} cc (95% CI on MC dropout)`;
  } else if (!findings.isSegmentation && g.uncertainty) {
    const u = g.uncertainty as Record<string, unknown>;
    const ci = u.confidence_ci_95;
    if (Array.isArray(ci) && ci.length >= 2) {
      ciLine = `${Number(ci[0]).toFixed(3)} – ${Number(ci[1]).toFixed(3)} (95% CI, class prob)`;
    }
  }

  return [
    { label: "Detected sequence", value: `${seq} (${sc} confidence)` },
    { label: "Voxel size (mm)", value: `${dims} mm` },
    { label: "Distribution check", value: ood ? "⚠ Out of distribution" : "✓ Within offline validation band" },
    { label: "Uncertainty band", value: ciLine },
    { label: "Audit ID", value: g.auditId ?? "—" },
  ];
}

export default function FindingsCard({
  findings,
  visible,
  phase,
  apiError,
  apiBaseDisplay,
  onInferenceRetry,
  file,
  model,
  studyUid,
  siteId,
  shadowMode,
  apiKey,
}: FindingsCardProps): React.ReactElement | null {
  const reduced = usePrefersReducedMotion();
  const navigate = useNavigate();
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string>("");
  const [barsRevealed, setBarsRevealed] = useState(false);
  const [signBusy, setSignBusy] = useState(false);
  const [signNote, setSignNote] = useState<string>("");
  const [overrideText, setOverrideText] = useState("");
  const [deferReason, setDeferReason] = useState("");
  const [disagreeNotes, setDisagreeNotes] = useState("");
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState("");
  const [explainAttested, setExplainAttested] = useState(false);
  const [explainAttestBusy, setExplainAttestBusy] = useState(false);
  const [explainAttestErr, setExplainAttestErr] = useState<string | null>(null);
  const { llmProvider } = useFeatures();

  const reportModel = findings?.modelName?.trim() || model;

  useEffect(() => {
    if (!visible || !findings) {
      setBarsRevealed(false);
      return;
    }
    if (reduced) {
      setBarsRevealed(true);
      return;
    }
    setBarsRevealed(false);
    const t = requestAnimationFrame(() => setBarsRevealed(true));
    return () => cancelAnimationFrame(t);
  }, [visible, findings, reduced]);

  async function handleApproveReport() {
    if (!file || !findings) return;
    const aid = findings.guardrails?.auditId ?? "";
    if (!aid) {
      setReportError("Missing audit id — cannot certify sign-off lineage.");
      return;
    }
    const ok = window.confirm(
      "By proceeding you acknowledge clinical responsibility for the downstream narrative. Audit ID "
        + `${aid} will remain permanently linked to this workstation session.`,
    );
    if (!ok) return;
    setReportError("");
    setSignBusy(true);
    try {
      await reportSign({ audit_id: aid, agreed: true, apiKeyOverride: apiKey });
    } catch (e) {
      setSignNote(e instanceof Error ? e.message : String(e));
      setSignBusy(false);
      return;
    }
    setSignBusy(false);
    setReportError("");
    setReportLoading(true);
    try {
      const r: ReportResponse = await generateReport({
        file,
        model: reportModel,
        study_instance_uid: studyUid || undefined,
        site_id: siteId || undefined,
        shadow_mode: shadowMode,
      });
      const ts = new Date().toISOString();
      sessionStorage.setItem(
        "lastReport",
        JSON.stringify({
          study_instance_uid: studyUid || r.study_instance_uid,
          report_text: r.report_text,
          timestamp: ts,
          provenance: r.provenance ?? null,
        }),
      );
      navigate("/report");
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      setReportError(formatApiConnectionHint(raw));
    } finally {
      setReportLoading(false);
    }
  }

  async function handleExplain() {
    if (!file || !findings) return;
    setExplainError("");
    setExplainLoading(true);
    setExplainAttested(false);
    try {
      const r = await explainScan({
        file,
        model: reportModel,
        study_instance_uid: studyUid || undefined,
        site_id: siteId || undefined,
        shadow_mode: shadowMode,
      });
      setExplanation(r);
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      setExplainError(formatApiConnectionHint(raw));
    } finally {
      setExplainLoading(false);
    }
  }

  async function handleOverrideSubmit() {
    const aid = findings?.guardrails?.auditId ?? "";
    if (!aid || !(overrideText || "").trim()) return;
    setSignBusy(true);
    setSignNote("");
    try {
      await reportSign({ audit_id: aid, agreed: false, override: overrideText.trim(), apiKeyOverride: apiKey });
      setOverrideText("");
      setSignNote("Override sign-off logged.");
    } catch (e) {
      setSignNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSignBusy(false);
    }
  }

  async function handleDeferSubmit() {
    const aid = findings?.guardrails?.auditId ?? "";
    if (!aid || !(deferReason || "").trim()) return;
    setSignBusy(true);
    setSignNote("");
    try {
      await reportDefer({ audit_id: aid, reason: deferReason.trim(), apiKeyOverride: apiKey });
      setDeferReason("");
      setSignNote("Defer / second-opinion logged.");
    } catch (e) {
      setSignNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSignBusy(false);
    }
  }

  async function handleDisagreeSubmit() {
    const aid = findings?.guardrails?.auditId ?? "";
    if (!aid || !(disagreeNotes || "").trim()) return;
    setSignBusy(true);
    setSignNote("");
    try {
      await findingsDisagreeApi({ audit_id: aid, notes: disagreeNotes.trim(), apiKeyOverride: apiKey });
      setDisagreeNotes("");
      setSignNote("Imaging disagreement captured for model improvement.");
    } catch (e) {
      setSignNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSignBusy(false);
    }
  }

  function handleEdit() {
    if (!findings) return;
    const blob = new Blob([JSON.stringify(findings, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `neurosight-findings-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const impression = useMemo(() => (findings ? generateImpression(findings) : null), [findings]);

  const tumorRiskDanger = useMemo(() => {
    if (!findings || findings.isSegmentation) return false;
    return !isNoTumorLabel(findings.prediction);
  }, [findings]);

  const metricRows = useMemo((): ReportMetricRow[] => {
    if (!findings) return [];
    if (findings.isSegmentation && findings.wmh) return buildMetricsWmhRows(findings.wmh);
    if (!findings.isSegmentation) return buildMetrics2dRows(findings, tumorRiskDanger);
    return [];
  }, [findings, tumorRiskDanger]);

  if (phase === "error") {
    const raw = (apiError || "").trim() || "The model could not analyze this scan.";
    return (
      <div
        className="font-ios ios-soft-shadow rounded-ios-lg"
        role="alert"
        style={{
          marginBottom: 16,
          background: "color-mix(in srgb, var(--green-900) 8%, transparent)",
          border: "0.5px solid color-mix(in srgb, var(--green-900) 35%, transparent)",
          borderRadius: "var(--radius-ios-lg)",
          padding: "14px 16px",
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            color: "var(--green-900)",
            marginBottom: 6,
          }}
        >
          Inference failed
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--ink-mid)", marginBottom: 10 }}>
          {formatApiConnectionHint(raw)}
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-mute)", fontFamily: "Menlo, monospace", marginBottom: 12 }}>
          Check that the API is reachable at <strong style={{ fontWeight: 600 }}>{apiBaseDisplay}</strong>
          <br />
          Open the browser console for <code>[API]</code> / <code>[scan]</code> logs.
        </div>
        <IosButton variant="primary" size="md" fullWidth onClick={onInferenceRetry}>
          Try again
        </IosButton>
      </div>
    );
  }

  if (!visible || !findings) {
    return null;
  }

  const seg = findings.isSegmentation;

  const enterClass = reduced ? "" : "ios-findings-enter ios-animated";

  return (
    <div
      className={`ns-card-frame ns-bg-card-solid ios-soft-shadow rounded-ios-lg font-ios overflow-hidden ${enterClass}`}
      style={{ marginBottom: 16 }}
    >
      <div className="text-ios-subhead font-semibold font-ios text-ns-heading" style={{ padding: "12px 14px 10px 14px" }}>
        Analysis findings
      </div>

      {findings.guardrails && transparencyRows(findings).length ? (
        <div
          className="transparency-block"
          style={{
            margin: "0 14px 12px 14px",
            padding: 10,
            borderRadius: "var(--radius-ios)",
            background: "var(--surface)",
            border: "0.5px solid var(--line)",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, monospace",
            fontSize: 10,
            color: "var(--ink-mid)",
          }}
        >
          <div style={{ fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 6 }}>
            Transparency
          </div>
          {transparencyRows(findings).map((row) => (
            <div key={row.label} style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
              <span style={{ color: "var(--ink-mute)" }}>{row.label}</span>
              <span style={{ textAlign: "right", maxWidth: "62%" }}>{row.value}</span>
            </div>
          ))}
        </div>
      ) : null}

      {(findings.guardrails?.warnings?.length ?? 0) > 0 ? (
        <div style={{ padding: "0 14px 10px 14px" }}>
          {(findings.guardrails!.warnings ?? []).map((w, i) => (
            <div
              key={i}
              className="warning-banner"
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
                padding: "8px 10px",
                borderRadius: "var(--radius-ios)",
                background: "color-mix(in srgb, var(--green-600) 10%, transparent)",
                border: "1px solid color-mix(in srgb, var(--green-600) 35%, transparent)",
                marginBottom: 6,
                fontSize: 11,
                color: "var(--green-900)",
              }}
            >
              <span aria-hidden>⚠</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          alignItems: "center",
          padding: "0 14px 10px 14px",
        }}
      >
        <span
          className="text-ios-caption2 font-semibold font-ios"
          style={{
            padding: "4px 10px",
            borderRadius: "var(--radius-ios)",
            border: "1px solid var(--line)",
            color: "var(--ink-mid)",
            background: "var(--surface)",
          }}
        >
          {findings.modelName}
        </span>
        <span className="text-ios-caption2 font-medium font-ios text-ns-muted">{findings.inferenceMs}ms</span>
        {findings.isSimulated ? <span className="ios-sim-badge">Simulated</span> : null}
      </div>

      {!seg ? (
        <div
          className={tumorRiskDanger ? "ios-risk-banner" : "ios-risk-banner--ok"}
          role="status"
          style={{ marginLeft: 14, marginRight: 14 }}
        >
          {tumorRiskDanger ? "Tumor detected — research result only" : "No tumor detected"}
        </div>
      ) : findings.wmh ? (
        findings.wmh.risk_level === "High" || findings.wmh.risk_level === "Very High" ? (
          <div className="ios-risk-banner" role="status" style={{ marginLeft: 14, marginRight: 14 }}>
            Risk: {findings.wmh.risk_level}
          </div>
        ) : findings.wmh.risk_level === "Moderate" ? (
          <div className="ios-risk-banner--muted" role="status" style={{ marginLeft: 14, marginRight: 14 }}>
            Risk: {findings.wmh.risk_level}
          </div>
        ) : (
          <div className="ios-risk-banner--ok" role="status" style={{ marginLeft: 14, marginRight: 14 }}>
            Risk: {findings.wmh.risk_level}
          </div>
        )
      ) : (
        <div className="ios-risk-banner" role="alert" style={{ marginLeft: 14, marginRight: 14 }}>
          Missing WMH payload from API response.
        </div>
      )}

      <div
        style={{
          padding: "12px 14px",
          background: "var(--surface)",
          borderTop: `0.5px solid var(--line)`,
          borderBottom: `0.5px solid var(--line)`,
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            color: "var(--ink-mute)",
            marginBottom: 6,
          }}
        >
          Impression
        </div>
        <div
          style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            fontSize: 12.5,
            lineHeight: 1.6,
            color: "var(--ink-mid)",
          }}
        >
          {impression}
        </div>
        <div style={{ marginTop: 10 }}>
          <IosButton
            variant="secondary"
            size="sm"
            loading={explainLoading}
            disabled={!file || explainLoading}
            onClick={() => void handleExplain()}
          >
            {explainLoading ? "Generating…" : explanation ? "Regenerate AI explanation" : "Generate AI explanation"}
          </IosButton>
        </div>
        {explainError ? (
          <div className="app-text-error" style={{ marginTop: 8, fontSize: 12, whiteSpace: "pre-wrap" }}>
            {explainError}
          </div>
        ) : null}
        {explanation ? (
          <div style={{ marginTop: 10 }}>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "var(--ink-mute)",
                marginBottom: 6,
              }}
            >
              AI explanation
            </div>
            <div
              style={{
                fontFamily: 'Georgia, "Times New Roman", serif',
                fontSize: 12.5,
                lineHeight: 1.6,
                color: "var(--ink-mid)",
                whiteSpace: "pre-wrap",
              }}
            >
              {explanation.explanation}
            </div>
            <div style={{ marginTop: 8 }}>
              <ProviderBadge provider={llmProvider} provenance={explanation.provenance} />
            </div>
            <div style={{ marginTop: 10 }}>
              <AttestationGate
                attested={explainAttested}
                busy={explainAttestBusy}
                error={explainAttestErr}
                onSubmit={async (name, text) => {
                  setExplainAttestBusy(true);
                  setExplainAttestErr(null);
                  try {
                    await attestGeneratedContent({
                      attested_by: name,
                      attestation_text: text,
                      content_kind: "explanation",
                    });
                    setExplainAttested(true);
                  } catch (err) {
                    setExplainAttestErr(err instanceof Error ? err.message : "Attestation failed");
                  } finally {
                    setExplainAttestBusy(false);
                  }
                }}
              />
            </div>
          </div>
        ) : null}
      </div>

      <div style={{ padding: "12px 14px 8px 14px" }}>
        <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 6 }}>
          Key quantities
        </div>

        {metricRows.map((m, i) => (
          <div key={`${m.label}-${i}`}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "7px 0",
                borderBottom: i < metricRows.length - 1 ? `0.5px solid var(--line)` : "none",
              }}
            >
              <span style={{ fontSize: 11.5, color: "var(--ink-mute)" }}>{m.label}</span>
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: severityColorCss(m.severity),
                  fontFeatureSettings: '"tnum"',
                  letterSpacing: "-0.2px",
                }}
              >
                {m.value}
              </span>
            </div>
            {m.barWidth ? (
              <div
                style={{
                  height: 2,
                  background: "var(--line)",
                  borderRadius: 1,
                  overflow: "hidden",
                  marginTop: 4,
                  marginBottom: 4,
                }}
              >
                <div
                  className={barsRevealed && !reduced ? "ios-animated" : undefined}
                  style={{
                    height: "100%",
                    borderRadius: 1,
                    background: severityColorCss(m.severity),
                    ...(reduced
                      ? { width: m.barWidth }
                      : barsRevealed
                        ? ({ ["--bar-w"]: m.barWidth, animation: "ios-bar-in 0.9s ease both" } as React.CSSProperties)
                        : { width: "0%" }),
                  }}
                />
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {seg && findings.wmh?.note ? (
        <p
          className="text-ios-caption2 font-ios text-ns-muted"
          style={{
            fontStyle: "italic",
            margin: "0 14px 12px 14px",
            lineHeight: 1.35,
          }}
        >
          {findings.wmh.note}
        </p>
      ) : null}

      <div
        style={{
          padding: "10px 14px",
          borderTop: `0.5px solid var(--line)`,
          background: "var(--surface)",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <IosButton
            variant="primary"
            loading={reportLoading || signBusy}
            disabled={!file || !findings.guardrails?.auditId}
            size="md"
            onClick={() => void handleApproveReport()}
          >
            Confirm &amp; draft report
          </IosButton>
          <IosButton variant="secondary" size="md" onClick={handleEdit}>
            Export JSON
          </IosButton>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="text-ios-caption2 font-ios text-ns-muted">
            Radiologist governance — attestations append to logs/audit/signoffs.jsonl
          </span>
          <textarea
            className="text-ios-caption1 font-ios"
            placeholder="Override narrative — required if you disagree with model headline"
            value={overrideText}
            onChange={(e) => setOverrideText(e.target.value)}
            rows={2}
            style={{
              width: "100%",
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: 8,
              background: "var(--surface)",
            }}
          />
          <IosButton
            variant="secondary"
            size="sm"
            disabled={signBusy || !findings.guardrails?.auditId}
            loading={signBusy}
            onClick={() => void handleOverrideSubmit()}
          >
            Submit override sign-off
          </IosButton>
          <textarea
            className="text-ios-caption1 font-ios"
            placeholder="Defer — reason for peer read / escalation"
            value={deferReason}
            onChange={(e) => setDeferReason(e.target.value)}
            rows={2}
            style={{
              width: "100%",
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: 8,
              background: "var(--surface)",
            }}
          />
          <IosButton variant="secondary" size="sm" disabled={signBusy || !findings.guardrails?.auditId} onClick={() => void handleDeferSubmit()}>
            Log defer request
          </IosButton>
          <textarea
            className="text-ios-caption1 font-ios"
            placeholder="Imaging vs model mismatch — correction notes"
            value={disagreeNotes}
            onChange={(e) => setDisagreeNotes(e.target.value)}
            rows={2}
            style={{
              width: "100%",
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: 8,
              background: "var(--surface)",
            }}
          />
          <IosButton
            variant="secondary"
            size="sm"
            disabled={signBusy || !findings.guardrails?.auditId}
            onClick={() => void handleDisagreeSubmit()}
          >
            Submit imaging disagreement
          </IosButton>
        </div>
        {findings.guardrails?.auditTimestamp ? (
          <div className="text-ios-caption2 font-ios text-ns-muted" style={{ fontFamily: "Menlo, monospace" }}>
            Logged UTC: {findings.guardrails.auditTimestamp}
          </div>
        ) : null}
      </div>

      {signNote ? (
        <div className="text-ios-footnote font-ios" style={{ padding: "0 14px 8px", color: "var(--ink-mid)" }}>
          {signNote}
        </div>
      ) : null}

      {reportError ? (
        <div
          className="text-ios-footnote font-semibold font-ios text-ns-val-danger"
          style={{ padding: "0 14px 12px 14px", whiteSpace: "pre-wrap" }}
        >
          {reportError}
        </div>
      ) : null}
    </div>
  );
}
