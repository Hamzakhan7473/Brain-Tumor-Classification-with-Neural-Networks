/**
 * Imaging-model picker. These are Keras CNNs / U-Net — not the Bedrock LLM.
 * Bedrock only writes report prose after a scan is classified.
 */

import React, { useEffect, useState } from "react";
import type { RegistryModelRow } from "../../api/client";
import { listRegistryModels } from "../../api/client";

const DISPLAY_NAME: Record<string, string> = {
  custom_cnn: "Custom CNN",
  transfer: "Transfer",
  xception: "Xception",
  unet_3d_wmh: "WMH U-Net",
};

type ModelSelectorProps = {
  value: string;
  onChange: (name: string) => void;
  apiKey?: string;
};

function Skeleton() {
  return (
    <div className="model-pill-strip" aria-busy>
      {[0, 1, 2].map((i) => (
        <div key={i} className="model-skel-pill ios-skel-pulse ios-animated" />
      ))}
    </div>
  );
}

export default function ModelSelector({
  value,
  onChange,
  apiKey,
}: ModelSelectorProps): React.ReactElement {
  const envKey =
    typeof import.meta !== "undefined"
      ? (import.meta.env.VITE_API_KEY as string | undefined)?.trim() ?? ""
      : "";
  const storeKey =
    typeof window !== "undefined" ? window.localStorage.getItem("api_key")?.trim() ?? "" : "";
  const resolvedKey = (apiKey?.trim() || envKey || storeKey || "").trim();

  const [rows, setRows] = useState<RegistryModelRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchFailed, setFetchFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listRegistryModels(resolvedKey || undefined);
        if (cancelled) return;
        setRows(Array.isArray(data) ? data : []);
        setFetchFailed(false);
      } catch {
        if (cancelled) return;
        setRows([]);
        setFetchFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resolvedKey]);

  const loaded = rows.filter((m) => m.loaded !== false);
  const loadedKey = loaded.map((m) => m.name).join(",");

  useEffect(() => {
    if (loading || !loadedKey) return;
    const names = loadedKey.split(",");
    if (!names.includes(value)) {
      onChange(names[0]);
    }
    // Intentionally omit onChange — parent passes an inline handler.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, loadedKey, value]);

  return (
    <div style={{ marginBottom: 12 }}>
      <label className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ display: "block", marginBottom: 8 }}>
        Imaging model
      </label>
      {loading ? (
        <Skeleton />
      ) : loaded.length === 0 ? (
        <p className="text-ios-caption1 font-ios text-ns-muted" style={{ margin: 0, lineHeight: 1.45 }}>
          {fetchFailed
            ? "Could not reach the model registry. Start the API, then refresh."
            : "No Keras checkpoints are loaded. Place .keras files under models/saved/ — Bedrock does not replace these."}
        </p>
      ) : (
        <div className="model-pill-strip">
          {loaded.map((m) => {
            const selected = value === m.name;
            return (
              <button
                key={m.name}
                type="button"
                onClick={() => onChange(m.name)}
                className={`model-pill ${selected ? "model-pill--active" : ""} font-ios ios-animated`.trim()}
                title={m.description}
              >
                <span>{DISPLAY_NAME[m.name] ?? m.name}</span>
                {Number(m.dims) === 3 ? <span className="model-pill-badge">3D</span> : null}
              </button>
            );
          })}
        </div>
      )}
      <p className="text-ios-caption2 font-ios text-ns-muted" style={{ marginTop: 8, lineHeight: 1.4 }}>
        {value === "unet_3d_wmh"
          ? "3D WMH segmentation needs a NIfTI volume (.nii / .nii.gz). Report text still comes from Bedrock after inference."
          : "These classify or segment the scan. Claude on AWS Bedrock only drafts the written report — it is not a fifth imaging model."}
      </p>
    </div>
  );
}
