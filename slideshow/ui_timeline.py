"""The video Edit dialog: a filmstrip timeline with several cut points.

The old Από/Έως sliders are replaced by a timeline. The whole video is shown as
a filmstrip, every segment between two cut points is either ΚΡΑΤΑ (kept) or
ΠΕΤΑ (dropped) and clicking the bar toggles it. Splitting at the playhead is
how a new cut point is added, so "keep the start and the end, drop the middle"
is two splits and one click.

The drag zones are deliberately one behaviour each:
  filmstrip + ruler -> move the playhead (scrub)
  keep/cut bar      -> click a segment to toggle it
  yellow handles    -> drag a cut point
"""

import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

from .deps import Image, ImageTk
from .ui_color_controls import ColorControls
from .ui_video_playback import VideoPreviewPlayer


MIN_SEG = 0.3      # shortest segment the user may create, in seconds
TL_W = 1140        # timeline canvas width
STRIP_H = 81       # filmstrip band height
BAR_H = 45         # keep/cut bar height
RULER_H = 24       # time ruler height
HANDLE_W = 13      # clickable width of a cut point
STRIP_CELLS = 12   # thumbnails sampled across the video

MAIN_W = 630       # crop frame width (was 420)
MAIN_H = 450       # crop frame height (was 300)


def _strip_cell(img, w, h):
    """Scale + centre-crop one frame into a w x h filmstrip cell."""
    if w < 1 or h < 1:
        return img
    r = max(w / img.width, h / img.height)
    im = img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))),
                    Image.Resampling.LANCZOS)
    x0 = (im.width - w) // 2
    y0 = (im.height - h) // 2
    return im.crop((x0, y0, x0 + w, y0 + h))


class TimelineMixin:
    """The video Edit dialog: a filmstrip timeline with several cut points."""

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _tl_mmss(t):
        t = max(0, int(round(t)))
        return f"{t // 60}:{t % 60:02d}"

    @staticmethod
    def _tl_step(duration):
        """A ruler step that yields at most ~10 ticks."""
        for step in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600):
            if duration / step <= 10:
                return step
        return 900

    @staticmethod
    def _tl_build_state(kept, duration):
        """(bounds, keep) built from a list of kept (start, end) ranges.

        bounds[i]..bounds[i+1] is one segment and keep[i] says whether it gets
        encoded. The timeline always starts at 0 and ends at duration, so the
        gaps in front of, between and after the kept ranges become ΠΕΤΑ.
        """
        duration = max(0.1, float(duration))
        kept = sorted((max(0.0, float(s)), min(duration, float(e)))
                      for s, e in kept if float(e) - float(s) > 0.05)
        if not kept:
            return [0.0, duration], [True]
        bounds, keep, pos = [0.0], [], 0.0
        for s, e in kept:
            if s - pos > 0.05:
                bounds.append(s)
                keep.append(False)
            bounds.append(e)
            keep.append(True)
            pos = e
        if duration - pos > 0.05:
            bounds.append(duration)
            keep.append(False)
        if abs(bounds[-1] - duration) > 0.005:
            bounds[-1] = duration
        return bounds, keep

    @staticmethod
    def _tl_kept_ranges(bounds, keep):
        return [(bounds[k], bounds[k + 1]) for k, ok in enumerate(keep) if ok]

    @staticmethod
    def _tl_color_edit(color_ui):
        """The brightness/colour part of a video edit, from the live sliders."""
        return {"brightness": color_ui.brightness.get(),
                "color": color_ui.color.get()}

    # -------------------------------------------------------------- dialog
    def _open_video_editor(self, idx):
        _, path, edit = self.media_files[idx]
        duration = self._video_duration(path)
        if not duration or duration <= 0:
            messagebox.showerror("Edit", "Δεν μπόρεσα να διαβάσω τη διάρκεια του βίντεο.")
            return

        existing = [(s, s + d) for s, d in self.video_keep_segments(edit, duration)]
        bounds, keep = self._tl_build_state(existing, duration)

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit βίντεο — {Path(path).name}")
        self._setup_edit_dialog(dlg, on_fullscreen=lambda full: rescale_main(full))

        state = {"crop": list(edit["crop"]) if edit.get("crop") else None,
                 "play": existing[0][0] if existing else 0.0, "seg": 0,
                 "drag": None, "job": None, "handle": None,
                 "strip": None, "strip_refs": [], "prev": None,
                 "frame": None,
                 "audio": edit.get("audio"),
                 "main_max": (MAIN_W, MAIN_H)}

        ttk.Label(dlg, text="Η γραμμή χρόνου δείχνει όλο το βίντεο. Σύρε πάνω στο filmstrip ή στον "
                            "χάρακα για να μετακινήσεις τη γραμμή αναπαραγωγής, πάτα «Χωρισμός εδώ» "
                            "για νέο σημείο κοψίματος, κλικ σε ένα κομμάτι για ΚΡΑΤΑ/ΠΕΤΑ, και σύρε "
                            "τα κίτρινα σημεία για να τα μετακινήσεις. Στο καρέ αριστερά κάνεις crop.",
                  foreground="#555", wraplength=1180, justify='left').pack(padx=12, pady=(10, 2), anchor='w')

        body = ttk.Frame(dlg)
        body.pack(padx=12, pady=6)
        left = ttk.Frame(body)
        left.pack(side='left', anchor='n')
        ttk.Label(left, text="Καρέ στη γραμμή αναπαραγωγής", font=("Calibri", 9, "bold")).pack()
        canvas = tk.Canvas(left, bg='black', width=MAIN_W, height=MAIN_H, cursor='crosshair',
                           highlightthickness=1, highlightbackground='#888')
        canvas.pack()

        right = ttk.Frame(body)
        right.pack(side='left', padx=(14, 0), anchor='n')
        ttk.Label(right, text="Αναπαραγωγή", font=("Calibri", 9, "bold")).pack()
        play_btn = ttk.Button(right, text="▶  Play από εδώ", width=24, command=lambda: play_here())
        play_btn.pack(pady=(6, 0), fill='x')
        audio_btn = ttk.Button(right, text="", width=24, command=lambda: toggle_audio())
        audio_btn.pack(pady=(6, 0), fill='x')
        status_lbl = ttk.Label(right, text="", foreground="#888", wraplength=200, justify='left')
        status_lbl.pack(pady=(8, 0))

        player = VideoPreviewPlayer(self.root, path, MAIN_W, MAIN_H,
                                    on_frame=lambda img, t: show_play_frame(img, t),
                                    on_finish=lambda: play_finished())

        tl = tk.Canvas(dlg, width=TL_W, height=STRIP_H + BAR_H + RULER_H, bg='#1c1c1c',
                       highlightthickness=1, highlightbackground='#888', cursor='hand2')
        tl.pack(padx=12, pady=(4, 2))

        info_lbl = ttk.Label(dlg, text="", foreground="#333")
        info_lbl.pack(padx=12, anchor='w')

        color_ui = ColorControls(dlg, brightness=edit.get("brightness", 1.0),
                                 color=edit.get("color", 1.0),
                                 on_change=lambda: render_main(),
                                 all_label="Ίδιο σε όλα τα βίντεο")
        color_ui.frame.pack(padx=12, pady=(6, 0), anchor='w')

        def effective_audio():
            """This video's sound: its own override, else the global setting."""
            if state["audio"] is None:
                return bool(self.settings.get("video_audio", False))
            return bool(state["audio"])

        def update_audio_btn():
            audio_btn.config(text=("🔊  Ήχος: ΑΝΟΙΧΤΟΣ" if effective_audio()
                                   else "🔇  Ήχος:  MUTE"))

        def toggle_audio():
            # One click flips this video only (an override of the global setting).
            state["audio"] = not effective_audio()
            update_audio_btn()

        def show_play_frame(img, t):
            """Called for every frame while playing: paint it and move the playhead."""
            if not player.is_playing():
                return
            state["play"] = max(0.0, min(duration, t))
            ref = ImageTk.PhotoImage(img)
            canvas.img_ref = ref
            canvas.delete('all')
            canvas.create_image(0, 0, image=ref, anchor='nw')
            update_playhead()
            status_lbl.config(text=f"▶ {self._tl_mmss(state['play'])} / {self._tl_mmss(duration)}")

        def play_finished():
            if player.is_playing():
                return
            play_btn.config(text="▶  Play από εδώ")
            status_lbl.config(text="")
            refresh_frames(0)

        def play_here():
            """Play/stop the video inside the preview canvas (no extra window)."""
            if player.is_playing():
                player.stop()
                return
            t = max(0.0, float(state["play"]))
            play_dur = 0.0
            for s, e in self._tl_kept_ranges(bounds, keep):
                if s <= t <= e:
                    play_dur = e - t
                    break
            if state["job"]:
                try:
                    self.root.after_cancel(state["job"])
                except Exception:
                    pass
                state["job"] = None
            player.set_size(*state["main_max"])
            canvas.config(width=player.width, height=player.height)
            play_btn.config(text="⏹  Stop")
            gain = 10 ** (float(self.settings.get("video_audio_volume_db", 0) or 0) / 20)
            player.start(start=t, duration=(play_dur if play_dur > 0.05 else None),
                         with_audio=effective_audio(), volume=gain)

        update_audio_btn()

        split_var = tk.BooleanVar(value=False)
        split_cb = ttk.Checkbutton(dlg, variable=split_var,
                                   text="Ξεχωριστές σκηνές — κάθε κομμάτι γίνεται δικό του slide στη "
                                        "βιβλιοθήκη, ώστε να το μετακινήσεις ξεχωριστά",
                                   state='disabled')
        split_cb.pack(padx=14, pady=(6, 2), anchor='w')

        # ---- coordinate helpers ------------------------------------------
        def t2x(t):
            return int(max(0.0, min(1.0, t / duration)) * (TL_W - 1))

        def x2t(x):
            return max(0.0, min(duration, x / (TL_W - 1) * duration))

        def nearest_handle(x):
            best, bd = None, HANDLE_W + 3
            for i in range(1, len(bounds) - 1):
                d = abs(t2x(bounds[i]) - x)
                if d <= bd:
                    best, bd = i, d
            return best

        def seg_at(x):
            t = x2t(x)
            for k in range(len(keep)):
                if bounds[k] <= t <= bounds[k + 1]:
                    return k
            return max(0, len(keep) - 1)

        # ---- timeline rendering ------------------------------------------
        def render_timeline():
            tl.delete('all')
            tl.strip_refs = []
            strip = state["strip"]
            if strip:
                x = 0
                for cell in strip:
                    ref = ImageTk.PhotoImage(cell)
                    tl.strip_refs.append(ref)
                    tl.create_image(x, 0, image=ref, anchor='nw')
                    x += cell.width
            else:
                tl.create_rectangle(0, 0, TL_W, STRIP_H, fill='#1c1c1c', outline='')
                tl.create_text(TL_W / 2, STRIP_H / 2, text="Φόρτωση καρέ...", fill='#aaa')

            y0, y1 = STRIP_H, STRIP_H + BAR_H
            for k, ok in enumerate(keep):
                xa, xb = t2x(bounds[k]), t2x(bounds[k + 1])
                if xb - xa < 2:
                    xb = xa + 2
                selected = (k == state["seg"])
                tl.create_rectangle(xa, y0, xb, y1,
                                    fill='#2e9e4f' if ok else '#6d2b2b',
                                    outline='#ffcc00' if selected else '#111',
                                    width=2 if selected else 1)
                if xb - xa > 52:
                    tl.create_text((xa + xb) / 2, (y0 + y1) / 2,
                                   text="ΚΡΑΤΑ" if ok else "ΠΕΤΑ",
                                   fill='white', font=("Calibri", 8, "bold"))

            ry = STRIP_H + BAR_H
            step = self._tl_step(duration)
            t = 0.0
            while t <= duration + 1e-6:
                x = t2x(t)
                tl.create_line(x, ry, x, ry + 5, fill='#999')
                tl.create_text(x + 2, ry + 7, text=self._tl_mmss(t), anchor='nw',
                               fill='#aaa', font=("Calibri", 7))
                t += step

            for i in range(1, len(bounds) - 1):
                x = t2x(bounds[i])
                tl.create_rectangle(x - HANDLE_W / 2, y0 - 5, x + HANDLE_W / 2, y1 + 5,
                                    fill='#ffcc00', outline='#7a5c00')

            px = t2x(state["play"])
            tl.create_line(px, 0, px, y1, fill='#ff3b30', width=2, tags='playhead')
            tl.create_polygon(px - 5, 0, px + 5, 0, px, 8, fill='#ff3b30', tags='playhead')

        def update_playhead():
            """Move only the red playhead line (cheap; used during playback)."""
            tl.delete('playhead')
            px = t2x(state["play"])
            y1 = STRIP_H + BAR_H
            tl.create_line(px, 0, px, y1, fill='#ff3b30', width=2, tags='playhead')
            tl.create_polygon(px - 5, 0, px + 5, 0, px, 8, fill='#ff3b30', tags='playhead')

        def update_playhead():
            """Move only the red playhead line (cheap; used during playback)."""
            tl.delete('playhead')
            px = t2x(state["play"])
            y1 = STRIP_H + BAR_H
            tl.create_line(px, 0, px, y1, fill='#ff3b30', width=2, tags='playhead')
            tl.create_polygon(px - 5, 0, px + 5, 0, px, 8, fill='#ff3b30', tags='playhead')

        # ---- main canvas (crop) ------------------------------------------
        def render_main():
            canvas.delete('all')
            disp = state["prev"]
            if disp is None:
                canvas.create_text(MAIN_W // 2, MAIN_H // 2, text="Φόρτωση καρέ...", fill='white')
                return
            disp = self._apply_image_edit(disp, self._tl_color_edit(color_ui), m_type="video")
            canvas.config(width=disp.width, height=disp.height)
            ref = ImageTk.PhotoImage(disp)
            canvas.img_ref = ref
            canvas.create_image(0, 0, image=ref, anchor='nw')
            self._draw_crop_overlay(canvas, state["crop"], disp.width, disp.height)

        def rescale_main(full):
            """Re-fit the crop frame: normal 1.5x size, or as big as the screen."""
            player.stop()
            play_btn.config(text="▶  Play από εδώ")
            if full:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                state["main_max"] = (max(1, int(sw * 0.52)), max(1, int(sh * 0.46)))
            else:
                state["main_max"] = (MAIN_W, MAIN_H)
            f = state["frame"]
            if f is not None:
                disp = f.copy()
                disp.thumbnail(state["main_max"])
                state["prev"] = disp
            render_main()

        # ---- info line ----------------------------------------------------
        def update_info(*_):
            kept = self._tl_kept_ranges(bounds, keep)
            total = sum(e - s for s, e in kept)
            txt = "  ".join(f"{self._tl_mmss(s)}→{self._tl_mmss(e)}" for s, e in kept[:4])
            if len(kept) > 4:
                txt += f"  +{len(kept) - 4} ακόμη"
            info_lbl.config(text=f"Κρατάς {total:.2f}s από {duration:.2f}s — "
                                 f"{len(kept)} κομμάτι(α):  {txt}")
            split_cb.config(state='normal' if len(kept) > 1 else 'disabled')
            if len(kept) <= 1:
                split_var.set(False)

        # ---- frame extraction (threaded + debounced) ----------------------
        def refresh_frames(delay=250):
            if player.is_playing():
                return
            if state["job"]:
                try:
                    self.root.after_cancel(state["job"])
                except Exception:
                    pass
            state["job"] = self.root.after(delay, extract_now)

        def extract_now():
            state["job"] = None
            status_lbl.config(text="Φόρτωση καρέ...")
            threading.Thread(target=extract_worker,
                             args=(state["play"],), daemon=True).start()

        def extract_worker(t):
            try:
                f = self._video_frame_at(path, t)
            except Exception:
                f = None
            self.root.after(0, lambda: apply_frames(f))

        def apply_frames(f):
            status_lbl.config(text="")
            state["frame"] = f
            if f is not None:
                disp = f.copy()
                disp.thumbnail(state["main_max"])
                state["prev"] = disp
            render_main()

        # ---- filmstrip (once per file, cached) ----------------------------
        def load_strip():
            cached = getattr(self, "_tl_strip_cache", None)
            if cached is None:
                cached = self._tl_strip_cache = {}
            key = str(path)
            if key not in cached:
                cells = []
                for k in range(STRIP_CELLS):
                    t = duration * (k + 0.5) / STRIP_CELLS
                    x0, x1 = round(k * TL_W / STRIP_CELLS), round((k + 1) * TL_W / STRIP_CELLS)
                    try:
                        fr = self._video_frame_at(path, t)
                    except Exception:
                        fr = None
                    if fr is not None:
                        cells.append(_strip_cell(fr, max(1, x1 - x0), STRIP_H))
                if cells:
                    cached[key] = cells
            cells = cached.get(key)
            if cells:
                self.root.after(0, lambda: set_strip(cells))

        def set_strip(cells):
            state["strip"] = cells
            render_timeline()

        # ---- editing actions ---------------------------------------------
        def toggle_seg(k):
            if not (0 <= k < len(keep)):
                return
            if keep[k] and sum(keep) <= 1:
                messagebox.showinfo("Edit", "Πρέπει να κρατήσεις τουλάχιστον ένα κομμάτι.")
                return
            keep[k] = not keep[k]
            update_info()

        def split_here():
            t = state["play"]
            hit = None
            for k in range(len(keep)):
                if bounds[k] + MIN_SEG <= t <= bounds[k + 1] - MIN_SEG:
                    hit = k
                    break
            if hit is None:
                messagebox.showinfo("Edit", f"Το σημείο αναπαραγωγής είναι πολύ κοντά σε υπάρχον "
                                            f"σημείο — χρειάζονται τουλάχιστον {MIN_SEG}s απόσταση.")
                return
            bounds.insert(hit + 1, t)
            keep.insert(hit + 1, keep[hit])
            state["seg"] = hit + 1
            render_timeline()
            update_info()
            refresh_frames()

        def delete_point():
            if len(bounds) <= 2:
                messagebox.showinfo("Edit", "Δεν υπάρχει ενδιάμεσο σημείο κοψίματος να διαγράψεις.")
                return
            i = min(range(1, len(bounds) - 1), key=lambda k: abs(bounds[k] - state["play"]))
            del bounds[i]
            # The two segments merge; keep the content if either side was kept.
            keep[i - 1] = keep[i - 1] or keep[i]
            del keep[i]
            if not any(keep):
                keep[0] = True
            state["seg"] = max(0, min(state["seg"], len(keep) - 1))
            render_timeline()
            update_info()
            refresh_frames()

        def clear_crop():
            state["crop"] = None
            render_main()

        def reset_all():
            state["crop"] = None
            state["play"] = 0.0
            state["seg"] = 0
            bounds[:] = [0.0, duration]
            keep[:] = [True]
            split_var.set(False)
            color_ui.brightness.set(1.0)
            color_ui.color.set(1.0)
            state["audio"] = None
            update_audio_btn()
            render_timeline()
            render_main()
            update_info()
            refresh_frames(60)

        # ---- crop dragging on the main canvas ----------------------------
        def canvas_size():
            disp = state["prev"]
            return (disp.width, disp.height) if disp else (420, 300)

        def on_press(e):
            player.stop()
            play_btn.config(text="▶  Play από εδώ")
            cw, ch = canvas_size()
            state["crop_drag"] = (min(max(e.x, 0), cw), min(max(e.y, 0), ch))
            state["crop"] = None
            render_main()

        def on_move(e):
            if not state.get("crop_drag"):
                return
            cw, ch = canvas_size()
            x0, y0 = state["crop_drag"]
            x1, y1 = min(max(e.x, 0), cw), min(max(e.y, 0), ch)
            if x1 < x0:
                x0, x1 = x1, x0
            if y1 < y0:
                y0, y1 = y1, y0
            if (x1 - x0) >= 5 and (y1 - y0) >= 5:
                state["crop"] = [x0 / cw, y0 / ch, x1 / cw, y1 / ch]
            else:
                state["crop"] = None
            render_main()

        def on_release(e):
            state["crop_drag"] = None
            render_main()

        # ---- timeline events ---------------------------------------------
        def on_tl_press(e):
            player.stop()
            play_btn.config(text="▶  Play από εδώ")
            if STRIP_H <= e.y < STRIP_H + BAR_H:
                h = nearest_handle(e.x)
                if h is not None:
                    state["drag"] = ("bound", h)
                    state["seg"] = h
                    render_timeline()
                    return
                state["drag"] = None
                state["seg"] = seg_at(e.x)
                toggle_seg(state["seg"])
                render_timeline()
                refresh_frames()
                return
            state["drag"] = "play"
            state["play"] = x2t(e.x)
            render_timeline()

        def on_tl_move(e):
            d = state["drag"]
            if d == "play":
                state["play"] = x2t(e.x)
                render_timeline()
            elif isinstance(d, tuple) and d[0] == "bound":
                i = d[1]
                lo = bounds[i - 1] + MIN_SEG
                hi = max(lo, bounds[i + 1] - MIN_SEG)
                bounds[i] = max(lo, min(hi, x2t(e.x)))
                render_timeline()
                update_info()

        def on_tl_release(e):
            was = state["drag"]
            state["drag"] = None
            if was == "play":
                refresh_frames()
            elif isinstance(was, tuple):
                refresh_frames()

        # ---- apply -------------------------------------------------------
        def apply_and_close():
            kept = self._tl_kept_ranges(bounds, keep)
            if not kept:
                messagebox.showwarning("Edit", "Δεν κράτησες κανένα κομμάτι. Άφησε τουλάχιστον "
                                                "ένα κομμάτι σε ΚΡΑΤΑ.")
                return
            target = self.media_files[idx][2]
            target["crop"] = list(state["crop"]) if state["crop"] else None
            brightness, color = color_ui.values()
            target["brightness"] = brightness
            target["color"] = color
            target["audio"] = state["audio"]
            # Optional per-slider "apply to all videos" switches.
            if color_ui.apply_brightness.get():
                for item in self.media_files:
                    if item[0] == "video":
                        item[2]["brightness"] = brightness
            if color_ui.apply_color.get():
                for item in self.media_files:
                    if item[0] == "video":
                        item[2]["color"] = color
            # trim_start/trim_end stay meaningful for the preview and for any
            # older build reading the project; "segments" carries the real cut.
            target["trim_start"] = 0.0 if kept[0][0] < 0.005 else round(kept[0][0], 3)
            target["trim_end"] = (None if kept[-1][1] >= duration - 0.005
                                  else round(kept[-1][1], 3))
            if len(kept) > 1:
                target["segments"] = [[round(s, 3), round(e, 3)] for s, e in kept]
            else:
                target["segments"] = None
            if split_var.get() and len(kept) > 1:
                m_type, m_path = self.media_files[idx][0], self.media_files[idx][1]
                new_items = []
                for s, e in kept:
                    ed = dict(target)
                    ed["segments"] = None
                    ed["trim_start"] = 0.0 if s < 0.005 else round(s, 3)
                    ed["trim_end"] = None if e >= duration - 0.005 else round(e, 3)
                    new_items.append((m_type, m_path, ed))
                self.media_files[idx:idx + 1] = new_items
            self.is_modified = True
            self.update_media_display()
            player.stop()
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(fill='x', padx=12, pady=(8, 10))
        ttk.Button(btns, text="✂ Χωρισμός εδώ (νέο σημείο)", command=split_here).pack(side='left', padx=3)
        ttk.Button(btns, text="Διαγραφή σημείου", command=delete_point).pack(side='left', padx=3)
        ttk.Button(btns, text="ΚΡΑΤΑ / ΠΕΤΑ", command=lambda: toggle_seg(state["seg"])).pack(side='left', padx=3)
        ttk.Button(btns, text="Καθαρισμός crop", command=clear_crop).pack(side='left', padx=3)
        ttk.Button(btns, text="Επαναφορά", command=reset_all).pack(side='left', padx=3)
        ttk.Button(btns, text="Άκυρο", command=lambda: (player.stop(), dlg.destroy())).pack(side='right', padx=3)
        ttk.Button(btns, text="Εφαρμογή", command=apply_and_close).pack(side='right', padx=3)

        def _on_destroy(e):
            if e.widget is dlg:
                player.stop()
        dlg.bind("<Destroy>", _on_destroy)

        canvas.bind("<Button-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)
        tl.bind("<Button-1>", on_tl_press)
        tl.bind("<B1-Motion>", on_tl_move)
        tl.bind("<ButtonRelease-1>", on_tl_release)

        render_timeline()
        render_main()
        update_info()
        dlg.after(60, lambda: threading.Thread(target=load_strip, daemon=True).start())
        dlg.after(80, lambda: refresh_frames(0))
