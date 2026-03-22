================================================================================
              SLIDESHOW VIDEO CREATOR PRO - BETA v2 - ΟΔΗΓΙΕΣ ΧΡΗΣΗΣ
================================================================================

ΠΕΡΙΓΡΑΦΗ
---------
Επαγγελματική εφαρμογή για δημιουργία video slideshow για αγγελίες ακινήτων.
Συνδυάζει εικόνες, videos, κείμενο και μουσική για να δημιουργήσει
ελκυστικά videos για social media και πλατφόρμες αγγελιών —
χωρίς να χρειάζεται πρόγραμμα επεξεργασίας βίντεο.

ΕΓΚΑΤΑΣΤΑΣΗ
-----------
1. Βεβαιωθείτε ότι έχετε Python 3.8 ή νεότερο εγκατεστημένο

2. Εγκατάσταση dependencies:
   pip install -r requirements.txt

   Απαιτούμενα packages:
   - moviepy        (video processing)
   - pillow         (επεξεργασία εικόνων)
   - numpy          (υπολογισμοί)
   - tkinterdnd2    (drag & drop - προαιρετικό)

3. Εκτέλεση:
   python slideshow_app_beta.py

ΥΠΟΣΤΗΡΙΖΟΜΕΝΕΣ ΜΟΡΦΕΣ
------------------------
   Videos : .mp4, .avi, .mov, .mkv
   Images : .jpg, .jpeg, .png, .bmp
   Music  : .mp4 (αρχεία με audio track)

ΒΑΣΙΚΗ ΧΡΗΣΗ
------------

1. ΠΡΟΣΘΗΚΗ MEDIA FILES
   - Κλικ "+ Video" για προσθήκη video αρχείων
   - Κλικ "+ Image" για προσθήκη εικόνων
   - Drag & Drop — Σύρτε αρχεία απευθείας στη βιβλιοθήκη media
   - Δεξί κλικ σε κάθε thumbnail για: Delete, Move Up/Down, Change Position

   Η βιβλιοθήκη εμφανίζει thumbnails (Icons view) ή απλή λίστα (List view).
   Τα video clips εμφανίζονται σωστά (με background και κείμενο) στο export.

2. ΚΕΙΜΕΝΟ (Text Overlay)
   - Κλικ "Text Input" για να ανοίξει το παράθυρο κειμένου
   - Γράψτε το κείμενο της αγγελίας
   - Χρησιμοποιήστε **κείμενο** για bold (π.χ. **Τιμή: 300.000€**)
   - Υποστηρίζει πολλές γραμμές και Ελληνικούς χαρακτήρες
   - Κουμπί "Quick Paste Clipboard" για γρήγορη επικόλληση

   Παράδειγμα:
   **Πωλείται Διαμέρισμα 100τ.μ.**

   Περιοχή: Κέντρο Αθήνας
   Τιμή: **250.000€**
   Τηλέφωνο: 6977123456

3. PREVIEW (Προεπισκόπηση)
   - Κλικ "Generate Preview Frame"
   - Εμφανίζει άμεσα το πρώτο frame με κείμενο
   - Πολύ γρήγορο — χωρίς rendering ολόκληρου video

4. ΕΞΑΓΩΓΗ VIDEO
   - Γράψτε όνομα project στο πεδίο "Project Name"
   - Επιλέξτε output folder (Browse)
   - Κλικ "GENERATE VIDEO"
   - Παρακολουθήστε την progress bar

ΡΥΘΜΙΣΕΙΣ (Settings Menu)
--------------------------

1. AUDIO & MUSIC SETTINGS
   - Music Volume   : Ρύθμιση έντασης μουσικής (-20 έως +20 dB)
   - Mute Video Audio: Σίγαση ήχου από τα video files (προτείνεται: ON)
   - Music Folder   : Επιλογή φακέλου μουσικής (default: music/)
   - Refresh Music List: Ανίχνευση νέων τραγουδιών στον φάκελο
   - Reset Used Music: Επαναφορά tracker — όλα τα τραγούδια ξαναγίνονται διαθέσιμα
   - Crossfade (sec): Διάρκεια crossfade μεταξύ τραγουδιών
   - Auto Trim Silence: Αυτόματη αφαίρεση σιωπής

2. VIDEO SETTINGS
   - Resolution:
     • 1080x1080 (Square) — Για Instagram, Facebook
     • 1920x1080 (16:9)   — Για YouTube, widescreen

   - Background Mode (όταν δεν γίνεται crop):
     • White  — Λευκό φόντο
     • Black  — Μαύρο φόντο
     • Blur   — Θολό φόντο από την ίδια εικόνα/frame

   - Enable Cropping  : Γέμισμα frame (crop αντί για fit)
   - Auto position photos: Zoom out φωτογραφίες για να φαίνεται το κείμενο κάτω
   - Auto position videos: Ίδιο για video clips
   - Slide Duration (sec): Διάρκεια κάθε εικόνας στο slideshow

3. TEXT SETTINGS
   - Font Size   : Μέγεθος γραμματοσειράς (10-150)
   - Font Family : Calibri, Arial, Verdana, Georgia

ΔΙΑΧΕΙΡΙΣΗ ΜΟΥΣΙΚΗΣ
--------------------
- Τοποθετήστε αρχεία .mp4 (με audio track) στον φάκελο music/
  ή επιλέξτε διαφορετικό φάκελο στα Audio & Music Settings.
- Η εφαρμογή θυμάται ποια τραγούδια έχετε χρησιμοποιήσει και επιλέγει
  αυτόματα το επόμενο αχρησιμοποίητο.
- Όταν εξαντληθούν όλα, ξεκινάει αυτόματα από την αρχή.
- Αν το video είναι μεγαλύτερο από ένα τραγούδι, κάνει chaining αυτόματα.

ΔΙΑΧΕΙΡΙΣΗ PROJECTS
--------------------
- File > New Project  : Νέο κενό project
- File > Save Project : Αποθήκευση στον φάκελο projects/
- File > Load Project : Φόρτωση με λίστα επιλογής

ΧΑΡΑΚΤΗΡΙΣΤΙΚΑ v2 BETA
-----------------------
✅ Media library με thumbnail/icon view και list view
✅ Drag & Drop media files στη βιβλιοθήκη
✅ Reorder media με δεξί κλικ (Move Up/Down, Change Position, Delete)
✅ Ξεχωριστό παράθυρο text input με Quick Paste
✅ Αυτόματο tracking μουσικής
✅ Configurable music folder
✅ Crossfade μεταξύ τραγουδιών
✅ Auto trim silence
✅ Background modes: λευκό, μαύρο, blur
✅ Enable Cropping (Fill Frame)
✅ Auto position photos και videos (κείμενο κάτω)
✅ Slide duration ρυθμιζόμενο
✅ Preview frame άμεσο
✅ Save/Load projects
✅ Volume control (dB)
✅ Markdown bold support (**text**)
✅ Mute original video audio
✅ Σωστή εμφάνιση video clips στο exported video (bug fix)

ΣΥΜΒΟΥΛΕΣ ΧΡΗΣΗΣ
-----------------
1. Κάντε πάντα Preview πριν το Export
2. Χρησιμοποιήστε 1080x1080 για Instagram/Facebook
3. Χρησιμοποιήστε 1920x1080 για YouTube/Website
4. Κρατήστε το κείμενο σύντομο και ευανάγνωστο
5. Χρησιμοποιήστε bold για σημαντικές πληροφορίες (τιμή, τηλέφωνο)
6. Αποθηκεύστε το project πριν το export (File > Save Project)
7. Δοκιμάστε διαφορετικά background modes για καλύτερο αποτέλεσμα

TROUBLESHOOTING
---------------
Πρόβλημα: Το βίντεο στο export εμφανίζεται μαύρο
Λύση: Βεβαιωθείτε ότι χρησιμοποιείτε την τελευταία έκδοση (bug έχει διορθωθεί)

Πρόβλημα: Drag & drop δεν λειτουργεί
Λύση: pip install tkinterdnd2

Πρόβλημα: Το κείμενο δεν γίνεται bold
Λύση: Χρησιμοποιήστε **κείμενο** (χωρίς κενά μεταξύ ** και κειμένου)

Πρόβλημα: Η μουσική δεν ακούγεται
Λύση: Ελέγξτε ότι τα .mp4 στο music folder έχουν audio track

Πρόβλημα: Το export παγώνει
Λύση: Περιμένετε — μεγάλα projects παίρνουν χρόνο. Δείτε την progress bar.

Πρόβλημα: Κείμενο δεν φαίνεται καθαρά
Λύση: Αυξήστε το font size στα Text Settings

Πρόβλημα: Blurred background δεν λειτουργεί
Λύση: Απενεργοποιήστε "Enable cropping" στα Video Settings

ΤΕΧΝΙΚΕΣ ΠΛΗΡΟΦΟΡΙΕΣ
---------------------
- Γλώσσα         : Python 3.8+
- GUI Framework  : Tkinter
- Video Processing: FFmpeg (subprocess) + MoviePy
- Image Processing: Pillow (PIL)
- Supported Codecs: H.264 (libx264)
- Audio Codec    : AAC

ΔΟΜΗ ΦΑΚΕΛΩΝ
------------
slideshow-video-genarator/
├── slideshow_app_beta.py   # Κύρια εφαρμογή (v2 Beta) ← ΑΥΤΗ ΧΡΗΣΙΜΟΠΟΙΕΙΣ
├── slideshow_app.py        # Πρώτη έκδοση (v1)
├── requirements.txt
├── settings.json           # Ρυθμίσεις χρήστη
├── music_tracker.json      # Tracking μουσικής
├── music/                  # Φάκελος μουσικής (.mp4 files)
├── projects/               # Αποθηκευμένα projects (.json)
├── temp/                   # Προσωρινά αρχεία (auto-created)
└── README.txt              # Αυτό το αρχείο

VERSIONS
--------
v2 Beta (Current)
- Media library με thumbnail/icon view
- Drag & drop + reorder media
- Ξεχωριστό text input window με Quick Paste
- Configurable music folder
- Crossfade & trim silence settings
- Auto position για photos και videos ξεχωριστά
- Ρυθμιζόμενο slide duration
- Bug fix: video clips εμφανίζονται σωστά στο export

v1 (Initial)
- Βασική δημιουργία slideshow
- Music tracking
- Project management
- Multiple video settings

================================================================================
                        Καλή δημιουργία!
================================================================================
