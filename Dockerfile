# Single-container build of the SA-QCA public demo: built frontend + FastAPI backend + R (QCA).
# Hugging Face Spaces (Docker SDK) expects the app on port 7860 and a non-root user with uid 1000.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM rocker/r-ver:4.5.1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl \
    && rm -rf /var/lib/apt/lists/*
RUN R -q -e 'install.packages(c("QCA", "jsonlite"))' \
    && R -q -e 'stopifnot(requireNamespace("QCA"), requireNamespace("jsonlite"))'

RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -e backend
COPY rservice/R rservice/R
COPY demo demo
COPY --from=web /web/dist frontend/dist

ENV PATH="/opt/venv/bin:$PATH" \
    SA_QCA_MODE=demo \
    SA_QCA_STATIC_DIR=/app/frontend/dist \
    SA_QCA_DB=sqlite:////tmp/sa_qca.sqlite \
    PORT=7860
RUN chown -R user:user /app
USER user
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://localhost:7860/health || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
