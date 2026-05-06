#!/usr/bin/env python3
"""Extract per-buffer latency arrays from patched Ramulator RD:/WR: stdout traces."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse
import numpy as np


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def parse_ramulator_trace(path: Path) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 4 or parts[0] not in {"RD:", "WR:"}:
                continue
            try:
                addr = int(parts[1], 16)
                arrive = int(parts[2])
                depart = int(parts[3])
            except ValueError:
                continue
            rows.append((addr, depart - arrive))
    return rows


def category(addr: int, filter_offset: int, ofmap_offset: int, meta_offset: int) -> str | None:
    if 0 <= addr < filter_offset:
        return "ifmap"
    if filter_offset <= addr < ofmap_offset:
        return "filter"
    if ofmap_offset <= addr < meta_offset:
        return "ofmap"
    return None


def append_group(latencies: dict[str, list[int]], group: list[tuple[str, int]]) -> None:
    if not group:
        return
    cat = group[0][0]
    latencies[cat].append(max(v for _, v in group))


def extract_one(path: Path, topology: str, results_dir: Path, *, bw: int, shaper: bool, filter_offset: int, ofmap_offset: int, meta_offset: int) -> str:
    layer_no = path.stem.split("_")[-1]
    rows = parse_ramulator_trace(path)
    latencies: dict[str, list[int]] = {"ifmap": [], "filter": [], "ofmap": []}
    last_cat = "ifmap"
    i = 0
    while i < len(rows):
        chunk = rows[i:i + bw]
        cats = [(category(addr, filter_offset, ofmap_offset, meta_offset), lat) for addr, lat in chunk]
        valid = [(cat, lat) for cat, lat in cats if cat is not None]
        if not valid:
            i += max(1, len(chunk))
            continue
        unique = {cat for cat, _ in valid}
        if len(unique) == 1 or shaper:
            cat = valid[0][0] if len(unique) == 1 else last_cat
            latencies[cat].append(max(lat for _, lat in valid))
            last_cat = cat
            i += max(1, len(chunk))
        else:
            # Split mixed chunks into contiguous same-category runs to avoid dropping padding/mixed groups.
            group: list[tuple[str, int]] = []
            for cat, lat in valid:
                if not group or group[-1][0] == cat:
                    group.append((cat, lat))
                else:
                    append_group(latencies, group)
                    last_cat = group[-1][0]
                    group = [(cat, lat)]
            append_group(latencies, group)
            if group:
                last_cat = group[-1][0]
            i += max(1, len(chunk))

    np.save(results_dir / f"{topology}_ifmapFile{layer_no}.npy", np.asarray(latencies["ifmap"], dtype=np.int64))
    np.save(results_dir / f"{topology}_filterFile{layer_no}.npy", np.asarray(latencies["filter"], dtype=np.int64))
    np.save(results_dir / f"{topology}_ofmapFile{layer_no}.npy", np.asarray(latencies["ofmap"], dtype=np.int64))
    return f"{path.name}: ifmap={len(latencies['ifmap'])}, filter={len(latencies['filter'])}, ofmap={len(latencies['ofmap'])}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-topology", default="", help="Trace filename prefix")
    parser.add_argument("-results-dir", default="results")
    parser.add_argument("-parallel", type=parse_bool, default=False)
    parser.add_argument("-jobs", type=int, default=1)
    parser.add_argument("-shaper", type=parse_bool, default=False)
    parser.add_argument("-bw", type=int, default=10)
    parser.add_argument("-filter-offset", type=int, default=10000000)
    parser.add_argument("-ofmap-offset", type=int, default=20000000)
    parser.add_argument("-meta-offset", type=int, default=30000000)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    topology = args.topology or "default"
    traces = sorted(p for p in results_dir.iterdir() if p.name.startswith(f"{topology}_RamulatorTrace") and p.suffix == ".trace")
    if not traces:
        raise FileNotFoundError(f"No RamulatorTrace files found for prefix {topology!r} in {results_dir}")

    jobs = args.jobs if args.parallel else 1
    jobs = max(1, jobs)
    kwargs = dict(bw=args.bw, shaper=args.shaper, filter_offset=args.filter_offset, ofmap_offset=args.ofmap_offset, meta_offset=args.meta_offset)
    if jobs == 1:
        for trace in traces:
            print(extract_one(trace, topology, results_dir, **kwargs))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(extract_one, trace, topology, results_dir, **kwargs) for trace in traces]
            for fut in as_completed(futs):
                print(fut.result())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
