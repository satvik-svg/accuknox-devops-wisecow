#!/usr/bin/env python3
"""Application health checker.

Sends an HTTP request to one or more URLs and reports each one as UP or DOWN
based on the status code. A site counts as UP when it answers with a status
code below 400 (or one of the codes passed with --ok-codes).
"""

import argparse
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


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Check if web applications are up using their HTTP status code."
    )
    p.add_argument("urls", nargs="+", help="one or more URLs to check")
    p.add_argument(
        "--timeout", type=float, default=5.0, help="seconds to wait for a reply (default 5)"
    )
    p.add_argument(
        "--ok-codes",
        default="",
        help="comma separated status codes that count as UP, for example 200,204 "
        "(default: anything below 400)",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS certificate checks, useful for self signed certs",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=0,
        help="seconds between rounds; 0 means check once and exit (default 0)",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    ok_codes = {int(c) for c in args.ok_codes.split(",") if c.strip()}
    if args.insecure:
        # the user asked for this on purpose, so do not print a warning every round
        requests.packages.urllib3.disable_warnings()
    try:
        while True:
            results = [check_url(u, args.timeout, ok_codes, not args.insecure) for u in args.urls]
            for r in results:
                print(format_result(r), flush=True)
            down = sum(1 for r in results if r["status"] == "DOWN")
            if args.interval <= 0:
                return 1 if down else 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
