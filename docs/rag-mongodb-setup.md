# RAG with MongoDB Atlas Vector Search

This project uses MongoDB Atlas Vector Search to ground LLM report generation in retrieved evidence.

## 1. What gets stored in MongoDB
MongoDB collections (set via environment variables in `.env` / deployment):
- `MONGODB_COLLECTION_RAG` (default `rag_chunks`)

Each chunk document is stored with:
- `_id`: `chunk_id` (sha256-based)
- `text`: chunk text (markdown or document excerpt)
- `metadata`: JSON (source path, chunk index, doc id)
- `embedding`: vector of floats for the chosen embedding model

## 2. Vector index requirements (Atlas)
You must create a Vector Search index on:
- collection: `MONGODB_COLLECTION_RAG`
- embedding field: `embedding`
- index name: `MONGODB_RAG_VECTOR_INDEX` (default `rag_vector_index`)

Important:
- The embedding vector dimension depends on `RAG_EMBED_MODEL`.
- Create the Atlas index with the correct `dimensions` value for your embedding model.

## 3. Retrieval query used by the backend
When generating reports (`POST /report`), the backend:
1. embeds the query via Google embeddings
2. runs a `$vectorSearch` aggregation pipeline against Atlas Vector Search
3. returns top-k chunks as `evidence_context`

If retrieval is empty, the report prompt instructs the LLM to state insufficient evidence from retrieved sources.

## 4. Ingestion job
Use the script:
- `scripts/rag_ingest_docs.py`

Recommended GCP setup:
- Cloud Run Job or scheduled Cloud Run
- Environment:
  - `GOOGLE_API_KEY`
  - `MONGODB_URI`, `MONGODB_DB`
  - `MONGODB_COLLECTION_RAG`, `MONGODB_RAG_VECTOR_INDEX`
  - `RAG_EMBED_MODEL` (optional override)

Example command (run from repo root):
```bash
python scripts/rag_ingest_docs.py --docs-glob "docs/**/*.md" --chunk-size-chars 1200 --overlap-chars 180 --batch-size 25
```

