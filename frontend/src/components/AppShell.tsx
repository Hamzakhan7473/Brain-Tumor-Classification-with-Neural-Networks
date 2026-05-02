import React, { useEffect, useState } from "react";
import { checkApiHealth, isFrontendApiKeyConfigured } from "../api/client";
import { IosNavBar } from "./layout/IosNavBar";

export default function AppShell(props: { children: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [apiBanner, setApiBanner] = useState<"ok" | "down" | "need_key">("ok");

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const h = await checkApiHealth();
      if (cancelled) return;
      if (!h.ok) {
        setApiBanner("down");
        return;
      }
      if (h.auth_required && !isFrontendApiKeyConfigured()) {
        setApiBanner("need_key");
        return;
      }
      setApiBanner("ok");
    };
    run();
    const t = window.setInterval(run, 45_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  return (
    <>
      {apiBanner === "down" ? (
        <div
          role="status"
          style={{
            background: "rgba(251, 191, 36, 0.25)",
            borderBottom: "1px solid rgba(245, 158, 11, 0.45)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--ink)",
          }}
        >
          <strong>Backend not reachable.</strong> Upload and reports need the API. From the project root run{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>./scripts/demo_local.sh</code>{" "}
          or{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>./scripts/run_api.sh</code>
          , then refresh this page.
        </div>
      ) : null}
      {apiBanner === "need_key" ? (
        <div
          role="status"
          style={{
            background: "rgba(96, 165, 250, 0.2)",
            borderBottom: "1px solid rgba(59, 130, 246, 0.35)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--ink)",
          }}
        >
          <strong>API key required.</strong> The server expects <code>X-API-Key</code>. Add{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>VITE_API_KEY</code> to{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>frontend/.env</code>{" "}
          (same value as backend <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>API_KEY</code>
          ), restart <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>npm run dev</code>.
        </div>
      ) : null}
      <IosNavBar moreOpen={moreOpen} setMoreOpen={setMoreOpen} />

      <div className="page">{props.children}</div>
    </>
  );
}

