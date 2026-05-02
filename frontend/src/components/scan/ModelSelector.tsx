/**
 * Model pills use global palette: surface / line / ink-soft inactive; green-600 active;
 * 3D badge tint: green-500 mix backgrounds, green-600 label text (accent lane).
 */

import React, { useEffect, useState } from "react";
import type { RegistryModelRow } from "../../api/client";
import { listRegistryModels } from "../../api/client";

const FALLBACK: RegistryModelRow[] = [
  {
    name: "custom_cnn",
    description: "Custom CNN — 4-class classifier",
    input_shape: [224, 224, 3],
    dims: 2,
    classes: ["glioma", "meningioma", "pituitary", "notumor"],
    task: "classification",
    loaded: true,
  },
  {
    name: "transfer",
    description: "Transfer learning — EfficientNet backbone",
    input_shape: [224, 224, 3],
    dims: 2,
    classes: ["glioma", "meningioma", "pituitary", "notumor"],
    task: "classification",
    loaded: true,
  },
  {
    name: "xception",
    description: "Xception — 4-class classifier",
    input_shape: [299, 299, 3],
    dims: 2,
    classes: ["glioma", "meningioma", "pituitary", "notumor"],
    task: "classification",
    loaded: true,
  },
  {
    name: "unet_3d_wmh",
    description: "3D U-Net WMH segmentation",
    input_shape: [96, 96, 96, 2],
    dims: 3,
    classes: ["background", "wmh_lesion"],
    task: "segmentation",
    loaded: true,
  },
];

type ModelSelectorProps = {
  value: string;
  onChange: (name: string) => void;
  apiKey?: string;
};

function Skeleton() {
  return (
    <div className="model-pill-strip" aria-busy>
      {[0, 1, 2, 3].map((i) => (
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

  const [rows, setRows] = useState<RegistryModelRow[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listRegistryModels(resolvedKey || undefined);
        if (!cancelled) setRows(data.length ? data : FALLBACK);
      } catch {
        if (!cancelled) setRows(FALLBACK);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resolvedKey]);

  const list = rows ?? FALLBACK;

  return (
    <div style={{ marginBottom: 12 }}>
      <label className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ display: "block", marginBottom: 8 }}>
        Model
      </label>
      {loading ? (
        <Skeleton />
      ) : (
        <div className="model-pill-strip">
          {list.map((m) => {
            const disabled = m.loaded === false;
            const selected = value === m.name;
            return (
              <button
                key={m.name}
                type="button"
                disabled={disabled}
                onClick={() => onChange(m.name)}
                className={`model-pill ${selected ? "model-pill--active" : ""} font-ios ios-animated`.trim()}
                style={{ opacity: disabled ? 0.45 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
                title={m.description}
              >
                <span>{m.name}</span>
                {Number(m.dims) === 3 ? <span className="model-pill-badge">3D</span> : null}
              </button>
            );
          })}
        </div>
      )}
      {value === "unet_3d_wmh" ? (
        <p
          className="text-ios-caption2 font-ios text-ns-muted"
          style={{
            marginTop: 8,
            lineHeight: 1.35,
          }}
        >
          3D model requires NIfTI file (.nii or .nii.gz)
        </p>
      ) : null}
    </div>
  );
}
