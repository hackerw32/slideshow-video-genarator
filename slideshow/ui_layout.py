"""The main window layout (panels, library canvas, controls, preview canvases)."""

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


class LayoutMixin:
    """The main window layout (panels, library canvas, controls, preview canvases)."""

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=5, pady=(5, 0))
        ttk.Button(bar, text="↶ Undo", command=self.undo).pack(side='left', padx=2)
        ttk.Button(bar, text="↷ Redo", command=self.redo).pack(side='left', padx=2)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Button(bar, text="Text Input", command=self.open_text_window).pack(side='left', padx=2)


    def setup_gui(self):
        self._build_toolbar()

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned = paned
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        # Left Panel: project name + library
        left = ttk.Frame(paned, width=1000)
        paned.add(left, weight=1)
        # Right Panel: Preview & ALL Controls
        right = ttk.Frame(paned, width=500)
        paned.add(right, weight=1)

        name_frame = ttk.Frame(left)
        name_frame.pack(fill='x', padx=10, pady=(10, 2))
        ttk.Label(name_frame, text="Project Name:", font=("Calibri", 11, "bold")).pack(side='left')
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_var, font=("Calibri", 11))
        self.name_entry.pack(side='left', fill='x', expand=True, padx=(8, 0))

        media_header = ttk.Frame(left)
        media_header.pack(fill='x', padx=10, pady=(8,5))
        ttk.Label(media_header, text="Media Content Library", font=("Calibri", 12, "bold")).pack(side='left')
        ttk.Radiobutton(media_header, text="List", variable=self.view_mode, value="list", command=self.update_media_display).pack(side='right')
        ttk.Radiobutton(media_header, text="Icons", variable=self.view_mode, value="thumbnails", command=self.update_media_display).pack(side='right', padx=10)

        lib_container = ttk.Frame(left)
        lib_container.pack(fill='both', expand=True, padx=10, pady=5)
        self.media_canvas = tk.Canvas(lib_container, bg='#eee', highlightthickness=0)
        self.media_scrollbar = ttk.Scrollbar(lib_container, orient="vertical", command=self.media_canvas.yview)
        self.thumb_frame = ttk.Frame(self.media_canvas)
        self.canvas_window = self.media_canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")
        self.media_canvas.configure(yscrollcommand=self.media_scrollbar.set)
        
        self.media_canvas.pack(side='left', fill='both', expand=True)
        self.media_scrollbar.pack(side='right', fill='y')
        
        self.thumb_frame.bind("<Configure>", lambda e: self.media_canvas.configure(scrollregion=self.media_canvas.bbox("all")))
        self.media_canvas.bind("<Configure>", self._debounced_resize)
        self.media_canvas.bind_all("<MouseWheel>", lambda e: self.media_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # RIGHT PANEL
        # Bottom controls are packed first, so the preview gets all the rest.
        self.status = ttk.Label(right, text="Ready", relief='sunken')
        self.status.pack(side='bottom', fill='x')

        controls = ttk.Frame(right)
        controls.pack(side='bottom', fill='x', padx=10, pady=(0, 4))
        ttk.Button(controls, text="Generate Preview Frame",
                   command=self.generate_preview).pack(pady=(0, 8))

        ttk.Label(controls, text="Output Folder:", font=("Calibri", 10, "bold")).pack(anchor='w')
        r2 = ttk.Frame(controls)
        r2.pack(fill='x', pady=5)
        self.out_var = tk.StringVar(value=self.settings.get("output_folder", ""))
        ttk.Entry(r2, textvariable=self.out_var).pack(side='left', fill='x', expand=True)
        def browse_out():
            f = filedialog.askdirectory()
            if f:
                self.out_var.set(f)
        ttk.Button(r2, text="Browse", command=browse_out).pack(side='left', padx=2)
        ttk.Button(r2, text="GENERATE VIDEO", command=self.export_video,
                   style='Accent.TButton').pack(side='left', padx=2)
        self.cancel_btn = ttk.Button(r2, text="Cancel Export", command=self.cancel_export, state='disabled')
        self.cancel_btn.pack(side='left', padx=2)

        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(controls, variable=self.progress_var, maximum=100).pack(fill='x', pady=(4, 0))

        # Preview fills the rest of the panel, above the controls.
        ttk.Label(right, text="Preview (πρώτο καρέ)", font=("Calibri", 12, "bold")).pack(pady=(8, 0))
        prev_frame = ttk.Frame(right)
        prev_frame.pack(fill='both', expand=True, padx=6, pady=5)
        self.preview_photo_canvas = self._build_preview_canvas(prev_frame, "ΦΩΤΟΓΡΑΦΙΑ")
        self.preview_video_canvas = self._build_preview_canvas(prev_frame, "ΒΙΝΤΕΟ")
        ttk.Label(right, text="Κλικ σε preview = μεγέθυνση σε πραγματικό μέγεθος",
                  foreground="#666", font=("Calibri", 8)).pack(pady=(0, 5))

        if TKDND_AVAILABLE:
            self.media_canvas.drop_target_register(DND_FILES)
            self.media_canvas.dnd_bind('<<Drop>>', lambda e: self.handle_drop(e.data))


    def _build_preview_canvas(self, parent, label):
        f = ttk.Frame(parent)
        f.pack(side='left', padx=4, fill='both', expand=True)
        ttk.Label(f, text=label, font=("Calibri", 9, "bold")).pack()
        c = tk.Canvas(f, bg='black', width=180, height=180,
                      highlightthickness=1, highlightbackground='#888')
        c.pack(fill='both', expand=True)
        c.bind("<Button-1>", lambda e: self._show_preview_zoom(c))
        c.bind("<Configure>", lambda e: self._on_preview_configure(c), add="+")
        return c


    def _debounced_resize(self, event):
        if self._resize_timer is not None:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(200, lambda: self._on_canvas_resize(event.width))


    def _on_canvas_resize(self, width):
        self.media_canvas.itemconfig(self.canvas_window, width=width)
        if self.view_mode.get() == "thumbnails":
            self.update_media_display()

