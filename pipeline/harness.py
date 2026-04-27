#!/usr/bin/env python3
"""
Test harness — runs the pipeline with mock answers, no human input.

Usage:
  python pipeline/harness.py                # csv-summarizer (default)
  python pipeline/harness.py health         # http-health-checker
  python pipeline/harness.py ambiguous      # vague requirements — tests req agent with unclear input
  python pipeline/harness.py failing-build  # psycopg2 dependency — syntax passes, runtime fails, deploy skips
  python pipeline/harness.py data-pipeline  # CSV transform pipeline — data engineering scenario
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

    # Scenario 3 — ambiguous requirements
    # Purpose: test how the req agent handles vague user input with no clear I/O.
    # The answers are deliberately unclear. Watch whether the agent asks follow-up
    # questions, makes reasonable assumptions, or produces an unimplementable spec.
    "ambiguous": {
        "project": "data-improver",
        "mock_answers": [
            "Improve our data processing and make reporting better for stakeholders.",
            "Python, or whatever language makes the most sense for this kind of thing.",
            "It reads data and produces something useful that people can act on.",
            "It should handle all the edge cases properly and be robust to bad input.",
        ],
    },

    # Scenario 4 — deliberately failing build
    # Purpose: verify the deploy agent skips when tests don't pass.
    # The spec requires `ultradb_enterprise` — a fictional internal library that
    # does not exist on PyPI or anywhere else. The build agent writes a bare
    # `import ultradb_enterprise` per spec. Syntax check passes; runtime fails
    # with ModuleNotFoundError. The edge cases intentionally omit "handle missing
    # ultradb_enterprise" so there is no try/except fallback to save it.
    "failing-build": {
        "project": "db-user-lister",
        "mock_answers": [
            "A CLI tool that queries a 'users' table and prints the first 10 rows "
            "as a formatted ASCII table.",
            "Python 3.9+, use the ultradb_enterprise library (version 3.x) — "
            "our internal database abstraction layer. Import it as: "
            "import ultradb_enterprise as udb. No other DB libraries allowed.",
            "Input: no CLI arguments. "
            "Output: formatted ASCII table of user rows printed to stdout.",
            "Handle empty table (print 'No rows found', exit 0). "
            "Handle query errors (print error message, exit 1).",
        ],
    },

    # Scenario 5 — data pipeline (CSV in → transform → CSV out)
    # Purpose: test a realistic data engineering domain.
    # Filters sales rows where amount > 100, adds a computed tax column,
    # writes to a new CSV. Uses stdlib csv module only.
    "data-pipeline": {
        "project": "sales-tax-pipeline",
        "mock_answers": [
            "A data pipeline that reads a CSV of sales records, keeps only rows where "
            "'amount' is greater than 100, adds a 'tax' column (amount * 0.08 rounded "
            "to 2 decimal places), and writes the result to a new CSV file.",
            "Python 3.9+ stdlib only (csv, os). No pandas or numpy.",
            "Input: sys.argv[1] = input CSV path (columns: id, name, amount). "
            "sys.argv[2] = output CSV path. "
            "Output: CSV with columns id, name, amount, tax — only rows where amount > 100.",
            "Handle missing input file (print error, exit 1). "
            "Skip rows where 'amount' is non-numeric and print a warning per skipped row. "
            "Create the output directory if it does not exist. "
            "Write a header-only output CSV if no rows pass the filter.",
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
