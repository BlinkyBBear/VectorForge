#!/usr/bin/env sh
# Launch VectorForge desktop UI (requires Tk on Linux/macOS).
set -eu
cd "$(dirname "$0")/.."
python3 -m vectorforge
