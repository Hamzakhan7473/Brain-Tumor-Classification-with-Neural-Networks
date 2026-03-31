# Deploy API to cloud (GCP + AWS)

Your FastAPI app is containerized (`Dockerfile`). Use **one** cloud first (GCP Cloud Run is a good default if you use Gemini).

**Prerequisites:** Docker Desktop running locally; `docker build` succeeds; `.env` with `GOOGLE_API_KEY` for `/report` (optional for `/predict`).

---

## 1. Google Cloud Platform (Cloud Run)

```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# Create Artifact Registry repo (once)
gcloud artifacts repositories create brain-mri-repo \
  --repository-format=docker --location=us-central1

# Build and push (from project root)
docker build -t brain-tumor-mri-api:latest .
docker tag brain-tumor-mri-api:latest \
  us-central1-docker.pkg.dev/YOUR_GCP_PROJECT_ID/brain-mri-repo/brain-tumor-mri-api:latest
docker push us-central1-docker.pkg.dev/YOUR_GCP_PROJECT_ID/brain-mri-repo/brain-tumor-mri-api:latest

# Deploy
gcloud run deploy brain-tumor-mri-api \
  --image us-central1-docker.pkg.dev/YOUR_GCP_PROJECT_ID/brain-mri-repo/brain-tumor-mri-api:latest \
  --platform managed --region us-central1 --port 8000 \
  --set-secrets="GOOGLE_API_KEY=YOUR_SECRET_NAME:latest" \
  --allow-unauthenticated
```

For production, remove `--allow-unauthenticated` and add IAM / identity-aware access. Store secrets in **Secret Manager**, not in the image.

**Health check:** `curl https://YOUR_SERVICE_URL/health`

---

## 2. AWS (ECR + App Runner or ECS Fargate)

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr create-repository --repository-name brain-tumor-mri-api --region us-east-1

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com

docker tag brain-tumor-mri-api:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/brain-tumor-mri-api:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/brain-tumor-mri-api:latest
```

Then in **AWS Console → App Runner → Create service** from ECR image, port **8000**, add environment variables from `.env`.

---

## 3. GCP RAG ingestion job (MongoDB Atlas Vector Search)

Your `/report` endpoint uses MongoDB Atlas Vector Search to retrieve grounding evidence.
You must populate the vector collection using `scripts/rag_ingest_docs.py` at least once (and re-run when knowledge sources change).

Recommended:
- Create a Cloud Run Job (or scheduled Cloud Run) in the same region as your deployment.
- Run the same container image as the API, but override the command to execute the ingestion script.

Environment variables to set:
- `GOOGLE_API_KEY`
- `MONGODB_URI`, `MONGODB_DB`
- `MONGODB_COLLECTION_RAG`
- `MONGODB_RAG_VECTOR_INDEX`
- `RAG_EMBED_MODEL` (optional override)

Example (run locally from repo root):
```bash
python scripts/rag_ingest_docs.py --docs-glob "docs/**/*.md" --chunk-size-chars 1200 --overlap-chars 180 --batch-size 25
```

---
## 4. After deploy

- Point design partners at `https://.../docs` (Swagger) or integrate with your Streamlit app via `API_BASE_URL` (when wired).
- See `docs/compliance-baseline.md` before enabling PHI (BAA, encryption, audit).

### Frontend (browser) integration notes
- If you are running a browser frontend (Vite/React), set `CORS_ALLOW_ORIGINS` on the API service to the frontend domain(s).
- Local dev defaults are allowed automatically: `http://localhost:5173`, `http://127.0.0.1:5173`.

---

## Related

- `README.md` — local API: `uvicorn src.api.main:app --port 8000`
- `docs/api.md` — endpoints
- `docs/compliance-baseline.md` — HIPAA/BAA checklist
