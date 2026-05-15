# Copy the Docker CLI binary from the official image into a Python slim base.
# This avoids Alpine/Debian library conflicts while keeping the image lean.
FROM docker:27-cli AS docker-cli

FROM python:3.12-slim

# Grab just the docker and docker compose binaries from the official CLI image
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PYTHONUNBUFFERED=1
ENV PREVIEW_BASE_PORT=9000
ENV PREVIEW_DOMAIN=localhost
ENV TRAEFIK_NETWORK=idp-traefik
ENV COMPOSE_DIR=/tmp/preview-envs

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
