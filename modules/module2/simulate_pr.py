#!/usr/bin/env python3
"""
simulate_pr.py — Simulates GitHub PR webhook events against the IDP webhook server.
Works on Windows, macOS, and Linux. No external dependencies required.

Usage:
    python simulate_pr.py open   <pr_id> [branch] [service]
    python simulate_pr.py close  <pr_id>
    python simulate_pr.py sync   <pr_id> [branch] [service]
    python simulate_pr.py list
    python simulate_pr.py status <pr_id>
    python simulate_pr.py demo

Examples:
    python simulate_pr.py open  42 feature/payments payments-service
    python simulate_pr.py open  99 bugfix/login-fix
    python simulate_pr.py list
    python simulate_pr.py close 42
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8080")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{WEBHOOK_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except urllib.error.URLError as e:
        print(f"\n❌ Cannot reach webhook server at {WEBHOOK_URL}")
        print(f"   Make sure the stack is running: docker compose up -d")
        print(f"   Error: {e.reason}")
        sys.exit(1)


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{WEBHOOK_URL}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except urllib.error.URLError as e:
        print(f"\n❌ Cannot reach webhook server at {WEBHOOK_URL}")
        print(f"   Make sure the stack is running: docker compose up -d")
        print(f"   Error: {e.reason}")
        sys.exit(1)


def _print(data: dict):
    print(json.dumps(data, indent=2))


def _usage():
    print(__doc__)
    sys.exit(1)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_open(pr_id: str, branch: str = "feature/demo", service: str = "demo-app"):
    print(f"\n▶  Opening PR #{pr_id}  (branch: {branch}, service: {service})")
    result = _post("/webhook", {
        "action": "opened",
        "pr_id": pr_id,
        "branch": branch,
        "service_name": service,
        "author": "developer",
    })
    _print(result)

    if "port" in result:
        print(f"\n✅ Preview environment ready:")
        print(f"   Direct URL  →  http://localhost:{result['port']}")
        print(f"   Traefik URL →  http://pr-{pr_id}.localhost  (requires hosts entry)")


def cmd_close(pr_id: str, branch: str = "feature/demo", service: str = "demo-app"):
    print(f"\n⏹  Closing PR #{pr_id} ...")
    result = _post("/webhook", {
        "action": "closed",
        "pr_id": pr_id,
        "branch": branch,
        "service_name": service,
        "author": "developer",
    })
    _print(result)

    if "uptime_minutes" in result:
        print(f"\n💰 Cost summary:")
        print(f"   Uptime      : {result['uptime_minutes']} minutes")
        print(f"   Total cost  : ${result['total_cost_usd']}")


def cmd_sync(pr_id: str, branch: str = "feature/demo", service: str = "demo-app"):
    print(f"\n🔄 Syncing PR #{pr_id} — new commit on branch: {branch}")
    result = _post("/webhook", {
        "action": "synchronize",
        "pr_id": pr_id,
        "branch": branch,
        "service_name": service,
        "author": "developer",
    })
    _print(result)


def cmd_list():
    print(f"\n📋 Active preview environments:\n")
    result = _get("/environments")
    envs = result.get("active_environments", [])

    if not envs:
        print("  (no active environments)")
        return

    for env in envs:
        print(f"  PR #{env['pr_id']}  |  {env['branch']}  |  {env['status']}")
        print(f"    Direct URL  →  http://localhost:{env['port']}")
        print(f"    Uptime      →  {env['uptime_minutes']} min")
        print(f"    Cost so far →  ${env['estimated_cost_usd']}")
        print()


def cmd_status(pr_id: str):
    print(f"\n🔍 Status for PR #{pr_id}:\n")
    result = _get(f"/environments/{pr_id}")
    _print(result)


def cmd_demo():
    """Runs the full lifecycle: open two PRs, list, close one, list again."""
    print("\n🎬 Running full demo lifecycle...\n")

    print("─" * 50)
    print("Step 1: Open PR #42 (feature/payments)")
    cmd_open("42", "feature/payments", "payments-service")
    time.sleep(2)

    print("\n" + "─" * 50)
    print("Step 2: Open PR #99 (bugfix/login-fix)")
    cmd_open("99", "bugfix/login-fix", "auth-service")
    time.sleep(2)

    print("\n" + "─" * 50)
    print("Step 3: List all active environments")
    cmd_list()
    time.sleep(3)

    print("\n" + "─" * 50)
    print("Step 4: Push a new commit to PR #42 (sync)")
    cmd_sync("42", "feature/payments", "payments-service")
    time.sleep(2)

    print("\n" + "─" * 50)
    print("Step 5: Close PR #42")
    cmd_close("42")
    time.sleep(1)

    print("\n" + "─" * 50)
    print("Step 6: Final state — only PR #99 should remain")
    cmd_list()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        _usage()

    action = args[0].lower()
    pr_id  = args[1] if len(args) > 1 else None
    branch = args[2] if len(args) > 2 else "feature/demo"
    service = args[3] if len(args) > 3 else "demo-app"

    if action in ("open", "opened", "reopen", "reopened"):
        if not pr_id:
            print("❌ pr_id is required for 'open'")
            _usage()
        cmd_open(pr_id, branch, service)

    elif action in ("close", "closed"):
        if not pr_id:
            print("❌ pr_id is required for 'close'")
            _usage()
        cmd_close(pr_id, branch, service)

    elif action in ("sync", "synchronize"):
        if not pr_id:
            print("❌ pr_id is required for 'sync'")
            _usage()
        cmd_sync(pr_id, branch, service)

    elif action == "list":
        cmd_list()

    elif action == "status":
        if not pr_id:
            print("❌ pr_id is required for 'status'")
            _usage()
        cmd_status(pr_id)

    elif action == "demo":
        cmd_demo()

    else:
        print(f"❌ Unknown action: '{action}'")
        _usage()


if __name__ == "__main__":
    main()
