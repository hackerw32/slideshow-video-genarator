"""The erase tool: brush strokes, a zoomable view, and the model download.

Two pieces live here:

* ``ErasePanel(owner, parent, edit, source, path)`` - the tool itself: build it
  into a frame and call ``get_strokes()`` on Apply.
* ``EraseSettingsMixin.show_erase_settings()`` - the Settings dialog that
  downloads the 198 MB LaMa model once, with progress and a cancel button.

Strokes are stored as fractions of the source (like the crop), so they are
resolution independent and reusable; nothing is ever baked into a new file.
"""

import threading

import tkinter as tk
from tkinter import ttk, messagebox

from .deps import Image, ImageTk
from .erase import MODEL_DIR_NAME, download_model

CW, CH = 640, 420          # the erase canvas is a fixed size; the view zooms
MIN_SCALE, MAX_SCALE = 0.05, 8.0
BRUSH_MIN, BRUSH_MAX = 4, 160
PAINT = '#ff2d55'


class ErasePanel:
    """The erase tool built into a parent frame. Call ``get_strokes()``."""

    def __init__(self, owner, parent, edit, source, path=None):
        self.owner = owner
        self.parent = parent
        self.src = source.convert("RGB")
        self.W, self.H = self.src.size
        self.path = path
        self.strokes = []
        for s in (edit or {}).get("erase") or []:
            if isinstance(s, dict) and s.get("pts"):
                self.strokes.append({"r": float(s.get("r", 0.02)),
                                     "pts": [[float(p[0]), float(p[1])] for p in s["pts"]
                                             if isinstance(p, (list, tuple)) and len(p) >= 2]})
        self.strokes = [s for s in self.strokes if s["pts"]]
        self.work = self.src.copy()
        self.busy = False
        self.token = 0
        self.job = None
        self.painting = None
        self.panning = None
        self.scale = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self._build()
        self.fit()
        if self.strokes:
            self.schedule_erase(50)

    # ------------------------------------------------------------- widgets
    def _build(self):
        bar = ttk.Frame(self.parent)
        bar.pack(fill='x', padx=8, pady=(8, 4))

        ttk.Label(bar, text="Πινέλο:").pack(side='left')
        self.brush = tk.IntVar(value=40)
        ttk.Scale(bar, from_=BRUSH_MIN, to=BRUSH_MAX, variable=self.brush, length=150,
                  command=lambda *a: self._brush_label()).pack(side='left', padx=4)
        self.brush_lbl = ttk.Label(bar, text="40 px", width=7)
        self.brush_lbl.pack(side='left')

        ttk.Button(bar, text="Προσαρμογή", command=self.fit).pack(side='left', padx=(12, 2))
        ttk.Button(bar, text="1:1", command=lambda: self.set_scale(1.0)).pack(side='left', padx=2)
        ttk.Button(bar, text="2:1", command=lambda: self.set_scale(2.0)).pack(side='left', padx=2)
        ttk.Label(bar, text="   Τροχός = ζουμ, δεξί κλικ = μετακίνηση",
                  foreground="#777").pack(side='left', padx=6)

        self.canvas = tk.Canvas(self.parent, width=CW, height=CH, bg='#111',
                                highlightthickness=1, highlightbackground='#888',
                                cursor='crosshair')
        self.canvas.pack(padx=8)

        row = ttk.Frame(self.parent)
        row.pack(fill='x', padx=8, pady=(6, 2))
        self.undo_btn = ttk.Button(row, text="Αναίρεση πινελιάς", command=self.undo_stroke)
        self.undo_btn.pack(side='left', padx=(0, 4))
        ttk.Button(row, text="Καθαρισμός όλων", command=self.clear_strokes).pack(side='left', padx=4)
        self.refresh_btn = ttk.Button(row, text="Ανανέωση σβησίματος", command=self.schedule_erase_now)
        self.refresh_btn.pack(side='left', padx=4)

        self.status = ttk.Label(self.parent, text="", foreground="#333")
        self.status.pack(fill='x', padx=8, pady=(2, 4))

        ttk.Label(self.parent,
                  text="Ζωγράφισε πάνω σε ό,τι θέλεις να εξαφανιστεί (πινακίδα, σκουπίδια, "
                       "πρόσωπο). Το σβήσιμο γίνεται τοπικά, χωρίς internet.",
                  foreground="#777", wraplength=CW, justify='left').pack(padx=8, anchor='w')

        if not self.owner._erase_engine().model_ready():
            warn = ttk.Frame(self.parent)
            warn.pack(fill='x', padx=8, pady=(4, 0))
            ttk.Label(warn, foreground="#c0392b",
                      text="Το μοντέλο AI δεν έχει κατέβει — το σβήσιμο θα γίνει με OpenCV "
                           "(ακαριαίο αλλά κατώτερο).").pack(side='left')
            ttk.Button(warn, text="Κατέβασέ το",
                       command=self.owner.show_erase_settings).pack(side='left', padx=6)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_pan_press)
        self.canvas.bind("<B3-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-3>", lambda e: setattr(self, "panning", None))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self._brush_label()
        self.render()

    def _brush_label(self):
        self.brush_lbl.config(text=f"{self.brush.get()} px")

    # ------------------------------------------------------------- helpers
    @property
    def fit_scale(self):
        return max(MIN_SCALE, min(CW / self.W, CH / self.H))

    def fit(self):
        self.scale = self.fit_scale
        self.clamp_view(True)
        self.render()

    def set_scale(self, s):
        # keep the centre of the view fixed while zooming
        cx = self.ox + (CW / 2) / self.scale
        cy = self.oy + (CH / 2) / self.scale
        self.scale = max(MIN_SCALE, min(MAX_SCALE, s))
        self.ox = cx - (CW / 2) / self.scale
        self.oy = cy - (CH / 2) / self.scale
        self.clamp_view()
        self.render()

    def clamp_view(self, keep=False):
        sw, sh = CW / self.scale, CH / self.scale
        if self.W <= sw:
            self.ox = (self.W - sw) / 2
        else:
            self.ox = max(0.0, min(self.ox, self.W - sw))
        if self.H <= sh:
            self.oy = (self.H - sh) / 2
        else:
            self.oy = max(0.0, min(self.oy, self.H - sh))

    def to_screen(self, xf, yf):
        return (xf * self.W - self.ox) * self.scale, (yf * self.H - self.oy) * self.scale

    def to_source(self, sx, sy):
        return ((self.ox + sx / self.scale) / self.W, (self.oy + sy / self.scale) / self.H)

    def radius_fraction(self):
        """The on-screen brush size, expressed as a fraction of the source."""
        return (self.brush.get() / self.scale) / max(1, max(self.W, self.H))

    # ------------------------------------------------------------ painting
    def _on_press(self, e):
        if self.busy:
            return
        xf, yf = self.to_source(e.x, e.y)
        self.painting = {"r": self.radius_fraction(), "pts": [[xf, yf]]}
        self.strokes.append(self.painting)
        self.render_overlay()

    def _on_move(self, e):
        if not self.painting:
            return
        xf, yf = self.to_source(e.x, e.y)
        lx, ly = self.painting["pts"][-1]
        # ignore sub-pixel jitter so the stored stroke stays small
        if abs((xf - lx) * self.W * self.scale) < 2 and abs((yf - ly) * self.H * self.scale) < 2:
            return
        self.painting["pts"].append([xf, yf])
        self.render_overlay()

    def _on_release(self, e):
        if not self.painting:
            return
        self.painting = None
        self.schedule_erase()
        self.render_overlay()

    def _on_pan_press(self, e):
        self.panning = (e.x, e.y, self.ox, self.oy)

    def _on_pan_move(self, e):
        if not self.panning:
            return
        sx, sy, ox0, oy0 = self.panning
        self.ox = ox0 - (e.x - sx) / self.scale
        self.oy = oy0 - (e.y - sy) / self.scale
        self.clamp_view()
        self.render()

    def _on_wheel(self, e):
        factor = 1.25 if e.delta > 0 else 1 / 1.25
        old = self.scale
        new = max(MIN_SCALE, min(MAX_SCALE, old * factor))
        if abs(new - old) > 1e-9:
            cx = self.ox + e.x / old
            cy = self.oy + e.y / old
            self.scale = new
            self.ox = cx - e.x / new
            self.oy = cy - e.y / new
            self.clamp_view()
            self.render()
        return "break"      # otherwise the library canvas scrolls too

    def undo_stroke(self):
        if self.busy or not self.strokes:
            return
        self.strokes.pop()
        self.schedule_erase(10)

    def clear_strokes(self):
        if self.busy:
            return
        self.token += 1                 # ignore any result still in flight
        self.strokes = []
        self.work = self.src.copy()
        self.set_status("")
        self.render()

    def schedule_erase_now(self):
        self.schedule_erase(10)

    def schedule_erase(self, delay=300):
        if self.job:
            try:
                self.owner.root.after_cancel(self.job)
            except Exception:
                pass
        self.job = self.owner.root.after(delay, self.run_erase)

    # -------------------------------------------------------------- erase
    def run_erase(self):
        self.job = None
        if self.busy or not self.strokes:
            return
        self.busy = True
        self.token += 1
        token = self.token
        snapshot = [{"r": s["r"], "pts": [list(p) for p in s["pts"]]} for s in self.strokes]
        engine = self.owner._erase_engine()
        cold = engine.model_ready() and not engine.is_loaded()
        self.set_status("Φόρτωση μοντέλου AI και σβήσιμο... (την πρώτη φορά θέλει ~20s)"
                        if cold else "Σβήσιμο...")
        self._set_buttons(False)
        threading.Thread(target=self._worker, args=(snapshot, token), daemon=True).start()

    def _worker(self, snapshot, token):
        try:
            out = self.owner._apply_erase(self.src, snapshot, self.path)
            err = None
        except Exception as e:
            out, err = None, str(e)
        self.owner.root.after(0, lambda: self._done(out, err, token))

    def _done(self, out, err, token):
        self.busy = False
        self._set_buttons(True)
        if token != self.token:
            return                       # a newer stroke already superseded this
        if err:
            self.set_status(f"Αποτυχία: {err}", "#c0392b")
            return
        self.work = out
        self.set_status("Έτοιμο. Συνέχισε να ζωγραφίζεις ή πάτα Εφαρμογή.", "#1e7a34")
        self.render()

    def _set_buttons(self, on):
        state = 'normal' if on else 'disabled'
        for b in (self.undo_btn, self.refresh_btn):
            b.config(state=state)

    def set_status(self, text, color="#333"):
        try:
            self.status.config(text=text, foreground=color)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ drawing
    def _view_image(self):
        sw, sh = CW / self.scale, CH / self.scale
        box = (int(self.ox), int(self.oy), int(min(self.W, self.ox + sw)),
               int(min(self.H, self.oy + sh)))
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            return Image.new("RGB", (CW, CH), (17, 17, 17))
        region = self.work.crop(box)
        disp = region.resize((max(1, int(round(region.width * self.scale))),
                              max(1, int(round(region.height * self.scale)))),
                             Image.Resampling.LANCZOS)
        if disp.size == (CW, CH):
            return disp
        base = Image.new("RGB", (CW, CH), (17, 17, 17))
        base.paste(disp, (int(round((box[0] - self.ox) * self.scale)),
                          int(round((box[1] - self.oy) * self.scale))))
        return base

    def render(self):
        self.canvas.delete('all')
        ref = ImageTk.PhotoImage(self._view_image())
        self.canvas.img_ref = ref
        self.canvas.create_image(0, 0, image=ref, anchor='nw', tags='base')
        self.render_overlay()

    def render_overlay(self):
        self.canvas.delete('ovl')
        for s in self.strokes:
            live = s is self.painting
            r = max(1.0, s["r"] * max(self.W, self.H) * self.scale)
            pts = [self.to_screen(x, y) for x, y in s["pts"]]
            flat = [c for p in pts for c in p]
            if live:
                # a translucent-looking band (Tk has no alpha, so stipple)
                if len(flat) >= 4:
                    self.canvas.create_line(*flat, fill=PAINT, width=max(2, int(r * 2)),
                                            stipple='gray50', capstyle='round',
                                            tags='ovl')
                else:
                    x, y = pts[0]
                    self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=PAINT,
                                            stipple='gray50', outline='', tags='ovl')
            # a thin dashed trace marks what has already been erased
            if len(flat) >= 4:
                self.canvas.create_line(*flat, fill=PAINT, width=1, dash=(3, 3),
                                        capstyle='round', tags='ovl')
            x0, y0 = pts[0]
            x1, y1 = pts[-1]
            self.canvas.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, outline=PAINT,
                                    width=1, dash=(3, 3), tags='ovl')
            if (x0, y0) != (x1, y1):
                self.canvas.create_oval(x1 - r, y1 - r, x1 + r, y1 + r, outline=PAINT,
                                        width=1, dash=(3, 3), tags='ovl')
        self.canvas.create_rectangle(1, 1, CW - 1, CH - 1, outline='#444', tags='ovl')

    # -------------------------------------------------------------- output
    def get_strokes(self):
        out = []
        for s in self.strokes:
            if len(s["pts"]) < 1:
                continue
            out.append({"r": round(float(s["r"]), 6),
                        "pts": [[round(float(x), 6), round(float(y), 6)] for x, y in s["pts"]]})
        return out


class EraseSettingsMixin:
    """The Settings dialog that downloads (and reports on) the LaMa model."""

    def show_erase_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Σβήσιμο αντικειμένων — μοντέλο AI")
        dlg.geometry("660x430")
        dlg.minsize(520, 340)
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()

        engine = self._erase_engine()
        body, bottom = self._scrollable(dlg, 350)

        ttk.Label(body, text="Τοπικό σβήσιμο αντικειμένων", font=("Calibri", 11, "bold")).pack(
            padx=18, pady=(14, 2), anchor='w')
        ttk.Label(body, foreground="#555", wraplength=570, justify='left',
                  text="Χρησιμοποιεί το μοντέλο LaMa, που τρέχει τοπικά στον υπολογιστή σου "
                       "μέσω onnxruntime. Χωρίς σύνδεση στο internet, χωρίς αποστολή της "
                       "φωτογραφίας πουθενά — μόνο η λήψη του μοντέλου χρειάζεται internet, "
                       "μία φορά.").pack(padx=18, anchor='w', pady=(0, 8))

        info = ttk.Label(body, text="", justify='left', wraplength=570)
        info.pack(padx=18, anchor='w')

        bar = ttk.Progressbar(body, maximum=100, length=560)
        bar.pack(padx=18, pady=(10, 4), anchor='w')

        note = ttk.Label(body, text="", foreground="#333", justify='left', wraplength=570)
        note.pack(padx=18, anchor='w')

        btns = ttk.Frame(bottom)
        btns.pack(fill='x', padx=18)
        cancel = {"v": False}
        state = {"busy": False}

        def refresh():
            if engine.model_ready():
                mb = engine.model_path.stat().st_size / 1048576
                info.config(text=f"Κατάσταση: έτοιμο — {mb:.0f} MB στο models/", foreground="#1e7a34")
                dl_btn.config(text="Ξανά κατέβασμα", state='normal')
            else:
                info.config(text="Κατάσταση: το μοντέλο δεν έχει κατέβει. Το σβήσιμο θα γίνει "
                                 "προσωρινά με OpenCV (ακαριαίο αλλά πολύ κατώτερο σε "
                                 "πολύπλοκες εικόνες).", foreground="#c0392b")
                dl_btn.config(text="Κατέβασμα μοντέλου (198 MB)", state='normal')

        def set_busy(b):
            state["busy"] = b
            dl_btn.config(state='disabled' if b else 'normal')
            close_btn.config(state='disabled' if b else 'normal')
            cancel_btn.config(state='normal' if b else 'disabled')

        def worker():
            def prog(done, total):
                pct = (done / total * 100) if total else 0
                txt = f"{done / 1048576:.0f} / {total / 1048576:.0f} MB" if total else \
                      f"{done / 1048576:.0f} MB"
                self.root.after(0, lambda: (bar.config(value=pct),
                                            note.config(text=txt)))
            try:
                download_model(self.app_dir / MODEL_DIR_NAME, prog, lambda: cancel["v"])
                self.root.after(0, lambda: finished(None))
            except Exception as e:
                self.root.after(0, lambda: finished(str(e)))

        def finished(err):
            set_busy(False)
            cancel["v"] = False
            bar.config(value=0)
            if err:
                note.config(text=err, foreground="#c0392b")
            else:
                note.config(text="Το μοντέλο κατέβηκε. Φορτώνει στο παρασκήνιο...",
                            foreground="#1e7a34")
                engine.prewarm()
            refresh()

        def start():
            if state["busy"]:
                return
            if engine.model_ready() and not messagebox.askyesno(
                    "Σβήσιμο", "Το μοντέλο υπάρχει ήδη. Να το ξανακατεβάσω;"):
                return
            cancel["v"] = False
            set_busy(True)
            note.config(text="Ξεκινάει η λήψη...", foreground="#333")
            threading.Thread(target=worker, daemon=True).start()

        def do_cancel():
            cancel["v"] = True
            note.config(text="Ακύρωση...", foreground="#333")

        dl_btn = ttk.Button(btns, text="Κατέβασμα μοντέλου (198 MB)", command=start)
        dl_btn.pack(side='left')
        cancel_btn = ttk.Button(btns, text="Ακύρωση λήψης", command=do_cancel, state='disabled')
        cancel_btn.pack(side='left', padx=6)
        close_btn = ttk.Button(btns, text="Κλείσιμο", command=dlg.destroy)
        close_btn.pack(side='right')

        refresh()
