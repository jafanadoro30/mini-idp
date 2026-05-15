"""
Tests for Module 3 — Observability as Code
"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "modules/module3"

def test_prometheus_scrapes_demo_app():
    import yaml
    config = yaml.safe_load((BASE / "prometheus/prometheus.yml").read_text())
    jobs = [s["job_name"] for s in config["scrape_configs"]]
    assert "demo-app" in jobs

def test_all_alerts_have_noise_suppression():
    import yaml
    rules = yaml.safe_load((BASE / "prometheus/rules/sli_alerts.yml").read_text())
    for group in rules["groups"]:
        for rule in group["rules"]:
            if "alert" in rule:
                assert "for" in rule, f"Alert '{rule['alert']}' missing 'for' clause"

def test_grafana_dashboard_has_three_sli_panels():
    dashboard = json.loads((BASE / "grafana/provisioning/dashboards/sli-overview.json").read_text())
    titles = [p["title"].lower() for p in dashboard["panels"]]
    assert any("latency" in t or "p99" in t for t in titles)
    assert any("error" in t for t in titles)
    assert any("throughput" in t or "request" in t for t in titles)
