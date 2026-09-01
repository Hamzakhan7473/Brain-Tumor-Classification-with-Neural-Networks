/** Shared clinician-attestation + provenance display helpers (no React). */

export const DEFAULT_ATTESTATION_TEXT =
  "I have reviewed the AI-generated content against the source measurements and confirm its accuracy";

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
 * @param {boolean} attested
 */
export function canFinalize(attested) {
  return Boolean(attested);
}
