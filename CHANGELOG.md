# Changelog

## [2.0.0] — 2026-08-07

### Added
- **Python desktop app** (CustomTkinter) — primary product path
- **vtracer** high-quality vectorization engine
- **rembg (u2net)** offline AI background removal + iterative wand/brush refine
- Headless CLI: `python -m vectorforge.cli`
- PyInstaller one-file Windows build (`VectorForge.spec`, `scripts/build_windows.bat`)
- Memory-safe downsampling (hard max 2000px) and non-recursive flood-fill tools

### Changed
- Repository is **desktop-first**; web prototype under `src/` is legacy/optional
- README rewritten for install / run / `.exe` build on Windows

## [1.1.0] — 2026-08-07

### Added
- Web app background removal, workers, Electron shell experiments

## [1.0.0] — 2026-08-07

### Added
- Initial hybrid TypeScript vectorization web app
