# Brain Tumor MRI API — deploy to Cloud Run, ECS, or any container host
# Build: docker build -t brain-tumor-mri-api .
# Run:   docker run -p 8000:8000 -e GOOGLE_API_KEY=optional brain-tumor-mri-api
FROM python:3.11-slim

WORKDIR /app

# System deps (minimal for TensorFlow CPU and pydicom)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (API + inference; Streamlit optional for local demo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: install only API deps in a slimmer layer (uncomment to trim image)
# RUN pip install --no-cache-dir fastapi uvicorn[standard] pydicom numpy pillow pyyaml python-dotenv google-generativeai tensorflow

COPY . .

# After setting PAGEINDEX_API_KEY, index clinical PDFs once per deploy (or use a Cloud Run job):
#   docker run ... -e PAGEINDEX_API_KEY=... python scripts/index_clinical_docs.py

# Default: run API
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
