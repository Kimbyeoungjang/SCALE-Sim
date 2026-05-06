#!/usr/bin/env python3
"""Create a clean zip without macOS resource forks, __MACOSX, or .DS_Store files."""

from __future__ import annotations
from pathlib import Path
import argparse
import zipfile

EXCLUDE_NAMES = {".DS_Store"}
EXCLUDE_PREFIXES = ("__MACOSX/",)
EXCLUDE_PATTERNS = ("._",)


def should_skip(path: Path, arcname: str) -> bool:
    if any(arcname.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
        return True
    if path.name in EXCLUDE_NAMES:
        return True
    if path.name.startswith(EXCLUDE_PATTERNS):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("zipfile")
    args = parser.parse_args()
    src = Path(args.source)
    dst = Path(args.zipfile)
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if src.is_file():
            zf.write(src, src.name)
        else:
            for p in src.rglob("*"):
                if not p.is_file():
                    continue
                arcname = str(p.relative_to(src.parent))
                if should_skip(p, arcname):
                    continue
                zf.write(p, arcname)
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
