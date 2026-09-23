#!/usr/bin/env python3
"""
JMeter Test Runner for Flask API Performance Testing
Runs JMeter test plans and posts results to the experiment API.
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
JMETER_DIR = PROJECT_ROOT / "jmeter"

SCENARIO_MAP = {
    "normal": "normal_behavior.jmx",
    "massive": "massive_extraction.jmx",
    "gradual": "gradual_stair.jmx",
}

API_BASE = "http://localhost:5002"


def run_jmeter(jmeter_path: str, jmx_file: Path, output_jtl: Path) -> None:
    cmd = [
        jmeter_path,
        "-n",
        "-t", str(jmx_file),
        "-l", str(output_jtl),
    ]
    print(f"[RUN] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] JMeter failed with code {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        sys.exit(1)
    print("[OK] JMeter test completed successfully.")


def parse_jtl(jtl_path: Path) -> dict:
    if not jtl_path.exists():
        print(f"[ERROR] JTL file not found: {jtl_path}")
        sys.exit(1)

    samples = []
    with open(jtl_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                samples.append({
                    "timestamp": int(row.get("elapsed", 0)),
                    "label": row.get("label", ""),
                    "response_time": float(row.get("elapsed", 0)),
                    "latency": float(row.get("Latency", 0)),
                    "success": row.get("success", "true").lower() == "true",
                    "response_code": int(row.get("responseCode", 0)),
                    "response_message": row.get("responseMessage", ""),
                    "thread_name": row.get("threadName", ""),
                    "bytes": int(row.get("bytes", 0)),
                    "sent_bytes": int(row.get("sentBytes", 0)),
                })
            except (ValueError, KeyError):
                continue

    if not samples:
        print("[WARN] No samples parsed from JTL file.")
        return {}

    total = len(samples)
    successful = sum(1 for s in samples if s["success"])
    failed = total - successful
    response_times = [s["response_time"] for s in samples]
    latencies = [s["latency"] for s in samples]

    avg_rt = sum(response_times) / total
    min_rt = min(response_times)
    max_rt = max(response_times)
    p90 = sorted(response_times)[int(total * 0.9)]
    p95 = sorted(response_times)[int(total * 0.95)]
    p99 = sorted(response_times)[int(total * 0.99)]
    avg_latency = sum(latencies) / total
    throughput = total / (max(response_times) / 1000) if max(response_times) > 0 else 0

    summary = {
        "total_samples": total,
        "successful": successful,
        "failed": failed,
        "error_rate": round((failed / total) * 100, 2),
        "avg_response_time": round(avg_rt, 2),
        "min_response_time": round(min_rt, 2),
        "max_response_time": round(max_rt, 2),
        "p90_response_time": round(p90, 2),
        "p95_response_time": round(p95, 2),
        "p99_response_time": round(p99, 2),
        "avg_latency": round(avg_latency, 2),
        "throughput_rps": round(throughput, 2),
    }
    return summary


def post_results(scenario: str, summary: dict, jmx_name: str) -> dict:
    payload = {
        "scenario": scenario,
        "test_plan": jmx_name,
        "results": summary,
    }
    print(f"[POST] Sending results to {API_BASE}/api/experiment/run ...")
    try:
        resp = requests.post(
            f"{API_BASE}/api/experiment/run",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[OK] API responded with status {resp.status_code}")
        return resp.json()
    except requests.ConnectionError:
        print("[WARN] API not reachable. Results not posted.")
    except requests.RequestException as e:
        print(f"[WARN] Failed to post results: {e}")
    return {}


def print_summary(summary: dict, scenario: str) -> None:
    print("\n" + "=" * 50)
    print(f"  RESULTS SUMMARY - {scenario.upper()}")
    print("=" * 50)
    for key, value in summary.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<25} {value}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Run JMeter performance tests and report results."
    )
    parser.add_argument(
        "--scenario",
        required=True,
        choices=list(SCENARIO_MAP.keys()),
        help="Test scenario: normal, massive, or gradual",
    )
    parser.add_argument(
        "--jmeter-path",
        default="jmeter",
        help="Path to JMeter executable (default: jmeter)",
    )
    args = parser.parse_args()

    jmx_name = SCENARIO_MAP[args.scenario]
    jmx_file = JMETER_DIR / jmx_name
    timestamp = int(time.time())
    output_jtl = JMETER_DIR / f"{args.scenario}_{timestamp}.jtl"

    if not jmx_file.exists():
        print(f"[ERROR] JMX file not found: {jmx_file}")
        sys.exit(1)

    print(f"[INFO] Scenario: {args.scenario}")
    print(f"[INFO] Test plan: {jmx_file}")
    print(f"[INFO] Output JTL: {output_jtl}")

    run_jmeter(args.jmeter_path, jmx_file, output_jtl)
    summary = parse_jtl(output_jtl)

    if summary:
        print_summary(summary, args.scenario)
        post_results(args.scenario, summary, jmx_name)
    else:
        print("[WARN] No results to report.")

    print(f"\n[DONE] JTL file saved at: {output_jtl}")


if __name__ == "__main__":
    main()
