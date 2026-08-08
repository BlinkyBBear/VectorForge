"""
VectorForge v1.0 UI — Simple (presets + few sliders) / Advanced (full control).

Zoom + pan · Binary mask preview · Silhouette mode for CNC cut-outs.
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
from vectorforge.engine.dxf_export import save_dxf
from vectorforge.engine.image_ops import load_image
from vectorforge.engine.memory import HARD_MAX_PROCESS_SIZE, clamp_process_size
from vectorforge.engine.presets import DEFAULT_PRESET_ID, PRESETS, preset_choices
from vectorforge.engine.svg_render import render_svg_preview
from vectorforge.engine.vectorize import VectorizeParams, vectorize_image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class VectorForgeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"VectorForge v{__version__} — CNC / Laser SVG")
        self.geometry("1480x940")
        self.minsize(1100, 720)

        self._source: Image.Image | None = None
        self._subject: Image.Image | None = None
        self._svg_text: str | None = None
        self._vector_preview: Image.Image | None = None
        self._binary_preview: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._busy = False
        self._brush_points: list[tuple[float, float]] = []
        self._source_path: Path | None = None

        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_start: tuple[int, int] | None = None
        self._panning = False

        self._view_mode = ctk.StringVar(value="source")
        self._ui_mode = ctk.StringVar(value="simple")  # simple | advanced

        self._build()
        self._apply_preset_to_controls(DEFAULT_PRESET_ID)
        self._update_mode_visibility()
        self._apply_ui_mode()
        self._set_status(rembg_status())

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkScrollableFrame(self, width=380, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        self._side = side

        ctk.CTkLabel(
            side, text="VectorForge", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(padx=12, pady=(14, 0), anchor="w")
        ctk.CTkLabel(
            side,
            text=f"v{__version__} · offline · CNC outline + laser SVG/DXF",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        ).pack(padx=12, pady=(0, 8), anchor="w")

        # Simple / Advanced toggle
        mode_row = ctk.CTkFrame(side, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(mode_row, text="UI:").pack(side="left")
        for val, lab in (("simple", "Simple"), ("advanced", "Advanced")):
            ctk.CTkRadioButton(
                mode_row,
                text=lab,
                variable=self._ui_mode,
                value=val,
                command=self._apply_ui_mode,
            ).pack(side="left", padx=8)

        ctk.CTkButton(side, text="Open image…", command=self._open_image).pack(
            fill="x", padx=12, pady=4
        )

        # ---- Always visible: preset + colour mode ----
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
            wraplength=340,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="gray65",
        )
        self.preset_desc.pack(fill="x", padx=12, pady=(2, 6))

        self._section(side, "Colour / output mode")
        self.color_mode = ctk.StringVar(value="outline")
        row = ctk.CTkFrame(side, fg_color="transparent")
        row.pack(fill="x", padx=10)
        for val, lab in (
            ("outline", "Outline-only"),
            ("bw", "Pure B&W"),
            ("centerline", "Centerline"),
            ("color", "Colour"),
        ):
            ctk.CTkRadioButton(
                row,
                text=lab,
                variable=self.color_mode,
                value=val,
                command=self._update_mode_visibility,
            ).pack(side="left", padx=2)

        # ---- Simple panel: few key sliders ----
        self._simple_frame = ctk.CTkFrame(side, fg_color="transparent")
        self._section(self._simple_frame, "Quick controls")
        self.s_denoise, _ = self._slider(self._simple_frame, "Denoise / clean", 0, 1, 0.45)
        self.s_turdsize, _ = self._slider(
            self._simple_frame, "Despeckle (turd size)", 0, 24, 14, int_mode=True
        )
        self.s_opttolerance, _ = self._slider(
            self._simple_frame, "Smooth curves", 0.05, 1.0, 0.60
        )
        self.s_silhouette = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self._simple_frame,
            text="Silhouette only (CNC cut-out, drop internal detail)",
            variable=self.s_silhouette,
        ).pack(anchor="w", padx=12, pady=6)
        self.s_sil_strength = ctk.StringVar(value="Normal")
        ctk.CTkLabel(
            self._simple_frame,
            text="Silhouette strength",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(2, 0))
        ctk.CTkOptionMenu(
            self._simple_frame,
            variable=self.s_sil_strength,
            values=["Soft", "Normal", "Aggressive"],
        ).pack(fill="x", padx=12, pady=2)

        # ---- Advanced panel ----
        self._advanced_frame = ctk.CTkFrame(side, fg_color="transparent")

        self._section(self._advanced_frame, "Raster prep")
        ctk.CTkLabel(
            self._advanced_frame,
            text="Tune until Binary mask shows solid clean shapes",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
        ).pack(anchor="w", padx=12)
        self.max_side, _ = self._slider(
            self._advanced_frame, "Max process size", 800, HARD_MAX_PROCESS_SIZE, 3600, int_mode=True
        )
        self.highpass_radius, _ = self._slider(
            self._advanced_frame, "Highpass radius (px)", 0, 12, 3.5
        )
        self.scale_factor, _ = self._slider(
            self._advanced_frame, "Scale factor (pre-threshold)", 1.0, 4.0, 2.0
        )
        self.edge_strength, _ = self._slider(self._advanced_frame, "Edge boost", 0, 1, 0.20)
        self.denoise, _ = self._slider(self._advanced_frame, "Denoise", 0, 1, 0.45)
        self.contrast, _ = self._slider(self._advanced_frame, "Contrast", 0, 1, 0.22)
        self.blacklevel, _ = self._slider(self._advanced_frame, "Black level", 0.05, 0.95, 0.50)
        self.threshold_method = ctk.StringVar(value="otsu")
        ctk.CTkLabel(self._advanced_frame, text="Threshold method", anchor="w").pack(
            fill="x", padx=12, pady=(4, 0)
        )
        ctk.CTkOptionMenu(
            self._advanced_frame,
            variable=self.threshold_method,
            values=["otsu", "fixed", "adaptive"],
        ).pack(fill="x", padx=12, pady=2)

        self._potrace_frame = ctk.CTkFrame(self._advanced_frame, fg_color="transparent")
        self._potrace_frame.pack(fill="x")
        self._section(self._potrace_frame, "Trace (Potrace)")
        self.turdsize, _ = self._slider(
            self._potrace_frame, "Turd size (despeckle)", 0, 24, 14, int_mode=True
        )
        self.alphamax, _ = self._slider(
            self._potrace_frame, "Corner threshold α", 0, 1.34, 0.65
        )
        self.opttolerance, _ = self._slider(
            self._potrace_frame, "Curve optimize", 0.05, 1.0, 0.60
        )
        self.stroke_width, _ = self._slider(
            self._potrace_frame, "Stroke width", 0.25, 4, 1.0
        )
        self.invert_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self._potrace_frame, text="Invert ink", variable=self.invert_var
        ).pack(anchor="w", padx=12, pady=2)
        self.outer_only_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self._potrace_frame,
            text="Outer + counters only",
            variable=self.outer_only_var,
        ).pack(anchor="w", padx=12, pady=2)
        self.silhouette_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self._potrace_frame,
            text="Silhouette mode (CNC cut-out, drop internal detail)",
            variable=self.silhouette_var,
        ).pack(anchor="w", padx=12, pady=2)
        self.sil_strength = ctk.StringVar(value="Normal")
        ctk.CTkLabel(
            self._potrace_frame,
            text="Silhouette strength",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(2, 0))
        ctk.CTkOptionMenu(
            self._potrace_frame,
            variable=self.sil_strength,
            values=["Soft", "Normal", "Aggressive"],
        ).pack(fill="x", padx=12, pady=2)

        self._centerline_frame = ctk.CTkFrame(self._advanced_frame, fg_color="transparent")
        self._section(self._centerline_frame, "Centerline / Skeleton")
        ctk.CTkLabel(
            self._centerline_frame,
            text="Thick strokes → single centre path (open strokes)",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
        ).pack(anchor="w", padx=12)
        self.min_branch_len, _ = self._slider(
            self._centerline_frame, "Min branch length (px)", 2, 40, 10, int_mode=True
        )
        self.spur_prune, _ = self._slider(
            self._centerline_frame, "Spur prune strength", 0, 1, 0.55
        )
        self.centerline_simplify, _ = self._slider(
            self._centerline_frame, "Path simplify", 0.05, 1.0, 0.40
        )

        self._vtracer_frame = ctk.CTkFrame(self._advanced_frame, fg_color="transparent")
        self._section(self._vtracer_frame, "Vtracer (colour only)")
        self.filter_speckle, _ = self._slider(
            self._vtracer_frame, "Filter speckle", 0, 20, 4, int_mode=True
        )
        self.color_precision, _ = self._slider(
            self._vtracer_frame, "Color precision", 1, 8, 6, int_mode=True
        )
        self.layer_difference, _ = self._slider(
            self._vtracer_frame, "Layer difference", 1, 32, 14, int_mode=True
        )
        self.corner_threshold, _ = self._slider(
            self._vtracer_frame, "Corner threshold °", 0, 180, 50, int_mode=True
        )
        self.path_precision, _ = self._slider(
            self._vtracer_frame, "Path precision", 1, 8, 3, int_mode=True
        )

        self._section(self._advanced_frame, "Background removal")
        self.bg_strength, _ = self._slider(self._advanced_frame, "BG strength", 0, 1, 0.55)
        self.tolerance, _ = self._slider(
            self._advanced_frame, "Wand tolerance", 8, 80, 36, int_mode=True
        )
        self.brush_radius, _ = self._slider(
            self._advanced_frame, "Brush radius", 4, 48, 14, int_mode=True
        )
        self.bg_tool = ctk.StringVar(value="erase")
        tools = ctk.CTkFrame(self._advanced_frame, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=4)
        for key, label in (("erase", "Erase"), ("restore", "Restore"), ("brush", "Brush−")):
            ctk.CTkRadioButton(
                tools, text=label, variable=self.bg_tool, value=key
            ).pack(side="left", padx=4)
        ctk.CTkButton(
            self._advanced_frame, text="Auto remove background", command=self._auto_bg
        ).pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkButton(
            self._advanced_frame, text="Reset subject", command=self._reset_subject, fg_color="gray30"
        ).pack(fill="x", padx=12, pady=4)

        # Shared action buttons (always visible)
        ctk.CTkButton(
            side,
            text="Vectorize",
            command=self._vectorize,
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(fill="x", padx=12, pady=(16, 4))

        exp = ctk.CTkFrame(side, fg_color="transparent")
        exp.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(exp, text="Export SVG…", command=self._export_svg).pack(
            side="left", expand=True, fill="x", padx=(0, 4)
        )
        ctk.CTkButton(exp, text="Export DXF…", command=self._export_dxf).pack(
            side="left", expand=True, fill="x", padx=(4, 0)
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
        self.progress.pack(fill="x", padx=12, pady=(0, 16))

        # Main view
        main = ctk.CTkFrame(self, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(main, fg_color="transparent", height=36)
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        ctk.CTkLabel(bar, text="Preview:").pack(side="left", padx=(4, 8))
        for val, lab in (
            ("source", "Original"),
            ("binary", "Binary mask"),
            ("vector", "Vector paths"),
            ("split", "Split"),
        ):
            ctk.CTkRadioButton(
                bar,
                text=lab,
                variable=self._view_mode,
                value=val,
                command=self._on_view_change,
            ).pack(side="left", padx=4)

        ctk.CTkButton(
            bar, text="Reset view", width=80, command=self._reset_view, fg_color="gray30"
        ).pack(side="right", padx=4)
        ctk.CTkLabel(
            bar, text="Wheel=zoom  Drag=pan", text_color="gray55", font=ctk.CTkFont(size=11)
        ).pack(side="right", padx=8)

        self.canvas = ctk.CTkCanvas(main, bg="#1a1a1c", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel_linux(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel_linux(e, -1))
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

        self.status = ctk.CTkLabel(
            main, text="Open a high-contrast logo / sign to begin", anchor="w", height=28
        )
        self.status.grid(row=2, column=0, sticky="ew", padx=8, pady=4)

        self.drop_hint = ctk.CTkLabel(
            self.canvas,
            text=(
                "Open image → choose preset → Vectorize\n"
                "Simple = few controls · Advanced = full raster + trace tuning\n"
                "Binary mask = what Potrace sees · Wheel zoom · Drag pan"
            ),
            font=ctk.CTkFont(size=14),
            text_color="gray60",
        )
        self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")

    def _apply_ui_mode(self) -> None:
        mode = self._ui_mode.get()
        if mode == "simple":
            self._advanced_frame.pack_forget()
            if not self._simple_frame.winfo_ismapped():
                self._simple_frame.pack(fill="x", after=self.preset_desc.master if False else self.preset_desc)
                # pack after colour mode row's parent is hard; just pack at end before vectorize
                self._simple_frame.pack(fill="x", padx=0)
        else:
            self._simple_frame.pack_forget()
            if not self._advanced_frame.winfo_ismapped():
                self._advanced_frame.pack(fill="x")
            self._update_mode_visibility()

    def _update_mode_visibility(self) -> None:
        if self._ui_mode.get() != "advanced":
            return
        cm = self.color_mode.get()
        # Vtracer only for colour
        if cm == "color":
            if not self._vtracer_frame.winfo_ismapped():
                self._vtracer_frame.pack(fill="x", after=self._potrace_frame)
        else:
            self._vtracer_frame.pack_forget()
        # Centerline controls
        if cm == "centerline":
            if not self._centerline_frame.winfo_ismapped():
                self._centerline_frame.pack(fill="x", after=self._potrace_frame)
        else:
            self._centerline_frame.pack_forget()
        # Potrace silhouette less relevant for centerline but keep frame

    def _section(self, parent, title: str) -> None:
        ctk.CTkLabel(
            parent,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="x", padx=12, pady=(12, 2))

    def _slider(
        self,
        parent,
        label: str,
        lo: float,
        hi: float,
        default: float,
        *,
        int_mode: bool = False,
    ) -> tuple[ctk.CTkSlider, ctk.CTkLabel]:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(row, text=label, anchor="w", font=ctk.CTkFont(size=11)).pack(
            side="left"
        )
        val_lbl = ctk.CTkLabel(
            row,
            text=str(int(default) if int_mode else f"{default:.2f}"),
            width=56,
            anchor="e",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        )
        val_lbl.pack(side="right")
        steps = max(1, int(hi - lo) if int_mode else 100)
        s = ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=steps)
        s.set(default)

        def on_change(v: float, lbl=val_lbl, im=int_mode) -> None:
            lbl.configure(text=str(int(round(v))) if im else f"{float(v):.2f}")

        s.configure(command=on_change)
        s.pack(fill="x", padx=12, pady=(0, 2))
        return s, val_lbl

    def _on_preset_label(self, label: str) -> None:
        key = label.split(" — ", 1)[0].strip()
        if key in PRESETS:
            self.preset_var.set(key)
            self.preset_desc.configure(text=PRESETS[key]["description"])
            self._apply_preset_to_controls(key)
            self._update_mode_visibility()

    def _apply_preset_to_controls(self, key: str) -> None:
        p = PRESETS[key]["params"]
        # simple
        self.s_denoise.set(p.get("denoise", 0.45))
        self.s_turdsize.set(p.get("turdsize", 14))
        self.s_opttolerance.set(p.get("opttolerance", 0.60))
        # advanced
        self.max_side.set(p.get("max_process_size", 3600))
        self.highpass_radius.set(float(p.get("highpass_radius", 3.5)))
        self.scale_factor.set(max(1.0, float(p.get("scale_factor", 2.0) or 2.0)))
        self.edge_strength.set(p.get("edge_strength", 0.20))
        self.denoise.set(p.get("denoise", 0.45))
        self.contrast.set(p.get("contrast", 0.22))
        self.blacklevel.set(p.get("blacklevel", 0.5))
        self.threshold_method.set(p.get("threshold_method", "otsu"))
        self.turdsize.set(p.get("turdsize", 14))
        self.alphamax.set(p.get("alphamax", 0.65))
        self.opttolerance.set(p.get("opttolerance", 0.60))
        self.stroke_width.set(p.get("stroke_width", 1.0))
        if hasattr(self, "min_branch_len"):
            self.min_branch_len.set(p.get("min_branch_len", 10))
            self.spur_prune.set(p.get("spur_prune", 0.55))
            self.centerline_simplify.set(p.get("centerline_simplify", 0.4))
        self.filter_speckle.set(p.get("filter_speckle", 4))
        self.color_precision.set(p.get("color_precision", 6))
        self.layer_difference.set(p.get("layer_difference", 14))
        self.corner_threshold.set(p.get("corner_threshold", 50))
        self.path_precision.set(p.get("path_precision", 3))
        self.invert_var.set(bool(p.get("invert", False)))
        cm = str(p.get("color_mode", "outline"))
        if cm in ("outline", "bw", "color", "centerline"):
            self.color_mode.set(cm)
        elif p.get("output_style") == "outline":
            self.color_mode.set("outline")
        elif p.get("engine") == "vtracer":
            self.color_mode.set("color")
        else:
            self.color_mode.set("bw")
        for s in (
            self.s_denoise,
            self.s_turdsize,
            self.s_opttolerance,
            self.max_side,
            self.highpass_radius,
            self.scale_factor,
            self.edge_strength,
            self.denoise,
            self.contrast,
            self.blacklevel,
            self.turdsize,
            self.alphamax,
            self.opttolerance,
            self.stroke_width,
            self.filter_speckle,
            self.color_precision,
            self.layer_difference,
            self.corner_threshold,
            self.path_precision,
        ):
            cmd = s.cget("command")
            if callable(cmd):
                cmd(s.get())

    def _collect_overrides(self) -> dict[str, Any]:
        cm = self.color_mode.get()
        simple = self._ui_mode.get() == "simple"

        if simple:
            o: dict[str, Any] = {
                "denoise": float(self.s_denoise.get()),
                "turdsize": int(round(self.s_turdsize.get())),
                "opttolerance": float(self.s_opttolerance.get()),
                "silhouette": bool(self.s_silhouette.get()),
                "silhouette_strength": self.s_sil_strength.get().lower(),
                "outer_and_counters_only": True,
                "logo_text": True,
                "color_mode": cm,
                "edge_strength": 0.20,
                "highpass_radius": 3.5,
                "scale_factor": 0.0,
                "auto_scale": True,
                "contrast": 0.22,
                "blacklevel": 0.50,
                "threshold_method": "otsu",
                "alphamax": 0.65,
                "stroke_width": 1.0,
                "invert": False,
                "max_process_size": 3600,
            }
        else:
            o = {
                "max_process_size": clamp_process_size(self.max_side.get()),
                "highpass_radius": float(self.highpass_radius.get()),
                "scale_factor": float(self.scale_factor.get()),
                "auto_scale": False,
                "edge_strength": float(self.edge_strength.get()),
                "denoise": float(self.denoise.get()),
                "contrast": float(self.contrast.get()),
                "blacklevel": float(self.blacklevel.get()),
                "threshold_method": self.threshold_method.get(),
                "turdsize": int(round(self.turdsize.get())),
                "alphamax": float(self.alphamax.get()),
                "opttolerance": float(self.opttolerance.get()),
                "stroke_width": float(self.stroke_width.get()),
                "filter_speckle": int(round(self.filter_speckle.get())),
                "color_precision": int(round(self.color_precision.get())),
                "layer_difference": int(round(self.layer_difference.get())),
                "corner_threshold": int(round(self.corner_threshold.get())),
                "path_precision": int(round(self.path_precision.get())),
                "invert": bool(self.invert_var.get()),
                "outer_and_counters_only": bool(self.outer_only_var.get()),
                "silhouette": bool(self.silhouette_var.get()),
                "silhouette_strength": self.sil_strength.get().lower(),
                "logo_text": True,
                "color_mode": cm,
            }

        if cm == "outline":
            o["engine"] = "potrace"
            o["output_style"] = "outline"
        elif cm == "bw":
            o["engine"] = "potrace"
            o["output_style"] = "fill"
        elif cm == "centerline":
            o["engine"] = "centerline"
            o["output_style"] = "centerline"
            o["logo_text"] = False
            if not simple:
                o["min_branch_len"] = int(round(self.min_branch_len.get()))
                o["spur_prune"] = float(self.spur_prune.get())
                o["centerline_simplify"] = float(self.centerline_simplify.get())
            else:
                o["min_branch_len"] = 10
                o["spur_prune"] = 0.55
                o["centerline_simplify"] = 0.40
        else:
            o["engine"] = "vtracer"
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
            err = None
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

    def _reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._redraw()

    def _on_view_change(self) -> None:
        self._reset_view()

    def _on_wheel(self, event) -> None:
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._zoom = float(max(0.1, min(20.0, self._zoom * factor)))
        self._redraw()

    def _on_wheel_linux(self, event, direction: int) -> None:
        factor = 1.15 if direction > 0 else 1 / 1.15
        self._zoom = float(max(0.1, min(20.0, self._zoom * factor)))
        self._redraw()

    def _redraw(self) -> None:
        mode = self._view_mode.get()
        if mode == "vector" and self._vector_preview is not None:
            self._show_zoomable(self._vector_preview, label="VECTOR PATHS")
            return
        if mode == "binary" and self._binary_preview is not None:
            self._show_zoomable(self._binary_preview, label="BINARY MASK (what Potrace traces)")
            return
        if mode == "split" and self._vector_preview is not None and self._active_image():
            self._show_split(self._active_image(), self._vector_preview)
            return
        img = self._active_image()
        if img is not None:
            self._show_zoomable(
                img,
                brush_overlay=self._brush_points if self.bg_tool.get() == "brush" else None,
            )

    def _show_zoomable(
        self,
        img: Image.Image,
        *,
        label: str | None = None,
        brush_overlay: list[tuple[float, float]] | None = None,
    ) -> None:
        self.drop_hint.place_forget()
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())

        w, h = img.size
        fit = min(cw / w, ch / h, 1.0) * 0.92
        scale = fit * self._zoom
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))

        preview = img.resize(
            (dw, dh),
            Image.Resampling.NEAREST if scale > 2 else Image.Resampling.BILINEAR,
        )
        if preview.mode == "RGBA":
            bg = Image.new("RGBA", preview.size, (40, 40, 44, 255))
            preview = Image.alpha_composite(bg, preview).convert("RGB")
        else:
            preview = preview.convert("RGB")

        if brush_overlay:
            draw = ImageDraw.Draw(preview, "RGBA")
            r = max(1, int(round(self.brush_radius.get() * scale)))
            for x, y in brush_overlay:
                cx, cy = int(x * scale), int(y * scale)
                draw.ellipse(
                    (cx - r, cy - r, cx + r, cy + r),
                    fill=(255, 60, 60, 90),
                    outline=(255, 80, 80, 180),
                )

        self._photo = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        cx = cw / 2 + self._pan_x
        cy = ch / 2 + self._pan_y
        self.canvas.create_image(cx, cy, image=self._photo, anchor="center")
        if label:
            self.canvas.create_text(
                12, 12, anchor="nw", fill="#8cf0a0", text=f"{label}  ·  zoom {self._zoom:.2f}×"
            )

    def _show_split(self, left: Image.Image, right: Image.Image) -> None:
        self.drop_hint.place_forget()
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        half = cw // 2 - 8

        def fit(im: Image.Image) -> Image.Image:
            w, h = im.size
            sc = min(half / w, ch / h, 1.0) * 0.92 * self._zoom
            return im.resize(
                (max(1, int(w * sc)), max(1, int(h * sc))),
                Image.Resampling.NEAREST if sc > 2 else Image.Resampling.BILINEAR,
            ).convert("RGB")

        L, R = fit(left), fit(right)
        canvas_img = Image.new("RGB", (cw, ch), (26, 26, 28))
        ox = int(self._pan_x)
        oy = int(self._pan_y)
        canvas_img.paste(L, (8 + ox, (ch - L.height) // 2 + oy))
        canvas_img.paste(R, (half + 12 + ox, (ch - R.height) // 2 + oy))
        draw = ImageDraw.Draw(canvas_img)
        draw.line([(half + 4, 0), (half + 4, ch)], fill=(80, 80, 90), width=2)
        self._photo = ImageTk.PhotoImage(canvas_img)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")

    def _on_canvas_press(self, event) -> None:
        mode = self._view_mode.get()
        if mode != "source" or self.bg_tool.get() != "brush":
            self._panning = True
            self._drag_start = (event.x, event.y)
            return
        if self._busy or self._active_image() is None:
            return
        img = self._active_image()
        if img is None:
            return
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        w, h = img.size
        fit = min(cw / w, ch / h, 1.0) * 0.92
        scale = fit * self._zoom
        cx = cw / 2 + self._pan_x
        cy = ch / 2 + self._pan_y
        px = (event.x - cx) / scale + w / 2
        py = (event.y - cy) / scale + h / 2
        if not (0 <= px < w and 0 <= py < h):
            return
        if self.bg_tool.get() == "brush":
            self._brush_points = [(px, py)]
            self._redraw()
            return
        erase = self.bg_tool.get() != "restore"

        def job() -> None:
            base = self._active_image()
            assert base is not None
            out = wand_at(
                base, px, py, erase=erase,
                tolerance=int(round(self.tolerance.get())),
            )
            self._subject = out
            self.after(0, self._redraw)

        self._run_async(job)

    def _on_canvas_drag(self, event) -> None:
        if self._panning and self._drag_start is not None:
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._pan_x += dx
            self._pan_y += dy
            self._drag_start = (event.x, event.y)
            self._redraw()
            return
        if self.bg_tool.get() != "brush" or self._busy or self._view_mode.get() != "source":
            return
        img = self._active_image()
        if img is None:
            return
        self.canvas.update_idletasks()
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        w, h = img.size
        fit = min(cw / w, ch / h, 1.0) * 0.92
        scale = fit * self._zoom
        cx = cw / 2 + self._pan_x
        cy = ch / 2 + self._pan_y
        px = (event.x - cx) / scale + w / 2
        py = (event.y - cy) / scale + h / 2
        if 0 <= px < w and 0 <= py < h:
            self._brush_points.append((px, py))
            if len(self._brush_points) % 2 == 0:
                self._redraw()

    def _on_canvas_release(self, event) -> None:
        if self._panning:
            self._panning = False
            self._drag_start = None
            return
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
            self.after(0, self._redraw)

        self._run_async(job)

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
        self._vector_preview = None
        self._binary_preview = None
        self._brush_points = []
        self._view_mode.set("source")
        self._reset_view()
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
            self.after(0, lambda: self._view_mode.set("source"))
            self.after(0, self._redraw)
            self.after(0, lambda: self._set_status(f"Subject ready (strength={strength:.2f})"))

        self._run_async(job)

    def _reset_subject(self) -> None:
        self._subject = None
        self._brush_points = []
        self._view_mode.set("source")
        self._redraw()
        self._set_status("Subject reset")

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
                    max_process_size=overrides.get("max_process_size", 3600),
                    overrides=overrides,
                ),
                on_progress=prog,
            )
            self._svg_text = result.svg
            vp = render_svg_preview(result.svg, max_side=1400)
            bp = result.preview_png

            def done() -> None:
                self._vector_preview = vp
                self._binary_preview = bp
                # Binary mask reflects highpass/scale; switch to Vector paths as needed
                self._view_mode.set("binary" if bp is not None else "vector")
                self._reset_view()
                tip = getattr(result, "quality_tip", "") or ""
                hp = result.params.get("highpass_radius", "?")
                sf = result.params.get("scale_factor", "?")
                self.stats.configure(
                    text=(
                        f"paths: {result.path_count}  nodes~{result.node_estimate}\n"
                        f"engine: {result.engine}  {result.process_label}\n"
                        f"hp={hp} scale={sf}\n"
                        f"{tip}\n"
                        f"{result.duration_ms} ms · {preset}"
                    )
                )
                self._set_status(tip or "Done — check Binary mask if letters look wrong")
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
        self._set_status(f"Saved SVG {path}")

    def _export_dxf(self) -> None:
        if not self._svg_text:
            self._set_status("Vectorize first, then export.")
            return
        from tkinter import filedialog

        default = "vectorforge.dxf"
        if self._source_path:
            default = self._source_path.with_suffix(".dxf").name
        path = filedialog.asksaveasfilename(
            title="Export DXF",
            defaultextension=".dxf",
            initialfile=default,
            filetypes=[("DXF", "*.dxf")],
        )
        if not path:
            return
        save_dxf(self._svg_text, path)
        self._set_status(f"Saved DXF {path}")


def run_app() -> None:
    app = VectorForgeApp()
    app.mainloop()
