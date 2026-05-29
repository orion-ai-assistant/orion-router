# --- Stage 1: Build Next.js Frontend ---
FROM node:20-alpine AS frontend-builder
WORKDIR /build/dashboard

# Copy lock files and install dependencies
COPY dashboard/package*.json ./
RUN npm ci

# Copy sources and compile static export
COPY dashboard/ ./
RUN npm run build

# --- Stage 2: Final FastAPI/Python Production Image ---
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install package manager uv
RUN pip install --no-cache-dir uv

# 1. Copy backend and project files
COPY . /app/

# 2. Copy the compiled Next.js static files from Stage 1
COPY --from=frontend-builder /build/dashboard/out /dashboard_out
ENV DASHBOARD_OUT_DIR=/dashboard_out

# 3. Install backend packages and dependencies
RUN uv pip install --system --no-cache-dir .

ENV ROUTER_PORT=20128
EXPOSE 20128

CMD ["python", "main.py"]
