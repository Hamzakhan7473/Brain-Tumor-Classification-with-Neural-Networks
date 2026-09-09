import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CaseSummary, formatApiConnectionHint, getMetrics, listCases, MetricsResponse } from "../api/client";
import { DashboardInsights, type DashboardInsight } from "../components/ui/DashboardInsights";
import { DashboardTableSkeleton } from "../components/ui/DashboardSkeleton";
import { IosLinkButton } from "../components/ui/IosButton";
import { TRIAGE_BANNER } from "../lib/triageCopy";
import "./Dashboard.css";

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

export default function Dashboard() {
  const [stored, setStored] = useState<StoredPrediction | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<string>("pending");
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    const raw = sessionStorage.getItem("lastPrediction");
    if (raw) {
      try {
        setStored(JSON.parse(raw) as StoredPrediction);
      } catch {
        // ignore
      }
    }
    const fb = sessionStorage.getItem("lastFeedbackStatus");
    if (fb) setFeedbackStatus(fb);
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [c, m] = await Promise.all([listCases({ limit: 25 }), getMetrics()]);
        if (!mounted) return;
        setCases(c);
        setMetrics(m);
      } catch (e) {
        if (!mounted) return;
        const raw = e instanceof Error ? e.message : String(e);
        setError(formatApiConnectionHint(raw));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const filteredCases = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter((c) => (c.study_instance_uid || "").toLowerCase().includes(q) || (c.site_id || "").toLowerCase().includes(q));
  }, [cases, filter]);

  const pending = filteredCases.filter((c) => (c.feedback_status || "pending") === "pending");

  const totalCases = metrics?.total_cases ?? (stored ? 1 : 0);
  const correctedCount =
    (metrics?.corrected ?? 0) + (metrics?.unclear ?? 0) ||
    (stored && (feedbackStatus === "wrong_class" || feedbackStatus === "unclear") ? 1 : 0);

  const insights = useMemo((): DashboardInsight[] => {
    const list: DashboardInsight[] = [];

    if (pending.length > 0) {
      list.push({
        id: "pending-feedback",
        title: `${pending.length} case${pending.length === 1 ? "" : "s"} need feedback`,
        description: "Submit radiologist agreement for shadow QA and trial metrics.",
        to: "/clinical-feedback",
        cta: "Review now",
        tone: "action",
      });
    }

    if (stored?.study_instance_uid) {
      list.push({
        id: "resume-case",
        title: "Resume last session",
        description: `${stored.filename || "Scan"} · ${TRIAGE_BANNER}. Suggested class (research): ${stored.prediction?.label || "—"}`,
        to: `/cases/${encodeURIComponent(stored.study_instance_uid)}`,
        cta: "Open case",
      });
    }

    if (totalCases === 0 && !stored) {
      list.push({
        id: "first-upload",
        title: "Start your first read",
        description: "Upload a brain MRI or WMH volume to run inference and generate a structured report.",
        to: "/upload",
        cta: "Upload scan",
        tone: "action",
      });
    } else {
      list.push({
        id: "bicr",
        title: "BICR dual-read ready",
        description: "Independent reader slots, adjudication, and time-point lock for trial imaging.",
        to: "/bicr-review",
        cta: "Open BICR",
      });
    }

    if (correctedCount > 0) {
      list.push({
        id: "corrections",
        title: `${correctedCount} corrected / unclear`,
        description: "Review disagreement patterns persisted for QA metrics.",
        to: "/shadow-queue",
        cta: "Shadow queue",
        tone: "muted",
      });
    }

    return list.slice(0, 3);
  }, [correctedCount, pending.length, stored, totalCases]);

  return (
    <div className="dashboard-page">
      <div className="dashboard-inner">
        <header className="dashboard-header">
          <div className="dashboard-header-row">
            <div>
              <h1>Dashboard</h1>
              <p>Actionable overview for imaging AI workflows — press ⌘K to jump anywhere.</p>
            </div>
            <div className="dashboard-header-actions">
              <IosLinkButton to="/upload" variant="primary" className="dashboard-header-btn">
                New scan
              </IosLinkButton>
              <IosLinkButton to="/shadow-queue" variant="ghost" className="dashboard-header-btn">
                Shadow queue
              </IosLinkButton>
            </div>
          </div>
        </header>

        <DashboardInsights insights={insights} loading={loading} />

        <div className="dashboard-metrics">
          <div className="dashboard-metric">
            <div className="dashboard-metric-label">Total cases</div>
            <div className="dashboard-metric-value">
              {loading ? "—" : totalCases}
            </div>
          </div>
          <div className="dashboard-metric">
            <div className="dashboard-metric-label">Feedback submitted</div>
            <div className="dashboard-metric-value">
              {loading ? "—" : metrics?.total_feedback ?? (feedbackStatus !== "pending" && stored ? 1 : 0)}
            </div>
          </div>
          <div className="dashboard-metric">
            <div className="dashboard-metric-label">Corrected / unclear</div>
            <div className="dashboard-metric-value">{loading ? "—" : correctedCount}</div>
          </div>
        </div>

        <section className="dashboard-panel">
          <div className="dashboard-panel-head">
            <h2>Cases</h2>
            <input
              type="text"
              className="dashboard-search"
              placeholder="Search by study UID or site…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <IosLinkButton to="/upload" variant="primary" className="dashboard-panel-btn">
              New scan
            </IosLinkButton>
          </div>

          {error ? <div className="dashboard-error">{error}</div> : null}

          {loading ? (
            <DashboardTableSkeleton />
          ) : (
            <div className="dashboard-table-wrap">
              <table className="dashboard-table">
                <thead>
                  <tr>
                    <th>Study UID</th>
                    <th>Site</th>
                    <th>Model</th>
                    <th>Label</th>
                    <th>Conf</th>
                    <th>Feedback</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCases.map((c) => (
                    <tr key={c.study_instance_uid}>
                      <td>
                        <Link to={`/cases/${c.study_instance_uid}`}>{c.study_instance_uid}</Link>
                      </td>
                      <td>{c.site_id || "—"}</td>
                      <td>{c.model || "—"}</td>
                      <td>{c.label || "—"}</td>
                      <td>{typeof c.confidence === "number" ? `${(c.confidence * 100).toFixed(1)}%` : "—"}</td>
                      <td>
                        {(c.feedback_status || "pending") === "pending" ? (
                          <span className="dashboard-status-pending">Pending</span>
                        ) : (
                          <span className="dashboard-status-done">{c.feedback_status}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!filteredCases.length ? (
                    <tr>
                      <td colSpan={6} className="dashboard-empty">
                        No cases found.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="dashboard-panel">
          <h2 className="dashboard-panel-subtitle">Pending feedback</h2>
          {!pending.length ? (
            <p className="dashboard-muted">No pending cases.</p>
          ) : (
            <ul className="dashboard-pending-list">
              {pending.slice(0, 8).map((c) => (
                <li key={c.study_instance_uid} className="dashboard-pending-item">
                  <div className="dashboard-pending-meta">
                    <Link to={`/cases/${c.study_instance_uid}`}>{c.study_instance_uid}</Link>
                    <span>
                      {" "}
                      · {c.site_id || "—"} · {c.label || "—"}
                    </span>
                  </div>
                  <IosLinkButton to="/clinical-feedback" variant="secondary" size="sm" className="dashboard-panel-btn">
                    Open feedback
                  </IosLinkButton>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
