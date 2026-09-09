#!/usr/bin/env python3
"""
Enable Amazon Bedrock model invocation logging to S3 + CloudWatch.

This repo uses Python scripts under scripts/ (not Terraform) for AWS setup.
See also: scripts/create_bedrock_guardrail.py

Usage (from project root):
  python scripts/enable_bedrock_invocation_logging.py --dry-run
  python scripts/enable_bedrock_invocation_logging.py

Env:
  AWS_REGION                          (default us-east-1)
  BEDROCK_AUDIT_BUCKET                (default neurosight-bedrock-audit-logs)
  BEDROCK_AUDIT_LOG_GROUP             (default /neurosight/bedrock-invocations)
  BEDROCK_AUDIT_KEY_PREFIX            (default invocations/)
  BEDROCK_LOGGING_ROLE_NAME           (default NeuroSightBedrockLoggingDelivery)
  BEDROCK_AUDIT_KMS_KEY_ARN           (optional; default SSE-S3 AES256)

What this does:
  1. Creates the S3 bucket with default encryption (KMS if ARN set, else AES256),
     public-access block, and a lifecycle rule that transitions to Glacier after
     90 days. Expiration is NOT set — HIPAA minimum retention is 6 years; do not
     auto-delete.
  2. Creates the CloudWatch Logs group (retention = never expire).
  3. Creates an IAM delivery role that Bedrock assumes to write logs/S3.
  4. Calls bedrock put-model-invocation-logging-configuration.

IAM: merge scripts/iam/NeuroSightBedrockInvoke-logging-addon.json into the
existing NeuroSightBedrockInvoke policy (see that file for the exact extra
statements: logs:CreateLogGroup/Stream, logs:PutLogEvents, s3:PutObject).
The delivery role created here is what Bedrock itself uses at write time.
"""
from __future__ import annotations

import argparse
import json
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

DEFAULT_BUCKET = "neurosight-bedrock-audit-logs"
DEFAULT_LOG_GROUP = "/neurosight/bedrock-invocations"
DEFAULT_PREFIX = "invocations/"
DEFAULT_ROLE = "NeuroSightBedrockLoggingDelivery"
# HIPAA: retain at least 6 years. CloudWatch "never expire" = 0 in some APIs;
# we document 2190 days as the floor and do not attach an S3 Expiration action.
HIPAA_MIN_RETENTION_DAYS = 2190
GLACIER_TRANSITION_DAYS = 90


def s3_lifecycle_configuration(prefix: str = DEFAULT_PREFIX) -> dict:
    """
    Transition to Glacier after 90 days. No Expiration — do not auto-delete.
    Operators may delete only after a documented 6-year (or longer) hold.
    """
    return {
        "Rules": [
            {
                "ID": "neurosight-bedrock-audit-glacier-90d-no-delete",
                "Status": "Enabled",
                "Filter": {"Prefix": prefix},
                "Transitions": [
                    {
                        "Days": GLACIER_TRANSITION_DAYS,
                        "StorageClass": "GLACIER",
                    }
                ],
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
            }
        ]
    }


def logging_config_body(
    *,
    bucket: str,
    prefix: str,
    log_group: str,
    role_arn: str,
) -> dict:
    return {
        "cloudWatchConfig": {
            "logGroupName": log_group,
            "roleArn": role_arn,
        },
        "s3Config": {
            "bucketName": bucket,
            "keyPrefix": prefix,
        },
        "textDataDeliveryEnabled": True,
        "imageDataDeliveryEnabled": True,
    }


def delivery_role_trust_policy() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def delivery_role_permissions(bucket: str, log_group: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "WriteCloudWatch",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": [
                    f"arn:aws:logs:*:*:log-group:{log_group}",
                    f"arn:aws:logs:*:*:log-group:{log_group}:log-stream:*",
                ],
            },
            {
                "Sid": "WriteS3Audit",
                "Effect": "Allow",
                "Action": ["s3:PutObject"],
                "Resource": f"arn:aws:s3:::{bucket}/*",
            },
        ],
    }


def _account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or "us-east-1")
    parser.add_argument("--bucket", default=os.environ.get("BEDROCK_AUDIT_BUCKET") or DEFAULT_BUCKET)
    parser.add_argument("--log-group", default=os.environ.get("BEDROCK_AUDIT_LOG_GROUP") or DEFAULT_LOG_GROUP)
    parser.add_argument("--prefix", default=os.environ.get("BEDROCK_AUDIT_KEY_PREFIX") or DEFAULT_PREFIX)
    parser.add_argument("--role-name", default=os.environ.get("BEDROCK_LOGGING_ROLE_NAME") or DEFAULT_ROLE)
    parser.add_argument("--kms-key-arn", default=os.environ.get("BEDROCK_AUDIT_KMS_KEY_ARN") or "")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config JSON and CLI; do not call AWS.",
    )
    args = parser.parse_args()
    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"
    lifecycle = s3_lifecycle_configuration(prefix)

    if args.dry_run:
        placeholder_role = f"arn:aws:iam::ACCOUNT_ID:role/{args.role_name}"
        body = logging_config_body(
            bucket=args.bucket,
            prefix=prefix,
            log_group=args.log_group,
            role_arn=placeholder_role,
        )
        print("DRY RUN — no AWS calls.")
        print(f"HIPAA retention: S3 lifecycle transitions to Glacier after {GLACIER_TRANSITION_DAYS} days.")
        print(f"No S3 Expiration is attached. Minimum hold {HIPAA_MIN_RETENTION_DAYS} days (6 years); do not auto-delete.")
        print("\nS3 lifecycle:")
        print(json.dumps(lifecycle, indent=2))
        print("\nput-model-invocation-logging-configuration:")
        print(json.dumps(body, indent=2))
        print("\nEquivalent CLI:")
        print("aws bedrock put-model-invocation-logging-configuration \\")
        print(f"  --region {args.region} \\")
        print("  --logging-config '" + json.dumps(body) + "'")
        print("\nMerge IAM addon into NeuroSightBedrockInvoke:")
        print("  scripts/iam/NeuroSightBedrockInvoke-logging-addon.json")
        return 0

    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("FAIL: boto3 is not installed. pip install boto3", file=sys.stderr)
        return 1

    session = boto3.session.Session(region_name=args.region)
    s3 = session.client("s3")
    logs = session.client("logs")
    iam = session.client("iam")
    sts = session.client("sts")
    bedrock = session.client("bedrock")
    account = _account_id(sts)
    role_arn = f"arn:aws:iam::{account}:role/{args.role_name}"

    # Bucket
    try:
        if args.region == "us-east-1":
            s3.create_bucket(Bucket=args.bucket)
        else:
            s3.create_bucket(
                Bucket=args.bucket,
                CreateBucketConfiguration={"LocationConstraint": args.region},
            )
        print(f"Created bucket s3://{args.bucket}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise
        print(f"Bucket s3://{args.bucket} already exists")

    s3.put_public_access_block(
        Bucket=args.bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    enc_rule: dict = {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
    if args.kms_key_arn:
        enc_rule = {
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "aws:kms",
                "KMSMasterKeyID": args.kms_key_arn,
            },
            "BucketKeyEnabled": True,
        }
    s3.put_bucket_encryption(
        Bucket=args.bucket,
        ServerSideEncryptionConfiguration={"Rules": [enc_rule]},
    )
    s3.put_bucket_lifecycle_configuration(
        Bucket=args.bucket,
        LifecycleConfiguration=lifecycle,
    )
    print(
        f"Encryption + lifecycle applied (Glacier @{GLACIER_TRANSITION_DAYS}d, "
        f"no expiration; retain ≥ {HIPAA_MIN_RETENTION_DAYS}d)."
    )

    try:
        logs.create_log_group(logGroupName=args.log_group)
        print(f"Created log group {args.log_group}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceAlreadyExistsException":
            raise
        print(f"Log group {args.log_group} already exists")
    # Leave CloudWatch retention at "Never expire" so the 6-year HIPAA hold
    # is operator-managed, matching the S3 rule (no auto-delete).

    try:
        iam.create_role(
            RoleName=args.role_name,
            AssumeRolePolicyDocument=json.dumps(delivery_role_trust_policy()),
            Description="Bedrock model-invocation logging delivery (NeuroSight)",
        )
        print(f"Created role {args.role_name}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "EntityAlreadyExists":
            raise
        print(f"Role {args.role_name} already exists")
    iam.put_role_policy(
        RoleName=args.role_name,
        PolicyName="NeuroSightBedrockLoggingDeliveryInline",
        PolicyDocument=json.dumps(delivery_role_permissions(args.bucket, args.log_group)),
    )

    body = logging_config_body(
        bucket=args.bucket,
        prefix=prefix,
        log_group=args.log_group,
        role_arn=role_arn,
    )
    bedrock.put_model_invocation_logging_configuration(loggingConfig=body)
    print("Bedrock model invocation logging is enabled.")
    print(json.dumps(body, indent=2))
    print("Merge scripts/iam/NeuroSightBedrockInvoke-logging-addon.json into NeuroSightBedrockInvoke.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
