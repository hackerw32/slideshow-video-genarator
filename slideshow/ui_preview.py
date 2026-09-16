"""Rendering and showing the photo/video preview frames."""

import io
import json
import os
import random
import re
import subprocess
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)


class PreviewMixin:
    """Rendering and showing the photo/video preview frames."""

    def generate_preview(self):
        if not self.media_files:
            messagebox.showinfo("Preview", "Πρόσθεσε πρώτα φωτογραφίες ή βίντεο στο project.")
            return
        threading.Thread(target=self._preview_task, daemon=True).start()


    def _schedule_preview(self, delay=700):
        """Refresh the preview automatically (debounced) after any change."""
        if self._preview_job:
            try:
                self.root.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.root.after(delay, self._auto_preview)


    def _auto_preview(self):
        self._preview_job = None
        if self.media_files:
            self.generate_preview()


    def _preview_task(self):
        try:
            res = self.settings["resolution"].split('x')
            w, h = int(res[0]), int(res[1])
            photo_item = next((it for it in self.media_files if it[0] == "image"), None)
            video_item = next((it for it in self.media_files if it[0] == "video"), None)
            if photo_item is None and video_item is None:
                self.root.after(0, lambda: messagebox.showinfo("Preview", "Δεν υπάρχουν media για preview."))
                return

            if photo_item is not None:
                self._render_preview(photo_item[1], "image", w, h, self.preview_photo_canvas, photo_item[2])
            else:
                self.root.after(0, lambda: self._clear_preview(self.preview_photo_canvas))
            if video_item is not None:
                # For a trimmed video the export starts at trim_start, so preview that frame.
                t_start = float(video_item[2].get("trim_start") or 0.0)
                self._render_preview(video_item[1], "video", w, h, self.preview_video_canvas,
                                     video_item[2], t_start)
            else:
                self.root.after(0, lambda: self._clear_preview(self.preview_video_canvas))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))


    @staticmethod
    def _wm_xy(position, width, height, w, h, margin=10):
        return {
            "top_left": (margin, margin),
            "top_right": (width - w - margin, margin),
            "bottom_left": (margin, height - h - margin),
            "bottom_right": (width - w - margin, height - h - margin),
            "center": ((width - w) // 2, (height - h) // 2),
        }.get(position, (width - w - margin, height - h - margin))

    def _apply_watermark_overlay(self, frame):
        """Composite the logo and/or text watermark like the export does."""
        img_wm = self._effective_image_watermark()
        txt_wm = self._effective_text_watermark()
        width, height = frame.size
        base = frame.convert("RGBA")

        if img_wm and Path(img_wm["path"]).exists():
            try:
                logo = Image.open(img_wm["path"]).convert("RGBA")
            except Exception:
                logo = None
            if logo is not None:
                wm_w = max(1, int(width * img_wm["size_pct"] / 100))
                wm_h = max(1, round(logo.height * wm_w / logo.width))
                logo = logo.resize((wm_w, wm_h), Image.Resampling.LANCZOS)
                alpha = max(0.0, min(1.0, float(img_wm["opacity"]) / 100.0))
                if alpha < 1.0:
                    logo.putalpha(logo.getchannel("A").point(lambda v: int(v * alpha)))
                base.alpha_composite(
                    logo, self._wm_xy(img_wm["position"], width, height, wm_w, wm_h))

        if txt_wm:
            font_size = max(8, int(height * txt_wm["size_pct"] / 100))
            timg = self._watermark_text_image(txt_wm["text"], txt_wm["color"], font_size,
                                              txt_wm["opacity"] / 100.0)
            base.alpha_composite(
                timg, self._wm_xy(txt_wm["position"], width, height, timg.width, timg.height))

        return base.convert(frame.mode)

    def _clear_preview(self, canvas):
        canvas.delete("all")
        if hasattr(canvas, 'full_image'):
            del canvas.full_image


    def _render_preview(self, path, m_type, w, h, canvas, edit=None, t_start=0.0):
        """Render the first frame of the export for this media type (full
        resolution), then downscale only for display. For fit_and_move the
        export picks a random pan direction, so this shows the pan start -
        the text layout is identical for every pan position."""
        edit = edit or {}
        if m_type == "image":
            img = Image.open(path)
            img = self._apply_image_edit(img, edit, path, m_type="image")
            frame = self._fit_image_logic(img, w, h, "image")
            fit_move_data = getattr(frame, 'fit_move_data', None)
            if fit_move_data is not None:
                # Actual first frame of the pan animation (t=0), not the middle.
                overlay = self._make_text_overlay(self.get_text_for("image"), w, h)
                frame = self._render_fit_and_move_frame(frame, fit_move_data, 0.0, w, h, overlay)
            else:
                frame = self.render_text_on_image(frame, self.get_text_for("image"), w, h)
        else:
            if t_start > 0.005:
                raw = self._video_frame_at(path, t_start)
            else:
                raw = self._video_first_frame(path)
            first = self._apply_image_edit(raw, edit, m_type="video")  # apply the video crop
            frame = self._render_video_first_frame(first, w, h)
            frame = self.render_text_on_image(frame, self.get_text_for("video"), w, h)

        frame = self._apply_watermark_overlay(frame)
        full = frame.copy()
        cw, ch = self._preview_canvas_size(w, h)
        disp = frame.resize((cw, ch), Image.Resampling.LANCZOS)
        # Pass the PIL image through after(); PhotoImage must be built in the
        # main thread, not in this worker thread.
        self.root.after(0, lambda: self._show_preview(canvas, disp, full, cw, ch))


    def _show_preview(self, canvas, disp, full, cw, ch):
        canvas.config(width=cw, height=ch)
        canvas.delete("all")
        tk_p = ImageTk.PhotoImage(disp)
        canvas.create_image(cw // 2, ch // 2, image=tk_p)
        canvas.img = tk_p          # keep a reference so the image isn't garbage-collected
        canvas.full_image = full   # kept for the click-to-zoom view


    def _show_preview_zoom(self, canvas):
        """Open the full-resolution first frame in a scrollable window."""
        full = getattr(canvas, 'full_image', None)
        if full is None:
            return
        top = tk.Toplevel(self.root)
        top.title("Προεπισκόπηση - πραγματικό μέγεθος")
        top.transient(self.root)
        c = tk.Canvas(top, bg='black', highlightthickness=0)
        sb_y = ttk.Scrollbar(top, orient='vertical', command=c.yview)
        sb_x = ttk.Scrollbar(top, orient='horizontal', command=c.xview)
        c.configure(xscrollcommand=sb_x.set, yscrollcommand=sb_y.set)
        c.grid(row=0, column=0, sticky='nsew')
        sb_y.grid(row=0, column=1, sticky='ns')
        sb_x.grid(row=1, column=0, sticky='ew')
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        tk_p = ImageTk.PhotoImage(full)
        c.create_image(0, 0, image=tk_p, anchor='nw')
        c.config(scrollregion=c.bbox('all'), width=min(full.width, 900), height=min(full.height, 700))
        c.img = tk_p  # keep a reference

