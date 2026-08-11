#!/usr/bin/env python3
"""Entry point de desenvolvimento para o CLI empacotado do Bianchini Method."""

from pathlib import Path
import runpy


runpy.run_path(
    Path(__file__).resolve().parents[1] / "skills" / "_shared" / "scripts" / "bm.py",
    run_name="__main__",
)
