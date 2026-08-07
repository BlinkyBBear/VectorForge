# VectorForge

**Offline desktop app** that converts any raster image into **laser-ready SVG** files.

- **Background removal** (AI via [rembg](https://github.com/danielgatis/rembg) / U2Net, offline after model cache) + click wand / brush refine  
- **High-quality vectorization** via [vtracer](https://github.com/visioncortex/vtracer) (Rust)  
- **Memory-safe** downsampling (hard max 2000px long side)  
- **Windows `.exe`** via PyInstaller  
- Fully offline after install (no cloud APIs)

> This repository is **desktop-first**. A legacy web prototype may exist under `src/`; it is **not** required to run VectorForge.

---

## Quick start (Windows)

### 1. Install Python 3.10+

From [python.org](https://www.python.org/downloads/) — enable **“Add python.exe to PATH”** and **tcl/tk**.

### 2. Clone and install

```bat
git clone https://github.com/YOUR_USER/vectorforge.git
cd vectorforge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the desktop app

```bat
python -m vectorforge
```

Or double-click `scripts\run_desktop.bat`.

### 4. Headless CLI (no GUI)

```bat
python -m vectorforge.cli photo.png -o out.svg --preset photo --bg
python -m vectorforge.cli logo.png  -o logo.svg --preset logo
python -m vectorforge.cli cut.png   -o cut.svg  --preset laser --max-side 1200
```

---

## Build a Windows `.exe`

On a **Windows** PC (recommended for a native `.exe`):

```bat
scripts\build_windows.bat
```

Or PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Output:

```text
dist\VectorForge.exe
```

### First-run model download

The first background-removal uses **rembg u2net** (~176 MB). It is cached under:

```text
%USERPROFILE%\.u2net\u2net.onnx
```

After that, the app runs **fully offline**. To pre-seed offline installs, copy `u2net.onnx` into that folder (or set env `U2NET_HOME` to a folder containing the file).

### One-file notes

- Antivirus may scan the first launch of a PyInstaller binary (normal for unsigned builds).  
- For a **console debug** build, set `console=True` in `VectorForge.spec` and rebuild.

---

## Quality presets

| Preset | Max side | Mode | Best for |
| --- | --- | --- | --- |
| **Logo / Line Art** (default) | 1800 | color spline | Icons, logos, line art |
| **Illustration** | 1700 | color | Flat artwork |
| **High Detail Photo** | 1800 | color | Photos / product shots |
| **Laser Optimized** | 1200 | binary | Cut-ready B&W, fewer islands |
| **Maximum Quality** | 2000 | color | Experimental fidelity |

---

## Workflow

1. **Open** image (JPEG, PNG, WebP, BMP, TIFF, GIF, …)  
2. **Auto remove background** (optional) → click **Erase / Restore / Brush** to refine  
3. Choose a **quality preset**  
4. **Vectorize**  
5. **Export SVG** → open in LightBurn, Inkscape, Illustrator, LaserGRBL, etc.

---

## Project layout

```text
main.py                 # entry for PyInstaller
vectorforge/            # Python package
  __main__.py           # python -m vectorforge  → GUI
  cli.py                # headless convert
  engine/               # memory, bg remove, vtracer wrapper, presets
  ui/app.py             # CustomTkinter desktop UI
requirements.txt
VectorForge.spec        # PyInstaller one-file Windows build
scripts/
  build_windows.bat
  build_windows.ps1
  run_desktop.bat
prompts/                # product prompt history
LICENSE                 # MIT
```

---

## Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# GUI needs Tk (python.org macOS build includes it; Linux: install python3-tk)
python -m vectorforge
# always available:
python -m vectorforge.cli input.png -o out.svg --preset logo --bg
```

---

## Dependencies (why)

| Library | Role |
| --- | --- |
| **CustomTkinter** | Modern offline desktop UI |
| **Pillow** | Image load, EXIF, downsample |
| **numpy** | Iterative flood-fill / wand (no recursion) |
| **rembg + onnxruntime** | Offline subject cutout |
| **vtracer** | High-quality path tracing (Rust) |
| **PyInstaller** | Windows `.exe` packaging |

---

## Safety

- Max process long side **2000px** (hard cap)  
- Images always downsampled **before** rembg/vtracer when larger  
- Flood-fill / wand / brush are **iterative** (queue + visited), never recursive  
- Failed AI BG falls back to corner flood-fill  

---

## License

MIT — see [LICENSE](./LICENSE). You own every exported SVG.

---

## Prompt history

Major product prompts live in [`prompts/`](./prompts/) for version history when you push to your own GitHub.
