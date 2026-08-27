import React, { useEffect, useState } from "react";
import { checkApiHealth, isFrontendApiKeyConfigured } from "../api/client";
import { AppThemeProvider } from "../context/AppThemeContext";
import { CommandPalette, useCommandPalette } from "./layout/CommandPalette";
import { IosNavBar } from "./layout/IosNavBar";
import { APP_WORKFLOW_TILES, GlassTilePanel } from "./ui/GlassTilePanel";

export default function AppShell(props: { children: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [apiBanner, setApiBanner] = useState<"ok" | "down" | "need_key">("ok");
  const cmdk = useCommandPalette();

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
    <AppThemeProvider>
      {apiBanner === "down" ? (
        <div className="app-banner app-banner--warn" role="status">
          <strong>Backend not reachable.</strong> Upload and reports need the API. From the project root run{" "}
          <code>./scripts/demo_local.sh</code> or <code>./scripts/run_api.sh</code>, then refresh.
        </div>
      ) : null}
      {apiBanner === "need_key" ? (
        <div className="app-banner app-banner--info" role="status">
          <strong>API key required.</strong> Add <code>VITE_API_KEY</code> to <code>frontend/.env</code> (same as backend{" "}
          <code>API_KEY</code>), restart <code>npm run dev</code>.
        </div>
      ) : null}
      <IosNavBar moreOpen={moreOpen} setMoreOpen={setMoreOpen} onOpenCommandPalette={() => cmdk.setOpen(true)} />
      <CommandPalette open={cmdk.open} onClose={() => cmdk.setOpen(false)} />
      <div className="page">
        <div className="app-shell-tilebar">
          <GlassTilePanel variant="app" tiles={APP_WORKFLOW_TILES} aria-label="Workflow shortcuts" />
        </div>
        {props.children}
      </div>
    </AppThemeProvider>
  );
}
