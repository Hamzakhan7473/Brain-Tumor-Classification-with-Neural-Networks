/// <reference types="vite/client" />

declare module "*.mjs" {
  export const DEFAULT_ATTESTATION_TEXT: string;
  export const ATTESTATION_TEXT_TEMPLATE: string;
  export function attestationTextFor(auditId?: string | null): string;
  export function provenanceTone(status?: string | null): "passed" | "warnings" | "failed";
  export function humanModelName(slug?: string | null): string;
  export function provenanceCaption(
    provenance?: {
      generated_by?: string;
      grounding_score?: number | null;
      validator_status?: string;
    } | null,
  ): string;
  export function canFinalize(
    attested: boolean,
    ingestPath?: string | null,
    exportAllowed?: boolean | null,
  ): boolean;
}


