#!/usr/bin/env python3
"""Build a clean zip package for moving the app to another computer."""

from __future__ import annotations

import argparse
import fnmatch
import os
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
IGNORE_FILE = ROOT / ".packageignore"
DEFAULT_PACKAGE_DIR = ROOT / "dist"


def _as_posix(path: Path) -> str:
    text = path.as_posix()
    return text[2:] if text.startswith("./") else text


def _read_patterns() -> list[str]:
    if not IGNORE_FILE.exists():
        return []
    patterns: list[str] = []
    for raw_line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _matches_pattern(rel_path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if not pattern:
        return False
    if pattern.startswith("/"):
        return fnmatch.fnmatch(rel_path, pattern.lstrip("/"))
    if pattern.endswith("/"):
        prefix = pattern.rstrip("/")
        return rel_path == prefix or rel_path.startswith(prefix + "/") or f"/{prefix}/" in f"/{rel_path}/"
    return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(Path(rel_path).name, pattern)


def _is_ignored(path: Path, patterns: list[str]) -> bool:
    rel_path = _as_posix(path.relative_to(ROOT))
    parts = path.relative_to(ROOT).parts
    if any(part == "__pycache__" or part.startswith("._") for part in parts):
        return True
    return any(_matches_pattern(rel_path, pattern) for pattern in patterns)


def iter_package_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        current = Path(dirpath)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not _is_ignored(current / dirname, patterns)
        ]
        for filename in filenames:
            path = current / filename
            if not _is_ignored(path, patterns):
                files.append(path)
    return sorted(files, key=lambda item: _as_posix(item.relative_to(ROOT)))


def build_package(output_path: Path) -> tuple[int, int]:
    patterns = _read_patterns()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    files = [
        path
        for path in iter_package_files(patterns)
        if path.resolve() != output_path.resolve()
    ]
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            rel_path = _as_posix(path.relative_to(ROOT))
            archive.write(path, arcname=f"way_stock/{rel_path}")
    return len(files), output_path.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a clean WAY stock app zip.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_PACKAGE_DIR / f"way_stock_clean_{datetime.now():%Y%m%d_%H%M%S}.zip",
        help="Output zip path. Default: dist/way_stock_clean_YYYYMMDD_HHMMSS.zip",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only list package contents summary; do not write zip.")
    args = parser.parse_args()

    patterns = _read_patterns()
    files = iter_package_files(patterns)
    if args.dry_run:
        total_size = sum(path.stat().st_size for path in files if path.is_file())
        print(f"Package file count: {len(files)}")
        print(f"Package source size: {total_size / 1024 / 1024:.2f} MB")
        for path in files[:80]:
            print(_as_posix(path.relative_to(ROOT)))
        if len(files) > 80:
            print(f"... {len(files) - 80} more files")
        return 0

    file_count, package_size = build_package(args.output)
    print(f"Package created: {args.output}")
    print(f"Packaged files: {file_count}")
    print(f"Zip size: {package_size / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
