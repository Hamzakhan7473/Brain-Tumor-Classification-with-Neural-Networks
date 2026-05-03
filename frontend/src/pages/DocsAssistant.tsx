import React, { useEffect, useRef, useState } from "react";
import { askDocs, flagDocsInaccurate, listIndexedDocs, type DocsAssistantAnswer, type DocsManifestResponse } from "@/lib/docsApi";
import "./DocsAssistant.css";

const SUGGESTED_QUESTIONS = [
  "What is the Fazekas grading scale?",
  "When should I escalate a stroke finding?",
  "What is the WMH validation protocol for v1?",
  "What FDA pathway applies to our device?",
];

function SearchIcon() {
  return (
    <svg className="da-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3-3" strokeLinecap="round" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M5 12h12M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ConfidenceIndicator({ level }: { level: string }) {
  const cls = level === "high" || level === "med" || level === "low" ? level : "low";
  return (
    <span className={`da-confidence ${cls}`}>
      <span className="da-confidence-dot" aria-hidden />
      Confidence: {level}
    </span>
  );
}

export default function DocsAssistant() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [reasoningStep, setReasoningStep] = useState(0);
  const [answer, setAnswer] = useState<DocsAssistantAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [docManifest, setDocManifest] = useState<DocsManifestResponse | null>(null);

  const stepIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const citationRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    listIndexedDocs().then(setDocManifest).catch(() => setDocManifest(null));
  }, []);

  useEffect(() => {
    return () => {
      if (stepIntervalRef.current) clearInterval(stepIntervalRef.current);
    };
  }, []);

  const runAsk = async (text?: string) => {
    const q = (text ?? question).trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setAnswer(null);
    setReasoningStep(0);
    citationRefs.current = new Map();

    if (stepIntervalRef.current) clearInterval(stepIntervalRef.current);
    stepIntervalRef.current = setInterval(() => {
      setReasoningStep((s) => Math.min(s + 1, 2));
    }, 600);

    try {
      const result = await askDocs(q);
      if (stepIntervalRef.current) {
        clearInterval(stepIntervalRef.current);
        stepIntervalRef.current = null;
      }
      setAnswer(result);
    } catch (e: unknown) {
      if (stepIntervalRef.current) {
        clearInterval(stepIntervalRef.current);
        stepIntervalRef.current = null;
      }
      setError(e instanceof Error ? e.message : "Failed to get answer");
    } finally {
      setLoading(false);
    }
  };

  const scrollToCitation = (idx: number) => {
    const el = citationRefs.current.get(idx);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("cite-highlight");
    window.setTimeout(() => el?.classList.remove("cite-highlight"), 1200);
  };

  const renderAnswer = (text: string, citations: DocsAssistantAnswer["citations"]) => {
    const parts = text.split(/(\[\d+\])/g);
    return parts.map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (match) {
        const idx = parseInt(match[1], 10) - 1;
        if (idx >= 0 && idx < citations.length) {
          return (
            <button
              key={`cite-${i}`}
              type="button"
              className="cite-chip"
              title={citations[idx].doc_name}
              onClick={() => scrollToCitation(idx)}
            >
              {match[1]}
            </button>
          );
        }
      }
      return <span key={`t-${i}`}>{part}</span>;
    });
  };

  const handleCopyWithCitations = () => {
    if (!answer) return;
    const cited = answer.citations
      .map((c, i) => `[${i + 1}] ${c.doc_name} — ${c.section}, p.${c.page}`)
      .join("\n");
    const full = `${answer.answer}\n\nCitations:\n${cited}\n\nAudit: ${answer.audit_id}`;
    void navigator.clipboard.writeText(full);
  };

  const handleFlagInaccurate = async () => {
    if (!answer) return;
    const reason = window.prompt("What is inaccurate? (this will be logged for review)");
    if (!reason) return;
    try {
      await flagDocsInaccurate({ audit_id: answer.audit_id, reason, question });
      window.alert("Thanks — flagged for review.");
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Could not submit feedback");
    }
  };

  const docCount = docManifest?.documents?.length ?? 0;

  return (
    <div className="docs-assistant">
      <div className="da-header">
        <div>
          <h1>Docs Assistant</h1>
          <p>
            Ask questions over your clinical workflows, SOPs, and validation docs. Citations preserve an auditable trail
            (PageIndex primary; Mongo vector search fallback).
          </p>
        </div>
        <span className="badge-pageindex">PageIndex</span>
      </div>

      <div className="da-layout">
        <div className="da-main-card">
          <div className="da-search-bar">
            <div className="da-input-wrap">
              <SearchIcon />
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runAsk();
                }}
                placeholder="Ask anything about your SOPs, validation docs, or workflow…"
                disabled={loading}
                aria-label="Question"
              />
              <button type="button" className="da-ask-btn" onClick={() => void runAsk()} disabled={!question.trim() || loading}>
                Ask <ArrowIcon />
              </button>
            </div>

            {!answer && !loading && (
              <div className="da-suggestions">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    type="button"
                    key={q}
                    className="da-suggest"
                    onClick={() => {
                      setQuestion(q);
                      void runAsk(q);
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>

          {loading && (
            <div className="da-reasoning">
              <div className="da-spinner" />
              <span className="da-reasoning-label">Reasoning over document tree</span>
              <span className="da-reasoning-step">
                {["Searching index", "Selecting relevant sections", "Composing answer with citations"][reasoningStep] ??
                  "Composing"}
              </span>
            </div>
          )}

          <div className="da-answer-area">
            {!answer && !loading && !error && (
              <div className="da-empty">
                <SearchIcon />
                <p style={{ marginTop: 12 }}>Ask a question to retrieve cited answers from your indexed knowledge base.</p>
              </div>
            )}

            {error && (
              <div className="da-error">
                <strong>Error:</strong> {error}
                <div>
                  <button type="button" className="btn" onClick={() => void runAsk()}>
                    Try again
                  </button>
                </div>
              </div>
            )}

            {answer && (
              <div className="da-answer">
                <div className="da-answer-meta">
                  <ConfidenceIndicator level={answer.confidence} />
                  <span className="da-tokens">
                    {answer.tokens_used} tokens · {answer.citations.length} sources · {answer.latency_ms} ms
                  </span>
                </div>

                <div className="da-answer-text">{renderAnswer(answer.answer, answer.citations)}</div>

                {answer.reasoning_trace?.length ? (
                  <div style={{ marginTop: 12, fontSize: 12, color: "var(--ink-mute)" }}>
                    {answer.reasoning_trace.map((t, j) => (
                      <div key={j}>• {t}</div>
                    ))}
                  </div>
                ) : null}

                <div className="da-actions">
                  <button type="button" className="primary" onClick={handleCopyWithCitations}>
                    Copy with citations
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard.writeText(answer.audit_id);
                    }}
                  >
                    Copy audit id
                  </button>
                  <button type="button" onClick={() => void handleFlagInaccurate()}>
                    Flag inaccurate
                  </button>
                  <span className="da-audit-id">audit {answer.audit_id}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="da-right">
          <div className="da-cite-card">
            <div className="da-cite-head">
              <span className="da-label">Evidence</span>
              <h3>
                {answer ? `${answer.citations.length} citation${answer.citations.length === 1 ? "" : "s"}` : "No citations yet"}
              </h3>
            </div>

            {!answer && (
              <p className="da-cite-empty">
                Citations appear here after you ask a question. Click any citation chip in the answer to jump to its source.
              </p>
            )}

            {answer && (
              <div className="da-cite-list">
                {answer.citations.map((c, i) => (
                  <div
                    key={`${c.doc_id}-${i}`}
                    className="da-cite-item"
                    ref={(el) => {
                      if (el) citationRefs.current.set(i, el);
                    }}
                  >
                    <div className="da-cite-head-row">
                      <div className="da-cite-num">{i + 1}</div>
                      <div style={{ minWidth: 0 }}>
                        <div className="da-cite-source" title={c.doc_name}>
                          {c.doc_name}
                        </div>
                        <div className="da-cite-loc">
                          {c.section} · p. {c.page}
                        </div>
                      </div>
                    </div>
                    <p className="da-cite-snippet">{c.snippet}</p>
                    <div className="da-cite-relevance">
                      <span>relevance {Math.round(c.relevance * 100)}%</span>
                      <div className="da-relevance-bar">
                        <div style={{ width: `${Math.min(100, c.relevance * 100)}%` }} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {docManifest ? (
            <div className="da-kb-card">
              <div className="da-kb-row">
                <span>Knowledge base</span>
                <span className="da-kb-live">{docManifest.indexed ? "● indexed" : "○ not indexed"}</span>
              </div>
              <div className="da-kb-row">
                <span>Documents</span>
                <span>{docCount}</span>
              </div>
              <div className="da-kb-row">
                <span>Last updated</span>
                <span>{docManifest.updated_at ?? "—"}</span>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
