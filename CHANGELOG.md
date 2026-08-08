# Changelog

## [1.0.2] — 2026-08-08

### Fixed
- **Silhouette mode** no longer drops text / secondary animals (tiered Soft/Normal/Aggressive)
- Normal keeps major elements (text blocks, icons); Aggressive ≈ previous over-filter

### Improved
- Closed-path enforcement + near-duplicate stroke cull for laser cut safety
- DXF `$INSUNITS=4` (mm) for Fusion 360 / CAM
- Stronger laser-ready status tips (open paths, node density)

[1.0.1] — 2026-08-08

### Added
- **Highpass radius** (0–12 px) and **Scale factor** (1–4×) in Advanced → Raster prep
- Binary mask preview reflects highpass/scale after Vectorize
- Post-vectorize **laser-ready / warning tip** on status + stats
- Simple mode: auto scale (~1700px) + default highpass 3.5

[1.0.0] — 2026-08-08

### Added
- **Potrace-first architecture** for CNC Outline / Logo / Laser B&W
- **CNC Outline** preset — stroke-only closed paths for sheet-metal cut-outs
- **Live SVG path preview** after vectorize (actual geometry, not raster guess)
- **DXF export** for Fusion 360 / CNC workflows
- Clean Otsu/fixed/adaptive threshold (no dual-min flood)
- Auto ink-fraction invert when subject is inverted
- Full numeric sidebar + scrollable controls
- Colour mode: Outline-only / Pure B&W / Colour compound
- Max process size up to **6000px**
- Acceptance tests for Kelpie-style diamond sign

### Changed
- Default preset is **CNC Outline**
- Colour / photo still use vtracer with milder preprocess
- Version tag **v1.0**

## [0.5.0] — 2026-08-07

- Edge-aware OpenCV preprocess + vtracer-only pipeline

## [2.0.0] / early — 2026-08-07

- Initial Python desktop shell (rembg + vtracer)
