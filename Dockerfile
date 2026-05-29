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
COPY --from=frontend-builder /build/dashboard/out /app/dashboard/out

# 3. Install backend packages and dependencies
RUN uv pip install --system --no-cache-dir .

EXPOSE 20128

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "20128", "--log-level", "warning"]
