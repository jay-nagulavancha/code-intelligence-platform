# =============================================================================
# Code Intelligence Platform — Backend Dockerfile
# =============================================================================
# Stages:
#   base         — Python + system tools (git, curl)
#   deps-prod    — production Python packages only
#   deps-dev     — production + test/dev packages
#   java-tools   — JDK + SpotBugs + OWASP Dependency-Check (layered on deps-prod)
#   production   — final lean image (no test deps, non-root user)
#   development  — hot-reload image with test deps + source mounts
#   test         — runs pytest suite (used in CI)
#
# Build targets:
#   docker build --target production  -t cip-backend .
#   docker build --target development -t cip-backend-dev .
#   docker build --target test        -t cip-backend-test .
# =============================================================================

# ---------- Stage 1: Base ----------
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------- Stage 2: Production Python deps ----------
FROM base AS deps-prod

COPY requirements.txt .

# Install only production deps — strip out test packages
RUN grep -v -E "^(pytest|pytest-asyncio|httpx|hypothesis)" requirements.txt \
    > /tmp/requirements-prod.txt && \
    pip install --no-cache-dir -r /tmp/requirements-prod.txt

# ---------- Stage 3: Dev + test Python deps ----------
FROM deps-prod AS deps-dev

# Install the full requirements (includes pytest, httpx, hypothesis)
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Stage 4: Java scanning tools (layered on prod deps) ----------
FROM deps-prod AS java-tools

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    maven \
    gradle \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# SpotBugs
ARG SPOTBUGS_VERSION=4.8.3
RUN wget -q \
    https://github.com/spotbugs/spotbugs/releases/download/${SPOTBUGS_VERSION}/spotbugs-${SPOTBUGS_VERSION}.tgz \
    -O /tmp/spotbugs.tgz && \
    tar -xzf /tmp/spotbugs.tgz -C /opt/ && \
    ln -s /opt/spotbugs-${SPOTBUGS_VERSION}/bin/spotbugs /usr/local/bin/spotbugs && \
    rm /tmp/spotbugs.tgz

# OWASP Dependency-Check
ARG DC_VERSION=9.0.9
RUN wget -q \
    https://github.com/jeremylong/DependencyCheck/releases/download/v${DC_VERSION}/dependency-check-${DC_VERSION}-release.zip \
    -O /tmp/dc.zip && \
    unzip -q /tmp/dc.zip -d /opt/ && \
    ln -s /opt/dependency-check/bin/dependency-check.sh /usr/local/bin/dependency-check.sh && \
    rm /tmp/dc.zip


# ---------- Stage 5: Production ----------
FROM java-tools AS production

# Copy application source
COPY app/ ./app/
COPY scan_github_repo.py .
COPY .env.example .

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser && \
    mkdir -p /app/.vector_db /app/repos /app/reports /tmp/remediate && \
    chown -R appuser:appuser /app /tmp/remediate

USER appuser

EXPOSE 8000

# curl is available from the base stage — verify health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]

# ---------- Stage 6: Development (hot-reload + test deps) ----------
FROM java-tools AS development

# Install test deps on top of prod deps
RUN pip install --no-cache-dir pytest>=7.4.0 pytest-asyncio>=0.21.0 httpx>=0.25.0 hypothesis>=6.88.0

# Copy full source (overridden by volume mounts in docker-compose dev profile)
COPY . .

RUN mkdir -p /app/.vector_db /app/repos /app/reports /tmp/remediate

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------- Stage 7: Test (CI — runs pytest and exits) ----------
FROM deps-dev AS test

# Copy application source + tests
COPY app/ ./app/
COPY scan_github_repo.py .
COPY tests/ ./tests/
COPY .env.example .

# Env defaults for test run (no real services needed — all mocked)
ENV LLM_PROVIDER=ollama \
    GITHUB_TOKEN=test-token \
    VECTOR_DB_TYPE=faiss \
    REMEDIATION_MODE=deterministic

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "--no-header"]
