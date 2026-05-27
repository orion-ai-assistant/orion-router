FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

# 1. Copy source code
COPY . /app/

# 2. Install package and dependencies
RUN uv pip install --system --no-cache-dir .

EXPOSE 20128

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "20128", "--log-level", "warning"]
