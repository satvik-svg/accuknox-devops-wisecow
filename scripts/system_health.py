#!/usr/bin/env python3
"""System health monitor.

Checks CPU, memory, disk usage and the number of running processes.
Anything over its threshold is logged as an alert, both on the console
and in a log file. Runs once by default, or keeps checking with --interval.
"""

import argparse
import logging
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
        metrics["cpu"], metrics["memory"], metrics["disk"], metrics["processes"],
    )
    alerts = find_alerts(metrics, thresholds)
    for alert in alerts:
        log.warning("ALERT: %s", alert)
    if not alerts:
        log.info("All checks within limits")
    return alerts


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Monitor CPU, memory, disk and process count.")
    p.add_argument("--cpu", type=float, default=80.0, help="CPU usage limit in percent (default 80)")
    p.add_argument("--memory", type=float, default=80.0, help="memory usage limit in percent (default 80)")
    p.add_argument("--disk", type=float, default=80.0, help="disk usage limit in percent (default 80)")
    p.add_argument("--processes", type=int, default=500, help="max number of running processes (default 500)")
    p.add_argument("--disk-path", default="/", help="mount point to check for disk usage (default /)")
    p.add_argument("--interval", type=int, default=0,
                   help="seconds between checks; 0 means run once and exit (default 0)")
    p.add_argument("--log-file", default="system_health.log",
                   help="file to write logs to; pass an empty string to skip (default system_health.log)")
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
