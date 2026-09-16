"""The photo Edit dialog: two tabs - crop/brightness/colour, and erasing."""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from .deps import Image, ImageTk, ImageEnhance
from .ui_erase import ErasePanel


class PhotoEditorMixin:
    """The photo Edit dialog: crop / brightness / colour, plus the erase tool."""

    def _open_photo_editor(self, idx):
        _, path, edit = self.media_files[idx]
        try:
            src = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Edit", f"Δεν μπόρεσα να ανοίξω τη φωτογραφία:\n{e}")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit φωτογραφίας — {Path(path).name}")
        self._setup_edit_dialog(dlg, on_fullscreen=lambda full: recompute_preview(full))

        nb = ttk.Notebook(dlg)
        nb.pack(fill='both', expand=True, padx=10, pady=(10, 0))
        tab_crop = ttk.Frame(nb)
        tab_erase = ttk.Frame(nb)
        nb.add(tab_crop, text="  ✂  Crop & Φως  ")
        nb.add(tab_erase, text="  🧽  Σβήσιμο  ")

        # ============================ tab 1: crop / brightness / colour
        prev_src = src.copy()
        prev_src.thumbnail((840, 690))   # 50% bigger than the old 560x460
        pw, ph = prev_src.size
        state = {"crop": list(edit["crop"]) if edit.get("crop") else None, "drag": None}

        brightness_var = tk.DoubleVar(value=float(edit.get("brightness", 1.0) or 1.0))
        color_var = tk.DoubleVar(value=float(edit.get("color", 1.0) or 1.0))

        ttk.Label(tab_crop, text="Σύρε το ποντίκι πάνω στην εικόνα για crop. Η προεπισκόπηση "
                                 "δείχνει αμέσως φωτεινότητα και χρώμα.",
                  foreground="#555").pack(padx=12, pady=(10, 0), anchor='w')

        canvas = tk.Canvas(tab_crop, width=pw, height=ph, bg='black', cursor='crosshair',
                           highlightthickness=1, highlightbackground='#888')
        canvas.pack(padx=12, pady=8)

        def render_image():
            canvas.delete('base')
            img = prev_src
            b, c = brightness_var.get(), color_var.get()
            if abs(b - 1.0) > 1e-3:
                img = ImageEnhance.Brightness(img).enhance(b)
            if abs(c - 1.0) > 1e-3:
                img = ImageEnhance.Color(img).enhance(c)
            tk_img = ImageTk.PhotoImage(img)
            canvas.create_image(0, 0, image=tk_img, anchor='nw', tags='base')
            canvas.img_ref = tk_img
            canvas.tag_raise('ovl')

        def render_overlay():
            canvas.delete('ovl')
            self._draw_crop_overlay(canvas, state["crop"], pw, ph, tag='ovl')
            update_size_lbl()

        def render_all():
            render_image()
            render_overlay()

        def preview_max(full):
            if full:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                return max(1, int(sw * 0.80)), max(1, int(sh * 0.72))
            return 840, 690

        def recompute_preview(full):
            """Re-fit the preview to the window size (normal 1.5x, or fullscreen)."""
            nonlocal prev_src, pw, ph
            p = src.copy()
            p.thumbnail(preview_max(full))
            prev_src = p
            pw, ph = p.size
            canvas.config(width=pw, height=ph)
            render_all()

        def on_press(e):
            state["drag"] = (min(max(e.x, 0), pw), min(max(e.y, 0), ph))
            state["crop"] = None
            render_overlay()

        def on_move(e):
            if not state["drag"]:
                return
            x0, y0 = state["drag"]
            x1, y1 = min(max(e.x, 0), pw), min(max(e.y, 0), ph)
            if x1 < x0:
                x0, x1 = x1, x0
            if y1 < y0:
                y0, y1 = y1, y0
            if (x1 - x0) >= 5 and (y1 - y0) >= 5:
                state["crop"] = [x0 / pw, y0 / ph, x1 / pw, y1 / ph]
            else:
                state["crop"] = None
            render_overlay()

        def on_release(e):
            state["drag"] = None
            render_overlay()

        size_lbl = ttk.Label(tab_crop, text="", foreground="#555")
        size_lbl.pack(padx=12, anchor='w')

        def update_size_lbl():
            crop = state["crop"]
            if crop:
                w = int(round((crop[2] - crop[0]) * src.width))
                h = int(round((crop[3] - crop[1]) * src.height))
                size_lbl.config(text=f"Crop: {w} x {h} px  (από {src.width} x {src.height})")
            else:
                size_lbl.config(text=f"Χωρίς crop — {src.width} x {src.height} px")

        sl = ttk.Frame(tab_crop)
        sl.pack(fill='x', padx=14, pady=(6, 2))
        ttk.Label(sl, text="Φωτεινότητα", width=16).grid(row=0, column=0, sticky='w')
        ttk.Scale(sl, from_=0.2, to=2.0, variable=brightness_var, length=330,
                  command=lambda *a: render_image()).grid(row=0, column=1)
        b_lbl = ttk.Label(sl, width=7)
        b_lbl.grid(row=0, column=2)
        ttk.Label(sl, text="Χρώμα (κορεσμός)", width=16).grid(row=1, column=0, sticky='w')
        ttk.Scale(sl, from_=0.0, to=2.0, variable=color_var, length=330,
                  command=lambda *a: render_image()).grid(row=1, column=1)
        c_lbl = ttk.Label(sl, width=7)
        c_lbl.grid(row=1, column=2)

        def update_vals(*_):
            b_lbl.config(text=f"{brightness_var.get():.2f}x")
            c_lbl.config(text=f"{color_var.get():.2f}x")

        brightness_var.trace_add('write', update_vals)
        color_var.trace_add('write', update_vals)
        update_vals()

        # Two separate "apply to all" switches: the crop ratio and the
        # brightness/colour are independent decisions.
        apply_crop_var = tk.BooleanVar(value=False)
        apply_colour_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab_crop, text="Ίδιο crop σε όλες τις φωτογραφίες",
                        variable=apply_crop_var).pack(padx=14, pady=(8, 0), anchor='w')
        ttk.Checkbutton(tab_crop, text="Ίδια φωτεινότητα / χρώμα σε όλες τις φωτογραφίες",
                        variable=apply_colour_var).pack(padx=14, pady=(2, 0), anchor='w')

        row_crop = ttk.Frame(tab_crop)
        row_crop.pack(pady=(8, 10))

        def clear_crop():
            state["crop"] = None
            render_overlay()

        def reset_tab1():
            brightness_var.set(1.0)
            color_var.set(1.0)
            state["crop"] = None
            render_all()

        ttk.Button(row_crop, text="Καθαρισμός crop", command=clear_crop).pack(side='left', padx=4)
        ttk.Button(row_crop, text="Επαναφορά crop & φωτός",
                   command=reset_tab1).pack(side='left', padx=4)

        canvas.bind("<Button-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)
        render_all()

        # ============================ tab 2: erase
        panel = ErasePanel(self, tab_erase, edit, src, path)

        # ============================ shared buttons
        btns = ttk.Frame(dlg)
        btns.pack(fill='x', padx=12, pady=10)

        def apply_and_close():
            target = self.media_files[idx][2]
            target["crop"] = list(state["crop"]) if state["crop"] else None
            target["brightness"] = round(brightness_var.get(), 4)
            target["color"] = round(color_var.get(), 4)
            strokes = panel.get_strokes()
            target["erase"] = strokes or None
            if apply_crop_var.get():
                for item in self.media_files:
                    if item[0] == "image":
                        item[2]["crop"] = list(target["crop"]) if target["crop"] else None
            if apply_colour_var.get():
                for item in self.media_files:
                    if item[0] == "image":
                        item[2]["brightness"] = target["brightness"]
                        item[2]["color"] = target["color"]
            self.is_modified = True
            self.update_media_display()
            dlg.destroy()

        ttk.Button(btns, text="Άκυρο", command=dlg.destroy).pack(side='right', padx=4)
        ttk.Button(btns, text="Εφαρμογή", command=apply_and_close).pack(side='right')
