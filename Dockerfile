# GARUDA-ID API + frontend in one container.
# Works on: Hugging Face Spaces (Docker SDK, port 7860), Fly.io, Koyeb,
# Oracle Cloud, or any VPS with Docker. No credit card needed on HF Spaces.
FROM python:3.12-slim

WORKDIR /app

# System libs for Pillow/OpenCV (slim image doesn't ship them).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

# Hugging Face Spaces expects port 7860; others inject $PORT (Render/Railway).
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]

# ---- Optional: full OCR on roomy hosts (HF Spaces free = 16 GB RAM) ----
# PaddlePaddle is too heavy for Render free (512 MB) but fine here.
# Uncomment, rebuild, redeploy:
#   RUN pip install --no-cache-dir paddlepaddle paddleocr
# First request downloads OCR models (~200 MB), then works offline.
