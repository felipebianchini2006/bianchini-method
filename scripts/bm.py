#!/usr/bin/env python3
"""Launcher público e fail-closed do backend Go oficial."""

from __future__ import annotations

import os
from pathlib import Path
import sys


EXIT_INSTALLATION_INVALID = 4
ROOT = Path(__file__).resolve().parents[1]


def _binary_path() -> Path:
    override = os.environ.get("BM_GO_BINARY")
    if override:
        return Path(override).expanduser().resolve()
    name = "bm.exe" if os.name == "nt" else "bm"
    return ROOT / "bin" / name


def main() -> int:
    binary = _binary_path()
    executable = binary.is_file() and (os.name == "nt" or os.access(binary, os.X_OK))
    if not executable:
        print(
            f"BM_INSTALLATION_INVALID: backend Go ausente ou não executável: {binary}",
            file=sys.stderr,
        )
        return EXIT_INSTALLATION_INVALID
    try:
        os.execv(str(binary), [str(binary), *sys.argv[1:]])
    except OSError as error:
        print(
            f"BM_INSTALLATION_INVALID: não foi possível executar o backend Go "
            f"{binary}: {error}",
            file=sys.stderr,
        )
        return EXIT_INSTALLATION_INVALID
    return EXIT_INSTALLATION_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
