# Market, Regulatory, and GTM Intelligence for Brain Tumor MRI AI Startup

Structured summary from external deep research (e.g. ChatGPT / analyst-style report). Use this alongside `docs/startup-gap-analysis.md` for strategy and roadmap decisions.

---

## 1. Market sizing (TAM anchors)

**Why numbers differ:** Definitions vary (software-only vs software+services; algorithm-only vs broad radiology IT). Use ranges and state definitions.

| Definition | Source | 2024–2025 | Horizon | CAGR |
|------------|--------|-----------|---------|-----|
| AI in radiology (broad, global) | Grand View Research | ~$10.57B | — | High |
| Radiology AI (software/apps, global) | MarketsandMarkets | ~$0.61B → $0.76B | ~$2.27B by 2030 | 24.5% |
| AI in medical imaging (software, global) | MarketsandMarkets | ~$1.5B | ~$4.5B by 2029 | 23.2% |
| Clinical imaging AI (>$700M 2023) | Signify Research | — | >$2B by 2028 | — |
| **Brain tumor AI in cancer diagnostics (global)** | Grand View Research (horizon) | **~$23.7M** | **~$110.3M by 2030** | **~28.8%** |
| AI in neurology (global) | BCC Research | ~$563.6M | ~$2.5B by 2030 | ~28.9% |
| AI in oncology (broad, global) | Grand View Research | ~$6.0B (2025) | ~$38.9B by 2033 | — |

**Takeaway:** Brain tumor–specific TAM is narrow (tens of millions); SAM expands if you include neuro imaging AI, oncology imaging workflows, and reporting automation. Use a two-step story: neuro-oncology workflow first, then adjacent neuro (MS, dementia, stroke).

### SAM model (defendable)

- **US incidence (CBTRUS):** ~107,100 new brain/CNS tumors in US in 2025 (~26,480 malignant, ~80,610 non-malignant); ~13,930 new glioblastoma.
- **Imaging intensity (NCCN-style):** Post-op MRI 48–72h, 2–8 weeks post-RT, then every 2–4 months for 3 years, then every 3–6 months indefinitely.
- **SAM framing:** Target treated glioma/GBM follow-up → SAM = repeat MRIs per patient (multi-scan “lifetime value”), not just incident cases. This justifies commercial focus on **segmentation + longitudinal volumetrics**, not single-scan classification only.

---

## 2. Competitive landscape (brain tumor MRI)

**Pattern:** FDA-cleared brain tumor AI is overwhelmingly **segmentation + volumetric quantification + longitudinal tracking** for known/previously diagnosed tumors, often **not** for primary diagnosis.

| Company / product | FDA / note | Intended use |
|-------------------|------------|--------------|
| **Cortechs.ai** NeuroQuant Brain Tumor | 510(k) K241098 (Aug 2024) | Automated labeling/visualization/volumetric quantification; DL segmentation; glioma, then metastases/meningioma (2025). |
| **Neosoma** NS-HGlio | K221738 (2022) | High-grade glioma labeling/segmentation/volumetrics from T1/T1c/T2/FLAIR; known pathologically proven tumors. |
| **Neosoma** Brain Mets | K252922 (Dec 2025) | Semi-auto segmentation of previously diagnosed brain mets (T1 post-contrast); volumetric outputs; clinician finalization; sensitivity 0.90, DSC 0.86. |
| **Vysioneer** VBrain | K203235 (2021) | GTV contours for brain mets/meningioma/acoustic neuroma on T1c; **not** for detection/diagnosis; clinician finalizes. |
| **MRIMath** i2Contour | K233822 (2024) | Semi-auto labeling/volumetrics for WHO G4 GBM, pathologically proven; **not** for primary diagnosis. |
| **Philips** MMTT | K162955 (2016) | Post-processing for display/analysis/quantification across CT/MR/PET/SPECT and timepoints; oncology follow-up; predicate for tracking. |
| **Brainlab** (e.g. K250440) | 510(k) | Elements AI Tumor Segmentation RT, radiotherapy planning. |

**Workflow / reporting (competing for budget):** Rad AI (report “impressions,” workflow/time-savings); Microsoft/Nuance Dragon Copilot (radiology documentation at RSNA 2025).

**Where we differentiate today (pre-FDA, pre-DICOM):** Single-screen demo (model + saliency + report draft + human review) = strong storytelling for design partners as a **research workflow prototype**, not a clinical device. **Gap:** Clinical buyers want DICOM, multi-sequence MRI, segmentation, volumes, longitudinal tracking—none of which the current 2D JPG classifier delivers. **Opportunity:** “Suspicion flagging” could be a regulated niche but likely CADx (POK), not pure triage (CADt), since brain tumors are not time-critical like stroke/ICH.

---

## 3. Regulatory roadmap

**Reality:** If the product influences diagnosis/management of brain tumors from MRI, it is very likely **SaMD** in the US. Multiple regulatory surfaces:

- **Classifier** → “characterization of lesions suspicious for cancer” → **CADx**, product code **POK** (21 CFR 892.2060).
- **Report drafting** → can be **CDS**; FDA CDS guidance (Jan 2026) clarifies device vs non-device.
- **Triage/queue reprioritization** → **CADt**, product code **QAS** (radiological triage and notification).

**Action:** Choose **one** initial regulated claim and scope the product to it; “classifier + saliency + report draft + chat” in one first clearance is hard to justify.

### FDA pathway options

| Pathway | Code / family | Notes |
|---------|----------------|-------|
| **A. CADx (POK)** | 21 CFR 892.2060, Class II | Tumor suspicion/characterization; De Novo precedent QuantX DEN170022; 510(k) if predicate in same intended-use family. |
| **B. Segmentation/volumetrics** | 892.2050, QIH/QKB | “Medical image management and processing”; segmentation/volumetrics for **known** tumors + clinician finalization; aligns with how neuro-oncology tools are bought. |
| **C. CADt (QAS)** | Triage/notification | For time-sensitive findings; brain tumor “triage” is harder to justify than stroke/ICH; possible narrow use (e.g. suspected mass effect). |

**Timelines/costs (US):**  
- MDUFA V: 510(k) total time to decision ~124 days (FY2024), ~112 days (FY2026).  
- Median concept-to-clearance cited ~**31 months** (wide variation).  
- FY2026 user fees: standard 510(k) ~$26k; small business ~$6k.  
- Full program cost (QMS, clinical validation, cybersecurity, regulatory consulting) often **tens of millions** for 510(k) devices; for SaMD, drivers are QMS, cybersecurity, validation data, stats, consulting. **Budget:** (1) Pre-FDA R&D + retrospective validation (design partners, IRB); (2) Regulated build (DICOM, QMS, cybersecurity, locked model, validation). FDA AI lifecycle and PCCP guidance (Aug 2025) imply change-control for post-clearance model updates.

### HIPAA / pilot-ready checklist

- BAA-ready architecture; encryption (transit/at rest); audit logs; RBAC; incident response; data retention/deletion policy.
- Hospitals often require **BAA** + security evidence; **SOC 2 Type II** common in vendor selection; **HITRUST CSF** can speed enterprise procurement.
- 2025 HIPAA Security Rule NPRM: tighter MFA, encryption expectations.
- **Google Cloud:** HIPAA guidance and BAA for covered products; customer builds compliant solution on approved services.

---

## 4. Clinical and technical product requirements

**Neuro-oncology reality:** Workflows are about **tracking disease burden over time** (multi-component assessment, response vs pseudoprogression, consistent measurement). Commercial tools are bought for **segmentation + volumes** (and DICOM for planning), not 2D slice classification.

**2D vs 3D:**  
- **2D defensible for:** Retrospective research, education, early feasibility with human review and disclaimers.  
- **Buyers expect 3D:** BraTS-style multi-parametric volumes (T1, T1c, T2, FLAIR); segmentations; volumetrics; clinician finalization.

**Minimum sellable hospital product (from research):**  
1) DICOM-native ingestion + PACS integration.  
2) Segmentation masks + volumetrics (at least 1–2 tumor types).  
3) Safety/quality: acceptance testing + monitoring (ACR-SIIM practice parameter).  
4) If keeping LLM: constrained, grounded, auditable outputs (RSNA generative AI guidance).

**Product decision:** Shortest path to clinical relevance = (1) DICOM + multi-sequence, (2) segmentation + volumetrics for one high-value cohort (e.g. brain mets for RT, or glioma longitudinal), (3) **structured report templates from measured outputs**, not unconstrained generative text.

---

## 5. Go-to-market and pricing

**Best first segment (current state: 2D JPG + demo + LLM; no DICOM/FDA):** **Design partners for retrospective validation**, not paying clinical customers.

**Design partner profiles:**  
1) Academic neuroradiology/neuro-oncology with IRB + PACS research pipelines (DICOM, sequences, ground truth, clinical review).  
2) Radiation oncology planning teams if you pivot to auto-contouring/volumetrics (contour-centric workflows).  
3) Community/outpatient imaging later, after integration + clearance.

**Positioning for first pilots:** “Workflow concept + retrospective evaluation”: auto-summarize model outputs, radiologist feedback, structured measurements when segmentation exists, quantify time savings.

**Pricing benchmarks:**  
- UK Digital Marketplace (deepc): £5,000–£150,000/year for radiology AI platform.  
- Blackford: ~$5/study as rough “IT tools” context.  
- Viz LVO: CMS NTAP up to **$1,040** per stroke episode (reimbursement example).  
- **Pre-FDA:** Free or low-cost for data + clinician time; optimize for IRB retrospective validation and workflow metrics.  
- **Post-clearance:** Per-site annual module, platform subscription, or per-study (tied to ROI).

**Recruit first 5–10 design partners:**  
1) Offer “retrospective evaluation pack” (per-patient split, calibration, error analysis by scanner/site, clinician feedback).  
2) Anchor on one workflow with measurable pain (e.g. time on segmentation/longitudinal, not “glioma vs meningioma” from one slice).  
3) Use human-in-the-loop as safety selling point (clinician finalization).  
4) Target institutions with imaging AI infrastructure (ACR AI-LAB, RSNA integration patterns).

---

## 6. Risks and unknowns (2025–2026)

**Technical:** Domain shift (2D JPG vulnerable to scanner/protocol); clinical mismatch (four classes don’t cover metastases, post-treatment, non-tumor); saliency not accepted as clinical proof—validation vs ground truth segmentation expected.

**Regulatory:** Generative text (hallucination) under RSNA/FDA scrutiny; post-market AI lifecycle (PCCPs, real-world monitoring) is non-trivial for small teams.

**Commercial:** Integration burden and procurement friction; crowded reporting automation; reimbursement mostly via hospital ROI (throughput, delays, standardization), not fee-for-service. Neuro example: icometrix CPT III 0865T/0866T for icobrain—not automatically applicable to brain tumor AI.

**Safety/reputation:** AI performance issues and recalls can materially harm trust; conservative claims and monitoring are critical.

---

## 7. Key references (from source report)

- Grand View: AI radiology market; AI in cancer diagnostics (brain tumor); AI in oncology.  
- MarketsandMarkets: Radiology AI; AI in medical imaging.  
- Signify Research: Medical imaging AI >$2B by 2028.  
- BCC Research: AI in neurology.  
- CBTRUS: 2025 statistical report (incidence).  
- FDA: K241098 (Cortechs), K221738 / K252922 (Neosoma), K203235 (Vysioneer), K233822 (MRIMath), K162955 (Philips MMTT), K250440 (Brainlab); POK, QAS product classification; CDS guidance; AI SaMD; PCCP guidance; MDUFA fees.  
- ACR: AI-LAB reference architecture; workforce shortage.  
- RSNA: AI in radiology; LLM best practices.  
- ACR-SIIM: Practice parameter imaging AI.  
- HIPAA: Security Rule; 2025 NPRM takeaways.  
- HITRUST CSF; Google Cloud HIPAA.  
- Blackford: Value for medical imaging AI.  
- icometrix: CPT 0865T/0866T.  
- RANO 2.0; BraTS; workflow integration (PMC).

---

*Source: External deep-research report (e.g. ChatGPT prompt output). Integrate with `docs/startup-gap-analysis.md` and `docs/roadmap-radiologist-questions.md` for roadmap and prioritization.*
