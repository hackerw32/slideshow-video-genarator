"""Shared entry point for the Edit dialogs, plus the crop overlay they share.

The dialogs themselves live in their own modules so each stays small:
``ui_photo_editor`` (crop / brightness / colour) and ``ui_timeline`` (the
filmstrip timeline with several cut points).
"""

import tkinter as tk
from tkinter import ttk


class EditorsMixin:
    """Dispatches to the photo / video Edit dialogs and draws the crop overlay."""

    def open_edit_dialog(self, idx):
        if not (0 <= idx < len(self.media_files)):
            return
        if self.media_files[idx][0] == "image":
            self._open_photo_editor(idx)
        else:
            self._open_video_editor(idx)


    def _setup_edit_dialog(self, dlg, on_fullscreen=None):
        """Add the "Πλήρης οθόνη" switch to a photo/video Edit dialog.

        The choice is saved in settings as ``edit_fullscreen``, so the next
        Edit dialog opens the same way. ``on_fullscreen(bool)`` lets the caller
        relayout its preview for the new size. F11 toggles, Escape leaves.
        """
        dlg.transient(self.root)
        dlg.grab_set()
        full_var = tk.BooleanVar(value=bool(self.settings.get("edit_fullscreen", False)))
        saved_geo = {}

        def apply():
            on = bool(full_var.get())
            try:
                if on:
                    saved_geo["geo"] = dlg.winfo_geometry()
                    dlg.attributes('-fullscreen', True)
                else:
                    dlg.attributes('-fullscreen', False)
                    if saved_geo.get("geo"):
                        dlg.geometry(saved_geo["geo"])
            except tk.TclError:
                pass
            if bool(self.settings.get("edit_fullscreen", False)) != on:
                self.settings["edit_fullscreen"] = on
                self.save_settings()
            if on_fullscreen:
                on_fullscreen(on)

        def set_full(on):
            full_var.set(on)
            apply()

        bar = ttk.Frame(dlg)
        bar.pack(fill='x', padx=10, pady=(8, 0))
        ttk.Checkbutton(bar, text="Πλήρης οθόνη (F11)", variable=full_var,
                        command=apply).pack(side='right')

        def toggle(_event=None):
            set_full(not full_var.get())
            return "break"

        def escape(_event=None):
            if full_var.get():
                set_full(False)
            return "break"

        dlg.bind("<F11>", toggle)
        dlg.bind("<Escape>", escape)

        def init():
            dlg.update_idletasks()
            if not full_var.get():
                w, h = dlg.winfo_width(), dlg.winfo_height()
                x = max(0, (dlg.winfo_screenwidth() - w) // 2)
                y = max(0, (dlg.winfo_screenheight() - h) // 3)
                dlg.geometry(f"+{x}+{y}")
            apply()

        dlg.after(0, init)
        return full_var


    def _draw_crop_overlay(self, canvas, crop, cw, ch, tag=None):
        """Dim everything outside ``crop`` (stipple, since a Tk canvas has no
        alpha) and outline the kept region, so you see exactly what you cut."""
        if not crop:
            return
        x0, y0 = int(crop[0] * cw), int(crop[1] * ch)
        x1, y1 = int(crop[2] * cw), int(crop[3] * ch)
        kw = {'tags': tag} if tag else {}
        for rx0, ry0, rx1, ry1 in ((0, 0, cw, y0), (0, y1, cw, ch),
                                   (0, y0, x0, y1), (x1, y0, cw, y1)):
            if rx1 > rx0 and ry1 > ry0:
                canvas.create_rectangle(rx0, ry0, rx1, ry1, fill='black',
                                        stipple='gray50', outline='', **kw)
        canvas.create_rectangle(x0, y0, x1, y1, outline='#ffcc00', width=2, **kw)
