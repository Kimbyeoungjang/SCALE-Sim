#!/usr/bin/env python3
from __future__ import annotations

import configparser
import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    here = Path.cwd().resolve()
    if (here / "scalesim").exists():
        return here
    for parent in here.parents:
        if (parent / "scalesim").exists():
            return parent
    raise SystemExit("Could not find SCALE-Sim repo root")


def main() -> None:
    root = repo_root()
    ram = Path(os.environ.get("SCALE_SIM_RAMULATOR_DIR", root / "ramulator"))
    errors: list[str] = []
    warnings: list[str] = []

    if not ram.exists():
        errors.append(f"Ramulator directory not found: {ram}")
    else:
        for rel in ["Makefile", "src", "configs/DDR4-config.cfg"]:
            if not (ram / rel).exists():
                errors.append(f"Missing Ramulator file/dir: {ram / rel}")
        if (ram / ".git").exists():
            errors.append(f"Nested .git metadata still exists: {ram / '.git'}")
        if (ram / "ramulator").exists():
            warnings.append("Ramulator binary exists. It is usually ignored by ramulator/.gitignore and should not be committed.")

    gm = root / ".gitmodules"
    if gm.exists():
        text = gm.read_text(encoding="utf-8", errors="replace")
        if "ramulator" in text.lower():
            errors.append(".gitmodules still contains a Ramulator entry")

    if (root / ".git").exists():
        proc = subprocess.run(["git", "ls-files", "-s", "ramulator"], cwd=str(root), text=True, capture_output=True)
        if proc.stdout.startswith("160000"):
            errors.append("ramulator is still tracked as a gitlink submodule. Run apply_vendor_ramulator.py again, then git add the files.")

    for w in warnings:
        print(f"[WARN] {w}")
    if errors:
        for e in errors:
            print(f"[ERROR] {e}")
        raise SystemExit(1)
    print("[OK] Ramulator is vendored as normal source files")
    print(f"Ramulator path: {ram}")


if __name__ == "__main__":
    main()
