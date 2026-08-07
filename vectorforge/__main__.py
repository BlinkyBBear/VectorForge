"""python -m vectorforge  → launch desktop UI (falls back to help if no Tk)."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"cli", "convert"}:
        from vectorforge.cli import main as cli_main

        return cli_main(sys.argv[2:])

    try:
        from vectorforge.ui.app import run_app

        run_app()
        return 0
    except Exception as e:  # noqa: BLE001
        print(
            "Desktop UI failed to start (missing Tk/display?).\n"
            f"  {e}\n\n"
            "Use the CLI instead:\n"
            "  python -m vectorforge.cli INPUT.png -o OUT.svg --preset logo --bg\n"
            "Or on Windows with standard Python (includes Tk):\n"
            "  python -m vectorforge\n",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
