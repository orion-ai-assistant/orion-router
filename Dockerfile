# --- Stage 1: Build Next.js Frontend ---
FROM node:20-alpine AS frontend-builder
WORKDIR /build/dashboard

# Copy lock files and install dependencies
COPY dashboard/package*.json ./
RUN npm ci

# Copy sources and compile static export
COPY dashboard/ ./
COPY providers/ /build/providers/
RUN npm run build

# --- Stage 2: Final FastAPI/Python Production Image ---
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/orion-ai-assistant/orion-router"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Local video frame extraction for vision-capable OpenAI models.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install package manager uv
RUN pip install --no-cache-dir uv

# 1. Copy backend and project files
COPY . /app/

# 2. Copy the compiled Next.js static files from Stage 1
COPY --from=frontend-builder /build/dashboard/out /dashboard_out
ENV DASHBOARD_OUT_DIR=/dashboard_out

# 3. Install backend packages and dependencies
RUN uv pip install --system --no-cache-dir .

ENV ORION_ROUTER_TLS_PORT=9443

CMD ["python", "main.py"]
