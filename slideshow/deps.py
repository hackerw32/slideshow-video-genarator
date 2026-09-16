"""Third-party imports shared by the whole app (imported once)."""
try:
    from PIL import Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.Resampling.LANCZOS

    from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
    import numpy as np
except ImportError as e:
    print(f"Missing dependencies: {e}")
    exit(1)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    # Bound to None (not left undefined) so `from .deps import TkinterDnD`
    # never raises for users without the optional drag & drop package.
    DND_FILES = None
    TkinterDnD = None
    TKDND_AVAILABLE = False
