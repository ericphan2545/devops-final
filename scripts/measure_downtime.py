#!/usr/bin/env python3
"""Observe /health during a deployment; Python standard library only."""
import argparse
import csv
from datetime import datetime, timezone
import http.client
import json
import math
from pathlib import Path
import re
import signal
import socket
import threading
import time
from urllib import error, parse, request
import uuid


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def probe(opener, url, timeout):
    req = request.Request(url, headers={
        "Cache-Control": "no-cache", "Pragma": "no-cache",
        "User-Agent": "DevOps-Final-Week4-Measurement/1.0",
    })
    status = 0
    try:
        with opener.open(req, timeout=timeout) as response:
            status = response.status
            body = response.read(65537)
        if status != 200:
            return False, status, "HTTP_" + str(status)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            return False, status, "INVALID_HEALTH_JSON"
        if not isinstance(data, dict) or data.get("status") != "ok":
            return False, status, "HEALTH_NOT_OK"
        return True, status, ""
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        return False, status, "HTTP_" + str(status)
    except (TimeoutError, socket.timeout):
        return False, status, "NETWORK_TIMEOUT"
    except error.URLError as exc:
        return False, status, "NETWORK_" + type(exc.reason).__name__
    except (OSError, http.client.HTTPException) as exc:
        return False, status, "NETWORK_" + type(exc).__name__


def observe(args, stop):
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = output_dir / (args.run + "-" + stamp + "-" + uuid.uuid4().hex[:6])
    csv_path = prefix.with_suffix(".csv")
    summary_path = prefix.with_suffix(".summary.json")
    text_path = prefix.with_suffix(".summary.txt")
    opener = request.build_opener(NoRedirect())
    started_utc, started_clock = utc_now(), time.monotonic()
    checks = healthy = failed = 0
    baseline_ok = False
    episodes = []
    active = None
    last_probe_end = 0.0
    print("Target:", args.url)
    print("CSV:", csv_path)
    print("Ctrl+C: stop and save. Wait for deployment AND stable recovery first.", flush=True)

    fields = ["check", "started_utc", "finished_utc", "start_elapsed_s",
              "end_elapsed_s", "request_s", "http_status", "healthy", "error"]
    with csv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        while not stop.is_set():
            if args.duration and time.monotonic() - started_clock >= args.duration:
                break
            begin, begin_utc = time.monotonic(), utc_now()
            ok, status, reason = probe(opener, args.url, args.timeout)
            end, end_utc = time.monotonic(), utc_now()
            checks += 1
            if checks == 1:
                baseline_ok = ok
                print("Initial healthy baseline:", "YES" if ok else "NO", flush=True)
            healthy += int(ok)
            failed += int(not ok)
            last_probe_end = end - started_clock
            row = dict(check=checks, started_utc=begin_utc, finished_utc=end_utc,
                       start_elapsed_s=round(begin - started_clock, 6),
                       end_elapsed_s=round(last_probe_end, 6),
                       request_s=round(end - begin, 6), http_status=status,
                       healthy=int(ok), error=reason)
            writer.writerow(row)
            handle.flush()
            if not ok:
                if active is None:
                    active = dict(first_failure_utc=begin_utc,
                                  first_failure_elapsed_s=begin - started_clock,
                                  healthy_before=healthy > 0, failed_checks=0)
                    print("\nFAIL", begin_utc, reason, flush=True)
                active["failed_checks"] += 1
                active["last_failure_utc"] = end_utc
            elif active is not None:
                active.update(recovered_utc=end_utc,
                              observed_window_s=round(last_probe_end -
                                                      active["first_failure_elapsed_s"], 6),
                              recovered=True)
                episodes.append(active)
                print("RECOVERED", end_utc, "window_s=",
                      active["observed_window_s"], flush=True)
                active = None
            if ok:
                print(".", end="", flush=True)
            if args.samples and checks >= args.samples:
                break
            delay = args.interval
            if args.duration:
                delay = min(delay, max(0, args.duration - (time.monotonic() - started_clock)))
            stop.wait(delay)

    if active is not None:
        active.update(recovered=False, recovered_utc=None, observed_window_s=None,
                      open_window_observed_s=round(last_probe_end -
                                                   active["first_failure_elapsed_s"], 6))
        episodes.append(active)
    valid = checks > 0 and baseline_ok and active is None
    total_closed = round(sum(e["observed_window_s"] for e in episodes if e["recovered"]), 6)
    summary = dict(
        run=args.run, url=args.url, started_utc=started_utc, finished_utc=utc_now(),
        monitor_elapsed_s=round(time.monotonic() - started_clock, 6),
        interval_after_response_s=args.interval, network_timeout_s=args.timeout,
        checks=checks, healthy_checks=healthy, failed_checks=failed,
        initial_baseline_ok=baseline_ok, status="COMPLETE" if valid else "INCOMPLETE",
        observed_downtime_s=total_closed if valid else None,
        closed_observation_windows_s=total_closed, episodes=episodes,
        interpretation=(
            "Estimated client-observed window: first failed request START to first "
            "subsequent healthy response END, summed across recovered episodes. "
            "Includes request latency/timeouts and sampling effects; not exact server "
            "downtime or an outage bound. No failures means no interruption observed, "
            "not proof of zero downtime. COMPLETE describes this monitor recording, "
            "not GitHub Actions/deployment success. Record pipeline status separately."
        ),
        csv_file=csv_path.name,
    )
    with summary_path.open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    lines = [
        "Run: " + args.run, "Target: " + args.url, "Status: " + summary["status"],
        "Started (UTC): " + started_utc, "Finished (UTC): " + summary["finished_utc"],
        "Checks / healthy / failed: %s / %s / %s" % (checks, healthy, failed),
        "Initial healthy baseline: " + str(baseline_ok),
        "Observed interruption window (seconds): " + str(summary["observed_downtime_s"]),
        "Recovered episodes: " + str(sum(e["recovered"] for e in episodes)),
        "Open episode at finish: " + str(active is not None),
        "CSV: " + csv_path.name, "JSON: " + summary_path.name, "",
        summary["interpretation"],
    ]
    with text_path.open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("\n\n" + "\n".join(lines))
    print("TXT:", text_path)
    return 0 if valid else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public /health URL (HTTP 200 and JSON status=ok)")
    parser.add_argument("--run", required=True, help="Run label, e.g. run-01")
    parser.add_argument("--interval", type=positive_float, default=0.5,
                        help="Seconds to wait AFTER each response (default 0.5)")
    parser.add_argument("--timeout", type=positive_float, default=2,
                        help="Network blocking-operation timeout, not a total run deadline")
    parser.add_argument("--duration", type=positive_float,
                        help="Optional monitoring duration in seconds")
    parser.add_argument("--samples", type=positive_int, help="Optional maximum probe count")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] /
                        "docs/evidence/week-4/measurements")
    args = parser.parse_args()
    url = parse.urlsplit(args.url)
    if url.scheme not in ("http", "https") or not url.hostname:
        parser.error("URL must be HTTP or HTTPS")
    if url.username or url.password or url.query or url.fragment:
        parser.error("Use a plain public /health URL without credentials, query or fragment")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", args.run):
        parser.error("--run must contain 1-50 letters, digits, hyphens or underscores")
    stop = threading.Event()
    def request_stop(signum, frame):
        stop.set()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    return observe(args, stop)


if __name__ == "__main__":
    raise SystemExit(main())
