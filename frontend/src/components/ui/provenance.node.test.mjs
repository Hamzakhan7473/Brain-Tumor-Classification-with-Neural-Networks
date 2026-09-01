import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_ATTESTATION_TEXT,
  canFinalize,
  provenanceCaption,
  provenanceTone,
} from "./provenance.mjs";

test("finalize stays disabled until attestation is completed", () => {
  assert.equal(canFinalize(false), false);
  assert.equal(canFinalize(true), true);
});

test("provenance caption and tone for validator_status values", () => {
  assert.equal(provenanceTone("passed"), "passed");
  assert.equal(provenanceTone("warnings"), "warnings");
  assert.equal(provenanceTone("failed"), "failed");
  assert.equal(
    provenanceCaption({
      generated_by: "claude-sonnet-4-6",
      grounding_score: 0.87,
      validator_status: "passed",
    }),
    "AI-generated · Claude Sonnet 4.6 · Grounding score: 0.87",
  );
  assert.equal(
    provenanceCaption({ generated_by: "claude-sonnet-4-6", validator_status: "warnings" }),
    "AI-generated · Claude Sonnet 4.6",
  );
  assert.match(DEFAULT_ATTESTATION_TEXT, /source measurements/);
});

test("provenance badge class follows validator_status", () => {
  assert.equal(provenanceTone("passed"), "passed");
  assert.equal(provenanceTone("warnings"), "warnings");
  assert.equal(provenanceTone("failed"), "failed");
  assert.equal(provenanceTone(undefined), "passed");
  assert.equal(provenanceTone("unknown"), "passed");
});
