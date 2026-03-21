================================================================================
                    SLIDESHOW VIDEO CREATOR - ΟΔΗΓΙΕΣ ΧΡΗΣΗΣ
================================================================================

ΠΕΡΙΓΡΑΦΗ
---------
Επαγγελματική εφαρμογή για δημιουργία video slideshow για αγγελίες ακινήτων.
Συνδυάζει εικόνες/videos με κείμενο και μουσική για να δημιουργήσει
ελκυστικά videos για social media και πλατφόρμες αγγελιών.

ΕΓΚΑΤΑΣΤΑΣΗ
-----------
1. Βεβαιωθείτε ότι έχετε Python 3.8 ή νεότερο εγκατεστημένο

2. Εγκατάσταση dependencies:
   pip install -r requirements.txt

   Απαιτούμενα packages:
   - moviepy (δημιουργία video)
   - pillow (επεξεργασία εικόνων)
   - numpy (υπολογισμοί)
   - tkinterdnd2 (drag & drop - προαιρετικό)
   - windnd (drag & drop για Windows - προαιρετικό)

3. Εκτέλεση:
   python slideshow_app.py

ΒΑΣΙΚΗ ΧΡΗΣΗ
------------
1. ΠΡΟΣΘΗΚΗ MEDIA FILES
   - Κλικ "Add Videos" για προσθήκη video αρχείων
   - Κλικ "Add Images" για προσθήκη εικόνων
   - ΝΕΟ: Drag & Drop - Σύρτε αρχεία απευθείας στη λίστα media!

   Υποστηριζόμενες μορφές:
   Videos: .mp4, .avi, .mov, .mkv, .wmv, .flv, .webm
   Images: .jpg, .jpeg, .png, .bmp, .gif, .tiff, .webp

2. ΚΕΙΜΕΝΟ (Text Overlay)
   - Γράψτε το κείμενο της αγγελίας
   - Χρησιμοποιήστε **κείμενο** για bold (π.χ. **Τιμή: 300.000€**)
   - Υποστηρίζει πολλές γραμμές και Ελληνικούς χαρακτήρες
   - Δεξί κλικ για Cut/Copy/Paste

   Παράδειγμα:
   **Πωλείται Διαμέρισμα 100τ.μ.**

   Περιοχή: Κέντρο Αθήνας
   Τιμή: **250.000€**
   Τηλέφωνο: 6977123456

3. PREVIEW (Προεπισκόπηση)
   - Κλικ "Generate Preview"
   - ΝΕΟ: Εμφανίζει άμεσα την πρώτη εικόνα με κείμενο
   - Πολύ γρήγορο - χωρίς rendering video
   - Δείχνει ακριβώς πως θα φαίνεται το τελικό αποτέλεσμα

4. ΕΞΑΓΩΓΗ VIDEO
   - Επιλέξτε output folder (θυμάται την τελευταία επιλογή σας)
   - Δώστε όνομα αρχείου
   - Κλικ "Export Video"
   - Αν υπάρχει ήδη αρχείο: Επιλέξτε Overwrite ή Auto-rename

ΡΥΘΜΙΣΕΙΣ (Settings Menu)
--------------------------

1. AUDIO SETTINGS
   - Music Volume: Ρύθμιση έντασης μουσικής (-20 έως +20 dB)
   - Mute Video Audio: Σίγαση ήχου από video αρχεία (προτείνεται: ON)

2. VIDEO SETTINGS
   - Resolution:
     • 1080x1080 (Square) - Για Instagram, Facebook
     • 1920x1080 (16:9) - Για YouTube, widescreen

   - Background Mode (όταν δεν χρησιμοποιείται cropping):
     • White bars - Λευκό φόντο
     • Black bars - Μαύρο φόντο
     • Blurred background - Θολό φόντο από την ίδια εικόνα

   - Enable Cropping: Γέμισμα frame (crop αντί για fit)

   - Auto Position Photos: Zoom out φωτογραφίες για να φαίνεται
     το κείμενο από κάτω (αντί να είναι πάνω στην εικόνα)

3. TEXT SETTINGS
   - Font Size: Μέγεθος γραμματοσειράς (12-72)
   - Font Family: Calibri, Arial, Times New Roman, Verdana, Georgia
   - Text Style: Black text with white background box

ΔΙΑΧΕΙΡΙΣΗ ΜΟΥΣΙΚΗΣ
--------------------
- Τοποθετήστε αρχεία .mp4 (με audio) στον φάκελο music/
- Music > Refresh Music List: Ανίχνευση νέων τραγουδιών
- Music > Reset Used Music: Επαναφορά για επανάληψη τραγουδιών

Η εφαρμογή θυμάται ποια τραγούδια έχετε χρησιμοποιήσει και επιλέγει
αυτόματα το επόμενο αχρησιμοποίητο. Όταν εξαντληθούν, ξεκινάει από την αρχή.

ΔΙΑΧΕΙΡΙΣΗ PROJECTS
--------------------
- File > New Project: Νέο project
- File > Save Project: Αποθήκευση στον φάκελο projects/
- File > Load Project: Φόρτωση με δυνατότητα αναζήτησης
- Προειδοποίηση για μη αποθηκευμένες αλλαγές

ΝΕΑ ΧΑΡΑΚΤΗΡΙΣΤΙΚΑ (Latest Updates)
------------------------------------
✅ Drag & Drop για media files
✅ Right-click context menu σε Project Name και Output Name
✅ Πολύ γρηγορότερο Preview (δείχνει μόνο μία εικόνα)
✅ Θυμάται το output folder που χρησιμοποιήσατε
✅ Bold text υποστηρίζει κενά (** κείμενο **)
✅ Bold text σε πολλές γραμμές
✅ Διόρθωση blurred background με auto position photos
✅ Απλοποιημένο Text Style (μόνο black box)
✅ Μεγαλύτερο text input για καλύτερη ορατότητα

ΠΡΟΤΑΣΕΙΣ ΒΕΛΤΙΩΣΗΣ
--------------------

1. ΕΡΓΟΝΟΜΙΑ & UI
   ○ Προσθήκη keyboard shortcuts (π.χ. Ctrl+P για Preview, Ctrl+E για Export)
   ○ Προσθήκη Recent Projects list για γρήγορη πρόσβαση
   ○ Undo/Redo functionality
   ○ Preview με zoom in/out για λεπτομέρειες
   ○ Bulk import φωτογραφιών από φάκελο
   ○ Reorder media files με drag & drop μέσα στη λίστα
   ○ Delete επιλεγμένων media files με Delete key

2. ΚΕΙΜΕΝΟ & TYPOGRAPHY
   ○ Live preview του κειμένου καθώς γράφετε
   ○ Περισσότερα text styles (italic, underline, colors)
   ○ Text animations (fade in/out, slide)
   ○ Πολλαπλά text overlays με διαφορετικές θέσεις
   ○ Emoji support
   ○ Templates για συνηθισμένες αγγελίες

3. MEDIA & ΕΦΦΕ
   ○ Transitions μεταξύ εικόνων (fade, slide, zoom)
   ○ Ken Burns effect (zoom & pan) για εικόνες
   ○ Image filters (brightness, contrast, saturation)
   ○ Batch processing για πολλά projects
   ○ Video trimming (αρχή/τέλος κάθε video)
   ○ Προσθήκη logo/watermark

4. ΜΟΥΣΙΚΗ & ΗΧΟΣ
   ○ Audio fade in/out στην αρχή/τέλος
   ○ Επιλογή συγκεκριμένου τραγουδιού αντί για αυτόματο
   ○ Music preview (ακούστε το τραγούδι πριν το export)
   ○ Crossfade μεταξύ τραγουδιών
   ○ Voiceover support

5. EXPORT & SHARING
   ○ Πολλαπλές αναλύσεις ταυτόχρονα (1080x1080 + 1920x1080)
   ○ Presets για social media (Instagram, Facebook, YouTube)
   ○ Compression settings για μικρότερο file size
   ○ Direct upload σε social media
   ○ GIF export για preview
   ○ Export ως image sequence

6. PERFORMANCE
   ○ Hardware acceleration (GPU encoding) για ταχύτερο export
   ○ Background export (συνεχίστε να εργάζεστε ενώ κάνει export)
   ○ Queue system για πολλαπλά exports
   ○ Cache system για γρηγορότερο re-export
   ○ Multi-threading optimization

7. ANALYTICS & TEMPLATES
   ○ Στατιστικά χρήσης (πόσα videos, ποια τραγούδια)
   ○ Templates βάσει τύπου ακινήτου (διαμέρισμα, μονοκατοικία, οικόπεδο)
   ○ Import από Excel/CSV για μαζική παραγωγή
   ○ Αποθήκευση favorite settings

8. ΕΚΠΑΙΔΕΥΣΗ & HELP
   ○ Built-in tutorial για νέους χρήστες
   ○ Tooltips στα buttons
   ○ Video tutorials
   ○ Παραδείγματα projects

ΠΡΟΤΕΙΝΟΜΕΝΕΣ ΠΡΟΣΘΗΚΕΣ (Υψηλής Προτεραιότητας)
------------------------------------------------
🔥 Recent Projects list (5 τελευταία projects)
🔥 Keyboard shortcuts (Ctrl+S save, Ctrl+P preview, Ctrl+E export)
🔥 Delete selected media με Delete key ή button
🔥 Reorder media files (drag & drop στη λίστα)
🔥 Transitions μεταξύ εικόνων (fade)
🔥 Ken Burns effect για εικόνες
🔥 Multiple export resolutions
🔥 Background export
🔥 Templates για τύπους ακινήτων

ΣΥΜΒΟΥΛΕΣ ΧΡΗΣΗΣ
-----------------
1. Κάντε πάντα Preview πριν το Export
2. Χρησιμοποιήστε 1080x1080 για Instagram/Facebook
3. Χρησιμοποιήστε 1920x1080 για YouTube/Website
4. Κρατήστε το κείμενο σύντομο και ευανάγνωστο
5. Χρησιμοποιήστε bold για σημαντικές πληροφορίες (τιμή, τηλέφωνο)
6. Προσθέστε πρώτα videos, μετά εικόνες (αυτόματη σειρά)
7. Αποθηκεύστε το project πριν το export
8. Δοκιμάστε διαφορετικά background modes για καλύτερο αποτέλεσμα

TROUBLESHOOTING
---------------
Πρόβλημα: Drag & drop δεν λειτουργεί
Λύση: Εγκαταστήστε: pip install tkinterdnd2 windnd

Πρόβλημα: Το κείμενο δεν γίνεται bold
Λύση: Χρησιμοποιήστε **κείμενο** (χωρίς κενά μεταξύ * και κειμένου)

Πρόβλημα: Το preview είναι άδειο
Λύση: Βεβαιωθείτε ότι έχετε προσθέσει media files

Πρόβλημα: Η μουσική δεν ακούγεται
Λύση: Ελέγξτε ότι τα .mp4 στο music/ έχουν audio track

Πρόβλημα: Το export παγώνει
Λύση: Περιμένετε - μεγάλα projects παίρνουν χρόνο. Δείτε την progress bar.

Πρόβλημα: Κείμενο δεν φαίνεται καθαρά
Λύση: Αυξήστε το font size στα Text Settings

Πρόβλημα: Blurred background δεν λειτουργεί
Λύση: Απενεργοποιήστε "Enable cropping" στα Video Settings

ΤΕΧΝΙΚΕΣ ΠΛΗΡΟΦΟΡΙΕΣ
---------------------
- Γλώσσα: Python 3.8+
- GUI Framework: Tkinter
- Video Processing: MoviePy + FFmpeg
- Image Processing: Pillow (PIL)
- Supported Codecs: H.264 (libx264)
- Audio Codec: AAC

ΔΟΜΗ ΦΑΚΕΛΩΝ
------------
slideshow_rita_aggelia/
├── slideshow_app.py        # Κύρια εφαρμογή
├── requirements.txt         # Dependencies
├── settings.json           # Ρυθμίσεις χρήστη
├── music_tracker.json      # Tracking μουσικής
├── music/                  # Φάκελος μουσικής (.mp4 files)
├── projects/               # Αποθηκευμένα projects (.json)
├── temp/                   # Προσωρινά αρχεία (auto-created)
└── README.txt             # Αυτό το αρχείο

ΕΠΙΚΟΙΝΩΝΙΑ & SUPPORT
---------------------
Για ερωτήσεις, προτάσεις ή bug reports:
- Ανοίξτε issue στο GitHub repository
- Email: [Προσθέστε το email σας]

VERSIONS
--------
v2.0 (Latest)
- Drag & drop support
- Faster preview (image only)
- Right-click context menus
- Multiline bold support
- Remember output folder
- Improved text input size
- Bug fixes

v1.0 (Initial)
- Basic slideshow creation
- Music tracking
- Project management
- Multiple video settings

================================================================================
                        Καλή δημιουργία! 🎬
================================================================================
