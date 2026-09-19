# AGENTS.md — οδηγίες για τον AI βοηθό

Project: **Slideshow Video Creator Pro** (Python + Tkinter, Windows).

## Ροή εργασίας (ΣΗΜΑΝΤΙΚΟ)
- **Κάνε τις αλλαγές κώδικα ΕΔΩ** σε αυτόν τον φάκελο (το καθαρό repo), **ποτέ** απευθείας στον φάκελο που τρέχει ο χρήστης.
- Αφού ολοκληρώσεις και επαληθεύσεις:
  1. `git add -A`
  2. `git commit -m "σύντομο αγγλικό μήνυμα"`
  3. `git push origin main` — τα credentials είναι αποθηκευμένα, το push δεν ζητάει prompt.
  4. **Αντίγραψε τα αρχεία που άλλαξαν** στον φάκελο που τρέχει ο χρήστης (βλ. «Τοποθεσίες»).
- **Ποτέ μην κάνεις commit** δεδομένα χρήστη: `settings.json` (περιέχει το API key),
  `projects/`, `music/`, `models/`, `temp/`, `erase_cache/`, `ffmpeg/`, `dist/`, `release/`, `logo.jpg`.
  Είναι ήδη στο `.gitignore`.

## Τοποθεσίες
- **GitHub**: https://github.com/hackerw32/slideshow-video-genarator (branch `main`)
- **Καθαρό repo (αυτός ο φάκελος)**: `C:\Users\George\Desktop\python projects\slideshow app`
- **Φάκελος χρήστη (runtime / sync target)**: `C:\Users\George\Desktop\python projects\slideshow_rita_aggelia`
  (ΔΕΝ είναι git repo — μην τρέχεις git εκεί.)

## Περιβάλλον / εκτέλεση
- Windows. Στο dev PC η Python με τα dependencies είναι μέσω `py` (pythoncore 3.14)·
  το σκέτο `python` μπορεί να δείχνει σε άλλη εγκατάσταση χωρίς τα dependencies → χρησιμοποίησε `py`.
- Εκτέλεση: `python "slideshow_app v4.py"` ή `run.bat`.
- Απαιτείται **FFmpeg** (ο τοπικός φάκελος `ffmpeg/` ή στο PATH).
- Ο κώδικας, τα projects, οι ρυθμίσεις και το `models/` ζουν στον φάκελο του launcher (`APP_DIR`).

## Δομή
- `slideshow_app v4.py` — εκκινητής (μόνο ξεκινάει την εφαρμογή).
- `slideshow/` — ο κώδικας, ένα αρχείο ανά αρμοδιότητα (mixins που συνθέτει το `SlideshowApp`).
- `install.bat` / `install.ps1` — one-click εγκατάσταση σε νέο PC (Python + venv + FFmpeg).
- `run.bat` — εκκίνηση με το `.venv`.
- `build_exe.bat` / `build_exe.ps1` — standalone `.exe` (PyInstaller, auto-version από `build_version.json`).

## Κανόνες κώδικα
- **Στόχος ~400–800 γραμμές ανά αρχείο· hard cap ~1500.** Αν κάτι θα το ξεπεράσει, πρότεινε σπάσιμο πρώτα.
- Ένα θέμα ανά αρχείο.
- Σχόλια μόνο όπου προσθέτουν πληροφορία.
- Μην αλλάζεις αρχεία δεδομένων του χρήστη.

## Επαλήθευση πριν το «έτοιμο»
- `py -m py_compile` στα αρχεία που άλλαξαν (ή σε όλα τα `slideshow\*.py`).
- Μία εκκίνηση της εφαρμογής.
- Αν αγγίζεις export / erase / audio: ένα μικρό δοκιμαστικό export.
