#!/usr/bin/env python3
"""VectorForge desktop entrypoint (for PyInstaller and `python main.py`)."""

from vectorforge.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
