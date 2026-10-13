#!/usr/bin/env python3
"""Compatibility entrypoint for the health check shipped with the plugin."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "plugins" / "kaoyan-408" / "scripts" / "health_check.py"


def _load_runtime():
    spec = importlib.util.spec_from_file_location("_kaoyan_408_health_check", RUNTIME)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runtime helper: {RUNTIME}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


_runtime = _load_runtime()

if __name__ == "__main__":
    raise SystemExit(_runtime.main())

sys.modules[__name__] = _runtime
