"""Minimale Tkinter-GUI: Ordner (Drag & Drop), Untertitel-Sprachen, Start, Fortschritt, Ergebnis, Einstellungen.
GUI-Sprache umschaltbar (de/ru/en) — siehe i18n.py. Farbschema angelehnt an vl-minisync."""
from __future__ import annotations

import os
import queue
import re
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

FRAME = "#3d7d69"        # Fensterfläche (vl-minisync-Rahmen)
FRAME_DARK = "#2f6152"
SECTION_BG = os.environ.get("SUBSYNC_SECTION_BG") or FRAME   # Bereichs-Innenfläche (Experiment: zweiter Ton)
TEAL = "#00b0b0"         # Akzent (vl-minisync-Tray-Türkis)
TEAL_DARK = "#008a8a"
INK = "#1b3a36"          # dunkle Schrift auf hellen Flächen
LIGHT = "#dcebe5"        # helle Schrift auf dunkler Fläche
IDLE_BG = "#e9e9e6"      # Ladebalken/Log im Ruhezustand — leichtes Grau statt Weiß
OK_LIGHT, WARN_LIGHT, ERR_LIGHT = "#9fe8bb", "#ffd97a", "#ff9d8f"
GREY = "#8aa79d"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
OPENSUBTITLES_URL = "https://www.opensubtitles.com"
IMDB_RE = re.compile(r"tt\d{6,10}")


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


class CanvasBar(tk.Canvas):
    """Fortschrittsbalken: Prozent mittig, Idle-Text im Ruhezustand, Puls fürs Suchen/Laden."""

    def __init__(self, master, height=22):
        super().__init__(master, height=height, highlightthickness=1,
                         highlightbackground=FRAME_DARK, bg=IDLE_BG)
        self._fraction = 0.0
        self._text = ""
        self._idle_text = ""
        self._pulse_pos = None
        self.bind("<Configure>", lambda e: self._draw())

    def idle(self, text: str):
        self._pulse_pos = None
        self._fraction = 0.0
        self._idle_text = text
        self._draw()

    def set(self, fraction: float, text: str = ""):
        self._pulse_pos = None
        self._fraction = max(0.03, min(1.0, fraction))   # nie ganz leer — man sieht sofort, dass etwas läuft
        self._text = text
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
        elif self._idle_text:
            self.create_text(w // 2, h // 2, text=self._idle_text, fill="#8a8a86", font=("Segoe UI", 9))


class App(_Root):
    def __init__(self, folder: str | None = None, langs: list[str] | None = None):
        super().__init__()
        self.geometry("640x600")
        self.minsize(560, 500)
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
        self._missing: dict[str, list[str]] = {}
        self._style()
        self._build()
        if folder:
            self.after(200, self.start)

    @property
    def ui(self) -> str:
        return self.cfg.get("ui_language", "en")

    def t(self, key: str, **kw) -> str:
        return i18n.tr(self.ui, key, **kw)

    # ---- Stil (vl-minisync-Farben) ------------------------------------------
    def _style(self):
        self.configure(bg=FRAME)
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=FRAME, foreground=LIGHT, font=("Segoe UI", 10))
        s.configure("TFrame", background=FRAME)
        s.configure("TLabel", background=FRAME, foreground=LIGHT)
        s.configure("TButton", background="#f2f2f2", foreground=INK, bordercolor=FRAME_DARK,
                    focuscolor="#f2f2f2", padding=(10, 2))
        s.map("TButton", background=[("active", "white"), ("pressed", "#d8d8d8")])
        s.configure("Square.TButton", padding=(6, 1))
        s.configure("Gear.TButton", padding=(5, 4))
        s.configure("Accent.TButton", background=TEAL, foreground="white", bordercolor=TEAL_DARK,
                    font=("Segoe UI", 10, "bold"), padding=(10, 2))
        s.map("Accent.TButton", background=[("active", TEAL_DARK), ("pressed", TEAL_DARK)])
        s.configure("TMenubutton", background="white", foreground=INK, bordercolor=FRAME_DARK,
                    arrowcolor=TEAL_DARK, padding=(10, 2))
        s.configure("TEntry", fieldbackground="white", foreground=INK, bordercolor=FRAME_DARK, padding=(4, 2))
        s.configure("TCombobox", fieldbackground="white", foreground=INK, bordercolor=FRAME_DARK,
                    arrowcolor=TEAL_DARK)
        s.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)])
        s.configure("Vertical.TScrollbar", background="#e8e8e8", troughcolor=IDLE_BG,
                    bordercolor=FRAME_DARK, arrowcolor=INK)
        # Bereichs-Stile (Innenfläche kann als zweiter Ton abweichen)
        s.configure("Sec.TLabelframe", background=SECTION_BG, bordercolor=LIGHT, relief="groove")
        s.configure("Sec.TLabelframe.Label", background=FRAME, foreground="white", font=("Segoe UI", 10, "bold"))
        s.configure("Sec.TFrame", background=SECTION_BG)
        s.configure("Sec.TLabel", background=SECTION_BG, foreground=LIGHT)
        self.option_add("*TCombobox*Listbox.background", "white")
        self.option_add("*TCombobox*Listbox.foreground", INK)

    # ---- Aufbau -------------------------------------------------------------
    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.title("subsync — Find & Sync Subtitles")

        # Zahnrad in eigener Zeile ganz oben rechts
        gearrow = ttk.Frame(self); gearrow.pack(fill="x", padx=10, pady=(8, 0))
        try:
            self._gear_img = tk.PhotoImage(file=str(asset("gear.png")))
            gear = ttk.Button(gearrow, image=self._gear_img, style="Gear.TButton", command=self.settings)
        except tk.TclError:
            gear = ttk.Button(gearrow, text="⚙", width=3, style="Gear.TButton", command=self.settings)
        gear.pack(side="right")

        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=(2, 4))
        ttk.Label(top, text=self.t("folder")).pack(side="left")
        self.folder_var = tk.StringVar(value=getattr(self, "folder_var", None) and self.folder_var.get() or self._pending_folder)
        ttk.Entry(top, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="…", width=3, style="Square.TButton", command=self.browse).pack(side="left", fill="y")

        self.drop = tk.Canvas(self, height=118, bg=FRAME, highlightthickness=0, cursor="hand2")
        self.drop.pack(fill="x", padx=10, pady=(4, 6))
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
        self.start_btn = ttk.Button(row, text=self.t("start"), command=self.start, width=12, style="Accent.TButton")
        self.start_btn.pack(side="right")

        # Unterer Bereich: Balken, Status, Ergebnis, Log — optisch getrennt wie in den Einstellungen
        sec = ttk.Labelframe(self, text=self.t("sec_status"), style="Sec.TLabelframe", padding=8)
        sec.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        self.bar = CanvasBar(sec)
        self.bar.pack(fill="x", pady=(0, 3))
        self.bar.idle(self.t("ready"))
        srow = ttk.Frame(sec, style="Sec.TFrame"); srow.pack(fill="x")
        self.spinner = tk.Label(srow, text="", font=("Segoe UI", 12), fg="white", width=2, bg=SECTION_BG)
        self.spinner.pack(side="left")
        self.status = ttk.Label(srow, text="", style="Sec.TLabel")
        self.status.pack(side="left", fill="x")
        self.imdb_btn = ttk.Button(srow, text=self.t("btn_imdb"), command=self.imdb_dialog)
        # wird nur bei „nicht gefunden" eingeblendet

        self.result = tk.Label(sec, text="", font=("Segoe UI", 13, "bold"), bg=SECTION_BG, fg="white")
        self.result.pack(fill="x", pady=2)

        logf = ttk.Frame(sec, style="Sec.TFrame")
        logf.pack(fill="both", expand=True)
        self.log = tk.Text(logf, height=9, state="disabled", font=("Consolas", 9), wrap="word",
                           relief="flat", highlightthickness=1, highlightbackground=FRAME_DARK,
                           bg=IDLE_BG, fg=INK)
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    def _draw_drop(self, _event=None):
        c = self.drop
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        bw = min(470, max(300, w - 140))          # nicht volle Breite
        x0, x1 = (w - bw) // 2, (w + bw) // 2
        y0, y1 = 2, h - 2
        c.create_rectangle(x0, y0, x1, y1, fill="white", width=0)
        c.create_rectangle(x0 + 12, y0 + 10, x1 - 12, y1 - 10, dash=(7, 4), outline=TEAL, width=2)
        cx, cy = w // 2, h // 2 - 14
        c.create_rectangle(cx - 4, cy - 9, cx + 4, cy + 4, fill=FRAME, width=0)
        c.create_polygon(cx - 10, cy + 4, cx + 10, cy + 4, cx, cy + 15, fill=FRAME, width=0)
        c.create_text(cx, h // 2 + 20, text=self.t("drop_main"), font=("Segoe UI", 11, "bold"), fill=FRAME)

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

    def _busy(self, on: bool):
        self.start_btn.config(text=self.t("cancel_run") if on else self.t("start"))
        if on:
            self.imdb_btn.pack_forget()
            self.result.config(text="")
            self.after(100, self._poll)
            self.after(90, self._animate)

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
        self.cancel.clear()
        self._log_clear()
        self.worker = threading.Thread(target=self._work, args=(folder, langs), daemon=True)
        self._busy(True)
        self.worker.start()

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
        self._busy(False)
        self.spinner.config(text="")
        if res.error:
            self.bar.idle(self.t("error"))
            self.result.config(text=f"✖  {res.error}", fg=ERR_LIGHT); self.status.config(text=""); return
        self.bar.set(1.0, "100 %")
        self.status.config(text=self.t("done"))
        self._missing = {}
        for path, lang in res.missing_items:
            self._missing.setdefault(path, []).append(lang)
        if self._missing:
            self.imdb_btn.pack(side="right")
        if not res.synced and not res.unsynced and not res.missing and not res.noaccess and not res.cancelled:
            self.result.config(text=self.t("res_all_have", n=res.skipped), fg=OK_LIGHT)
            return
        parts = [self.t("p_synced", n=len(res.synced))]
        if res.skipped: parts.append(self.t("p_existing", n=res.skipped))
        if res.unsynced: parts.append(self.t("p_unsynced", n=len(res.unsynced)))
        if res.missing: parts.append(self.t("p_missing", n=len(res.missing)))
        if res.noaccess: parts.append(self.t("p_noaccess", n=len(res.noaccess)))
        ok = not res.missing and not res.unsynced and not res.noaccess and not res.cancelled
        head = self.t("res_cancelled") if res.cancelled else self.t("res_done")
        self.result.config(text=("✔  " if ok else "⚠  ") + head + ", ".join(parts), fg=OK_LIGHT if ok else WARN_LIGHT)
        if res.missing:
            self._log(self.t("missing_hint"))
            for m in res.missing: self._log("  " + m)
        if res.noaccess:
            self._log(self.t("noaccess_hint"))
            for d in res.noaccess: self._log("  " + d)

    # ---- IMDb-Nachsuche ------------------------------------------------------
    def imdb_dialog(self):
        win = tk.Toplevel(self); win.title("IMDb"); win.resizable(False, False); win.grab_set()
        win.configure(bg=FRAME)
        try:
            win.iconbitmap(str(asset("icon.ico")))
        except tk.TclError:
            pass
        f = ttk.Frame(win, padding=14); f.pack(fill="both", expand=True)
        ttk.Label(f, text=self.t("imdb_intro"), justify="left").grid(row=0, column=0, columnspan=2,
                                                                    sticky="w", pady=(0, 10))
        entries: list[tuple[str, list[str], tk.StringVar]] = []
        for r, (path, langs) in enumerate(sorted(self._missing.items()), start=1):
            name = Path(path).name
            if len(name) > 52:
                name = name[:49] + "…"
            ttk.Label(f, text=f"{name}  [{', '.join(langs)}]").grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            ttk.Entry(f, textvariable=var, width=26).grid(row=r, column=1, sticky="w", padx=(10, 0), pady=2)
            entries.append((path, langs, var))

        def cancel():
            self._log(self.t("c_imdb_cancel"))
            win.destroy()

        def search():
            jobs, bad = [], []
            for path, langs, var in entries:
                raw = var.get().strip()
                if not raw:
                    continue
                m = IMDB_RE.search(raw)
                if not m:
                    bad.append(raw)
                    continue
                jobs.append((path, langs, m.group(0)))
            if bad:
                messagebox.showwarning("subsync", self.t("c_imdb_invalid", val=", ".join(bad)), parent=win)
                return
            win.destroy()
            if not jobs:
                self._log(self.t("c_imdb_cancel"))
                return
            self._start_imdb(jobs)

        b = ttk.Frame(f); b.grid(row=len(entries) + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(b, text=self.t("imdb_search"), command=search, style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=cancel).pack(side="left", padx=4)

    def _start_imdb(self, jobs: list[tuple[str, list[str], str]]):
        if self.worker and self.worker.is_alive():
            return
        ui = self.ui
        self.cancel.clear()

        def work():
            res = core.run_imdb(jobs, self.cfg,
                                progress=lambda m, i, n: self.q.put(("progress", m, i, n)),
                                log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                                tr=lambda key, **kw: i18n.tr(ui, key, **kw))
            self.q.put(("done", res))

        self.worker = threading.Thread(target=work, daemon=True)
        self._busy(True)
        self.worker.start()

    # ---- Einstellungen ------------------------------------------------------
    def settings(self):
        win = tk.Toplevel(self); win.title(self.t("st_title")); win.resizable(False, False); win.grab_set()
        win.configure(bg=FRAME)
        try:
            win.iconbitmap(str(asset("icon.ico")))
        except tk.TclError:
            pass
        outer = ttk.Frame(win, padding=14); outer.pack(fill="both", expand=True)

        # -- App-Sprache
        f1 = ttk.Labelframe(outer, text=self.t("sec_app_lang"), style="Sec.TLabelframe", padding=10)
        f1.pack(fill="x", pady=(0, 10))
        ui_box = ttk.Combobox(f1, state="readonly", width=18, values=list(i18n.UI_LANGS.values()))
        ui_box.set(i18n.UI_LANGS.get(self.ui, "English"))
        ui_box.pack(anchor="w")

        # -- OpenSubtitles-Account
        f2 = ttk.Labelframe(outer, text=self.t("sec_account"), style="Sec.TLabelframe", padding=10)
        f2.pack(fill="x", pady=(0, 10))
        ttk.Label(f2, text=self.t("st_user"), style="Sec.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        user = tk.StringVar(value=self.cfg["opensubtitles_user"])
        ttk.Entry(f2, textvariable=user, width=30).grid(row=0, column=1, sticky="w", pady=3, padx=(8, 0))
        ttk.Label(f2, text=self.t("st_pw"), style="Sec.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        pw = tk.StringVar(value=config.decrypt(self.cfg["opensubtitles_password"]))
        ttk.Entry(f2, textvariable=pw, width=30, show="•").grid(row=1, column=1, sticky="w", pady=3, padx=(8, 0))
        reg = tk.Label(f2, text="🔗 " + self.t("st_register"), fg="#bfffff", bg=SECTION_BG,
                       cursor="hand2", font=("Segoe UI", 9, "underline"))
        reg.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        reg.bind("<Button-1>", lambda e: webbrowser.open(OPENSUBTITLES_URL))
        ttk.Label(f2, text=self.t("st_pw_note"), foreground=GREY, style="Sec.TLabel",
                  font=("Segoe UI", 8)).grid(row=3, column=0, columnspan=2, sticky="w")

        # -- Untertitel-Sprachen
        f3 = ttk.Labelframe(outer, text=self.t("sec_sub_langs"), style="Sec.TLabelframe", padding=10)
        f3.pack(fill="x", pady=(0, 10))
        ttk.Label(f3, text=self.t("st_langs"), style="Sec.TLabel").pack(anchor="w")
        known = tk.StringVar(value=", ".join(self.cfg["known_languages"]))
        ttk.Entry(f3, textvariable=known, width=42).pack(anchor="w", pady=(3, 0))

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
            self.cfg["ui_language"] = next((c for c, n in i18n.UI_LANGS.items() if n == ui_box.get()), "en")
            config.save(self.cfg)
            win.destroy()
            self._build()
        b = ttk.Frame(outer); b.pack(pady=(2, 0))
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
