#!/usr/bin/env python3
"""
IDP Ops Assistant — Module 4
A CLI chatbot that fetches live Prometheus metrics on every question
and answers in plain English using Groq (Llama 3).

Usage:
    python modules/module4/ops_assistant.py
    python modules/module4/ops_assistant.py --question "Is everything healthy?"
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL   = "https://api.groq.com/openai/v1/chat/completions"
# Why Groq over OpenAI: free tier with no credit card, fastest inference latency
# (~200ms), generous rate limits. Model is swappable via this constant.
# Why llama-3.1-8b-instant over larger models: sufficient reasoning for metric
# analysis, faster response, lower cost per token.
GROQ_MODEL     = "llama-3.1-8b-instant"

# ── Security validation ───────────────────────────────────────────────────────

def _validate_api_key(key: str) -> None:
    """
    Validates the API key before any network call is made.
    Fails fast with a clear message rather than leaking the key in an error.
    """
    if not key:
        print("❌ GROQ_API_KEY is not set.")
        print("   1. Get a free key at https://console.groq.com")
        print("   2. Set it as an environment variable — never hardcode it:")
        print()
        print("   PowerShell:  $env:GROQ_API_KEY='gsk_...'"  )
        print("   bash/zsh:    export GROQ_API_KEY='gsk_...'" )
        print()
        print("   Or add it to your .env file (it is already in .gitignore).")
        sys.exit(1)

    if not key.startswith("gsk_"):
        print("❌ GROQ_API_KEY does not look like a valid Groq key (should start with gsk_).")
        print("   Get a key at https://console.groq.com")
        sys.exit(1)

    if len(key) < 20:
        print("❌ GROQ_API_KEY looks too short — it may be malformed.")
        sys.exit(1)

# ── Prometheus client ─────────────────────────────────────────────────────────

def _prom_query(query: str) -> list:
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "success":
                return data["data"]["result"]
    except Exception:
        pass
    return []


def _prom_query_range(query: str, minutes: int = 5) -> list:
    """Query a range of the last N minutes to compute uptime windows."""
    import time
    end   = int(time.time())
    start = end - (minutes * 60)
    url   = (
        f"{PROMETHEUS_URL}/api/v1/query_range"
        f"?query={urllib.parse.quote(query)}"
        f"&start={start}&end={end}&step=15"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "success":
                return data["data"]["result"]
    except Exception:
        pass
    return []


def _prom_alerts() -> list:
    url = f"{PROMETHEUS_URL}/api/v1/alerts"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "success":
                return [a for a in data["data"]["alerts"] if a.get("state") == "firing"]
    except Exception:
        pass
    return []


def _scalar(results: list) -> float | None:
    if results and results[0].get("value"):
        try:
            return float(results[0]["value"][1])
        except (ValueError, IndexError):
            pass
    return None


def _per_job(results: list) -> dict:
    out = {}
    for r in results:
        job = r.get("metric", {}).get("job", "unknown")
        try:
            out[job] = float(r["value"][1])
        except (KeyError, ValueError, IndexError):
            out[job] = None
    return out


def _minutes_without_errors(job: str) -> float | None:
    """
    Checks how many minutes ago the last 5xx spike occurred for a job.
    Returns minutes of clean traffic, or None if no data.
    """
    import time
    results = _prom_query_range(
        f'sum(rate(http_requests_total{{job="{job}",status=~"5.."}}[1m]))',
        minutes=60,
    )
    if not results or not results[0].get("values"):
        return None

    values = results[0]["values"]  # [[timestamp, value], ...]
    now = time.time()

    # Walk backwards to find the last non-zero error point
    for ts, val in reversed(values):
        if float(val) > 0.001:
            minutes_ago = (now - float(ts)) / 60
            return round(minutes_ago, 1)

    # All zeros — no errors in the entire window
    total_minutes = (float(values[-1][0]) - float(values[0][0])) / 60
    return round(total_minutes, 1)


# ── Metrics snapshot ──────────────────────────────────────────────────────────

def collect_metrics() -> dict:
    """
    Fetches a rich snapshot from Prometheus with enough context
    for the LLM to give specific, useful answers.
    """
    up_status    = _per_job(_prom_query("up"))
    error_rate   = _per_job(_prom_query(
        'sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)'
        ' / sum(rate(http_requests_total[5m])) by (job)'
    ))
    p99_latency  = _per_job(_prom_query(
        'histogram_quantile(0.99,'
        ' sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))'
    ))
    throughput   = _per_job(_prom_query(
        'sum(rate(http_requests_total[5m])) by (job)'
    ))

    # Compute clean minutes per job
    clean_minutes = {}
    for job in up_status:
        mins = _minutes_without_errors(job)
        clean_minutes[job] = mins

    # Firing alerts
    raw_alerts = _prom_alerts()
    alerts = [
        {
            "name":        a["labels"].get("alertname"),
            "severity":    a["labels"].get("severity"),
            "job":         a["labels"].get("job", "unknown"),
            "summary":     a.get("annotations", {}).get("summary", ""),
            "firing_since": a.get("activeAt", "unknown"),
        }
        for a in raw_alerts
    ]

    # Build per-service summary
    services = []
    for job, is_up in up_status.items():
        err  = error_rate.get(job)
        lat  = p99_latency.get(job)
        tput = throughput.get(job)
        mins = clean_minutes.get(job)

        # Determine if this service has HTTP instrumentation
        # (i.e. it emits http_requests_total). Services like prometheus
        # and traefik use different metric names — mark them clearly.
        has_http_metrics = any(v is not None for v in [err, lat, tput])

        entry = {
            "name":   job,
            "status": "up" if is_up == 1.0 else "down",
        }

        if has_http_metrics:
            entry["error_rate_pct"]         = round(err * 100, 2) if err is not None else None
            entry["p99_latency_ms"]          = round(lat * 1000, 1) if lat is not None else None
            entry["throughput_req_per_sec"]  = round(tput, 3) if tput is not None else None
            entry["minutes_without_errors"]  = mins
        else:
            entry["note"] = "Service is up but does not emit http_requests_total metrics. Only reachability (up/down) is tracked."

        services.append(entry)

    return {
        "fetched_at":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "services":      services,
        "firing_alerts": alerts,
    }


# ── Groq LLM client ───────────────────────────────────────────────────────────

def ask_llm(metrics: dict, question: str) -> str:
    if not GROQ_API_KEY:
        return "❌ GROQ_API_KEY not set. Run: $env:GROQ_API_KEY='gsk_...'"

    system_prompt = """\
You are an SRE assistant embedded in an Internal Developer Platform.
You receive a live snapshot of Prometheus metrics and answer questions
about system health in plain, conversational English.

Rules:
- Always mention service names explicitly
- Express error rates as percentages (e.g. "2.4% error rate")
- Express latency in milliseconds (e.g. "p99 is 320ms")
- Use the "minutes_without_errors" field to say things like
  "no errors in the last 12 minutes" or "last error was 3 minutes ago"
- If a service is down, say so immediately and clearly
- If alerts are firing, mention them with their severity
- If metrics are null for a service, say data is not available yet — do NOT
  say the service is down just because metrics are missing
- Only say a service is "down" if its status field is explicitly "down"
- Keep answers concise but specific — no vague statements like "everything looks fine"
"""

    user_prompt = f"""\
Live metrics snapshot (fetched just now):
{json.dumps(metrics, indent=2)}

Question: {question}
"""

    payload = json.dumps({
        "model":       GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens":  512,
    }).encode()

    req = urllib.request.Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent":    "idp-ops-assistant/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        # Read error body but never echo the request (which contains the key)
        try:
            error_body = json.loads(e.read())
            message = error_body.get("error", {}).get("message", str(e))
        except Exception:
            message = f"HTTP {e.code}"
        return f"❌ Groq API error: {message}"
    except Exception as e:
        # Never include the full exception which might contain auth headers
        return f"❌ Could not reach Groq API. Check your internet connection."


# ── CLI ───────────────────────────────────────────────────────────────────────

SUGGESTED_QUESTIONS = [
    "Is everything healthy?",
    "Which service has the highest error rate?",
    "How long have the services been running without errors?",
    "Are there any slow services right now?",
    "Summarize the current system status.",
    "Should I be worried about anything?",
]

BANNER = """
╔══════════════════════════════════════════════════════╗
║          IDP Ops Assistant  —  Module 4              ║
║  Live Prometheus metrics · Powered by Groq           ║
╚══════════════════════════════════════════════════════╝
Type your question, 'help' for suggestions, or 'quit' to exit.
Metrics are fetched fresh on every question.
"""


def interactive_mode():
    print(BANNER)

    while True:
        try:
            question = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not question:
            continue

        if question.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        if question.lower() == "help":
            print("\nSuggested questions:")
            for i, q in enumerate(SUGGESTED_QUESTIONS, 1):
                print(f"  {i}. {q}")
            print()
            continue

        # Fetch fresh metrics on every question
        print("  📡 Fetching live metrics...", end="\r")
        metrics = collect_metrics()
        services_up = sum(1 for s in metrics["services"] if s["status"] == "up")
        print(f"  📡 {services_up} service(s) up — metrics as of {metrics['fetched_at']}")

        if metrics["firing_alerts"]:
            print(f"  🚨 {len(metrics['firing_alerts'])} alert(s) firing")

        print("\n🤖 Assistant: ", end="", flush=True)
        answer = ask_llm(metrics, question)
        print(answer)
        print()


def main():
    global PROMETHEUS_URL, GROQ_API_KEY  # must be declared before any use

    parser = argparse.ArgumentParser(
        description="IDP Ops Assistant — ask questions about your live system",
    )
    parser.add_argument("--question", "-q", help="Single question mode")
    parser.add_argument("--prometheus", default=PROMETHEUS_URL)
    parser.add_argument("--api-key", default=GROQ_API_KEY)
    args = parser.parse_args()

    PROMETHEUS_URL = args.prometheus
    if args.api_key:
        GROQ_API_KEY = args.api_key

    # Validate API key before doing anything else
    _validate_api_key(GROQ_API_KEY)

    # Quick connectivity check
    try:
        urllib.request.urlopen(f"{PROMETHEUS_URL}/-/healthy", timeout=3)
    except Exception:
        print(f"⚠️  Could not reach Prometheus at {PROMETHEUS_URL}")
        print("   Make sure the stack is running: docker compose up -d")
        sys.exit(1)

    print(f"✅ Connected to Prometheus at {PROMETHEUS_URL}")

    if args.question:
        print(f"\nYou: {args.question}")
        print("📡 Fetching live metrics...")
        metrics = collect_metrics()
        print(f"✅ Metrics fetched — {metrics['fetched_at']}\n")
        print("🤖 Assistant:")
        print(ask_llm(metrics, args.question))
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
