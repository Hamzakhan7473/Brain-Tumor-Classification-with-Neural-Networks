# Compliance Baseline (research prototype → BAA-ready)

This document summarizes a **minimum compliance baseline** for the Brain Tumor MRI AI project as it evolves from a research prototype to a product that can be deployed under a **Business Associate Agreement (BAA)** and support a future FDA submission.

It does **not** constitute legal advice; it is a technical checklist to align engineering work with common expectations (HIPAA, QMSR/ISO 13485, FDA cybersecurity guidance, SOC 2 readiness).

---

## 1. Data flows and PHI touchpoints

- **Inputs:** Brain MRI (DICOM or JPG/PNG) that may contain **PHI in headers** or burned into pixels.
- **Processing:** Model inference (classification) and optional LLM calls (Gemini) for explanations/reports.
- **Outputs:** JSON responses from the API, HTML/PDF reports, logs, and audit records.
- **Storage:** Model artifacts, configuration, limited audit logs, and (in a clinical setting) DICOM and reports in PACS/RIS/EMR.

For any deployment that touches PHI:

- Map all components that see PHI: DICOM loader, inference API, LLM gateway (if used on PHI), storage buckets, logs, monitoring.
- Treat everything that can see patient identifiers as **in-scope** for HIPAA and security controls.

---

## 2. Encryption (in transit & at rest)

**In transit**

- All external traffic **must** use TLS:
  - HTTPS for REST API (e.g. Cloud Run / API Gateway / ALB).
  - TLS for any DICOM transport (e.g. DICOM TLS or VPN/privately peered connection).
- Internal service-to-service communication:
  - Prefer private networking (VPC) and, where available, mTLS or service identity.

**At rest**

- Use managed, encrypted storage:
  - **GCP:** GCS, Cloud SQL, etc. with CMEK or provider-managed keys.
  - **AWS:** S3, RDS, etc. with KMS-managed keys.
- Avoid writing PHI to:
  - Local disks on ephemeral instances (or ensure full-disk encryption + lifecycle policies).
  - Ad-hoc logs that are not part of the controlled audit trail.

---

## 3. Access control and RBAC

- **Principle of least privilege:**
  - Limit who can access:
    - DICOM images.
    - Inference endpoints.
    - Logs/audit trail.
  - Separate roles: engineering vs. clinical reviewers vs. administrators.
- **Authentication and authorization:**
  - For pilots/production:
    - Require authenticated API access (e.g., OAuth2/JWT, mTLS, or VPN + IP allowlists).
    - Enforce per-tenant or per-site isolation if serving multiple institutions.
  - For the Streamlit demo:
    - Keep it in research/non-PHI environments, or add authentication and IP restrictions if used on PHI.
- **Account management:**
  - Centralized identity (e.g., SSO, IdPs) where possible.
  - Onboarding/offboarding procedures for engineers and clinical users.

---

## 4. Logging, audit, and retention

**Current state**

- `src/app/audit.log_event()` writes JSONL audit records (`logs/audit.log.jsonl`) for:
  - Inference events (model, label, confidence).
  - LLM explanation/report generation.
  - Report export.

**Baseline for BAA-ready deployment**

- **Audit contents** (per event):
  - Timestamp (UTC), user/session ID, model version, endpoint, outcome (success/failure).
  - Minimal patient-identifying fields necessary to trace a case (or a link to PACS UID).
  - For LLM events: which provider/model, prompt type (explanation vs report), and whether PHI was included.
- **Retention:**
  - Define a retention policy (e.g., 6–7 years for clinical logs, shorter for non-clinical dev logs).
  - Use cloud-native logging (e.g., Cloud Logging / CloudWatch) with log buckets and retention controls.
- **Access:**
  - Restrict log access to a small set of roles (security/engineering/QA).
  - Monitor access to logs (meta-audit).

---

## 5. Cloud architecture and BAA

**Target**: one primary cloud (GCP or AWS) with a BAA for HIPAA-eligible services.

- **GCP (natural fit with Gemini):**
  - Cloud Run or GKE for the FastAPI service.
  - GCS for storage (images, reports, logs).
  - Cloud Logging + Cloud Monitoring.
  - Use HIPAA-eligible services and execute a BAA with Google.
- **AWS (alternative or additional):**
  - ECS Fargate / EKS / App Runner for the API.
  - S3 for storage, CloudWatch for logs.
  - Use HIPAA-eligible services and execute a BAA with AWS.

**Key expectations:**

- Network isolation (VPC, private subnets, VPC Service Controls / PrivateLink where appropriate).
- Infrastructure-as-code (Terraform, CloudFormation) to make environments reproducible and auditable.
- Clear separation of:
  - **Production** (PHI) vs **staging/demo** (synthetic or de-identified data).

---

## 6. Privacy policy & data handling

For any external users (design partners, pilots), you will need:

- A clear **privacy policy** describing:
  - What data is collected (images, metadata, logs).
  - How it is used (model improvement, monitoring).
  - How long it is retained and how users can request deletion (where applicable).
- Data processing agreements/BAAs with covered entities (hospitals, clinics).
- Explicit statement that:
  - The current implementation is **research-only** unless deployed in a BAA-covered environment.
  - LLM usage on PHI is either disabled, limited to HIPAA-eligible services, or covered by contractual terms.

---

## 7. Cybersecurity and FDA alignment (high level)

From `docs/roadmap-research-to-hospital-grade.md`:

- Follow FDA’s **cybersecurity guidance** (e.g., SBOM, threat modeling, update mechanisms).
- Treat model and service updates as controlled changes:
  - Versioned releases.
  - Rollback strategy.
  - Documented impact analysis.
- Monitor:
  - Access logs, error rates, unusual patterns.
  - Model drift and data quality (domain shift).

---

## 8. How this affects day‑to‑day engineering

- Prefer:
  - **Config-driven** control of logging levels (e.g., no PHI in debug logs).
  - Secrets in `.env` / secret managers, **never** in code or Git.
  - Environment flags to distinguish **research/dev** vs **pilot/prod**.
- When adding new features:
  - Ask: does this touch PHI? If yes:
    - Is it encrypted in transit and at rest?
    - Is access controlled and logged?
    - Does it change the threat surface (e.g., new endpoint, new external service)?

This baseline is a starting point. The 24‑month roadmap in `docs/roadmap-research-to-hospital-grade.md` adds the full QMSR/ISO 13485 and FDA documentation layer on top of these controls.

