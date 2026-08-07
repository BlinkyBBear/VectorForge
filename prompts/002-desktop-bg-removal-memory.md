# Prompt 002 — Desktop, BG removal, memory safety

**Date:** 2026-08-07  
**Goal:** Offline subject isolation, OOM-safe processing, Windows .exe packaging, GitHub-ready repo.

## Critical requirements

1. Simple click background removal (auto + click erase/restore + brush), offline
2. Highest quality vectors (presets: Laser Optimized, High Detail Photo, Logo / Line Art)
3. Memory safety: downsample 1200–1600, workers, sequential layers, large-image warnings
4. Desktop .exe distribution (Electron preferred in this stack; Tauri alternative documented)
5. GitHub structure: .gitignore, README, /prompts, build scripts, MIT LICENSE, CHANGELOG

Full user prompt summarized above; implementation prioritizes stability then quality then packaging.
