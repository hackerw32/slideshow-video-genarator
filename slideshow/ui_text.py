"""The Project Text Input window: two texts side-by-side with live previews.

Layout: left column has the photos text (top) and the videos text (bottom),
right column has their previews, and the AI instructions sit below with their
own buttons. The window confirms before closing with unsaved changes.
"""

import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from .deps import Image, ImageTk


class TextInputMixin:
    """The Project Text Input window and its clipboard shortcuts."""

    def open_text_window(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Text Input")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win_w = min(1500, max(1000, int(sw * 0.92)))
        win_h = min(1000, max(640, int(sh * 0.90)))
        dialog.geometry(f"{win_w}x{win_h}")
        dialog.minsize(min(900, sw - 80), min(600, sh - 80))
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        w, h = map(int, self.settings["resolution"].split("x"))

        main = ttk.Frame(dialog)
        main.pack(fill='both', expand=True, padx=10, pady=(10, 4))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        # -------------------- photos text (top-left) + preview (top-right)
        pf = ttk.LabelFrame(main, text="Κείμενο για ΦΩΤΟΓΡΑΦΙΕΣ")
        pf.grid(row=0, column=0, sticky='nsew', padx=(0, 8), pady=(0, 6))
        ph = ttk.Frame(pf)
        ph.pack(fill='x')
        ttk.Button(ph, text="Quick Paste", command=lambda: quick_paste(txt_p)).pack(side='left')
        txt_p = scrolledtext.ScrolledText(pf, height=7, wrap=tk.WORD, undo=True)
        txt_p.pack(fill='both', expand=True, padx=4, pady=(0, 4))

        pv = ttk.LabelFrame(main, text="Preview ΦΩΤΟΓΡΑΦΙΑΣ")
        pv.grid(row=0, column=1, sticky='nsew', pady=(0, 6))
        canvas_p = tk.Canvas(pv, bg='black', highlightthickness=1, highlightbackground='#888')
        canvas_p.pack(padx=6, pady=6)

        # -------------------- videos text (bottom-left) + preview (bottom-right)
        vf = ttk.LabelFrame(main, text="Κείμενο για ΒΙΝΤΕΟ")
        vf.grid(row=1, column=0, sticky='nsew', padx=(0, 8))
        vh = ttk.Frame(vf)
        vh.pack(fill='x')
        ttk.Button(vh, text="Quick Paste", command=lambda: quick_paste(txt_v)).pack(side='left')
        txt_v = scrolledtext.ScrolledText(vf, height=7, wrap=tk.WORD, undo=True)
        txt_v.pack(fill='both', expand=True, padx=4, pady=(0, 4))

        vv = ttk.LabelFrame(main, text="Preview ΒΙΝΤΕΟ")
        vv.grid(row=1, column=1, sticky='nsew')
        canvas_v = tk.Canvas(vv, bg='black', highlightthickness=1, highlightbackground='#888')
        canvas_v.pack(padx=6, pady=6)

        ttk.Label(main, foreground="#555",
                  text="Αν αφήσεις κενό το ένα κείμενο, αυτό του άλλου εμφανίζεται και στα δύο."
                  ).grid(row=2, column=0, columnspan=2, sticky='w', pady=(4, 0))

        # -------------------- AI instructions + buttons
        instr_f = ttk.LabelFrame(main, text="Οδηγίες για AI βελτίωση (προαιρετικές)")
        instr_f.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        instr = scrolledtext.ScrolledText(instr_f, height=3, wrap=tk.WORD, undo=True)
        instr.pack(side='left', fill='both', expand=True, padx=4, pady=4)
        ai_btns = ttk.Frame(instr_f)
        ai_btns.pack(side='right', fill='y', padx=4, pady=4)
        ai_status = ttk.Label(ai_btns, text="", foreground="#2d6cdf", wraplength=210,
                              justify='left')
        ai_status.pack(anchor='w')

        # -------------------- bottom bar
        btns = ttk.Frame(main)
        btns.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        ttk.Button(btns, text="Apply Text", command=lambda: save()).pack(side='right')
        ttk.Button(btns, text="Κλείσιμο", command=lambda: on_close()).pack(side='right', padx=6)
        ttk.Label(btns, foreground="#777",
                  text="Το κείμενο αποθηκεύεται στο project και το preview ανανεώνεται αυτόματα."
                  ).pack(side='left')

        # -------------------- contents
        txt_v.insert("1.0", self.project_text_videos)
        txt_p.insert("1.0", self.project_text_photos)
        instr.insert("1.0", self.project_ai_instructions)
        for t in (txt_v, txt_p, instr):
            t.edit_reset()   # so Ctrl+Z doesn't wipe the loaded text
            self._bind_text_shortcuts(t)

        # -------------------- helpers
        def quick_paste(t):
            try:
                t.insert(tk.INSERT, self.root.clipboard_get())
            except tk.TclError:
                pass

        def replace_text(widget, new_text):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", new_text)

        def current_values():
            return (txt_v.get("1.0", tk.END).strip(),
                    txt_p.get("1.0", tk.END).strip(),
                    instr.get("1.0", tk.END).strip())

        initial = (self.project_text_videos.strip(), self.project_text_photos.strip(),
                   self.project_ai_instructions.strip())
        saved = {"v": False}

        def save():
            v, p, i = current_values()
            self.project_text_videos = v
            self.project_text_photos = p
            self.project_ai_instructions = i
            self.is_modified = True
            saved["v"] = True
            self._schedule_preview()
            close_dialog()

        def on_close():
            if saved["v"] or current_values() == initial:
                close_dialog()
                return
            answer = messagebox.askyesnocancel(
                "Κείμενο", "Έγιναν αλλαγές στο κείμενο.\n\nΝα αποθηκευτούν;")
            if answer is None:
                return
            if answer:
                save()
            else:
                close_dialog()

        dialog.protocol("WM_DELETE_WINDOW", on_close)

        # -------------------- previews
        preview_job = {"id": None}
        initial_job = {"id": None}
        closed = {"v": False}

        def close_dialog():
            """Cancel the dialog's pending timers, then destroy it.

            The timers are created with dialog.after(), so they must be
            cancelled with dialog.after_cancel() too - cancelling them on
            another widget leaves a stale Tcl command behind and destroy()
            then fails with "can't delete Tcl command".
            """
            closed["v"] = True
            for holder in (preview_job, initial_job):
                if holder["id"]:
                    try:
                        dialog.after_cancel(holder["id"])
                    except Exception:
                        pass
                    holder["id"] = None
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        def schedule_preview(_event=None):
            if closed["v"]:
                return
            if preview_job["id"]:
                try:
                    dialog.after_cancel(preview_job["id"])
                except Exception:
                    pass
            preview_job["id"] = dialog.after(500, render_previews)

        def render_previews():
            preview_job["id"] = None
            if closed["v"]:
                return
            tv, tp, _ = current_values()
            self._render_text_dialog_previews(canvas_v, canvas_p, tv, tp, w, h)

        for t in (txt_v, txt_p):
            t.bind("<KeyRelease>", schedule_preview, add="+")

        # -------------------- AI improvement
        ai_buttons = []

        def set_ai_busy(busy):
            for b in ai_buttons:
                b.config(state='disabled' if busy else 'normal')
            ai_status.config(text="Το AI γράφει..." if busy else "")

        def ai_improve(widget):
            self.improve_text_with_ai(
                widget.get("1.0", tk.END).strip(),
                instr.get("1.0", tk.END).strip(),
                apply_result=lambda new_text, wdg=widget: (replace_text(wdg, new_text),
                                                           schedule_preview()),
                set_busy=set_ai_busy)

        b_p = ttk.Button(ai_btns, text="Βελτίωση με AI (Φωτό)", command=lambda: ai_improve(txt_p))
        b_p.pack(anchor='w', pady=(0, 4))
        ai_buttons.append(b_p)
        b_v = ttk.Button(ai_btns, text="Βελτίωση με AI (Βίντεο)", command=lambda: ai_improve(txt_v))
        b_v.pack(anchor='w')
        ai_buttons.append(b_v)
        if not self.ai_configured():
            ttk.Label(ai_btns, foreground="#c0392b", wraplength=210,
                      text="Το AI δεν είναι ρυθμισμένο — Settings → AI / DeepSeek").pack(
                anchor='w', pady=(4, 0))

        # Ctrl+V anywhere in the window pastes into the last text box that had
        # focus (so it keeps working after clicking a button).
        last_text = {"w": txt_v}

        def remember_text(e):
            last_text["w"] = e.widget
        for t in (txt_v, txt_p, instr):
            t.bind("<FocusIn>", remember_text, add="+")

        def paste_anywhere(_e=None):
            w = self.root.focus_get()
            if not isinstance(w, tk.Text):
                w = last_text["w"]
            self._do_text_shortcut(w, "paste")
            return "break"
        dialog.bind("<Control-v>", paste_anywhere)
        dialog.bind("<Control-V>", paste_anywhere)

        initial_job["id"] = dialog.after(200, render_previews)


    def _render_text_dialog_previews(self, canvas_video, canvas_photo,
                                     text_videos, text_photos, w, h):
        """Render the first photo and the first video with the dialog's texts.

        Runs off the Tk thread; the canvases are updated back on the main thread.
        """
        def worker():
            out = []
            for m_type, canvas in (("video", canvas_video), ("image", canvas_photo)):
                item = next((it for it in self.media_files if it[0] == m_type), None)
                if item is None:
                    out.append((canvas, None))
                    continue
                try:
                    path, edit = item[1], item[2]
                    if m_type == "image":
                        img = Image.open(path)
                    else:
                        img = self._video_first_frame(path)
                    img = self._apply_image_edit(img, edit, path, m_type=m_type)
                    if m_type == "image":
                        text = text_photos if text_photos.strip() else text_videos
                    else:
                        text = text_videos if text_videos.strip() else text_photos
                    out.append((canvas, self._render_with_text(img, m_type, text, w, h)))
                except Exception:
                    out.append((canvas, None))
            self.root.after(0, lambda: [self._show_dialog_preview(c, f, w, h)
                                        for c, f in out])
        threading.Thread(target=worker, daemon=True).start()


    def _render_with_text(self, img, m_type, text, w, h):
        """The export's first frame for one media item, using ``text``."""
        if m_type == "image":
            frame = self._fit_image_logic(img, w, h, "image", text=text)
            fit_move_data = getattr(frame, 'fit_move_data', None)
            if fit_move_data is not None:
                overlay = self._make_text_overlay(text, w, h)
                return self._render_fit_and_move_frame(frame, fit_move_data, 0.0, w, h, overlay)
            return self.render_text_on_image(frame, text, w, h)
        frame = self._render_video_first_frame(img, w, h)
        return self.render_text_on_image(frame, text, w, h)


    def _show_dialog_preview(self, canvas, frame, w, h):
        try:
            if not canvas.winfo_exists():
                return
            cw, ch = self._preview_canvas_size(w, h)
            cw, ch = min(cw, 320), min(ch, 320)
            canvas.config(width=cw, height=ch)
            canvas.delete('all')
            if frame is None:
                canvas.create_text(cw // 2, ch // 2, text="— δεν υπάρχει media —",
                                   fill="#aaa", width=cw - 16)
                return
            disp = frame.resize((cw, ch), Image.Resampling.LANCZOS)
            ref = ImageTk.PhotoImage(disp)
            canvas.img = ref
            canvas.create_image(cw // 2, ch // 2, image=ref)
        except tk.TclError:
            pass      # the dialog was closed while a preview was rendering


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
                clip = None
                try:
                    clip = self.root.clipboard_get()
                except tk.TclError:
                    clip = None
                if clip is not None:
                    sel = txt.tag_ranges(tk.SEL)
                    if sel:
                        txt.delete(sel[0], sel[1])
                        txt.insert(sel[0], clip)
                    else:
                        txt.insert(tk.INSERT, clip)
                else:
                    # Some clipboards refuse clipboard_get(): let Tk try itself.
                    try:
                        txt.event_generate("<<Paste>>")
                    except tk.TclError:
                        pass
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
