/** 2D 4-class CNN is research triage, never a signed diagnosis. */

export const TRIAGE_BANNER = "Research / protocol-check triage — not a signed finding";

export function triageSuggestedLine(cls: string): string {
  return `Slice-wise research classifier suggested class ${cls}; not used for measurement or signature.`;
}
