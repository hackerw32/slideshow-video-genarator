"""Reusable brightness / saturation sliders with per-slider "apply to all".

The photo editor keeps its own inline copy; the video editor uses this class
so the two sliders and their checkboxes don't make ``ui_timeline`` any bigger.
``on_change`` fires on every move, so the host can redraw its preview.
"""

import tkinter as tk
from tkinter import ttk


class ColorControls:
    """Two sliders (brightness, saturation) + value labels + apply-to-all boxes.

    ``apply_brightness`` / ``apply_color`` are the checkboxes the host reads
    when saving; ``values()`` returns the rounded ``(brightness, color)``.
    """

    def __init__(self, parent, brightness=1.0, color=1.0, on_change=None,
                 all_label=None):
        self.on_change = on_change or (lambda *_: None)
        self.all_label = all_label
        self.brightness = tk.DoubleVar(value=float(brightness or 1.0))
        self.color = tk.DoubleVar(value=float(color or 1.0))
        self.apply_brightness = tk.BooleanVar(value=False)
        self.apply_color = tk.BooleanVar(value=False)

        box = ttk.LabelFrame(parent, text=" Φως & κορεσμός ", padding=8)
        self.frame = box

        self.b_lbl = self._row(box, 0, "Φωτεινότητα", self.brightness,
                               self.apply_brightness)
        self.c_lbl = self._row(box, 1, "Κορεσμός", self.color, self.apply_color)

        self.brightness.trace_add('write', self._update_labels)
        self.color.trace_add('write', self._update_labels)
        self._update_labels()

    def _row(self, box, row, label, var, apply_var):
        ttk.Label(box, text=label, width=13).grid(row=row, column=0, sticky='w')
        ttk.Scale(box, from_=0.2 if row == 0 else 0.0, to=2.0, variable=var,
                  length=240, command=self._changed).grid(row=row, column=1, padx=(4, 6))
        lbl = ttk.Label(box, width=7)
        lbl.grid(row=row, column=2, sticky='w')
        if self.all_label:
            ttk.Checkbutton(box, text=self.all_label, variable=apply_var).grid(
                row=row, column=3, padx=(12, 0), sticky='w')
        return lbl

    def values(self):
        return (round(self.brightness.get(), 4), round(self.color.get(), 4))

    def _changed(self, *_):
        self._update_labels()
        self.on_change()

    def _update_labels(self, *_):
        self.b_lbl.config(text=f"{self.brightness.get():.2f}x")
        self.c_lbl.config(text=f"{self.color.get():.2f}x")
