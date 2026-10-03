# MindWell — one image: the React build, served by the FastAPI process.
#
#   docker build -t mindwell .
#   docker run --env-file backend/.env -e ENV=production -p 8000:8000 mindwell
#
# No torch in here. Sentiment runs on ONNX Runtime with a 68 MB quantised
# model, which is what lets the whole thing fit a 512 MB instance.

# ---------------------------------------------------------------- frontend
FROM node:20-alpine AS web
WORKDIR /web

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund \
 || npm install --legacy-peer-deps --no-audit --no-fund

COPY frontend/ ./

# Same origin as the API, so the app calls /api and there is no CORS.
ENV REACT_APP_API_URL=/api \
    GENERATE_SOURCEMAP=false \
    CI=false
RUN npm run build

# ----------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENV=production \
    SENTIMENT_BACKEND=onnx

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./

# Fetch the model and prove it classifies correctly. If the download breaks
# or the model misbehaves, the build fails here instead of shipping an app
# that quietly labels every message NEUTRAL.
ARG SENTIMENT_ONNX_URL
RUN python scripts/fetch_sentiment_model.py \
 && python scripts/verify_sentiment.py

COPY --from=web /web/build ./static

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health',timeout=8)" || exit 1

# One worker on purpose: the rate limiter and circuit breaker keep their
# state in process. Hosts inject PORT; default to 8000 elsewhere.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
