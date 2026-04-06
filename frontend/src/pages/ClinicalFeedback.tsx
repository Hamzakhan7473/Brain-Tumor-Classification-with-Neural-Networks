import React, { useEffect, useMemo, useState } from "react";
import { formatApiConnectionHint, submitClinicalFeedback } from "../api/client";

type StoredPrediction = {
  scanBase64: string;
  filename: string;
  model: string;
  study_instance_uid: string;
  site_id?: string;
  shadow_mode: boolean;
  prediction: {
    label: string;
    confidence: number;
  };
};

export default function ClinicalFeedback() {
  const [stored, setStored] = useState<StoredPrediction | null>(null);
  const [feedback, setFeedback] = useState<"agree" | "wrong_class" | "unclear">("agree");
  const [correctedClass, setCorrectedClass] = useState<string>("glioma");
  const [notes, setNotes] = useState<string>("");
  const [reasonTags, setReasonTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<string>("");

  const classOptions = useMemo(() => ["glioma", "meningioma", "pituitary", "notumor"], []);

  useEffect(() => {
    const raw = sessionStorage.getItem("lastPrediction");
    if (!raw) return;
    try {
      setStored(JSON.parse(raw) as StoredPrediction);
    } catch {
      // ignore
    }
    const handler = (e: KeyboardEvent) => {
      if (e.key === "1") setFeedback("agree");
      if (e.key === "2") setFeedback("wrong_class");
      if (e.key === "3") setFeedback("unclear");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const allReasonOptions = useMemo(
    () => ["Artifact / motion", "Non-tumor lesion", "Different tumor type", "Imaging incomplete", "Other"],
    [],
  );

  function toggleReason(tag: string) {
    setReasonTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!stored) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const reasonsText = reasonTags.length ? `Reasons: ${reasonTags.join(", ")}` : "";
      const mergedNotes =
        reasonsText && notes ? `${reasonsText} | ${notes}` : reasonsText || (notes || undefined);

      const res = await submitClinicalFeedback({
        study_instance_uid: stored.study_instance_uid,
        site_id: stored.site_id,
        feedback,
        corrected_class: feedback === "wrong_class" ? correctedClass : null,
        notes: mergedNotes || null,
        model: stored.model,
      });
      setSuccess(`Saved: ${res.status || "ok"}`);
      sessionStorage.setItem("lastFeedbackStatus", feedback);
    } catch (ex) {
      const raw = ex instanceof Error ? ex.message : String(ex);
      setError(formatApiConnectionHint(raw));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Clinical Feedback</h2>

      {!stored ? (
        <div style={{ marginTop: 14, color: "var(--muted)" }}>
          No prediction found in this session. Go to <a href="/upload">Upload & Predict</a>.
        </div>
      ) : (
        <div className="grid2" style={{ marginTop: 14 }}>
          <div className="card">
            <div style={{ fontWeight: 800 }}>Case summary</div>
            <div style={{ marginTop: 10, color: "var(--muted)" }}>
              <div>
                <b>Study UID:</b> {stored.study_instance_uid}
              </div>
              <div>
                <b>Site ID:</b> {stored.site_id || "—"}
              </div>
              <div>
                <b>Model:</b> {stored.model}
              </div>
              <div>
                <b>AI label:</b> {stored.prediction.label} ({(stored.prediction.confidence * 100).toFixed(1)}%)
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-mute)", marginBottom: 6 }}>Scan</div>
              <div
                style={{
                  position: "relative",
                  borderRadius: 16,
                  overflow: "hidden",
                  border: "1px solid rgba(15, 23, 42, 0.06)",
                  maxWidth: 260,
                }}
              >
                <img src={stored.scanBase64} alt="Current scan" style={{ width: "100%", display: "block" }} />
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background:
                      "radial-gradient(circle at 50% 40%, rgba(244, 63, 94, 0.35), transparent 55%), radial-gradient(circle at 30% 70%, rgba(59, 130, 246, 0.3), transparent 55%)",
                    mixBlendMode: "screen",
                    pointerEvents: "none",
                  }}
                />
              </div>
              <p style={{ fontSize: 12, color: "var(--ink-mute)", marginTop: 6 }}>
                Saliency overlay is illustrative only. Final interpretation must be performed in PACS.
              </p>
            </div>
          </div>

          <div className="card">
            <form onSubmit={onSubmit}>
              <div style={{ fontWeight: 800 }}>Feedback (design partner)</div>
              <div style={{ marginTop: 12 }}>
                <label style={{ fontWeight: 700 }}>Feedback</label>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
                  <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="radio"
                      name="fb"
                      value="agree"
                      checked={feedback === "agree"}
                      onChange={() => setFeedback("agree")}
                    />
                    agree
                  </label>
                  <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="radio"
                      name="fb"
                      value="wrong_class"
                      checked={feedback === "wrong_class"}
                      onChange={() => setFeedback("wrong_class")}
                    />
                    wrong class
                  </label>
                  <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="radio"
                      name="fb"
                      value="unclear"
                      checked={feedback === "unclear"}
                      onChange={() => setFeedback("unclear")}
                    />
                    unclear
                  </label>
                </div>
                <p style={{ fontSize: 11, color: "var(--ink-mute)", marginTop: 4 }}>
                  Shortcuts: 1 = agree, 2 = wrong class, 3 = unclear.
                </p>
              </div>

              {feedback === "wrong_class" ? (
                <div style={{ marginTop: 14 }}>
                  <label style={{ display: "block", fontWeight: 700, marginBottom: 8 }}>Corrected class</label>
                  <select value={correctedClass} onChange={(e) => setCorrectedClass(e.target.value)} style={{ width: "100%", padding: 10 }}>
                    {classOptions.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}

              {feedback === "wrong_class" && (
                <div style={{ marginTop: 14 }}>
                  <label style={{ display: "block", fontWeight: 700, marginBottom: 8 }}>Reason tags</label>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {allReasonOptions.map((tag) => {
                      const active = reasonTags.includes(tag);
                      return (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => toggleReason(tag)}
                          style={{
                            padding: "4px 10px",
                            borderRadius: 999,
                            border: active ? "1px solid var(--green-600)" : "1px solid var(--line)",
                            background: active ? "rgba(37,196,143,0.12)" : "rgba(248,250,249,0.9)",
                            fontSize: 12,
                            cursor: "pointer",
                          }}
                        >
                          {tag}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ marginTop: 14 }}>
                <label style={{ display: "block", fontWeight: 700, marginBottom: 8 }}>Notes (optional)</label>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional clinician notes" style={{ width: "100%", padding: 10, minHeight: 92 }} />
              </div>

              <div style={{ marginTop: 16 }}>
                <button className="btnPrimary" type="submit" disabled={loading} style={{ width: "100%", padding: "12px 18px" }}>
                  {loading ? "Submitting..." : "Submit feedback"}
                </button>
              </div>

              {error ? (
                <div style={{ marginTop: 12, color: "crimson", fontWeight: 600, whiteSpace: "pre-wrap" }}>{error}</div>
              ) : null}
              {success ? <div style={{ marginTop: 12, color: "#166534", fontWeight: 700 }}>{success}</div> : null}
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

