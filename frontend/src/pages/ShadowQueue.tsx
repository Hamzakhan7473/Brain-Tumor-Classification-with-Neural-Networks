import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ShadowModeBanner from "../components/shadow/ShadowModeBanner";
import { assignShadowCase, fetchShadowQueue, predictApiDisplayBase, retryShadowCase } from "../lib/api";
import { IosButton, IosLinkButton } from "../components/ui/IosButton";
import "./ShadowQueue.css";

type Row = Record<string, unknown>;

function truncateUid(uid: string, n = 18): string {
  if (uid.length <= n) return uid;
  return `${uid.slice(0, n)}…`;
}

function relTime(iso: string | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function statusPill(status: string): string {
  const s = (status || "").toLowerCase();
  if (["queued", "processing"].includes(s)) return `sq-pill ${s}`;
  if (s === "review") return "sq-pill review";
  if (s === "complete") return "sq-pill complete";
  if (s === "flagged") return "sq-pill flagged";
  if (s === "failed") return "sq-pill failed";
  return "sq-pill review";
}

export default function ShadowQueue() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [kpis, setKpis] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [chip, setChip] = useState<"all" | "pending" | "flagged" | "failed">("all");
  const [search, setSearch] = useState("");
  const prevIds = useRef<Set<string>>(new Set());
  const [flashId, setFlashId] = useState<string | null>(null);

  const params = useMemo(() => {
    const p = new URLSearchParams();
    p.set("limit", "50");
    p.set("offset", "0");
    if (search.trim()) p.set("search", search.trim());
    if (chip === "pending") p.set("feedback", "pending");
    if (chip === "flagged") p.set("flagged", "true");
    if (chip === "failed") p.append("status", "failed");
    return p;
  }, [chip, search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchShadowQueue(params);
      const next = (data.items || []) as Row[];
      const ids = new Set(next.map((r) => String(r.study_uid || "")));
      for (const id of ids) {
        if (id && !prevIds.current.has(id)) {
          setFlashId(id);
          window.setTimeout(() => setFlashId(null), 1400);
          break;
        }
      }
      prevIds.current = ids;
      setItems(next);
      setTotal(Number(data.total || 0));
      setKpis(data.kpis || {});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const id = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(id);
  }, [load]);

  const exportCsv = async () => {
    const end = new Date();
    const start = new Date(Date.now() - 7 * 86400000);
    const root = predictApiDisplayBase();
    const q = `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&format=csv`;
    const key = ((import.meta.env.VITE_API_KEY as string | undefined) ?? "").trim();
    const url = `${root}/shadow/export?${q}`;
    const headers: Record<string, string> = {};
    if (key) headers["X-API-Key"] = key;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      window.alert(await res.text());
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `shadow_export_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const onRow = (uid: string) => {
    navigate(`/clinical-feedback?caseId=${encodeURIComponent(uid)}&fromQueue=1`);
  };

  const onAssign = async (e: React.MouseEvent, uid: string) => {
    e.stopPropagation();
    const rid = window.prompt("Radiologist id (e.g. rad_dr_reyes)");
    if (!rid) return;
    const name = window.prompt("Display name (e.g. Dr. Reyes)") || rid;
    await assignShadowCase(uid, { radiologist_id: rid, radiologist_name: name });
    void load();
  };

  const onRetry = async (e: React.MouseEvent, uid: string) => {
    e.stopPropagation();
    await retryShadowCase(uid);
    void load();
  };

  const listener = String(kpis.listener_status || "stale");
  const live = listener === "live";

  return (
    <div className="app-page shadow-queue-page">
      <div className="shadow-queue-inner">
      <ShadowModeBanner />

      <div className="sq-header-row">
        <div>
          <div className="sq-title">
            Shadow queue <span className="sq-phase">Phase B</span>
          </div>
          <p className="sq-sub">
            Review AI output against PACS-linked studies. Capture structured agreement for IRB / QMS evidence. Nothing
            here is prospective or patient-facing.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <IosButton variant="ghost" onClick={() => void exportCsv()}>
            Export CSV
          </IosButton>
          <IosLinkButton to="/upload" variant="primary">
            Manual upload
          </IosLinkButton>
        </div>
      </div>

      <div className="sq-kpis">
        <div className="sq-kpi">
          <div className="sq-kpi-label">PACS / ingest listener</div>
          <div className="sq-kpi-value" style={{ fontSize: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <span className={`sq-live-dot ${live ? "" : "stale"}`} aria-hidden />
            {live ? "Live" : "Stale"}
          </div>
          <div className="sq-kpi-sub">Last study {kpis.last_received ? relTime(String(kpis.last_received)) : "—"}</div>
        </div>
        <div className="sq-kpi">
          <div className="sq-kpi-label">Today</div>
          <div className="sq-kpi-value">{String(kpis.total_today ?? 0)}</div>
          <div className={`sq-kpi-sub${Number(kpis.delta_vs_yesterday) >= 0 ? " sq-kpi-sub--up" : ""}`}>
            Δ vs yesterday {String(kpis.delta_vs_yesterday ?? 0)}
          </div>
        </div>
        <div className="sq-kpi">
          <div className="sq-kpi-label">Pending feedback</div>
          <div className="sq-kpi-value">{String(kpis.pending_feedback ?? 0)}</div>
          <div className="sq-kpi-sub">{String(kpis.sla_breach_count ?? 0)} over 24h SLA</div>
        </div>
        <div className="sq-kpi">
          <div className="sq-kpi-label">Agreement (7d)</div>
          <div className="sq-kpi-value">
            {Math.round(Number(kpis.agreement_rate_7d || 0) * 1000) / 10}
            <span style={{ fontSize: 14, fontWeight: 700 }}>%</span>
          </div>
          <div className="sq-kpi-sub">Confirmed ÷ reviewed</div>
        </div>
        <div className="sq-kpi">
          <div className="sq-kpi-label">Mean inference</div>
          <div className="sq-kpi-value" style={{ fontSize: 18 }}>
            {String(kpis.mean_inference_ms_24h ?? 0)} ms
          </div>
          <div className="sq-kpi-sub">24h window · 2D + 3D jobs</div>
        </div>
      </div>

      <div className="card" style={{ padding: 16 }}>
        <div className="sq-toolbar">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input
              type="text"
              placeholder="Search study UID or site…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ minWidth: 200, maxWidth: 280 }}
            />
            <div className="sq-chips">
              {(
                [
                  ["all", "All"],
                  ["pending", "Pending review"],
                  ["flagged", "Flagged"],
                  ["failed", "Failed"],
                ] as const
              ).map(([k, label]) => (
                <button key={k} type="button" className={`sq-chip ${chip === k ? "active" : ""}`} onClick={() => setChip(k)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <IosButton variant="secondary" onClick={() => void load()} disabled={loading} loading={loading}>
              Refresh
            </IosButton>
          </div>
        </div>

        {error ? (
          <div style={{ color: "crimson", fontSize: 13, marginBottom: 10 }}>{error}</div>
        ) : null}

        {items.length === 0 && !loading ? (
          <div className="sq-empty">
            <div style={{ fontSize: 28, marginBottom: 8 }}>∅</div>
            <div style={{ fontWeight: 800, color: "var(--ink)" }}>No cases match your filters</div>
            <p style={{ marginTop: 8 }}>Adjust filters or ingest via POST /shadow/ingest (authenticated).</p>
            <IosButton variant="ghost" style={{ marginTop: 12 }} onClick={() => { setChip("all"); setSearch(""); }}>
              Reset filters
            </IosButton>
          </div>
        ) : (
          <div className="sq-table-wrap">
            <table className="sq-table">
              <thead>
                <tr>
                  <th>Study</th>
                  <th>Site</th>
                  <th>Status</th>
                  <th>AI label</th>
                  <th>Feedback</th>
                  <th>Assigned</th>
                  <th>Received</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  const uid = String(r.study_uid || "");
                  const site = String(r.site_id || "—");
                  const siteName = String(r.site_name || "");
                  const st = String(r.status || "—");
                  const mr = (r.model_run as Record<string, unknown> | undefined) || {};
                  const fb = (r.feedback as Record<string, unknown> | undefined) || {};
                  const asg = (r.assignment as Record<string, unknown> | undefined) || {};
                  const label = String(mr.label || "—");
                  const conf = typeof mr.confidence === "number" ? mr.confidence : Number(mr.confidence || 0);
                  const fbs = String(fb.status || "pending");
                  const assignee = String(asg.radiologist_name || "");
                  const received = String(r.received_at || "");
                  return (
                    <tr
                      key={uid}
                      className={`sq-row ${flashId === uid ? "flash" : ""}`}
                      onClick={() => uid && onRow(uid)}
                    >
                      <td>
                        <div className="sq-mono">{truncateUid(uid, 22)}</div>
                        <div style={{ fontSize: 11, color: "var(--ink-mute)", marginTop: 2 }}>
                          {String(r.modality || "MR")} · {String(r.sequence || "—")} · {String(r.slice_count ?? "—")} slices
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 700 }}>{siteName || site}</div>
                        <div className="sq-mono">{site}</div>
                      </td>
                      <td>
                        <span className={statusPill(st)}>{st}</span>
                      </td>
                      <td>
                        <div style={{ fontWeight: 700 }}>{label}</div>
                        <div className="sq-mono">{(conf * 100).toFixed(1)}%</div>
                      </td>
                      <td>
                        {fbs === "pending" ? "⏳ awaiting" : null}
                        {fbs === "confirmed" ? "✓ confirmed" : null}
                        {fbs === "disagreed" ? "✗ disagreed" : null}
                        {fbs === "needs_more_info" ? "↻ needs info" : null}
                        {fbs === "skipped" ? "— skipped" : null}
                        {!["pending", "confirmed", "disagreed", "needs_more_info", "skipped"].includes(fbs) ? fbs : null}
                      </td>
                      <td style={{ color: assignee ? "var(--ink)" : "var(--ink-mute)", fontStyle: assignee ? "normal" : "italic" }}>
                        {assignee || "Unassigned"}
                      </td>
                      <td className="sq-mono">{relTime(received)}</td>
                      <td className="sq-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="sq-icon-btn"
                          title="Review"
                          onClick={() =>
                            navigate(`/clinical-feedback?caseId=${encodeURIComponent(uid)}&fromQueue=1`)
                          }
                        >
                          ◎
                        </button>
                        <button type="button" className="sq-icon-btn" title="Assign" onClick={(e) => void onAssign(e, uid)}>
          ⧉
                        </button>
                        {st === "failed" ? (
                          <button type="button" className="sq-icon-btn" title="Retry" onClick={(e) => void onRetry(e, uid)}>
                            ↻
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ marginTop: 10, fontSize: 12, color: "var(--ink-mute)" }}>
          Showing {items.length} of {total} · auto-refresh 15s
        </div>
      </div>
      </div>
    </div>
  );
}
