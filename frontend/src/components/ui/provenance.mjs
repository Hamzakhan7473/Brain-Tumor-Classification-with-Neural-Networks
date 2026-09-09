/** Shared clinician-attestation + provenance display helpers (no React). */

export const ATTESTATION_TEXT_TEMPLATE =
  "I reviewed these statements against the source measurements for audit_id {id}.";

/**
 * @param {string | null | undefined} auditId
 */
export function attestationTextFor(auditId) {
  const id = String(auditId || "unbound").trim() || "unbound";
  return ATTESTATION_TEXT_TEMPLATE.replace("{id}", id);
}

/** Fallback when no measurement audit_id is bound (free-text content attest). */
export const DEFAULT_ATTESTATION_TEXT = attestationTextFor("unbound");

export const VALIDATOR_STATUSES = /** @type {const} */ (["passed", "warnings", "failed"]);

/**
 * @param {string | null | undefined} status
 * @returns {"passed" | "warnings" | "failed"}
 */
export function provenanceTone(status) {
  if (status === "failed") return "failed";
  if (status === "warnings") return "warnings";
  return "passed";
}

/**
 * @param {string | null | undefined} slug  e.g. claude-sonnet-4-6
 */
export function humanModelName(slug) {
  const s = (slug || "").trim();
  if (!s) return "Claude";
  if (/claude-sonnet-4-6/i.test(s)) return "Claude Sonnet 4.6";
  return s
    .replace(/^claude-/, "Claude ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * @param {{ generated_by?: string, grounding_score?: number | null, validator_status?: string } | null | undefined} provenance
 */
export function provenanceCaption(provenance) {
  if (!provenance) return "AI-generated";
  const model = humanModelName(provenance.generated_by);
  const score = provenance.grounding_score;
  const scoreBit =
    typeof score === "number" && Number.isFinite(score) ? ` · Grounding score: ${score.toFixed(2)}` : "";
  return `AI-generated · ${model}${scoreBit}`;
}

/**
 * Finalize/sign is allowed only after a successful attestation submit.
 * Demo / JPG-as-MRI path and 2D-only triage (export_allowed=false) cannot be signed or exported.
 * @param {boolean} attested
 * @param {string | null | undefined} [ingestPath]
 * @param {boolean | null | undefined} [exportAllowed]
 */
export function canFinalize(attested, ingestPath, exportAllowed) {
  if (String(ingestPath || "").toLowerCase() === "demo") return false;
  if (exportAllowed === false) return false;
  return Boolean(attested);
}
