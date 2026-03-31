import React, { useMemo, useState } from "react";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";
import { askDocs } from "../api/client";

export default function DocsAssistant() {
  const [question, setQuestion] = useState<string>(
    "What is the workflow when the model confidence is low in shadow mode?"
  );
  const [answer, setAnswer] = useState<string>("");
  const [citations, setCitations] = useState<EvidenceCitation[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const hasCitations = citations.length > 0;

  async function onAsk() {
    setLoading(true);
    setError("");
    setAnswer("");
    setCitations([]);
    try {
      const res = await askDocs(question);
      setAnswer(res.answer || "");
      setCitations(
        (res.citations || []).map((c, i) => ({
          id: c.id || `c-${i}`,
          title: c.title,
          source: c.source,
          snippet: c.snippet,
          score: c.score,
        }))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const summaryLine = useMemo(() => {
    if (!hasCitations) return "No citations yet";
    return `${citations.length} citation${citations.length === 1 ? "" : "s"} available`;
  }, [citations, hasCitations]);

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Docs Assistant (PageIndex-ready)</h2>
      <p style={{ color: "var(--ink-mute)", marginBottom: 14 }}>
        Ask questions over your clinical workflows, SOPs, and validation docs. The UI expects citations (sections +
        sources) so you can keep an auditable trail.
      </p>

      <div className="grid2">
        <div className="card">
          <div style={{ fontWeight: 800 }}>Question</div>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about workflows, guidelines, or validation…"
            style={{ marginTop: 10, minHeight: 120 }}
          />
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
            <button className="btnPrimary" type="button" disabled={loading || !question.trim()} onClick={onAsk}>
              {loading ? "Retrieving…" : "Ask"}
            </button>
            <button className="btn" type="button" disabled={!hasCitations} onClick={() => setDrawerOpen(true)}>
              View evidence
            </button>
            <span style={{ color: "var(--ink-mute)", fontSize: 12 }}>{summaryLine}</span>
          </div>
          {error ? <p style={{ color: "crimson", marginTop: 10 }}>{error}</p> : null}
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>Answer</div>
          <p style={{ marginTop: 10, color: answer ? "var(--ink)" : "var(--ink-mute)", whiteSpace: "pre-wrap" }}>
            {answer || "Ask a question to generate an answer with citations."}
          </p>
          {hasCitations ? (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: "var(--ink-mute)", marginBottom: 6 }}>Top citation</div>
              <div className="card" style={{ padding: "12px 14px", background: "rgba(240,250,246,0.65)" }}>
                <div style={{ fontWeight: 800 }}>{citations[0].title || "Section"}</div>
                <div style={{ fontSize: 12, color: "var(--ink-mute)", marginTop: 2 }}>{citations[0].source}</div>
                <div style={{ marginTop: 8, fontSize: 13, color: "var(--ink)" }}>{citations[0].snippet}</div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <EvidenceDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Retrieved citations"
        citations={citations}
      />
    </div>
  );
}

