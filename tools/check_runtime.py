#!/usr/bin/env python3
"""Check the local runtime before launching the Streamlit app."""

from __future__ import annotations

import importlib
import platform
import sys
from pathlib import Path


MIN_PYTHON = (3, 11)
REQUIRED_PACKAGES = [
    "streamlit",
    "pandas",
    "plotly",
    "requests",
    "yfinance",
    "google.genai",
    "openpyxl",
]


def _version_text() -> str:
    return ".".join(str(part) for part in sys.version_info[:3])


def _read_runtime_txt() -> str:
    runtime_path = Path(__file__).resolve().parents[1] / "runtime.txt"
    if not runtime_path.exists():
        return "missing"
    return runtime_path.read_text(encoding="utf-8").strip() or "empty"


def main() -> int:
    errors = []
    warnings = []
    python_version = sys.version_info[:3]
    runtime_txt = _read_runtime_txt()

    print(f"Python executable: {sys.executable}")
    print(f"Python version: {_version_text()} ({platform.platform()})")
    print(f"runtime.txt: {runtime_txt}")

    if python_version < MIN_PYTHON:
        errors.append(
            f"Python {_version_text()} is too old. Use Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ to avoid EOL/runtime warnings."
        )

    if runtime_txt != "python-3.11":
        warnings.append("runtime.txt is not python-3.11; verify Streamlit Cloud runtime compatibility before deploying.")

    if not errors:
        missing = []
        for package in REQUIRED_PACKAGES:
            try:
                importlib.import_module(package)
            except Exception as exc:
                missing.append(f"{package} ({exc.__class__.__name__}: {exc})")

        if missing:
            errors.append("Missing or broken packages: " + "; ".join(missing))

    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"- {item}")

    if errors:
        print("\nRuntime check failed:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("\nRuntime check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
