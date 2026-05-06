"""
Utilities for safer SCALE-Sim experiment outputs.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import csv
import json
import os
import platform
import shlex
import sys
from typing import Any

REPORT_FILES = [
    "COMPUTE_REPORT.csv",
    "BANDWIDTH_REPORT.csv",
    "DETAILED_ACCESS_REPORT.csv",
    "TIME_REPORT.csv",
]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def prepare_output_dir(
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    unique: bool = False,
    verbose: bool = True,
) -> str:
    requested = Path(path)

    if overwrite:
        requested.mkdir(parents=True, exist_ok=True)
        return str(requested)

    if unique or (requested.exists() and any(requested.iterdir())):
        parent = requested.parent
        stem = requested.name
        candidate = parent / f"{stem}_{_timestamp()}"
        counter = 1
        while candidate.exists():
            candidate = parent / f"{stem}_{_timestamp()}_{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=False)
        if verbose:
            print("[SCALE-Sim] Output directory already exists or unique output was requested.")
            print(f"[SCALE-Sim] Writing this run to: {candidate}")
        return str(candidate)

    requested.mkdir(parents=True, exist_ok=True)
    return str(requested)


def _clean_csv_file(path: Path) -> None:
    if not path.exists():
        return

    rows: list[list[str]] = []
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            while row and row[-1] == "":
                row.pop()
            rows.append(row)

    if path.name == "TIME_REPORT.csv" and rows:
        rows[0] = ["Cycles" if cell.strip() == "Time (us)" else cell for cell in rows[0]]

    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def cleanup_csv_reports(output_dir: str | os.PathLike[str]) -> None:
    out = Path(output_dir)
    for name in REPORT_FILES:
        _clean_csv_file(out / name)


def _read_all_rows(csv_path: Path) -> list[dict[str, Any]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        return [{k: _coerce_value(v) for k, v in row.items() if k is not None and k != ""} for row in reader]


def _coerce_value(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    s = value.strip()
    if s == "":
        return s
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def write_summary_report(output_dir: str | os.PathLike[str]) -> None:
    out = Path(output_dir)
    compute_rows = _read_all_rows(out / "COMPUTE_REPORT.csv")
    bandwidth_rows = _read_all_rows(out / "BANDWIDTH_REPORT.csv")
    access_rows = _read_all_rows(out / "DETAILED_ACCESS_REPORT.csv")

    layers: list[dict[str, Any]] = []
    n = max(len(compute_rows), len(bandwidth_rows), len(access_rows))
    for i in range(n):
        layer: dict[str, Any] = {}
        if i < len(compute_rows):
            layer.update({f"compute.{k}": v for k, v in compute_rows[i].items()})
        if i < len(bandwidth_rows):
            layer.update({f"bandwidth.{k}": v for k, v in bandwidth_rows[i].items()})
        if i < len(access_rows):
            layer.update({f"access.{k}": v for k, v in access_rows[i].items()})
        layers.append(layer)

    def sum_field(rows: list[dict[str, Any]], field: str) -> float:
        total = 0.0
        for row in rows:
            val = row.get(field)
            if isinstance(val, (int, float)):
                total += val
        return total

    total_cycles = sum_field(compute_rows, "Total Cycles")
    total_cycles_prefetch = sum_field(compute_rows, "Total Cycles (incl. prefetch)")
    stall_cycles = sum_field(compute_rows, "Stall Cycles")

    summary = {
        "layers": layers,
        "total": {
            "layer_count": len(compute_rows),
            "total_cycles": int(total_cycles) if float(total_cycles).is_integer() else total_cycles,
            "total_cycles_including_prefetch": int(total_cycles_prefetch) if float(total_cycles_prefetch).is_integer() else total_cycles_prefetch,
            "stall_cycles": int(stall_cycles) if float(stall_cycles).is_integer() else stall_cycles,
        },
        "notes": {
            "negative_dram_start_cycle": "Negative DRAM start cycles indicate prefetch scheduled before compute cycle 0.",
            "time_report_cycles": "TIME_REPORT.csv column was normalized from 'Time (us)' to 'Cycles' because SCALE-Sim reports cycle counts there in this version.",
        },
    }

    (out / "SUMMARY_REPORT.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_config_snapshot(scale_obj: Any) -> dict[str, Any]:
    cfg = getattr(scale_obj, "config", None)
    if cfg is None:
        cfg = getattr(scale_obj, "config_obj", None)
    if cfg is None:
        runner = getattr(scale_obj, "runner", None)
        cfg = getattr(runner, "conf", None)
    result: dict[str, Any] = {}
    if cfg is None:
        return result
    getters = {
        "array_dims": ["get_array_dims", "get_array_dims_as_list"],
        "dataflow": ["get_dataflow"],
        "topology": ["get_topology_path", "get_topofile"],
        "layout": ["get_layout_path", "get_layoutfile"],
        "ifmap_sram_kb": ["get_ifmap_sram_size"],
        "filter_sram_kb": ["get_filter_sram_size"],
        "ofmap_sram_kb": ["get_ofmap_sram_size"],
    }
    for key, names in getters.items():
        for name in names:
            fn = getattr(cfg, name, None)
            if callable(fn):
                try:
                    result[key] = fn()
                    break
                except Exception:
                    pass
    return result


def write_run_metadata(output_dir: str | os.PathLike[str], *, args: Any = None, requested_output: str | os.PathLike[str] | None = None, save_traces: bool | None = None, scale_obj: Any = None) -> None:
    out = Path(output_dir)
    arg_dict: dict[str, Any] = {}
    if args is not None:
        try:
            arg_dict = vars(args)
        except TypeError:
            arg_dict = {}
    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "platform": {"system": platform.system(), "release": platform.release(), "python": sys.version.split()[0]},
        "command": " ".join(shlex.quote(x) for x in sys.argv),
        "requested_output_dir": str(requested_output) if requested_output is not None else str(out),
        "actual_output_dir": str(out),
        "save_traces": save_traces,
        "args": arg_dict,
        "config_snapshot": _extract_config_snapshot(scale_obj),
        "reports": {name: (out / name).exists() for name in REPORT_FILES},
    }
    (out / "run_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def postprocess_reports(output_dir: str | os.PathLike[str], *, args: Any = None, requested_output: str | os.PathLike[str] | None = None, save_traces: bool | None = None, scale_obj: Any = None, verbose: bool = True) -> None:
    cleanup_csv_reports(output_dir)
    write_summary_report(output_dir)
    write_run_metadata(output_dir, args=args, requested_output=requested_output, save_traces=save_traces, scale_obj=scale_obj)
    if verbose:
        print(f"[SCALE-Sim] Post-processed reports in: {output_dir}")
