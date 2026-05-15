"""
Tests for Module 2 — Ephemeral Environment Lifecycle
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "modules/module2/webhook_server"))
import main as wh

def test_port_is_in_valid_range():
    """Ports must always be in the 9000-9899 range."""
    for pr_id in ["1", "42", "99", "500", "3000", "300000"]:
        assert 9000 <= wh._port_for(pr_id) <= 9899

def test_port_collision_is_resolved():
    """PR IDs that hash to the same base port must get different ports."""
    # 3000 % 900 == 300000 % 900 == 300, both would land on 9300
    port_a = wh._port_for("3000")
    # Simulate port_a already in use by registering it in ACTIVE_ENVS
    wh.ACTIVE_ENVS["3000"] = {"port": port_a}
    port_b = wh._port_for("300000")
    del wh.ACTIVE_ENVS["3000"]
    assert port_a != port_b, f"Collision: both 3000 and 300000 got port {port_a}"

def test_generated_compose_is_valid_yaml():
    import yaml
    content = wh._generate_compose("42", "feature/test", "my-service", 9042)
    parsed = yaml.safe_load(content)
    assert "services" in parsed
    assert "traefik.enable=true" in content
    assert "name:" in content  # explicit network name required

def test_cost_increases_with_uptime():
    from datetime import datetime, timezone, timedelta
    old    = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert wh._calculate_cost(old) > wh._calculate_cost(recent)
