# 48-hour go-live runbook — AWS, GCP, MongoDB Atlas

Goal: ship a **working production-shaped demo**: browser UI + FastAPI backend + **MongoDB Atlas** (operational DB + **vector search** for RAG) + **Gemini** for reports/docs + **2D models** in the container or pulled from object storage.

This is **not** a full HIPAA/BAA attestation in two days — see `docs/compliance-baseline.md` for what comes after the first launch.

---

## 1. Split responsibilities (avoid duplicating the API twice)

Pick **one** primary host for the **FastAPI** container; use the other cloud only if you truly need it.

| Layer | Recommended (Gemini + low ops) | Alternative (AWS-native shop) |
|-------|-------------------------------|-------------------------------|
| **API + inference** | **GCP Cloud Run** (same project as Gemini / Secret Manager) | **AWS App Runner** or **ECS Fargate** + **ALB** |
| **Container registry** | **Artifact Registry** | **ECR** |
| **Secrets** | **Secret Manager** | **Secrets Manager** or **SSM** |
| **Frontend static site** | **Cloud Storage + Cloud CDN** or **Firebase Hosting** | **S3 + CloudFront** |
| **LLM** | **Google AI (Gemini)** — `GOOGLE_API_KEY` | Same (GCP-adjacent) |
| **DB + vectors** | **MongoDB Atlas** (M10+ if you need stable performance; M0/M2 for smoke tests only) | Same — Atlas is multi-cloud |
| **Model weights** | **GCS** or baked into image; set `MODEL_DIR` if loading from volume | **S3** + IAM role; or bake into image |

**Practical rule for 48h:** Deploy API on **GCP Cloud Run** + Atlas + GCS for large `.keras` files *or* bake **custom_cnn + xception + transfer** into the Docker image if total size is acceptable. Add **AWS** only for frontend (S3/CloudFront) or corporate requirement — do **not** run two copies of the same API without a reason.

---

## 2. Feature → infrastructure mapping

| Feature | Needs | Env / config |
|--------|--------|----------------|
| `GET /health`, `GET /features`, `GET /models` | API up; models on disk | `MODEL_DIR` or default `models/saved/` |
| `POST /predict` (JPG/PNG/DICOM) | 2D Keras weights | Files present; optional `API_KEY` |
| `POST /report` | Weights + **Gemini** + optional **RAG** | `GOOGLE_API_KEY`; `MONGODB_URI` + RAG collections |
| `POST /docs/ask` | **Atlas Vector Search** + ingest + Gemini | Same + `MONGODB_RAG_VECTOR_INDEX` |
| `POST /clinical/feedback`, `GET /cases`, `GET /metrics` | **MongoDB** collections | `MONGODB_URI`, collection names |
| Trials / auths / inbox / agent-traces | MongoDB | Same |
| React UI | Build → static host; `VITE_API_BASE_URL`, `VITE_API_KEY` | `CORS_ALLOW_ORIGINS` = frontend origin |
| Shadow mode / audit JSONL | Writable volume or defer to Mongo only | Prefer Mongo for multi-instance |
| 3D classify `/predict-3d` | Separate 3D weights | Optional — **defer** if not demo-critical |
| WMH / BraTS U-Net training path | Not part of API | **Out of scope** for 48h go-live |

---

## 3. MongoDB Atlas (single checklist)

1. Create project + **M0/M2/M10** cluster (region close to Cloud Run / App Runner).
2. Database user (least privilege) + IP allowlist **or** private endpoint (48h: allowlist Cloud Run egress IPs is painful — use **0.0.0.0/0** only for demo with strong `API_KEY` and rotate post-demo, or Atlas **Serverless** + connection string with TLS).
3. Collections: inference, feedback, RAG chunks, trials, etc. (names via env — see `src/db/settings.py`).
4. **Vector Search**: create index on RAG collection `embedding` field; name matches `MONGODB_RAG_VECTOR_INDEX`.
5. Run ingestion once (from laptop CI or Cloud Run Job):

   ```bash
   python scripts/rag_ingest_docs.py --docs-glob "docs/**/*.md" ...
   ```

---

## 4. Models for launch

**Minimum viable demo (2D):**

- `custom_cnn_best.keras`, `xception_best.keras`, `transfer_best.keras` under `models/saved/` **or** synced to `MODEL_DIR` at startup from GCS/S3.

**Options:**

- **A. Bake into image** — simplest for 48h; image grows (~200MB+).
- **B. Startup pull** — entrypoint script `gsutil cp` / `aws s3 cp` to `/models/saved` then `uvicorn` (add to Dockerfile or Cloud Run Job sidecar pattern).

**Skip for v1 unless required:** 3D classifier weights, WMH U-Net training.

---

## 5. Environment variables (API)

Copy from `.env.example` and set in Cloud Run / App Runner:

**Required for full feature parity**

- `GOOGLE_API_KEY` (report + docs assistant + RAG answer synthesis)
- `MONGODB_URI`, `MONGODB_DB`
- RAG: `MONGODB_COLLECTION_RAG`, `MONGODB_RAG_VECTOR_INDEX`

**Strongly recommended for “live”**

- `API_KEY` or `API_KEYS` + frontend `VITE_API_KEY`
- `CORS_ALLOW_ORIGINS=https://your-frontend-domain`

**Optional tuning**

- `RAG_TOP_K`, rate limits already in code (`slowapi`)

---

## 6. Frontend go-live

1. `cd frontend && npm ci && npm run build`
2. Deploy `dist/` to **S3+CloudFront** or **GCS+Cloud CDN**.
3. Set **`VITE_API_BASE_URL`** to public API URL (e.g. `https://api.yourdomain.com`).
4. Set **`VITE_API_KEY`** to match backend.

---

## 7. Two-day execution plan

### Day 1 — Foundation

| Block | Tasks |
|-------|--------|
| Morning | Freeze scope: **2D API + UI + Mongo + RAG + Gemini**; no WMH training. |
| Morning | Atlas cluster + DB user + vector index placeholder; test connect from laptop. |
| Midday | Docker build with models (A) or GCS upload + startup script (B). |
| Afternoon | Deploy API to **Cloud Run** (or App Runner): secrets, env, `/health` 200. |
| Afternoon | Run `rag_ingest_docs.py` against Atlas; verify `/docs/ask` returns citations. |
| Evening | Deploy frontend; set CORS + API key; smoke test upload → predict → report. |

### Day 2 — Hardening + demo

| Block | Tasks |
|-------|--------|
| Morning | End-to-end QA checklist (below); fix CORS/auth/rate limits. |
| Midday | Custom domain + TLS (Cloud Run domain mapping / CloudFront cert). |
| Afternoon | Monitoring: Cloud Run logs + Atlas metrics; document rollback. |
| Evening | Freeze image tags; write down URLs, keys rotation plan, known limitations. |

---

## 8. Verification checklist (before “live”)

- [ ] `GET /health` returns `200` and correct `auth_required`
- [ ] `GET /models` lists expected 2D models
- [ ] `POST /predict` with sample MRI returns label + probabilities
- [ ] `POST /report` returns text (Gemini + RAG if configured)
- [ ] `POST /docs/ask` returns grounded answer when RAG populated
- [ ] Mongo paths: feedback + cases/metrics if using dashboards
- [ ] Frontend: upload, report, docs assistant with no console CORS errors
- [ ] Secrets not in GitHub; only in Secret Manager / Atlas UI

---

## 9. What to defer (still “live,” but honest)

- HIPAA/BAA, PHI — use **de-identified** or **public sample** images for public demo
- Multi-region, zero-downtime deploy
- Drift monitoring (UI placeholders exist)
- 3D inference + WMH/BraTS training pipelines

---

## 10. Related docs

- `docs/deploy-cloud.md` — Cloud Run + ECR commands
- `docs/compliance-baseline.md` — post-demo compliance
- `README.md` — local API and `demo_local.sh`
