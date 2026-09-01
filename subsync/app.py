"""Minimale Tkinter-GUI: Ordner (Drag & Drop), Untertitel-Sprachen, Start, Fortschritt, Ergebnis, Einstellungen.
GUI-Sprache umschaltbar (de/ru/en) — siehe i18n.py."""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import config, core, i18n

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:  # ohne Drag & Drop trotzdem lauffähig
    DND_FILES, _Root = None, tk.Tk

TEAL, TEAL_DARK, TEAL_BG, TEAL_MID = "#14b8a6", "#0f766e", "#e4f5f2", "#99d9d0"
GREEN, RED, AMBER, GREY = "#2e8b57", "#c0392b", "#b8860b", "#666"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
OPENSUBTITLES_URL = "https://www.opensubtitles.com"


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


class CanvasBar(tk.Canvas):
    """Fortschrittsbalken mit Prozentangabe in der Mitte; Indeterminate-Puls fürs Suchen/Laden."""

    def __init__(self, master, height=22):
        super().__init__(master, height=height, highlightthickness=1,
                         highlightbackground=TEAL_MID, bg="white")
        self._fraction = 0.0
        self._text = ""
        self._pulse_pos = None
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, fraction: float, text: str = ""):
        self._pulse_pos = None
        self._fraction = max(0.03, min(1.0, fraction))   # nie ganz leer — man sieht sofort, dass etwas läuft
        self._text = text
        self._draw()

    def reset(self):
        self._pulse_pos = None
        self._fraction, self._text = 0.0, ""
        self._draw()

    def pulse(self):
        self._pulse_pos = 0.0 if self._pulse_pos is None else (self._pulse_pos + 0.02) % 1.0
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2:
            return
        if self._pulse_pos is not None:
            bw = int(w * 0.25)
            x = int((w + bw) * self._pulse_pos) - bw
            self.create_rectangle(max(0, x), 0, min(w, x + bw), h, fill=TEAL, width=0)
        elif self._fraction > 0:
            self.create_rectangle(0, 0, int(w * self._fraction), h, fill=TEAL, width=0)
            if self._text:
                self.create_text(w // 2, h // 2, text=self._text, fill="white" if self._fraction > 0.55 else TEAL_DARK,
                                 font=("Segoe UI", 9, "bold"))


class App(_Root):
    def __init__(self, folder: str | None = None, langs: list[str] | None = None):
        super().__init__()
        self.geometry("640x560")
        self.minsize(560, 470)
        try:
            self.iconbitmap(default=str(asset("icon.ico")))
        except tk.TclError:
            pass
        self.cfg = config.load()
        if langs:
            for l in langs:
                if l not in self.cfg["known_languages"]:
                    self.cfg["known_languages"].append(l)
            self.cfg["languages"] = langs
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._spin = 0
        self._pending_folder = folder or ""
        self._style()
        self._build()
        if folder:
            self.after(200, self.start)

    @property
    def ui(self) -> str:
        return self.cfg.get("ui_language", "de")

    def t(self, key: str, **kw) -> str:
        return i18n.tr(self.ui, key, **kw)

    # ---- Stil (Teal wie vl-minisync) ----------------------------------------
    def _style(self):
        self.configure(bg=TEAL_BG)
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=TEAL_BG, foreground="#1b3a36", font=("Segoe UI", 10))
        s.configure("TFrame", background=TEAL_BG)
        s.configure("TLabel", background=TEAL_BG)
        s.configure("TButton", background="white", foreground=TEAL_DARK, bordercolor=TEAL_MID,
                    focuscolor=TEAL_BG, padding=(10, 4))
        s.map("TButton", background=[("active", "#f0faf8"), ("pressed", TEAL_MID)])
        s.configure("Accent.TButton", background=TEAL, foreground="white", bordercolor=TEAL_DARK,
                    font=("Segoe UI", 10, "bold"))
        s.map("Accent.TButton", background=[("active", TEAL_DARK), ("pressed", TEAL_DARK)])
        s.configure("TMenubutton", background="white", foreground="#1b3a36", bordercolor=TEAL_MID,
                    arrowcolor=TEAL_DARK, padding=(10, 4))
        s.configure("TEntry", fieldbackground="white", bordercolor=TEAL_MID)
        s.configure("TCombobox", fieldbackground="white", bordercolor=TEAL_MID, arrowcolor=TEAL_DARK)
        s.configure("Vertical.TScrollbar", background=TEAL_MID, troughcolor=TEAL_BG, bordercolor=TEAL_BG,
                    arrowcolor=TEAL_DARK)

    # ---- Aufbau -------------------------------------------------------------
    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.title("subsync — Find & Sync Subtitles")

        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(top, text=self.t("folder")).pack(side="left")
        self.folder_var = tk.StringVar(value=getattr(self, "folder_var", None) and self.folder_var.get() or self._pending_folder)
        ttk.Entry(top, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="…", width=3, command=self.browse).pack(side="left", padx=(0, 8))
        self.ui_box = ttk.Combobox(top, state="readonly", width=9,
                                   values=list(i18n.UI_LANGS.values()))
        self.ui_box.set(i18n.UI_LANGS.get(self.ui, "Deutsch"))
        self.ui_box.bind("<<ComboboxSelected>>", self._switch_ui)
        self.ui_box.pack(side="right")

        self.drop = tk.Canvas(self, height=92, bg="white", highlightthickness=0, cursor="hand2")
        self.drop.pack(fill="x", padx=10, pady=(2, 6))
        self.drop.bind("<Configure>", self._draw_drop)
        self.drop.bind("<Button-1>", lambda e: self.browse())
        if DND_FILES:
            for w in (self, self.drop):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)

        row = ttk.Frame(self); row.pack(fill="x", padx=10, pady=4)
        ttk.Label(row, text=self.t("subtitles")).pack(side="left")
        self.lang_sel: dict[str, tk.BooleanVar] = {}
        self.lang_btn = ttk.Menubutton(row, direction="below")
        self.lang_btn.pack(side="left", padx=6)
        self._build_lang_menu()
        ttk.Button(row, text=self.t("settings"), command=self.settings).pack(side="right")
        self.start_btn = ttk.Button(row, text=self.t("start"), command=self.start, width=12, style="Accent.TButton")
        self.start_btn.pack(side="right", padx=6)

        self.bar = CanvasBar(self)
        self.bar.pack(fill="x", padx=10, pady=(8, 2))
        srow = ttk.Frame(self); srow.pack(fill="x", padx=10)
        self.spinner = tk.Label(srow, text="", font=("Segoe UI", 12), fg=TEAL_DARK, width=2, bg=TEAL_BG)
        self.spinner.pack(side="left")
        self.status = ttk.Label(srow, text=self.t("ready"), foreground=GREY)
        self.status.pack(side="left", fill="x")

        self.result = tk.Label(self, text="", font=("Segoe UI", 14, "bold"), bg=TEAL_BG)
        self.result.pack(fill="x", padx=10, pady=4)

        logf = ttk.Frame(self)
        logf.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(logf, height=10, state="disabled", font=("Consolas", 9), wrap="word",
                           relief="flat", highlightthickness=1, highlightbackground=TEAL_MID, bg="white")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    def _draw_drop(self, _event=None):
        c = self.drop
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        c.create_rectangle(5, 5, w - 5, h - 5, dash=(7, 4), outline=TEAL, width=2)
        c.create_text(w // 2, h // 2 - 16, text="⬇", font=("Segoe UI", 20, "bold"), fill=TEAL_DARK)
        c.create_text(w // 2, h // 2 + 14, text=self.t("drop_main"), font=("Segoe UI", 11, "bold"), fill=TEAL_DARK)
        c.create_text(w // 2, h // 2 + 33, text=self.t("drop_sub"), font=("Segoe UI", 9), fill=GREY)

    def _build_lang_menu(self):
        menu = tk.Menu(self.lang_btn, tearoff=0)
        prev = {c: v.get() for c, v in self.lang_sel.items()}
        self.lang_sel = {}
        for code in self.cfg["known_languages"]:
            var = tk.BooleanVar(value=prev.get(code, code in self.cfg["languages"]))
            self.lang_sel[code] = var
            menu.add_checkbutton(label=i18n.lang_name(self.ui, code), variable=var,
                                 command=self._update_lang_btn)
        self.lang_btn.configure(menu=menu)
        self._update_lang_btn()

    def _update_lang_btn(self):
        sel = [i18n.lang_name(self.ui, c) for c, v in self.lang_sel.items() if v.get()]
        self.lang_btn.configure(text=", ".join(sel) if sel else "—")

    def _switch_ui(self, _event=None):
        name = self.ui_box.get()
        code = next((c for c, n in i18n.UI_LANGS.items() if n == name), "de")
        self.cfg["ui_language"] = code
        config.save(self.cfg)
        self._build()

    # ---- Aktionen -----------------------------------------------------------
    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.folder_var.set(d.replace("/", "\\"))

    def on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if paths:
            p = paths[0]
            self.folder_var.set(p if os.path.isdir(p) else os.path.dirname(p))

    def start(self):
        if self.worker and self.worker.is_alive():
            self.cancel.set(); self.status.config(text=self.t("cancelling")); return
        folder = self.folder_var.get().strip().strip('"')
        langs = [c for c, v in self.lang_sel.items() if v.get()]
        if not os.path.isdir(folder):
            messagebox.showwarning("subsync", self.t("warn_folder")); return
        if not langs:
            messagebox.showwarning("subsync", self.t("warn_lang")); return
        self.cfg["languages"] = langs; config.save(self.cfg)
        self.cancel.clear(); self.result.config(text="")
        self._log_clear()
        self.start_btn.config(text=self.t("cancel_run"))
        self.worker = threading.Thread(target=self._work, args=(folder, langs), daemon=True)
        self.worker.start()
        self.after(100, self._poll)
        self.after(90, self._animate)

    def _work(self, folder, langs):
        ui = self.ui
        res = core.run(folder, langs, self.cfg,
                       progress=lambda m, i, n: self.q.put(("progress", m, i, n)),
                       log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                       tr=lambda key, **kw: i18n.tr(ui, key, **kw))
        self.q.put(("done", res))

    def _animate(self):
        if not (self.worker and self.worker.is_alive()):
            self.spinner.config(text="")
            return
        self._spin = (self._spin + 1) % len(SPINNER)
        self.spinner.config(text=SPINNER[self._spin])
        if self.bar._pulse_pos is not None:
            self.bar.pulse()
        self.after(90, self._animate)

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "log":
                    self._log(item[1])
                elif item[0] == "progress":
                    _, m, i, n = item
                    if n:
                        frac = (i - 1 + 0.4) / n
                        self.bar.set(frac, f"{int(frac * 100)} %")
                        self.status.config(text=f"[{i}/{n}] {m}")
                    else:
                        self.bar.pulse()
                        self.status.config(text=m)
                elif item[0] == "done":
                    self._finish(item[1]); return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, res: core.Result):
        self.start_btn.config(text=self.t("start"))
        self.spinner.config(text="")
        if res.error:
            self.bar.reset()
            self.result.config(text=f"✖  {res.error}", fg=RED); self.status.config(text=self.t("error")); return
        self.bar.set(1.0, "100 %")
        self.status.config(text=self.t("done"))
        if not res.synced and not res.unsynced and not res.missing and not res.noaccess and not res.cancelled:
            self.result.config(text=self.t("res_all_have", n=res.skipped), fg=GREEN)
            return
        parts = [self.t("p_synced", n=len(res.synced))]
        if res.skipped: parts.append(self.t("p_existing", n=res.skipped))
        if res.unsynced: parts.append(self.t("p_unsynced", n=len(res.unsynced)))
        if res.missing: parts.append(self.t("p_missing", n=len(res.missing)))
        if res.noaccess: parts.append(self.t("p_noaccess", n=len(res.noaccess)))
        ok = not res.missing and not res.unsynced and not res.noaccess and not res.cancelled
        head = self.t("res_cancelled") if res.cancelled else self.t("res_done")
        self.result.config(text=("✔  " if ok else "⚠  ") + head + ", ".join(parts), fg=GREEN if ok else AMBER)
        if res.missing:
            self._log(self.t("missing_hint"))
            for m in res.missing: self._log("  " + m)
        if res.noaccess:
            self._log(self.t("noaccess_hint"))
            for d in res.noaccess: self._log("  " + d)

    # ---- Einstellungen ------------------------------------------------------
    def settings(self):
        win = tk.Toplevel(self); win.title(self.t("st_title")); win.resizable(False, False); win.grab_set()
        win.configure(bg=TEAL_BG)
        try:
            win.iconbitmap(str(asset("icon.ico")))
        except tk.TclError:
            pass
        f = ttk.Frame(win, padding=12); f.pack()
        ttk.Label(f, text=self.t("st_user")).grid(row=0, column=0, sticky="w", pady=3)
        user = tk.StringVar(value=self.cfg["opensubtitles_user"])
        ttk.Entry(f, textvariable=user, width=32).grid(row=0, column=1, sticky="w", pady=3)
        hb = tk.Label(f, text="?", font=("Segoe UI", 10, "bold"), fg="white", bg=TEAL, width=2, cursor="hand2")
        hb.grid(row=0, column=2, padx=(6, 0))
        hb.bind("<Button-1>", lambda e: webbrowser.open(OPENSUBTITLES_URL))
        ttk.Label(f, text=self.t("st_pw")).grid(row=1, column=0, sticky="w", pady=3)
        pw = tk.StringVar(value=config.decrypt(self.cfg["opensubtitles_password"]))
        ttk.Entry(f, textvariable=pw, width=32, show="•").grid(row=1, column=1, sticky="w", pady=3)
        help_lbl = tk.Label(f, text=self.t("st_help", limit=i18n.OPENSUBTITLES_LIMIT), justify="left",
                            fg=TEAL_DARK, bg=TEAL_BG, cursor="hand2", font=("Segoe UI", 9))
        help_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 8))
        help_lbl.bind("<Button-1>", lambda e: webbrowser.open(OPENSUBTITLES_URL))
        ttk.Label(f, text=self.t("st_langs")).grid(row=3, column=0, sticky="w", pady=3)
        known = tk.StringVar(value=", ".join(self.cfg["known_languages"]))
        ttk.Entry(f, textvariable=known, width=32).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(f, text=self.t("st_pw_note"), foreground=GREY).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        def ok():
            from babelfish import Language
            codes = [x.strip().lower() for x in known.get().split(",") if x.strip()]
            bad = []
            for c in codes:
                try:
                    Language.fromietf(c)
                except Exception:  # noqa: BLE001
                    bad.append(c)
            if bad:
                messagebox.showwarning("subsync", self.t("st_invalid", codes=", ".join(bad)), parent=win)
                return
            self.cfg["opensubtitles_user"] = user.get().strip()
            self.cfg["opensubtitles_password"] = config.encrypt(pw.get())
            self.cfg["known_languages"] = codes or ["ru"]
            self.cfg["languages"] = [c for c in self.cfg["languages"] if c in self.cfg["known_languages"]]
            config.save(self.cfg)
            self._build_lang_menu(); win.destroy()
        b = ttk.Frame(f); b.grid(row=5, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(b, text=self.t("st_save"), command=ok, style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=win.destroy).pack(side="left", padx=4)

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
    App(folder, langs).mainloop()
