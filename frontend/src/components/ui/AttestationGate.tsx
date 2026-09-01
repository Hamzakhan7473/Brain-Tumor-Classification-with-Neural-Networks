import React, { useState } from "react";
import { DEFAULT_ATTESTATION_TEXT, canFinalize } from "./provenance.mjs";

type AttestationGateProps = {
  attested: boolean;
  attestedBy?: string | null;
  attestedAt?: string | null;
  disabled?: boolean;
  busy?: boolean;
  error?: string | null;
  onSubmit: (attestedBy: string, attestationText: string) => void | Promise<void>;
};

/**
 * Mandatory clinician attestation. Checkbox is never pre-checked.
 * Distinct from viewing the report and from electronic sign-off.
 */
export function AttestationGate({
  attested,
  attestedBy,
  attestedAt,
  disabled,
  busy,
  error,
  onSubmit,
}: AttestationGateProps): React.ReactElement {
  const [checked, setChecked] = useState(false);
  const [name, setName] = useState("");

  if (attested) {
    return (
      <div className="attestation-gate attestation-gate--done" data-testid="attestation-gate">
        <div className="attestation-gate-title">Clinician attestation recorded</div>
        <p className="text-ios-footnote" style={{ margin: "6px 0 0" }}>
          {attestedBy || "Clinician"} · {attestedAt || ""}
        </p>
      </div>
    );
  }

  const canSubmit = checked && name.trim().length > 0 && !disabled && !busy;

  return (
    <div className="attestation-gate" data-testid="attestation-gate">
      <div className="attestation-gate-title">Required before finalize / export</div>
      <p className="text-ios-footnote" style={{ color: "var(--ink-soft)", margin: "6px 0 10px" }}>
        This is a distinct clinician action — viewing the draft is not attestation. Automated
        validator gates still apply; this does not replace them.
      </p>
      <label className="attestation-gate-row">
        <input
          type="checkbox"
          data-testid="attestation-checkbox"
          checked={checked}
          disabled={disabled || busy}
          onChange={(e) => setChecked(e.target.checked)}
        />
        <span>{DEFAULT_ATTESTATION_TEXT}</span>
      </label>
      <label style={{ display: "block", marginTop: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Attested by</div>
        <input
          data-testid="attestation-name"
          value={name}
          disabled={disabled || busy}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name and credentials"
          style={{ width: "100%", padding: 8 }}
        />
      </label>
      {error ? <div className="app-text-error" style={{ marginTop: 8, fontSize: 13 }}>{error}</div> : null}
      <button
        type="button"
        className="attestation-gate-submit"
        data-testid="attestation-submit"
        disabled={!canSubmit}
        onClick={() => void onSubmit(name.trim(), DEFAULT_ATTESTATION_TEXT)}
      >
        {busy ? "Submitting…" : "Submit attestation"}
      </button>
    </div>
  );
}

export { canFinalize, DEFAULT_ATTESTATION_TEXT };
