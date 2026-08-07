# Changelog

## [0.5.0] — 2026-08-07

### Added
- Edge-aware **preprocessing pipeline** (CLAHE, bilateral, Canny boost, adaptive + Otsu threshold, morphology)
- New presets: **Laser Pro**, **Logo / Line Art**, **Illustration Colour**, **High Detail Photo**, **Photorealistic Max**, **B&W Compound**
- Full sidebar controls for preprocess + all major vtracer parameters
- Pure B&W vs Colour mode toggle
- Max process size up to **6000px**
- BG removal **strength** control
- **Live brush preview** while dragging
- SVG sanitize for xTool / Fusion / LightBurn / Inkscape

### Changed
- Version scheme aligned to product tags (`0.5.0`)
- Presets no longer overwrite `filter_speckle` via auto-tune by default
- README rewritten for quality tips and CAD import

## [2.0.0] — 2026-08-07

### Added
- Initial Python desktop app (CustomTkinter + rembg + vtracer + PyInstaller)

## [1.0.0] — 2026-08-07

### Added
- Legacy web prototype experiments
