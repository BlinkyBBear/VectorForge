"""
VectorForge desktop UI — CustomTkinter.

Fully offline after install (rembg model cached under U2NET_HOME / ~/.u2net).
Heavy work runs on a worker thread so the UI stays responsive.
"""

from __future__ import annotations

import io
import threading
import traceback
from pathlib import Path
from typing import Callable

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
from vectorforge.engine.vectorize import VectorizeParams, save_svg, vectorize_image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class VectorForgeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("VectorForge — Offline Laser SVG")
        self.geometry("1280x820")
        self.minsize(960, 640)

        self._source: Image.Image | None = None
        self._subject: Image.Image | None = None
        self._display: Image.Image | None = None
        self._svg_text: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._busy = False
        self._brush_points: list[tuple[float, float]] = []
        self._source_path: Path | None = None

        self._build()
        self._set_status(rembg_status())

    # ── layout ──────────────────────────────────────────────
    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        side = ctk.CTkFrame(self, width=320, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)

        ctk.CTkLabel(
            side, text="VectorForge", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(padx=16, pady=(16, 4), anchor="w")
        ctk.CTkLabel(
            side,
            text="Offline image → laser-ready SVG",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        ).pack(padx=16, pady=(0, 12), anchor="w")

        ctk.CTkButton(side, text="Open image…", command=self._open_image).pack(
            fill="x", padx=16, pady=4
        )

        ctk.CTkLabel(side, text="Quality preset", anchor="w").pack(
            fill="x", padx=16, pady=(12, 2)
        )
        self.preset_var = ctk.StringVar(value=DEFAULT_PRESET_ID)
        labels = [f"{k} — {v['label']}" for k, v in PRESETS.items()]
        self._preset_keys = list(PRESETS.keys())
        self.preset_menu = ctk.CTkOptionMenu(
            side,
            values=labels,
            command=self._on_preset_label,
        )
        self.preset_menu.set(f"{DEFAULT_PRESET_ID} — {PRESETS[DEFAULT_PRESET_ID]['label']}")
        self.preset_menu.pack(fill="x", padx=16, pady=2)
        self.preset_desc = ctk.CTkLabel(
            side,
            text=PRESETS[DEFAULT_PRESET_ID]["description"],
            wraplength=280,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="gray65",
        )
        self.preset_desc.pack(fill="x", padx=16, pady=(2, 8))

        self.max_side = ctk.CTkSlider(
            side, from_=800, to=HARD_MAX_PROCESS_SIZE, number_of_steps=24
        )
        self.max_side.set(PRESETS[DEFAULT_PRESET_ID]["params"]["max_process_size"])
        ctk.CTkLabel(side, text="Max process size (px)", anchor="w").pack(
            fill="x", padx=16
        )
        self.max_side.pack(fill="x", padx=16, pady=2)
        self.max_side_label = ctk.CTkLabel(side, text="1800 px", anchor="w")
        self.max_side_label.pack(fill="x", padx=16)
        self.max_side.configure(command=self._on_max_side)

        ctk.CTkLabel(side, text="BG tool", anchor="w").pack(
            fill="x", padx=16, pady=(12, 2)
        )
        self.bg_tool = ctk.StringVar(value="auto")
        tools = ctk.CTkFrame(side, fg_color="transparent")
        tools.pack(fill="x", padx=12)
        for key, label in (
            ("auto", "Auto"),
            ("erase", "Erase"),
            ("restore", "Restore"),
            ("brush", "Brush−"),
        ):
            ctk.CTkRadioButton(
                tools, text=label, variable=self.bg_tool, value=key
            ).pack(side="left", padx=4)

        self.tolerance = ctk.CTkSlider(side, from_=8, to=80)
        self.tolerance.set(36)
        ctk.CTkLabel(side, text="Wand tolerance", anchor="w").pack(
            fill="x", padx=16, pady=(8, 0)
        )
        self.tolerance.pack(fill="x", padx=16)

        ctk.CTkButton(
            side, text="Auto remove background", command=self._auto_bg
        ).pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkButton(
            side, text="Reset subject", command=self._reset_subject, fg_color="gray30"
        ).pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(
            side,
            text="Vectorize",
            command=self._vectorize,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkButton(
            side, text="Export SVG…", command=self._export_svg
        ).pack(fill="x", padx=16, pady=4)

        self.stats = ctk.CTkLabel(
            side,
            text="No result yet",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        )
        self.stats.pack(fill="x", padx=16, pady=12)

        self.progress = ctk.CTkProgressBar(side)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=16, pady=(0, 8))

        # Main canvas area
        main = ctk.CTkFrame(self, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(main, bg="#1a1a1c", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        self.status = ctk.CTkLabel(
            main, text="Open an image to begin", anchor="w", height=28
        )
        self.status.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        # Checkerboard-ish hint via label
        self.drop_hint = ctk.CTkLabel(
            self.canvas,
            text="Drop / Open a JPEG, PNG, WebP, BMP…\nThen: Auto remove BG → refine clicks → Vectorize → Export SVG",
            font=ctk.CTkFont(size=14),
            text_color="gray60",
        )
        self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")

    # ── helpers ─────────────────────────────────────────────
    def _on_preset_label(self, label: str) -> None:
        key = label.split(" — ", 1)[0].strip()
        if key in PRESETS:
            self.preset_var.set(key)
            self.preset_desc.configure(text=PRESETS[key]["description"])
            self.max_side.set(PRESETS[key]["params"]["max_process_size"])
            self._on_max_side(self.max_side.get())
            if key == "max":
                self._set_status(
                    "Maximum Quality uses more memory/CPU — offline still safe."
                )

    def _on_max_side(self, value: float) -> None:
        self.max_side_label.configure(text=f"{int(round(value))} px")

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        # CTk buttons don't all share state the same way — ignore failures
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

    def _show_image(self, img: Image.Image) -> None:
        self._display = img
        self.drop_hint.place_forget()
        # Fit to canvas
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        w, h = img.size
        scale = min(cw / w, ch / h, 1.0) * 0.95
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        preview = img.resize((dw, dh), Image.Resampling.BILINEAR)
        # Composite on checker-like dark for alpha
        if preview.mode == "RGBA":
            bg = Image.new("RGBA", preview.size, (40, 40, 44, 255))
            # simple checker
            for y in range(0, dh, 12):
                for x in range(0, dw, 12):
                    if ((x // 12) + (y // 12)) % 2 == 0:
                        for yy in range(y, min(y + 12, dh)):
                            for xx in range(x, min(x + 12, dw)):
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
        if img is None or not hasattr(self, "_preview_scale"):
            return None
        cw, ch = self._canvas_size
        dw, dh = self._preview_size
        # image top-left on canvas
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
        self._show_image(img)
        self.stats.configure(
            text=f"Loaded {img.width}×{img.height}\n{Path(path).name}"
        )
        self._set_status(f"Loaded {Path(path).name} — remove BG or vectorize")

    def _auto_bg(self) -> None:
        if self._source is None:
            self._set_status("Open an image first.")
            return

        def job() -> None:
            self.after(0, lambda: self._set_status("Removing background (offline)…"))
            self.after(0, lambda: self.progress.set(0.3))
            out = auto_remove_background(self._source, prefer_ai=True)
            self._subject = out
            self.after(0, lambda: self._show_image(out))
            self.after(0, lambda: self.progress.set(1.0))
            self.after(
                0,
                lambda: self._set_status(
                    "Subject ready — click Erase/Restore to refine, then Vectorize"
                ),
            )

        self._run_async(job)

    def _reset_subject(self) -> None:
        self._subject = None
        if self._source is not None:
            self._show_image(self._source)
        self._set_status("Subject reset to original")

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
                out = wand_at(
                    base,
                    pt[0],
                    pt[1],
                    erase=erase,
                    tolerance=int(self.tolerance.get()),
                )
                self._subject = out
                self.after(0, lambda: self._show_image(out))
                self.after(0, lambda: self._set_status("Refined subject"))

            self._run_async(job)
        elif tool == "brush":
            self._brush_points = [pt]

    def _on_canvas_drag(self, event) -> None:  # noqa: ANN001
        if self.bg_tool.get() != "brush" or self._busy:
            return
        pt = self._canvas_to_image(event.x, event.y)
        if pt:
            self._brush_points.append(pt)

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

        self._run_async(job)

    def _vectorize(self) -> None:
        img = self._active_image()
        if img is None:
            self._set_status("Open an image first.")
            return
        preset = self.preset_var.get()
        max_side = clamp_process_size(self.max_side.get())

        def job() -> None:
            def prog(stage: str, p: float) -> None:
                self.after(0, lambda: self._set_status(stage))
                self.after(0, lambda: self.progress.set(p))

            result = vectorize_image(
                img,
                VectorizeParams(
                    preset_id=preset,
                    max_process_size=max_side,
                    overrides={"max_process_size": max_side},
                ),
                on_progress=prog,
            )
            self._svg_text = result.svg

            def done() -> None:
                self.stats.configure(
                    text=(
                        f"paths: {result.path_count}  nodes~{result.node_estimate}\n"
                        f"working: {result.process_label}\n"
                        f"{result.duration_ms} ms · preset={preset}"
                    )
                )
                warn = f" | {result.warning}" if result.warning else ""
                self._set_status(f"Vectorized — Export SVG when ready{warn}")
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
