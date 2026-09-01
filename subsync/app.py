"""Minimale Tkinter-GUI: Ordner (Drag & Drop), Sprachen, Start, Fortschritt, Ergebnis, Einstellungen."""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import config, contextmenu, core

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:  # ohne Drag & Drop trotzdem lauffähig
    DND_FILES, _Root = None, tk.Tk

GREEN, RED, GREY = "#2e8b57", "#c0392b", "#777"


class App(_Root):
    def __init__(self, folder: str | None = None, langs: list[str] | None = None):
        super().__init__()
        self.title("subsync — Find & Sync Subtitles")
        self.geometry("620x520")
        self.minsize(520, 420)
        self.cfg = config.load()
        if langs:
            for l in langs:
                if l not in self.cfg["known_languages"]:
                    self.cfg["known_languages"].append(l)
            self.cfg["languages"] = langs
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._build()
        if folder:
            self.folder_var.set(folder)
            self.after(200, self.start)

    # ---- Aufbau -------------------------------------------------------------
    def _build(self):
        pad = {"padx": 10, "pady": 4}
        top = ttk.Frame(self); top.pack(fill="x", **pad)
        ttk.Label(top, text="Ordner:").pack(side="left")
        self.folder_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="…", width=3, command=self.browse).pack(side="left")

        self.drop = tk.Label(self, text="Ordner hierher ziehen", relief="groove", fg=GREY,
                             height=2, cursor="hand2")
        self.drop.pack(fill="x", padx=10, pady=(0, 6))
        self.drop.bind("<Button-1>", lambda e: self.browse())
        if DND_FILES:
            for w in (self, self.drop):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)

        row = ttk.Frame(self); row.pack(fill="x", **pad)
        ttk.Label(row, text="Sprachen:").pack(side="left")
        self.lang_vars: dict[str, tk.BooleanVar] = {}
        self.lang_frame = ttk.Frame(row); self.lang_frame.pack(side="left", padx=6)
        self._build_langs()
        ttk.Button(row, text="Einstellungen…", command=self.settings).pack(side="right")
        self.start_btn = ttk.Button(row, text="Start", command=self.start, width=12)
        self.start_btn.pack(side="right", padx=6)

        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", padx=10, pady=(8, 2))
        self.status = ttk.Label(self, text="Bereit.", foreground=GREY)
        self.status.pack(fill="x", padx=10)

        self.result = tk.Label(self, text="", font=("Segoe UI", 14, "bold"))
        self.result.pack(fill="x", padx=10, pady=4)

        self.log = tk.Text(self, height=10, state="disabled", font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_langs(self):
        for w in self.lang_frame.winfo_children():
            w.destroy()
        self.lang_vars = {}
        for l in self.cfg["known_languages"]:
            var = tk.BooleanVar(value=l in self.cfg["languages"])
            self.lang_vars[l] = var
            ttk.Checkbutton(self.lang_frame, text=l, variable=var).pack(side="left", padx=2)

    # ---- Aktionen -----------------------------------------------------------
    def browse(self):
        d = filedialog.askdirectory(title="Ordner mit Videos wählen")
        if d:
            self.folder_var.set(d.replace("/", "\\"))

    def on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if paths:
            p = paths[0]
            import os
            self.folder_var.set(p if os.path.isdir(p) else os.path.dirname(p))

    def start(self):
        if self.worker and self.worker.is_alive():
            self.cancel.set(); self.status.config(text="Abbruch nach aktueller Episode…"); return
        folder = self.folder_var.get().strip().strip('"')
        langs = [l for l, v in self.lang_vars.items() if v.get()]
        import os
        if not os.path.isdir(folder):
            messagebox.showwarning("subsync", "Bitte einen existierenden Ordner angeben."); return
        if not langs:
            messagebox.showwarning("subsync", "Bitte mindestens eine Sprache wählen."); return
        self.cfg["languages"] = langs; config.save(self.cfg)
        self.cancel.clear(); self.result.config(text="")
        self._log_clear(); self.bar.config(mode="indeterminate"); self.bar.start(12)
        self.start_btn.config(text="Abbrechen")
        self.worker = threading.Thread(target=self._work, args=(folder, langs), daemon=True)
        self.worker.start()
        self.after(100, self._poll)

    def _work(self, folder, langs):
        res = core.run(folder, langs, self.cfg,
                       progress=lambda m, i, n: self.q.put(("progress", m, i, n)),
                       log=lambda s: self.q.put(("log", s)), cancel=self.cancel)
        self.q.put(("done", res))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "log":
                    self._log(item[1])
                elif item[0] == "progress":
                    _, m, i, n = item
                    if n:
                        self.bar.stop(); self.bar.config(mode="determinate", maximum=n, value=i - 1)
                        self.status.config(text=f"[{i}/{n}] {m}")
                    else:
                        self.status.config(text=m)
                elif item[0] == "done":
                    self._finish(item[1]); return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, res: core.Result):
        self.bar.stop(); self.bar.config(mode="determinate", value=self.bar["maximum"])
        self.start_btn.config(text="Start")
        if res.error:
            self.result.config(text=f"✖  {res.error}", fg=RED); self.status.config(text="Fehler."); return
        if not res.synced and not res.unsynced and not res.missing and not res.cancelled:
            self.result.config(text=f"✔  Alle {res.skipped} Videos haben bereits Untertitel.", fg=GREEN)
            self.status.config(text="Fertig."); return
        parts = [f"{len(res.synced)} gesynct"]
        if res.skipped: parts.append(f"{res.skipped} vorhanden")
        if res.unsynced: parts.append(f"{len(res.unsynced)} unsynct")
        if res.missing: parts.append(f"{len(res.missing)} nicht gefunden")
        ok = not res.missing and not res.unsynced and not res.cancelled
        self.result.config(text=("✔  " if ok else "⚠  ") + ("Abgebrochen — " if res.cancelled else "Fertig — ") + ", ".join(parts),
                           fg=GREEN if ok else "#b8860b")
        self.status.config(text="Fertig.")
        if res.missing:
            self._log("\nKein Untertitel gefunden (Dateiname braucht Serienname + SxxExx bzw. Titel + Jahr):")
            for m in res.missing: self._log("  " + m)

    # ---- Einstellungen ------------------------------------------------------
    def settings(self):
        win = tk.Toplevel(self); win.title("Einstellungen"); win.resizable(False, False); win.grab_set()
        f = ttk.Frame(win, padding=12); f.pack()
        ttk.Label(f, text="OpenSubtitles.com Benutzername:").grid(row=0, column=0, sticky="w", pady=3)
        user = tk.StringVar(value=self.cfg["opensubtitles_user"])
        ttk.Entry(f, textvariable=user, width=32).grid(row=0, column=1, pady=3)
        ttk.Label(f, text="OpenSubtitles.com Passwort:").grid(row=1, column=0, sticky="w", pady=3)
        pw = tk.StringVar(value=config.decrypt(self.cfg["opensubtitles_password"]))
        ttk.Entry(f, textvariable=pw, width=32, show="•").grid(row=1, column=1, pady=3)
        ttk.Label(f, text="Sprachen zur Auswahl (Kürzel, Komma):").grid(row=2, column=0, sticky="w", pady=3)
        known = tk.StringVar(value=", ".join(self.cfg["known_languages"]))
        ttk.Entry(f, textvariable=known, width=32).grid(row=2, column=1, pady=3)
        ctx = tk.BooleanVar(value=contextmenu.is_installed())
        ttk.Checkbutton(f, text="Explorer-Kontextmenü „Find & Sync Subtitles“ auf Ordnern", variable=ctx)\
            .grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 3))
        ttk.Label(f, text="Passwort wird verschlüsselt gespeichert (Windows DPAPI, nur dieser Benutzer).",
                  foreground=GREY).grid(row=4, column=0, columnspan=2, sticky="w")

        def ok():
            self.cfg["opensubtitles_user"] = user.get().strip()
            self.cfg["opensubtitles_password"] = config.encrypt(pw.get())
            self.cfg["known_languages"] = [x.strip().lower() for x in known.get().split(",") if x.strip()] or ["ru"]
            config.save(self.cfg)
            try:
                (contextmenu.install if ctx.get() else contextmenu.uninstall)()
            except OSError as e:
                messagebox.showerror("subsync", f"Kontextmenü: {e}")
            self._build_langs(); win.destroy()
        b = ttk.Frame(f); b.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(b, text="Speichern", command=ok).pack(side="left", padx=4)
        ttk.Button(b, text="Abbrechen", command=win.destroy).pack(side="left", padx=4)

    # ---- Log ----------------------------------------------------------------
    def _log(self, s: str):
        self.log.config(state="normal"); self.log.insert("end", s + "\n"); self.log.see("end"); self.log.config(state="disabled")

    def _log_clear(self):
        self.log.config(state="normal"); self.log.delete("1.0", "end"); self.log.config(state="disabled")


def main():
    """subsync.exe [Ordner] [--lang ru,de]  — mit Ordner wird sofort gestartet."""
    args = sys.argv[1:]
    langs = None
    if "--lang" in args:
        i = args.index("--lang")
        langs = [x.strip().lower() for x in args[i + 1].split(",") if x.strip()] if i + 1 < len(args) else None
        del args[i:i + 2]
    folder = args[0] if args else None
    app = App(folder, langs)
    app.mainloop()
