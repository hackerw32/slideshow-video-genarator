# Slideshow Video Creator Pro (Beta v2)

Επαγγελματική εφαρμογή δημιουργίας slideshow videos με μουσική για αγγελίες ακινήτων.
Συνδυάζει εικόνες, videos, κείμενο και μουσική για να φτιάξεις ελκυστικά videos για social media χωρίς πρόγραμμα επεξεργασίας βίντεο.

## Εγκατάσταση

1. Python 3.8+

2. Εγκατάσταση dependencies:
```bash
pip install -r requirements.txt
```

## Εκτέλεση

```bash
python slideshow_app_beta.py
```

## Χρήση

1. **Προσθήκη Media:**
   - Κλικ στα κουμπιά "+ Video" και "+ Image"
   - Drag & Drop αρχεία απευθείας στη βιβλιοθήκη (αν είναι εγκατεστημένο tkinterdnd2)
   - Δεξί κλικ σε κάθε media για Delete, Move, Change Position

2. **Κείμενο:**
   - Κλικ "Text Input" για να ανοίξει το παράθυρο κειμένου
   - Χρησιμοποίησε `**κείμενο**` για bold
   - Υποστηρίζει Ελληνικούς χαρακτήρες και πολλές γραμμές

3. **Ρυθμίσεις:**
   - **Settings > Audio & Music Settings:** Volume (dB), mute video audio, music folder, crossfade, trim silence
   - **Settings > Video Settings:** Ανάλυση (1080x1080 ή 1920x1080), background mode, cropping, slide duration, auto position
   - **Settings > Text Settings:** Font size, font family

4. **Preview:**
   - Κλικ "Generate Preview Frame" για να δεις την πρώτη εικόνα/frame με κείμενο

5. **Export:**
   - Διάλεξε output folder, δώσε όνομα project
   - Κλικ "GENERATE VIDEO"

## Features

✅ Media library με thumbnail/icon view και list view
✅ Drag & Drop media files
✅ Reorder media με δεξί κλικ (Move Up/Down, Change Position, Delete)
✅ Ξεχωριστό παράθυρο text input (με clipboard paste)
✅ Αυτόματο tracking μουσικής (δεν επαναλαμβάνει τραγούδια)
✅ Configurable music folder
✅ Crossfade μεταξύ τραγουδιών
✅ Auto trim silence
✅ Fit χωρίς cropping με επιλογές background (λευκό, μαύρο, blurred)
✅ Enable Cropping (Fill Frame)
✅ Auto position photos/videos (κείμενο κάτω, εικόνα πάνω)
✅ Slide duration ρυθμιζόμενο ανά project
✅ Preview frame γρήγορα
✅ Save/Load projects
✅ Volume control (dB)
✅ Markdown bold support (**text**)
✅ Mute original video audio

## Μουσική

- Τοποθέτησε αρχεία `.mp4` (με audio) στον φάκελο `music/` (ή επίλεξε άλλο φάκελο στα Audio Settings)
- **Settings > Audio & Music Settings > Refresh Music List** για νέα τραγούδια
- **Reset Used Music** για να ξεκινήσεις από την αρχή

## Διαχείριση Projects

- **File > New Project** – Νέο κενό project
- **File > Save Project** – Αποθήκευση στον φάκελο `projects/`
- **File > Load Project** – Φόρτωση αποθηκευμένου project

## Υποστηριζόμενες μορφές

| Τύπος  | Μορφές                              |
|--------|-------------------------------------|
| Video  | .mp4, .avi, .mov, .mkv              |
| Image  | .jpg, .jpeg, .png, .bmp             |
| Music  | .mp4 (audio track)                  |

## Troubleshooting

**Το βίντεο στο export εμφανίζεται μαύρο**
→ Βεβαιώσου ότι χρησιμοποιείς την τελευταία έκδοση (bug διορθώθηκε)

**Drag & drop δεν λειτουργεί**
→ `pip install tkinterdnd2`

**Το κείμενο δεν γίνεται bold**
→ Χρησιμοποίησε `**κείμενο**` χωρίς κενά μεταξύ `**` και κειμένου

**Η μουσική δεν ακούγεται**
→ Έλεγξε ότι τα `.mp4` στο music folder έχουν audio track

**Το export παγώνει**
→ Περίμενε — μεγάλα projects παίρνουν χρόνο. Δες την progress bar.

## Τεχνικές πληροφορίες

- Γλώσσα: Python 3.8+
- GUI: Tkinter
- Video Processing: FFmpeg (subprocess) + MoviePy
- Image Processing: Pillow (PIL)
- Codec: H.264 (libx264) / AAC

## Δομή φακέλων

```
slideshow-video-genarator/
├── slideshow_app_beta.py   # Κύρια εφαρμογή (v2 Beta)
├── slideshow_app.py        # Πρώτη έκδοση (v1)
├── requirements.txt
├── settings.json
├── music_tracker.json
├── music/                  # Μουσική (.mp4 files)
├── projects/               # Αποθηκευμένα projects (.json)
└── temp/                   # Προσωρινά αρχεία (auto-created)
```

## Versions

**v2 Beta (Current)**
- Media library με thumbnail/icon view
- Drag & drop + reorder media
- Ξεχωριστό text input window
- Configurable music folder
- Crossfade & trim silence
- Auto position για photos και videos
- Ρυθμιζόμενο slide duration
- Διόρθωση: video clips εμφανίζονται σωστά στο export

**v1**
- Βασική δημιουργία slideshow
- Music tracking
- Project management
- Multiple video settings
