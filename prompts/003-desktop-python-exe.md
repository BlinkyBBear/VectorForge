# Prompt 003 — Offline Windows desktop .exe

**Date:** 2026-08-07  
**Goal:** Stop relying on web preview; ship offline desktop app + GitHub-ready repo.

## Requirements

1. Convert to offline desktop app packable as Windows `.exe`
2. Preferred: Python + CustomTkinter + rembg + vtracer + PyInstaller
3. BG removal + click refine + high-quality vectorization
4. Memory safety + non-recursive algorithms
5. GitHub structure: .gitignore, README, /prompts, requirements.txt, MIT LICENSE
6. Build scripts for `.exe`

## Implementation notes

- Package root: `vectorforge/` (Python)
- Entry: `python -m vectorforge` (GUI) / `python -m vectorforge.cli` (headless)
- Build: `scripts/build_windows.bat` → `dist/VectorForge.exe`
