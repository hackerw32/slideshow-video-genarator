"""The Project Text Input window and its clipboard shortcuts."""

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


class TextInputMixin:
    """The Project Text Input window and its clipboard shortcuts."""

    def open_text_window(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Text Input")
        dialog.geometry("1180x780")
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
            self.project_ai_instructions = instr.get("1.0", tk.END).strip()
            self.is_modified = True
            dialog.destroy()

        # ---- optional AI rewriting --------------------------------------
        # Instructions stored per project (like the project watermark), while
        # the global ones live in Settings -> AI / DeepSeek.
        instr_f = ttk.LabelFrame(dialog, text="Οδηγίες για αυτό το project — τις χρησιμοποιεί μόνο το AI")
        instr_f.pack(fill='x', padx=10, pady=(2, 2))
        instr = scrolledtext.ScrolledText(instr_f, height=4, wrap=tk.WORD, undo=True)
        instr.pack(fill='x', padx=5, pady=5)
        instr.insert("1.0", self.project_ai_instructions)
        instr.edit_reset()   # so Ctrl+Z doesn't wipe the loaded instructions
        self._bind_text_shortcuts(instr)

        ttk.Label(dialog, foreground="#777", wraplength=1100, justify='left',
                  text='Παράδειγμα: «Έμφαση στην τιμή και στο τηλέφωνο. Πρώτο πληθυντικό.»  '
                       'Στη βελτίωση προστίθενται πάντα και οι παγκόσμιες οδηγίες από '
                       'Settings → AI / DeepSeek.').pack(padx=12, anchor='w')

        ai_row = ttk.Frame(dialog)
        ai_row.pack(fill='x', padx=12, pady=(8, 0))
        ai_status = ttk.Label(ai_row, text="", foreground="#2d6cdf")
        ai_btns = []

        def set_ai_busy(busy):
            for b in ai_btns:
                b.config(state='disabled' if busy else 'normal')
            ai_status.config(text="Το AI γράφει..." if busy else "")

        def replace_text(widget, new_text):
            # The widgets are undo=True, so Ctrl+Z brings the original back.
            widget.delete("1.0", tk.END)
            widget.insert("1.0", new_text)

        def ai_improve(widget):
            self.improve_text_with_ai(
                widget.get("1.0", tk.END).strip(),
                instr.get("1.0", tk.END).strip(),
                apply_result=lambda new_text, w=widget: replace_text(w, new_text),
                set_busy=set_ai_busy)

        b_v = ttk.Button(ai_row, text="Βελτίωση με AI (Βίντεο)", command=lambda: ai_improve(txt_v))
        b_v.pack(side='left')
        ai_btns.append(b_v)
        b_p = ttk.Button(ai_row, text="Βελτίωση με AI (Φωτό)", command=lambda: ai_improve(txt_p))
        b_p.pack(side='left', padx=4)
        ai_btns.append(b_p)
        if not self.ai_configured():
            ttk.Label(ai_row, foreground="#c0392b",
                      text="  Το AI δεν είναι ρυθμισμένο — Settings → AI / DeepSeek").pack(side='left')
        ai_status.pack(side='left', padx=8)

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

