"""The media library: adding/removing/reordering items and their badges.

Supports single and multi selection (Ctrl/Shift + click), drag & drop reorder,
video duration + file name tooltips, and Undo/Redo for structural changes.
"""

import copy
import re
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from .deps import Image, ImageTk


class LibraryMixin:
    """The media library: adding/removing/reordering items and their badges."""

    # ----------------------------------------------------------- undo/redo
    def push_undo(self):
        """Snapshot the media list before a structural change."""
        self._undo_stack.append(copy.deepcopy(self.media_files))
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(copy.deepcopy(self.media_files))
        self.media_files = self._undo_stack.pop()
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(copy.deepcopy(self.media_files))
        self.media_files = self._redo_stack.pop()
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()

    # ------------------------------------------------------------ adding
    def import_media(self):
        """File → Import Media...: pick any mix of photos and videos at once."""
        fs = filedialog.askopenfilenames(
            title="Import Media",
            filetypes=[("Media (φωτογραφίες & βίντεο)",
                        "*.jpg *.jpeg *.png *.bmp *.mp4 *.avi *.mov *.mkv"),
                       ("Video", "*.mp4 *.avi *.mov *.mkv"),
                       ("Image", "*.jpg *.jpeg *.png *.bmp"),
                       ("All files", "*.*")])
        added = False
        for f in fs:
            ext = Path(f).suffix.lower()
            if ext in ('.mp4', '.avi', '.mov', '.mkv'):
                self.media_files.append(self._new_item("video", f))
                added = True
            elif ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                self.media_files.append(self._new_item("image", f))
                added = True
        if added:
            self.is_modified = True
            self.update_media_display()

    def handle_drop(self, data):
        files = re.findall(r'\{([^}]*)\}', data) if '{' in data else data.split()
        added = False
        for f in files:
            f = f.strip('{} ')
            ext = Path(f).suffix.lower()
            if ext in ('.mp4', '.avi', '.mov', '.mkv'):
                self.media_files.append(self._new_item("video", f))
                added = True
            elif ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                self.media_files.append(self._new_item("image", f))
                added = True
        if added:
            self.is_modified = True
            self.update_media_display()

    def add_videos(self):
        fs = filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv")])
        if fs:
            for f in fs:
                self.media_files.append(self._new_item("video", f))
            self.is_modified = True
            self.update_media_display()

    def add_images(self):
        fs = filedialog.askopenfilenames(filetypes=[("Image", "*.jpg *.jpeg *.png *.bmp")])
        if fs:
            for f in fs:
                self.media_files.append(self._new_item("image", f))
            self.is_modified = True
            self.update_media_display()

    def clear_media(self):
        if self.media_files and not messagebox.askyesno(
                "Καθαρισμός", "Να αδειάσει όλη η βιβλιοθήκη;\n\n(Μπορείς να το αναιρέσεις με Undo)"):
            return
        self.push_undo()
        self.media_files = []
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()

    # ---------------------------------------------------------- selection
    def _selected(self):
        return sorted(i for i in self.selected_indices if 0 <= i < len(self.media_files))

    def _select_click(self, idx, event):
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if ctrl:
            if idx in self.selected_indices:
                self.selected_indices.discard(idx)
            else:
                self.selected_indices.add(idx)
            self._sel_anchor = idx
        elif shift and self._sel_anchor is not None:
            a, b = sorted((self._sel_anchor, idx))
            self.selected_indices = set(range(a, b + 1))
        else:
            self.selected_indices = {idx}
            self._sel_anchor = idx
        self._refresh_selection()

    def _refresh_selection(self):
        mode = self.view_mode.get()
        for i, w in enumerate(getattr(self, "_item_widgets", [])):
            sel = i in self.selected_indices
            try:
                if mode == "list":
                    w.config(bg='#cfe3ff' if sel else '#eee')
                else:
                    w.config(highlightbackground='#2d6cdf' if sel else '#cccccc',
                             highlightthickness=2 if sel else 1)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ display
    def update_media_display(self):
        self.selected_indices = {i for i in self.selected_indices
                                 if 0 <= i < len(self.media_files)}
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self.thumbnails = []
        self._item_widgets = []
        if self.view_mode.get() == "list":
            self._build_list()
        else:
            self._build_icons()
        self._refresh_selection()
        self._schedule_preview()

    def _media_duration(self, m_type, path):
        if m_type != "video":
            return ""
        key = str(path)
        d = self._video_dur_cache.get(key)
        if d is None:
            try:
                d = self._video_duration(path)
            except Exception:
                d = 0.0
            self._video_dur_cache[key] = d
        return f"  ⏱ {self._tl_mmss(d)}" if d and d > 0 else ""

    def _build_list(self):
        for i, (t, p, ed) in enumerate(self.media_files):
            icon = "▶" if t == "video" else "▦"
            mark = "  ✎" if self.has_edit(ed) else ""
            text = f"{i+1}. {icon} [{t.upper()}] {Path(p).name}{self._media_duration(t, p)}{mark}"
            lbl = tk.Label(self.thumb_frame, text=text, anchor='w', bg='#eee', padx=10, pady=2)
            lbl.pack(fill='x')
            self._item_widgets.append(lbl)
            self._bind_item(lbl, i)
            self._add_tooltip(lbl, p)

    def _build_icons(self):
        w_limit = self.media_canvas.winfo_width() - 30
        cols = max(1, w_limit // 145) if w_limit > 100 else 4
        for i, (t, p, ed) in enumerate(self.media_files):
            outer = tk.Frame(self.thumb_frame, bg='#f4f4f4', bd=0,
                             highlightthickness=1, highlightbackground='#cccccc')
            r, c = divmod(i, cols)
            outer.grid(row=r, column=c, padx=5, pady=5, sticky='n')
            self._item_widgets.append(outer)
            try:
                if t == "image":
                    img = Image.open(p)
                else:
                    img = self._video_first_frame(p)
                thumb_edit = {k: v for k, v in ed.items() if k != "erase"}
                img = self._apply_image_edit(img.copy(), thumb_edit, p, m_type=t)
                img.thumbnail((120, 120))
                tk_img = ImageTk.PhotoImage(img)
                self.thumbnails.append(tk_img)
                lbl = tk.Label(outer, image=tk_img, bg="black")
                lbl.pack(padx=1, pady=1)
                tk.Label(outer, text=str(i + 1), font=("Calibri", 9, "bold"),
                         fg="#111", bg="#ffcc00", padx=5).place(x=2, y=2)
                if t == "video":
                    tk.Label(outer, text="▶ VIDEO", font=("Calibri", 7, "bold"),
                             fg="white", bg="#c0392b", padx=3).place(relx=1.0, x=-2, y=2, anchor='ne')
                    dur = self._media_duration(t, p)
                    if dur:
                        tk.Label(outer, text=dur.strip(), font=("Calibri", 7, "bold"),
                                 fg="white", bg="#333", padx=3).place(
                            relx=0.0, rely=1.0, x=2, y=-2, anchor='sw')
                if self.has_edit(ed):
                    tk.Label(outer, text="✎", font=("Calibri", 9, "bold"),
                             fg="white", bg="#2d6cdf", padx=4).place(
                        relx=1.0, x=-2, rely=1.0, y=-2, anchor='se')
            except Exception:
                tk.Label(outer, text="Error").pack()
            self._bind_tree(outer, i)
            self._add_tooltip(outer, p)

    # -------------------------------------------------------- item events
    def _bind_tree(self, widget, idx):
        self._bind_item(widget, idx)
        for c in widget.winfo_children():
            self._bind_tree(c, idx)

    def _bind_item(self, w, idx):
        w.bind("<Button-1>", lambda e, i=idx: self._on_item_press(e, i))
        w.bind("<B1-Motion>", lambda e, i=idx: self._on_item_motion(e, i))
        w.bind("<ButtonRelease-1>", lambda e, i=idx: self._on_item_release(e, i))
        w.bind("<Double-Button-1>", lambda e, i=idx: self.open_edit_dialog(i))
        w.bind("<Button-3>", lambda e, i=idx: self.media_menu(e, i))

    def _on_item_press(self, event, idx):
        if idx not in self.selected_indices or (event.state & 0x0004):
            self._select_click(idx, event)
        self._drag = {"idx": idx, "x0": event.x_root, "y0": event.y_root, "moved": False}

    def _on_item_motion(self, event, idx):
        d = getattr(self, "_drag", None)
        if not d:
            return
        if not d["moved"] and (abs(event.x_root - d["x0"]) + abs(event.y_root - d["y0"])) < 6:
            return
        d["moved"] = True
        self._show_drop_marker(self._index_at_pointer(event.x_root, event.y_root))

    def _on_item_release(self, event, idx):
        d = getattr(self, "_drag", None)
        self._drag = None
        if not d or not d["moved"]:
            return
        self._move_selection_to(self._index_at_pointer(event.x_root, event.y_root))

    def _index_at_pointer(self, xr, yr):
        best, bd = None, float("inf")
        for i, w in enumerate(getattr(self, "_item_widgets", [])):
            try:
                x, y = w.winfo_rootx(), w.winfo_rooty()
                ww, hh = w.winfo_width(), w.winfo_height()
            except tk.TclError:
                continue
            if x <= xr <= x + ww and y <= yr <= y + hh:
                return i
            cx, cy = x + ww / 2, y + hh / 2
            dist = (xr - cx) ** 2 + (yr - cy) ** 2
            if dist < bd:
                bd, best = dist, i
        return best

    def _show_drop_marker(self, tgt):
        mode = self.view_mode.get()
        for i, w in enumerate(getattr(self, "_item_widgets", [])):
            try:
                if mode == "list":
                    w.config(bg='#ffe9a8' if i == tgt else
                             ('#cfe3ff' if i in self.selected_indices else '#eee'))
                else:
                    w.config(highlightbackground='#e67e22' if i == tgt else
                             ('#2d6cdf' if i in self.selected_indices else '#cccccc'))
            except tk.TclError:
                pass

    def _move_selection_to(self, target):
        sel = self._selected()
        if not sel or target is None or target in sel:
            self._refresh_selection()
            return
        before = sum(1 for i in sel if i < target)
        insert_at = target - before
        block = [self.media_files[i] for i in sel]
        rest = [m for i, m in enumerate(self.media_files) if i not in self.selected_indices]
        self.push_undo()
        for m in block:
            rest.insert(insert_at, m)
            insert_at += 1
        self.media_files = rest
        self.selected_indices = set(range(target - before, target - before + len(block)))
        self._sel_anchor = min(self.selected_indices) if self.selected_indices else None
        self.is_modified = True
        self.update_media_display()

    # ----------------------------------------------------------- tooltips
    def _add_tooltip(self, widget, path):
        def show(_e=None):
            hide()
            try:
                self._tooltip = tk.Toplevel(self.root)
                self._tooltip.wm_overrideredirect(True)
                self._tooltip.attributes("-topmost", True)
                x = widget.winfo_rootx() + 12
                y = widget.winfo_rooty() + widget.winfo_height() + 4
                self._tooltip.wm_geometry(f"+{x}+{y}")
                tk.Label(self._tooltip, text=Path(path).name, bg="#ffffe0",
                         relief='solid', borderwidth=1, padx=4, pady=2).pack()
            except Exception:
                self._tooltip = None

        def hide(_e=None):
            t = getattr(self, "_tooltip", None)
            if t is not None:
                try:
                    t.destroy()
                except Exception:
                    pass
                self._tooltip = None

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")

    # -------------------------------------------------------------- menu
    def media_menu(self, event, idx):
        if idx not in self.selected_indices:
            self.selected_indices = {idx}
            self._sel_anchor = idx
            self._refresh_selection()
        n = len(self.selected_indices)
        m = tk.Menu(self.root, tearoff=0)
        m_type = self.media_files[idx][0]
        edit_label = "Edit (crop & trim)..." if m_type == "video" else "Edit (crop & brightness)..."
        m.add_command(label=edit_label, command=lambda: self.open_edit_dialog(idx))
        m.add_separator()
        m.add_command(label="Delete" if n == 1 else f"Delete ({n} επιλεγμένα)",
                      command=self.delete_selected)
        m.add_command(label="Change Position", command=lambda: self.change_pos(idx))
        m.add_separator()
        m.add_command(label="Move Left/Up", command=lambda: self.move_media(idx, -1))
        m.add_command(label="Move Right/Down", command=lambda: self.move_media(idx, 1))
        m.add_separator()
        m.add_command(label="Undo", command=self.undo)
        m.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ editing
    def delete_selected(self):
        sel = self._selected()
        if not sel:
            if self.media_files:
                messagebox.showinfo("Διαγραφή", "Διάλεξε πρώτα ένα στοιχείο.")
            return
        msg = ("Να διαγραφεί το επιλεγμένο στοιχείο;" if len(sel) == 1
               else f"Να διαγραφούν {len(sel)} στοιχεία;")
        if not messagebox.askyesno("Διαγραφή", msg + "\n\n(Αναιρείται με Undo)"):
            return
        self.push_undo()
        self.media_files = [m for i, m in enumerate(self.media_files)
                            if i not in self.selected_indices]
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()

    def delete_media(self, idx):
        self.selected_indices = {idx}
        self.delete_selected()

    def change_pos(self, idx):
        new_idx = simpledialog.askinteger("Position", f"Move item {idx+1} to position:",
                                          initialvalue=idx + 1, minvalue=1,
                                          maxvalue=len(self.media_files))
        if new_idx:
            self.push_undo()
            item = self.media_files.pop(idx)
            self.media_files.insert(new_idx - 1, item)
            self.selected_indices = {new_idx - 1}
            self.is_modified = True
            self.update_media_display()

    def move_media(self, idx, d):
        sel = sorted(self._selected() or [idx])
        if not sel:
            return
        if d < 0 and sel[0] == 0:
            return
        if d > 0 and sel[-1] == len(self.media_files) - 1:
            return
        self.push_undo()
        if d < 0:
            for i in sel:
                self.media_files[i - 1], self.media_files[i] = \
                    self.media_files[i], self.media_files[i - 1]
            self.selected_indices = {i - 1 for i in sel}
        else:
            for i in reversed(sel):
                self.media_files[i + 1], self.media_files[i] = \
                    self.media_files[i], self.media_files[i + 1]
            self.selected_indices = {i + 1 for i in sel}
        self.is_modified = True
        self.update_media_display()
