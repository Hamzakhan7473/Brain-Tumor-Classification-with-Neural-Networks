import React, { useMemo } from "react";
import type { ClinicalContextPayload } from "../../types/scan";

const SEX_OPTS = ["M", "F", "Other"] as const;
const TRI = ["yes", "no", "unknown"] as const;

type Props = {
  value: ClinicalContextPayload;
  onChange: (next: ClinicalContextPayload) => void;
};

export function isClinicalContextComplete(c: ClinicalContextPayload): boolean {
  const ageNum = c.age.trim() === "" ? NaN : Number(c.age);
  const ageOk = Number.isFinite(ageNum) && ageNum >= 0 && ageNum <= 120;
  return (
    ageOk &&
    c.sex.trim() !== "" &&
    c.indication.trim().length > 3 &&
    c.prior_stroke.trim() !== "" &&
    c.hypertension.trim() !== ""
  );
}

export function clinicalContextToApiJson(c: ClinicalContextPayload): Record<string, unknown> {
  const age = Number(c.age);
  return {
    age: Number.isFinite(age) ? Math.round(age) : null,
    sex: c.sex,
    indication: c.indication.trim(),
    prior_stroke: c.prior_stroke,
    hypertension: c.hypertension,
    prior_imaging: c.prior_imaging || "unknown",
  };
}

/** Required clinical demographics before NeuroSight accepts an upload for analysis. */
export default function ClinicalContextForm({ value, onChange }: Props): React.ReactElement {
  const complete = useMemo(() => isClinicalContextComplete(value), [value]);

  const field = (
    label: string,
    el: React.ReactNode,
    required?: boolean,
  ): React.ReactElement => (
    <label
      style={{ display: "flex", flexDirection: "column", gap: 4, fontFamily: "var(--font-ios, system-ui)" }}
    >
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-mid)", letterSpacing: "0.03em" }}>
        {label}
        {required ? " *" : ""}
      </span>
      {el}
    </label>
  );

  return (
    <div
      className="ns-card-frame ns-bg-card-solid ios-soft-shadow rounded-ios-lg ios-pad-card"
      style={{ display: "flex", flexDirection: "column", gap: 12 }}
    >
      <div className="text-ios-footnote font-semibold font-ios text-ns-heading">
        Clinical context
      </div>
      <div className="text-ios-caption1 font-ios text-ns-muted">
        Context is logged with each inference for attribution; convolutional stacks remain fixed.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
        {field(
          "Patient age (years)",
          <input
            type="number"
            min={0}
            max={120}
            className="text-ios-caption1 font-ios"
            style={{
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: "8px 10px",
              background: "var(--surface)",
            }}
            value={value.age}
            onChange={(e) => onChange({ ...value, age: e.target.value })}
          />,
          true,
        )}
        {field(
          "Sex",
          <select
            className="text-ios-caption1 font-ios"
            style={{
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: "8px 10px",
              background: "var(--surface)",
            }}
            value={value.sex}
            onChange={(e) => onChange({ ...value, sex: e.target.value })}
          >
            <option value="">Select…</option>
            {SEX_OPTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>,
          true,
        )}
      </div>
      {field(
        "Indication / reason for study",
        <textarea
          className="text-ios-caption1 font-ios"
          rows={2}
          style={{
            borderRadius: "var(--radius-ios)",
            border: "1px solid var(--line)",
            padding: "8px 10px",
            background: "var(--surface)",
            resize: "vertical",
          }}
          value={value.indication}
          placeholder="Brief clinical question"
          onChange={(e) => onChange({ ...value, indication: e.target.value })}
        />,
        true,
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
        {field(
          "Prior stroke / TIA",
          <select
            className="text-ios-caption1 font-ios"
            style={{
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: "8px 10px",
              background: "var(--surface)",
            }}
            value={value.prior_stroke}
            onChange={(e) => onChange({ ...value, prior_stroke: e.target.value })}
          >
            <option value="">Select…</option>
            {TRI.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>,
          true,
        )}
        {field(
          "Hypertension",
          <select
            className="text-ios-caption1 font-ios"
            style={{
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: "8px 10px",
              background: "var(--surface)",
            }}
            value={value.hypertension}
            onChange={(e) => onChange({ ...value, hypertension: e.target.value })}
          >
            <option value="">Select…</option>
            {TRI.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>,
          true,
        )}
        {field(
          "Prior imaging available",
          <select
            className="text-ios-caption1 font-ios"
            style={{
              borderRadius: "var(--radius-ios)",
              border: "1px solid var(--line)",
              padding: "8px 10px",
              background: "var(--surface)",
            }}
            value={value.prior_imaging}
            onChange={(e) => onChange({ ...value, prior_imaging: e.target.value })}
          >
            <option value="unknown">Unknown</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>,
        )}
      </div>
      {!complete ? (
        <div className="text-ios-caption2 font-ios text-ns-val-danger">
          Complete all required clinical fields before attaching a scan.
        </div>
      ) : null}
    </div>
  );
}

export function emptyClinicalContext(): ClinicalContextPayload {
  return {
    age: "",
    sex: "",
    indication: "",
    prior_stroke: "",
    hypertension: "",
    prior_imaging: "unknown",
  };
}
