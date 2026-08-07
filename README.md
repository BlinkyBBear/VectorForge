# VectorForge v0.5

**Offline desktop app** — convert any raster image into **high-quality laser / CAD-ready SVG**.

Targets: **xTool Studio**, **Fusion 360**, **LightBurn**, **Inkscape**, Glowforge, OMTech, etc.

| | |
| --- | --- |
| **Version** | 0.5.0 |
| **Engine** | Edge-aware preprocess (OpenCV) → [vtracer](https://github.com/visioncortex/vtracer) |
| **BG removal** | [rembg](https://github.com/danielgatis/rembg) u2net + wand/brush |
| **Offline** | Yes, after first model download |
| **Windows** | `scripts\build_windows.bat` → `dist\VectorForge.exe` |

---

## What’s new in v0.5

- **Edge-aware preprocessing** before tracing (CLAHE, bilateral denoise, Canny boost, adaptive threshold for laser)
- **Retuned presets** that actually differ (Laser Pro → Photorealistic Max)
- **Full sidebar controls** for every major vtracer + preprocess parameter
- **Pure B&W vs Colour Compound** mode toggle
- **Max process size up to 6000px**
- **BG strength** control + **live brush preview**
- SVG sanitized for CAD import (`viewBox`, `fill-rule`, no scripts)

---

## Quick start (Windows)

```bat
git clone https://github.com/BlinkyBBear/VectorForge.git
cd VectorForge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m vectorforge
```

### Build `.exe`

```bat
scripts\build_windows.bat
```

Output: `dist\VectorForge.exe`  
First BG removal downloads `u2net.onnx` (~176 MB) into `%USERPROFILE%\.u2net\` — fully offline after that.

### CLI

```bat
python -m vectorforge.cli logo.png  -o logo.svg  --preset logo
python -m vectorforge.cli sign.png  -o cut.svg   --preset laser_pro --max-side 3200
python -m vectorforge.cli photo.jpg -o photo.svg --preset photoreal --bg --bg-strength 0.6
python -m vectorforge.cli engrave.jpg -o eng.svg --preset bw_compound
```

---

## Presets (recommended settings)

| Preset | Best for | Tips |
| --- | --- | --- |
| **Laser Pro** | Cut paths, solid black fills | High contrast source; raise **Edge strength**; lower **Filter speckle** for thin lines |
| **Logo / Line Art** | Icons, signs, brand marks | Default for most logos; keep process size ≥ 2800 if source is large |
| **Illustration Colour** | Flat colour art | Increase **Layer difference** if colours muddy |
| **High Detail Photo** | Product shots, portraits | Use BG remove first; 24+ effective colours via color precision 8 |
| **Photorealistic Max** | Max detail → CAD | Slow; max side 4000–4800; filter_speckle=1 |
| **B&W Compound** | Engrave tonal layers | Adjust compound levels via re-running with contrast |

### Logos & signs

1. Prefer **Logo / Line Art** or **Laser Pro**  
2. Optional: Auto remove BG → erase remaining fringe  
3. Max process **2800–4000**  
4. Export SVG → open in xTool / LightBurn as **fill** (engrave) or **line** (cut)

### Photographs

1. **High Detail Photo** or **Photorealistic Max**  
2. BG remove with strength ~0.5–0.7  
3. Colour mode **Colour**  
4. Expect multi-layer stacked paths (hierarchical)

---

## Project layout

```text
vectorforge/
  engine/
    preprocess.py   # edge-aware pipeline (v0.5)
    vectorize.py    # vtracer + SVG sanitize
    bg_remove.py    # rembg + wand/brush
    presets.py
    memory.py
  ui/app.py         # CustomTkinter desktop UI
  cli.py
main.py
VectorForge.spec
scripts/build_windows.bat
prompts/
tests/
```

---

## Dependencies

| Package | Role |
| --- | --- |
| customtkinter | Desktop UI |
| Pillow / numpy / opencv-python-headless | Load + edge preprocess |
| vtracer | Path tracing (Rust) |
| rembg[cpu] | Offline subject cutout |
| pyinstaller | Windows `.exe` |

---

## License

MIT — see [LICENSE](./LICENSE). You own every exported SVG.
