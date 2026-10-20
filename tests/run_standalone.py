# -*- coding: utf-8 -*-
"""Ejecuta las pruebas sin pytest (solo las que no usan fixtures): python tests/run_standalone.py"""
import importlib
import inspect
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(names):
    failed = passed = 0
    for name in names:
        module = importlib.import_module(name)
        for fn_name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn_name.startswith("test_") and not inspect.signature(fn).parameters:
                try:
                    fn()
                    passed += 1
                    print(f"  ok   {name}.{fn_name}")
                except Exception:
                    failed += 1
                    print(f"  FAIL {name}.{fn_name}")
                    traceback.print_exc()
    print(f"\n{passed} aprobadas, {failed} fallidas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["test_eco_core"]))
