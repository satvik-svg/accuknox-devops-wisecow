#!/usr/bin/env python3
"""System health monitor.

Checks CPU, memory, disk usage and the number of running processes.
Anything over its threshold is logged as an alert, both on the console
and in a log file. Runs once by default, or keeps checking with --interval.

Every option can also come from an environment variable, which is handy in
cron jobs and containers. A command line flag wins over the variable.

    HEALTH_CPU_LIMIT       CPU usage limit in percent        (default 80)
    HEALTH_MEMORY_LIMIT    memory usage limit in percent     (default 80)
    HEALTH_DISK_LIMIT      disk usage limit in percent       (default 80)
    HEALTH_PROCESS_LIMIT   max number of running processes   (default 500)
    HEALTH_DISK_PATH       mount point to check              (default /)
    HEALTH_INTERVAL        seconds between checks, 0 = once  (default 0)
    HEALTH_LOG_FILE        log file, empty to skip           (default system_health.log)
"""

import argparse
import logging
import os
import sys
import time

import psutil

log = logging.getLogger("system_health")


def setup_logging(log_file):
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        log.addHandler(file_handler)


def collect_metrics(disk_path="/"):
    """Read the current numbers from the machine."""
    return {
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage(disk_path).percent,
        "processes": len(psutil.pids()),
    }


def find_alerts(metrics, thresholds):
    """Return a list of human readable alerts for metrics above their limit."""
    labels = {
        "cpu": ("CPU usage", "%"),
        "memory": ("Memory usage", "%"),
        "disk": ("Disk usage", "%"),
        "processes": ("Running processes", ""),
    }
    alerts = []
    for key, limit in thresholds.items():
        value = metrics.get(key)
        if value is not None and value > limit:
            name, unit = labels[key]
            alerts.append(f"{name} is {value}{unit}, above the limit of {limit}{unit}")
    return alerts


def run_check(thresholds, disk_path):
    metrics = collect_metrics(disk_path)
    log.info(
        "CPU %.1f%% | Memory %.1f%% | Disk %.1f%% | Processes %d",
        metrics["cpu"],
        metrics["memory"],
        metrics["disk"],
        metrics["processes"],
    )
    alerts = find_alerts(metrics, thresholds)
    for alert in alerts:
        log.warning("ALERT: %s", alert)
    if not alerts:
        log.info("All checks within limits")
    return alerts


def env(name, default, cast=str, environ=None):
    """Read a setting from the environment, falling back to a default."""
    environ = os.environ if environ is None else environ
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        return cast(raw)
    except ValueError:
        raise SystemExit(f"{name}={raw!r} is not a valid {cast.__name__}") from None


def parse_args(argv=None, environ=None):
    def d(name, default, cast=str):
        return env(name, default, cast, environ)

    p = argparse.ArgumentParser(
        description="Monitor CPU, memory, disk and process count.",
        epilog="Each option can also be set with the HEALTH_* environment variables "
        "listed at the top of this script.",
    )
    p.add_argument(
        "--cpu",
        type=float,
        default=d("HEALTH_CPU_LIMIT", 80.0, float),
        help="CPU usage limit in percent (env HEALTH_CPU_LIMIT, default 80)",
    )
    p.add_argument(
        "--memory",
        type=float,
        default=d("HEALTH_MEMORY_LIMIT", 80.0, float),
        help="memory usage limit in percent (env HEALTH_MEMORY_LIMIT, default 80)",
    )
    p.add_argument(
        "--disk",
        type=float,
        default=d("HEALTH_DISK_LIMIT", 80.0, float),
        help="disk usage limit in percent (env HEALTH_DISK_LIMIT, default 80)",
    )
    p.add_argument(
        "--processes",
        type=int,
        default=d("HEALTH_PROCESS_LIMIT", 500, int),
        help="max number of running processes (env HEALTH_PROCESS_LIMIT, default 500)",
    )
    p.add_argument(
        "--disk-path",
        default=d("HEALTH_DISK_PATH", "/"),
        help="mount point to check for disk usage (env HEALTH_DISK_PATH, default /)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=d("HEALTH_INTERVAL", 0, int),
        help="seconds between checks; 0 means run once and exit (env HEALTH_INTERVAL, default 0)",
    )
    p.add_argument(
        "--log-file",
        default=d("HEALTH_LOG_FILE", "system_health.log"),
        help="file to write logs to; pass an empty string to skip "
        "(env HEALTH_LOG_FILE, default system_health.log)",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.log_file)
    thresholds = {
        "cpu": args.cpu,
        "memory": args.memory,
        "disk": args.disk,
        "processes": args.processes,
    }
    try:
        while True:
            alerts = run_check(thresholds, args.disk_path)
            if args.interval <= 0:
                # exit code 1 lets cron or CI notice that something is over the limit
                return 1 if alerts else 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("Stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
