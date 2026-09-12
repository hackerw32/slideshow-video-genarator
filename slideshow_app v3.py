import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
import threading
from datetime import datetime
import re
import subprocess
import random
import traceback
import io

try:
    from PIL import Image, ImageTk, ImageFilter, ImageDraw, ImageFont
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.Resampling.LANCZOS

    from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
    import numpy as np
except ImportError as e:
    print(f"Missing dependencies: {e}")
    exit(1)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False


class SlideshowApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Slideshow Video Creator Pro")
        self.root.geometry("1550x950")

        self.app_dir = Path(__file__).parent
        self.projects_dir = self.app_dir / "projects"
        self.settings_file = self.app_dir / "settings.json"
        self.music_tracker_file = self.app_dir / "music_tracker.json"
        self.temp_dir = self.app_dir / "temp"

        self.projects_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)

        self.current_project = None
        self.media_files = []
        self.is_modified = False
        self.thumbnails = []
        self.view_mode = tk.StringVar(value="thumbnails")
        self.project_text_videos = ""
        self.project_text_photos = ""
        self._resize_timer = None
        self._video_frame_cache = {}  # first-frame per video path (rotation-corrected)
        self.project_watermark = {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        }

        self.load_settings()
        self.load_music_tracker()
        self.setup_menu()
        self.setup_gui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_settings(self):
        default_settings = {
            "volume_db": 0, "resolution": "1080x1080", "background_mode": "blur",
            "cropping": False, "font_size": 32, "font_family": "Calibri",
            "text_style": "black_box", "auto_position_photos": False,
            "auto_position_videos": False, "mute_video_audio": True,
            "output_folder": str(self.app_dir), "slide_duration": 3,
            "music_folder": str(self.app_dir / "music"), "crossfade_duration": 3, "trim_silence": True,
            "transition_effect": "fade", "transition_duration": 0.7, "random_transitions": [],
            "watermark_enabled": False, "watermark_path": "", "watermark_position": "bottom_right",
            "watermark_size_pct": 15, "watermark_opacity": 80
        }
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings = {**default_settings, **json.load(f)}
            except:
                self.settings = default_settings
        else:
            self.settings = default_settings
            self.save_settings()
        os.makedirs(self.settings["music_folder"], exist_ok=True)

    def save_settings(self):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2)

    def load_music_tracker(self):
        if self.music_tracker_file.exists():
            try:
                with open(self.music_tracker_file, 'r', encoding='utf-8') as f:
                    self.music_tracker = json.load(f)
            except:
                self.music_tracker = {"used_music": [], "available_music": []}
        else:
            self.music_tracker = {"used_music": [], "available_music": []}
            self.refresh_music_list(silent=True)

    def save_music_tracker(self):
        with open(self.music_tracker_file, 'w', encoding='utf-8') as f:
            json.dump(self.music_tracker, f, indent=2)

    def refresh_music_list(self, silent=False):
        music_path = Path(self.settings["music_folder"])
        if not music_path.exists():
            self.music_tracker["available_music"] = []
        else:
            self.music_tracker["available_music"] = sorted([str(f.name) for f in music_path.glob("*.mp4")])
        self.save_music_tracker()
        if not silent:
            messagebox.showinfo("Success", f"Found {len(self.music_tracker['available_music'])} music files")

    def get_next_music(self) -> Optional[str]:
        available = self.music_tracker.get("available_music", [])
        used = self.music_tracker.get("used_music", [])
        music_path = Path(self.settings["music_folder"])
        unused = [m for m in available if m not in used]
        if not unused:
            self.music_tracker["used_music"] = []
            unused = available
        if unused:
            return str(music_path / unused[0])
        return None

    def mark_music_used(self, music_file: str):
        name = Path(music_file).name
        if "used_music" not in self.music_tracker:
            self.music_tracker["used_music"] = []
        if name not in self.music_tracker["used_music"]:
            self.music_tracker["used_music"].append(name)
        # NOTE: not persisted here - the export calls save_music_tracker() once
        # after the output succeeds, so a failed export doesn't burn the music.

    def reset_music_tracker(self):
        self.music_tracker["used_music"] = []
        self.save_music_tracker()
        messagebox.showinfo("Reset", "Music tracker reset. All songs are available again.")

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project", command=self.new_project)
        file_menu.add_command(label="Load Project", command=self.load_project)
        file_menu.add_command(label="Save Project", command=self.save_project)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Audio & Music Settings", command=self.show_audio_settings)
        settings_menu.add_command(label="Video Settings", command=self.show_video_settings)
        settings_menu.add_command(label="Text Settings", command=self.show_text_settings)
        settings_menu.add_command(label="Watermark / Logo Settings", command=self.show_watermark_settings)

    def show_audio_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Audio & Music Settings")
        dialog.geometry("550x650")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="General Audio", font=("Calibri", 11, "bold")).pack(pady=(15,5), padx=20, anchor='w')
        vol_frame = ttk.Frame(dialog)
        vol_frame.pack(fill='x', padx=30, pady=5)
        ttk.Label(vol_frame, text="Music Volume (dB):").pack(side='left')
        volume_var = tk.DoubleVar(value=self.settings.get("volume_db", 0))
        scale = ttk.Scale(vol_frame, from_=-60, to=20, variable=volume_var, length=200)
        scale.pack(side='left', padx=10)
        v_lbl = ttk.Label(vol_frame, text=f"{volume_var.get():.1f} dB")
        v_lbl.pack(side='left')
        volume_var.trace_add('write', lambda *a: v_lbl.config(text=f"{volume_var.get():.1f} dB"))
        
        mute_var = tk.BooleanVar(value=self.settings.get("mute_video_audio", True))
        ttk.Checkbutton(dialog, text="Mute original video audio", variable=mute_var).pack(padx=30, anchor='w')
        
        ttk.Separator(dialog).pack(fill='x', padx=20, pady=15)
        ttk.Label(dialog, text="Music Library", font=("Calibri", 11, "bold")).pack(padx=20, anchor='w')
        
        folder_var = tk.StringVar(value=self.settings.get("music_folder", ""))
        ff = ttk.Frame(dialog)
        ff.pack(fill='x', padx=30, pady=5)
        ttk.Entry(ff, textvariable=folder_var).pack(side='left', fill='x', expand=True)
        def browse():
            f = filedialog.askdirectory()
            if f:
                folder_var.set(f)
        ttk.Button(ff, text="Browse", command=browse).pack(side='right')
        
        af = ttk.Frame(dialog)
        af.pack(fill='x', padx=30, pady=10)
        ttk.Button(af, text="Refresh Music List", command=self.refresh_music_list).pack(side='left', padx=5)
        ttk.Button(af, text="Reset Used Music", command=self.reset_music_tracker).pack(side='left', padx=5)
        
        ttk.Separator(dialog).pack(fill='x', padx=20, pady=15)
        ttk.Label(dialog, text="Processing", font=("Calibri", 11, "bold")).pack(padx=20, anchor='w')
        
        cf_var = tk.IntVar(value=self.settings.get("crossfade_duration", 3))
        ttk.Label(dialog, text="Crossfade (sec):").pack(padx=30, anchor='w')
        ttk.Spinbox(dialog, from_=0, to=10, textvariable=cf_var).pack(padx=30, anchor='w')
        
        trim_var = tk.BooleanVar(value=self.settings.get("trim_silence", True))
        ttk.Checkbutton(dialog, text="Auto Trim Silence", variable=trim_var).pack(padx=30, anchor='w', pady=5)
        
        def save():
            self.settings.update({
                "volume_db": volume_var.get(), "mute_video_audio": mute_var.get(), 
                "music_folder": folder_var.get(), "crossfade_duration": cf_var.get(), 
                "trim_silence": trim_var.get()
            })
            self.save_settings()
            self.refresh_music_list(silent=True)
            dialog.destroy()
        ttk.Button(dialog, text="Save Settings", command=save).pack(pady=20)

    def show_video_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Video Settings")
        dialog.transient(self.root)
        dialog.grab_set()

        res_var = tk.StringVar(value=self.settings["resolution"])
        ttk.Label(dialog, text="Resolution:", font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')
        for label, value in [
            ("1080x1080 (Square)", "1080x1080"),
            ("1920x1080 (16:9)", "1920x1080"),
            ("1080x1920 (9:16 Portrait)", "1080x1920"),
            ("1080x1350 (4:5 Portrait)", "1080x1350"),
            ("720x1280 (9:16 HD)", "720x1280"),
        ]:
            ttk.Radiobutton(dialog, text=label, variable=res_var, value=value).pack(padx=40, anchor='w')

        bg_var = tk.StringVar(value=self.settings["background_mode"])
        ttk.Label(dialog, text="Background Mode:", font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')
        for label, value in [("White", "white"), ("Black", "black"), ("Blur", "blur"), ("Fit and Move", "fit_and_move")]:
            ttk.Radiobutton(dialog, text=label, variable=bg_var, value=value).pack(padx=40, anchor='w')

        crop_var = tk.BooleanVar(value=self.settings["cropping"])
        crop_cb = ttk.Checkbutton(dialog, text="Enable Cropping (Fill Frame)", variable=crop_var)
        crop_cb.pack(padx=20, pady=(15,5), anchor='w')

        last_crop = crop_var.get()

        def sync_crop_state(*_):
            nonlocal last_crop
            # Fit and Move needs extra pixels to pan across, so cropping (fill frame)
            # is incompatible with it — force it off while it is selected.
            if bg_var.get() == "fit_and_move":
                if not crop_cb.instate(['disabled']):
                    last_crop = crop_var.get()
                crop_var.set(False)
                crop_cb.state(['disabled'])
            else:
                crop_cb.state(['!disabled'])
                crop_var.set(last_crop)
        bg_var.trace_add('write', sync_crop_state)
        sync_crop_state()

        pos_img_var = tk.BooleanVar(value=self.settings.get("auto_position_photos", False))
        ttk.Checkbutton(dialog, text="Auto position photos (Text below)", variable=pos_img_var).pack(padx=20, pady=5, anchor='w')

        pos_vid_var = tk.BooleanVar(value=self.settings.get("auto_position_videos", False))
        ttk.Checkbutton(dialog, text="Auto position videos (Text below)", variable=pos_vid_var).pack(padx=20, pady=5, anchor='w')

        dur_var = tk.IntVar(value=self.settings["slide_duration"])
        ttk.Label(dialog, text="Slide Duration (sec):").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Spinbox(dialog, from_=1, to=30, textvariable=dur_var, width=10).pack(padx=40, anchor='w')

        ttk.Separator(dialog).pack(fill='x', padx=20, pady=15)
        ttk.Label(dialog, text="Transitions (between clips)", font=("Calibri", 10, "bold")).pack(padx=20, anchor='w')

        TRANSITION_EFFECTS = [
            ("None", "none"), ("Fade", "fade"), ("Fade to Black", "fadeblack"), ("Fade to White", "fadewhite"),
            ("Wipe Left", "wipeleft"), ("Wipe Right", "wiperight"), ("Wipe Up", "wipeup"), ("Wipe Down", "wipedown"),
            ("Smooth Left", "smoothleft"), ("Smooth Right", "smoothright"),
        ]
        RANDOM_EFFECTS = [
            ("Fade", "fade"), ("Fade to Black", "fadeblack"), ("Fade to White", "fadewhite"),
            ("Wipe Left", "wipeleft"), ("Wipe Right", "wiperight"), ("Wipe Up", "wipeup"), ("Wipe Down", "wipedown"),
            ("Smooth Left", "smoothleft"), ("Smooth Right", "smoothright"),
        ]

        current_effect = self.settings.get("transition_effect", "fade")
        is_random = current_effect == "random"
        current_label = next((lbl for lbl, val in TRANSITION_EFFECTS if val == current_effect), "Fade")

        tr_f = ttk.Frame(dialog)
        tr_f.pack(fill='x', padx=30, pady=5)
        ttk.Label(tr_f, text="Effect:").pack(side='left')
        tr_effect_var = tk.StringVar(value=current_label)
        tr_combo = ttk.Combobox(tr_f, textvariable=tr_effect_var,
                                values=[lbl for lbl, _ in TRANSITION_EFFECTS],
                                state='disabled' if is_random else 'readonly', width=18)
        tr_combo.pack(side='left', padx=10)

        td_f = ttk.Frame(dialog)
        td_f.pack(fill='x', padx=30, pady=5)
        ttk.Label(td_f, text="Duration (sec):").pack(side='left')
        tr_dur_var = tk.DoubleVar(value=self.settings.get("transition_duration", 0.7))
        tr_dur_spin = ttk.Spinbox(td_f, from_=0.2, to=2.0, increment=0.1, textvariable=tr_dur_var, width=8,
                                   format="%.1f")
        tr_dur_spin.pack(side='left', padx=10)

        # Random toggle + sub-options container
        saved_random = self.settings.get("random_transitions", [])
        random_effect_vars = {}
        for lbl, val in RANDOM_EFFECTS:
            is_sel = (not saved_random) or (val in saved_random)
            random_effect_vars[val] = tk.BooleanVar(value=is_sel)

        random_var = tk.BooleanVar(value=is_random)
        random_container = ttk.Frame(dialog)
        random_container.pack(fill='x', padx=30)

        random_sub_frame = ttk.LabelFrame(random_container, text="Εφέ που συμπεριλαμβάνονται στο Random")

        for lbl, val in RANDOM_EFFECTS:
            ttk.Checkbutton(random_sub_frame, text=lbl, variable=random_effect_vars[val]).pack(anchor='w', padx=10, pady=1)

        def toggle_random():
            if random_var.get():
                tr_combo.config(state='disabled')
                random_sub_frame.pack(fill='x', pady=(5, 0))
                dialog.geometry("500x1100")
            else:
                tr_combo.config(state='readonly')
                random_sub_frame.pack_forget()
                dialog.geometry("500x920")

        ttk.Checkbutton(random_container, text="Random", variable=random_var, command=toggle_random).pack(anchor='w', pady=5)

        if is_random:
            random_sub_frame.pack(fill='x', pady=(5, 0))
            dialog.geometry("500x1100")
        else:
            dialog.geometry("500x920")

        def save():
            if random_var.get():
                chosen_value = "random"
                selected_randoms = [val for val, var in random_effect_vars.items() if var.get()]
                if not selected_randoms:
                    selected_randoms = [val for _, val in RANDOM_EFFECTS]
            else:
                chosen_label = tr_effect_var.get()
                chosen_value = next((val for lbl, val in TRANSITION_EFFECTS if lbl == chosen_label), "fade")
                selected_randoms = self.settings.get("random_transitions", [])
            self.settings.update({
                "resolution": res_var.get(), "background_mode": bg_var.get(),
                "cropping": crop_var.get(), "slide_duration": dur_var.get(),
                "auto_position_photos": pos_img_var.get(), "auto_position_videos": pos_vid_var.get(),
                "transition_effect": chosen_value, "transition_duration": round(tr_dur_var.get(), 1),
                "random_transitions": selected_randoms
            })
            self.save_settings()
            dialog.destroy()
        ttk.Button(dialog, text="Save Settings", command=save).pack(pady=20)

    def show_text_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Text Settings")
        dialog.geometry("400x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        size_var = tk.IntVar(value=self.settings["font_size"])
        ttk.Label(dialog, text="Font Size:").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Spinbox(dialog, from_=10, to=150, textvariable=size_var).pack(padx=40, anchor='w')
        
        fam_var = tk.StringVar(value=self.settings["font_family"])
        ttk.Label(dialog, text="Font Family:").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Combobox(dialog, textvariable=fam_var, values=["Calibri", "Arial", "Verdana", "Georgia"]).pack(padx=40, anchor='w', fill='x')
        
        def save():
            self.settings.update({"font_size": size_var.get(), "font_family": fam_var.get()})
            self.save_settings()
            dialog.destroy()
        ttk.Button(dialog, text="Save Settings", command=save).pack(pady=20)

    def _build_watermark_ui(self, parent, wm_data):
        """Build watermark controls into parent frame. Returns getter lambda."""
        POSITIONS = [("Bottom Right", "bottom_right"), ("Bottom Left", "bottom_left"),
                     ("Top Right", "top_right"), ("Top Left", "top_left"), ("Center", "center")]
        pos_labels = [lbl for lbl, _ in POSITIONS]
        pos_values = [val for _, val in POSITIONS]
        cur_pos_label = next((lbl for lbl, val in POSITIONS if val == wm_data.get("position", "bottom_right")), "Bottom Right")

        path_var = tk.StringVar(value=wm_data.get("path", ""))
        pf = ttk.Frame(parent)
        pf.pack(fill='x', padx=20, pady=5)
        ttk.Label(pf, text="Logo file (PNG/JPG):").pack(anchor='w')
        pf2 = ttk.Frame(pf)
        pf2.pack(fill='x')
        ttk.Entry(pf2, textvariable=path_var).pack(side='left', fill='x', expand=True)
        def browse_logo():
            f = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg")])
            if f:
                path_var.set(f)
        ttk.Button(pf2, text="Browse", command=browse_logo).pack(side='right')

        pos_var = tk.StringVar(value=cur_pos_label)
        pof = ttk.Frame(parent)
        pof.pack(fill='x', padx=20, pady=5)
        ttk.Label(pof, text="Position:").pack(side='left')
        ttk.Combobox(pof, textvariable=pos_var, values=pos_labels, state='readonly', width=15).pack(side='left', padx=10)

        size_var = tk.IntVar(value=wm_data.get("size_pct", 15))
        sf = ttk.Frame(parent)
        sf.pack(fill='x', padx=20, pady=5)
        ttk.Label(sf, text="Size (% of width):").pack(side='left')
        ttk.Spinbox(sf, from_=5, to=50, textvariable=size_var, width=6).pack(side='left', padx=10)

        opacity_var = tk.IntVar(value=wm_data.get("opacity", 80))
        of = ttk.Frame(parent)
        of.pack(fill='x', padx=20, pady=5)
        ttk.Label(of, text="Opacity (%):").pack(side='left')
        op_lbl = ttk.Label(of, text=f"{opacity_var.get()}%")
        opacity_scale = ttk.Scale(of, from_=10, to=100, variable=opacity_var, length=150)
        opacity_scale.pack(side='left', padx=10)
        op_lbl.pack(side='left')
        opacity_var.trace_add('write', lambda *a: op_lbl.config(text=f"{int(opacity_var.get())}%"))

        def get_values():
            chosen_pos = next((val for lbl, val in POSITIONS if lbl == pos_var.get()), "bottom_right")
            return {
                "path": path_var.get(), "position": chosen_pos,
                "size_pct": size_var.get(), "opacity": int(opacity_var.get())
            }
        return get_values

    def show_watermark_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Watermark / Logo Settings (Global)")
        dialog.geometry("480x380")
        dialog.transient(self.root)
        dialog.grab_set()

        enabled_var = tk.BooleanVar(value=self.settings.get("watermark_enabled", False))
        ttk.Checkbutton(dialog, text="Enable watermark on all videos", variable=enabled_var).pack(padx=20, pady=(15,5), anchor='w')

        wm_data = {
            "path": self.settings.get("watermark_path", ""),
            "position": self.settings.get("watermark_position", "bottom_right"),
            "size_pct": self.settings.get("watermark_size_pct", 15),
            "opacity": self.settings.get("watermark_opacity", 80)
        }
        get_values = self._build_watermark_ui(dialog, wm_data)

        def save():
            vals = get_values()
            self.settings.update({
                "watermark_enabled": enabled_var.get(),
                "watermark_path": vals["path"], "watermark_position": vals["position"],
                "watermark_size_pct": vals["size_pct"], "watermark_opacity": vals["opacity"]
            })
            self.save_settings()
            dialog.destroy()
        ttk.Button(dialog, text="Save Settings", command=save).pack(pady=20)

    def show_project_watermark(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Logo Override")
        dialog.geometry("480x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Override global watermark for this project:",
                  font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')

        enabled_var = tk.BooleanVar(value=self.project_watermark.get("enabled", False))
        ttk.Checkbutton(dialog, text="Enable project logo override", variable=enabled_var).pack(padx=20, pady=5, anchor='w')

        get_values = self._build_watermark_ui(dialog, self.project_watermark)

        def save():
            vals = get_values()
            vals["enabled"] = enabled_var.get()
            self.project_watermark = vals
            dialog.destroy()
        ttk.Button(dialog, text="Apply to Project", command=save).pack(pady=20)

    def setup_gui(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
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

    def open_text_window(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Text Input")
        dialog.geometry("1180x580")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Αριστερά: κείμενο για τα ΒΙΝΤΕΟ   |   Δεξιά: κείμενο για τις ΦΩΤΟΓΡΑΦΙΕΣ",
                  font=("Calibri", 10, "bold")).pack(padx=12, pady=(10, 0), anchor='w')
        ttk.Label(dialog, text="Αν αφήσεις κενό το δεξί πεδίο, το κείμενο των βίντεο θα εμφανίζεται και στις φωτογραφίες.",
                  foreground="#555").pack(padx=12, pady=(0, 6), anchor='w')

        frames = ttk.Frame(dialog)
        frames.pack(fill='both', expand=True, padx=10, pady=5)
        left_f = ttk.LabelFrame(frames, text="Κείμενο για ΒΙΝΤΕΟ")
        left_f.pack(side='left', fill='both', expand=True, padx=(0, 4))
        right_f = ttk.LabelFrame(frames, text="Κείμενο για ΦΩΤΟΓΡΑΦΙΕΣ")
        right_f.pack(side='right', fill='both', expand=True, padx=(4, 0))

        txt_v = scrolledtext.ScrolledText(left_f, wrap=tk.WORD, undo=True)
        txt_v.pack(fill='both', expand=True, padx=5, pady=5)
        txt_p = scrolledtext.ScrolledText(right_f, wrap=tk.WORD, undo=True)
        txt_p.pack(fill='both', expand=True, padx=5, pady=5)
        txt_v.insert("1.0", self.project_text_videos)
        txt_p.insert("1.0", self.project_text_photos)
        # Clear the undo stack so Ctrl+Z on a freshly opened window doesn't
        # wipe out the loaded text.
        txt_v.edit_reset()
        txt_p.edit_reset()

        def _undo(w):
            try:
                w.edit_undo()
            except tk.TclError:
                pass

        for t in (txt_v, txt_p):
            self._bind_text_shortcuts(t)
            m = tk.Menu(t, tearoff=0)
            m.add_command(label="Copy", command=lambda w=t: w.event_generate("<<Copy>>"))
            m.add_command(label="Paste", command=lambda w=t: w.event_generate("<<Paste>>"))
            m.add_command(label="Cut", command=lambda w=t: w.event_generate("<<Cut>>"))
            m.add_command(label="Undo", command=lambda w=t: _undo(w))
            t.bind("<Button-3>", lambda e, w=t, menu=m: menu.tk_popup(e.x_root, e.y_root))

        def save():
            self.project_text_videos = txt_v.get("1.0", tk.END).strip()
            self.project_text_photos = txt_p.get("1.0", tk.END).strip()
            self.is_modified = True
            dialog.destroy()

        btns = ttk.Frame(dialog)
        btns.pack(fill='x', padx=12, pady=10)
        def quick_paste(t):
            try:
                t.insert(tk.INSERT, self.root.clipboard_get())
            except tk.TclError:
                pass  # clipboard is empty / has no text

        ttk.Button(btns, text="Quick Paste Clipboard (Βίντεο)", command=lambda: quick_paste(txt_v)).pack(side='left', padx=(0, 5))
        ttk.Button(btns, text="Quick Paste Clipboard (Φωτό)", command=lambda: quick_paste(txt_p)).pack(side='left', padx=5)
        ttk.Button(btns, text="Apply Text", command=save).pack(side='right')

    def get_text_for(self, m_type):
        """Text overlay for a media type: videos' text by default; photos get
        their own text when the right field is filled, otherwise they share it."""
        if m_type == "image" and self.project_text_photos.strip():
            return self.project_text_photos
        return self.project_text_videos

    def _bind_text_shortcuts(self, txt):
        """Explicit Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+Z support for the text boxes."""
        txt.bind("<Control-c>", lambda e: self._do_text_shortcut(txt, "copy"))
        txt.bind("<Control-C>", lambda e: self._do_text_shortcut(txt, "copy"))
        txt.bind("<Control-v>", lambda e: self._do_text_shortcut(txt, "paste"))
        txt.bind("<Control-V>", lambda e: self._do_text_shortcut(txt, "paste"))
        txt.bind("<Control-x>", lambda e: self._do_text_shortcut(txt, "cut"))
        txt.bind("<Control-X>", lambda e: self._do_text_shortcut(txt, "cut"))
        txt.bind("<Control-z>", lambda e: self._do_text_shortcut(txt, "undo"))
        txt.bind("<Control-Z>", lambda e: self._do_text_shortcut(txt, "undo"))

    def _do_text_shortcut(self, txt, action):
        # Direct clipboard operations - this Tk build has NO class binding for
        # Ctrl+C/V/X on Text widgets, so event_generate("<<Copy>>") was never
        # guaranteed. Doing it directly always works.
        try:
            if action == "copy":
                if txt.tag_ranges(tk.SEL):
                    txt.clipboard_clear()
                    txt.clipboard_append(txt.get(tk.SEL_FIRST, tk.SEL_LAST))
            elif action == "paste":
                clip = self.root.clipboard_get()  # may raise TclError -> caught below, nothing deleted yet
                sel = txt.tag_ranges(tk.SEL)
                if sel:
                    # Replace the selection: remember its start, delete, then
                    # insert there (tk.INSERT drifts to the end after a delete).
                    txt.delete(sel[0], sel[1])
                    txt.insert(sel[0], clip)
                else:
                    txt.insert(tk.INSERT, clip)
            elif action == "cut":
                if txt.tag_ranges(tk.SEL):
                    txt.clipboard_clear()
                    txt.clipboard_append(txt.get(tk.SEL_FIRST, tk.SEL_LAST))
                    txt.delete(tk.SEL_FIRST, tk.SEL_LAST)
            elif action == "undo":
                txt.edit_undo()
        except tk.TclError:
            pass
        return "break"

    def handle_drop(self, data):
        files = re.findall(r'\{([^}]+)\}', data) if '{' in data else data.split()
        for f in files:
            f = f.strip('{} ')
            ext = Path(f).suffix.lower()
            if ext in ('.mp4', '.avi', '.mov', '.mkv'):
                self.media_files.append(("video", f))
            elif ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                self.media_files.append(("image", f))
        self.update_media_display()

    def update_media_display(self):
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self.thumbnails = []
        if self.view_mode.get() == "list":
            for i, (t, p) in enumerate(self.media_files):
                lbl = tk.Label(self.thumb_frame, text=f"{i+1}. [{t.upper()}] {Path(p).name}", anchor='w', bg='#eee', padx=10, pady=2)
                lbl.pack(fill='x')
                lbl.bind("<Button-3>", lambda e, idx=i: self.media_menu(e, idx))
        else:
            w_limit = self.media_canvas.winfo_width() - 30
            cols = max(1, w_limit // 145) if w_limit > 100 else 4
            for i, (t, p) in enumerate(self.media_files):
                f = ttk.Frame(self.thumb_frame, padding=2, relief="ridge")
                r, c = divmod(i, cols)
                f.grid(row=r, column=c, padx=5, pady=5)
                try:
                    if t == "image":
                        img = Image.open(p)
                    else:
                        img = self._video_first_frame(p)
                    img = img.copy()  # thumbnail mutates in place - never touch the cached frame
                    img.thumbnail((120, 120))
                    tk_img = ImageTk.PhotoImage(img)
                    self.thumbnails.append(tk_img)
                    lbl = tk.Label(f, image=tk_img, bg="black")
                    lbl.pack()
                    tk.Label(f, text=str(i+1), font=("Calibri", 8, "bold"), fg="white", bg="#333").place(x=2, y=2)
                    lbl.bind("<Button-3>", lambda e, idx=i: self.media_menu(e, idx))
                except:
                    tk.Label(f, text="Error").pack()

    def media_menu(self, event, idx):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Delete", command=lambda: [self.media_files.pop(idx), self.update_media_display()])
        m.add_command(label="Change Position", command=lambda: self.change_pos(idx))
        m.add_separator()
        m.add_command(label="Move Left/Up", command=lambda: self.move_media(idx, -1))
        m.add_command(label="Move Right/Down", command=lambda: self.move_media(idx, 1))
        m.tk_popup(event.x_root, event.y_root)

    def change_pos(self, idx):
        new_idx = simpledialog.askinteger("Position", f"Move item {idx+1} to position:", initialvalue=idx+1, minvalue=1, maxvalue=len(self.media_files))
        if new_idx:
            item = self.media_files.pop(idx)
            self.media_files.insert(new_idx-1, item)
            self.update_media_display()

    def move_media(self, idx, d):
        ni = idx + d
        if 0 <= ni < len(self.media_files):
            self.media_files[idx], self.media_files[ni] = self.media_files[ni], self.media_files[idx]
            self.update_media_display()

    def add_videos(self):
        fs = filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv")])
        for f in fs:
            self.media_files.append(("video", f))
        if fs:
            self.is_modified = True
            self.update_media_display()

    def add_images(self):
        fs = filedialog.askopenfilenames(filetypes=[("Image", "*.jpg *.jpeg *.png *.bmp")])
        for f in fs:
            self.media_files.append(("image", f))
        if fs:
            self.is_modified = True
            self.update_media_display()

    def clear_media(self):
        self.media_files = []
        self.is_modified = True
        self.update_media_display()

    def new_project(self):
        self.name_var.set("")
        self.media_files = []
        self.project_text_videos = ""
        self.project_text_photos = ""
        self.project_watermark = {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        }
        self.update_media_display()

    def save_project(self):
        n = self.name_var.get().strip()
        data = {
            "name": n,
            "media_files": self.media_files,
            "text": self.project_text_videos,
            "text_videos": self.project_text_videos,
            "text_photos": self.project_text_photos,
            "out": self.out_var.get(),
            "project_watermark": self.project_watermark
        }
        p = self.projects_dir / f"{re.sub(r'\W+', '_', n)}.json"
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.is_modified = False
        messagebox.showinfo("Saved", "Project saved.")

    def load_project(self):
        d = tk.Toplevel(self.root)
        d.title("Load Project")
        d.geometry("400x500")
        
        # Search field at the top
        search_frame = ttk.Frame(d)
        search_frame.pack(fill='x', padx=10, pady=(10, 5))
        ttk.Label(search_frame, text="🔍 Αναζήτηση:").pack(side='left', padx=(0, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True)
        search_entry.focus_set()
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(d)
        list_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        lb = tk.Listbox(list_frame, width=50)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=scrollbar.set)
        lb.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        pfs = sorted(list(self.projects_dir.glob("*.json")), key=os.path.getmtime, reverse=True)
        for p in pfs:
            lb.insert(tk.END, p.stem)
        
        def filter_projects(*args):
            search_text = search_var.get().lower()
            lb.delete(0, tk.END)
            for p in pfs:
                if search_text in p.stem.lower():
                    lb.insert(tk.END, p.stem)
        
        search_var.trace_add('write', filter_projects)
        
        def do_load():
            if not lb.curselection():
                return
            # Find the actual index in pfs matching the selected display name
            selected_name = lb.get(lb.curselection()[0])
            for idx, p in enumerate(pfs):
                if p.stem == selected_name:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.name_var.set(data.get("name", ""))
                        self.media_files = data.get("media_files", data.get("media", []))
                        old_text = data.get("text", "")
                        self.project_text_videos = data.get("text_videos", old_text)
                        self.project_text_photos = data.get("text_photos", "")
                        self.out_var.set(data.get("out", ""))
                        self.project_watermark = data.get("project_watermark", {
                            "enabled": False, "path": "", "position": "bottom_right",
                            "size_pct": 15, "opacity": 80
                        })
                        self.is_modified = False
                        self.update_media_display()
                        d.destroy()
                    break
        
        def do_duplicate():
            if not lb.curselection():
                return
            selected_name = lb.get(lb.curselection()[0])
            for old_path in pfs:
                if old_path.stem == selected_name:
                    with open(old_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data["name"] = data.get("name", "") + " -copy"
                    new_filename = re.sub(r'\W+', '_', data["name"]) + ".json"
                    new_path = self.projects_dir / new_filename
                    if new_path.exists():
                        messagebox.showerror("Duplicate",
                                             f"Υπάρχει ήδη project με το όνομα '{data['name']}'. "
                                             "Διάλεξε άλλο όνομα ή διέγραψε το υπάρχον.")
                        break
                    with open(new_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    messagebox.showinfo("Success", f"Project duplicated as: {data['name']}")
                    pfs.append(new_path)
                    # Re-apply filter to update list
                    filter_projects()
                    break
        
        def do_rename():
            if not lb.curselection():
                return
            selected_name = lb.get(lb.curselection()[0])
            for idx, old_path in enumerate(pfs):
                if old_path.stem == selected_name:
                    current_name = old_path.stem.replace('_', ' ')
                    new_name = simpledialog.askstring("Rename Project", "New name:", initialvalue=current_name)
                    if new_name:
                        with open(old_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        data["name"] = new_name
                        new_filename = re.sub(r'\W+', '_', new_name) + ".json"
                        new_path = self.projects_dir / new_filename
                        # The sanitized name may map back to the same file (e.g. the
                        # prefilled name, "_" vs space, case changes). In that case we
                        # rewrite in place and must NOT delete the file afterwards.
                        same_file = os.path.normcase(str(old_path.resolve())) == os.path.normcase(str(new_path.resolve()))
                        if not same_file and new_path.exists():
                            messagebox.showerror("Rename",
                                                 f"Υπάρχει ήδη project με το όνομα '{new_name}'. Διάλεξε άλλο όνομα.")
                            break
                        with open(new_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        if not same_file:
                            old_path.unlink()
                        messagebox.showinfo("Success", f"Project renamed to: {new_name}")
                        pfs[idx] = new_path
                        # Re-apply filter to update list
                        filter_projects()
                    break
        
        def do_delete():
            if not lb.curselection():
                return
            selected_name = lb.get(lb.curselection()[0])
            for old_path in pfs:
                if old_path.stem == selected_name:
                    if messagebox.askyesno("Delete Project", f"Delete project '{selected_name}'? This cannot be undone."):
                        old_path.unlink()
                        pfs.remove(old_path)
                        filter_projects()
                        messagebox.showinfo("Success", "Project deleted.")
                    break
        
        def show_context_menu(event):
            idx = lb.nearest(event.y)
            if idx < 0:
                return
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx)
            lb.see(idx)
            cm = tk.Menu(self.root, tearoff=0)
            cm.add_command(label="Load", command=do_load)
            cm.add_command(label="Duplicate (-copy)", command=do_duplicate)
            cm.add_command(label="Rename", command=do_rename)
            cm.add_command(label="Delete", command=do_delete)
            cm.tk_popup(event.x_root, event.y_root)
        
        lb.bind("<Button-3>", show_context_menu)
        ttk.Button(d, text="Load", command=do_load).pack(pady=5)

    def generate_preview(self):
        if not self.media_files:
            messagebox.showinfo("Preview", "Πρόσθεσε πρώτα φωτογραφίες ή βίντεο στο project.")
            return
        threading.Thread(target=self._preview_task, daemon=True).start()

    def _preview_task(self):
        try:
            res = self.settings["resolution"].split('x')
            w, h = int(res[0]), int(res[1])
            photo_path = next((p for t, p in self.media_files if t == "image"), None)
            video_path = next((p for t, p in self.media_files if t == "video"), None)
            if photo_path is None and video_path is None:
                self.root.after(0, lambda: messagebox.showinfo("Preview", "Δεν υπάρχουν media για preview."))
                return

            if photo_path is not None:
                self._render_preview(photo_path, "image", w, h, self.preview_photo_canvas)
            else:
                self.root.after(0, lambda: self._clear_preview(self.preview_photo_canvas))
            if video_path is not None:
                self._render_preview(video_path, "video", w, h, self.preview_video_canvas)
            else:
                self.root.after(0, lambda: self._clear_preview(self.preview_video_canvas))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _clear_preview(self, canvas):
        canvas.delete("all")
        if hasattr(canvas, 'full_image'):
            del canvas.full_image

    def _render_preview(self, path, m_type, w, h, canvas):
        """Render the first frame of the export for this media type (full
        resolution), then downscale only for display. For fit_and_move the
        export picks a random pan direction, so this shows the pan start -
        the text layout is identical for every pan position."""
        if m_type == "image":
            img = Image.open(path)
            frame = self._fit_image_logic(img, w, h, "image")
            fit_move_data = getattr(frame, 'fit_move_data', None)
            if fit_move_data is not None:
                # Actual first frame of the pan animation (t=0), not the middle.
                overlay = self._make_text_overlay(self.get_text_for("image"), w, h)
                frame = self._render_fit_and_move_frame(frame, fit_move_data, 0.0, w, h, overlay)
            else:
                frame = self.render_text_on_image(frame, self.get_text_for("image"), w, h)
        else:
            first = self._video_first_frame(path)
            frame = self._render_video_first_frame(first, w, h)
            frame = self.render_text_on_image(frame, self.get_text_for("video"), w, h)

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

    def _create_blur_bg(self, img, tw, th):
        img = img.convert("RGB")  # GaussianBlur does not support palette/RGBA modes
        iw, ih = img.size
        ratio = max(tw/iw, th/ih)
        bg = img.resize((int(iw*ratio), int(ih*ratio)), Image.Resampling.LANCZOS)
        x0 = (bg.width - tw) // 2
        y0 = (bg.height - th) // 2
        return bg.crop((x0, y0, x0 + tw, y0 + th)).filter(ImageFilter.GaussianBlur(30))

    def _make_text_overlay(self, text, width, height):
        """Precompute the text overlay (white box + text on a transparent layer)
        once, so it can be pasted onto every frame cheaply instead of re-rendering
        the text 120 times per photo."""
        if not text:
            return None
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        return self.render_text_on_image(base, text, width, height)

    def _render_fit_and_move_frame(self, bg, fit_move_data, pos, width, height, overlay=None):
        """Render one pan frame at relative position pos (0 = start, 1 = end)."""
        fg = fit_move_data["fg"]
        is_landscape = fit_move_data["is_landscape"]
        available_h = fit_move_data["available_h"]
        if is_landscape:
            pan_range = max(0, fg.width - width)
            crop_x = int(round(pos * pan_range))
            crop_y = (fg.height - available_h) // 2
        else:
            pan_range = max(0, fg.height - available_h)
            crop_x = (fg.width - width) // 2
            crop_y = int(round(pos * pan_range))
        frame = bg.copy()
        window = fg.crop((crop_x, crop_y, crop_x + width, crop_y + available_h))
        frame.paste(window, (0, 0))
        if overlay is not None:
            frame.paste(overlay, (0, 0), overlay)
        return frame

    def _video_first_frame(self, path):
        """First frame of a video with its rotation metadata applied.

        moviepy's ``get_frame(0)`` ignores rotation, so portrait phone videos
        (stored as landscape pixels + a display-matrix rotation) come back
        landscape. ffmpeg's autorotate is exactly what the export pipeline
        uses, so extract the frame through ffmpeg to match the export's
        orientation. Falls back to a moviepy raw frame, then to a small
        placeholder, so callers never crash. Results are cached per path so
        repeated UI refreshes don't re-spawn ffmpeg every time.
        """
        key = str(path)
        if not hasattr(self, '_video_frame_cache'):
            self._video_frame_cache = {}
        if key in self._video_frame_cache:
            return self._video_frame_cache[key]
        img = None
        try:
            p = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', '0', '-i', str(path),
                                '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                               capture_output=True, timeout=30)
            if p.returncode == 0 and p.stdout:
                img = Image.open(io.BytesIO(p.stdout))
                img.load()
        except Exception:
            pass
        if img is None:
            try:
                # Fallback: moviepy raw frame (rotation ignored, better than nothing).
                v = VideoFileClip(str(path))
                try:
                    img = Image.fromarray(v.get_frame(0).astype('uint8'))
                finally:
                    v.close()
            except Exception:
                pass
        if img is None:
            # Last resort: small placeholder so callers keep working.
            img = Image.new("RGB", (64, 64), (30, 30, 30))
        self._video_frame_cache[key] = img
        return img

    def _render_video_first_frame(self, img, tw, th):
        """Replicate the export video branch: blurred background + video frame
        scaled with force_original_aspect_ratio=decrease (or increase+crop when
        cropping is enabled), centered."""
        bg = self._create_blur_bg(img, tw, th)
        iw, ih = img.size
        if self.settings.get("cropping"):
            r = max(tw / iw, th / ih)
            fg = img.resize((int(iw * r), int(ih * r)), Image.Resampling.LANCZOS)
            x0 = (fg.width - tw) // 2
            y0 = (fg.height - th) // 2
            fg = fg.crop((x0, y0, x0 + tw, y0 + th))
            bg.paste(fg, (0, 0))
        else:
            r = min(tw / iw, th / ih)
            fg = img.resize((int(iw * r), int(ih * r)), Image.Resampling.LANCZOS)
            bg.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
        return bg

    def _preview_canvas_size(self, w, h):
        """Display size for a preview, preserving the resolution's aspect ratio."""
        max_w, max_h = 240, 420
        ar = w / h
        if ar >= 1.0:
            cw, ch = max_w, max(1, int(max_w / ar))
        else:
            cw, ch = max(1, int(max_h * ar)), max_h
        return cw, ch

    def _fit_image_logic(self, img, tw, th, m_type):
        img = img.convert("RGB")  # keep every downstream op (blur, resize, paste, rawvideo) in RGB
        auto_pos = self.settings.get("auto_position_photos" if m_type == "image" else "auto_position_videos", False)
        iw, ih = img.size
        lh = self.settings["font_size"] + 5
        text_here = self.get_text_for(m_type)
        _, wrapped_lines = self._wrap_text_lines(text_here, tw) if text_here.strip() else ([], [])
        
        bg_m = self.settings["background_mode"]
        if bg_m in ("blur", "fit_and_move"):
            bg = self._create_blur_bg(img, tw, th)
        else:
            bg = Image.new("RGB", (tw, th), (255,255,255) if bg_m == "white" else (0,0,0))
        
        if bg_m == "fit_and_move":
            # Fit the image in the area above the text, zoom in a bit, and attach
            # pan data so the export can animate a slow pan across the rest of the
            # photo. Auto-position is effectively implied (image sits above text).
            text_h = (len(wrapped_lines) * lh + 40) if wrapped_lines else 0
            available_h = max(th - text_h, 100)
            is_landscape = (iw / ih) >= (tw / available_h)
            zoom = min(1.6, max(1.25, 1.25 * th / available_h))
            if is_landscape:
                r = (available_h * zoom) / ih
            else:
                r = (tw * zoom) / iw
            fg = img.resize((int(iw * r), int(ih * r)), Image.Resampling.LANCZOS)
            bg.fit_move_data = {"fg": fg, "is_landscape": is_landscape, "available_h": available_h}
            crop_x = (fg.width - tw) // 2
            crop_y = (fg.height - available_h) // 2
            bg.paste(fg.crop((crop_x, crop_y, crop_x + tw, crop_y + available_h)), (0, 0))
            return bg
        elif auto_pos:
            av_h = th - (len(wrapped_lines) * lh + 40)
            r = min(tw/iw, max(100, av_h)/ih)
            fg = img.resize((int(iw*r), int(ih*r)), Image.Resampling.LANCZOS)
            y = 20
        elif self.settings["cropping"]:
            r = max(tw/iw, th/ih)
            fg = img.resize((int(iw*r), int(ih*r)), Image.Resampling.LANCZOS)
            x0 = (fg.width - tw) // 2
            y0 = (fg.height - th) // 2
            fg = fg.crop((x0, y0, x0 + tw, y0 + th))
            y = 0
        else:
            r = min(tw/iw, th/ih)
            fg = img.resize((int(iw*r), int(ih*r)), Image.Resampling.LANCZOS)
            y = (th - fg.height) // 2
        
        bg.paste(fg, ((tw-fg.width)//2, max(0, y)))
        return bg

    def _render_fit_and_move_clip(self, bg, fit_move_data, temp_dir, index, width, height, image_duration, clip_path):
        """Render a slow pan clip for the 'Fit and Move' background mode.

        The foreground image was already zoomed in ``_fit_image_logic`` so it
        overflows the visible area. Here we pan across it — horizontally for
        landscape photos, vertically for portrait ones — over the slide
        duration, starting from a random side. The text overlay is drawn once
        and the frames are streamed straight into ffmpeg as raw RGB, which
        avoids writing 120 PNG files and makes this several times faster.
        """
        fg = fit_move_data["fg"]
        is_landscape = fit_move_data["is_landscape"]
        available_h = fit_move_data["available_h"]

        fps = 30
        total_frames = max(1, int(image_duration * fps))
        forward = random.choice([True, False])
        overlay = self._make_text_overlay(self.get_text_for("image"), width, height)
        self._log_export(f"fit_and_move img {index}: is_landscape={is_landscape} "
                         f"available_h={available_h} fg={fg.size} frames={total_frames} "
                         f"direction={'L->R' if forward else 'R->L'}")

        cmd = ['ffmpeg', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{width}x{height}', '-r', str(fps), '-i', '-',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
               '-r', str(fps), '-pix_fmt', 'yuv420p', '-an', str(clip_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for f_idx in range(total_frames):
                t = f_idx / (total_frames - 1) if total_frames > 1 else 0.0
                pos = t if forward else (1.0 - t)
                frame = self._render_fit_and_move_frame(bg, fit_move_data, pos, width, height, overlay)
                # Always feed exact 3-bytes-per-pixel RGB: PNG-with-alpha sources
                # would otherwise produce RGBA bytes that ffmpeg misreads.
                proc.stdin.write(frame.convert("RGB").tobytes())
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise
        finally:
            proc.stdin.close()
        _, err = proc.communicate()
        if proc.returncode != 0:
            err_tail = err.decode(errors='replace')[-500:] if err else ""
            self._log_export(f"ffmpeg FAILED encoding Fit and Move clip: {err_tail}")
            raise RuntimeError(f"ffmpeg failed while encoding Fit and Move clip:\n{err_tail}")
        return float(image_duration)

    def _get_text_fonts(self, fs):
        try:
            font = ImageFont.truetype("calibri.ttf", fs)
            f_bold = ImageFont.truetype("calibrib.ttf", fs)
        except:
            font = f_bold = ImageFont.load_default()
        return font, f_bold

    def _wrap_text_lines(self, text, w, fs=None):
        """Split text into drawable parts and wrapped lines — same layout as rendering.

        Returns (parts, lines) where parts is [(is_bold, chunk), ...] used for
        drawing and lines is [(chunk_list, line_width), ...] used both for
        drawing and for estimating how much vertical space the text occupies.
        """
        if fs is None:
            fs = self.settings["font_size"]
        font, f_bold = self._get_text_fonts(fs)

        parts = []
        last = 0
        for m in re.finditer(r'\*\*\s*([\s\S]*?)\s*\*\*', text):
            if m.start() > last:
                parts.append((False, text[last:m.start()]))
            parts.append((True, m.group(1)))
            last = m.end()
        if last < len(text):
            parts.append((False, text[last:]))

        lines = []
        cur_line = []
        cur_w = 0
        for is_b, txt in parts:
            f = f_bold if is_b else font
            paragraphs = txt.split('\n')
            for idx, p in enumerate(paragraphs):
                for word in p.split():
                    ww = f.getlength(word + " ")
                    if cur_w + ww > w - 60 and cur_line:
                        lines.append((cur_line, cur_w))
                        cur_line = []
                        cur_w = 0
                    cur_line.append((is_b, word + " "))
                    cur_w += ww
                # Flush only on actual newline (not at the end of the last paragraph)
                if idx < len(paragraphs) - 1:
                    if cur_line:
                        lines.append((cur_line, cur_w))
                        cur_line = []
                        cur_w = 0
        if cur_line:
            lines.append((cur_line, cur_w))
            cur_line = []
            cur_w = 0
        return parts, lines

    def render_text_on_image(self, img, text, w, h):
        if not text:
            return img
        img = img.copy().convert("RGBA")
        draw = ImageDraw.Draw(img)
        fs = self.settings["font_size"]
        font, f_bold = self._get_text_fonts(fs)
        parts, lines = self._wrap_text_lines(text, w, fs)
        
        lh = fs + 5
        y = h - (len(lines) * lh) - 15
        if self.settings["text_style"] == "black_box" and lines:
            max_lw = max([l[1] for l in lines])
            draw.rectangle([(w-max_lw)//2-15, y-5, (w+max_lw)//2+15, h-5], fill=(255,255,255,255))
        for lp, lw in lines:
            x = (w - lw) // 2
            for is_b, txt in lp:
                f = f_bold if is_b else font
                draw.text((x, y), txt, font=f, fill="black")
                x += f.getlength(txt)
            y += lh
        return img

    def _build_merged_with_transitions(self, clip_files, clip_durations, temp_dir, merged):
        """Merge clip files using xfade transitions (or simple concat if effect is 'none')."""
        effect = self.settings.get("transition_effect", "fade")
        td = self.settings.get("transition_duration", 0.7)
        XFADE_EFFECTS = ["fade", "fadeblack", "fadewhite", "wipeleft", "wiperight",
                         "wipeup", "wipedown", "smoothleft", "smoothright"]

        if effect == "none" or len(clip_files) <= 1:
            concat_file = temp_dir / "list.txt"
            with open(concat_file, 'w', encoding='utf-8') as f:
                for c in clip_files:
                    f.write(f"file '{str(c).replace(os.sep, '/')}'\n")
            self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                                       '-i', str(concat_file), '-c', 'copy', str(merged)],
                                      "merging clips (concat)")
            return

        inputs = []
        for c in clip_files:
            inputs += ['-i', str(c)]

        n = len(clip_files)
        filter_parts = []
        prev_label = "[0:v]"
        cumulative = 0.0
        for i in range(1, n):
            cumulative += clip_durations[i - 1]
            offset = max(0.0, cumulative - i * td)
            if effect == "random":
                random_pool = self.settings.get("random_transitions", [])
                if not random_pool:
                    random_pool = XFADE_EFFECTS
                eff = random.choice(random_pool)
            else:
                eff = effect
            out_label = f"[x{i}]" if i < n - 1 else ""
            filter_parts.append(
                f"{prev_label}[{i}:v]xfade=transition={eff}:duration={td}:offset={offset:.3f}{out_label}"
            )
            prev_label = f"[x{i}]"

        cmd = (['ffmpeg', '-y'] + inputs +
               ['-filter_complex', ";".join(filter_parts),
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-r', '30', '-pix_fmt', 'yuv420p', '-an', str(merged)])
        self._run_ffmpeg_or_raise(cmd, "merging clips with transitions")

    def _apply_watermark(self, input_path, output_path, width, height):
        """Overlay watermark on video. Uses project override if enabled, else global setting."""
        wm = None
        if self.project_watermark.get("enabled") and self.project_watermark.get("path"):
            wm = self.project_watermark
        elif self.settings.get("watermark_enabled") and self.settings.get("watermark_path"):
            wm = {
                "path": self.settings["watermark_path"],
                "position": self.settings.get("watermark_position", "bottom_right"),
                "size_pct": self.settings.get("watermark_size_pct", 15),
                "opacity": self.settings.get("watermark_opacity", 80)
            }

        if not wm or not Path(wm["path"]).exists():
            self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-i', str(input_path), '-c', 'copy', str(output_path)],
                                      "copying video (no watermark)")
            return

        wm_w = int(width * wm["size_pct"] / 100)
        alpha = wm["opacity"] / 100.0
        pos_map = {
            "top_left": "10:10",
            "top_right": "W-w-10:10",
            "bottom_left": "10:H-h-10",
            "bottom_right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2"
        }
        xy = pos_map.get(wm["position"], "W-w-10:H-h-10")
        fc = (f"[1:v]scale={wm_w}:-1,format=rgba,"
              f"colorchannelmixer=aa={alpha:.2f}[wm];[0:v][wm]overlay={xy}")
        cmd = ['ffmpeg', '-y', '-i', str(input_path), '-i', wm["path"],
               '-filter_complex', fc,
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-an', str(output_path)]
        self._run_ffmpeg_or_raise(cmd, "applying watermark")

    def export_video(self):
        n = self.name_var.get().strip()
        if not n:
            messagebox.showwarning(
                "Λείπει το όνομα",
                "Παρακαλώ γράψε ένα όνομα για το project πριν κάνεις Generate Video!"
            )
            return
        out = Path(self.out_var.get()) / f"{n}.mp4"
        self.status.config(text="Exporting...")
        threading.Thread(target=self._export_task, args=(out,), daemon=True).start()

    def _export_task(self, out_path):
        try:
            temp_dir = self.app_dir / "temp"
            temp_dir.mkdir(exist_ok=True)
            for f in temp_dir.glob("*"):
                try: f.unlink()
                except: pass

            res = self.settings["resolution"]
            width, height = map(int, res.split('x'))
            image_duration = self.settings.get("slide_duration", 3)
            cpu_count = os.cpu_count() or 8

            # Fresh debug log for this export run
            try:
                (temp_dir / "export_log.txt").unlink()
            except OSError:
                pass
            self._log_export(f"EXPORT START: {len(self.media_files)} items, res={res}, "
                             f"bg={self.settings.get('background_mode')}, "
                             f"slide_dur={image_duration}s, "
                             f"music_folder={self.settings.get('music_folder')}")
            self._export_music_missing = False

            clip_files = []
            clip_durations = []
            total_duration = 0

            for i, (m_type, path) in enumerate(self.media_files):
                self.progress_var.set((i / len(self.media_files)) * 50)
                clip_path = temp_dir / f"clip_{i:04d}.mp4"

                if m_type == "image":
                    img = Image.open(path)
                    img = self._fit_image_logic(img, width, height, m_type)
                    fit_move_data = getattr(img, 'fit_move_data', None)
                    if fit_move_data is None:
                        png_path = temp_dir / f"frame_{i:04d}.png"
                        img = self.render_text_on_image(img, self.get_text_for("image"), width, height)
                        img.save(str(png_path), "PNG")

                        cmd = ['ffmpeg', '-y', '-loop', '1', '-i', str(png_path), '-t', str(image_duration),
                               '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30',
                               '-pix_fmt', 'yuv420p', '-an', str(clip_path)]
                        self._run_ffmpeg_or_raise(cmd, f"encoding image clip {i}")
                        clip_dur = float(image_duration)
                    else:
                        clip_dur = self._render_fit_and_move_clip(
                            img, fit_move_data, temp_dir, i, width, height, image_duration, clip_path
                        )
                else:
                    v = VideoFileClip(path)
                    dur = v.duration
                    v.close()

                    txt_overlay = Image.new("RGBA", (width, height), (0,0,0,0))
                    txt_overlay = self.render_text_on_image(txt_overlay, self.get_text_for("video"), width, height)
                    txt_p = temp_dir / f"txt_{i:04d}.png"
                    txt_overlay.save(str(txt_p), "PNG")

                    bg_p = temp_dir / f"bg_{i:04d}.png"
                    first_f = self._video_first_frame(path)
                    self._create_blur_bg(first_f, width, height).save(str(bg_p), "PNG")

                    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
                    if self.settings["cropping"]:
                        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"

                    cmd = ['ffmpeg', '-y',
                           '-i', str(path),
                           '-loop', '1', '-i', str(bg_p),
                           '-loop', '1', '-i', str(txt_p),
                           '-filter_complex',
                           f'[0:v]{vf},format=yuv420p[v];[1:v][v]overlay=(W-w)/2:(H-h)/2[base];[base][2:v]overlay=0:0',
                           '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30', '-pix_fmt', 'yuv420p',
                           '-t', str(dur), '-an', str(clip_path)]
                    self._run_ffmpeg_or_raise(cmd, f"encoding video clip {i}")
                    clip_dur = float(dur)

                    # The first frame of a video clip renders only the blurred background.
                    # Skip it so playback starts from the second frame.
                    if m_type == "video" and not clip_files and clip_path.exists():
                        trimmed_path = temp_dir / f"clip_{i:04d}_t.mp4"
                        r = subprocess.run(['ffmpeg', '-y', '-i', str(clip_path),
                                            '-vf', "select='gte(n,1)',setpts=PTS-STARTPTS",
                                            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                                            '-r', '30', '-pix_fmt', 'yuv420p', '-an',
                                            str(trimmed_path)], capture_output=True)
                        if r.returncode == 0 and trimmed_path.exists():
                            clip_path.unlink()
                            trimmed_path.rename(clip_path)
                            clip_dur -= 1 / 30
                        else:
                            # A failed trim can leave a partial file - never use it.
                            if trimmed_path.exists():
                                try:
                                    trimmed_path.unlink()
                                except OSError:
                                    pass
                            self._log_export(f"item {i}: first-frame trim failed, keeping original clip")

                if clip_path.exists():
                    clip_files.append(clip_path)
                    clip_durations.append(clip_dur)
                    total_duration += clip_dur

                self._log_export(f"item {i} [{m_type}] {Path(path).name[:50]}: "
                                 f"clip={'OK' if clip_path.exists() else 'MISSING'} "
                                 f"dur={clip_dur:.2f}s")

            # Merge clips with transitions
            self.progress_var.set(60)
            merged = temp_dir / "merged.mp4"
            self._build_merged_with_transitions(clip_files, clip_durations, temp_dir, merged)
            self._log_export(f"merge: {len(clip_files)} clips, total {total_duration:.1f}s, "
                             f"merged={'OK' if merged.exists() else 'FAILED'}")

            # Apply watermark
            self.progress_var.set(75)
            merged_wm = temp_dir / "merged_wm.mp4"
            self._apply_watermark(merged, merged_wm, width, height)

            # Add Music - use the ACTUAL merged video length (not the raw sum of
            # clips, which is a bit longer because transitions overlap).
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                    '-of', 'default=noprint_wrappers=1:nokey=1', str(merged_wm)],
                                   capture_output=True, text=True)
            try:
                video_dur = float(probe.stdout.strip())
            except:
                # Estimate the merged length from the raw sum of clips, minus the
                # time consumed by xfade transition overlaps. A plain concat
                # (effect "none" or a single clip) has no overlap at all.
                if self.settings.get("transition_effect") != "none" and len(clip_files) > 1:
                    overlaps = (len(clip_files) - 1) * float(self.settings.get("transition_duration", 0.7))
                    video_dur = max(1.0, float(total_duration) - overlaps)
                else:
                    video_dur = max(1.0, float(total_duration))
            self._log_export(f"video duration for music: {video_dur:.1f}s "
                             f"(sum of clips={total_duration:.1f}s)")
            self.finalize_audio_ffmpeg(merged_wm, out_path, video_dur, temp_dir)
            self.progress_var.set(100)
            note = ("\n\nΣημείωση: δεν βρέθηκε μουσική, το βίντεο είναι χωρίς ήχο."
                    if getattr(self, '_export_music_missing', False) else "")
            self.root.after(0, lambda: messagebox.showinfo("Done", "Export Complete!" + note))
        except Exception as e:
            self._log_export(f"EXPORT ERROR: {e}")
            self._log_export(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.root.after(0, lambda: self.status.config(text="Ready"))

    def _log_export(self, msg):
        """Append a debug line to temp/export_log.txt (shows the latest export)."""
        try:
            log = self.app_dir / "temp" / "export_log.txt"
            with open(log, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    def _run_ffmpeg_or_raise(self, cmd, what):
        """Run ffmpeg and surface failures instead of silently dropping content."""
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            err = r.stderr.decode(errors='replace')[-500:]
            self._log_export(f"ffmpeg FAILED {what}: {err}")
            raise RuntimeError(f"ffmpeg failed while {what}:\n{err}")
        return r

    def finalize_audio_ffmpeg(self, vid_p, out_p, duration, temp_dir):
        music = []
        music_dur = 0.0
        rem = duration
        guard = 0
        while rem > 0:
            guard += 1
            if guard > 300:  # safety cap - never loop forever
                self._log_export("music: safety cap reached, stopping selection")
                break
            m = self.get_next_music()
            if not m:
                break
            if not Path(m).exists():
                # The file was deleted but is still listed in the tracker.
                # Skipping it prevents a broken concat and a wrongly shortened
                # music selection (which used to truncate the video via -shortest).
                self.mark_music_used(m)
                self._log_export(f"music: skipped missing file {Path(m).name}")
                continue
            music.append(m)
            self.mark_music_used(m)  # advances the rotation in memory

            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', m], capture_output=True, text=True)
            try:
                d = float(probe.stdout.strip())
                rem -= d
                music_dur += d
                self._log_export(f"music: +{Path(m).name} ({d:.1f}s) rem={rem:.1f}")
            except:
                # Duration unknown - assume ~1s so the loop keeps adding music
                # instead of stopping early and truncating the video.
                rem -= 1
                music_dur += 1
                self._log_export(f"music: +{Path(m).name} (duration unknown, assumed 1s) rem={rem:.1f}")

        self._log_export(f"music: {len(music)} track(s), {music_dur:.1f}s total (video {duration:.1f}s)")

        if not music:
            # No music available - keep the video as-is (silent) instead of erroring.
            self._export_music_missing = True
            tmp_out = out_p.with_name(out_p.stem + "_tmp" + out_p.suffix)
            try:
                self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-i', str(vid_p), '-c', 'copy', str(tmp_out)],
                                          "copying video")
                os.replace(tmp_out, out_p)
            finally:
                try:
                    tmp_out.unlink()
                except OSError:
                    pass
            self._log_export("music: none found, video copied without audio")
            return

        if music_dur < duration - 0.1:
            raise RuntimeError(
                f"Η μουσική που επιλέχθηκε είναι μόνο {music_dur:.0f} δευτ., ενώ το βίντεο θέλει "
                f"{duration:.0f} δευτ. Πρόσθεσε περισσότερα τραγούδια στον φάκελο μουσικής "
                "ή κάνε Refresh Music List στις ρυθμίσεις."
            )

        vol = 10**(self.settings["volume_db"]/20)
        if len(music) == 1:
            cmd = ['ffmpeg', '-y', '-i', str(vid_p), '-i', music[0], '-filter_complex', f'[1:a]volume={vol}[a]', '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(out_p)]
        else:
            list_m = temp_dir / "music.txt"
            with open(list_m, 'w', encoding='utf-8') as f:
                for m in music: f.write(f"file '{str(m).replace(os.sep, '/')}'\n")
            concat_m = temp_dir / "music.m4a"
            self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_m), '-c:a', 'aac', str(concat_m)], "concatenating music")
            # ffmpeg's concat demuxer can report success (rc=0) even when a file
            # was skipped - verify the concatenated music actually covers the video.
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                    '-of', 'default=noprint_wrappers=1:nokey=1', str(concat_m)],
                                   capture_output=True, text=True)
            try:
                concat_dur = float(probe.stdout.strip())
            except:
                concat_dur = 0.0
            self._log_export(f"music: concatenated {concat_dur:.1f}s (video needs {duration:.1f}s)")
            if concat_dur < duration - 0.1:
                raise RuntimeError(
                    f"Η μουσική που επιλέχθηκε είναι μόνο {concat_dur:.0f} δευτ., ενώ το βίντεο θέλει "
                    f"{duration:.0f} δευτ. Πρόσθεσε περισσότερα τραγούδια στον φάκελο μουσικής "
                    "ή κάνε Refresh Music List στις ρυθμίσεις."
                )
            cmd = ['ffmpeg', '-y', '-i', str(vid_p), '-i', str(concat_m), '-filter_complex', f'[1:a]volume={vol}[a]', '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(out_p)]

        # Mux to a temporary file (same dir, valid .mp4 extension so ffmpeg can
        # infer the format) and verify before replacing the destination, so a
        # failed/truncated export never destroys the user's previous output file.
        tmp_out = out_p.with_name(out_p.stem + "_tmp" + out_p.suffix)
        cmd[cmd.index(str(out_p))] = str(tmp_out)
        try:
            self._run_ffmpeg_or_raise(cmd, "mixing music into video")

            # Final safety net: -shortest can truncate the video if the music turned
            # out shorter than expected (e.g. a failed duration probe). Verify the
            # output really keeps the whole video before declaring success.
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                    '-of', 'default=noprint_wrappers=1:nokey=1', str(tmp_out)],
                                   capture_output=True, text=True)
            try:
                out_dur = float(probe.stdout.strip())
            except:
                out_dur = 0.0
            self._log_export(f"music: final output {out_dur:.1f}s (video was {duration:.1f}s)")
            if out_dur < duration - 0.1:
                raise RuntimeError(
                    f"Το τελικό βίντεο βγήκε μόνο {out_dur:.0f} δευτ. ενώ έπρεπε να είναι {duration:.0f} δευτ. "
                    "Μάλλον η μουσική ήταν πιο σύντομη από το βίντεο. Πρόσθεσε περισσότερα τραγούδια "
                    "στον φάκελο μουσικής ή κάνε Refresh Music List στις ρυθμίσεις."
                )
            os.replace(tmp_out, out_p)
        finally:
            try:
                tmp_out.unlink()
            except OSError:
                pass

        # Only now that the output succeeded, persist the used-music marks - so a
        # failed export doesn't burn the music for the next attempt.
        for m in music:
            self.mark_music_used(m)
        self.save_music_tracker()
        self._log_export(f"music: output written ({Path(out_p).name}), {len(music)} track(s) marked used")

    def on_closing(self):
        if not self.is_modified:
            self.root.destroy()
            return
        answer = messagebox.askyesnocancel(
            "Έξοδος",
            "Έχεις αποθηκεύσει το project;\n\nΠάτα 'Yes' για να αποθηκεύσεις και να βγεις,\n'No' για να βγεις χωρίς αποθήκευση,\n'Cancel' για να μείνεις."
        )
        if answer is None:
            # Cancel - μην κλείσεις
            return
        elif answer:
            # Yes - αποθήκευσε και κλείσε
            self.save_project()
            self.root.destroy()
        else:
            # No - κλείσε χωρίς αποθήκευση
            self.root.destroy()

if __name__ == "__main__":
    root = TkinterDnD.Tk() if TKDND_AVAILABLE else tk.Tk()
    SlideshowApp(root)
    root.mainloop()
