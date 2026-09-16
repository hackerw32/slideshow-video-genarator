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

        def add(text, cmd):
            ttk.Button(bar, text=text, command=cmd).pack(side='left', padx=2)

        add("Νέο", self.new_project)
        add("Άνοιγμα", self.load_project)
        add("Αποθήκευση", self.save_project)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=6)
        add("↶ Undo", self.undo)
        add("↷ Redo", self.redo)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=6)
        add("+ Εικόνα", self.add_images)
        add("+ Βίντεο", self.add_videos)
        add("Κείμενο", self.open_text_window)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=6)
        add("Preview", self.generate_preview)
        ttk.Button(bar, text="GENERATE VIDEO", command=self.export_video,
                   style='Accent.TButton').pack(side='right', padx=2)


    def setup_gui(self):
        self._build_toolbar()

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned = paned
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        # Left Panel: Library ONLY
        left = ttk.Frame(paned, width=1000)
        paned.add(left, weight=3)
        # Right Panel: Preview & ALL Controls
        right = ttk.Frame(paned, width=500)
        paned.add(right, weight=1)
        
        media_header = ttk.Frame(left)
        media_header.pack(fill='x', padx=10, pady=(10,5))
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
        ttk.Label(right, text="Preview (πρώτο καρέ)", font=("Calibri", 12, "bold")).pack(pady=(10,0))
        prev_frame = ttk.Frame(right)
        prev_frame.pack(pady=5)
        self.preview_photo_canvas = self._build_preview_canvas(prev_frame, "ΦΩΤΟΓΡΑΦΙΑ")
        self.preview_video_canvas = self._build_preview_canvas(prev_frame, "ΒΙΝΤΕΟ")
        ttk.Label(right, text="Κλικ σε preview = μεγέθυνση σε πραγματικό μέγεθος",
                  foreground="#666", font=("Calibri", 8)).pack(pady=(0, 5))
        ttk.Button(right, text="Generate Preview Frame", command=self.generate_preview).pack()

        # Controls Row 1
        name_frame = ttk.Frame(right)
        name_frame.pack(fill='x', padx=20, pady=15)
        ttk.Label(name_frame, text="Project Name & Controls:", font=("Calibri", 10, "bold")).pack(anchor='w')
        
        r1 = ttk.Frame(name_frame)
        r1.pack(fill='x', pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.name_var).pack(side='left', fill='x', expand=True)
        ttk.Button(r1, text="Text Input", command=self.open_text_window).pack(side='left', padx=2)
        ttk.Button(r1, text="+ Video", command=self.add_videos).pack(side='left', padx=2)
        ttk.Button(r1, text="+ Image", command=self.add_images).pack(side='left', padx=2)
        ttk.Button(r1, text="Clear", command=self.clear_media).pack(side='left', padx=2)
        ttk.Button(r1, text="Logo", command=self.show_project_watermark).pack(side='left', padx=2)

        # Controls Row 2
        o_f = ttk.Frame(right)
        o_f.pack(fill='x', padx=20, pady=15)
        ttk.Label(o_f, text="Output Folder:", font=("Calibri", 10, "bold")).pack(anchor='w')
        
        r2 = ttk.Frame(o_f)
        r2.pack(fill='x', pady=5)
        self.out_var = tk.StringVar(value=self.settings.get("output_folder", ""))
        ttk.Entry(r2, textvariable=self.out_var).pack(side='left', fill='x', expand=True)
        def browse_out():
            f = filedialog.askdirectory()
            if f:
                self.out_var.set(f)
        ttk.Button(r2, text="Browse", command=browse_out).pack(side='left', padx=2)
        ttk.Button(r2, text="GENERATE VIDEO", command=self.export_video, style='Accent.TButton').pack(side='left', padx=2)
        self.cancel_btn = ttk.Button(r2, text="Cancel Export", command=self.cancel_export, state='disabled')
        self.cancel_btn.pack(side='left', padx=2)
        
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(right, variable=self.progress_var, maximum=100).pack(fill='x', padx=20, pady=5)
        self.status = ttk.Label(right, text="Ready", relief='sunken')
        self.status.pack(side='bottom', fill='x')

        if TKDND_AVAILABLE:
            self.media_canvas.drop_target_register(DND_FILES)
            self.media_canvas.dnd_bind('<<Drop>>', lambda e: self.handle_drop(e.data))


    def _build_preview_canvas(self, parent, label):
        f = ttk.Frame(parent)
        f.pack(side='left', padx=4)
        ttk.Label(f, text=label, font=("Calibri", 9, "bold")).pack()
        c = tk.Canvas(f, bg='black', width=240, height=240, highlightthickness=1, highlightbackground='#888')
        c.pack()
        c.bind("<Button-1>", lambda e: self._show_preview_zoom(c))
        return c


    def _debounced_resize(self, event):
        if self._resize_timer is not None:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(200, lambda: self._on_canvas_resize(event.width))


    def _on_canvas_resize(self, width):
        self.media_canvas.itemconfig(self.canvas_window, width=width)
        if self.view_mode.get() == "thumbnails":
            self.update_media_display()

