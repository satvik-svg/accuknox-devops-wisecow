import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import system_health  # noqa: E402

LIMITS = {"cpu": 80, "memory": 80, "disk": 80, "processes": 300}


def test_no_alerts_when_everything_is_low():
    metrics = {"cpu": 10, "memory": 20, "disk": 30, "processes": 100}
    assert system_health.find_alerts(metrics, LIMITS) == []


def test_alert_for_each_metric_over_limit():
    metrics = {"cpu": 95, "memory": 85, "disk": 50, "processes": 400}
    alerts = system_health.find_alerts(metrics, LIMITS)
    assert len(alerts) == 3
    assert any("CPU usage" in a for a in alerts)
    assert any("Memory usage" in a for a in alerts)
    assert any("Running processes is 400" in a for a in alerts)


def test_value_equal_to_limit_is_not_an_alert():
    metrics = {"cpu": 80, "memory": 80, "disk": 80, "processes": 300}
    assert system_health.find_alerts(metrics, LIMITS) == []


def test_collect_metrics_returns_real_numbers():
    m = system_health.collect_metrics("/")
    assert set(m) == {"cpu", "memory", "disk", "processes"}
    assert 0 <= m["memory"] <= 100
    assert m["processes"] > 0


def test_main_writes_alert_to_log_file(tmp_path, monkeypatch):
    log_file = tmp_path / "health.log"
    monkeypatch.setattr(
        system_health,
        "collect_metrics",
        lambda path: {"cpu": 99.0, "memory": 10.0, "disk": 10.0, "processes": 5},
    )
    code = system_health.main(["--log-file", str(log_file)])
    logging.shutdown()
    assert code == 1
    text = log_file.read_text()
    assert "ALERT: CPU usage is 99.0%" in text


def test_main_returns_zero_when_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        system_health,
        "collect_metrics",
        lambda path: {"cpu": 1.0, "memory": 1.0, "disk": 1.0, "processes": 1},
    )
    assert system_health.main(["--log-file", str(tmp_path / "h.log")]) == 0


def test_env_vars_set_the_defaults():
    environ = {
        "HEALTH_CPU_LIMIT": "70",
        "HEALTH_PROCESS_LIMIT": "42",
        "HEALTH_DISK_PATH": "/data",
        "HEALTH_INTERVAL": "15",
        "HEALTH_LOG_FILE": "",
    }
    args = system_health.parse_args([], environ)
    assert args.cpu == 70.0 and args.memory == 80.0
    assert args.processes == 42
    assert args.disk_path == "/data"
    assert args.interval == 15
    assert args.log_file == ""


def test_flags_win_over_env_vars():
    args = system_health.parse_args(["--cpu", "90"], {"HEALTH_CPU_LIMIT": "70"})
    assert args.cpu == 90.0


def test_bad_env_value_gives_a_clear_error():
    import pytest

    with pytest.raises(SystemExit, match="HEALTH_DISK_LIMIT"):
        system_health.parse_args([], {"HEALTH_DISK_LIMIT": "lots"})
