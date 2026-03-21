# Slideshow Video Creator

Εφαρμογή δημιουργίας slideshow videos με μουσική για αγγελίες.

## Εγκατάσταση

1. Εγκατάσταση Python 3.8+ (αν δεν το έχεις ήδη)

2. Εγκατάσταση dependencies:
```bash
pip install -r requirements.txt
```

## Χρήση

1. Εκτέλεση της εφαρμογής:
```bash
python slideshow_app.py
```

2. **Προσθήκη Media:**
   - Κλικ στα κουμπιά "Add Videos" και "Add Images"
   - Τα videos εμφανίζονται πρώτα, μετά οι εικόνες

3. **Κείμενο:**
   - Γράψε το κείμενο της αγγελίας στο text field
   - Χρησιμοποίησε `**κείμενο**` για bold

4. **Ρυθμίσεις:**
   - **Settings > Audio Settings:** Ρύθμιση έντασης ήχου (dB)
   - **Settings > Video Settings:** Επιλογή ανάλυσης (1080x1080 ή 1920x1080), background mode, cropping
   - **Settings > Text Settings:** Μέγεθος και γραμματοσειρά κειμένου

5. **Preview:**
   - Κλικ "Generate Preview" για να δεις το αποτέλεσμα
   - Χρησιμοποίησε το slider για navigation

6. **Export:**
   - Διάλεξε output folder και όνομα αρχείου
   - Κλικ "Export Video"

## Features

✅ Αυτόματο tracking μουσικής (δεν επαναλαμβάνει τραγούδια)
✅ Refresh music list για νέα τραγούδια
✅ Fit χωρίς cropping με επιλογές background (άσπρο, μαύρο, blurred)
✅ Preview με slider
✅ Save/Load projects με αναζήτηση
✅ Αυτόματο chaining μουσικής (αν δεν φτάνει ένα τραγούδι)
✅ Volume control με memory (dB)
✅ Markdown bold support (**text**)
✅ Warning για unsaved changes

## Μουσική

- Τα τραγούδια πρέπει να είναι στον φάκελο `music/`
- Υποστηριζόμενη μορφή: .mp4 (audio)
- Χρησιμοποίησε **Music > Refresh Music List** μετά από προσθήκη νέων τραγουδιών
- Χρησιμοποίησε **Music > Reset Used Music** για να ξεκινήσεις από την αρχή

## Shortcuts

- File > New Project: Νέο project
- File > Load Project: Φόρτωση project με αναζήτηση
- File > Save Project: Αποθήκευση project

## Προτάσεις

1. Δοκίμασε πρώτα με λίγα media files για να δεις το αποτέλεσμα
2. Χρησιμοποίησε το preview πριν το export (πιο γρήγορο)
3. Κάνε save το project πριν το export
4. Για μεγάλα projects, το export μπορεί να πάρει χρόνο - περίμενε υπομονετικά

## Troubleshooting

**Πρόβλημα:** Το preview δεν δουλεύει
**Λύση:** Βεβαιώσου ότι τα media files υπάρχουν και είναι έγκυρα

**Πρόβλημα:** Η μουσική δεν παίζει
**Λύση:** Έλεγξε ότι τα mp4 files στον φάκελο music έχουν audio track

**Πρόβλημα:** Το κείμενο δεν φαίνεται
**Λύση:** Δοκίμασε μεγαλύτερο font size στα Text Settings
