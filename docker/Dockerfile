# ==============================================================================
# Stage 1: Build & Compilation Environment (Wheels Builder)
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compilation toolchain and headers needed for Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and pre-build binary wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt pre-commit pytest ruff

# ==============================================================================
# Stage 2: Hardened Ephemeral Runtime Environment
# ==============================================================================
FROM python:3.11-slim AS runtime

LABEL maintainer="HistorySnooze Team <triplex2909.002@gmail.com>" \
      description="HistorySnooze Containerized Orchestrator & Media Generation Station" \
      version="1.0.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NODE_VERSION=20 \
    HOME="/home/appuser" \
    PATH="/home/appuser/.local/bin:/usr/local/bin:$PATH" \
    PYTHONPATH="/workspace"

# 1. Install system utilities, FFmpeg probe, and Chrome headless shared libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    procps \
    ffmpeg \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxinerama1 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Node.js 20.x LTS via official NodeSource distribution
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 3. Create non-root user and group (UID 1000, GID 1000)
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser && \
    chmod 700 /home/appuser

# 4. Prepare workspace
WORKDIR /workspace
RUN chown -R appuser:appuser /workspace

# 5. Install pre-compiled Python wheels from Stage 1
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

# 6. Copy application code with non-root ownership
COPY --chown=appuser:appuser . /workspace

# 7. Enforce non-root execution
USER appuser

# 8. Set entrypoint and default command
ENTRYPOINT ["/bin/bash", "/workspace/docker/entrypoint.sh"]
CMD ["python3", "pipeline_orchestrator.py", "--help"]
