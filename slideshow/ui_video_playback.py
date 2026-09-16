"""In-dialog video playback for the video Edit window.

ffmpeg streams frames (raw RGB, paced with ``-re`` so they arrive in real time)
into a Tk callback, letting the editor paint them on its own canvas and move its
playhead instead of opening a separate player window. The optional sound is
played by a parallel ``ffplay -nodisp`` (audio only, no window).
"""

import shutil
import subprocess
import threading

from .deps import Image


class VideoPreviewPlayer:
    """Streams a video into ``on_frame(image, seconds)`` on the Tk main thread."""

    def __init__(self, root, path, width, height, on_frame, on_finish=None, fps=15):
        self.root = root
        self.path = str(path)
        self.width = max(2, int(width))
        self.height = max(2, int(height))
        self.on_frame = on_frame
        self.on_finish = on_finish
        self.fps = max(1, int(fps))
        self._proc = None
        self._audio = None
        self._stop = threading.Event()

    def is_playing(self):
        return self._proc is not None and self._proc.poll() is None

    def set_size(self, width, height):
        self.width = max(2, int(width))
        self.height = max(2, int(height))

    def start(self, start=0.0, duration=None, with_audio=False, volume=1.0):
        self.stop()
        self._stop.clear()
        self._start_audio(start, duration, with_audio, volume)
        threading.Thread(target=self._run, args=(max(0.0, start), duration),
                         daemon=True).start()

    def stop(self):
        self._stop.set()
        for p in (self._proc, self._audio):
            if p is not None:
                try:
                    p.terminate()
                except Exception:
                    pass
        self._proc = None
        self._audio = None

    def _start_audio(self, start, duration, with_audio, volume):
        if not with_audio:
            return
        exe = shutil.which("ffplay")
        if not exe:
            return
        args = [exe, "-nodisp", "-autoexit", "-loglevel", "error",
                "-volume", str(int(max(0, min(100, volume * 100))))]
        args += ["-ss", f"{max(0.0, start):.3f}"]
        if duration and duration > 0.05:
            args += ["-t", f"{duration:.3f}"]
        args += [self.path]
        try:
            self._audio = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
        except Exception:
            self._audio = None

    def _run(self, start, duration):
        w, h = self.width, self.height
        vf = (f"fps={self.fps},scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
        args = ["ffmpeg", "-nostdin", "-re", "-ss", f"{start:.3f}", "-i", self.path,
                "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24"]
        if duration and duration > 0.05:
            args += ["-t", f"{duration:.3f}"]
        args += ["-"]
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            self.root.after(0, self._finish)
            return
        self._proc = proc
        frame_bytes = w * h * 3
        idx = 0
        try:
            while not self._stop.is_set():
                data = proc.stdout.read(frame_bytes)
                if not data or len(data) < frame_bytes:
                    break
                img = Image.frombytes("RGB", (w, h), data)
                self.root.after(0, self.on_frame, img, start + idx / self.fps)
                idx += 1
        except Exception:
            pass
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            if self._audio is not None:
                try:
                    self._audio.terminate()
                except Exception:
                    pass
                self._audio = None
            self._proc = None
            self.root.after(0, self._finish)

    def _finish(self):
        if self.on_finish:
            self.on_finish()
