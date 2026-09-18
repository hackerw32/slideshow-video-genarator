"""Optional AI text improvement through an OpenAI-compatible API (DeepSeek).

The whole feature is inert until the user stores an API key in the settings,
so a machine without internet or without a key behaves exactly as before.
Only the stdlib is used for the network call - no extra dependency.
"""

import json
import threading
import urllib.error
import urllib.request

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODELS = ["deepseek-chat", "deepseek-reasoner"]

# The app renders **bold** out of the box, and every newline becomes its own
# line in the video, so the model is told to respect both.
SYSTEM_PROMPT = (
    "Είσαι επαγγελματίας copywriter. Παίρνεις ένα κείμενο και το ξαναγράφεις καλύτερα, "
    "χωρίς να αλλάξεις το νόημα, τα γεγονότα ή τα στοιχεία επικοινωνίας.\n"
    "Κανόνες:\n"
    "- Απάντησε ΜΟΝΟ με το βελτιωμένο κείμενο. Χωρίς σχόλια, χωρίς εισαγωγικά, χωρίς εξηγήσεις.\n"
    "- Κράτα την ίδια γλώσσα με το αρχικό κείμενο.\n"
    "- Κράτα τις αλλαγές γραμμής: κάθε γραμμή του αρχικού κειμένου εμφανίζεται σε ξεχωριστή "
    "γραμμή στο βίντεο.\n"
    "- Για έμφαση χρησιμοποίησε **έντονα** (διπλά αστεράκια). Μην χρησιμοποιείς άλλα σύμβολα "
    "markdown, ούτε emoji, hashtags ή συνδέσμους αν δεν σου ζητηθεί ρητά.\n"
    "- Μην προσθέτεις πληροφορίες που δεν υπάρχουν στο αρχικό κείμενο (τιμές, τηλέφωνα, "
    "διευθύνσεις, ονόματα)."
)

_HTTP_HINTS = {
    400: "Το αίτημα απορρίφθηκε από το AI",
    401: "Λάθος ή άκυρο API key — ξαναγράψε το στις ρυθμίσεις AI",
    402: "Το υπόλοιπο του λογαριασμού σου στο AI τελείωσε",
    403: "Το AI αρνήθηκε το αίτημα",
    404: "Το μοντέλο ή η διεύθυνση (base URL) δεν βρέθηκε — έλεγξε τις ρυθμίσεις AI",
    422: "Το AI δεν κατάλαβε το αίτημα",
    429: "Πολλά αιτήματα σε λίγο χρόνο — περίμενε λίγο και δοκίμασε ξανά",
    500: "Σφάλμα στον server του AI",
    502: "Ο server του AI δεν απάντησε σωστά",
    503: "Το AI είναι προσωρινά εκτός λειτουργίας",
}


class AITextMixin:
    """Settings, API client and helpers for the optional AI text improvement."""

    # ---------------------------------------------------------------- config
    def ai_configured(self):
        """True only when the feature is on AND a key is stored."""
        return (bool(self.settings.get("ai_enabled"))
                and bool((self.settings.get("ai_api_key") or "").strip()))

    def _ai_base_url(self, override=None):
        base = (override if override is not None else self.settings.get("ai_base_url")) or ""
        return (base.strip() or DEFAULT_BASE_URL).rstrip("/")

    def build_ai_system_prompt(self, project_instructions=""):
        """Global instructions always apply; project ones are added on top."""
        parts = [SYSTEM_PROMPT]
        g = (self.settings.get("ai_global_instructions") or "").strip()
        if g:
            parts.append("Μόνιμες οδηγίες του χρήστη (ισχύουν πάντα):\n" + g)
        p = (project_instructions or "").strip()
        if p:
            parts.append("Οδηγίες μόνο για αυτό το project:\n" + p)
        return "\n\n".join(parts)

    # ------------------------------------------------------------- API calls
    def _ai_call(self, path, payload=None, timeout=120, key=None, base_url=None):
        """One JSON call to the configured OpenAI-compatible endpoint.

        Always called from a worker thread; failures raise RuntimeError with a
        ready-to-show Greek message.
        """
        token = (key if key is not None else self.settings.get("ai_api_key") or "").strip()
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self._ai_base_url(base_url) + path, data=data,
                                     method="POST" if data is not None else "GET")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(self._ai_http_error(e))
        except urllib.error.URLError as e:
            raise RuntimeError(f"Δεν μπόρεσα να συνδεθώ με το AI ({e.reason}). "
                               "Έλεγξε τη σύνδεση στο internet.")
        except (TimeoutError, OSError) as e:
            raise RuntimeError(f"Το AI άργησε να απαντήσει ({e}). Δοκίμασε ξανά.")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Το AI έστειλε μη αναμενόμενη απάντηση ({e}).")

    @staticmethod
    def _ai_http_error(e):
        try:
            body = json.loads(e.read().decode("utf-8", errors="replace"))
            detail = (body.get("error") or {}).get("message") or ""
        except Exception:
            detail = ""
        hint = _HTTP_HINTS.get(e.code, f"Σφάλμα AI ({e.code})")
        return f"{hint}." + (f"\n\n{detail}" if detail else "")

    # ---------------------------------------------------------- improvement
    def improve_text_with_ai(self, text, project_instructions, apply_result, set_busy=None):
        """Rewrite ``text`` with the AI and hand the result to ``apply_result``.

        The network call runs on a daemon thread; ``apply_result(new_text)``
        and ``set_busy(False)`` always come back on the Tk main thread.
        """
        text = (text or "").strip()
        if not text:
            messagebox.showinfo("AI", "Γράψε πρώτα ένα κείμενο και μετά πάτα Βελτίωση με AI.")
            return
        if not self.ai_configured():
            if messagebox.askyesno(
                    "AI",
                    "Η βελτίωση κειμένου με AI δεν είναι ρυθμισμένη.\n\n"
                    "Θέλεις να ανοίξεις τις ρυθμίσεις AI τώρα;"):
                self.show_ai_settings()
            return
        if set_busy:
            set_busy(True)
        threading.Thread(target=self._ai_improve_worker,
                         args=(text, project_instructions, apply_result, set_busy),
                         daemon=True).start()

    def _ai_improve_worker(self, text, project_instructions, apply_result, set_busy):
        model = (self.settings.get("ai_model") or "").strip() or DEEPSEEK_MODELS[0]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.build_ai_system_prompt(project_instructions)},
                {"role": "user", "content": text},
            ],
            "stream": False,
        }
        try:
            data = self._ai_call("/chat/completions", payload)
            choices = data.get("choices") or []
            out = (choices[0].get("message", {}).get("content") if choices else "") or ""
            out = out.strip()
            if not out:
                raise RuntimeError("Το AI δεν επέστρεψε κείμενο. Δοκίμασε ξανά.")
        except Exception as e:
            err = str(e)   # bound before the lambda: `e` is cleared at block end
            self.root.after(0, lambda: self._ai_done(None, set_busy, apply_result, err))
            return
        self.root.after(0, lambda: self._ai_done(out, set_busy, apply_result, None))

    def _ai_done(self, result, set_busy, apply_result, error):
        """Back on the Tk main thread: restore the UI, then show or apply."""
        if set_busy:
            set_busy(False)
        if error:
            messagebox.showerror("AI", error)
            return
        apply_result(result)

    # ------------------------------------------------------------ test/test
    def ai_test_connection(self, key, base_url, set_status, set_busy=None):
        """Check the key against the endpoint's /models route on a worker thread."""
        if not (key or "").strip():
            set_status("Γράψε πρώτα το API key.", "#c0392b")
            return
        if set_busy:
            set_busy(True)
        threading.Thread(target=self._ai_test_worker,
                         args=(key, base_url, set_status, set_busy), daemon=True).start()

    def _ai_test_worker(self, key, base_url, set_status, set_busy):
        try:
            data = self._ai_call("/models", timeout=30, key=key, base_url=base_url)
            ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict)]
            ids = [i for i in ids if i]
            msg = "Το κλειδί δουλεύει." + (f"  Μοντέλα: {', '.join(ids[:6])}" if ids else "")
            color = "#1e7a34"
        except Exception as e:
            msg, color = str(e), "#c0392b"
        self.root.after(0, lambda: self._ai_test_done(msg, color, set_status, set_busy))

    def _ai_test_done(self, msg, color, set_status, set_busy):
        if set_busy:
            set_busy(False)
        set_status(msg, color)

    # ---------------------------------------------------------- settings UI
    def show_ai_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("AI / DeepSeek — Βελτίωση κειμένου")
        dlg.geometry("680x740")
        dlg.minsize(560, 460)
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()

        body, bottom = self._scrollable(dlg, 650)

        ttk.Label(body, text="Βελτίωση κειμένου με AI", font=("Calibri", 11, "bold")).pack(
            padx=20, pady=(14, 2), anchor='w')
        ttk.Label(body, foreground="#555", wraplength=610, justify='left',
                  text="Το κείμενο που βελτιώνεις στέλνεται στους server του DeepSeek. "
                       "Το κλειδί αποθηκεύεται σε απλό κείμενο στο settings.json — μην το μοιραστείς."
                  ).pack(padx=20, anchor='w', pady=(0, 8))

        enabled_var = tk.BooleanVar(value=bool(self.settings.get("ai_enabled")))
        ttk.Checkbutton(body, text="Ενεργό — εμφάνιση κουμπιών «Βελτίωση με AI»",
                        variable=enabled_var).pack(padx=20, anchor='w')

        key_var = tk.StringVar(value=self.settings.get("ai_api_key", ""))
        kf = ttk.Frame(body)
        kf.pack(fill='x', padx=20, pady=(10, 2))
        ttk.Label(kf, text="API key:", width=14).pack(side='left')
        key_entry = ttk.Entry(kf, textvariable=key_var, show='•')
        key_entry.pack(side='left', fill='x', expand=True)

        def toggle_key():
            key_entry.config(show='' if key_entry.cget('show') else '•')
        ttk.Button(kf, text="👁", width=3, command=toggle_key).pack(side='left', padx=(4, 0))

        mf = ttk.Frame(body)
        mf.pack(fill='x', padx=20, pady=4)
        ttk.Label(mf, text="Μοντέλο:", width=14).pack(side='left')
        model_var = tk.StringVar(value=self.settings.get("ai_model", DEEPSEEK_MODELS[0]))
        ttk.Combobox(mf, textvariable=model_var, values=DEEPSEEK_MODELS,
                     width=26).pack(side='left')
        ttk.Label(mf, text="  deepseek-chat = γρήγορο, reasoner = καλύτερο κείμενο",
                  foreground="#777").pack(side='left')

        bf = ttk.Frame(body)
        bf.pack(fill='x', padx=20, pady=4)
        ttk.Label(bf, text="Base URL:", width=14).pack(side='left')
        base_var = tk.StringVar(value=self.settings.get("ai_base_url", DEFAULT_BASE_URL))
        ttk.Entry(bf, textvariable=base_var).pack(side='left', fill='x', expand=True)
        ttk.Label(body, foreground="#777", text="Άφησέ το όπως είναι για DeepSeek. "
                                                "Δουλεύει και με άλλα OpenAI-compatible API.",
                  ).pack(padx=20, anchor='w')

        ttk.Separator(body).pack(fill='x', padx=20, pady=(12, 6))
        ttk.Label(body, text="Παγκόσμιες οδηγίες (ισχύουν σε όλα τα projects)",
                  font=("Calibri", 10, "bold")).pack(padx=20, anchor='w')
        glob = scrolledtext.ScrolledText(body, height=8, wrap=tk.WORD, undo=True)
        glob.pack(fill='x', expand=True, padx=20, pady=(4, 2))
        glob.insert("1.0", self.settings.get("ai_global_instructions", ""))
        glob.edit_reset()

        ttk.Label(body, foreground="#777", wraplength=610, justify='left',
                  text='Παράδειγμα: «Γράψε ζεστά και σύντομα, σε πρώτο πληθυντικό. Ξεκίνα με ένα '
                       'δυνατό **έντονο** σημείο. Μέγιστο 4 γραμμές, χωρίς emoji.»'
                  ).pack(padx=20, anchor='w', pady=(0, 6))

        status_lbl = ttk.Label(body, text="", wraplength=610, justify='left')
        status_lbl.pack(padx=20, anchor='w')

        def set_status(text, color="#333"):
            status_lbl.config(text=text, foreground=color)

        btns = ttk.Frame(bottom)
        btns.pack(fill='x')

        def do_test():
            set_status("Έλεγχος...", "#333")
            self.ai_test_connection(key_var.get(), base_var.get(), set_status,
                                    set_busy=lambda b: test_btn.config(state='disabled' if b else 'normal'))
        test_btn = ttk.Button(btns, text="Δοκιμή σύνδεσης", command=do_test)
        test_btn.pack(side='left')

        def save():
            self.settings.update({
                "ai_enabled": bool(enabled_var.get()),
                "ai_api_key": key_var.get().strip(),
                "ai_model": model_var.get().strip() or DEEPSEEK_MODELS[0],
                "ai_base_url": base_var.get().strip() or DEFAULT_BASE_URL,
                "ai_global_instructions": glob.get("1.0", tk.END).strip(),
            })
            self.save_settings()
            dlg.destroy()

        ttk.Button(btns, text="Άκυρο", command=dlg.destroy).pack(side='right', padx=4)
        ttk.Button(btns, text="Αποθήκευση", command=save).pack(side='right')
