"""Per-media, non-destructive edit data: crop / brightness / colour / trim."""

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


class MediaEditMixin:
    """Per-media, non-destructive edit data: crop / brightness / colour / trim."""

    @staticmethod
    def default_edit(m_type):
        if m_type == "image":
            return {"crop": None, "brightness": 1.0, "color": 1.0, "erase": None}
        # "segments" is the multi-cut timeline: a list of [start, end] kept
        # ranges in seconds. None means the classic single trim_start/trim_end
        # range, which is what every project saved before multi-cut has.
        # brightness / color (saturation) work for videos too, like photos.
        # "audio": None means "follow the global video_audio setting"; True/False
        # is a per-video override (unmute / mute) set from the Edit dialog.
        return {"crop": None, "trim_start": 0.0, "trim_end": None, "segments": None,
                "brightness": 1.0, "color": 1.0, "audio": None}


    @classmethod
    def normalize_item(cls, item):
        """Return a (type, path, edit) tuple from old or new project data."""
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            return None
        m_type, path = item[0], item[1]
        edit = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
        base = dict(cls.default_edit(m_type))
        base.update(edit)
        return (m_type, path, base)


    def _new_item(self, m_type, path):
        return (m_type, path, self.default_edit(m_type))


    def normalize_media_list(self, items):
        out = []
        for it in items or []:
            norm = self.normalize_item(it)
            if norm is not None:
                out.append(norm)
        return out


    @staticmethod
    def has_edit(edit):
        if not edit:
            return False
        if edit.get("crop"):
            return True
        if abs(float(edit.get("brightness", 1.0) or 1.0) - 1.0) > 1e-3:
            return True
        if abs(float(edit.get("color", 1.0) or 1.0) - 1.0) > 1e-3:
            return True
        if float(edit.get("trim_start", 0.0) or 0.0) > 0.001:
            return True
        if edit.get("trim_end") is not None:
            return True
        # A multi-cut edit can keep the whole start and the whole end (so both
        # trim_* look untouched) while still dropping the middle.
        segs = edit.get("segments")
        if isinstance(segs, (list, tuple)) and len(segs) > 1:
            return True
        if edit.get("audio") is not None:
            return True
        return bool(edit.get("erase"))


    # -------------------------------------------------------- erase (photo)
    def _erase_engine(self):
        """One EraseEngine per app; the LaMa model loads lazily on first use."""
        engine = getattr(self, "_erase_engine_obj", None)
        if engine is None:
            from .erase import EraseEngine, MODEL_DIR_NAME
            engine = EraseEngine(self.app_dir / MODEL_DIR_NAME)
            self._erase_engine_obj = engine
        return engine

    def _apply_erase(self, img, strokes, path=None):
        """Run the stored strokes through the eraser, with a small cache.

        Inpainting costs a couple of seconds per photo, so the result is cached
        per (path, source size, strokes, engine). The strokes are the only
        input that ever changes, so the key is exact whenever the path is
        known; without a path we simply do not cache.
        """
        if not strokes:
            return img
        key = None
        if path is not None:
            from .erase import strokes_key
            key = (str(path), img.size, strokes_key(strokes), self._erase_engine().engine_name)
            cached = getattr(self, "_erase_cache", None)
            if cached is None:
                cached = self._erase_cache = {}
            if key in cached:
                return cached[key].copy()
        out = self._erase_engine().erase(img, strokes)
        if key is not None:
            cache = self._erase_cache
            cache[key] = out.copy()
            while len(cache) > 12:                  # keep the last few photos
                cache.pop(next(iter(cache)))
        return out


    def _global_color(self, m_type):
        """Global brightness / saturation from Settings for this media type."""
        key = "photo" if m_type == "image" else "video"
        return (float(self.settings.get(f"{key}_brightness", 1.0) or 1.0),
                float(self.settings.get(f"{key}_color", 1.0) or 1.0))


    def _combined_color(self, edit, m_type):
        """Per-item brightness/colour multiplied by the global setting.

        The global sliders are a base for every photo/video; each item's own
        Edit values scale on top of it, so 1.0 means "no extra change".
        """
        edit = edit or {}
        eb = float(edit.get("brightness", 1.0) or 1.0)
        ec = float(edit.get("color", 1.0) or 1.0)
        gb, gc = self._global_color(m_type)
        return eb * gb, ec * gc


    def _video_audio_enabled(self, edit):
        """Whether this video's own sound is kept (per-video override or global)."""
        override = (edit or {}).get("audio")
        if override is None:
            return bool(self.settings.get("video_audio", False))
        return bool(override)


    def _video_has_audio(self, path):
        """True when the file has at least one audio stream (ffprobe)."""
        try:
            p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                                '-show_entries', 'stream=index', '-of', 'csv=p=0', str(path)],
                               capture_output=True, text=True, timeout=30)
            return bool(p.stdout.strip())
        except Exception:
            return False


    def _apply_image_edit(self, img, edit, path=None, m_type="image"):
        """Apply the stored erase / crop / brightness / color of one media item.

        Videos also carry crop / brightness / colour, so the same helper serves
        both. The global Settings values are combined in, so every preview,
        thumbnail and export gets them. ``path`` is only used to cache the
        (slow) erase step, and is optional. Always returns a new image.

        Order matters: erase first, while the coordinates still match the
        original source, then crop and the colour work.
        """
        edit = edit or {}
        img = img.convert("RGB")
        img = self._apply_erase(img, edit.get("erase"), path)
        crop = edit.get("crop")
        if crop and len(crop) == 4:
            iw, ih = img.size
            l, t, r, b = [max(0.0, min(1.0, float(v))) for v in crop]
            x0, y0 = int(l * iw), int(t * ih)
            x1, y1 = int(round(r * iw)), int(round(b * ih))
            if x1 - x0 >= 1 and y1 - y0 >= 1:
                img = img.crop((x0, y0, x1, y1))
        b_v, c_v = self._combined_color(edit, m_type)
        if abs(b_v - 1.0) > 1e-3:
            img = ImageEnhance.Brightness(img).enhance(b_v)
        if abs(c_v - 1.0) > 1e-3:
            img = ImageEnhance.Color(img).enhance(c_v)
        return img


    @staticmethod
    def video_crop_filter(edit):
        """ffmpeg filter prefix that crops a video frame to the stored region.

        The crop is expressed in source fractions, so it is resolution
        independent, and the result is rounded to even dimensions because
        yuv420p (what the export encodes) requires them.
        """
        crop = (edit or {}).get("crop")
        if not crop or len(crop) != 4:
            return ""
        cl, ct, cr, cb = [max(0.0, min(1.0, float(x))) for x in crop]
        if cr - cl <= 0.01 or cb - ct <= 0.01:
            return ""
        return (f"crop=iw*{cr - cl:.6f}:ih*{cb - ct:.6f}:iw*{cl:.6f}:ih*{ct:.6f},"
                f"scale=trunc(iw/2)*2:trunc(ih/2)*2,")


    def video_color_filter(self, edit):
        """ffmpeg filter chain for a video's brightness / saturation.

        Uses the item values combined with the global video Settings, so the
        exported video looks like the preview and like the photo export.
        Brightness is a multiply: Pillow's ImageEnhance.Brightness does
        ``p * factor``, which colorlevels reproduces exactly by moving the
        input/output white points. Saturation uses ``eq`` and matches
        ImageEnhance.Color closely. Returns "" when both are neutral, and
        never ends with a comma (callers append one).
        """
        b, c = self._combined_color(edit, "video")
        parts = []
        if abs(b - 1.0) > 1e-3:
            b = max(0.05, min(4.0, b))
            in_white, out_white = (1.0 / b, 1.0) if b >= 1.0 else (1.0, b)
            parts.append("colorlevels=" +
                         ":".join(f"{ch}imin=0" for ch in "rgb") + ":" +
                         ":".join(f"{ch}imax={in_white:.6f}" for ch in "rgb") + ":" +
                         ":".join(f"{ch}omax={out_white:.6f}" for ch in "rgb"))
        if abs(c - 1.0) > 1e-3:
            parts.append(f"eq=saturation={max(0.0, min(3.0, c)):.4f}")
        return ",".join(parts)


    @staticmethod
    def video_trim(edit, full_dur):
        """(start, duration) seconds actually encoded for a video item."""
        ts = max(0.0, min(float((edit or {}).get("trim_start") or 0.0),
                          max(0.0, full_dur - 0.1)))
        te = (edit or {}).get("trim_end")
        if te is not None:
            return ts, max(0.1, min(float(te), full_dur) - ts)
        return ts, max(0.1, full_dur - ts)


    @staticmethod
    def video_trim_filter(segs):
        """ffmpeg filter prefix that turns the kept segments into one stream.

        Returns ``[0:v]`` when nothing has to be trimmed (a single kept range
        covering the seek), otherwise a trim + concat graph ending in the
        ``[vc]`` label, which the caller appends its crop/scale chain to. The
        times must already be relative to the caller's input seek.
        """
        if len(segs) <= 1:
            return "[0:v]"
        first = segs[0][0]
        rel = [(max(0.0, s - first), max(0.05, d)) for s, d in segs]
        chunks = [f"[0:v]trim=start={s:.3f}:duration={d:.3f},setpts=PTS-STARTPTS[c{k}]"
                  for k, (s, d) in enumerate(rel)]
        chunks.append("".join(f"[c{k}]" for k in range(len(rel))) +
                      f"concat=n={len(rel)}:v=1:a=0[vc]")
        return ";".join(chunks) + ";[vc]"


    @staticmethod
    def video_keep_segments(edit, full_dur):
        """Every (start, duration) actually encoded for a video item.

        ``segments`` (the multi-cut timeline) wins when it holds more than one
        usable range; otherwise the classic single trim_start/trim_end range is
        used, so projects saved before multi-cut behave exactly as they did.
        Ranges are clamped to the real duration and anything shorter than
        0.05s is dropped, so a corrupted project can never produce a broken
        ffmpeg filter.
        """
        edit = edit or {}
        full_dur = max(0.0, float(full_dur or 0.0))
        out = []
        segs = edit.get("segments")
        if isinstance(segs, (list, tuple)):
            for seg in segs:
                if not isinstance(seg, (list, tuple)) or len(seg) < 2:
                    continue
                try:
                    s, e = float(seg[0]), float(seg[1])
                except (TypeError, ValueError):
                    continue
                s = max(0.0, min(s, full_dur))
                e = max(0.0, min(e, full_dur))
                if e - s > 0.05:
                    out.append((s, e - s))
        if out:
            return out
        return [MediaEditMixin.video_trim(edit, full_dur)]


    @staticmethod
    def video_kept_duration(edit, full_dur):
        """Seconds of the source that the export will actually keep."""
        return sum(d for _, d in MediaEditMixin.video_keep_segments(edit, full_dur))


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


    def _video_frame_at(self, path, t):
        """One frame of a video at time t (seconds), rotation applied, via
        ffmpeg - so the video editor previews exactly what the export seeks to.
        Falls back to the cached first frame."""
        try:
            p = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error',
                                '-ss', f"{max(0.0, float(t)):.3f}", '-i', str(path),
                                '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                               capture_output=True, timeout=60)
            if p.returncode == 0 and p.stdout:
                img = Image.open(io.BytesIO(p.stdout))
                img.load()
                return img
        except Exception:
            pass
        return self._video_first_frame(path)


    def _video_duration(self, path):
        """Duration in seconds (ffprobe, then moviepy, else 0)."""
        try:
            p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                               capture_output=True, text=True, timeout=30)
            d = float(p.stdout.strip())
            if d > 0:
                return d
        except Exception:
            pass
        try:
            v = VideoFileClip(str(path))
            try:
                return float(v.duration)
            finally:
                v.close()
        except Exception:
            return 0.0

