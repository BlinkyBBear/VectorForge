# VectorForge v1.0

**Offline Windows desktop app** — convert raster images into **clean, cut-ready SVG + DXF** for CNC sheet-metal, plasma, laser, and CAD.

| | |
| --- | --- |
| **Version** | 1.0.0 |
| **Primary engine** | **Potrace** (CNC Outline / Logo / Laser B&W) |
| **Colour engine** | [vtracer](https://github.com/visioncortex/vtracer) |
| **BG removal** | rembg (u2net) + wand/brush |
| **Export** | SVG + DXF |
| **Offline** | After first model download |

**Repo:** [github.com/BlinkyBBear/VectorForge](https://github.com/BlinkyBBear/VectorForge)

---

## Why v1.0 (not a v0.5 patch)

v0.5 used aggressive dual-threshold preprocessing that often flooded logos.  
v1.0 is rebuilt for **geometric fidelity**:

1. **Potrace-first** for solid high-contrast art (same class of algorithm as Inkscape Trace Bitmap / Super Vectorizer-style logo work)
2. **Single Otsu / fixed / adaptive** threshold — no flood-to-black merge
3. **Live preview of actual path geometry** after Vectorize
4. **DXF export** for CNC / Fusion 360

### Acceptance (Kelpie-style sign)

High-contrast diamond “ON BOARD” style logo → **CNC Outline**:

- Closed stroke paths
- Outer diamond as a clean closed contour
- Internal figures as separate closed paths
- Export SVG/DXF → cut with minimal node editing

---

## Quick start (Windows)

```bat
git clone https://github.com/BlinkyBBear/VectorForge.git
cd VectorForge
git checkout v1.0
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m vectorforge
```

### Build `.exe`

```bat
scripts\build_windows.bat
```

→ `dist\VectorForge.exe`  
First BG removal downloads `u2net.onnx` (~176 MB) into `%USERPROFILE%\.u2net\`.

### CLI

```bat
python -m vectorforge.cli sign.png -o cut.svg --dxf cut.dxf --preset cnc_outline
python -m vectorforge.cli logo.png -o logo.svg --preset logo
python -m vectorforge.cli photo.jpg -o photo.svg --preset photo --bg
```

---

## Presets

| Preset | Engine | Use for |
| --- | --- | --- |
| **CNC Outline** (default) | Potrace stroke | Plasma / router / laser cut-outs |
| **Laser Pro** | Potrace fill | Solid black fills + holes |
| **Logo / Line Art** | Potrace fill | Sharp brand marks & signs |
| **Colour Compound** | vtracer | Multi-colour stacked layers |
| **High Detail Photo** | vtracer | Photos |
| **Photorealistic Max** | vtracer | Max fidelity (slow) |

### Colour mode toggle

- **Outline-only** — stroke paths (CNC)
- **Pure B&W** — filled black evenodd
- **Colour** — vtracer compound

---

## Workflow (CNC cut-out)

1. Open a high-contrast logo or sign (or remove background first)
2. Preset **CNC Outline**
3. Adjust **Black level** / **Denoise** only if edges look soft
4. **Vectorize** → preview switches to **Vector paths** (real geometry)
5. **Export SVG** and/or **Export DXF**
6. Import into Fusion 360 / SheetCam / LightBurn / xTool

### Tips for best outline quality

- Prefer PNG or high-quality JPEG; avoid heavy compression artifacts
- High contrast (dark art on light bg) works best
- Raise max process size to 3000–5000 for large signs
- If the image is light-on-dark, enable **Invert ink**
- Lower **Turd size** to keep tiny holes; raise it to kill speckles

---

## Project layout

```text
vectorforge/
  engine/
    preprocess.py      # clean threshold (no flood)
    potrace_engine.py  # CNC / logo / B&W
    vectorize.py       # orchestrator
    svg_render.py      # live path preview
    dxf_export.py      # DXF for CAD/CNC
    bg_remove.py
    presets.py
  ui/app.py            # CustomTkinter UI
  cli.py
main.py
VectorForge.spec
scripts/build_windows.bat
tests/
prompts/
```

---

## License

MIT — see [LICENSE](./LICENSE). You own every exported file.
