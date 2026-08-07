"""
VectorForge desktop UI — CustomTkinter.

Features:
- Presets + full custom parameter controls
- Colour compound vectors + pure B&W
- Photorealistic high-node mode
- Live brush preview
- BG strength slider
"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image, ImageTk

from vectorforge.engine.bg_remove import (
    auto_remove_background,
    brush_stroke,
    rembg_status,
    wand_at,
)
from vectorforge.engine.image_ops import load_image
from vectorforge.engine.memory import HARD_MAX_PROCESS_SIZE, clamp_process_size
from vectorforge.engine.presets import DEFAULT_PRESET_ID, PRESETS
from vectorforge.engine.vectorize import VectorizeParams, vectorize_image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class VectorForgeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("VectorForge — Offline Laser SVG")
        self.geometry("1380x880")
        self.minsize(1000, 700)

        self._source: Image.Image | None = None
        self._subject: Image.Image | None = None
        self._display: Image.Image | None = None
        self._svg_text: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._busy = False
        self._brush_points: list[tuple[float, float]] = []
        self._source_path: Path | None = None
        self._preview_scale = 1.0
        self._preview_size = (1, 1)
        self._canvas_size = (1, 1)
        self._brush_overlay_ids: list[int] = []
        self._custom_overrides: dict[str, Any] = {}

        self._build()
        self._set_status(rembg_status())

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Sidebar (scrollable) ─────────────────────────────
        side_container = ctk.CTkFrame(self, width=360, corner_radius=0)
        side_container.grid(row=0, column=0, sticky="nsew")
        side_container.grid_propagate(False)

        side = ctk.CTkScrollableFrame(side_container, width=340)
        side.pack(fill="both", expand=True)

        ctk.CTkLabel(
            side, text="VectorForge", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(padx=12, pady=(12, 2), anchor="w")
        ctk.CTkLabel(
            side,
            text="Offline → laser / CAD ready SVG",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        ).pack(padx=12, pady=(0, 10), anchor="w")

        ctk.CTkButton(side, text="Open image…", command=self._open_image).pack(
            fill="x", padx=12, pady=3
        )

        # Presets
        ctk.CTkLabel(side, text="Quality preset", anchor="w").pack(
            fill="x", padx=12, pady=(10, 2)
        )
        self.preset_var = ctk.StringVar(value=DEFAULT_PRESET_ID)
        labels = [f"{k} — {v['label']}" for k, v in PRESETS.items()]
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
            wraplength=310,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="gray65",
        )
        self.preset_desc.pack(fill="x", padx=12, pady=(2, 6))

        # Max size
        self.max_side = ctk.CTkSlider(
            side, from_=800, to=HARD_MAX_PROCESS_SIZE, number_of_steps=52
        )
        self.max_side.set(PRESETS[DEFAULT_PRESET_ID]["params"]["max_process_size"])
        ctk.CTkLabel(side, text="Max process size (px)", anchor="w").pack(
            fill="x", padx=12
        )
        self.max_side.pack(fill="x", padx=12, pady=2)
        self.max_side_label = ctk.CTkLabel(side, text="1600 px", anchor="w")
        self.max_side_label.pack(fill="x", padx=12)
        self.max_side.configure(command=self._on_max_side)

        # ── Custom controls ─────────────────────────────────
        ctk.CTkLabel(
            side, text="Custom controls", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(fill="x", padx=12, pady=(14, 4))

        # Colour mode
        ctk.CTkLabel(side, text="Colour mode", anchor="w").pack(fill="x", padx=12)
        self.colormode = ctk.StringVar(value="binary")
        cm = ctk.CTkFrame(side, fg_color="transparent")
        cm.pack(fill="x", padx=8)
        ctk.CTkRadioButton(cm, text="B&W (Laser)", variable=self.colormode, value="binary").pack(side="left", padx=4)
        ctk.CTkRadioButton(cm, text="Colour compound", variable=self.colormode, value="color").pack(side="left", padx=4)

        # Speckle / detail
        self.filter_speckle = ctk.CTkSlider(side, from_=0, to=25, number_of_steps=25)
        self.filter_speckle.set(8)
        ctk.CTkLabel(side, text="Filter speckles (higher = cleaner)", anchor="w").pack(fill="x", padx=12, pady=(8, 0))
        self.filter_speckle.pack(fill="x", padx=12)

        self.path_precision = ctk.CTkSlider(side, from_=1, to=6, number_of_steps=5)
        self.path_precision.set(3)
        ctk.CTkLabel(side, text="Path precision (higher = more nodes)", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.path_precision.pack(fill="x", padx=12)

        self.corner_threshold = ctk.CTkSlider(side, from_=10, to=120, number_of_steps=22)
        self.corner_threshold.set(60)
        ctk.CTkLabel(side, text="Corner threshold", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.corner_threshold.pack(fill="x", padx=12)

        self.length_threshold = ctk.CTkSlider(side, from_=1.5, to=12.0, number_of_steps=21)
        self.length_threshold.set(4.0)
        ctk.CTkLabel(side, text="Length threshold", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.length_threshold.pack(fill="x", padx=12)

        self.color_precision = ctk.CTkSlider(side, from_=1, to=10, number_of_steps=9)
        self.color_precision.set(7)
        ctk.CTkLabel(side, text="Colour precision (colour mode)", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.color_precision.pack(fill="x", padx=12)

        # ── Background tools ────────────────────────────────
        ctk.CTkLabel(
            side, text="Background tools", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(fill="x", padx=12, pady=(14, 4))

        self.bg_tool = ctk.StringVar(value="auto")
        tools = ctk.CTkFrame(side, fg_color="transparent")
        tools.pack(fill="x", padx=8)
        for key, label in (("auto", "Auto"), ("erase", "Erase"), ("restore", "Restore"), ("brush", "Brush")):
            ctk.CTkRadioButton(tools, text=label, variable=self.bg_tool, value=key).pack(side="left", padx=3)

        self.tolerance = ctk.CTkSlider(side, from_=8, to=80)
        self.tolerance.set(36)
        ctk.CTkLabel(side, text="Wand tolerance", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.tolerance.pack(fill="x", padx=12)

        self.bg_strength = ctk.CTkSlider(side, from_=0.0, to=1.0, number_of_steps=20)
        self.bg_strength.set(0.85)
        ctk.CTkLabel(side, text="BG removal strength", anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        self.bg_strength.pack(fill="x", padx=12)
        self.bg_strength_label = ctk.CTkLabel(side, text="0.85 (strong)", anchor="w")
        self.bg_strength_label.pack(fill="x", padx=12)
        self.bg_strength.configure(command=self._on_bg_strength)

        ctk.CTkButton(side, text="Auto remove background", command=self._auto_bg).pack(
            fill="x", padx=12, pady=(10, 3)
        )
        ctk.CTkButton(
            side, text="Reset subject", command=self._reset_subject, fg_color="gray30"
        ).pack(fill="x", padx=12, pady=3)

        # Actions
        ctk.CTkButton(
            side,
            text="Vectorize",
            command=self._vectorize,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(fill="x", padx=12, pady=(16, 4))
        ctk.CTkButton(side, text="Export SVG…", command=self._export_svg).pack(
            fill="x", padx=12, pady=3
        )

        self.stats = ctk.CTkLabel(
            side, text="No result yet", justify="left", anchor="w",
            font=ctk.CTkFont(size=11), text_color="gray70",
        )
        self.stats.pack(fill="x", padx=12, pady=10)

        self.progress = ctk.CTkProgressBar(side)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=12, pady=(0, 12))

        # ── Canvas ──────────────────────────────────────────
        main = ctk.CTkFrame(self, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(main, bg="#1a1a1c", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        self.status = ctk.CTkLabel(main, text="Open an image to begin", anchor="w", height=28)
        self.status.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        self.drop_hint = ctk.CTkLabel(
            self.canvas,
            text="Open image → Auto BG (optional) → choose preset or custom → Vectorize → Export",
            font=ctk.CTkFont(size=14), text_color="gray60",
        )
        self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")

    # ── helpers ─────────────────────────────────────────────
    def _on_preset_label(self, label: str) -> None:
        key = label.split(" — ", 1)[0].strip()
        if key not in PRESETS:
            return
        self.preset_var.set(key)
        p = PRESETS[key]["params"]
        self.preset_desc.configure(text=PRESETS[key]["description"])
        self.max_side.set(p.get("max_process_size", 1600))
        self._on_max_side(self.max_side.get())

        # Sync custom controls to the chosen preset
        self.colormode.set(p.get("colormode", "binary"))
        self.filter_speckle.set(p.get("filter_speckle", 8))
        self.path_precision.set(p.get("path_precision", 3))
        self.corner_threshold.set(p.get("corner_threshold", 60))
        self.length_threshold.set(p.get("length_threshold", 4.0))
        self.color_precision.set(p.get("color_precision", 7))

    def _on_max_side(self, value: float) -> None:
        self.max_side_label.configure(text=f"{int(round(value))} px")

    def _on_bg_strength(self, value: float) -> None:
        v = float(value)
        label = "gentle" if v < 0.4 else "medium" if v < 0.7 else "strong"
        self.bg_strength_label.configure(text=f"{v:.2f} ({label})")

    def _collect_overrides(self) -> dict[str, Any]:
        return {
            "colormode": self.colormode.get(),
            "force_mono": self.colormode.get() == "binary",
            "filter_speckle": int(round(self.filter_speckle.get())),
            "path_precision": int(round(self.path_precision.get())),
            "corner_threshold": int(round(self.corner_threshold.get())),
            "length_threshold": float(self.length_threshold.get()),
            "color_precision": int(round(self.color_precision.get())),
            "max_process_size": int(round(self.max_side.get())),
        }

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        try:
            self.progress.start() if busy else self.progress.stop()
        except Exception:
            pass
        if not busy:
            self.progress.set(0)

    def _run_async(self, fn: Callable[[], None], on_done: Callable[[], None] | None = None) -> None:
        if self._busy:
            self._set_status("Busy — wait for current job to finish.")
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
                if on_done:
                    on_done()

            self.after(0, finish)

        self._set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    def _active_image(self) -> Image.Image | None:
        return self._subject if self._subject is not None else self._source

    def _clear_brush_overlay(self) -> None:
        for iid in self._brush_overlay_ids:
            try:
                self.canvas.delete(iid)
            except Exception:
                pass
        self._brush_overlay_ids.clear()

    def _show_image(self, img: Image.Image) -> None:
        self._display = img
        self.drop_hint.place_forget()
        self._clear_brush_overlay()
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        w, h = img.size
        scale = min(cw / w, ch / h, 1.0) * 0.95
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        preview = img.resize((dw, dh), Image.Resampling.BILINEAR)

        if preview.mode == "RGBA":
            bg = Image.new("RGBA", preview.size, (40, 40, 44, 255))
            for y in range(0, dh, 14):
                for x in range(0, dw, 14):
                    if ((x // 14) + (y // 14)) % 2 == 0:
                        for yy in range(y, min(y + 14, dh)):
                            for xx in range(x, min(x + 14, dw)):
                                bg.putpixel((xx, yy), (52, 52, 58, 255))
            preview = Image.alpha_composite(bg, preview).convert("RGB")
        else:
            preview = preview.convert("RGB")

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

    def _image_to_canvas(self, px: float, py: float) -> tuple[float, float]:
        cw, ch = self._canvas_size
        dw, dh = self._preview_size
        left = (cw - dw) / 2
        top = (ch - dh) / 2
        return left + px * self._preview_scale, top + py * self._preview_scale

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
        self._show_image(img)
        self.stats.configure(text=f"Loaded {img.width}×{img.height}\n{Path(path).name}")
        self._set_status(f"Loaded {Path(path).name}")

    def _auto_bg(self) -> None:
        if self._source is None:
            self._set_status("Open an image first.")
            return
        strength = float(self.bg_strength.get())
        tol = int(20 + strength * 50)

        def job() -> None:
            self.after(0, lambda: self._set_status("Removing background…"))
            self.after(0, lambda: self.progress.set(0.3))
            out = auto_remove_background(self._source, prefer_ai=True, tolerance=tol)
            self._subject = out
            self.after(0, lambda: self._show_image(out))
            self.after(0, lambda: self.progress.set(1.0))
            self.after(0, lambda: self._set_status("Subject ready — refine if needed, then Vectorize"))

        self._run_async(job)

    def _reset_subject(self) -> None:
        self._subject = None
        self._clear_brush_overlay()
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

        if tool in ("erase", "restore", "auto"):
            erase = tool != "restore"

            def job() -> None:
                base = self._active_image()
                assert base is not None
                out = wand_at(base, pt[0], pt[1], erase=erase, tolerance=int(self.tolerance.get()))
                self._subject = out
                self.after(0, lambda: self._show_image(out))
                self.after(0, lambda: self._set_status("Refined"))

            self._run_async(job)

        elif tool == "brush":
            self._brush_points = [pt]
            self._clear_brush_overlay()
            cx, cy = self._image_to_canvas(*pt)
            r = 8
            iid = self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#ff5555", width=2)
            self._brush_overlay_ids.append(iid)

    def _on_canvas_drag(self, event) -> None:  # noqa: ANN001
        if self.bg_tool.get() != "brush" or self._busy:
            return
        pt = self._canvas_to_image(event.x, event.y)
        if not pt:
            return
        self._brush_points.append(pt)
        cx, cy = self._image_to_canvas(*pt)
        r = 8
        iid = self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#ff5555", width=1)
        self._brush_overlay_ids.append(iid)
        if len(self._brush_overlay_ids) > 500:
            old = self._brush_overlay_ids.pop(0)
            try:
                self.canvas.delete(old)
            except Exception:
                pass

    def _on_canvas_release(self, event) -> None:  # noqa: ANN001
        if self.bg_tool.get() != "brush" or not self._brush_points:
            return
        pts = list(self._brush_points)
        self._brush_points = []

        def job() -> None:
            base = self._active_image()
            assert base is not None
            out = brush_stroke(base, pts, radius=14, erase=True)
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

        def job() -> None:
            def prog(stage: str, p: float) -> None:
                self.after(0, lambda: self._set_status(stage))
                self.after(0, lambda: self.progress.set(p))

            result = vectorize_image(
                img,
                VectorizeParams(
                    preset_id=preset,
                    max_process_size=overrides["max_process_size"],
                    overrides=overrides,
                ),
                on_progress=prog,
            )
            self._svg_text = result.svg

            def done() -> None:
                self.stats.configure(
                    text=(
                        f"paths: {result.path_count}   nodes ≈ {result.node_estimate}\n"
                        f"{result.process_label}   {result.duration_ms} ms\n"
                        f"preset={preset}  mode={overrides['colormode']}"
                    )
                )
                self._set_status("Vectorized — Export SVG when ready")
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
