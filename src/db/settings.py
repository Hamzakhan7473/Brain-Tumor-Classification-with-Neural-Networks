from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    db_name: str
    inference_collection: str
    feedback_collection: str
    rag_collection: str
    auths_collection: str
    inbox_collection: str
    traces_collection: str
    trials_collection: str
    trial_candidates_collection: str
    audit_log_collection: str
    shadow_cases_collection: str
    reports_collection: str
    enable: bool


def load_mongo_settings() -> MongoSettings:
    """
    MongoDB settings are considered "enabled" only when `MONGODB_URI` is set.
    This keeps local/dev environments working without Mongo.
    """
    uri = (os.environ.get("MONGODB_URI") or "").strip()
    enable = bool(uri)
    return MongoSettings(
        uri=uri,
        db_name=os.environ.get("MONGODB_DB", "brain_tumor_ai"),
        inference_collection=os.environ.get("MONGODB_COLLECTION_INFERENCE", "inference_events"),
        feedback_collection=os.environ.get("MONGODB_COLLECTION_FEEDBACK", "clinical_feedback"),
        rag_collection=os.environ.get("MONGODB_COLLECTION_RAG", "rag_chunks"),
        auths_collection=os.environ.get("MONGODB_COLLECTION_AUTHS", "prior_auths"),
        inbox_collection=os.environ.get("MONGODB_COLLECTION_INBOX", "inbox_messages"),
        traces_collection=os.environ.get("MONGODB_COLLECTION_TRACES", "agent_traces"),
        trials_collection=os.environ.get("MONGODB_COLLECTION_TRIALS", "clinical_trials"),
        trial_candidates_collection=os.environ.get("MONGODB_COLLECTION_TRIAL_CANDIDATES", "trial_candidates"),
        audit_log_collection=os.environ.get("MONGODB_COLLECTION_AUDIT_LOG", "audit_log"),
        shadow_cases_collection=os.environ.get("MONGODB_COLLECTION_SHADOW_CASES", "shadow_cases"),
        reports_collection=os.environ.get("MONGODB_COLLECTION_REPORTS", "report_drafts"),
        enable=enable,
    )

