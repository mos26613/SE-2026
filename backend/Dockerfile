# Backend image, built in two stages (User Story 1.4.1).

# 1. Install the Python packages into their own folder, so pip and its cache stay out of
#    the image that runs.
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 2. The image that runs: Python, the installed packages and the code.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Docker marks the container "healthy" when /health answers. docker-compose.yml starts the
# frontend only after that.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

# --reload is for local development only; production gets its own build (User Story 1.4.3)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
