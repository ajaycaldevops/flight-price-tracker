#!/usr/bin/env python3
"""
Test harness — runs the pipeline with mock answers, no human input.

Usage:
  python pipeline/harness.py          # csv-summarizer (default)
  python pipeline/harness.py health   # http-health-checker
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pipeline.orchestrator import run

MOCKS = {
    "csv": {
        "project": "csv-summarizer",
        "mock_answers": [
            "A CLI tool that reads a CSV file and prints summary stats: "
            "row count, column names, null count per column, min/max for numeric columns.",
            "Python 3.9+ stdlib only (csv, statistics).",
            "Input: path to CSV file as sys.argv[1]. Output: formatted summary to stdout.",
            "Handle missing file (print error, exit 1), empty CSV, non-numeric columns "
            "(skip min/max for those).",
        ],
    },
    "health": {
        "project": "http-health-check",
        "mock_answers": [
            "A script that checks if a list of URLs returns HTTP 200. "
            "Prints OK or FAIL per URL with response time in ms.",
            "Python 3.9+ stdlib only (urllib.request, time).",
            "Input: text file with one URL per line (sys.argv[1]). "
            "Output: URL + OK (Nms) or FAIL (status/error) per line.",
            "Handle timeouts (5s default), connection errors, malformed URLs. "
            "Exit code 1 if any URL fails.",
        ],
    },
}

if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "csv"
    if key not in MOCKS:
        print(f"Unknown mock '{key}'. Available: {list(MOCKS.keys())}")
        sys.exit(1)

    cfg = MOCKS[key]
    print(f"Mock: '{key}' - {cfg['project']}\n")
    # skip-permissions lets each claude subprocess write files without prompting
    ok = run(cfg, skip_permissions=True)
    sys.exit(0 if ok else 1)
