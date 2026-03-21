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
        self.project_text = ""
        self._resize_timer = None

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
            "music_folder": str(self.app_dir / "music"), "crossfade_duration": 3, "trim_silence": True
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
            self.save_music_tracker()

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
        scale = ttk.Scale(vol_frame, from_=-20, to=20, variable=volume_var, length=200)
        scale.pack(side='left', padx=10)
        v_lbl = ttk.Label(vol_frame, text=f"{volume_var.get():.1f} dB")
        v_lbl.pack(side='left')
        volume_var.trace('w', lambda *a: v_lbl.config(text=f"{volume_var.get():.1f} dB"))
        
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
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        res_var = tk.StringVar(value=self.settings["resolution"])
        ttk.Label(dialog, text="Resolution:", font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')
        ttk.Radiobutton(dialog, text="1080x1080 (Square)", variable=res_var, value="1080x1080").pack(padx=40, anchor='w')
        ttk.Radiobutton(dialog, text="1920x1080 (16:9)", variable=res_var, value="1920x1080").pack(padx=40, anchor='w')
        
        bg_var = tk.StringVar(value=self.settings["background_mode"])
        ttk.Label(dialog, text="Background Mode:", font=("Calibri", 10, "bold")).pack(padx=20, pady=(15,5), anchor='w')
        for m in ["white", "black", "blur"]:
            ttk.Radiobutton(dialog, text=m.capitalize(), variable=bg_var, value=m).pack(padx=40, anchor='w')
            
        crop_var = tk.BooleanVar(value=self.settings["cropping"])
        ttk.Checkbutton(dialog, text="Enable Cropping (Fill Frame)", variable=crop_var).pack(padx=20, pady=(15,5), anchor='w')
        
        pos_img_var = tk.BooleanVar(value=self.settings.get("auto_position_photos", False))
        ttk.Checkbutton(dialog, text="Auto position photos (Text below)", variable=pos_img_var).pack(padx=20, pady=5, anchor='w')
        
        pos_vid_var = tk.BooleanVar(value=self.settings.get("auto_position_videos", False))
        ttk.Checkbutton(dialog, text="Auto position videos (Text below)", variable=pos_vid_var).pack(padx=20, pady=5, anchor='w')
        
        dur_var = tk.IntVar(value=self.settings["slide_duration"])
        ttk.Label(dialog, text="Slide Duration (sec):").pack(padx=20, pady=(15,5), anchor='w')
        ttk.Spinbox(dialog, from_=1, to=30, textvariable=dur_var, width=10).pack(padx=40, anchor='w')
        
        def save():
            self.settings.update({
                "resolution": res_var.get(), "background_mode": bg_var.get(), 
                "cropping": crop_var.get(), "slide_duration": dur_var.get(), 
                "auto_position_photos": pos_img_var.get(), "auto_position_videos": pos_vid_var.get()
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
        ttk.Label(right, text="Preview", font=("Calibri", 12, "bold")).pack(pady=(10,0))
        self.preview_box = tk.Canvas(right, bg='black', width=540, height=540)
        self.preview_box.pack(pady=10)
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
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()
        txt = scrolledtext.ScrolledText(dialog, wrap=tk.WORD)
        txt.pack(fill='both', expand=True, padx=10, pady=10)
        txt.insert("1.0", self.project_text)
        m = tk.Menu(txt, tearoff=0)
        m.add_command(label="Copy", command=lambda: txt.event_generate("<<Copy>>"))
        m.add_command(label="Paste", command=lambda: txt.event_generate("<<Paste>>"))
        txt.bind("<Button-3>", lambda e: m.tk_popup(e.x_root, e.y_root))
        def save():
            self.project_text = txt.get("1.0", tk.END).strip()
            dialog.destroy()
        ttk.Button(dialog, text="Quick Paste Clipboard", command=lambda: txt.insert(tk.INSERT, self.root.clipboard_get())).pack(side='left', padx=10, pady=10)
        ttk.Button(dialog, text="Apply Text", command=save).pack(side='right', padx=10, pady=10)

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
                        clip = VideoFileClip(p)
                        img = Image.fromarray(clip.get_frame(0).astype('uint8'))
                        clip.close()
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
            self.update_media_display()

    def add_images(self):
        fs = filedialog.askopenfilenames(filetypes=[("Image", "*.jpg *.jpeg *.png *.bmp")])
        for f in fs:
            self.media_files.append(("image", f))
        if fs:
            self.update_media_display()

    def clear_media(self):
        self.media_files = []
        self.update_media_display()

    def new_project(self):
        self.name_var.set("")
        self.media_files = []
        self.project_text = ""
        self.update_media_display()

    def save_project(self):
        n = self.name_var.get().strip()
        data = {
            "name": n, 
            "media_files": self.media_files, 
            "text": self.project_text, 
            "out": self.out_var.get()
        }
        p = self.projects_dir / f"{re.sub(r'\W+', '_', n)}.json"
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Saved", "Project saved.")

    def load_project(self):
        d = tk.Toplevel(self.root)
        lb = tk.Listbox(d, width=50)
        lb.pack(padx=10, pady=10)
        pfs = sorted(list(self.projects_dir.glob("*.json")), key=os.path.getmtime, reverse=True)
        for p in pfs:
            lb.insert(tk.END, p.stem)
        def do_load():
            if not lb.curselection():
                return
            with open(pfs[lb.curselection()[0]], 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.name_var.set(data.get("name", ""))
                self.media_files = data.get("media_files", data.get("media", []))
                self.project_text = data.get("text", "")
                self.out_var.set(data.get("out", ""))
                self.update_media_display()
                d.destroy()
        ttk.Button(d, text="Load", command=do_load).pack(pady=5)

    def generate_preview(self):
        if not self.media_files:
            return
        threading.Thread(target=self._preview_task, daemon=True).start()

    def _preview_task(self):
        try:
            t, p = self.media_files[0]
            res = self.settings["resolution"].split('x')
            w, h = int(res[0]), int(res[1])
            if t == "image":
                img = Image.open(p)
            else:
                v = VideoFileClip(p)
                img = Image.fromarray(v.get_frame(0).astype('uint8'))
                v.close()
            
            img = self._fit_image_logic(img, w, h, t)
            img = self.render_text_on_image(img, self.project_text, w, h)
            img.thumbnail((540, 540))
            tk_p = ImageTk.PhotoImage(img)
            self.root.after(0, lambda: [self.preview_box.delete("all"), self.preview_box.create_image(270, 270, image=tk_p), setattr(self.preview_box, 'img', tk_p)])
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _create_blur_bg(self, img, tw, th):
        iw, ih = img.size
        ratio = max(tw/iw, th/ih)
        bg = img.resize((int(iw*ratio), int(ih*ratio)), Image.Resampling.LANCZOS)
        x0 = (bg.width - tw) // 2
        y0 = (bg.height - th) // 2
        return bg.crop((x0, y0, x0 + tw, y0 + th)).filter(ImageFilter.GaussianBlur(30))

    def _fit_image_logic(self, img, tw, th, m_type):
        auto_pos = self.settings.get("auto_position_photos" if m_type == "image" else "auto_position_videos", False)
        iw, ih = img.size
        lh = self.settings["font_size"] + 5
        lines = len(self.project_text.split('\n'))
        
        bg_m = self.settings["background_mode"]
        if bg_m == "blur":
            bg = self._create_blur_bg(img, tw, th)
        else:
            bg = Image.new("RGB", (tw, th), (255,255,255) if bg_m == "white" else (0,0,0))
        
        if auto_pos:
            av_h = th - (lines * lh + 40)
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

    def render_text_on_image(self, img, text, w, h):
        if not text:
            return img
        img = img.copy().convert("RGBA")
        draw = ImageDraw.Draw(img)
        fs = self.settings["font_size"]
        try:
            font = ImageFont.truetype("calibri.ttf", fs)
            f_bold = ImageFont.truetype("calibrib.ttf", fs)
        except:
            font = f_bold = ImageFont.load_default()
        
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
            for p in txt.split('\n'):
                for word in p.split():
                    ww = f.getlength(word + " ")
                    if cur_w + ww > w-60 and cur_line:
                        lines.append((cur_line, cur_w))
                        cur_line = []
                        cur_w = 0
                    cur_line.append((is_b, word + " "))
                    cur_w += ww
                if cur_line:
                    lines.append((cur_line, cur_w))
                    cur_line = []
                    cur_w = 0
        
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
        return img.convert("RGB")

    def export_video(self):
        n = self.name_var.get().strip()
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

            clip_files = []
            total_duration = 0

            for i, (m_type, path) in enumerate(self.media_files):
                self.progress_var.set((i / len(self.media_files)) * 50)
                clip_path = temp_dir / f"clip_{i:04d}.mp4"

                if m_type == "image":
                    png_path = temp_dir / f"frame_{i:04d}.png"
                    img = Image.open(path)
                    img = self._fit_image_logic(img, width, height, m_type)
                    img = self.render_text_on_image(img, self.project_text, width, height)
                    img.save(str(png_path), "PNG")

                    cmd = ['ffmpeg', '-y', '-loop', '1', '-i', str(png_path), '-t', str(image_duration), '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30', '-pix_fmt', 'yuv420p', '-an', str(clip_path)]
                    subprocess.run(cmd, capture_output=True)
                    total_duration += image_duration
                else:
                    v = VideoFileClip(path)
                    dur = v.duration
                    v.close()
                    total_duration += dur

                    txt_overlay = Image.new("RGBA", (width, height), (0,0,0,0))
                    txt_overlay = self.render_text_on_image(txt_overlay, self.project_text, width, height)
                    txt_p = temp_dir / f"txt_{i:04d}.png"
                    txt_overlay.save(str(txt_p), "PNG")

                    bg_p = temp_dir / f"bg_{i:04d}.png"
                    v_temp = VideoFileClip(path)
                    first_f = Image.fromarray(v_temp.get_frame(0).astype('uint8'))
                    self._create_blur_bg(first_f, width, height).save(str(bg_p), "PNG")
                    v_temp.close()

                    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
                    if self.settings["cropping"]:
                        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
                    
                    cmd = ['ffmpeg', '-y', '-i', str(path), '-i', str(bg_p), '-i', str(txt_p), '-filter_complex', f'[0:v]{vf},format=yuv420p[v];[1:v][v]overlay=(W-w)/2:(H-h)/2[base];[base][2:v]overlay=0:0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30', '-pix_fmt', 'yuv420p', '-an', str(clip_path)]
                    subprocess.run(cmd, capture_output=True)

                if clip_path.exists():
                    clip_files.append(clip_path)

            concat_file = temp_dir / "list.txt"
            with open(concat_file, 'w', encoding='utf-8') as f:
                for c in clip_files:
                    f.write(f"file '{str(c).replace(os.sep, '/')}'\n")

            merged = temp_dir / "merged.mp4"
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_file), '-c', 'copy', str(merged)], capture_output=True)

            # Add Music
            self.finalize_audio_ffmpeg(merged, out_path, total_duration, temp_dir)
            self.progress_var.set(100)
            self.root.after(0, lambda: messagebox.showinfo("Done", "Export Complete!"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.root.after(0, lambda: self.status.config(text="Ready"))

    def finalize_audio_ffmpeg(self, vid_p, out_p, duration, temp_dir):
        music = []
        rem = duration
        while rem > 0:
            m = self.get_next_music()
            if not m: break
            music.append(m)
            self.mark_music_used(m)
            
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', m], capture_output=True, text=True)
            try: rem -= float(probe.stdout.strip())
            except: rem -= 180

        if not music:
            subprocess.run(['ffmpeg', '-y', '-i', str(vid_p), '-c', 'copy', str(out_p)], capture_output=True)
            return

        vol = 10**(self.settings["volume_db"]/20)
        if len(music) == 1:
            cmd = ['ffmpeg', '-y', '-i', str(vid_p), '-i', music[0], '-filter_complex', f'[1:a]volume={vol}[a]', '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(out_p)]
        else:
            list_m = temp_dir / "music.txt"
            with open(list_m, 'w', encoding='utf-8') as f:
                for m in music: f.write(f"file '{str(m).replace(os.sep, '/')}'\n")
            concat_m = temp_dir / "music.m4a"
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_m), '-c:a', 'aac', str(concat_m)], capture_output=True)
            cmd = ['ffmpeg', '-y', '-i', str(vid_p), '-i', str(concat_m), '-filter_complex', f'[1:a]volume={vol}[a]', '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(out_p)]
        
        subprocess.run(cmd, capture_output=True)

    def on_closing(self):
        self.root.destroy()

if __name__ == "__main__":
    root = TkinterDnD.Tk() if TKDND_AVAILABLE else tk.Tk()
    SlideshowApp(root)
    root.mainloop()
