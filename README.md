# Mini IDP

Technical challenge for the AI Developer Experience Engineer role at Clara. Three required modules and one AI bonus, all running locally with Docker. No cloud account needed.

---

## Problem being solved

Clara has 100+ engineers across Mexico, Colombia, and Brazil. Today, spinning up a new service, creating a preview environment, or wiring up an alert means manual steps, Slack threads, and knowledge that lives in two heads. This IDP fixes that.

---

## Prerequisites

### Required for all modules

| Tool | Version | Install |
|---|---|---|
| Docker Desktop | Latest | https://www.docker.com/products/docker-desktop |
| Python | 3.10+ | https://www.python.org/downloads |

Docker Desktop already includes Docker Compose, so no extra install is needed on any OS.

### Required only for Module 1

| Tool | Windows | macOS | Linux |
|---|---|---|---|
| Terraform >= 1.5 | Download from https://developer.hashicorp.com/terraform/install, extract and add to PATH | brew install terraform | apt install terraform |
| AWS CLI v2 | Download from https://aws.amazon.com/cli/ | brew install awscli | apt install awscli |

Terraform and AWS CLI are only needed for Module 1. Modules 2, 3, and 4 run without them.

### Required only for Module 4

A free Groq API key from https://console.groq.com. No credit card required.

---


## Demo

>For the challenge, you can see the demo video below.
[Demo video](../video/video_clara.mkv)

---
## Quick Start

To start the full stack:

    git clone repo-url
    docker compose up -d
    docker compose ps

Once up:

| Service | URL | What it is |
|---|---|---|
| Webhook Server | http://localhost:8080 | Module 2 API |
| Traefik Dashboard | http://localhost:8081 | Shows active preview env routes |
| Demo App | http://localhost:8082 | Module 3 observability target |
| Prometheus | http://localhost:9090 | Metrics and alerts |
| Grafana | http://localhost:3000 | Dashboards, login admin/admin |
| LocalStack | http://localhost:4566 | AWS simulation for Module 1 |

### Makefile

On macOS and Linux, make is available out of the box. On Windows, install Git Bash from https://git-scm.com/downloads or use WSL. Otherwise just run the commands directly as shown in each section.

    make help
    make up
    make test
    make demo
    make scaffold NAME=payments-service TYPE=api

---

## Module 1 -- Service Scaffolding CLI

One command and you have a fully wired microservice ready to push. Dockerfile, CI pipeline, AWS resources, and a runbook included.

### Run

    python scaffold_cli/scaffold.py --name payments-service --type api
    python scaffold_cli/scaffold.py --name audit-worker --type worker
    python scaffold_cli/scaffold.py --name daily-report --type scheduler

### AWS resources per type

| Type | Resources |
|---|---|
| api | S3 bucket, SSM parameter |
| worker | SQS queue, DLQ (3 retries, 14-day retention), SSM parameter |
| scheduler | S3 bucket for job results, SSM parameter with cron expression |

### Provision via LocalStack

    docker compose up -d localstack
    aws configure  # use test/test/us-east-1/json
    cd services/payments-service/terraform
    terraform init
    terraform apply -auto-approve
    aws --endpoint-url=http://localhost:4566 s3 ls

### Design decisions

No external Python dependencies. The CLI uses stdlib only. Template rendering is a plain string replace, enough for substitution without loops or conditionals. Anyone can run it without installing anything.

Different resources per type. A worker without a queue is broken. The scaffold being opinionated prevents the kind of bug where something deploys but does nothing.

Terraform endpoint overrides for LocalStack. To point at real AWS, remove those three lines. Nothing else changes.

---

## Module 2 -- Ephemeral Environment Lifecycle

Every PR gets its own isolated environment. No more asking someone to deploy your branch so you can test it.

### Run

simulate_pr.py works on Windows, macOS, and Linux. Pure Python stdlib, nothing to install.

    python modules/module2/simulate_pr.py open 42 feature/payments payments-service
    python modules/module2/simulate_pr.py list
    python modules/module2/simulate_pr.py sync 42 feature/payments
    python modules/module2/simulate_pr.py close 42
    python modules/module2/simulate_pr.py demo

Port is always 9000 + (pr_id mod 900), so PR 42 is always port 9042.

    curl http://localhost:9042

### API reference

| Method | Path | Description |
|---|---|---|
| POST | /webhook | PR events: opened, closed, synchronize |
| GET | /environments | All active environments with uptime and cost |
| GET | /environments/id | Details for a specific environment |
| DELETE | /environments/id | Manually destroy an environment |
| GET | /health | Health check |

### Design decisions

Docker socket mount instead of Docker SDK or Kubernetes Jobs. The server writes a compose file and calls docker compose up through subprocess. Files are readable artifacts on disk. Docker SDK has limited Compose support. K8s Jobs would be right in production but need a cluster and RBAC that make no sense here. The trade-off is root access to the host Docker daemon, which is acceptable for a local dev tool.

Traefik instead of Nginx. Traefik picks up Docker labels automatically. Nginx would need a new upstream block and a reload on every PR event.

In-memory state instead of Redis. Works for a prototype. State is lost on restart. Redis with TTL would be the fix with more time.

---

## Module 3 -- Observability as Code

Dashboards and alerts from day one. No manual clicks in any UI.

    docker compose up -d

### Grafana dashboard

Open http://localhost:3000, login admin/admin. The IDP SLI Overview dashboard loads automatically.

| Panel | SLO |
|---|---|
| p99 Latency | under 1s |
| Error Rate | under 5% |
| Throughput | above 0.1 req/s |
| Current SLI Status | live values |

The demo app generates continuous traffic with a deliberate 15% error rate on /flaky so dashboards have real data from minute one.

### Alerting rules

Every alert uses for: 5m. The condition must be true for 5 continuous minutes before firing. Kills most false alarms from transient spikes and deploys.

| Alert | Condition | Severity |
|---|---|---|
| HighErrorRate | above 5% for 5m | warning |
| CriticalErrorRate | above 25% for 5m | critical |
| HighP99Latency | p99 above 1s for 5m | warning |
| LowThroughput | below 0.1 req/s for 5m | warning |
| ServiceDown | up == 0 for 2m | critical |

Check http://localhost:9090/alerts for currently firing alerts.

### Design decisions

JSON provisioning instead of manual UI. Grafana picks up datasources and dashboards from mounted files at startup. allowUiUpdates false means UI changes are discarded on restart.

Inline Prometheus metrics in the demo app. No external dependency. About 40 lines of stdlib. Keeps the image small.

for 5m on every alert. One slow response at 3am should not page anyone. Five minutes of sustained condition is the right trade-off.

---

## Module 4 -- Ops Assistant (AI Bonus)

Instead of opening five tabs to check if something is broken, you ask and get a specific answer based on live data.

### Setup

    Windows: set GROQ_API_KEY=gsk_...
    macOS/Linux: export GROQ_API_KEY=gsk_...

Do not paste keys in the terminal. Shell history keeps them. Use your editor to fill in .env instead. That file is in .gitignore.

### Run

    python modules/module4/ops_assistant.py
    python modules/module4/ops_assistant.py --question "Is everything healthy?"

### How it works

On every question: fetch live metrics from Prometheus, build a JSON snapshot with error rate, p99 latency, throughput, up/down status, and minutes since last error, then send it to the LLM with a system prompt that gives it an SRE persona and explicit formatting rules.

No fine-tuning, no RAG pipeline, no vector database. The knowledge base is a few hundred bytes of live JSON. Prompt engineering is enough.

### Design decisions

Groq instead of OpenAI or Ollama. Groq is free, no credit card, around 200ms inference. OpenAI needs a paid account. Ollama needs a 4GB download. Anyone can have this running in 2 minutes.

Metrics fetched per question, not cached. One API call per question. Always fresh data, predictable cost.

Prompt engineering instead of RAG. The data is live JSON, not a document corpus. Adding a vector database would add complexity with no benefit.

---

## Testing

All tests run offline. No Docker, no running services, no API calls needed.

    pip install -r tests/requirements-test.txt
    pytest tests/ -v

Expected output:

    tests/test_module1_scaffold.py::test_api_generates_expected_files          PASSED
    tests/test_module1_scaffold.py::test_each_type_gets_correct_terraform_resources PASSED
    tests/test_module1_scaffold.py::test_invalid_name_is_rejected              PASSED
    tests/test_module1_scaffold.py::test_service_name_substituted_correctly    PASSED
    tests/test_module2_lifecycle.py::test_port_is_deterministic_and_in_range   PASSED
    tests/test_module2_lifecycle.py::test_generated_compose_is_valid_yaml      PASSED
    tests/test_module2_lifecycle.py::test_cost_increases_with_uptime           PASSED
    tests/test_module3_observability.py::test_prometheus_scrapes_demo_app      PASSED
    tests/test_module3_observability.py::test_all_alerts_have_noise_suppression PASSED
    tests/test_module3_observability.py::test_grafana_dashboard_has_three_sli_panels PASSED
    tests/test_module4_assistant.py::test_empty_key_is_rejected                PASSED
    tests/test_module4_assistant.py::test_valid_key_passes                     PASSED
    tests/test_module4_assistant.py::test_error_never_exposes_api_key          PASSED
    13 passed in 0.80s

| Test | What it checks |
|---|---|
| test_api_generates_expected_files | CLI produces all required files |
| test_each_type_gets_correct_terraform_resources | api gets S3 only, worker gets SQS and DLQ, scheduler gets S3 and cron |
| test_invalid_name_is_rejected | CLI rejects names with spaces or special characters |
| test_service_name_substituted_correctly | No unresolved placeholders in generated files |
| test_port_is_deterministic_and_in_range | Same PR ID always maps to same port, always 9000 to 9899 |
| test_generated_compose_is_valid_yaml | Dynamic compose parses as valid YAML with Traefik labels |
| test_cost_increases_with_uptime | 2-hour env costs more than 5-minute env |
| test_prometheus_scrapes_demo_app | prometheus.yml has a scrape job for demo-app |
| test_all_alerts_have_noise_suppression | Every alert has a for clause |
| test_grafana_dashboard_has_three_sli_panels | Dashboard has p99 latency, error rate, and throughput |
| test_empty_key_is_rejected | Assistant exits with a clear message if no key is set |
| test_valid_key_passes | Valid key does not trigger the validation |
| test_error_never_exposes_api_key | API errors never log the key |

---

## Security

| Rule | How it is enforced |
|---|---|
| Keys never in code | ops_assistant.py reads only from env var, no hardcoded defaults |
| Keys never in Git | .env is in .gitignore, only .env.example with empty values is committed |
| Startup validation | Assistant exits with a clear message if the key is missing or malformed |
| Errors never log the key | Error handler only extracts the message text |

To set up credentials:

    cp .env.example .env
    # Open .env in your editor and fill in GROQ_API_KEY
    # Then load it in the current session

    Windows: :GROQ_API_KEY="gsk_..."
    macOS/Linux: export GROQ_API_KEY="gsk_..."

If a key is accidentally exposed: go to https://console.groq.com/keys, delete it, create a new one. Check Git history with git log --all -S "gsk_" and remove it with git filter-repo if needed.

What is not secured (prototype scope):

Grafana runs with admin/admin. In production, use SSO.
LocalStack accepts test/test, intentional for local dev.
Webhook server has no auth on port 8080. In production, validate the GitHub HMAC signature.
Preview env URLs are not isolated by team. Cloudflare Access would handle that in production.

---

## Architecture decisions

### Why one repo with a shared docker-compose

The modules have real dependencies. Module 3 scrapes Module 2, and Module 4 needs Prometheus running. Splitting into separate repos means coordinating startup order with no real benefit for a prototype. One docker compose up starts everything.

### Module 1: Python over Go, Bash, or Node.js

Bash is brittle on Windows. Go has appealing binary output but the setup overhead is too high for a 3-day challenge. Node.js needs npm install and a package.json. Python stdlib runs everywhere without setup and is the same language across all four modules.

### Module 1: plain string replace over Jinja2

Templates only need substitution, not loops or conditionals. str.replace is 5 lines and zero dependencies. Nobody should need to pip install anything to run the CLI.

### Module 2: Docker socket over Docker SDK or Kubernetes Jobs

Docker SDK has limited Compose support. K8s Jobs are right for production but need a cluster and RBAC that make no sense locally. The socket mount leaves readable compose files on disk. Trade-off: root-equivalent host access, acceptable for a local tool.

### Module 2: Traefik over Nginx

Traefik auto-discovers containers via Docker labels. No config file to write, no reload to trigger. Nginx needs a new upstream block and a process reload on every PR event.

### Module 3: Prometheus and Grafana over Datadog or CloudWatch

Datadog needs an account and network access to datadoghq.com. Nobody should have to create an account just to run the stack. CloudWatch has higher config overhead. Prometheus is the industry standard for containers and has zero external dependencies.

### Module 4: Groq over OpenAI or Ollama

OpenAI needs a paid account. Ollama needs a 4GB download. Groq is free, no credit card, and about 200ms inference latency. Anyone can be up and running in 2 minutes.

### Module 4: prompt engineering over RAG or fine-tuning

The knowledge base is a few hundred bytes of live JSON from Prometheus. There is no document corpus to index. RAG would add a vector database with no benefit. The simplest approach that solves the problem is the right one.

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| CLI language | Python stdlib | Go, Node.js, Bash | Zero setup, cross-platform |
| Template engine | String replace | Jinja2 | No dependencies |
| Preview orchestration | Docker socket | Docker SDK, K8s | Readable artifacts, no extra deps |
| Reverse proxy | Traefik | Nginx | Auto-discovery via Docker labels |
| Metrics stack | Prometheus and Grafana | Datadog, CloudWatch | No external accounts needed |
| LLM provider | Groq | OpenAI, Ollama | Free tier, fastest inference |
| AI approach | Prompt engineering | RAG, fine-tuning | Knowledge is live JSON not a corpus |

---

## What I would do differently with more time

Module 1: add a --dry-run flag to preview the file tree without writing anything, interactive mode with guided prompts, support for Go and Node.js service types.

Module 2: persist environment state in Redis with TTL so restarts do not orphan running envs, auto-cleanup for environments that exceed a max lifetime, post the preview URL as a PR comment with real GitHub integration.

Module 3: add Loki for log aggregation, add Alertmanager with a Slack webhook so alerts actually notify someone, make Module 1 auto-provision a Grafana dashboard for every new service.

Module 4: let the assistant trigger actions like restarting a container, add conversation history so follow-up questions have context, stream the response token by token instead of waiting for the full answer.
