FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

COPY src ./src
COPY tests ./tests