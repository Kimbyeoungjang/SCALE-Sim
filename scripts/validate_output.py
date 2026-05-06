#!/usr/bin/env python3
"""Validate SCALE-Sim output directories.

Robust against SCALE-Sim's historical CSV formatting quirks:
- spaces after commas in headers/values
- optional trailing comma / empty column
- TIME_REPORT using either "Time (us)" or "Cycles"
- negative DRAM start cycles caused by prefetch before compute cycle 0
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REQUIRED_REPORTS = [
    "COMPUTE_REPORT.csv",
    "BANDWIDTH_REPORT.csv",
    "DETAILED_ACCESS_REPORT.csv",
    "TIME_REPORT.csv",
]

TRACE_PATTERNS = [
    "*TRACE*.csv",
    "*_TRACE.csv",
    "*_TRACE*.csv",
]


def _clean_cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def _read_csv_dicts(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read CSV with stripped headers/cells and remove empty trailing columns."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, skipinitialspace=True)
        rows = [[_clean_cell(c) for c in row] for row in reader]

    # Remove fully empty rows.
    rows = [row for row in rows if any(cell != "" for cell in row)]
    if not rows:
        return [], []

    # Remove trailing empty cells caused by historical SCALE-Sim trailing commas.
    cleaned_rows: List[List[str]] = []
    for row in rows:
        while row and row[-1] == "":
            row.pop()
        cleaned_rows.append(row)

    headers = cleaned_rows[0]
    # Drop empty headers anywhere, keeping aligned data columns.
    keep_indices = [i for i, h in enumerate(headers) if h]
    headers = [headers[i] for i in keep_indices]

    dicts: List[Dict[str, str]] = []
    for row in cleaned_rows[1:]:
        values = [row[i] if i < len(row) else "" for i in keep_indices]
        dicts.append(dict(zip(headers, values)))
    return headers, dicts


def _as_float(row: Dict[str, str], key: str) -> float:
    if key not in row:
        raise KeyError(f"missing column {key!r}; available={list(row.keys())}")
    value = _clean_cell(row[key])
    if value == "":
        raise ValueError(f"empty value for {key!r}")
    return float(value)


def _find_traces(report_dir: Path) -> List[Path]:
    traces = []
    for pattern in TRACE_PATTERNS:
        traces.extend(report_dir.rglob(pattern))
    # Ignore macOS resource fork files from zip archives.
    traces = [p for p in traces if "__MACOSX" not in p.parts and not p.name.startswith("._")]
    return sorted(set(traces))


def validate(report_dir: Path, expect_no_traces: bool = False, expect_traces: bool = False) -> int:
    errors: List[str] = []
    warnings: List[str] = []

    if not report_dir.exists():
        errors.append(f"Output directory does not exist: {report_dir}")
        return _print_result(errors, warnings)

    for name in REQUIRED_REPORTS:
        if not (report_dir / name).is_file():
            errors.append(f"Missing required report: {name}")

    compute_path = report_dir / "COMPUTE_REPORT.csv"
    if compute_path.is_file():
        headers, rows = _read_csv_dicts(compute_path)
        if any(h == "" or h.startswith("Unnamed") for h in headers):
            errors.append("COMPUTE_REPORT.csv contains an empty/Unnamed column")
        if not rows:
            errors.append("COMPUTE_REPORT.csv has no data rows")
        for idx, row in enumerate(rows):
            try:
                total_with_prefetch = _as_float(row, "Total Cycles (incl. prefetch)")
                total_cycles = _as_float(row, "Total Cycles")
                stall_cycles = _as_float(row, "Stall Cycles")
                overall_util = _as_float(row, "Overall Util %")
                mapping_eff = _as_float(row, "Mapping Efficiency %")
                compute_util = _as_float(row, "Compute Util %")
            except Exception as exc:
                errors.append(f"COMPUTE_REPORT row {idx}: failed to parse numeric fields: {exc}")
                continue
            if total_cycles <= 0:
                errors.append(f"COMPUTE_REPORT row {idx}: Total Cycles must be > 0")
            if total_with_prefetch < total_cycles:
                errors.append(f"COMPUTE_REPORT row {idx}: Total Cycles incl. prefetch < Total Cycles")
            if stall_cycles < 0:
                errors.append(f"COMPUTE_REPORT row {idx}: Stall Cycles must be >= 0")
            for label, value in [
                ("Overall Util %", overall_util),
                ("Mapping Efficiency %", mapping_eff),
                ("Compute Util %", compute_util),
            ]:
                if not (0 <= value <= 100):
                    errors.append(f"COMPUTE_REPORT row {idx}: {label} out of range: {value}")

    detailed_path = report_dir / "DETAILED_ACCESS_REPORT.csv"
    if detailed_path.is_file():
        _, rows = _read_csv_dicts(detailed_path)
        for idx, row in enumerate(rows):
            for key in ["DRAM IFMAP Start Cycle", "DRAM Filter Start Cycle", "DRAM OFMAP Start Cycle"]:
                if key in row and row[key] != "":
                    try:
                        value = float(row[key])
                    except ValueError:
                        errors.append(f"DETAILED_ACCESS_REPORT row {idx}: invalid {key}: {row[key]!r}")
                        continue
                    if value < 0:
                        warnings.append(
                            f"{key} is negative in row {idx}; interpreted as prefetch before compute cycle 0"
                        )
            for key, value in row.items():
                if any(token in key for token in ["Reads", "Writes", "Accesses"]):
                    if value == "":
                        continue
                    try:
                        numeric = float(value)
                    except ValueError:
                        errors.append(f"DETAILED_ACCESS_REPORT row {idx}: invalid numeric value {key}={value!r}")
                        continue
                    if numeric < 0:
                        errors.append(f"DETAILED_ACCESS_REPORT row {idx}: {key} must be >= 0")

    time_path = report_dir / "TIME_REPORT.csv"
    if time_path.is_file():
        headers, rows = _read_csv_dicts(time_path)
        accepted = {"Cycles", "Runtime Cycles", "Time (us)", "Estimated Time (us)"}
        if not any(h in accepted for h in headers):
            warnings.append(f"TIME_REPORT.csv has no recognized runtime/time column: {headers}")
        if not rows:
            errors.append("TIME_REPORT.csv has no data rows")

    summary_path = report_dir / "SUMMARY_REPORT.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            layer_count = int(summary.get("total", {}).get("layer_count", 0))
            if layer_count <= 0:
                warnings.append("SUMMARY_REPORT.json has layer_count <= 0")
        except Exception as exc:
            errors.append(f"Failed to parse SUMMARY_REPORT.json: {exc}")
    else:
        warnings.append("SUMMARY_REPORT.json not found")

    metadata_path = report_dir / "run_metadata.json"
    if not metadata_path.exists():
        warnings.append("run_metadata.json not found")

    traces = _find_traces(report_dir)
    if expect_no_traces and traces:
        errors.append(f"Expected no trace files, but found {len(traces)} trace files")
    if expect_traces and not traces:
        errors.append("Expected trace files, but found none")

    return _print_result(errors, warnings)


def _print_result(errors: Iterable[str], warnings: Iterable[str]) -> int:
    errors = list(errors)
    warnings = list(warnings)
    for warning in warnings:
        print(f"[WARN]  {warning}")
    for error in errors:
        print(f"[ERROR] {error}")
    if errors:
        return 1
    print("[OK] SCALE-Sim output looks valid")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SCALE-Sim report outputs")
    parser.add_argument("report_dir", type=Path, help="Directory containing SCALE-Sim report CSV files")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--expect-no-traces", action="store_true", help="Fail if trace files are present")
    group.add_argument("--expect-traces", action="store_true", help="Fail if trace files are absent")
    args = parser.parse_args()
    return validate(args.report_dir, args.expect_no_traces, args.expect_traces)


if __name__ == "__main__":
    sys.exit(main())
