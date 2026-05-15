#!/usr/bin/env python3
"""
IDP Service Scaffolding CLI
Bootstraps a new microservice with Dockerfile, CI/CD workflow, Terraform module, and README.
"""

import argparse
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

# Force UTF-8 output on Windows (default is cp1252 which breaks emojis)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Available service types ──────────────────────────────────────────────────
VALID_TYPES = ["api", "worker", "scheduler"]

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path.cwd() / "services"


def parse_args():
    parser = argparse.ArgumentParser(
        prog="scaffold",
        description="Bootstrap a new microservice for the CloudFleet IDP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scaffold.py --name payments-service --type api
  python scaffold.py --name audit-worker --type worker
  python scaffold.py --name daily-report --type scheduler
        """,
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Service name (e.g. payments-service). Use kebab-case.",
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_TYPES,
        help=f"Service type: {', '.join(VALID_TYPES)}",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR),
        help="Directory where the scaffold will be created (default: ./services/<name>)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port the service listens on (default: 8000, only relevant for api type)",
    )
    return parser.parse_args()


def validate_name(name: str):
    import re
    if not re.match(r"^[a-z][a-z0-9-]+$", name):
        print(f"❌ Invalid service name '{name}'. Use lowercase letters, digits, and hyphens (e.g. my-service).")
        sys.exit(1)


def render_template(template_path: Path, context: dict) -> str:
    """Simple {{variable}} template renderer — no external deps required.

    Why not Jinja2 or Mako: a dev running this CLI should not need to pip install
    anything. str.replace is sufficient because templates only need variable
    substitution — no loops, no conditionals.
    """
    content = template_path.read_text()
    for key, value in context.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def scaffold_service(name: str, service_type: str, output_base: str, port: int):
    service_dir = Path(output_base) / name
    template_dir = TEMPLATES_DIR / service_type

    if service_dir.exists():
        print(f"❌ Directory '{service_dir}' already exists. Choose a different name or remove it first.")
        sys.exit(1)

    # ── Context variables injected into every template ────────────────────────
    context = {
        "SERVICE_NAME": name,
        "SERVICE_TYPE": service_type,
        "SERVICE_PORT": port,
        "SERVICE_NAME_SNAKE": name.replace("-", "_"),
        "SERVICE_NAME_UPPER": name.replace("-", "_").upper(),
        "YEAR": datetime.now().year,
        "DATE": datetime.now().strftime("%Y-%m-%d"),
    }

    print(f"\nScaffolding '{name}' ({service_type}) -> {service_dir}\n")

    # ── Create directory tree ─────────────────────────────────────────────────
    dirs = [
        service_dir,
        service_dir / "src",
        service_dir / ".github" / "workflows",
        service_dir / "terraform",
        service_dir / "tests",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  {d.relative_to(Path(output_base))}" )

    # ── Render and write files ────────────────────────────────────────────────
    files_to_render = [
        # (template_path, output_relative_to_service_dir)
        (template_dir / "Dockerfile.tmpl",            "Dockerfile"),
        (template_dir / "main.py.tmpl",               f"src/main.py"),
        (template_dir / "requirements.txt.tmpl",      "requirements.txt"),
        (TEMPLATES_DIR / "shared" / "ci.yml.tmpl", ".github/workflows/ci.yml"),  # shared across all types
        (template_dir / "terraform" / "main.tf.tmpl", "terraform/main.tf"),
        (template_dir / "terraform" / "variables.tf.tmpl", "terraform/variables.tf"),
        (template_dir / "terraform" / "outputs.tf.tmpl",   "terraform/outputs.tf"),
        (template_dir / "README.md.tmpl",             "README.md"),   # per-type README
        (TEMPLATES_DIR / "shared" / ".gitignore.tmpl", ".gitignore"),
        (TEMPLATES_DIR / "shared" / "tests" / "test_smoke.py.tmpl", "tests/test_smoke.py"),
    ]

    for tmpl_path, out_relative in files_to_render:
        if not tmpl_path.exists():
            print(f"  [skip] Template not found: {tmpl_path} — skipping")
            continue
        content = render_template(tmpl_path, context)
        out_path = service_dir / out_relative
        out_path.write_text(content)
        print(f"  + {out_relative}")

    print(f"\nDone! Service '{name}' scaffolded at: {service_dir}")
    print("\nNext steps:")
    print(f"  1. cd {service_dir}")
    print(f"  2. Review and customize src/main.py")
    print(f"  3. cd terraform && terraform init && terraform apply   # requires LocalStack running")
    print(f"  4. Push to GitLab/GitHub to trigger the CI pipeline\n")


def main():
    args = parse_args()
    validate_name(args.name)
    scaffold_service(args.name, args.type, args.output, args.port)


if __name__ == "__main__":
    main()
