#!/usr/bin/env python3
"""Run the app's 22 embedded regression tests using temporary files."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from DuplicateFinder import self_test
if __name__ == "__main__":
    raise SystemExit(self_test())
