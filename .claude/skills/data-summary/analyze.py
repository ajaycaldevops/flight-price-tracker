#!/usr/bin/env python3
"""Data quality analyzer for CSV and JSON files. Uses stdlib only."""
import sys
import json
import csv
import os
import re
import math
from collections import Counter


def _infer_scalar_type(v):
    sv = str(v).strip()
    if sv.lower() in ("true", "false", "yes", "no"):
        return "boolean"
    try:
        int(sv)
        return "integer"
    except ValueError:
        pass
    try:
        float(sv)
        return "float"
    except ValueError:
        pass
    if re.match(r"^\d{4}-\d{2}-\d{2}|\d{2}[\/\-]\d{2}[\/\-]\d{4}", sv):
        return "date"
    return "string"


def _infer_column_type(values):
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_null:
        return "empty"
    counts = Counter(_infer_scalar_type(v) for v in non_null)
    dominant, dom_n = counts.most_common(1)[0]
    return dominant if dom_n / len(non_null) >= 0.8 else "mixed"


def _numeric_stats(values):
    nums = []
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        try:
            nums.append(float(str(v).strip()))
        except ValueError:
            pass
    if len(nums) < 2:
        return None
    n = len(nums)
    mu = sum(nums) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in nums) / n)
    outliers = sum(1 for x in nums if sd > 0 and abs(x - mu) > 3 * sd)
    return {
        "min": round(min(nums), 4),
        "max": round(max(nums), 4),
        "mean": round(mu, 4),
        "std": round(sd, 4),
        "outlier_count": outliers,
    }


def _load_csv(filepath):
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        headers = list(reader.fieldnames or [])
    return rows, headers


def _load_json(filepath):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        if not data:
            return [], []
        if isinstance(data[0], dict):
            return data, list(data[0].keys())
        return [{"value": v} for v in data], ["value"]

    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val, list(val[0].keys())
        return [data], list(data.keys())

    return [], []


def analyze(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        rows, headers = _load_csv(filepath)
        fmt = "CSV"
    elif ext == ".json":
        rows, headers = _load_json(filepath)
        fmt = "JSON"
    else:
        try:
            rows, headers = _load_csv(filepath)
            fmt = "CSV (auto-detected)"
        except Exception:
            rows, headers = _load_json(filepath)
            fmt = "JSON (auto-detected)"

    row_count = len(rows)
    file_size = os.path.getsize(filepath)

    columns = {}
    for h in headers:
        vals = [r.get(h) for r in rows]
        null_count = sum(1 for v in vals if v is None or str(v).strip() == "")
        dtype = _infer_column_type(vals)
        info = {
            "type": dtype,
            "null_count": null_count,
            "null_pct": round(null_count / row_count * 100, 1) if row_count else 0,
            "unique_count": len({str(v) for v in vals if v is not None}),
        }
        if dtype in ("integer", "float", "mixed"):
            stats = _numeric_stats(vals)
            if stats:
                info["stats"] = stats
        columns[h] = info

    # Duplicate rows
    row_keys = [tuple(str(r.get(h, "")) for h in headers) for r in rows]
    dup_count = row_count - len(set(row_keys))

    # Anomalies
    anomalies = []
    if dup_count > 0:
        anomalies.append(f"{dup_count} duplicate row{'s' if dup_count > 1 else ''}")
    for col, info in columns.items():
        if info["null_pct"] == 100:
            anomalies.append(f"'{col}': entirely null")
        elif info["null_pct"] > 20:
            anomalies.append(f"'{col}': {info['null_pct']}% null ({info['null_count']} rows)")
        if info["unique_count"] == 1 and row_count > 1:
            anomalies.append(f"'{col}': only one unique value — no variance")
        if info["type"] == "mixed":
            anomalies.append(f"'{col}': mixed data types")
        if info.get("stats", {}).get("outlier_count", 0) > 0:
            n = info["stats"]["outlier_count"]
            anomalies.append(f"'{col}': {n} numeric outlier{'s' if n > 1 else ''} (>3σ from mean)")

    return {
        "file": os.path.basename(filepath),
        "format": fmt,
        "file_size_kb": round(file_size / 1024, 1),
        "rows": row_count,
        "columns": len(headers),
        "duplicate_rows": dup_count,
        "column_details": columns,
        "anomalies": anomalies,
    }


def print_report(r):
    W = 64
    print(f"\n{'═' * W}")
    print(f"  DATA QUALITY REPORT  ·  {r['file']}")
    print(f"{'═' * W}")
    print(f"  Format      {r['format']}")
    print(f"  File size   {r['file_size_kb']} KB")
    print(f"  Rows        {r['rows']:,}")
    print(f"  Columns     {r['columns']}")
    print(f"  Duplicates  {r['duplicate_rows']:,}")

    print(f"\n{'─' * W}")
    print(f"  {'COLUMN':<26} {'TYPE':<10} {'NULLS':>12}  {'UNIQUE':>7}")
    print(f"  {'─' * 26} {'─' * 10} {'─' * 12}  {'─' * 7}")
    for col, info in r["column_details"].items():
        null_str = f"{info['null_count']} ({info['null_pct']}%)"
        print(f"  {col[:26]:<26} {info['type']:<10} {null_str:>12}  {info['unique_count']:>7,}")
        if info.get("stats"):
            s = info["stats"]
            print(f"  {'':26}   min={s['min']}  max={s['max']}  mean={s['mean']}  std={s['std']}")

    print(f"\n{'─' * W}")
    print(f"  ANOMALIES")
    print(f"{'─' * W}")
    if r["anomalies"]:
        for a in r["anomalies"]:
            print(f"  ⚠  {a}")
    else:
        print("  ✓  None detected")

    print(f"{'═' * W}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Error: no file path provided. Usage: analyze.py <file.csv|file.json>")
        sys.exit(1)

    path = sys.argv[1].strip().strip('"')
    if not os.path.exists(path):
        # Search common subdirectories for a matching filename
        filename = os.path.basename(path)
        search_dirs = ["instance", "data", "exports", ".", ".."]
        found = None
        for d in search_dirs:
            candidate = os.path.join(d, filename)
            if os.path.exists(candidate):
                found = candidate
                break
        if found is None:
            print(f"Error: file not found: {path}")
            sys.exit(1)
        path = found

    try:
        report = analyze(path)
        print_report(report)
    except Exception as e:
        print(f"Error analyzing file: {e}")
        sys.exit(1)
