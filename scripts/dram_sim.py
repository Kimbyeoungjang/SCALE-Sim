#!/usr/bin/env python3
"""Generate Ramulator DRAM traces from SCALE-Sim layer traces and run Ramulator.

This replaces the old cycle-by-cycle scanner. It streams only rows that contain
requests, so sparse traces no longer spend time iterating over empty cycles.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import argparse
import heapq
import subprocess
from pathlib import Path
import sys
from typing import Iterable, Iterator


@dataclass(order=True)
class TraceEvent:
    cycle: int
    order: int
    op: str
    addresses: list[int]


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def parse_trace_file(path: Path, op: str, *, fake_address: int, shaper: bool, negate_addresses: bool = False) -> Iterator[TraceEvent]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        for order, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",") if p.strip() != ""]
            if len(parts) < 2:
                continue
            try:
                cycle = int(float(parts[0]))
            except ValueError:
                # Header or malformed row.
                continue
            addrs: list[int] = []
            for raw in parts[1:]:
                try:
                    addr = int(float(raw))
                except ValueError:
                    continue
                if negate_addresses:
                    addr = -addr
                if addr < 0:
                    if shaper:
                        addrs.append(fake_address)
                    continue
                addrs.append(addr)
            if addrs:
                yield TraceEvent(cycle=cycle, order=order, op=op, addresses=addrs)


def parse_ofmap_file(path: Path, *, fake_address: int, shaper: bool) -> Iterator[TraceEvent]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        for order, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",") if p.strip() != ""]
            if len(parts) < 2:
                continue
            try:
                cycle = int(float(parts[0]))
                first = float(parts[1])
            except ValueError:
                continue
            op = "W" if first > 0.0 else "R"
            addrs: list[int] = []
            for raw in parts[1:]:
                try:
                    addr = int(float(raw))
                except ValueError:
                    continue
                if op == "R":
                    addr = -addr
                if addr < 0:
                    if shaper:
                        addrs.append(fake_address)
                    continue
                addrs.append(addr)
            if addrs:
                yield TraceEvent(cycle=cycle, order=order, op=op, addresses=addrs)


def write_demand_trace(layer_path: Path, out_trace: Path, *, shaper: bool, fake_address: int) -> int:
    generators: list[Iterable[TraceEvent]] = [
        parse_trace_file(layer_path / "IFMAP_DRAM_TRACE.csv", "R", fake_address=fake_address, shaper=shaper),
        parse_trace_file(layer_path / "FILTER_DRAM_TRACE.csv", "R", fake_address=fake_address, shaper=shaper),
        parse_ofmap_file(layer_path / "OFMAP_DRAM_TRACE.csv", fake_address=fake_address, shaper=shaper),
    ]
    out_trace.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    # heapq.merge preserves sorted-by-cycle behavior without iterating empty cycles.
    with out_trace.open("w", encoding="utf-8") as f:
        for ev in heapq.merge(*generators):
            for addr in ev.addresses:
                f.write(f"0x{addr:x} {ev.op}\n")
                count += 1
    return count


def run_ramulator(ramulator_exe: Path, config: Path, demand_trace: Path, stats_path: Path, stdout_path: Path, *, mapping: Path | None = None) -> None:
    cmd = [str(ramulator_exe), str(config), "--mode=dram", "--stats", str(stats_path)]
    if mapping is not None:
        cmd.extend(["--mapping", str(mapping)])
    cmd.append(str(demand_trace))
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"Ramulator failed with code {proc.returncode}: {' '.join(cmd)}\n{proc.stdout}")


def process_layer(layer_path: Path, topology: str, results_dir: Path, ramulator_exe: Path, config: Path, mapping: Path | None, shaper: bool, fake_address: int) -> tuple[str, int]:
    layer_no = layer_path.name.replace("layer", "")
    demand_trace = results_dir / f"{topology}_DemandTrace_{layer_no}.trace"
    ramulator_stdout = results_dir / f"{topology}_RamulatorTrace_{layer_no}.trace"
    stats_path = results_dir / f"DDR4_{topology}{layer_no}.stats"
    nreq = write_demand_trace(layer_path, demand_trace, shaper=shaper, fake_address=fake_address)
    run_ramulator(ramulator_exe, config, demand_trace, stats_path, ramulator_stdout, mapping=mapping)
    return layer_path.name, nreq


def find_layer_paths(results_dir: Path, topology: str, run_name: str) -> list[Path]:
    # Backward-compatible search order.
    candidates = [results_dir / topology / run_name, results_dir / run_name]
    for base in candidates:
        if base.exists():
            layers = sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("layer"))
            if layers:
                return layers
    raise FileNotFoundError(f"No SCALE-Sim layer trace directories found under: {candidates}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-topology", default="", help="Topology/result prefix used by older scripts")
    parser.add_argument("-run_name", default="GoogleTPU_v1_ws", help="SCALE-Sim run_name directory")
    parser.add_argument("-results-dir", default="results")
    parser.add_argument("-ramulator", default="ramulator/ramulator")
    parser.add_argument("-ramulator-config", default="ramulator/configs/DDR4-config.cfg")
    parser.add_argument("-mapping", default="")
    parser.add_argument("-jobs", type=int, default=1)
    parser.add_argument("-shaper", type=parse_bool, default=False)
    parser.add_argument("-fake-address", type=int, default=40000000)
    args = parser.parse_args()

    root = Path.cwd()
    results_dir = (root / args.results_dir).resolve()
    topology = args.topology or "default"
    ramulator_exe = (root / args.ramulator).resolve()
    ramulator_config = (root / args.ramulator_config).resolve()
    mapping = (root / args.mapping).resolve() if args.mapping else None

    if not ramulator_exe.exists():
        raise FileNotFoundError(f"Ramulator executable not found: {ramulator_exe}. Build it with `make -C ramulator -j`.")
    if not ramulator_config.exists():
        raise FileNotFoundError(f"Ramulator config not found: {ramulator_config}")

    layers = find_layer_paths(results_dir, args.topology, args.run_name)
    print(f"Found {len(layers)} layer trace directories")

    jobs = max(1, args.jobs)
    if jobs == 1:
        for layer in layers:
            name, nreq = process_layer(layer, topology, results_dir, ramulator_exe, ramulator_config, mapping, args.shaper, args.fake_address)
            print(f"{name}: wrote and simulated {nreq} requests")
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(process_layer, layer, topology, results_dir, ramulator_exe, ramulator_config, mapping, args.shaper, args.fake_address) for layer in layers]
            for fut in as_completed(futs):
                name, nreq = fut.result()
                print(f"{name}: wrote and simulated {nreq} requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
