"""The Settings menus and the watermark/logo dialogs."""

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
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog, colorchooser

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)
from .ui_color_controls import ColorControls


class SettingsMixin:
    """The Settings menus and the watermark/logo dialogs."""

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
        settings_menu.add_command(label="Photo Settings", command=self.show_photo_settings)
        settings_menu.add_command(label="Text Settings", command=self.show_text_settings)
        settings_menu.add_command(label="AI / DeepSeek (Βελτίωση κειμένου)", command=self.show_ai_settings)
        settings_menu.add_command(label="Σβήσιμο αντικειμένων (μοντέλο AI)", command=self.show_erase_settings)
        settings_menu.add_command(label="Watermark / Logo Settings", command=self.show_watermark_settings)


    def _scrollable(self, dialog, canvas_height=560):
        """A scrollable body + a fixed bottom bar, for the settings dialogs.

        Returns ``(body, bottom)``: build content into ``body`` and action
        buttons into ``bottom``. The dialog itself stays a stable, resizable
        window and the wheel scrolls over any of its children.
        """
        bottom = ttk.Frame(dialog)
        bottom.pack(side='bottom', fill='x', padx=10, pady=(0, 10))
        canvas = tk.Canvas(dialog, highlightthickness=0, height=canvas_height)
        sb = ttk.Scrollbar(dialog, orient='vertical', command=canvas.yview)
        body = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=body, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        dialog.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        return body, bottom


    def show_audio_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Audio & Music Settings")
        dialog.geometry("560x640")
        dialog.minsize(480, 420)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        body, bottom = self._scrollable(dialog, 560)

        ttk.Label(body, text="General Audio", font=("Calibri", 11, "bold")).pack(pady=(15,5), padx=20, anchor='w')
        vol_frame = ttk.Frame(body)
        vol_frame.pack(fill='x', padx=30, pady=5)
        ttk.Label(vol_frame, text="Music Volume (dB):").pack(side='left')
        volume_var = tk.DoubleVar(value=self.settings.get("volume_db", 0))
        scale = ttk.Scale(vol_frame, from_=-60, to=20, variable=volume_var, length=200)
        scale.pack(side='left', padx=10)
        v_lbl = ttk.Label(vol_frame, text=f"{volume_var.get():.1f} dB")
        v_lbl.pack(side='left')
        volume_var.trace_add('write', lambda *a: v_lbl.config(text=f"{volume_var.get():.1f} dB"))
        
        mute_var = tk.BooleanVar(value=self.settings.get("mute_video_audio", True))
        ttk.Checkbutton(body, text="Mute original video audio", variable=mute_var).pack(padx=30, anchor='w')
        
        ttk.Separator(body).pack(fill='x', padx=20, pady=15)
        ttk.Label(body, text="Music Library", font=("Calibri", 11, "bold")).pack(padx=20, anchor='w')
        
        folder_var = tk.StringVar(value=self.settings.get("music_folder", ""))
        ff = ttk.Frame(body)
        ff.pack(fill='x', padx=30, pady=5)
        ttk.Entry(ff, textvariable=folder_var).pack(side='left', fill='x', expand=True)
        def browse():
            f = filedialog.askdirectory()
            if f:
                folder_var.set(f)
        ttk.Button(ff, text="Browse", command=browse).pack(side='right')
        
        af = ttk.Frame(body)
        af.pack(fill='x', padx=30, pady=10)
        ttk.Button(af, text="Refresh Music List", command=self.refresh_music_list).pack(side='left', padx=5)
        ttk.Button(af, text="Reset Used Music", command=self.reset_music_tracker).pack(side='left', padx=5)
        
        ttk.Separator(body).pack(fill='x', padx=20, pady=15)
        ttk.Label(body, text="Processing", font=("Calibri", 11, "bold")).pack(padx=20, anchor='w')
        
        cf_var = tk.IntVar(value=self.settings.get("crossfade_duration", 3))
        ttk.Label(body, text="Crossfade (sec):").pack(padx=30, anchor='w')
        ttk.Spinbox(body, from_=0, to=10, textvariable=cf_var).pack(padx=30, anchor='w')
        
        trim_var = tk.BooleanVar(value=self.settings.get("trim_silence", True))
        ttk.Checkbutton(body, text="Auto Trim Silence", variable=trim_var).pack(padx=30, anchor='w', pady=5)
        
        def save():
            self.settings.update({
                "volume_db": volume_var.get(), "mute_video_audio": mute_var.get(), 
                "music_folder": folder_var.get(), "crossfade_duration": cf_var.get(), 
                "trim_silence": trim_var.get()
            })
            self.save_settings()
            self.refresh_music_list(silent=True)
            self._schedule_preview()
            dialog.destroy()
        ttk.Button(bottom, text="Save Settings", command=save).pack(side='right')


    def show_video_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Video Settings")
        dialog.transient(self.root)
        dialog.grab_set()

        nb = ttk.Notebook(dialog)
        nb.pack(fill='both', expand=True, padx=10, pady=(10, 0))

        # ------------------------------------------------ Κάδρο & Ανάλυση
        tab_frame = ttk.Frame(nb)
        nb.add(tab_frame, text="  Κάδρο & Ανάλυση  ")

        res_var = tk.StringVar(value=self.settings["resolution"])
        ttk.Label(tab_frame, text="Resolution:", font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')
        for label, value in [
            ("1080x1080 (Square)", "1080x1080"),
            ("1920x1080 (16:9)", "1920x1080"),
            ("1080x1920 (9:16 Portrait)", "1080x1920"),
            ("1080x1350 (4:5 Portrait)", "1080x1350"),
            ("720x1280 (9:16 HD)", "720x1280"),
        ]:
            ttk.Radiobutton(tab_frame, text=label, variable=res_var, value=value).pack(padx=40, anchor='w')

        bg_var = tk.StringVar(value=self.settings["background_mode"])
        ttk.Label(tab_frame, text="Background Mode:", font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')
        for label, value in [("White", "white"), ("Black", "black"), ("Blur", "blur"), ("Fit and Move", "fit_and_move")]:
            ttk.Radiobutton(tab_frame, text=label, variable=bg_var, value=value).pack(padx=40, anchor='w')

        crop_var = tk.BooleanVar(value=self.settings["cropping"])
        crop_cb = ttk.Checkbutton(tab_frame, text="Enable Cropping (Fill Frame)", variable=crop_var)
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
        ttk.Checkbutton(tab_frame, text="Auto position photos (Text below)", variable=pos_img_var).pack(padx=20, pady=5, anchor='w')

        pos_vid_var = tk.BooleanVar(value=self.settings.get("auto_position_videos", False))
        ttk.Checkbutton(tab_frame, text="Auto position videos (Text below)", variable=pos_vid_var).pack(padx=20, pady=5, anchor='w')

        # ------------------------------------------------ Slides & Εφέ
        tab_slides = ttk.Frame(nb)
        nb.add(tab_slides, text="  Slides & Εφέ  ")

        dur_var = tk.IntVar(value=self.settings["slide_duration"])
        ttk.Label(tab_slides, text="Slide Duration (sec):").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Spinbox(tab_slides, from_=1, to=30, textvariable=dur_var, width=10).pack(padx=40, anchor='w')

        ttk.Separator(tab_slides).pack(fill='x', padx=20, pady=15)
        ttk.Label(tab_slides, text="Transitions (between clips)", font=("Calibri", 10, "bold")).pack(padx=20, anchor='w')

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

        tr_f = ttk.Frame(tab_slides)
        tr_f.pack(fill='x', padx=30, pady=5)
        ttk.Label(tr_f, text="Effect:").pack(side='left')
        tr_effect_var = tk.StringVar(value=current_label)
        tr_combo = ttk.Combobox(tr_f, textvariable=tr_effect_var,
                                values=[lbl for lbl, _ in TRANSITION_EFFECTS],
                                state='disabled' if is_random else 'readonly', width=18)
        tr_combo.pack(side='left', padx=10)

        td_f = ttk.Frame(tab_slides)
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
        random_container = ttk.Frame(tab_slides)
        random_container.pack(fill='x', padx=30)

        random_sub_frame = ttk.LabelFrame(random_container, text="Εφέ που συμπεριλαμβάνονται στο Random")

        for lbl, val in RANDOM_EFFECTS:
            ttk.Checkbutton(random_sub_frame, text=lbl, variable=random_effect_vars[val]).pack(anchor='w', padx=10, pady=1)

        def toggle_random():
            if random_var.get():
                tr_combo.config(state='disabled')
                random_sub_frame.pack(fill='x', pady=(5, 0))
            else:
                tr_combo.config(state='readonly')
                random_sub_frame.pack_forget()

        ttk.Checkbutton(random_container, text="Random", variable=random_var, command=toggle_random).pack(anchor='w', pady=5)

        if is_random:
            random_sub_frame.pack(fill='x', pady=(5, 0))

        # ------------------------------------------------ Φως & Κορεσμός
        tab_color = ttk.Frame(nb)
        nb.add(tab_color, text="  Φως & Κορεσμός  ")

        ttk.Label(tab_color, text="Καθολική φωτεινότητα & κορεσμός για ΟΛΑ τα βίντεο",
                  font=("Calibri", 10, "bold")).pack(padx=20, pady=(15, 2), anchor='w')
        ttk.Label(tab_color, text="Πολλαπλασιάζονται με τις ατομικές ρυθμίσεις κάθε βίντεο (Edit).",
                  foreground="#666", font=("Calibri", 8)).pack(padx=20, anchor='w')
        color_ui = ColorControls(tab_color,
                                 brightness=self.settings.get("video_brightness", 1.0),
                                 color=self.settings.get("video_color", 1.0))
        color_ui.frame.pack(padx=20, pady=12, anchor='w')

        # ------------------------------------------------ Ήχος βίντεο
        tab_audio = ttk.Frame(nb)
        nb.add(tab_audio, text="  Ήχος  ")

        audio_var = tk.BooleanVar(value=bool(self.settings.get("video_audio", False)))
        ttk.Label(tab_audio, text="Ήχος βίντεο (καθολικό)",
                  font=("Calibri", 10, "bold")).pack(padx=20, pady=(15, 2), anchor='w')
        ttk.Checkbutton(tab_audio, text="Ακούγεται ο ήχος των βίντεο (μαζί με τη μουσική)",
                        variable=audio_var).pack(padx=20, pady=(4, 2), anchor='w')
        ttk.Label(tab_audio,
                  text="Αν είναι off, όλα τα βίντεο γίνονται mute (ακούγεται μόνο η μουσική).\n"
                       "Κάθε βίντεο μπορεί να το αλλάξει ξεχωριστά από το Edit (εικονίδιο 🔊 / 🔇).",
                  foreground="#666", font=("Calibri", 8), justify='left').pack(padx=20, anchor='w')

        ttk.Separator(tab_audio).pack(fill='x', padx=20, pady=14)
        ttk.Label(tab_audio, text="Ένταση ήχου βίντεο (dB)",
                  font=("Calibri", 10, "bold")).pack(padx=20, pady=(0, 2), anchor='w')
        vvol_frame = ttk.Frame(tab_audio)
        vvol_frame.pack(fill='x', padx=20, pady=4)
        vvol_var = tk.DoubleVar(value=float(self.settings.get("video_audio_volume_db", 0) or 0))
        ttk.Scale(vvol_frame, from_=-60, to=20, variable=vvol_var, length=260).pack(side='left')
        vvol_lbl = ttk.Label(vvol_frame, width=9)
        vvol_lbl.pack(side='left', padx=8)
        vvol_var.trace_add('write', lambda *a: vvol_lbl.config(text=f"{vvol_var.get():.1f} dB"))
        vvol_lbl.config(text=f"{vvol_var.get():.1f} dB")
        ttk.Label(tab_audio, text="Ισχύει όταν ο ήχος των βίντεο είναι ενεργός (αρνητικές = πιο σιγά).",
                  foreground="#666", font=("Calibri", 8)).pack(padx=20, anchor='w')

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
            vb, vc = color_ui.values()
            self.settings.update({
                "resolution": res_var.get(), "background_mode": bg_var.get(),
                "cropping": crop_var.get(), "slide_duration": dur_var.get(),
                "auto_position_photos": pos_img_var.get(), "auto_position_videos": pos_vid_var.get(),
                "transition_effect": chosen_value, "transition_duration": round(tr_dur_var.get(), 1),
                "random_transitions": selected_randoms,
                "video_brightness": vb, "video_color": vc,
                "video_audio": bool(audio_var.get()),
                "video_audio_volume_db": round(vvol_var.get(), 1)
            })
            self.save_settings()
            self.update_media_display()
            dialog.destroy()
        ttk.Button(dialog, text="Save Settings", command=save).pack(pady=15)


    def show_photo_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Photo Settings")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Καθολική φωτεινότητα & κορεσμός για ΟΛΕΣ τις φωτογραφίες",
                  font=("Calibri", 10, "bold")).pack(padx=20, pady=(15, 2), anchor='w')
        ttk.Label(dialog, text="Πολλαπλασιάζονται με τις ατομικές ρυθμίσεις κάθε φωτογραφίας (Edit).",
                  foreground="#666", font=("Calibri", 8)).pack(padx=20, anchor='w')

        color_ui = ColorControls(dialog,
                                 brightness=self.settings.get("photo_brightness", 1.0),
                                 color=self.settings.get("photo_color", 1.0))
        color_ui.frame.pack(padx=20, pady=12, anchor='w')

        row = ttk.Frame(dialog)
        row.pack(pady=15)
        ttk.Button(row, text="Επαναφορά", command=lambda: (color_ui.brightness.set(1.0),
                                                           color_ui.color.set(1.0))).pack(side='left', padx=5)

        def save():
            b, c = color_ui.values()
            self.settings.update({"photo_brightness": b, "photo_color": c})
            self.save_settings()
            self.update_media_display()
            dialog.destroy()
        ttk.Button(row, text="Save Settings", command=save).pack(side='left', padx=5)


    def show_text_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Text Settings")
        dialog.geometry("460x420")
        dialog.minsize(380, 300)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        body, bottom = self._scrollable(dialog, 360)
        
        size_var = tk.IntVar(value=self.settings["font_size"])
        ttk.Label(body, text="Font Size:").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Spinbox(body, from_=10, to=150, textvariable=size_var).pack(padx=40, anchor='w')
        
        fam_var = tk.StringVar(value=self.settings["font_family"])
        ttk.Label(body, text="Font Family:").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Combobox(body, textvariable=fam_var, values=["Calibri", "Arial", "Verdana", "Georgia"]).pack(padx=40, anchor='w', fill='x')
        
        def save():
            self.settings.update({"font_size": size_var.get(), "font_family": fam_var.get()})
            self.save_settings()
            self._schedule_preview()
            dialog.destroy()
        ttk.Button(bottom, text="Save Settings", command=save).pack(side='right')


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
        dialog.geometry("500x430")
        dialog.minsize(420, 340)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        body, bottom = self._scrollable(dialog, 370)

        enabled_var = tk.BooleanVar(value=self.settings.get("watermark_enabled", False))
        ttk.Checkbutton(body, text="Enable watermark on all videos", variable=enabled_var).pack(padx=20, pady=(15,5), anchor='w')

        wm_data = {
            "path": self.settings.get("watermark_path", ""),
            "position": self.settings.get("watermark_position", "bottom_right"),
            "size_pct": self.settings.get("watermark_size_pct", 15),
            "opacity": self.settings.get("watermark_opacity", 80)
        }
        get_values = self._build_watermark_ui(body, wm_data)

        ttk.Separator(body).pack(fill='x', padx=20, pady=14)
        ttk.Label(body, text="Text watermark (όνομα / τηλέφωνο)",
                  font=("Calibri", 10, "bold")).pack(padx=20, anchor='w')
        t_enabled = tk.BooleanVar(value=self.settings.get("watermark_text_enabled", False))
        ttk.Checkbutton(body, text="Enable text watermark", variable=t_enabled).pack(
            padx=20, pady=(4, 2), anchor='w')

        tf = ttk.Frame(body)
        tf.pack(fill='x', padx=20, pady=4)
        ttk.Label(tf, text="Text:").pack(side='left')
        t_text = tk.StringVar(value=self.settings.get("watermark_text", ""))
        ttk.Entry(tf, textvariable=t_text).pack(side='left', fill='x', expand=True, padx=(6, 0))

        POSITIONS = [("Bottom Right", "bottom_right"), ("Bottom Left", "bottom_left"),
                     ("Top Right", "top_right"), ("Top Left", "top_left"), ("Center", "center")]
        cur_tpos = next((lbl for lbl, val in POSITIONS
                         if val == self.settings.get("watermark_text_position", "bottom_left")),
                        "Bottom Left")
        tpf = ttk.Frame(body)
        tpf.pack(fill='x', padx=20, pady=4)
        ttk.Label(tpf, text="Position:").pack(side='left')
        t_pos = tk.StringVar(value=cur_tpos)
        ttk.Combobox(tpf, textvariable=t_pos, values=[l for l, _ in POSITIONS],
                     state='readonly', width=13).pack(side='left', padx=6)

        tsf = ttk.Frame(body)
        tsf.pack(fill='x', padx=20, pady=4)
        ttk.Label(tsf, text="Size (% of height):").pack(side='left')
        t_size = tk.IntVar(value=self.settings.get("watermark_text_size_pct", 6))
        ttk.Spinbox(tsf, from_=3, to=30, textvariable=t_size, width=6).pack(side='left', padx=6)

        tof = ttk.Frame(body)
        tof.pack(fill='x', padx=20, pady=4)
        ttk.Label(tof, text="Opacity (%):").pack(side='left')
        t_op = tk.IntVar(value=self.settings.get("watermark_text_opacity", 90))
        t_op_lbl = ttk.Label(tof, text=f"{t_op.get()}%")
        ttk.Scale(tof, from_=10, to=100, variable=t_op, length=150).pack(side='left', padx=6)
        t_op_lbl.pack(side='left')
        t_op.trace_add('write', lambda *a: t_op_lbl.config(text=f"{int(t_op.get())}%"))

        tcf = ttk.Frame(body)
        tcf.pack(fill='x', padx=20, pady=(4, 10))
        ttk.Label(tcf, text="Color:").pack(side='left')
        t_color = tk.StringVar(value=self.settings.get("watermark_text_color", "#ffffff"))
        color_lbl = tk.Label(tcf, text="      ", bg=t_color.get(), relief='solid', borderwidth=1)
        color_lbl.pack(side='left', padx=6)

        def pick_color():
            chosen = colorchooser.askcolor(color=t_color.get())
            if chosen and chosen[1]:
                t_color.set(chosen[1])
                color_lbl.config(bg=chosen[1])
        ttk.Button(tcf, text="Διάλεξε", command=pick_color).pack(side='left')

        def save():
            vals = get_values()
            tpos_val = next((val for lbl, val in POSITIONS if lbl == t_pos.get()), "bottom_left")
            self.settings.update({
                "watermark_enabled": enabled_var.get(),
                "watermark_path": vals["path"], "watermark_position": vals["position"],
                "watermark_size_pct": vals["size_pct"], "watermark_opacity": vals["opacity"],
                "watermark_text_enabled": bool(t_enabled.get()),
                "watermark_text": t_text.get().strip(),
                "watermark_text_position": tpos_val,
                "watermark_text_size_pct": t_size.get(),
                "watermark_text_opacity": int(t_op.get()),
                "watermark_text_color": t_color.get(),
            })
            self.save_settings()
            self._schedule_preview()
            dialog.destroy()
        ttk.Button(bottom, text="Save Settings", command=save).pack(side='right')


    def show_project_watermark(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Logo Override")
        dialog.geometry("500x450")
        dialog.minsize(420, 360)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        body, bottom = self._scrollable(dialog, 390)

        ttk.Label(body, text="Override global watermark for this project:",
                  font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')

        enabled_var = tk.BooleanVar(value=self.project_watermark.get("enabled", False))
        ttk.Checkbutton(body, text="Enable project logo override", variable=enabled_var).pack(padx=20, pady=5, anchor='w')

        get_values = self._build_watermark_ui(body, self.project_watermark)

        def save():
            vals = get_values()
            vals["enabled"] = enabled_var.get()
            self.project_watermark = vals
            self._schedule_preview()
            dialog.destroy()
        ttk.Button(bottom, text="Apply to Project", command=save).pack(side='right')

