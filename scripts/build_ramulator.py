#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    here = Path.cwd().resolve()
    if (here / "ramulator").exists() and (here / "scalesim").exists():
        return here
    for parent in here.parents:
        if (parent / "ramulator").exists() and (parent / "scalesim").exists():
            return parent
    raise SystemExit("Could not find SCALE-Sim root with ramulator")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the vendored Ramulator binary")
    parser.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    root = repo_root()
    ram = Path(os.environ.get("SCALE_SIM_RAMULATOR_DIR", root / "ramulator"))
    if not ram.exists():
        raise SystemExit(f"Ramulator directory not found: {ram}")
    if not (ram / "Makefile").exists():
        raise SystemExit(f"Ramulator Makefile not found: {ram / 'Makefile'}")

    if args.clean:
        subprocess.run(["make", "clean"], cwd=str(ram), check=False)

    cmd = ["make", f"-j{args.jobs}"]
    print("$", " ".join(cmd), f"(cwd={ram})")
    subprocess.run(cmd, cwd=str(ram), check=True)
    binary = ram / "ramulator"
    if not binary.exists():
        raise SystemExit(f"Build completed but binary was not found: {binary}")
    print(f"Ramulator binary ready: {binary}")


if __name__ == "__main__":
    main()
