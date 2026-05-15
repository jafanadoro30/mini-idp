"""
Tests for Module 1 — Service Scaffolding CLI
"""
import subprocess, sys, tempfile
from pathlib import Path

SCAFFOLD = Path(__file__).parent.parent / "scaffold_cli" / "scaffold.py"

def scaffold(name, service_type, output_dir):
    return subprocess.run(
        [sys.executable, str(SCAFFOLD), "--name", name, "--type", service_type, "--output", output_dir],
        capture_output=True, text=True,
    )

def test_api_generates_expected_files():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold("payments-service", "api", tmp)
        assert result.returncode == 0
        base = Path(tmp) / "payments-service"
        for f in ["Dockerfile", "src/main.py", ".github/workflows/ci.yml",
                  "terraform/main.tf", "README.md", "tests/test_smoke.py"]:
            assert (base / f).exists(), f"Missing: {f}"

def test_each_type_gets_correct_terraform_resources():
    with tempfile.TemporaryDirectory() as tmp:
        scaffold("api-svc",   "api",       tmp)
        scaffold("wrk-svc",   "worker",    tmp)
        scaffold("sch-svc",   "scheduler", tmp)

        api_tf = (Path(tmp) / "api-svc"   / "terraform/main.tf").read_text()
        wrk_tf = (Path(tmp) / "wrk-svc"   / "terraform/main.tf").read_text()
        sch_tf = (Path(tmp) / "sch-svc"   / "terraform/main.tf").read_text()

        assert "aws_s3_bucket"  in api_tf and "aws_sqs_queue" not in api_tf
        assert "aws_sqs_queue"  in wrk_tf and "aws_s3_bucket" not in wrk_tf
        assert "aws_s3_bucket"  in sch_tf and "cron_schedule" in (Path(tmp) / "sch-svc/terraform/variables.tf").read_text()

def test_invalid_name_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold("Invalid Name!", "api", tmp)
        assert result.returncode != 0

def test_service_name_substituted_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        scaffold("my-service", "api", tmp)
        ci = (Path(tmp) / "my-service/.github/workflows/ci.yml").read_text()
        assert "my-service" in ci
