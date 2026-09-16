"""Slideshow Video Creator Pro — entry point.

Εκτέλεση:  python "slideshow_app v4.py"

Η εφαρμογή ζει πλέον στο πακέτο ``slideshow/`` (ένα αρχείο ανά αρμοδιότητα).
Αυτό το αρχείο υπάρχει μόνο για να ξεκινάει την εφαρμογή, ώστε η εντολή που
χρησιμοποιούσες μέχρι τώρα να δουλεύει ακριβώς όπως πριν.

Η παλιά μονολιθική έκδοση φυλάσσεται στο
``old/slideshow_app v4 (single file, πριν το σπάσιμο).py``.
"""
import sys
import tkinter as tk
from pathlib import Path

# Επιτρέπει το `import slideshow` ανεξάρτητα από τον φάκελο εκτέλεσης.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from slideshow.deps import TKDND_AVAILABLE, TkinterDnD  # noqa: E402
from slideshow.app import SlideshowApp                  # noqa: E402


def main():
    root = TkinterDnD.Tk() if TKDND_AVAILABLE else tk.Tk()
    SlideshowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
