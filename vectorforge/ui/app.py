"""
VectorForge v0.5 desktop UI — CustomTkinter.

Full custom controls, live brush preview, edge-aware pipeline.
"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from vectorforge import __version__
from vectorforge.engine.bg_remove import (
    auto_remove_background,
    brush_stroke,
    rembg_status,
    wand_at,
)
from vectorforge.engine.image_ops import load_image
from vectorforge.engine.memory import HARD_MAX_PROCESS_SIZE, clamp_process_size
from vectorforge.engine.presets import DEFAULT_PRESET_ID, PRESETS, preset_choices
from vectorforge.engine.vectorize import VectorizeParams, vectorize_image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class VectorForgeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"VectorForge v{__version__} — Offline Laser SVG")
        self.geometry("1360x900")
        self.minsize(1024, 700)

        self._source: Image.Image | None = None
        self._subject: Image.Image | None = None
        self._svg_text: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._busy = False
        self._brush_points: list[tuple[float, float]] = []
        self._source_path: Path | None = None
        self._preview_scale = 1.0
        self._preview_size = (1, 1)
        self._canvas_size = (800, 600)
        self._controls: dict[str, Any] = {}

        self._build()
        self._apply_preset_to_controls(DEFAULT_PRESET_ID)
        self._set_status(rembg_status())

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Scrollable sidebar
        side = ctk.CTkScrollableFrame(self, width=340, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(
            side, text="VectorForge", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(padx=12, pady=(12, 0), anchor="w")
        ctk.CTkLabel(
            side,
            text=f"v{__version__} · offline · laser / CAD ready",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        ).pack(padx=12, pady=(0, 10), anchor="w")

        ctk.CTkButton(side, text="Open image…", command=self._open_image).pack(
            fill="x", padx=12, pady=4
        )

        # Preset
        self._section(side, "Quality preset")
        self.preset_var = ctk.StringVar(value=DEFAULT_PRESET_ID)
        labels = [f"{k} — {lab}" for k, lab in preset_choices()]
        self.preset_menu = ctk.CTkOptionMenu(
            side, values=labels, command=self._on_preset_label
        )
        self.preset_menu.set(
            f"{DEFAULT_PRESET_ID} — {PRESETS[DEFAULT_PRESET_ID]['label']}"
        )
        self.preset_menu.pack(fill="x", padx=12, pady=2)
        self.preset_desc = ctk.CTkLabel(
            side,
            text=PRESETS[DEFAULT_PRESET_ID]["description"],
            wraplength=300,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="gray65",
        )
        self.preset_desc.pack(fill="x", padx=12, pady=(2, 8))

        # Colour mode
        self._section(side, "Colour mode")
        self.color_mode = ctk.StringVar(value="auto")
        row = ctk.CTkFrame(side, fg_color="transparent")
        row.pack(fill="x", padx=12)
        ctk.CTkRadioButton(
            row, text="Auto (preset)", variable=self.color_mode, value="auto"
        ).pack(side="left", padx=2)
        ctk.CTkRadioButton(
            row, text="Pure B&W", variable=self.color_mode, value="bw"
        ).pack(side="left", padx=2)
        ctk.CTkRadioButton(
            row, text="Colour", variable=self.color_mode, value="color"
        ).pack(side="left", padx=2)

        # Resolution
        self._section(side, "Max process size (px)")
        self.max_side = ctk.CTkSlider(
            side, from_=800, to=HARD_MAX_PROCESS_SIZE, number_of_steps=52
        )
        self.max_side.set(3200)
        self.max_side.pack(fill="x", padx=12, pady=2)
        self.max_side_label = ctk.CTkLabel(side, text="3200 px", anchor="w")
        self.max_side_label.pack(fill="x", padx=12)
        self.max_side.configure(command=self._on_max_side)

        # Preprocess controls
        self._section(side, "Edge / preprocess")
        self.edge_strength = self._slider(side, "Edge strength", 0, 1, 0.7)
        self.denoise = self._slider(side, "Denoise", 0, 1, 0.3)
        self.contrast = self._slider(side, "Contrast (CLAHE)", 0, 1, 0.65)
        self.threshold_bias = self._slider(side, "Threshold bias (laser)", 0, 1, 0.45)

        # Vtracer controls
        self._section(side, "Tracer (vtracer)")
        self.filter_speckle = self._slider(side, "Filter speckle", 0, 20, 3, int_mode=True)
        self.color_precision = self._slider(side, "Color precision", 1, 8, 7, int_mode=True)
        self.layer_difference = self._slider(side, "Layer difference", 1, 32, 12, int_mode=True)
        self.corner_threshold = self._slider(side, "Corner threshold °", 0, 180, 40, int_mode=True)
        self.length_threshold = self._slider(side, "Length threshold", 2, 12, 3.0)
        self.splice_threshold = self._slider(side, "Splice threshold", 0, 90, 35, int_mode=True)
        self.path_precision = self._slider(side, "Path precision", 1, 8, 3, int_mode=True)
        self.max_iterations = self._slider(side, "Max iterations", 1, 20, 12, int_mode=True)

        self.trace_mode = ctk.StringVar(value="spline")
        ctk.CTkLabel(side, text="Path mode", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkOptionMenu(
            side, variable=self.trace_mode, values=["spline", "polygon", "none"]
        ).pack(fill="x", padx=12, pady=2)

        self.invert_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(side, text="Invert", variable=self.invert_var).pack(
            anchor="w", padx=12, pady=6
        )

        # BG tools
        self._section(side, "Background removal")
        self.bg_strength = self._slider(side, "BG strength", 0, 1, 0.55)
        self.tolerance = self._slider(side, "Wand tolerance", 8, 80, 36, int_mode=True)
        self.brush_radius = self._slider(side, "Brush radius", 4, 48, 14, int_mode=True)

        self.bg_tool = ctk.StringVar(value="erase")
        tools = ctk.CTkFrame(side, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=4)
        for key, label in (
            ("erase", "Erase"),
            ("restore", "Restore"),
            ("brush", "Brush−"),
        ):
            ctk.CTkRadioButton(
                tools, text=label, variable=self.bg_tool, value=key
            ).pack(side="left", padx=4)

        ctk.CTkButton(
            side, text="Auto remove background", command=self._auto_bg
        ).pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkButton(
            side, text="Reset subject", command=self._reset_subject, fg_color="gray30"
        ).pack(fill="x", padx=12, pady=4)

        ctk.CTkButton(
            side,
            text="Vectorize",
            command=self._vectorize,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(fill="x", padx=12, pady=(14, 4))
        ctk.CTkButton(side, text="Export SVG…", command=self._export_svg).pack(
            fill="x", padx=12, pady=4
        )

        self.stats = ctk.CTkLabel(
            side,
            text="No result yet",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        )
        self.stats.pack(fill="x", padx=12, pady=10)

        self.progress = ctk.CTkProgressBar(side)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=12, pady=(0, 12))

        # Canvas
        main = ctk.CTkFrame(self, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(main, bg="#1a1a1c", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

        self.status = ctk.CTkLabel(
            main, text="Open an image to begin", anchor="w", height=28
        )
        self.status.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        self.drop_hint = ctk.CTkLabel(
            self.canvas,
            text=(
                "Open a JPEG / PNG / WebP…\n"
                "Auto BG → refine → pick preset → Vectorize → Export SVG\n"
                "Imports cleanly into xTool Studio · Fusion 360 · LightBurn · Inkscape"
            ),
            font=ctk.CTkFont(size=14),
            text_color="gray60",
        )
        self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")

    def _section(self, parent: ctk.CTkBaseClass, title: str) -> None:
        ctk.CTkLabel(
            parent,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="x", padx=12, pady=(12, 2))

    def _slider(
        self,
        parent: ctk.CTkBaseClass,
        label: str,
        lo: float,
        hi: float,
        default: float,
        *,
        int_mode: bool = False,
    ) -> ctk.CTkSlider:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(row, text=label, anchor="w", font=ctk.CTkFont(size=11)).pack(
            side="left"
        )
        val_lbl = ctk.CTkLabel(
            row,
            text=str(int(default) if int_mode else f"{default:.2f}"),
            width=48,
            anchor="e",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        )
        val_lbl.pack(side="right")
        steps = int(hi - lo) if int_mode else 100
        s = ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=max(1, steps))
        s.set(default)

        def on_change(v: float, lbl=val_lbl, im=int_mode) -> None:
            lbl.configure(text=str(int(round(v))) if im else f"{v:.2f}")

        s.configure(command=on_change)
        s.pack(fill="x", padx=12, pady=(0, 2))
        self._controls[label] = s
        return s

    # ── control helpers ─────────────────────────────────────
    def _on_preset_label(self, label: str) -> None:
        key = label.split(" — ", 1)[0].strip()
        if key in PRESETS:
            self.preset_var.set(key)
            self.preset_desc.configure(text=PRESETS[key]["description"])
            self._apply_preset_to_controls(key)

    def _apply_preset_to_controls(self, key: str) -> None:
        p = PRESETS[key]["params"]
        self.max_side.set(p.get("max_process_size", 2800))
        self._on_max_side(self.max_side.get())
        self.edge_strength.set(p.get("edge_strength", 0.55))
        self.denoise.set(p.get("denoise", 0.35))
        self.contrast.set(p.get("contrast", 0.55))
        self.threshold_bias.set(p.get("threshold_bias", 0.5))
        self.filter_speckle.set(p.get("filter_speckle", 4))
        self.color_precision.set(p.get("color_precision", 6))
        self.layer_difference.set(p.get("layer_difference", 16))
        self.corner_threshold.set(p.get("corner_threshold", 60))
        self.length_threshold.set(p.get("length_threshold", 4.0))
        self.splice_threshold.set(p.get("splice_threshold", 45))
        self.path_precision.set(p.get("path_precision", 3))
        self.max_iterations.set(p.get("max_iterations", 10))
        self.trace_mode.set(p.get("mode", "spline"))
        self.invert_var.set(bool(p.get("invert", False)))
        # fire label updates
        for s in (
            self.edge_strength,
            self.denoise,
            self.contrast,
            self.threshold_bias,
            self.filter_speckle,
            self.color_precision,
            self.layer_difference,
            self.corner_threshold,
            self.length_threshold,
            self.splice_threshold,
            self.path_precision,
            self.max_iterations,
        ):
            cmd = s.cget("command")
            if callable(cmd):
                cmd(s.get())

    def _on_max_side(self, value: float) -> None:
        self.max_side_label.configure(text=f"{int(round(value))} px")

    def _collect_overrides(self) -> dict[str, Any]:
        cm = self.color_mode.get()
        o: dict[str, Any] = {
            "max_process_size": clamp_process_size(self.max_side.get()),
            "edge_strength": float(self.edge_strength.get()),
            "denoise": float(self.denoise.get()),
            "contrast": float(self.contrast.get()),
            "threshold_bias": float(self.threshold_bias.get()),
            "filter_speckle": int(round(self.filter_speckle.get())),
            "color_precision": int(round(self.color_precision.get())),
            "layer_difference": int(round(self.layer_difference.get())),
            "corner_threshold": int(round(self.corner_threshold.get())),
            "length_threshold": float(self.length_threshold.get()),
            "splice_threshold": int(round(self.splice_threshold.get())),
            "path_precision": int(round(self.path_precision.get())),
            "max_iterations": int(round(self.max_iterations.get())),
            "mode": self.trace_mode.get(),
            "invert": bool(self.invert_var.get()),
        }
        if cm == "bw":
            o["force_binary"] = True
            o["colormode"] = "binary"
            o["preprocess_mode"] = "laser_bw"
        elif cm == "color":
            o["force_color"] = True
            o["colormode"] = "color"
        return o

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        try:
            if busy:
                self.progress.start()
            else:
                self.progress.stop()
                self.progress.set(0)
        except Exception:
            pass

    def _run_async(self, fn: Callable[[], None]) -> None:
        if self._busy:
            self._set_status("Busy — wait for current job.")
            return

        def worker() -> None:
            err: str | None = None
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                err = f"{e}\n{traceback.format_exc()}"

            def finish() -> None:
                self._set_busy(False)
                if err:
                    self._set_status(f"Error: {err.splitlines()[0]}")
                    print(err)

            self.after(0, finish)

        self._set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    def _active_image(self) -> Image.Image | None:
        return self._subject if self._subject is not None else self._source

    def _redraw(self) -> None:
        img = self._active_image()
        if img is not None:
            self._show_image(img, brush_overlay=self._brush_points if self.bg_tool.get() == "brush" else None)

    def _show_image(
        self,
        img: Image.Image,
        brush_overlay: list[tuple[float, float]] | None = None,
    ) -> None:
        self.drop_hint.place_forget()
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        w, h = img.size
        scale = min(cw / w, ch / h, 1.0) * 0.96
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        preview = img.resize((dw, dh), Image.Resampling.BILINEAR)

        if preview.mode == "RGBA":
            bg = Image.new("RGBA", preview.size, (40, 40, 44, 255))
            tile = 12
            px = bg.load()
            for y in range(0, dh, tile):
                for x in range(0, dw, tile):
                    if ((x // tile) + (y // tile)) % 2 == 0:
                        for yy in range(y, min(y + tile, dh)):
                            for xx in range(x, min(x + tile, dw)):
                                px[xx, yy] = (52, 52, 58, 255)
            preview = Image.alpha_composite(bg, preview).convert("RGB")
        else:
            preview = preview.convert("RGB")

        # Live brush trail
        if brush_overlay and len(brush_overlay) >= 1:
            draw = ImageDraw.Draw(preview, "RGBA")
            r = max(1, int(round(self.brush_radius.get() * scale)))
            for x, y in brush_overlay:
                cx = int(x * scale)
                cy = int(y * scale)
                draw.ellipse(
                    (cx - r, cy - r, cx + r, cy + r),
                    fill=(255, 60, 60, 90),
                    outline=(255, 80, 80, 180),
                )

        self._photo = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")
        self._preview_scale = scale
        self._preview_size = (dw, dh)
        self._canvas_size = (cw, ch)

    def _canvas_to_image(self, event_x: int, event_y: int) -> tuple[float, float] | None:
        img = self._active_image()
        if img is None:
            return None
        cw, ch = self._canvas_size
        dw, dh = self._preview_size
        left = (cw - dw) / 2
        top = (ch - dh) / 2
        px = (event_x - left) / self._preview_scale
        py = (event_y - top) / self._preview_scale
        if px < 0 or py < 0 or px >= img.width or py >= img.height:
            return None
        return px, py

    # ── actions ─────────────────────────────────────────────
    def _open_image(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Open image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            img = load_image(path)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"Load failed: {e}")
            return
        self._source_path = Path(path)
        self._source = img
        self._subject = None
        self._svg_text = None
        self._brush_points = []
        self._show_image(img)
        self.stats.configure(text=f"Loaded {img.width}×{img.height}\n{Path(path).name}")
        self._set_status(f"Loaded {Path(path).name}")

    def _auto_bg(self) -> None:
        if self._source is None:
            self._set_status("Open an image first.")
            return
        strength = float(self.bg_strength.get())

        def job() -> None:
            self.after(0, lambda: self._set_status("Removing background…"))
            out = auto_remove_background(
                self._source, prefer_ai=True, strength=strength
            )
            self._subject = out
            self.after(0, lambda: self._show_image(out))
            self.after(
                0,
                lambda: self._set_status(
                    f"Subject ready (strength={strength:.2f}) — refine then Vectorize"
                ),
            )

        self._run_async(job)

    def _reset_subject(self) -> None:
        self._subject = None
        self._brush_points = []
        if self._source is not None:
            self._show_image(self._source)
        self._set_status("Subject reset")

    def _on_canvas_click(self, event) -> None:  # noqa: ANN001
        if self._busy or self._active_image() is None:
            return
        tool = self.bg_tool.get()
        pt = self._canvas_to_image(event.x, event.y)
        if pt is None:
            return
        if tool == "brush":
            self._brush_points = [pt]
            self._show_image(self._active_image(), brush_overlay=self._brush_points)
            return
        erase = tool != "restore"

        def job() -> None:
            base = self._active_image()
            assert base is not None
            out = wand_at(
                base,
                pt[0],
                pt[1],
                erase=erase,
                tolerance=int(round(self.tolerance.get())),
            )
            self._subject = out
            self.after(0, lambda: self._show_image(out))
            self.after(0, lambda: self._set_status("Refined subject"))

        self._run_async(job)

    def _on_canvas_drag(self, event) -> None:  # noqa: ANN001
        if self.bg_tool.get() != "brush" or self._busy:
            return
        pt = self._canvas_to_image(event.x, event.y)
        if not pt:
            return
        self._brush_points.append(pt)
        # Live preview while dragging
        if len(self._brush_points) % 2 == 0 or len(self._brush_points) < 4:
            base = self._active_image()
            if base is not None:
                self._show_image(base, brush_overlay=self._brush_points)

    def _on_canvas_release(self, event) -> None:  # noqa: ANN001
        if self.bg_tool.get() != "brush" or not self._brush_points:
            return
        pts = list(self._brush_points)
        self._brush_points = []
        radius = int(round(self.brush_radius.get()))

        def job() -> None:
            base = self._active_image()
            assert base is not None
            out = brush_stroke(base, pts, radius=radius, erase=True)
            self._subject = out
            self.after(0, lambda: self._show_image(out))
            self.after(0, lambda: self._set_status("Brush applied"))

        self._run_async(job)

    def _vectorize(self) -> None:
        img = self._active_image()
        if img is None:
            self._set_status("Open an image first.")
            return
        preset = self.preset_var.get()
        overrides = self._collect_overrides()
        max_side = overrides["max_process_size"]

        def job() -> None:
            def prog(stage: str, p: float) -> None:
                self.after(0, lambda: self._set_status(stage))
                self.after(0, lambda: self.progress.set(p))

            result = vectorize_image(
                img,
                VectorizeParams(
                    preset_id=preset,
                    max_process_size=max_side,
                    overrides=overrides,
                ),
                on_progress=prog,
            )
            self._svg_text = result.svg

            def done() -> None:
                self.stats.configure(
                    text=(
                        f"paths: {result.path_count}  nodes~{result.node_estimate}\n"
                        f"working: {result.process_label}\n"
                        f"{result.preprocess_note}\n"
                        f"{result.duration_ms} ms · {preset}"
                    )
                )
                warn = f" | {result.warning}" if result.warning else ""
                self._set_status(f"Vectorized — Export SVG{warn}")
                self.progress.set(1.0)

            self.after(0, done)

        self._run_async(job)

    def _export_svg(self) -> None:
        if not self._svg_text:
            self._set_status("Vectorize first, then export.")
            return
        from tkinter import filedialog

        default = "vectorforge.svg"
        if self._source_path:
            default = self._source_path.with_suffix(".svg").name
        path = filedialog.asksaveasfilename(
            title="Export SVG",
            defaultextension=".svg",
            initialfile=default,
            filetypes=[("SVG", "*.svg")],
        )
        if not path:
            return
        Path(path).write_text(self._svg_text, encoding="utf-8")
        self._set_status(f"Saved {path}")


def run_app() -> None:
    app = VectorForgeApp()
    app.mainloop()
