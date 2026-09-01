#!/usr/bin/env python3
"""
Create an Amazon Bedrock Guardrail with contextual grounding / relevance filters.

Does not configure content filters or denied topics — those are a separate concern.

Usage (from project root):
  python scripts/create_bedrock_guardrail.py
  python scripts/create_bedrock_guardrail.py --grounding-threshold 0.8 --relevance-threshold 0.7

Env:
  AWS_REGION (default us-east-1)
  BEDROCK_GROUNDING_THRESHOLD (default 0.75)
  BEDROCK_RELEVANCE_THRESHOLD (default 0.75)

The script prints the guardrail id/version. Paste them into .env:
  BEDROCK_GUARDRAIL_ID=<id>
  BEDROCK_GUARDRAIL_VERSION=DRAFT

Filters use action=NONE so scores are returned for human-review flagging
without Bedrock blocking the model output. The deterministic validator in
src/llm/validation.py remains the pass/fail authority.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _threshold(cli_value: float | None, env_name: str, default: float) -> float:
    if cli_value is not None:
        return float(cli_value)
    raw = (os.environ.get(env_name) or "").strip()
    if raw:
        return float(raw)
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="neurosight-clinical-grounding")
    parser.add_argument("--description", default="NeuroSight contextual grounding for report/explanation prose.")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or "us-east-1")
    parser.add_argument("--grounding-threshold", type=float, default=None)
    parser.add_argument("--relevance-threshold", type=float, default=None)
    args = parser.parse_args()

    g_thr = _threshold(args.grounding_threshold, "BEDROCK_GROUNDING_THRESHOLD", 0.75)
    r_thr = _threshold(args.relevance_threshold, "BEDROCK_RELEVANCE_THRESHOLD", 0.75)

    try:
        import boto3
    except ImportError:
        print("FAIL: boto3 is not installed. pip install boto3", file=sys.stderr)
        return 1

    client = boto3.client("bedrock", region_name=args.region)
    filters = [
        {"type": "GROUNDING", "threshold": g_thr, "enabled": True, "action": "NONE"},
        {"type": "RELEVANCE", "threshold": r_thr, "enabled": True, "action": "NONE"},
    ]
    kwargs = {
        "name": args.name,
        "description": args.description,
        "contextualGroundingPolicyConfig": {"filtersConfig": filters},
        "blockedInputMessaging": "This request was blocked by the NeuroSight grounding guardrail.",
        "blockedOutputsMessaging": "This draft was blocked by the NeuroSight grounding guardrail.",
    }

    print(f"Creating guardrail {args.name!r} in {args.region}")
    print(f"  GROUNDING threshold={g_thr}  RELEVANCE threshold={r_thr}  action=NONE")
    try:
        resp = client.create_guardrail(**kwargs)
    except Exception as exc:
        # Older boto3 builds reject `action` / `enabled` on the filter object.
        print(f"  retrying without action/enabled ({exc})")
        kwargs["contextualGroundingPolicyConfig"] = {
            "filtersConfig": [
                {"type": "GROUNDING", "threshold": g_thr},
                {"type": "RELEVANCE", "threshold": r_thr},
            ]
        }
        resp = client.create_guardrail(**kwargs)

    gid = resp.get("guardrailId") or resp.get("id")
    gver = resp.get("version") or "DRAFT"
    print("Created.")
    print(f"  BEDROCK_GUARDRAIL_ID={gid}")
    print(f"  BEDROCK_GUARDRAIL_VERSION={gver}")
    print("  BEDROCK_GROUNDING_THRESHOLD=" + str(g_thr))
    print("  BEDROCK_RELEVANCE_THRESHOLD=" + str(r_thr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
