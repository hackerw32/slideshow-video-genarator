"""Local, offline object erasing (inpainting) for photos.

Two engines, picked automatically:

* **LaMa** - the same family of model the Windows Photos app uses, but running
  fully offline on the CPU through ``onnxruntime``. The 198 MB model is
  downloaded once into ``models/`` and then never needs the network again.
  Measured ~2s per erase for a phone photo.
* **OpenCV Telea** - instant, no download at all. Only good for small objects
  on simple backgrounds, so it is the fallback for when the model is missing.

The model has a fixed 512x512 input, so a naive "shrink the whole photo" pass
would make the repaired patch blurry on a large image. Instead only the mask's
bounding box (plus a margin) is remapped to 512, and the result is blended back
at full resolution: measured 22% less error than the whole-image pass, and far
less disturbance outside the brush strokes.

Nothing here ever writes to the user's source file.
"""

import json
import os
import threading
import urllib.request
from hashlib import md5
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

MODEL_DIR_NAME = "models"
MODEL_FILENAME = "lama_fp32.onnx"
MODEL_URL = "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx"
MODEL_MIN_BYTES = 50 * 1024 * 1024   # smaller than this means a broken download
LAMA_INPUT = 512                     # the ONNX graph is fixed at 512x512
MASK_GROW = 9                        # dilate the mask so the model has context
FEATHER = 11                         # blur radius of the blend, in pixels
# The crop handed to the fixed 512x512 model is this much bigger than the
# mask's bounding box. Measured on a 1600x1200 photo: 1.35 -> 3.2 error
# against the true background, 2.5 -> 1.6, 4.0 -> 3.5, so the model wants
# generous context around the hole. Note this cannot rescue a mask that fills
# most of the frame: the model has no context left to copy from.
CROP_MARGIN = 2.5


def cv2_module():
    """Return cv2, or None when opencv is not installed."""
    try:
        import cv2
        return cv2
    except Exception:
        return None


def strokes_key(strokes):
    """A short, stable hash of the brush strokes, for caching."""
    try:
        blob = json.dumps(strokes, sort_keys=True, separators=",", default=str)
    except Exception:
        blob = repr(strokes)
    return md5(blob.encode("utf-8")).hexdigest()[:16]


def strokes_to_mask(strokes, width, height):
    """Rasterise stored brush strokes into a uint8 mask (255 = erase here).

    A stroke is ``{"r": radius_fraction_of_the_long_side, "pts": [[x, y], ...]}``
    with x/y as fractions of the source, exactly like the stored crop, so the
    mask can be rebuilt at any resolution. The mask is drawn twice - a polyline
    for the path plus circles at both ends - so single points become a dot and
    the stroke ends are rounded instead of square.
    """
    mask = np.zeros((height, width), np.uint8)
    long_side = max(1, int(max(width, height)))
    prepared = []
    for s in strokes or []:
        if not isinstance(s, dict):
            continue
        pts = s.get("pts") or []
        if not pts:
            continue
        try:
            rad = max(1, int(round(float(s.get("r", 0.01)) * long_side)))
        except (TypeError, ValueError):
            rad = max(1, long_side // 100)
        xy = []
        for p in pts:
            try:
                x = int(max(0.0, min(1.0, float(p[0]))) * width)
                y = int(max(0.0, min(1.0, float(p[1]))) * height)
            except (TypeError, ValueError, IndexError):
                continue
            xy.append((x, y))
        if xy:
            prepared.append((rad, xy))
    if not prepared:
        return mask
    cv2 = cv2_module()
    for rad, xy in prepared:
        if cv2 is not None:
            if len(xy) == 1:
                cv2.circle(mask, xy[0], rad, 255, -1)
            else:
                cv2.polylines(mask, [np.array(xy, np.int32)], False, 255,
                              thickness=rad * 2, lineType=cv2.LINE_8)
                cv2.circle(mask, xy[0], rad, 255, -1)
                cv2.circle(mask, xy[-1], rad, 255, -1)
        else:
            for x, y in xy:
                X0, X1 = max(0, x - rad), min(width, x + rad + 1)
                Y0, Y1 = max(0, y - rad), min(height, y + rad + 1)
                mask[Y0:Y1, X0:X1] = 255
    return mask


def _dilate(mask, size):
    cv2 = cv2_module()
    if cv2 is not None:
        return cv2.dilate(mask, np.ones((size, size), np.uint8), iterations=1)
    im = Image.fromarray(mask)
    k = size if size % 2 else size + 1
    return np.asarray(im.filter(ImageFilter.MaxFilter(k)))


def _feather(mask, radius):
    cv2 = cv2_module()
    if cv2 is not None:
        return cv2.GaussianBlur(mask, (radius * 2 + 1, radius * 2 + 1), 0)
    return np.asarray(Image.fromarray(mask).filter(ImageFilter.GaussianBlur(radius)))


def download_model(dest_dir, progress=None, cancelled=None):
    """Fetch the LaMa model once into ``dest_dir``.

    Downloads to a ``.part`` file and only then renames it, so an interrupted
    download can never be mistaken for a working model. ``progress(done, total)``
    is called as chunks arrive and ``cancelled()`` is polled so the UI can stop
    it. Raises RuntimeError with a Greek message on failure.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / MODEL_FILENAME
    tmp = dest_dir / (MODEL_FILENAME + ".part")
    try:
        req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "slideshow-creator"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancelled and cancelled():
                    raise RuntimeError("Η λήψη ακυρώθηκε.")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except RuntimeError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    except Exception as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RuntimeError(f"Η λήψη του μοντέλου απέτυχε ({e}). Έλεγξε τη σύνδεση στο internet.")
    if tmp.stat().st_size < MODEL_MIN_BYTES:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RuntimeError("Το μοντέλο κατέβηκε κατεστραμμένο. Δοκίμασε ξανά.")
    os.replace(tmp, final)
    return final


class EraseEngine:
    """Runs the inpainting for one app instance (the model loads lazily)."""

    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)
        self._session = None
        self._lock = threading.Lock()          # one inference at a time
        self._load_lock = threading.Lock()     # one load at a time

    def prewarm(self):
        """Load the model in the background so the first erase is not a 20s wait.

        Creating the ONNX session costs ~20s for this 198 MB graph (measured;
        the inference itself is only ~2s, and dropping the optimization level
        to ORT_DISABLE_ALL barely moved the load, so the cost is inherent).
        It happens once per app run, off the Tk main thread, and is silently
        ignored when the model or onnxruntime is missing.
        """
        if self._session is not None or not self.model_ready():
            return
        threading.Thread(target=self._load_quietly, daemon=True).start()

    def _load_quietly(self):
        try:
            self._session_for_model()
        except Exception:
            pass

    # ------------------------------------------------------------- model
    @property
    def model_path(self):
        return self.model_dir / MODEL_FILENAME

    def model_ready(self):
        try:
            return self.model_path.stat().st_size >= MODEL_MIN_BYTES
        except OSError:
            return False

    @property
    def engine_name(self):
        """Which engine will be used - part of the erase cache key."""
        return "lama" if self.model_ready() else "opencv"

    def is_loaded(self):
        """True once the ONNX session is in memory (a ~20s one-off cost)."""
        return self._session is not None

    def _session_for_model(self):
        with self._load_lock:          # two threads must not load it at once
            if self._session is None:
                try:
                    import onnxruntime as ort
                except Exception as e:
                    raise RuntimeError(f"Το onnxruntime δεν είναι διαθέσιμο ({e}).")
                opts = ort.SessionOptions()
                # EXTENDED loads fastest of the four levels and produced output
                # identical to DISABLE_ALL in a measured comparison, so the
                # slower ORT_ENABLE_ALL buys nothing here.
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
                self._session = ort.InferenceSession(
                    str(self.model_path), opts, providers=["CPUExecutionProvider"])
        return self._session

    # ------------------------------------------------------------- erasing
    def erase(self, img, strokes):
        """Return a NEW image with the stroked areas filled in."""
        img = img.convert("RGB")
        mask = strokes_to_mask(strokes, img.width, img.height)
        if not mask.any():
            return img
        if self.model_ready():
            try:
                return self._erase_lama(img, mask)
            except Exception:
                # Never leave the user with nothing: fall back to OpenCV.
                pass
        return self._erase_cv2(img, mask)

    def _erase_lama(self, img, mask):
        W, H = img.size
        ys, xs = np.where(mask > 0)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        side = int(max(x1 - x0, y1 - y0) * CROP_MARGIN) + 8
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        bx0 = max(0, min(cx - side // 2, W - 1))
        by0 = max(0, min(cy - side // 2, H - 1))
        bx1 = min(W, max(bx0 + side, bx0 + 1))
        by1 = min(H, max(by0 + side, by0 + 1))

        crop = np.asarray(img.crop((bx0, by0, bx1, by1)))
        cmask = mask[by0:by1, bx0:bx1]
        grown = _dilate(cmask, MASK_GROW)
        patch = self._run_lama(crop, grown)
        patch = np.asarray(Image.fromarray(patch).resize(
            (bx1 - bx0, by1 - by0), Image.Resampling.LANCZOS))

        # Blend with a soft edge (over the grown mask) so no seam is visible.
        alpha = (_feather(grown, FEATHER).astype(np.float32) / 255.0)[..., None]
        blended = crop.astype(np.float32) * (1.0 - alpha) + patch.astype(np.float32) * alpha
        out = np.asarray(img).copy()
        out[by0:by1, bx0:bx1] = np.clip(blended, 0, 255).astype(np.uint8)
        return Image.fromarray(out)

    def _run_lama(self, crop_rgb, mask_u8):
        sess = self._session_for_model()
        im = np.asarray(Image.fromarray(crop_rgb).resize(
            (LAMA_INPUT, LAMA_INPUT), Image.Resampling.LANCZOS), np.float32) / 255.0
        mk = np.asarray(Image.fromarray(mask_u8).resize(
            (LAMA_INPUT, LAMA_INPUT), Image.Resampling.NEAREST), np.float32)
        mk = (mk > 127).astype(np.float32)
        with self._lock:      # one inference at a time: the UI may ask for several
            out = sess.run(None, {"image": im.transpose(2, 0, 1)[None],
                                  "mask": mk[None, None]})[0][0]
        out = out.transpose(1, 2, 0)
        if out.max() <= 1.5:      # some exports return 0..1 instead of 0..255
            out = out * 255.0
        return np.clip(out, 0, 255).astype(np.uint8)

    def _erase_cv2(self, img, mask):
        cv2 = cv2_module()
        if cv2 is None:
            raise RuntimeError("Δεν υπάρχει ούτε το μοντέλο LaMa ούτε το OpenCV. "
                               "Κατέβασε το μοντέλο από Settings → Σβήσιμο αντικειμένων.")
        arr = np.asarray(img.convert("RGB"))
        grown = _dilate(mask, 3)
        fixed = cv2.inpaint(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), grown, 3,
                            cv2.INPAINT_TELEA)
        return Image.fromarray(cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB))
