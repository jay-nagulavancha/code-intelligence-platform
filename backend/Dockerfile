# =============================================================================
# Code Intelligence Platform - Backend Dockerfile
# Multi-stage build for FastAPI + Security Scanning Tools
# =============================================================================

# ---------- Stage 1: Base Python ----------
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies (git is required for cloning repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------- Stage 2: Python Dependencies ----------
FROM base AS dependencies

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Stage 3: Java Scanning Tools ----------
FROM dependencies AS java-tools

# Install JDK (not JRE — needed for compilation), Maven, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    maven \
    gradle \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME for the default JDK
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Install SpotBugs
ARG SPOTBUGS_VERSION=4.8.3
RUN wget -q https://github.com/spotbugs/spotbugs/releases/download/${SPOTBUGS_VERSION}/spotbugs-${SPOTBUGS_VERSION}.tgz \
    -O /tmp/spotbugs.tgz && \
    tar -xzf /tmp/spotbugs.tgz -C /opt/ && \
    ln -s /opt/spotbugs-${SPOTBUGS_VERSION}/bin/spotbugs /usr/local/bin/spotbugs && \
    rm /tmp/spotbugs.tgz

# Install OWASP Dependency-Check
ARG DC_VERSION=9.0.9
RUN wget -q https://github.com/jeremylong/DependencyCheck/releases/download/v${DC_VERSION}/dependency-check-${DC_VERSION}-release.zip \
    -O /tmp/dc.zip && \
    unzip -q /tmp/dc.zip -d /opt/ && \
    ln -s /opt/dependency-check/bin/dependency-check.sh /usr/local/bin/dependency-check.sh && \
    rm /tmp/dc.zip

# ---------- Stage 4: Production ----------
FROM java-tools AS production

# Copy application code
COPY app/ ./app/

# Copy CLI scanner script and config files
COPY scan_github_repo.py .
COPY .env.example .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Create directories for vector DB, temp repos, and scan reports
RUN mkdir -p /app/.vector_db /app/repos /app/reports && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------- Stage 5: Development (with hot-reload) ----------
FROM java-tools AS development

# Copy full source tree (overridden by volume mounts in docker-compose)
COPY . .

# Create directories
RUN mkdir -p /app/.vector_db /app/repos /app/reports

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
