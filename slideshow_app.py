import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
import threading
from datetime import datetime
import re
import urllib.parse
import urllib.request

try:
    from PIL import Image, ImageTk, ImageFilter, ImageDraw, ImageFont
    # Fix for Pillow 10+ compatibility with moviepy
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.Resampling.LANCZOS

    from moviepy.editor import (VideoFileClip, ImageClip, concatenate_videoclips,
                                 CompositeVideoClip, AudioFileClip, concatenate_audioclips,
                                 TextClip)
    import numpy as np
    import subprocess
except ImportError as e:
    print(f"Missing dependencies: {e}")
    print("Please install: pip install moviepy pillow numpy")
    exit(1)

# Try to import tkinterdnd2 for drag and drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    print("tkinterdnd2 not available - drag and drop disabled")
    print("To enable: pip install tkinterdnd2")


class SlideshowApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Slideshow Video Creator")
        self.root.geometry("1400x800")

        # Paths
        self.app_dir = Path(__file__).parent
        self.music_dir = self.app_dir / "music"
        self.projects_dir = self.app_dir / "projects"
        self.settings_file = self.app_dir / "settings.json"
        self.music_tracker_file = self.app_dir / "music_tracker.json"

        # Create directories
        self.projects_dir.mkdir(exist_ok=True)
        self.music_dir.mkdir(exist_ok=True)

        # State variables
        self.current_project = None
        self.media_files = []  # List of (type, path) tuples
        self.preview_image = None
        self.is_modified = False
        self.preview_video_path = None
        self.total_duration = 0

        # Load settings and music tracker
        self.load_settings()
        self.load_music_tracker()

        # Setup GUI
        self.setup_menu()
        self.setup_gui()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_settings(self):
        """Load application settings"""
        default_settings = {
            "volume_db": 0,
            "resolution": "1080x1080",
            "background_mode": "white",  # white, black, blur
            "cropping": False,
            "font_size": 24,
            "font_family": "Calibri",
            "text_style": "black_box",  # black_box only
            "auto_position_photos": False,  # Zoom out photos to show text below
            "mute_video_audio": True,  # Mute original video audio, keep only music
            "output_folder": str(self.app_dir),  # Remember last output folder
            "slide_duration": 3  # Seconds per image slide
        }

        if self.settings_file.exists():
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                self.settings = {**default_settings, **json.load(f)}
        else:
            self.settings = default_settings
            self.save_settings()

    def save_settings(self):
        """Save application settings"""
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2)

    def load_music_tracker(self):
        """Load music usage tracker"""
        if self.music_tracker_file.exists():
            with open(self.music_tracker_file, 'r', encoding='utf-8') as f:
                self.music_tracker = json.load(f)
        else:
            self.music_tracker = {
                "used_music": [],
                "available_music": []
            }
            self.refresh_music_list()

    def save_music_tracker(self):
        """Save music usage tracker"""
        with open(self.music_tracker_file, 'w', encoding='utf-8') as f:
            json.dump(self.music_tracker, f, indent=2)

    def refresh_music_list(self):
        """Refresh available music files"""
        if not self.music_dir.exists():
            self.music_tracker["available_music"] = []
            self.save_music_tracker()
            return

        music_files = sorted([str(f.name) for f in self.music_dir.glob("*.mp4")])
        self.music_tracker["available_music"] = music_files
        self.save_music_tracker()
        messagebox.showinfo("Success", f"Found {len(music_files)} music files")

    def get_next_music(self) -> Optional[str]:
        """Get next unused music file"""
        available = self.music_tracker["available_music"]
        used = self.music_tracker["used_music"]

        # Filter out used music
        unused = [m for m in available if m not in used]

        # If all used, reset
        if not unused:
            self.music_tracker["used_music"] = []
            unused = available

        if unused:
            return str(self.music_dir / unused[0])
        return None

    def mark_music_used(self, music_file: str):
        """Mark music file as used"""
        music_name = Path(music_file).name
        if music_name not in self.music_tracker["used_music"]:
            self.music_tracker["used_music"].append(music_name)
            self.save_music_tracker()

    def setup_menu(self):
        """Setup menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project", command=self.new_project)
        file_menu.add_command(label="Load Project", command=self.load_project)
        file_menu.add_command(label="Save Project", command=self.save_project)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        # Settings menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Audio Settings", command=self.show_audio_settings)
        settings_menu.add_command(label="Video Settings", command=self.show_video_settings)
        settings_menu.add_command(label="Text Settings", command=self.show_text_settings)

        # Music menu
        music_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Music", menu=music_menu)
        music_menu.add_command(label="Refresh Music List", command=self.refresh_music_list)
        music_menu.add_command(label="Reset Used Music", command=self.reset_music_tracker)

    def reset_music_tracker(self):
        """Reset music tracker"""
        self.music_tracker["used_music"] = []
        self.save_music_tracker()
        messagebox.showinfo("Success", "Music tracker reset")

    def setup_gui(self):
        """Setup main GUI layout"""
        # Main container
        main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Controls
        left_panel = ttk.Frame(main_container, width=400)
        main_container.add(left_panel, weight=1)

        # Right panel - Preview
        right_panel = ttk.Frame(main_container)
        main_container.add(right_panel, weight=2)

        self.setup_left_panel(left_panel)
        self.setup_right_panel(right_panel)

    def setup_left_panel(self, parent):
        """Setup left control panel"""
        # Project name
        ttk.Label(parent, text="Project Name:", font=("Calibri", 10, "bold")).pack(pady=(10,5), padx=10, anchor='w')
        self.project_name_var = tk.StringVar()
        self.project_name_entry = ttk.Entry(parent, textvariable=self.project_name_var, width=50)
        self.project_name_entry.pack(padx=10, fill='x')
        self.setup_entry_context_menu(self.project_name_entry)

        # Media files section
        ttk.Label(parent, text="Media Files:", font=("Calibri", 10, "bold")).pack(pady=(15,5), padx=10, anchor='w')

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(padx=10, fill='x')
        ttk.Button(btn_frame, text="Add Videos", command=self.add_videos).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Add Images", command=self.add_images).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_media).pack(side='left', padx=2)

        # Media listbox
        list_frame = ttk.Frame(parent)
        list_frame.pack(padx=10, pady=5, fill='x')

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')

        self.media_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=4)
        self.media_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.media_listbox.yview)

        # Setup drag and drop
        self.setup_drag_and_drop()

        # Text section
        ttk.Label(parent, text="Text Overlay (use **text** for bold):", font=("Calibri", 10, "bold")).pack(pady=(10,5), padx=10, anchor='w')
        self.text_input = scrolledtext.ScrolledText(parent, height=10, wrap=tk.WORD)
        self.text_input.pack(padx=10, fill='both', expand=True)

        # Setup context menu for text input
        self.setup_text_context_menu()

        # Output section
        ttk.Label(parent, text="Output Settings:", font=("Calibri", 10, "bold")).pack(pady=(15,5), padx=10, anchor='w')

        # Output folder
        output_frame = ttk.Frame(parent)
        output_frame.pack(padx=10, fill='x', pady=2)
        ttk.Label(output_frame, text="Folder:").pack(side='left')
        self.output_folder_var = tk.StringVar(value=self.settings.get("output_folder", str(self.app_dir)))
        ttk.Entry(output_frame, textvariable=self.output_folder_var, width=30).pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(output_frame, text="Browse", command=self.browse_output_folder).pack(side='left')

        # Output name
        name_frame = ttk.Frame(parent)
        name_frame.pack(padx=10, fill='x', pady=2)
        ttk.Label(name_frame, text="Name:").pack(side='left')
        self.output_name_var = tk.StringVar(value="slideshow")
        self.output_name_entry = ttk.Entry(name_frame, textvariable=self.output_name_var, width=30)
        self.output_name_entry.pack(side='left', padx=5, fill='x', expand=True)
        self.setup_entry_context_menu(self.output_name_entry)

        # Export button
        ttk.Button(parent, text="Export Video", command=self.export_video,
                   style='Accent.TButton').pack(padx=10, pady=15, fill='x')

    def setup_right_panel(self, parent):
        """Setup right preview panel"""
        ttk.Label(parent, text="Preview", font=("Calibri", 12, "bold")).pack(pady=10)

        # Preview canvas
        self.preview_canvas = tk.Canvas(parent, bg='gray', width=540, height=540)
        self.preview_canvas.pack(padx=10, pady=5)

        # Preview button
        ttk.Button(parent, text="Generate Preview", command=self.generate_preview).pack(pady=10)

        # Progress bar
        progress_frame = ttk.Frame(parent)
        progress_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(progress_frame, text="Progress:").pack(side='left', padx=5)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                            maximum=100, mode='determinate')
        self.progress_bar.pack(side='left', fill='x', expand=True, padx=5)
        self.progress_percent = ttk.Label(progress_frame, text="0%", width=5)
        self.progress_percent.pack(side='left')

        # Status label
        self.status_label = ttk.Label(parent, text="Ready", relief='sunken')
        self.status_label.pack(side='bottom', fill='x', padx=10, pady=5)


    def add_videos(self):
        """Add video files"""
        files = filedialog.askopenfilenames(
            title="Select Videos",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")]
        )
        for file in files:
            self.media_files.append(("video", file))
            self.media_listbox.insert(tk.END, f"[VIDEO] {Path(file).name}")
        self.is_modified = True
        self.sort_media_files()

    def add_images(self):
        """Add image files"""
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All files", "*.*")]
        )
        for file in files:
            self.media_files.append(("image", file))
            self.media_listbox.insert(tk.END, f"[IMAGE] {Path(file).name}")
        self.is_modified = True
        self.sort_media_files()

    def sort_media_files(self):
        """Sort media files: videos first, then images"""
        self.media_files.sort(key=lambda x: (0 if x[0] == "video" else 1, x[1]))
        self.update_media_listbox()

    def update_media_listbox(self):
        """Update media listbox display"""
        self.media_listbox.delete(0, tk.END)
        for media_type, path in self.media_files:
            prefix = "[VIDEO]" if media_type == "video" else "[IMAGE]"
            self.media_listbox.insert(tk.END, f"{prefix} {Path(path).name}")

    def clear_media(self):
        """Clear all media files"""
        if messagebox.askyesno("Confirm", "Clear all media files?"):
            self.media_files = []
            self.media_listbox.delete(0, tk.END)
            self.is_modified = True

    def browse_output_folder(self):
        """Browse for output folder"""
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder_var.set(folder)
            # Remember the output folder
            self.settings["output_folder"] = folder
            self.save_settings()

    def setup_text_context_menu(self):
        """Setup right-click context menu for text input"""
        # Create context menu
        self.text_menu = tk.Menu(self.text_input, tearoff=0)
        self.text_menu.add_command(label="Cut", accelerator="Ctrl+X", command=self.text_cut)
        self.text_menu.add_command(label="Copy", accelerator="Ctrl+C", command=self.text_copy)
        self.text_menu.add_command(label="Paste", accelerator="Ctrl+V", command=self.text_paste)
        self.text_menu.add_separator()
        self.text_menu.add_command(label="Select All", accelerator="Ctrl+A", command=self.text_select_all)

        # Bind right-click to show menu
        self.text_input.bind("<Button-3>", self.show_text_menu)

        # Bind keyboard shortcuts (these should work by default, but we make sure)
        self.text_input.bind("<Control-x>", lambda e: self.text_cut())
        self.text_input.bind("<Control-c>", lambda e: self.text_copy())
        self.text_input.bind("<Control-v>", lambda e: self.text_paste())
        self.text_input.bind("<Control-a>", lambda e: self.text_select_all())

    def show_text_menu(self, event):
        """Show context menu at cursor position"""
        try:
            self.text_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.text_menu.grab_release()

    def text_cut(self):
        """Cut text"""
        try:
            self.text_input.event_generate("<<Cut>>")
        except:
            pass
        return "break"

    def text_copy(self):
        """Copy text"""
        try:
            self.text_input.event_generate("<<Copy>>")
        except:
            pass
        return "break"

    def text_paste(self):
        """Paste text"""
        try:
            self.text_input.event_generate("<<Paste>>")
        except:
            pass
        return "break"

    def text_select_all(self):
        """Select all text"""
        try:
            self.text_input.tag_add("sel", "1.0", "end")
            self.text_input.mark_set("insert", "1.0")
            self.text_input.see("insert")
        except:
            pass
        return "break"

    def setup_drag_and_drop(self):
        """Setup drag and drop for media listbox"""
        if TKDND_AVAILABLE:
            # Use tkinterdnd2 if available
            try:
                self.media_listbox.drop_target_register(DND_FILES)
                self.media_listbox.dnd_bind('<<Drop>>', self.handle_drop)
            except Exception as e:
                print(f"Drag and drop setup failed: {e}")
        else:
            # Fallback: Windows native drag and drop using windnd
            try:
                import windnd
                windnd.hook_dropfiles(self.media_listbox, func=self.handle_drop_windnd)
            except ImportError:
                print("Drag and drop not available. Install tkinterdnd2 or windnd")

    def handle_drop(self, event):
        """Handle drag and drop event (tkinterdnd2)"""
        # Get files from event data
        files = self.parse_drop_files(event.data)
        self.add_dropped_files(files)
        return event.action

    def handle_drop_windnd(self, files):
        """Handle drag and drop event (windnd)"""
        self.add_dropped_files(files)

    def parse_drop_files(self, data):
        """Parse dropped files from event data"""
        # Handle different formats
        if isinstance(data, (list, tuple)):
            return data

        # Parse string format (tkinterdnd2)
        files = []
        data = data.strip()

        if data.startswith('{'):
            # Handle grouped format: {file1} {file2}
            import re
            files = re.findall(r'\{([^}]+)\}', data)
        else:
            # Handle space-separated format
            files = data.split()

        # Clean up file paths
        cleaned_files = []
        for f in files:
            f = f.strip('{}')
            if f:
                cleaned_files.append(f)

        return cleaned_files

    def add_dropped_files(self, files):
        """Add dropped files to media list"""
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
        image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}

        added = 0
        for file_path in files:
            file_path = str(file_path).strip()
            if not file_path or not os.path.exists(file_path):
                continue

            # Get file extension
            ext = Path(file_path).suffix.lower()

            if ext in video_exts:
                self.media_files.append(("video", file_path))
                self.media_listbox.insert(tk.END, f"[VIDEO] {Path(file_path).name}")
                added += 1
            elif ext in image_exts:
                self.media_files.append(("image", file_path))
                self.media_listbox.insert(tk.END, f"[IMAGE] {Path(file_path).name}")
                added += 1

        if added > 0:
            self.is_modified = True
            self.sort_media_files()
            messagebox.showinfo("Success", f"Added {added} file(s)")

    def setup_entry_context_menu(self, entry_widget):
        """Setup right-click context menu for Entry widget"""
        # Create context menu
        menu = tk.Menu(entry_widget, tearoff=0)
        menu.add_command(label="Cut", accelerator="Ctrl+X",
                        command=lambda: self.entry_cut(entry_widget))
        menu.add_command(label="Copy", accelerator="Ctrl+C",
                        command=lambda: self.entry_copy(entry_widget))
        menu.add_command(label="Paste", accelerator="Ctrl+V",
                        command=lambda: self.entry_paste(entry_widget))
        menu.add_separator()
        menu.add_command(label="Select All", accelerator="Ctrl+A",
                        command=lambda: self.entry_select_all(entry_widget))

        # Bind right-click
        entry_widget.bind("<Button-3>", lambda e: self.show_entry_menu(e, menu))

        # Bind keyboard shortcuts
        entry_widget.bind("<Control-a>", lambda e: self.entry_select_all(entry_widget))

    def show_entry_menu(self, event, menu):
        """Show context menu for Entry widget"""
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def entry_cut(self, entry_widget):
        """Cut text from Entry widget"""
        try:
            entry_widget.event_generate("<<Cut>>")
        except:
            pass

    def entry_copy(self, entry_widget):
        """Copy text from Entry widget"""
        try:
            entry_widget.event_generate("<<Copy>>")
        except:
            pass

    def entry_paste(self, entry_widget):
        """Paste text to Entry widget"""
        try:
            entry_widget.event_generate("<<Paste>>")
        except:
            pass

    def entry_select_all(self, entry_widget):
        """Select all text in Entry widget"""
        try:
            entry_widget.select_range(0, tk.END)
            entry_widget.icursor(tk.END)
        except:
            pass
        return "break"

    def show_audio_settings(self):
        """Show audio settings dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Audio Settings")
        dialog.geometry("400x280")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Music Volume (dB):", font=("Calibri", 10, "bold")).pack(pady=(15,5))

        volume_frame = ttk.Frame(dialog)
        volume_frame.pack(pady=10)

        volume_var = tk.DoubleVar(value=self.settings["volume_db"])

        ttk.Label(volume_frame, text="-20").pack(side='left')
        volume_slider = ttk.Scale(volume_frame, from_=-20, to=20, orient='horizontal',
                                  variable=volume_var, length=250)
        volume_slider.pack(side='left', padx=10)
        ttk.Label(volume_frame, text="+20").pack(side='left')

        volume_label = ttk.Label(dialog, text=f"{volume_var.get():.1f} dB")
        volume_label.pack()

        def update_label(*args):
            volume_label.config(text=f"{volume_var.get():.1f} dB")

        volume_var.trace('w', update_label)

        # Mute video audio option
        ttk.Label(dialog, text="Video Audio:", font=("Calibri", 10, "bold")).pack(pady=(20,5))
        mute_var = tk.BooleanVar(value=self.settings.get("mute_video_audio", True))
        ttk.Checkbutton(dialog, text="Mute original video audio (keep only music)",
                        variable=mute_var).pack(padx=20)

        def save_audio():
            self.settings["volume_db"] = volume_var.get()
            self.settings["mute_video_audio"] = mute_var.get()
            self.save_settings()
            dialog.destroy()
            messagebox.showinfo("Success", "Audio settings saved")

        ttk.Button(dialog, text="Save", command=save_audio).pack(pady=20)

    def show_video_settings(self):
        """Show video settings dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Video Settings")
        dialog.geometry("500x560")
        dialog.transient(self.root)
        dialog.grab_set()

        # Resolution
        ttk.Label(dialog, text="Resolution:", font=("Calibri", 10, "bold")).pack(pady=(10,5), anchor='w', padx=20)
        resolution_var = tk.StringVar(value=self.settings["resolution"])
        ttk.Radiobutton(dialog, text="1080x1080 (Square)", variable=resolution_var,
                        value="1080x1080").pack(anchor='w', padx=40)
        ttk.Radiobutton(dialog, text="1920x1080 (16:9)", variable=resolution_var,
                        value="1920x1080").pack(anchor='w', padx=40)

        # Background mode
        ttk.Label(dialog, text="Background Mode (for fit without crop):",
                  font=("Calibri", 10, "bold")).pack(pady=(15,5), anchor='w', padx=20)
        bg_mode_var = tk.StringVar(value=self.settings["background_mode"])
        ttk.Radiobutton(dialog, text="White bars", variable=bg_mode_var,
                        value="white").pack(anchor='w', padx=40)
        ttk.Radiobutton(dialog, text="Black bars", variable=bg_mode_var,
                        value="black").pack(anchor='w', padx=40)
        ttk.Radiobutton(dialog, text="Blurred background", variable=bg_mode_var,
                        value="blur").pack(anchor='w', padx=40)

        # Cropping
        ttk.Label(dialog, text="Fit Mode:", font=("Calibri", 10, "bold")).pack(pady=(15,5), anchor='w', padx=20)
        cropping_var = tk.BooleanVar(value=self.settings["cropping"])
        ttk.Checkbutton(dialog, text="Enable cropping (fill frame)",
                        variable=cropping_var).pack(anchor='w', padx=40)

        # Auto position photos
        ttk.Label(dialog, text="Photo Layout:", font=("Calibri", 10, "bold")).pack(pady=(15,5), anchor='w', padx=20)
        auto_pos_var = tk.BooleanVar(value=self.settings.get("auto_position_photos", False))
        ttk.Checkbutton(dialog, text="Auto position photos (zoom out so text is below image)",
                        variable=auto_pos_var).pack(anchor='w', padx=40)

        # Slide duration
        ttk.Label(dialog, text="Slide Duration (seconds):", font=("Calibri", 10, "bold")).pack(pady=(15,5), anchor='w', padx=20)
        duration_var = tk.IntVar(value=self.settings.get("slide_duration", 3))
        duration_frame = ttk.Frame(dialog)
        duration_frame.pack(anchor='w', padx=40)
        ttk.Spinbox(duration_frame, from_=1, to=30, textvariable=duration_var,
                     width=5).pack(side='left')
        ttk.Label(duration_frame, text="sec").pack(side='left', padx=(5,0))

        def save_video():
            self.settings["resolution"] = resolution_var.get()
            self.settings["background_mode"] = bg_mode_var.get()
            self.settings["cropping"] = cropping_var.get()
            self.settings["auto_position_photos"] = auto_pos_var.get()
            self.settings["slide_duration"] = duration_var.get()
            self.save_settings()
            dialog.destroy()
            messagebox.showinfo("Success", "Video settings saved")

        ttk.Button(dialog, text="Save", command=save_video).pack(pady=30)

    def show_text_settings(self):
        """Show text settings dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Text Settings")
        dialog.geometry("400x280")
        dialog.transient(self.root)
        dialog.grab_set()

        # Font size
        ttk.Label(dialog, text="Font Size:", font=("Calibri", 10, "bold")).pack(pady=(10,5), anchor='w', padx=20)

        size_frame = ttk.Frame(dialog)
        size_frame.pack(pady=5, fill='x', padx=40)

        font_size_var = tk.IntVar(value=self.settings["font_size"])
        ttk.Label(size_frame, text="Size:").pack(side='left')
        ttk.Spinbox(size_frame, from_=12, to=72, textvariable=font_size_var,
                    width=10).pack(side='left', padx=10)

        # Font family
        ttk.Label(dialog, text="Font Family:", font=("Calibri", 10, "bold")).pack(pady=(15,5), anchor='w', padx=20)

        family_frame = ttk.Frame(dialog)
        family_frame.pack(pady=5, fill='x', padx=40)

        font_family_var = tk.StringVar(value=self.settings.get("font_family", "Calibri"))
        font_combo = ttk.Combobox(family_frame, textvariable=font_family_var,
                                  values=["Calibri", "Arial", "Times New Roman", "Verdana", "Georgia"])
        font_combo.pack(side='left', fill='x', expand=True)

        # Text style - only black box option
        ttk.Label(dialog, text="Text Style:", font=("Calibri", 10, "bold")).pack(pady=(15,5), anchor='w', padx=20)
        ttk.Label(dialog, text="Black text with white background box",
                  font=("Calibri", 9)).pack(anchor='w', padx=40)

        def save_text():
            self.settings["font_size"] = font_size_var.get()
            self.settings["font_family"] = font_family_var.get()
            self.settings["text_style"] = "black_box"  # Always use black_box
            self.save_settings()
            dialog.destroy()
            messagebox.showinfo("Success", "Text settings saved")

        ttk.Button(dialog, text="Save", command=save_text).pack(pady=30)

    def new_project(self):
        """Create new project"""
        if self.is_modified:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Continue?"):
                return

        self.current_project = None
        self.media_files = []
        self.media_listbox.delete(0, tk.END)
        self.text_input.delete("1.0", tk.END)
        self.project_name_var.set("")
        self.output_name_var.set("slideshow")
        self.is_modified = False

        # Clear preview
        self.preview_canvas.delete("all")
        self.preview_video_path = None

    def save_project(self):
        """Save current project"""
        project_name = self.project_name_var.get().strip()
        if not project_name:
            messagebox.showerror("Error", "Please enter a project name")
            return False  # Return False to indicate save failed

        project_data = {
            "name": project_name,
            "media_files": self.media_files,
            "text": self.text_input.get("1.0", tk.END).strip(),
            "output_folder": self.output_folder_var.get(),
            "output_name": self.output_name_var.get(),
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat()
        }

        # Save to projects folder
        safe_name = "".join(c for c in project_name if c.isalnum() or c in (' ', '-', '_')).strip()
        project_file = self.projects_dir / f"{safe_name}.json"

        with open(project_file, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=2, ensure_ascii=False)

        self.current_project = project_file
        self.is_modified = False
        messagebox.showinfo("Success", f"Project saved: {project_file.name}")
        return True  # Return True to indicate save succeeded

    def load_project(self):
        """Load project with search"""
        # Create search dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Load Project")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Search Projects:", font=("Calibri", 10, "bold")).pack(pady=10, padx=10, anchor='w')

        search_var = tk.StringVar()
        search_entry = ttk.Entry(dialog, textvariable=search_var)
        search_entry.pack(fill='x', padx=10, pady=5)

        # Project listbox
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')

        projects_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        projects_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=projects_listbox.yview)

        # Load project files
        project_files = list(self.projects_dir.glob("*.json"))
        project_data = []

        for pf in project_files:
            try:
                with open(pf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    project_data.append((pf, data))
            except:
                pass

        def update_list(*args):
            projects_listbox.delete(0, tk.END)
            search_term = search_var.get().lower()
            for pf, data in project_data:
                name = data.get("name", pf.stem)
                if search_term in name.lower():
                    projects_listbox.insert(tk.END, name)

        search_var.trace('w', update_list)
        update_list()

        def load_selected():
            selection = projects_listbox.curselection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a project")
                return

            selected_name = projects_listbox.get(selection[0])
            for pf, data in project_data:
                if data.get("name", pf.stem) == selected_name:
                    self.load_project_data(pf, data)
                    dialog.destroy()
                    return

        ttk.Button(dialog, text="Load", command=load_selected).pack(pady=10)

    def load_project_data(self, project_file, data):
        """Load project data into UI"""
        if self.is_modified:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Continue?"):
                return

        self.current_project = project_file
        self.project_name_var.set(data.get("name", ""))
        self.media_files = data.get("media_files", [])
        self.update_media_listbox()
        self.text_input.delete("1.0", tk.END)
        self.text_input.insert("1.0", data.get("text", ""))
        self.output_folder_var.set(data.get("output_folder", str(self.app_dir)))
        self.output_name_var.set(data.get("output_name", "slideshow"))
        self.is_modified = False
        messagebox.showinfo("Success", f"Project loaded: {data.get('name', '')}")

    def generate_preview(self):
        """Generate preview - shows first image with text"""
        if not self.media_files:
            messagebox.showwarning("Warning", "Please add media files first")
            return

        self.status_label.config(text="Generating preview...")
        self.root.update()

        # Run in thread
        threading.Thread(target=self._generate_preview_thread, daemon=True).start()

    def check_nvidia_gpu(self):
        """Check if NVIDIA GPU encoding actually works (not just available)"""
        try:
            # Create a tiny test to see if nvenc actually works
            temp_dir = Path(self.app_dir) / "temp"
            temp_dir.mkdir(exist_ok=True)
            test_file = temp_dir / "nvenc_test.mp4"

            # Try to encode a tiny video with nvenc
            result = subprocess.run([
                'ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
                '-c:v', 'h264_nvenc', '-preset', 'fast',
                str(test_file)
            ], capture_output=True, text=True, timeout=10)

            # Clean up test file
            if test_file.exists():
                test_file.unlink()

            # Check if it succeeded
            return result.returncode == 0
        except Exception as e:
            print(f"NVENC test failed: {e}")
            return False

    def update_progress(self, current, total):
        """Update progress bar"""
        if total > 0:
            percent = (current / total) * 100
            self.root.after(0, lambda: self.progress_var.set(percent))
            self.root.after(0, lambda: self.progress_percent.config(text=f"{int(percent)}%"))

    def _generate_preview_thread(self):
        """Generate preview - just render first image with text (fast!)"""
        try:
            # Reset progress
            self.root.after(0, lambda: self.progress_var.set(0))
            self.root.after(0, lambda: self.progress_percent.config(text="0%"))

            self.root.after(0, lambda: self.status_label.config(text="Rendering preview..."))
            self.update_progress(20, 100)

            # Get first media file
            media_type, path = self.media_files[0]

            # Get settings
            res_parts = self.settings["resolution"].split("x")
            width, height = int(res_parts[0]), int(res_parts[1])
            text = self.text_input.get("1.0", tk.END).strip()

            self.update_progress(50, 100)

            # Render image
            if media_type == "image":
                img = Image.open(path)
            else:  # video - extract first frame
                clip = VideoFileClip(path)
                frame = clip.get_frame(0)
                clip.close()
                img = Image.fromarray(frame.astype('uint8'))

            # Process image based on settings
            auto_position = self.settings.get("auto_position_photos", False)

            # For videos, don't use auto_position (they already use fit with background)
            if auto_position and text and media_type == "image":
                text_height = self.calculate_text_height(text, width)
                img = self.fit_image_with_text_below(img, width, height, text_height)
            elif self.settings["cropping"]:
                img = self.crop_image_to_fill(img, width, height)
            else:
                img = self.fit_image_with_background(img, width, height)

            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Add text overlay
            if text:
                img = self.add_text_to_image(img, text, width, height)

            self.update_progress(80, 100)

            # Display preview
            img_display = img.copy()
            img_display.thumbnail((540, 540), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_display)

            def show_image():
                self.preview_canvas.delete("all")
                self.preview_canvas.create_image(270, 270, image=photo)
                self.preview_canvas.image = photo

            self.root.after(0, show_image)
            self.update_progress(100, 100)
            self.root.after(0, lambda: self.status_label.config(text="Preview ready"))

        except Exception as e:
            print(f"Preview generation error: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: self.status_label.config(text=f"Error: {str(e)}"))

    def create_video_clip(self, is_preview=False):
        """Create video clip from media files - using pre-rendered PNGs for speed"""
        if not self.media_files:
            return None

        # Parse resolution
        res_parts = self.settings["resolution"].split("x")
        width, height = int(res_parts[0]), int(res_parts[1])

        # Use half resolution for preview (much faster)
        if is_preview:
            width = width // 2
            height = height // 2

        # Create temp directory for pre-rendered frames
        temp_dir = Path(self.app_dir) / "temp" / "frames"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Clean old frames
        for old_file in temp_dir.glob("*.png"):
            old_file.unlink()

        clips = []
        # Shorter duration for preview (faster rendering)
        image_duration = 1 if is_preview else self.settings.get("slide_duration", 3)

        # Get text for overlay
        text = self.text_input.get("1.0", tk.END).strip()

        # Process media files
        frame_index = 0
        for media_type, path in self.media_files:
            if media_type == "video":
                # Videos: NO processing, keep original, add text overlay
                clip = self.process_video_clip_with_text(path, width, height, text)
                if clip:
                    clips.append(clip)
            else:  # image
                # Pre-render image with text to PNG file (FAST method)
                clip = self.process_image_clip_fast(path, width, height, image_duration,
                                                     temp_dir, frame_index, text)
                if clip:
                    clips.append(clip)
                    frame_index += 1

        if not clips:
            return None

        # Concatenate clips
        final_clip = concatenate_videoclips(clips, method="compose")

        # Add music (skip for preview - much faster)
        if not is_preview:
            final_clip = self.add_music_to_clip(final_clip)

        return final_clip

    def process_video_clip(self, path, width, height):
        """Process video clip with fit/crop (legacy)"""
        try:
            clip = VideoFileClip(path)

            if self.settings["cropping"]:
                # Crop to fill
                clip = self.crop_to_fill(clip, width, height)
            else:
                # Fit with background
                clip = self.fit_with_background(clip, width, height)

            return clip
        except Exception as e:
            print(f"Video processing error: {e}")
            return None

    def process_video_clip_with_text(self, path, width, height, text=""):
        """Process video using FFMPEG for speed - with proper text wrapping"""
        try:
            temp_dir = Path(self.app_dir) / "temp"
            temp_dir.mkdir(exist_ok=True)

            cpu_count = os.cpu_count() or 8

            # Get background mode
            bg_mode = self.settings.get("background_mode", "white")

            # Step 1: Scale and pad video with ffmpeg (FAST, uses all cores)
            temp_scaled = temp_dir / f"scaled_{hash(path)}.mp4"

            # Use background color based on settings
            if bg_mode == "white":
                bg_color = "white"
            elif bg_mode == "black":
                bg_color = "black"
            else:  # blur - will handle separately
                bg_color = "white"  # Placeholder, will be replaced

            scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease"

            # For blur mode, we need to create blurred background differently
            if bg_mode == "blur":
                # Extract first frame to create blurred background
                temp_frame = temp_dir / f"first_frame_{hash(path)}.png"
                cmd_frame = [
                    'ffmpeg', '-y',
                    '-i', str(path),
                    '-vframes', '1',
                    str(temp_frame)
                ]
                subprocess.run(cmd_frame, capture_output=True, encoding='utf-8', errors='replace')

                # Create blurred background with PIL
                frame_img = Image.open(temp_frame)
                bg_img = frame_img.resize((width, height), Image.Resampling.LANCZOS)
                bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=20))
                bg_png = temp_dir / f"blur_bg_{hash(path)}.png"
                bg_img.save(str(bg_png), "PNG")

                # Scale video and overlay on blurred background
                cmd = [
                    'ffmpeg', '-y',
                    '-threads', str(cpu_count),
                    '-i', str(path),
                    '-i', str(bg_png),
                    '-filter_complex',
                    f"[0:v]{scale_filter}[scaled];[1:v]scale={width}:{height}[bg];[bg][scaled]overlay=(W-w)/2:(H-h)/2",
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '18',
                    '-threads', str(cpu_count),
                ]
            else:
                # For solid colors, use simple pad
                pad_filter = f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={bg_color}"
                cmd = [
                    'ffmpeg', '-y',
                    '-threads', str(cpu_count),
                    '-i', str(path),
                    '-vf', f"{scale_filter},{pad_filter}",
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '18',
                    '-threads', str(cpu_count),
                ]

            if self.settings.get("mute_video_audio", True):
                cmd.extend(['-an'])
            else:
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])

            cmd.append(str(temp_scaled))

            result = subprocess.run(cmd, capture_output=True, text=True,
                                     encoding='utf-8', errors='replace')

            if result.returncode != 0:
                print(f"FFmpeg scale error: {result.stderr}")
                return self.process_video_simple(path)

            # Step 2: Load scaled video
            clip = VideoFileClip(str(temp_scaled))

            # Step 3: Add text overlay using PIL (proper wrapping!)
            if text:
                # Create text overlay image with proper wrapping
                text_img = self.create_text_overlay_image(text, width, height)

                # Save as PNG
                text_png = temp_dir / f"text_overlay_{hash(path)}.png"
                text_img.save(str(text_png), "PNG")

                # Create text clip
                text_clip = ImageClip(str(text_png)).set_duration(clip.duration)

                # Composite (this is fast because it's just overlaying a static image)
                clip = CompositeVideoClip([clip, text_clip])

            return clip

        except Exception as e:
            print(f"Video processing error: {e}")
            return self.process_video_simple(path)

    def create_text_overlay_image(self, text, width, height):
        """Create transparent PNG with properly wrapped text"""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Load fonts
        font_size = self.settings["font_size"]
        font_family = self.settings.get("font_family", "Calibri")

        font_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}.ttf",
            f"C:/Windows/Fonts/{font_family}.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        bold_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}b.ttf",
            f"C:/Windows/Fonts/{font_family}b.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]

        font_regular = None
        font_bold = None

        for path in font_paths:
            try:
                font_regular = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        for path in bold_paths:
            try:
                font_bold = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        if font_regular is None:
            font_regular = ImageFont.load_default()
        if font_bold is None:
            font_bold = font_regular

        # Parse markdown bold
        parts = self.parse_markdown_bold(text)

        # Wrap text
        lines = self.wrap_text(parts, font_regular, font_bold, width - 40)

        # Calculate positions - flush to bottom
        line_height = font_size + 10
        total_text_height = len(lines) * line_height
        padding = 15
        y_start = height - total_text_height - padding

        # Get text style
        text_style = self.settings.get("text_style", "white_shadow")

        # Draw background box for black_box style - SOLID WHITE
        if text_style == "black_box":
            box_top = y_start - padding
            box_bottom = height
            max_line_width = max(lw for _, lw in lines) if lines else 0
            box_left = (width - max_line_width) // 2 - padding
            box_right = (width + max_line_width) // 2 + padding
            draw.rectangle([box_left, box_top, box_right, box_bottom],
                          fill=(255, 255, 255, 255))

        # Draw text
        for line_parts, line_width in lines:
            x = (width - line_width) // 2
            y = y_start

            for is_bold, txt in line_parts:
                font = font_bold if is_bold else font_regular

                if text_style == "white_shadow":
                    draw.text((x + 2, y + 2), txt, font=font, fill=(0, 0, 0, 255))
                    draw.text((x, y), txt, font=font, fill=(255, 255, 255, 255))
                else:
                    draw.text((x, y), txt, font=font, fill=(0, 0, 0, 255))

                bbox = draw.textbbox((x, y), txt, font=font)
                x += bbox[2] - bbox[0]

            y_start += line_height

        return img

    def process_video_simple(self, path):
        """Simple fallback: just load video as-is"""
        try:
            clip = VideoFileClip(path)
            if self.settings.get("mute_video_audio", True):
                clip = clip.without_audio()
            return clip
        except Exception as e:
            print(f"Video load error: {e}")
            return None

    def add_text_overlay_to_video(self, clip, text, width, height):
        """Add text overlay to video clip with SOLID white box"""
        # Create text image (use RGB, not RGBA for solid colors)
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Load fonts
        font_size = self.settings["font_size"]
        font_family = self.settings.get("font_family", "Calibri")

        font_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}.ttf",
            f"C:/Windows/Fonts/{font_family}.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        bold_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}b.ttf",
            f"C:/Windows/Fonts/{font_family}b.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]

        font_regular = None
        font_bold = None

        for path in font_paths:
            try:
                font_regular = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        for path in bold_paths:
            try:
                font_bold = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        if font_regular is None:
            font_regular = ImageFont.load_default()
        if font_bold is None:
            font_bold = font_regular

        # Parse markdown bold
        parts = self.parse_markdown_bold(text)

        # Wrap text
        lines = self.wrap_text(parts, font_regular, font_bold, width - 40)

        # Calculate positions - flush to bottom
        line_height = font_size + 10
        total_text_height = len(lines) * line_height
        padding = 15
        y_start = height - total_text_height - padding

        # Get text style
        text_style = self.settings.get("text_style", "white_shadow")

        # Draw background box for black_box style - SOLID WHITE (no transparency!)
        if text_style == "black_box":
            box_top = y_start - padding
            box_bottom = height  # Flush to bottom
            max_line_width = max(lw for _, lw in lines) if lines else 0
            box_left = (width - max_line_width) // 2 - padding
            box_right = (width + max_line_width) // 2 + padding
            # SOLID WHITE - no alpha!
            draw.rectangle([box_left, box_top, box_right, box_bottom],
                          fill=(255, 255, 255, 255))

        # Draw text
        for line_parts, line_width in lines:
            x = (width - line_width) // 2
            y = y_start

            for is_bold, txt in line_parts:
                font = font_bold if is_bold else font_regular

                if text_style == "white_shadow":
                    draw.text((x + 2, y + 2), txt, font=font, fill=(0, 0, 0, 255))
                    draw.text((x, y), txt, font=font, fill=(255, 255, 255, 255))
                else:  # black_box
                    draw.text((x, y), txt, font=font, fill=(0, 0, 0, 255))

                bbox = draw.textbbox((x, y), txt, font=font)
                x += bbox[2] - bbox[0]

            y_start += line_height

        # Convert to clip
        text_array = np.array(img)
        text_clip = ImageClip(text_array, duration=clip.duration)

        # Composite
        return CompositeVideoClip([clip, text_clip])

    def process_image_clip(self, path, width, height, duration):
        """Process image clip with fit/crop (old method - slower)"""
        try:
            img = Image.open(path)

            if self.settings["cropping"]:
                # Crop to fill
                img = self.crop_image_to_fill(img, width, height)
            else:
                # Fit with background
                img = self.fit_image_with_background(img, width, height)

            # Convert to numpy array
            img_array = np.array(img)
            clip = ImageClip(img_array, duration=duration)

            return clip
        except Exception as e:
            print(f"Image processing error: {e}")
            return None

    def process_image_clip_fast(self, path, width, height, duration, temp_dir, index, text=""):
        """Process image and save to PNG for faster video creation"""
        try:
            img = Image.open(path)

            # Check if auto position photos is enabled
            auto_position = self.settings.get("auto_position_photos", False)

            if auto_position and text:
                # Calculate text height first
                text_height = self.calculate_text_height(text, width)
                # Fit image above text area
                img = self.fit_image_with_text_below(img, width, height, text_height)
            elif self.settings["cropping"]:
                img = self.crop_image_to_fill(img, width, height)
            else:
                img = self.fit_image_with_background(img, width, height)

            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Add text overlay directly to image
            if text:
                img = self.add_text_to_image(img, text, width, height)

            # Save to PNG file
            png_path = temp_dir / f"frame_{index:04d}.png"
            img.save(str(png_path), "PNG")

            # Load as ImageClip from file (this is what makes it fast!)
            clip = ImageClip(str(png_path)).set_duration(duration)

            return clip
        except Exception as e:
            print(f"Image processing error: {e}")
            return None

    def calculate_text_height(self, text, width):
        """Calculate the height needed for text overlay"""
        font_size = self.settings["font_size"]
        font_family = self.settings.get("font_family", "Calibri")

        # Load font
        try:
            font = ImageFont.truetype(f"C:/Windows/Fonts/{font_family.lower()}.ttf", font_size)
        except:
            font = ImageFont.load_default()

        # Parse and wrap text
        parts = self.parse_markdown_bold(text)
        lines = self.wrap_text(parts, font, font, width - 40)

        # Calculate total height
        line_height = font_size + 10
        padding = 15
        return len(lines) * line_height + padding * 2 + 10  # Extra margin

    def fit_image_with_text_below(self, img, target_w, target_h, text_height):
        """Fit image in upper area, leaving space for text below"""
        # Available height for image (excluding text area)
        available_height = target_h - text_height

        # Calculate scaling to fit in available area
        scale = min(target_w / img.width, available_height / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)

        # Resize image
        resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Create background
        bg_mode = self.settings["background_mode"]
        if bg_mode == "white":
            bg = Image.new("RGB", (target_w, target_h), (255, 255, 255))
        elif bg_mode == "black":
            bg = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        elif bg_mode == "blur":
            # Blurred background
            bg = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=20))
        else:
            bg = Image.new("RGB", (target_w, target_h), (255, 255, 255))

        # Center image horizontally, align to top of available area
        x_pos = (target_w - new_w) // 2
        y_pos = (available_height - new_h) // 2  # Center in available area

        bg.paste(resized_img, (x_pos, y_pos))

        return bg

    def add_text_to_image(self, img, text, width, height):
        """Add text overlay directly to PIL image"""
        # Create a copy to draw on
        img = img.copy()
        draw = ImageDraw.Draw(img)

        # Load fonts
        font_size = self.settings["font_size"]
        font_family = self.settings.get("font_family", "Calibri")

        # Font paths for Windows
        font_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}.ttf",
            f"C:/Windows/Fonts/{font_family}.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        bold_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}b.ttf",
            f"C:/Windows/Fonts/{font_family}b.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]

        font_regular = None
        font_bold = None

        for path in font_paths:
            try:
                font_regular = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        for path in bold_paths:
            try:
                font_bold = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        if font_regular is None:
            font_regular = ImageFont.load_default()
        if font_bold is None:
            font_bold = font_regular

        # Parse markdown bold
        parts = self.parse_markdown_bold(text)

        # Wrap text
        lines = self.wrap_text(parts, font_regular, font_bold, width - 40)

        # Calculate positions - flush to bottom
        line_height = font_size + 10
        total_text_height = len(lines) * line_height
        padding = 15
        y_start = height - total_text_height - padding  # Text starts here

        # Get text style
        text_style = self.settings.get("text_style", "white_shadow")

        # Draw background box for black_box style
        if text_style == "black_box":
            box_top = y_start - padding
            box_bottom = height  # Flush to bottom edge
            max_line_width = max(lw for _, lw in lines) if lines else 0
            box_left = (width - max_line_width) // 2 - padding
            box_right = (width + max_line_width) // 2 + padding
            draw.rectangle([box_left, box_top, box_right, box_bottom],
                          fill=(255, 255, 255, 255))

        # Draw text
        for line_parts, line_width in lines:
            x = (width - line_width) // 2
            y = y_start

            for is_bold, txt in line_parts:
                font = font_bold if is_bold else font_regular

                if text_style == "white_shadow":
                    # Draw shadow
                    draw.text((x + 2, y + 2), txt, font=font, fill=(0, 0, 0))
                    # Draw white text
                    draw.text((x, y), txt, font=font, fill=(255, 255, 255))
                else:  # black_box
                    draw.text((x, y), txt, font=font, fill=(0, 0, 0))

                bbox = draw.textbbox((x, y), txt, font=font)
                x += bbox[2] - bbox[0]

            y_start += line_height

        return img

    def crop_to_fill(self, clip, target_w, target_h):
        """Crop video to fill target size"""
        aspect_target = target_w / target_h
        aspect_clip = clip.w / clip.h

        if aspect_clip > aspect_target:
            # Clip is wider, crop sides
            new_w = int(clip.h * aspect_target)
            x_center = clip.w // 2
            x1 = x_center - new_w // 2
            clip = clip.crop(x1=x1, width=new_w)
        else:
            # Clip is taller, crop top/bottom
            new_h = int(clip.w / aspect_target)
            y_center = clip.h // 2
            y1 = y_center - new_h // 2
            clip = clip.crop(y1=y1, height=new_h)

        return clip.resize((target_w, target_h))

    def crop_image_to_fill(self, img, target_w, target_h):
        """Crop image to fill target size"""
        aspect_target = target_w / target_h
        aspect_img = img.width / img.height

        if aspect_img > aspect_target:
            # Image is wider, crop sides
            new_w = int(img.height * aspect_target)
            x_center = img.width // 2
            x1 = x_center - new_w // 2
            img = img.crop((x1, 0, x1 + new_w, img.height))
        else:
            # Image is taller, crop top/bottom
            new_h = int(img.width / aspect_target)
            y_center = img.height // 2
            y1 = y_center - new_h // 2
            img = img.crop((0, y1, img.width, y1 + new_h))

        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def fit_with_background(self, clip, target_w, target_h):
        """Fit video with background"""
        # Calculate scaling
        scale = min(target_w / clip.w, target_h / clip.h)
        new_w = int(clip.w * scale)
        new_h = int(clip.h * scale)

        # Resize clip
        clip = clip.resize((new_w, new_h))

        # Create background
        bg_mode = self.settings["background_mode"]

        if bg_mode == "blur":
            # Blurred background - this is complex for video, use black for now
            bg_color = (0, 0, 0)
        elif bg_mode == "white":
            bg_color = (255, 255, 255)
        else:  # black
            bg_color = (0, 0, 0)

        # Create colored background clip
        bg_clip = ImageClip(np.full((target_h, target_w, 3), bg_color, dtype=np.uint8),
                           duration=clip.duration)

        # Composite
        x_pos = (target_w - new_w) // 2
        y_pos = (target_h - new_h) // 2

        final = CompositeVideoClip([bg_clip, clip.set_position((x_pos, y_pos))])

        return final

    def fit_image_with_background(self, img, target_w, target_h):
        """Fit image with background"""
        # Calculate scaling
        scale = min(target_w / img.width, target_h / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)

        # Resize image
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Create background
        bg_mode = self.settings["background_mode"]

        if bg_mode == "blur":
            # Blurred background
            bg = Image.open(img.filename) if hasattr(img, 'filename') else img.copy()
            bg = bg.resize((target_w, target_h), Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=20))
        elif bg_mode == "white":
            bg = Image.new("RGB", (target_w, target_h), (255, 255, 255))
        else:  # black
            bg = Image.new("RGB", (target_w, target_h), (0, 0, 0))

        # Paste image on background
        x_pos = (target_w - new_w) // 2
        y_pos = (target_h - new_h) // 2
        bg.paste(img, (x_pos, y_pos))

        return bg

    def add_text_overlay(self, clip, text, width, height):
        """Add text overlay with bold support"""
        # Parse markdown bold
        parts = self.parse_markdown_bold(text)

        # Create text image
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Load fonts
        font_size = self.settings["font_size"]
        font_family = self.settings.get("font_family", "Calibri")

        # Font paths for Windows - supports Greek characters
        font_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}.ttf",
            f"C:/Windows/Fonts/{font_family}.ttf",
            "C:/Windows/Fonts/calibri.ttf",  # Fallback with Greek support
            "C:/Windows/Fonts/arial.ttf",     # Another fallback
        ]
        bold_paths = [
            f"C:/Windows/Fonts/{font_family.lower()}b.ttf",
            f"C:/Windows/Fonts/{font_family}b.ttf",
            f"C:/Windows/Fonts/{font_family.lower()}-bold.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]

        font_regular = None
        font_bold = None

        # Try to load regular font
        for path in font_paths:
            try:
                font_regular = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        # Try to load bold font
        for path in bold_paths:
            try:
                font_bold = ImageFont.truetype(path, font_size)
                break
            except:
                continue

        # Fallback to default
        if font_regular is None:
            font_regular = ImageFont.load_default()
        if font_bold is None:
            font_bold = font_regular

        # Draw text with wrapping
        lines = self.wrap_text(parts, font_regular, font_bold, width - 40)

        # Calculate total height
        line_height = font_size + 10
        total_text_height = len(lines) * line_height

        # Position at bottom
        y_start = height - total_text_height - 20

        # Get text style
        text_style = self.settings.get("text_style", "white_shadow")

        # Draw background box for black_box style
        if text_style == "black_box":
            # Calculate box dimensions
            padding = 15
            box_top = y_start - padding
            box_bottom = height - 20 + padding

            # Find max line width
            max_line_width = max(lw for _, lw in lines) if lines else 0
            box_left = (width - max_line_width) // 2 - padding
            box_right = (width + max_line_width) // 2 + padding

            # Draw white rounded rectangle background
            draw.rectangle([box_left, box_top, box_right, box_bottom],
                          fill=(255, 255, 255, 255))

        for line_parts, line_width in lines:
            x = (width - line_width) // 2
            y = y_start

            for is_bold, txt in line_parts:
                font = font_bold if is_bold else font_regular

                if text_style == "white_shadow":
                    # Draw shadow first (offset by 2 pixels)
                    shadow_offset = 2
                    draw.text((x + shadow_offset, y + shadow_offset), txt,
                             font=font, fill=(0, 0, 0, 200))
                    # Draw white text
                    draw.text((x, y), txt, font=font, fill=(255, 255, 255, 255))
                else:  # black_box
                    # Draw black text
                    draw.text((x, y), txt, font=font, fill=(0, 0, 0, 255))

                bbox = draw.textbbox((x, y), txt, font=font)
                x += bbox[2] - bbox[0]

            y_start += line_height

        # Convert to clip
        text_array = np.array(img)
        text_clip = ImageClip(text_array, duration=clip.duration).set_opacity(1.0)

        # Composite
        return CompositeVideoClip([clip, text_clip])

    def parse_markdown_bold(self, text):
        """Parse **bold** markdown - allows spaces inside ** and multiline text"""
        parts = []
        # Use [\s\S] instead of . to match newlines too
        pattern = r'\*\*\s*([\s\S]*?)\s*\*\*'  # Allow spaces and newlines

        last_end = 0
        for match in re.finditer(pattern, text):
            # Add normal text before match
            if match.start() > last_end:
                parts.append((False, text[last_end:match.start()]))
            # Add bold text (trimmed)
            parts.append((True, match.group(1)))
            last_end = match.end()

        # Add remaining text
        if last_end < len(text):
            parts.append((False, text[last_end:]))

        return parts

    def wrap_text(self, parts, font_regular, font_bold, max_width):
        """Wrap text to fit width, respecting manual line breaks (Enter)"""
        lines = []
        current_line = []
        current_width = 0

        for is_bold, text in parts:
            font = font_bold if is_bold else font_regular

            # Split by newlines first to respect manual line breaks
            paragraphs = text.split('\n')

            for p_idx, paragraph in enumerate(paragraphs):
                # If not the first paragraph, force a new line (this is where Enter was pressed)
                if p_idx > 0:
                    if current_line:
                        lines.append((current_line, current_width))
                        current_line = []
                        current_width = 0

                # Now wrap words within this paragraph
                words = paragraph.split()

                for word in words:
                    word_width = font.getlength(word + " ")

                    if current_width + word_width > max_width and current_line:
                        # Start new line due to width
                        lines.append((current_line, current_width))
                        current_line = []
                        current_width = 0

                    current_line.append((is_bold, word + " "))
                    current_width += word_width

        if current_line:
            lines.append((current_line, current_width))

        return lines

    def add_music_to_clip(self, clip):
        """Add music to clip with automatic chaining"""
        music_clips = []
        remaining_duration = clip.duration

        while remaining_duration > 0:
            music_file = self.get_next_music()
            if not music_file:
                break

            try:
                audio = AudioFileClip(music_file)

                # Adjust volume
                volume_db = self.settings["volume_db"]
                volume_factor = 10 ** (volume_db / 20)
                audio = audio.volumex(volume_factor)

                # Trim if needed
                if audio.duration > remaining_duration:
                    audio = audio.subclip(0, remaining_duration)

                music_clips.append(audio)
                self.mark_music_used(music_file)

                remaining_duration -= audio.duration

            except Exception as e:
                print(f"Music processing error: {e}")
                break

        if music_clips:
            # Concatenate music
            final_audio = concatenate_audioclips(music_clips)
            clip = clip.set_audio(final_audio)

        return clip

    def export_video(self):
        """Export final video"""
        if not self.media_files:
            messagebox.showwarning("Warning", "Please add media files first")
            return

        output_name = self.output_name_var.get().strip()
        if not output_name:
            messagebox.showerror("Error", "Please enter output name")
            return

        output_folder = Path(self.output_folder_var.get())
        if not output_folder.exists():
            messagebox.showerror("Error", "Output folder does not exist")
            return

        output_path = output_folder / f"{output_name}.mp4"

        # Check if file already exists
        if output_path.exists():
            # Ask user what to do
            result = messagebox.askyesnocancel(
                "File Exists",
                f"'{output_name}.mp4' already exists.\n\n"
                "Yes = Overwrite\n"
                "No = Auto-rename (add _1, _2, etc.)\n"
                "Cancel = Cancel export"
            )

            if result is None:  # Cancel
                return
            elif result is False:  # No - auto rename
                counter = 1
                while True:
                    new_path = output_folder / f"{output_name}_{counter}.mp4"
                    if not new_path.exists():
                        output_path = new_path
                        break
                    counter += 1
            # If True (Yes), keep original path to overwrite

        self.status_label.config(text="Exporting video...")
        self.root.update()

        # Run in thread
        threading.Thread(target=self._export_thread, args=(output_path,), daemon=True).start()

    def _export_thread(self, output_path):
        """Export video using pure FFMPEG for maximum speed"""
        try:
            # Reset progress
            self.root.after(0, lambda: self.progress_var.set(0))
            self.root.after(0, lambda: self.progress_percent.config(text="0%"))

            temp_dir = Path(self.app_dir) / "temp"
            temp_dir.mkdir(exist_ok=True)

            # Clean temp dir
            for f in temp_dir.glob("*"):
                try:
                    f.unlink()
                except:
                    pass

            resolution = self.settings["resolution"]
            width, height = map(int, resolution.split('x'))
            text = self.text_input.get("1.0", tk.END).strip()
            image_duration = self.settings.get("slide_duration", 3)  # seconds per image
            cpu_count = os.cpu_count() or 8

            # Common encoding settings for all clips
            common_args = [
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                '-r', '30',
                '-pix_fmt', 'yuv420p',
                '-threads', str(cpu_count),
            ]

            clip_files = []
            total_items = len(self.media_files)
            total_duration = 0

            # Step 1: Create individual clip files
            self.root.after(0, lambda: self.status_label.config(text="Preparing clips..."))

            for i, (media_type, path) in enumerate(self.media_files):
                self.update_progress(int((i / total_items) * 50), 100)
                clip_path = temp_dir / f"clip_{i:04d}.mp4"

                if media_type == "image":
                    # Pre-render image with text to PNG
                    png_path = temp_dir / f"frame_{i:04d}.png"
                    self._render_image_to_png(path, png_path, width, height, text)

                    # Convert PNG to video with ffmpeg
                    cmd = [
                        'ffmpeg', '-y',
                        '-loop', '1',
                        '-i', str(png_path),
                        '-t', str(image_duration),
                    ] + common_args + ['-an', str(clip_path)]

                    subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
                    total_duration += image_duration

                else:  # video
                    # Get video duration first
                    probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1', str(path)]
                    result = subprocess.run(probe_cmd, capture_output=True, text=True,
                                           encoding='utf-8', errors='replace')
                    try:
                        vid_duration = float(result.stdout.strip())
                    except:
                        vid_duration = 10
                    total_duration += vid_duration

                    # Pre-render text overlay as PNG
                    text_png = temp_dir / f"text_overlay_{i:04d}.png"
                    text_img = self.create_text_overlay_image(text, width, height)
                    text_img.save(str(text_png), "PNG")

                    # Get background mode
                    bg_mode = self.settings.get("background_mode", "white")
                    scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease"

                    # Handle different background modes
                    if bg_mode == "blur":
                        # Extract first frame to create blurred background
                        temp_frame = temp_dir / f"first_frame_{i:04d}.png"
                        cmd_frame = [
                            'ffmpeg', '-y',
                            '-i', str(path),
                            '-vframes', '1',
                            str(temp_frame)
                        ]
                        subprocess.run(cmd_frame, capture_output=True, encoding='utf-8', errors='replace')

                        # Create blurred background with PIL
                        frame_img = Image.open(temp_frame)
                        bg_img = frame_img.resize((width, height), Image.Resampling.LANCZOS)
                        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=20))
                        bg_png = temp_dir / f"blur_bg_{i:04d}.png"
                        bg_img.save(str(bg_png), "PNG")

                        # Step 1: Create video with blurred background (no text yet)
                        temp_with_bg = temp_dir / f"with_bg_{i:04d}.mp4"
                        cmd_bg = [
                            'ffmpeg', '-y',
                            '-threads', str(cpu_count),
                            '-i', str(path),
                            '-i', str(bg_png),
                            '-filter_complex',
                            f"[0:v]{scale_filter}[scaled];[1:v]scale={width}:{height}[bg];[bg][scaled]overlay=(W-w)/2:(H-h)/2",
                            '-c:v', 'libx264',
                            '-preset', 'fast',
                            '-crf', '18',
                            '-threads', str(cpu_count),
                        ]

                        if self.settings.get("mute_video_audio", True):
                            cmd_bg.append('-an')
                        else:
                            cmd_bg.extend(['-c:a', 'aac', '-b:a', '192k'])

                        cmd_bg.append(str(temp_with_bg))
                        subprocess.run(cmd_bg, capture_output=True, encoding='utf-8', errors='replace')

                        # Step 2: Add text overlay and skip first frame (has bug)
                        cmd = [
                            'ffmpeg', '-y',
                            '-threads', str(cpu_count),
                            '-ss', '0.033',  # Skip first frame (1/30 second)
                            '-i', str(temp_with_bg),
                            '-i', str(text_png),
                            '-filter_complex',
                            f"[0:v][1:v]overlay=0:0",
                        ] + common_args

                        if self.settings.get("mute_video_audio", True):
                            cmd.append('-an')
                        else:
                            cmd.extend(['-c:a', 'copy'])
                    else:
                        # For solid colors (white or black)
                        bg_color = "white" if bg_mode == "white" else "black"
                        pad_filter = f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={bg_color}"

                        cmd = [
                            'ffmpeg', '-y',
                            '-threads', str(cpu_count),
                            '-i', str(path),
                            '-i', str(text_png),
                            '-filter_complex',
                            f"[0:v]{scale_filter},{pad_filter}[bg];[bg][1:v]overlay=0:0",
                        ] + common_args

                    if self.settings.get("mute_video_audio", True):
                        cmd.append('-an')
                    else:
                        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])

                    cmd.append(str(clip_path))
                    subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')

                if clip_path.exists():
                    clip_files.append(clip_path)

            if not clip_files:
                raise Exception("No clips were created")

            # Step 2: Create concat list file
            self.update_progress(55, 100)
            self.root.after(0, lambda: self.status_label.config(text="Concatenating clips..."))

            concat_file = temp_dir / "concat_list.txt"
            with open(concat_file, 'w', encoding='utf-8') as f:
                for clip_path in clip_files:
                    # Use forward slashes and escape single quotes
                    safe_path = str(clip_path).replace('\\', '/').replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            # Step 3: Concatenate all clips (stream copy = FAST!)
            concat_output = temp_dir / "concat_output.mp4"
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',
                str(concat_output)
            ]
            subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')

            # Step 4: Add music
            self.update_progress(70, 100)
            self.root.after(0, lambda: self.status_label.config(text="Adding music..."))

            final_output = self._add_music_ffmpeg(concat_output, output_path, total_duration, temp_dir)

            # Step 5: Done!
            self.update_progress(100, 100)
            self.root.after(0, lambda: messagebox.showinfo("Success",
                                                           f"Video exported:\n{final_output}"))
            self.root.after(0, lambda: self.status_label.config(text="Export complete"))

            # Cleanup temp files (optional - leave for debugging)
            # for f in temp_dir.glob("*"):
            #     try: f.unlink()
            #     except: pass

        except Exception as e:
            print(f"Export error: {e}")
            import traceback
            traceback.print_exc()
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", f"Export failed: {msg}"))
            self.root.after(0, lambda msg=error_msg: self.status_label.config(text=f"Error: {msg}"))

    def _render_image_to_png(self, path, png_path, width, height, text):
        """Render image with text overlay to PNG"""
        try:
            img = Image.open(path)

            auto_position = self.settings.get("auto_position_photos", False)

            if auto_position and text:
                text_height = self.calculate_text_height(text, width)
                img = self.fit_image_with_text_below(img, width, height, text_height)
            elif self.settings["cropping"]:
                img = self.crop_image_to_fill(img, width, height)
            else:
                img = self.fit_image_with_background(img, width, height)

            if img.mode != 'RGB':
                img = img.convert('RGB')

            if text:
                img = self.add_text_to_image(img, text, width, height)

            img.save(str(png_path), "PNG")
        except Exception as e:
            print(f"Image render error: {e}")

    def _add_music_ffmpeg(self, video_path, output_path, video_duration, temp_dir):
        """Add music using ffmpeg"""
        music_files = []
        remaining_duration = video_duration
        cpu_count = os.cpu_count() or 8

        # Collect music files
        while remaining_duration > 0:
            music_file = self.get_next_music()
            if not music_file:
                break

            music_files.append(music_file)
            self.mark_music_used(music_file)

            # Get music duration
            probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', str(music_file)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace')
            try:
                music_duration = float(result.stdout.strip())
            except:
                music_duration = 180  # Default 3 min

            remaining_duration -= music_duration

        if not music_files:
            # No music - just copy video
            import shutil
            shutil.copy(str(video_path), str(output_path))
            return str(output_path)

        # Get volume factor
        volume_db = self.settings["volume_db"]
        volume_factor = 10 ** (volume_db / 20)

        if len(music_files) == 1:
            # Single music file - simple case
            cmd = [
                'ffmpeg', '-y',
                '-threads', str(cpu_count),
                '-i', str(video_path),
                '-i', str(music_files[0]),
                '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '192k',
                '-filter:a', f"volume={volume_factor}",
                '-shortest',
                str(output_path)
            ]
        else:
            # Multiple music files - need to concat audio first
            audio_concat_file = temp_dir / "audio_concat.txt"
            with open(audio_concat_file, 'w', encoding='utf-8') as f:
                for mf in music_files:
                    safe_path = str(mf).replace('\\', '/').replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            # Concat audio
            concat_audio = temp_dir / "concat_audio.m4a"
            cmd_audio = [
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0',
                '-i', str(audio_concat_file),
                '-c:a', 'aac', '-b:a', '192k',
                str(concat_audio)
            ]
            subprocess.run(cmd_audio, capture_output=True, encoding='utf-8', errors='replace')

            # Merge video with concatenated audio
            cmd = [
                'ffmpeg', '-y',
                '-threads', str(cpu_count),
                '-i', str(video_path),
                '-i', str(concat_audio),
                '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '192k',
                '-filter:a', f"volume={volume_factor}",
                '-shortest',
                str(output_path)
            ]

        subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
        return str(output_path)

    def on_closing(self):
        """Handle window close"""
        if self.is_modified:
            result = messagebox.askyesnocancel("Unsaved Changes",
                                              "You have unsaved changes. Save project before closing?")
            if result is None:  # Cancel
                return
            elif result:  # Yes
                # Try to save, and only close if save succeeded
                if not self.save_project():
                    # Save failed (e.g., no project name), don't close
                    return

        self.root.destroy()


def main():
    # Use TkinterDnD if available, otherwise regular Tk
    if TKDND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except:
            root = tk.Tk()
    else:
        root = tk.Tk()

    app = SlideshowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
