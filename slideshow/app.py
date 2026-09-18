"""SlideshowApp — the application shell: settings, projects, music, lifecycle.

The feature code lives in mixins; this class just composes them, so every
`self.<method>` keeps working exactly as it did in the single-file version.
"""

import json
import os
import re
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
from typing import Dict, List, Optional

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)
from .media_edit import MediaEditMixin
from .render import RenderMixin
from .export import ExportMixin
from .ui_library import LibraryMixin
from .ui_editors import EditorsMixin
from .ui_photo_editor import PhotoEditorMixin
from .ui_erase import EraseSettingsMixin
from .ui_timeline import TimelineMixin
from .ui_settings import SettingsMixin
from .ui_layout import LayoutMixin
from .ui_preview import PreviewMixin
from .ui_text import TextInputMixin
from .ui_ai_text import AITextMixin, DEFAULT_BASE_URL


# Where settings.json, projects/, music/, temp/ and models/ live.
# - normal run: the folder that holds the launcher (parent of this package)
# - frozen .exe: the folder that holds the .exe, so the build is portable
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent


class SlideshowApp(MediaEditMixin, RenderMixin, ExportMixin, LibraryMixin, EditorsMixin, PhotoEditorMixin, EraseSettingsMixin, TimelineMixin, SettingsMixin, LayoutMixin, PreviewMixin, TextInputMixin, AITextMixin):
    """Composes every mixin above into the one application object."""

    def __init__(self, root):
        self.root = root
        self.root.title("Slideshow Video Creator Pro")
        self.root.geometry("1550x950")

        self.app_dir = APP_DIR
        self._use_local_ffmpeg()
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
        self.project_ai_instructions = ""
        self._resize_timer = None
        self._preview_job = None
        self._export_cancel = False
        self._export_proc = None
        self._video_frame_cache = {}  # first-frame per video path (rotation-corrected)
        self._video_dur_cache = {}    # duration per video path (library display)
        self.selected_indices = set()  # library selection (Ctrl/Shift for many)
        self._sel_anchor = None
        self._undo_stack = []
        self._redo_stack = []
        self.project_watermark = {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        }

        self.load_settings()
        self.view_mode.set(self.settings.get("view_mode", "thumbnails"))
        self.load_music_tracker()
        self.setup_menu()
        self.setup_gui()
        self.setup_shortcuts()
        self._restore_window_state()

        # Warm the LaMa erase model in the background: creating its ONNX
        # session costs ~20s, and doing it at startup means the user's first
        # erase is instant instead of a 20s freeze.
        try:
            self._erase_engine().prewarm()
        except Exception:
            pass

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def setup_shortcuts(self):
        """Keyboard shortcuts for the most common actions."""
        self.root.bind("<Control-s>", lambda e: self._shortcut(self.save_project))
        self.root.bind("<Control-S>", lambda e: self._shortcut(self.save_project))
        self.root.bind("<Control-o>", lambda e: self._shortcut(self.load_project))
        self.root.bind("<Control-O>", lambda e: self._shortcut(self.load_project))
        self.root.bind("<Control-n>", lambda e: self._shortcut(self.new_project))
        self.root.bind("<Control-N>", lambda e: self._shortcut(self.new_project))
        self.root.bind("<Control-z>", lambda e: self._shortcut(self.undo))
        self.root.bind("<Control-Z>", lambda e: self._shortcut(self.undo))
        self.root.bind("<Control-y>", lambda e: self._shortcut(self.redo))
        self.root.bind("<Control-Y>", lambda e: self._shortcut(self.redo))
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<F5>", lambda e: self._shortcut(self.generate_preview))

    @staticmethod
    def _is_text_widget(widget):
        return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox))

    def _shortcut(self, func):
        # Never steal Ctrl combos while the user types in an entry/text box.
        if self._is_text_widget(self.root.focus_get()):
            return None
        func()
        return "break"

    def _on_delete_key(self, event):
        if self._is_text_widget(self.root.focus_get()):
            return None
        self.delete_selected()
        return "break"


    def _restore_window_state(self):
        """Restore the main window size/position and the library splitter."""
        geo = self.settings.get("window_geometry")
        if geo:
            try:
                self.root.geometry(geo)
            except tk.TclError:
                pass

        def apply_sash():
            if not hasattr(self, "main_paned"):
                return
            width = self.main_paned.winfo_width()
            if width <= 1:
                width = self.root.winfo_width()
            sash = self.settings.get("library_sash")
            if sash is None:
                pos = max(200, width // 2)          # default: half and half
            else:
                # never let a stale value hide one of the two panels
                pos = max(int(width * 0.2), min(int(width * 0.8), int(sash)))
            try:
                self.main_paned.sashpos(0, pos)
            except tk.TclError:
                pass
        self.root.after(150, apply_sash)


    def _save_window_state(self):
        try:
            if self.root.state() == "normal":
                self.settings["window_geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        if hasattr(self, "main_paned"):
            try:
                self.settings["library_sash"] = self.main_paned.sashpos(0)
            except tk.TclError:
                pass
        self.settings["view_mode"] = self.view_mode.get()



    def _use_local_ffmpeg(self):
        """Prefer a bundled FFmpeg placed next to the app by install.ps1.

        The installer drops ffmpeg.exe / ffprobe.exe in an ``ffmpeg`` folder so
        the app works on a PC without FFmpeg in the system PATH. Prepending the
        folder here means every ``subprocess`` call finds it first.
        """
        local = self.app_dir / "ffmpeg"
        if (local / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(local) + os.pathsep + os.environ.get("PATH", "")
            return
        # A frozen build can also carry ffmpeg inside its bundle.
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle and (Path(bundle) / "ffmpeg" / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(Path(bundle) / "ffmpeg") + os.pathsep + os.environ.get("PATH", "")


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
            "watermark_size_pct": 15, "watermark_opacity": 80,
            # Text watermark (e.g. name / phone) - independent of the image logo.
            "watermark_text_enabled": False, "watermark_text": "",
            "watermark_text_position": "bottom_left",
            "watermark_text_size_pct": 6, "watermark_text_opacity": 90,
            "watermark_text_color": "#ffffff",
            # Remembered size of the photo/video Edit dialogs.
            "edit_fullscreen": False,
            # Global brightness / saturation applied to every photo or video,
            # on top of each item's own Edit values (they multiply).
            "photo_brightness": 1.0, "photo_color": 1.0,
            "video_brightness": 1.0, "video_color": 1.0,
            # Whether the sound of the source videos is heard at all (mixed under
            # the music). Each video can override this from its Edit dialog.
            "video_audio": False,
            "video_audio_volume_db": 0,
            # Inpainting model for object erasing ("lama" or "migan").
            "erase_model": "lama",
            # Optional AI text improvement (inert until a key is stored here;
            # the per-project instructions live in the project JSON instead).
            "ai_enabled": False, "ai_api_key": "", "ai_model": "deepseek-chat",
            "ai_base_url": DEFAULT_BASE_URL, "ai_global_instructions": ""
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


    def reset_music_tracker(self):
        self.music_tracker["used_music"] = []
        self.save_music_tracker()
        messagebox.showinfo("Reset", "Music tracker reset. All songs are available again.")


    def new_project(self):
        self.name_var.set("")
        self.media_files = []
        self.project_text_videos = ""
        self.project_text_photos = ""
        self.project_ai_instructions = ""
        self.project_watermark = {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        }
        self.update_media_display()


    def save_project(self):
        """Save the project. Returns True when it was saved, False otherwise.

        A project without a name is refused (that used to create a stray
        ``.json`` file and an empty entry in the Load list) and the name field
        is focused so the user can fix it.
        """
        n = self.name_var.get().strip()
        if not n:
            messagebox.showwarning(
                "Λείπει το όνομα",
                "Γράψε πρώτα ένα όνομα για το project (πεδίο «Project Name», πάνω-δεξιά) "
                "και μετά πάτα Αποθήκευση.")
            self._focus_name_entry()
            return False

        safe = re.sub(r'\W+', '_', n).strip('_')
        if not safe:
            messagebox.showwarning(
                "Μη έγκυρο όνομα",
                "Το όνομα πρέπει να περιέχει τουλάχιστον ένα γράμμα ή αριθμό.")
            self._focus_name_entry()
            return False

        data = {
            "name": n,
            "media_files": self.media_files,
            "text": self.project_text_videos,
            "text_videos": self.project_text_videos,
            "text_photos": self.project_text_photos,
            "ai_instructions": self.project_ai_instructions,
            "out": self.out_var.get(),
            "project_watermark": self.project_watermark
        }
        p = self.projects_dir / f"{safe}.json"
        try:
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            messagebox.showerror("Σφάλμα", f"Δεν μπόρεσα να αποθηκεύσω το project:\n{e}")
            return False
        self.is_modified = False
        messagebox.showinfo("Saved", "Project saved.")
        return True


    def _focus_name_entry(self):
        entry = getattr(self, "name_entry", None)
        if entry is None:
            return
        try:
            entry.focus_set()
            entry.selection_range(0, tk.END)
        except tk.TclError:
            pass


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

        def display_name(p):
            # A project saved without a name (older bug) has an empty stem.
            return p.stem or "(χωρίς όνομα)"

        for p in pfs:
            lb.insert(tk.END, display_name(p))
        
        def filter_projects(*args):
            search_text = search_var.get().lower()
            lb.delete(0, tk.END)
            for p in pfs:
                if search_text in display_name(p).lower():
                    lb.insert(tk.END, display_name(p))
        
        search_var.trace_add('write', filter_projects)
        
        def do_load():
            if not lb.curselection():
                return
            # Find the actual index in pfs matching the selected display name
            selected_name = lb.get(lb.curselection()[0])
            for idx, p in enumerate(pfs):
                if display_name(p) == selected_name:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.name_var.set(data.get("name", ""))
                        self.media_files = self.normalize_media_list(
                            data.get("media_files", data.get("media", [])))
                        old_text = data.get("text", "")
                        self.project_text_videos = data.get("text_videos", old_text)
                        self.project_text_photos = data.get("text_photos", "")
                        self.project_ai_instructions = data.get("ai_instructions", "")
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
                if display_name(old_path) == selected_name:
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
                if display_name(old_path) == selected_name:
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
                if display_name(old_path) == selected_name:
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


    def on_closing(self):
        self._save_window_state()
        try:
            self.save_settings()
        except Exception:
            pass
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
            # Yes - αποθήκευσε και κλείσε (αν λείπει όνομα, μείνε ανοιχτό)
            if not self.save_project():
                return
            self.root.destroy()
        else:
            # No - κλείσε χωρίς αποθήκευση
            self.root.destroy()

