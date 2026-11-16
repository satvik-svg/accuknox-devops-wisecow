#!/usr/bin/env python3
"""Application health checker.

Sends an HTTP request to one or more URLs and reports each one as UP or DOWN
based on the status code. A site counts as UP when it answers with a status
code below 400 (or one of the codes passed with --ok-codes).

Every option can also come from an environment variable. A command line
flag or URL wins over the variable.

    APP_HEALTH_URLS       URLs to check, separated by commas or spaces
    APP_HEALTH_TIMEOUT    seconds to wait for a reply           (default 5)
    APP_HEALTH_OK_CODES   status codes that count as UP, e.g. 200,204
    APP_HEALTH_INSECURE   1/true/yes to skip TLS certificate checks
    APP_HEALTH_INTERVAL   seconds between rounds, 0 = once      (default 0)
    APP_HEALTH_LOG_FILE   also append results to this file      (default: none)
"""

import argparse
import os
import sys
import time
from datetime import datetime

import requests


def check_url(url, timeout=5.0, ok_codes=None, verify_tls=True):
    """Check one URL and return a dict with the result."""
    started = time.monotonic()
    try:
        resp = requests.get(url, timeout=timeout, verify=verify_tls, allow_redirects=True)
    except requests.RequestException as exc:
        return {
            "url": url,
            "status": "DOWN",
            "code": None,
            "reason": type(exc).__name__,
            "ms": None,
        }

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if ok_codes:
        healthy = resp.status_code in ok_codes
    else:
        healthy = resp.status_code < 400
    return {
        "url": url,
        "status": "UP" if healthy else "DOWN",
        "code": resp.status_code,
        "reason": resp.reason or "",
        "ms": elapsed_ms,
    }


def format_result(r):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if r["code"] is None:
        return f"{stamp} {r['status']:<4} {r['url']} (no response: {r['reason']})"
    reason = f" {r['reason']}" if r["reason"] else ""
    return f"{stamp} {r['status']:<4} {r['url']} (HTTP {r['code']}{reason}, {r['ms']} ms)"


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


def is_true(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_codes(text):
    try:
        return {int(c) for c in text.replace(" ", ",").split(",") if c.strip()}
    except ValueError:
        raise SystemExit(f"--ok-codes must be numbers separated by commas, got {text!r}") from None


def parse_args(argv=None, environ=None):
    def d(name, default, cast=str):
        return env(name, default, cast, environ)

    p = argparse.ArgumentParser(
        description="Check if web applications are up using their HTTP status code.",
        epilog="Each option can also be set with the APP_HEALTH_* environment variables "
        "listed at the top of this script.",
    )
    p.add_argument("urls", nargs="*", help="one or more URLs to check (env APP_HEALTH_URLS)")
    p.add_argument(
        "--timeout",
        type=float,
        default=d("APP_HEALTH_TIMEOUT", 5.0, float),
        help="seconds to wait for a reply (env APP_HEALTH_TIMEOUT, default 5)",
    )
    p.add_argument(
        "--ok-codes",
        default=d("APP_HEALTH_OK_CODES", ""),
        help="comma separated status codes that count as UP, for example 200,204 "
        "(env APP_HEALTH_OK_CODES, default: anything below 400)",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        default=is_true(d("APP_HEALTH_INSECURE", "")),
        help="skip TLS certificate checks, useful for self signed certs (env APP_HEALTH_INSECURE)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=d("APP_HEALTH_INTERVAL", 0, int),
        help="seconds between rounds; 0 means check once and exit "
        "(env APP_HEALTH_INTERVAL, default 0)",
    )
    p.add_argument(
        "--log-file",
        default=d("APP_HEALTH_LOG_FILE", ""),
        help="also append every result to this file (env APP_HEALTH_LOG_FILE, default: none)",
    )
    args = p.parse_args(argv)
    if not args.urls:
        args.urls = d("APP_HEALTH_URLS", "").replace(",", " ").split()
    if not args.urls:
        p.error("give at least one URL, or set APP_HEALTH_URLS")
    return args


def main(argv=None):
    args = parse_args(argv)
    ok_codes = parse_codes(args.ok_codes)
    if args.insecure:
        # the user asked for this on purpose, so do not print a warning every round
        requests.packages.urllib3.disable_warnings()
    try:
        while True:
            results = [check_url(u, args.timeout, ok_codes, not args.insecure) for u in args.urls]
            for r in results:
                line = format_result(r)
                print(line, flush=True)
                if args.log_file:
                    with open(args.log_file, "a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
            down = sum(1 for r in results if r["status"] == "DOWN")
            if args.interval <= 0:
                return 1 if down else 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
