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
        enable=enable,
    )

