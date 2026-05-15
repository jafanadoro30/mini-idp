"""
IDP — Ephemeral Environment Webhook Server
Listens for simulated GitHub PR webhook events and manages the full
lifecycle of preview environments using Docker Compose + Traefik.
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("webhook-server")

app = FastAPI(title="IDP Preview Environment Manager", version="1.0.0")

# ── In-memory registry of active preview environments ────────────────────────
# Structure: { pr_id: { url, port, compose_file, created_at, status } }
# Why in-memory: sufficient for a prototype and eliminates a Redis dependency.
# Trade-off: state is lost if the server restarts. With more time: Redis with TTL
# matching the PR max lifetime so restarts don't orphan running environments.
ACTIVE_ENVS: dict[str, dict] = {}

# Base port for preview environments — each PR gets base_port + pr_id
BASE_PORT = int(os.getenv("PREVIEW_BASE_PORT", "9000"))
TRAEFIK_NETWORK = os.getenv("TRAEFIK_NETWORK", "idp-traefik")
PREVIEW_DOMAIN = os.getenv("PREVIEW_DOMAIN", "localhost")
COMPOSE_DIR = Path(os.getenv("COMPOSE_DIR", "/tmp/preview-envs"))
COMPOSE_DIR.mkdir(parents=True, exist_ok=True)

# Cost model (mocked) — USD per hour per resource
COST_PER_HOUR = {
    "container": 0.012,   # ~t3.micro equivalent
    "db": 0.025,          # small RDS equivalent
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class PREvent(BaseModel):
    action: Literal["opened", "reopened", "closed", "synchronize"]
    pr_id: str
    branch: str
    service_name: str = "demo-app"
    author: str = "developer"


class EnvStatus(BaseModel):
    pr_id: str
    status: str
    url: str
    port: int
    created_at: str
    uptime_minutes: float
    estimated_cost_usd: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _port_for(pr_id: str) -> int:
    """
    Port assignment: start from a hash of the pr_id, then walk forward
    until we find a port that is not already in use by another active env.
    This prevents collisions when two pr_ids hash to the same base port.
    """
    import socket  # noqa: PLC0415
    numeric = int("".join(filter(str.isdigit, pr_id)) or "1")
    candidate = BASE_PORT + (numeric % 900)

    # Collect ports already in use by active environments
    used_ports = {env["port"] for env in ACTIVE_ENVS.values()}

    # Walk forward until we find a free port (both in our registry and on the OS)
    for offset in range(900):
        port = BASE_PORT + ((numeric + offset) % 900)
        if port in used_ports:
            continue
        # Double-check at OS level
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", port))
                return port  # port is free
            except OSError:
                continue  # port already taken, try next

    # Fallback: return original candidate and let docker fail with a clear error
    return candidate


def _compose_path(pr_id: str) -> Path:
    return COMPOSE_DIR / f"docker-compose.pr-{pr_id}.yml"


def _project_name(pr_id: str) -> str:
    return f"preview-pr-{pr_id}"


def _generate_compose(pr_id: str, branch: str, service_name: str, port: int) -> str:
    """
    Generates a docker-compose YAML for the preview environment.
    Uses Traefik labels for automatic routing and a host-port fallback.
    """
    safe_branch = branch.replace("/", "-").replace("_", "-").lower()
    subdomain = f"pr-{pr_id}"

    return f"""# Auto-generated preview environment for PR #{pr_id}
# Branch: {branch} | Generated: {datetime.now(timezone.utc).isoformat()}
# DO NOT EDIT — managed by the IDP webhook server

networks:
  {TRAEFIK_NETWORK}:
    external: true
    name: {TRAEFIK_NETWORK}

services:
  app:
    # traefik/whoami is a lightweight image purpose-built for preview envs:
    # responds with request info (hostname, IP, headers) — no code needed.
    # Replace with your real service image in production.
    image: traefik/whoami:latest
    command:
      - --name
      - "PR #{pr_id} | Branch: {branch} | Service: {service_name}"
    ports:
      - "{port}:80"
    networks:
      - {TRAEFIK_NETWORK}
    labels:
      # Traefik routing
      - "traefik.enable=true"
      - "traefik.http.routers.{subdomain}.rule=Host(`{subdomain}.{PREVIEW_DOMAIN}`)"
      - "traefik.http.routers.{subdomain}.entrypoints=web"
      - "traefik.http.services.{subdomain}.loadbalancer.server.port=80"
      # IDP metadata
      - "idp.pr_id={pr_id}"
      - "idp.branch={safe_branch}"
      - "idp.service={service_name}"
    environment:
      - PR_ID={pr_id}
      - BRANCH={branch}
      - SERVICE_NAME={service_name}
    restart: unless-stopped
"""


def _run_compose(compose_file: Path, project: str, action: str) -> tuple[bool, str]:
    """Runs docker compose up or down. Returns (success, output)."""
    if action == "up":
        cmd = [
            "docker", "compose",
            "-f", str(compose_file),
            "-p", project,
            "up", "-d",
        ]
    elif action == "down":
        cmd = [
            "docker", "compose",
            "-f", str(compose_file),
            "-p", project,
            "down", "--remove-orphans", "--volumes",
        ]
    else:
        return False, f"Unknown action: {action}"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "docker compose timed out after 120s"
    except FileNotFoundError:
        return False, "docker not found in PATH"


def _calculate_cost(created_at_iso: str) -> float:
    """Mock cost estimate based on uptime."""
    created = datetime.fromisoformat(created_at_iso)
    now = datetime.now(timezone.utc)
    hours = (now - created).total_seconds() / 3600
    return round((COST_PER_HOUR["container"] + COST_PER_HOUR["db"]) * hours, 4)


def _uptime_minutes(created_at_iso: str) -> float:
    created = datetime.fromisoformat(created_at_iso)
    now = datetime.now(timezone.utc)
    return round((now - created).total_seconds() / 60, 1)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "IDP Webhook Server", "active_envs": len(ACTIVE_ENVS)}


@app.post("/webhook", status_code=202)
async def handle_webhook(event: PREvent):
    """
    Main webhook endpoint. Handles PR lifecycle events.

    Supported actions:
    - opened / reopened  → spin up preview environment
    - closed             → tear down and clean up
    - synchronize        → recreate (new commit pushed)
    """
    pr_id = event.pr_id
    logger.info("Received webhook: action=%s pr=%s branch=%s", event.action, pr_id, event.branch)

    if event.action in ("opened", "reopened"):
        return await _create_env(event)

    if event.action == "synchronize":
        # New commit — tear down and recreate
        if pr_id in ACTIVE_ENVS:
            await _destroy_env(pr_id)
        return await _create_env(event)

    if event.action == "closed":
        return await _destroy_env(pr_id)

    raise HTTPException(status_code=400, detail=f"Unknown action: {event.action}")


async def _create_env(event: PREvent) -> JSONResponse:
    pr_id = event.pr_id

    if pr_id in ACTIVE_ENVS:
        env = ACTIVE_ENVS[pr_id]
        return JSONResponse(
            status_code=200,
            content={"message": "Environment already running", "url": env["url"], "port": env["port"]},
        )

    port = _port_for(pr_id)
    compose_file = _compose_path(pr_id)
    project = _project_name(pr_id)

    # Write compose file
    compose_content = _generate_compose(pr_id, event.branch, event.service_name, port)
    compose_file.write_text(compose_content)
    logger.info("Compose file written: %s", compose_file)

    # Spin up
    success, output = _run_compose(compose_file, project, "up")
    if not success:
        compose_file.unlink(missing_ok=True)
        logger.error("docker compose up failed:\n%s", output)
        raise HTTPException(status_code=500, detail=f"Failed to start environment:\n{output}")

    url = f"http://pr-{pr_id}.{PREVIEW_DOMAIN}"
    port_url = f"http://localhost:{port}"
    created_at = datetime.now(timezone.utc).isoformat()

    ACTIVE_ENVS[pr_id] = {
        "url": url,
        "port_url": port_url,
        "port": port,
        "compose_file": str(compose_file),
        "project": project,
        "branch": event.branch,
        "service_name": event.service_name,
        "author": event.author,
        "created_at": created_at,
        "status": "running",
    }

    logger.info("Preview env up: PR=%s url=%s port=%d", pr_id, url, port)

    return JSONResponse(
        status_code=202,
        content={
            "message": "Preview environment created",
            "pr_id": pr_id,
            "url": url,
            "port_url": port_url,
            "port": port,
            "branch": event.branch,
            "estimated_hourly_cost_usd": sum(COST_PER_HOUR.values()),
        },
    )


async def _destroy_env(pr_id: str) -> JSONResponse:
    if pr_id not in ACTIVE_ENVS:
        return JSONResponse(
            status_code=200,
            content={"message": f"No active environment for PR {pr_id}"},
        )

    env = ACTIVE_ENVS[pr_id]
    compose_file = Path(env["compose_file"])
    project = env["project"]
    created_at = env["created_at"]

    cost = _calculate_cost(created_at)
    uptime = _uptime_minutes(created_at)

    success, output = _run_compose(compose_file, project, "down")
    if not success:
        logger.error("docker compose down failed:\n%s", output)
        # Don't block cleanup — mark as failed but continue
        ACTIVE_ENVS[pr_id]["status"] = "teardown_failed"
    else:
        compose_file.unlink(missing_ok=True)
        del ACTIVE_ENVS[pr_id]
        logger.info("Preview env destroyed: PR=%s uptime=%.1fmin cost=$%.4f", pr_id, uptime, cost)

    return JSONResponse(
        status_code=202,
        content={
            "message": "Preview environment destroyed",
            "pr_id": pr_id,
            "uptime_minutes": uptime,
            "total_cost_usd": cost,
            "cost_breakdown": {
                "container_hours": round(uptime / 60, 4),
                "rate_per_hour": COST_PER_HOUR,
            },
        },
    )


@app.get("/environments")
def list_environments():
    """Lists all currently active preview environments with cost estimates."""
    result = []
    for pr_id, env in ACTIVE_ENVS.items():
        result.append({
            "pr_id": pr_id,
            "status": env["status"],
            "url": env["url"],
            "port_url": env["port_url"],
            "port": env["port"],
            "branch": env["branch"],
            "service_name": env["service_name"],
            "author": env["author"],
            "created_at": env["created_at"],
            "uptime_minutes": _uptime_minutes(env["created_at"]),
            "estimated_cost_usd": _calculate_cost(env["created_at"]),
        })
    return {"active_environments": result, "count": len(result)}


@app.get("/environments/{pr_id}")
def get_environment(pr_id: str):
    """Get details for a specific preview environment."""
    if pr_id not in ACTIVE_ENVS:
        raise HTTPException(status_code=404, detail=f"No active environment for PR {pr_id}")
    env = ACTIVE_ENVS[pr_id]
    return {
        **env,
        "uptime_minutes": _uptime_minutes(env["created_at"]),
        "estimated_cost_usd": _calculate_cost(env["created_at"]),
    }


@app.delete("/environments/{pr_id}")
async def delete_environment(pr_id: str):
    """Manually destroy a preview environment (no webhook needed)."""
    return await _destroy_env(pr_id)


@app.get("/health")
def health():
    return {"status": "ok", "active_envs": len(ACTIVE_ENVS)}
