"""Minimale Tkinter-GUI: Ordner (Drag & Drop), Untertitel-Sprachen, Start, Fortschritt, Ergebnis, Einstellungen.
GUI-Sprache umschaltbar (de/ru/en) — siehe i18n.py. Farbschema angelehnt an vl-minisync:
dunkler Fenster-Hintergrund, Bereiche als gleichfarbige Karten darauf."""
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

from . import __version__, config, core, i18n

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:  # ohne Drag & Drop trotzdem lauffähig
    DND_FILES, _Root = None, tk.Tk

BG = "#2c5c4e"           # Fenster-Hintergrund (dunkler) — trennt die Bereiche sichtbar
CARD = "#3d7d69"         # Bereichs-Flächen (vl-minisync-Rahmenton)
CARD_EDGE = "#245043"
TEAL = "#00b0b0"         # Akzent (vl-minisync-Tray-Türkis)
TEAL_DARK = "#008a8a"
INK = "#1b3a36"          # dunkle Schrift auf hellen Flächen
LIGHT = "#dcebe5"        # helle Schrift auf dunklen Flächen
IDLE_BG = "#e2e2dd"      # Ladebalken/Log im Ruhezustand — leichtes Grau statt Weiß
OK_LIGHT, WARN_LIGHT, ERR_LIGHT = "#9fe8bb", "#ffd97a", "#ff9d8f"
GREY = "#8aa79d"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
OPENSUBTITLES_URL = "https://www.opensubtitles.com"
IMDB_RE = re.compile(r"tt\d{6,10}")
LABEL_W = 19             # Label-Spalte: gemeinsame Startkante der Eingabe-Elemente


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


class CanvasBar(tk.Canvas):
    """Fortschrittsbalken: Prozent mittig, Idle-Text im Ruhezustand, Puls fürs Suchen/Laden."""

    def __init__(self, master, height=22):
        super().__init__(master, height=height, highlightthickness=1,
                         highlightbackground=CARD_EDGE, bg=IDLE_BG)
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
            self.create_text(w // 2, h // 2, text=self._idle_text, fill="#4e5b56", font=("Segoe UI", 9))


class App(_Root):
    def __init__(self, folder: str | None = None, langs: list[str] | None = None):
        super().__init__()
        self.geometry("680x800")
        self.minsize(620, 680)
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
        self.scan: core.Scan | None = None      # Ergebnis des Vorlaufs (Tabelle)
        self._scan_gen = 0                       # verwirft veraltete Vorlauf-Ergebnisse
        self._auto_run = bool(folder)            # Kommandozeile: nach dem Vorlauf sofort starten
        self._style()
        self._build()
        if folder:
            self.after(200, self._trigger_scan)

    @property
    def ui(self) -> str:
        return self.cfg.get("ui_language", "en")

    def t(self, key: str, **kw) -> str:
        return i18n.tr(self.ui, key, **kw)

    # ---- Stil ---------------------------------------------------------------
    def _style(self):
        self.configure(bg=BG)
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=CARD, foreground=LIGHT, font=("Segoe UI", 10))
        s.configure("TFrame", background=CARD)
        s.configure("Bg.TFrame", background=BG)
        s.configure("TLabel", background=CARD, foreground=LIGHT)
        s.configure("TButton", background="#f2f2f2", foreground=INK, bordercolor=CARD_EDGE,
                    focuscolor="#f2f2f2", padding=(10, 2))
        s.map("TButton", background=[("active", "white"), ("pressed", "#d8d8d8")])
        s.configure("Square.TButton", padding=(6, 1))
        s.configure("Gear.TButton", padding=(5, 4))
        s.configure("Accent.TButton", background=TEAL, foreground="white", bordercolor=TEAL_DARK,
                    font=("Segoe UI", 10, "bold"), padding=(10, 2))
        s.map("Accent.TButton", background=[("active", TEAL_DARK), ("pressed", TEAL_DARK)])
        s.configure("TMenubutton", background="white", foreground=INK, bordercolor=CARD_EDGE,
                    arrowcolor=TEAL_DARK, padding=(10, 2))
        s.configure("TEntry", fieldbackground="white", foreground=INK, bordercolor=CARD_EDGE, padding=(4, 2))
        s.configure("TCombobox", fieldbackground="white", foreground=INK, bordercolor=CARD_EDGE,
                    arrowcolor=TEAL_DARK)
        s.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)])
        s.configure("Vertical.TScrollbar", background="#e8e8e8", troughcolor=IDLE_BG,
                    bordercolor=CARD_EDGE, arrowcolor=INK)
        self.option_add("*TCombobox*Listbox.background", "white")
        self.option_add("*TCombobox*Listbox.foreground", INK)
        s.configure("Treeview", background="white", fieldbackground="white", foreground=INK,
                    rowheight=22, font=("Segoe UI", 9), bordercolor=CARD_EDGE)
        s.configure("Treeview.Heading", background="#e8e8e8", foreground=INK, font=("Segoe UI", 9, "bold"),
                    relief="flat")
        s.map("Treeview", background=[("selected", TEAL)], foreground=[("selected", "white")])

    # ---- Aufbau -------------------------------------------------------------
    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.title(f"SuperSubber {__version__} — Find & Sync Subtitles")

        # Zahnrad in eigener Zeile ganz oben rechts (auf dem Hintergrund)
        gearrow = ttk.Frame(self, style="Bg.TFrame"); gearrow.pack(fill="x", padx=10, pady=(8, 6))
        try:
            self._gear_img = tk.PhotoImage(file=str(asset("gear.png")))
            gear = ttk.Button(gearrow, image=self._gear_img, style="Gear.TButton", command=self.settings)
        except tk.TclError:
            gear = ttk.Button(gearrow, text="⚙", width=3, style="Gear.TButton", command=self.settings)
        gear.pack(side="right")

        # ---- Karte 1: Bedienung
        card1 = tk.Frame(self, bg=CARD)
        card1.pack(fill="x", padx=10)
        top = ttk.Frame(card1); top.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(top, text=self.t("folder"), width=LABEL_W).pack(side="left")
        self.folder_var = tk.StringVar(value=getattr(self, "folder_var", None) and self.folder_var.get() or self._pending_folder)
        fe = ttk.Entry(top, textvariable=self.folder_var)
        fe.pack(side="left", fill="x", expand=True, padx=(0, 6))
        fe.bind("<Return>", lambda e: self._trigger_scan())
        ttk.Button(top, text="…", width=3, style="Square.TButton", command=self.browse).pack(side="left", fill="y")

        self.drop = tk.Canvas(card1, height=130, bg=CARD, highlightthickness=0, cursor="hand2")
        self.drop.pack(fill="x", padx=10, pady=(6, 12))
        self.drop.bind("<Configure>", self._draw_drop)
        self.drop.bind("<Button-1>", lambda e: self.browse())
        if DND_FILES:
            for w in (self, self.drop):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)

        row = ttk.Frame(card1); row.pack(fill="x", padx=10, pady=(0, 12))
        self._subrow = row
        ttk.Label(row, text=self.t("subtitles"), width=LABEL_W).pack(side="left")
        self.lang_sel: dict[str, tk.BooleanVar] = {}
        self.lang_btn = ttk.Menubutton(row, direction="below")
        self.lang_btn.pack(side="left")
        ttk.Button(row, text=self.t("btn_langs"), style="Square.TButton",
                   command=self.lang_picker).pack(side="left", padx=(6, 0))
        self._build_lang_menu()
        self.start_btn = ttk.Button(row, text=self.t("start"), command=self.start, width=12, style="Accent.TButton")
        self.start_btn.pack(side="right")
        self.start_btn.state(["disabled"])       # erst nach dem Vorlauf

        # ---- Karte 2: Vorlauf-Tabelle — ein Video pro Zeile, IMDb-ID für markierte Zeilen
        tcard = tk.Frame(self, bg=CARD)
        tcard.pack(fill="x", padx=10, pady=(14, 0))
        tf = ttk.Frame(tcard); tf.pack(fill="x", padx=10, pady=(10, 6))
        self.table = ttk.Treeview(tf, columns=("file", "rec", "subs"), show="headings", height=7,
                                  selectmode="extended")
        for col, key, w, stretch in (("file", "col_file", 220, True), ("rec", "col_rec", 150, True),
                                     ("subs", "col_subs", 250, False)):
            self.table.heading(col, text=self.t(key), anchor="w")
            self.table.column(col, width=w, minwidth=80, stretch=stretch, anchor="w")
        self.table.tag_configure("none", foreground="#8a3b2a")
        self.table.tag_configure("present", foreground="#7c8a86")
        self.table.tag_configure("ok", foreground=INK)
        tsb = ttk.Scrollbar(tf, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.table.pack(side="left", fill="x", expand=True)
        irow = ttk.Frame(tcard); irow.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(irow, text=self.t("imdb_for_sel")).pack(side="left")
        self.imdb_var = tk.StringVar()
        ie = ttk.Entry(irow, textvariable=self.imdb_var, width=20)
        ie.pack(side="left", padx=6)
        ie.bind("<Return>", lambda e: self.apply_imdb())
        ttk.Button(irow, text=self.t("apply"), style="Square.TButton", command=self.apply_imdb).pack(side="left")
        ttk.Button(irow, text=self.t("apply_all"), style="Square.TButton",
                   command=lambda: self.apply_imdb(all_missing=True)).pack(side="left", padx=(6, 0))
        self._row_items: dict[str, core.Item] = {}

        # ---- Karte 3: Balken, Statuszeile, Ergebnis, Log (ohne Titel)
        sec = tk.Frame(self, bg=CARD)
        sec.pack(fill="both", expand=True, padx=10, pady=(14, 20))

        self.bar = CanvasBar(sec)
        self.bar.pack(fill="x", padx=10, pady=(10, 2))
        self.bar.idle(self.t("ready"))
        srow = ttk.Frame(sec); srow.pack(fill="x", padx=10)
        self.spinner = tk.Label(srow, text="", font=("Segoe UI", 12), fg="white", width=2, bg=CARD)
        self.spinner.pack(side="left")
        self.status = ttk.Label(srow, text="")
        self.status.pack(side="left", fill="x")

        self.result = tk.Label(sec, text="", font=("Segoe UI", 13, "bold"), bg=CARD, fg="white")
        # wird nur mit Inhalt eingeblendet (sonst unnötiger Leerraum)

        self._logf = ttk.Frame(sec)
        self._logf.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log = tk.Text(self._logf, height=9, state="disabled", font=("Consolas", 9), wrap="word",
                           relief="flat", highlightthickness=1, highlightbackground=CARD_EDGE,
                           bg=IDLE_BG, fg=INK)
        sb = ttk.Scrollbar(self._logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("head", font=("Consolas", 9, "bold"), spacing1=7)
        self.log.tag_configure("sub", lmargin1=20, lmargin2=20)
        self.log.tag_configure("warn", foreground="#7a5c00")
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    def _set_result(self, text: str, fg: str):
        if text:
            self.result.config(text=text, fg=fg)
            self.result.pack(fill="x", padx=10, pady=(4, 0), before=self._logf)
        else:
            self.result.pack_forget()

    def _draw_drop(self, _event=None):
        c = self.drop
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        bw = min(380, max(280, w - 240))          # deutlich schmaler als das Fenster
        x0, x1 = (w - bw) // 2, (w + bw) // 2
        y0, y1 = 2, h - 2
        c.create_rectangle(x0, y0, x1, y1, fill="white", width=0)
        c.create_rectangle(x0 + 12, y0 + 10, x1 - 12, y1 - 10, dash=(7, 4), outline=TEAL, width=2)
        cx, cy = w // 2, h // 2 - 26
        c.create_rectangle(cx - 4, cy - 9, cx + 4, cy + 4, fill=CARD, width=0)
        c.create_polygon(cx - 10, cy + 4, cx + 10, cy + 4, cx, cy + 15, fill=CARD, width=0)
        c.create_text(cx, h // 2 + 22, text=self.t("drop_main"), font=("Segoe UI", 11, "bold"),
                      fill=CARD, justify="center")

    def _build_lang_menu(self):
        menu = tk.Menu(self.lang_btn, tearoff=0)
        self.lang_sel = {}
        for code in self.cfg["known_languages"]:
            var = tk.BooleanVar(value=code in self.cfg["languages"])
            self.lang_sel[code] = var
            menu.add_checkbutton(label=i18n.lang_name(code), variable=var,
                                 command=self._on_lang_toggle)
        self.lang_btn.configure(menu=menu)
        self._update_lang_btn()

    def _on_lang_toggle(self):
        # Auswahl sofort merken — nicht erst bei Start (sonst geht sie beim Schließen verloren)
        self.cfg["languages"] = [c for c, v in self.lang_sel.items() if v.get()]
        config.save(self.cfg)
        self._update_lang_btn()
        if os.path.isdir(self.folder_var.get().strip().strip('"')):
            self._trigger_scan()             # andere Sprachen = anderer Vorlauf

    def _update_lang_btn(self):
        sel = [i18n.lang_name(c) for c, v in self.lang_sel.items() if v.get()]
        self.lang_btn.configure(text=", ".join(sel) if sel else "—")

    def lang_picker(self):
        """Scrollbare Checkbox-Liste aller Sprachen mit Filterfeld; angehakt = im Dropdown angeboten."""
        win = tk.Toplevel(self); win.title(self.t("pick_langs_title")); win.grab_set()
        win.configure(bg=BG); win.geometry("380x540"); win.resizable(False, True)
        try:
            win.iconbitmap(str(asset("icon.ico")))
        except tk.TclError:
            pass
        outer = ttk.Frame(win, padding=12, style="Bg.TFrame"); outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD); card.pack(fill="both", expand=True)
        ttk.Label(card, text=self.t("pick_hint"), wraplength=330).pack(anchor="w", padx=10, pady=(10, 6))

        frow = ttk.Frame(card); frow.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(frow, text="🔍", bg=CARD, fg=LIGHT).pack(side="left", padx=(0, 6))
        filter_var = tk.StringVar()
        ttk.Entry(frow, textvariable=filter_var).pack(side="left", fill="x", expand=True)

        lf = ttk.Frame(card); lf.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(lf, bg="white", highlightthickness=1, highlightbackground=CARD_EDGE)
        sb = ttk.Scrollbar(lf, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # große Liste + evtl. manuell konfigurierte Codes außerhalb davon
        entries = dict(i18n.LANGS)
        for code in self.cfg["known_languages"]:
            entries.setdefault(code, (code, code))
        vars_ = {c: tk.BooleanVar(value=c in self.cfg["known_languages"]) for c in entries}

        def refill(*_):
            for w in inner.winfo_children():
                w.destroy()
            q = filter_var.get().strip().casefold()
            for code, (native, english) in entries.items():
                if q and q not in native.casefold() and q not in english.casefold() and q not in code.casefold():
                    continue
                label = native if native.casefold() == english.casefold() else f"{native}   ({english})"
                tk.Checkbutton(inner, text=label, variable=vars_[code], bg="white", fg=INK,
                               activebackground="white", activeforeground=INK, anchor="w",
                               font=("Segoe UI", 10), padx=8).pack(fill="x")
            canvas.yview_moveto(0)

        filter_var.trace_add("write", refill)
        refill()

        def close():
            win.unbind_all("<MouseWheel>")
            win.destroy()

        def ok():
            checked = [c for c in entries if vars_[c].get()]
            if not checked:
                messagebox.showwarning("SuperSubber", self.t("warn_lang"), parent=win)
                return
            added = [c for c in checked if c not in self.cfg["known_languages"]]
            self.cfg["known_languages"] = checked
            # neu hinzugefügte Sprachen gleich anhaken — dafür wurden sie ja geholt
            self.cfg["languages"] = [c for c in self.cfg["languages"] if c in checked] + added
            config.save(self.cfg)
            close()
            self._build_lang_menu()

        b = ttk.Frame(outer, style="Bg.TFrame"); b.pack(pady=(10, 0))
        ttk.Button(b, text=self.t("st_save"), command=ok, style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=close).pack(side="left", padx=4)
        win.protocol("WM_DELETE_WINDOW", close)

    # ---- Vorlauf (Tabelle) ---------------------------------------------------
    def _trigger_scan(self):
        """Ordner + Sprachen → Vorlauf im Hintergrund. Veraltete Ergebnisse werden per Generation verworfen."""
        if self.worker and self.worker.is_alive():
            return
        folder = self.folder_var.get().strip().strip('"')
        langs = [c for c, v in self.lang_sel.items() if v.get()]
        if not os.path.isdir(folder) or not langs:
            return
        self._scan_gen += 1
        gen = self._scan_gen
        self.scan = None
        self.table.delete(*self.table.get_children())
        self._row_items = {}
        self.start_btn.state(["disabled"])
        self.cancel.clear()
        self._log_clear()
        self.status.config(text=self.t("scanning"))
        ui = self.ui

        def work():
            sc = core.scan(folder, langs, self.cfg,
                           progress=lambda m, i, n: self.q.put(("progress", m, i, n)),
                           log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                           tr=lambda key, **kw: i18n.tr(ui, key, **kw))
            self.q.put(("scan_done", gen, sc))

        self.worker = threading.Thread(target=work, daemon=True)
        self._busy(True)
        self.worker.start()

    def _scan_finished(self, gen: int, sc: core.Scan):
        if gen != self._scan_gen:
            return
        self._busy(False)
        self.spinner.config(text="")
        self.scan = sc
        if sc.error:
            self.bar.idle(self.t("error"))
            self._set_result(f"✖  {sc.error}", ERR_LIGHT); self.status.config(text=""); return
        self._fill_table()
        n = len(sc.items)
        f = len(sc.runnable)
        p = sc.skipped
        self.bar.idle(self.t("ready"))
        self.status.config(text=self.t("scan_summary", n=n, f=f, m=n - f - p, p=p))
        if f:
            self.start_btn.state(["!disabled"])
        if self._auto_run:
            self._auto_run = False
            if f:
                self.start()

    def _row_text(self, it: core.Item) -> tuple[str, str]:
        parts = []
        for lang in (self.scan.languages if self.scan else it.status):
            st = it.status.get(lang)
            if not st:
                continue
            sym = {"present": "✔", "found": "✔", "synced": "✔", "suspect": "⚠", "unsynced": "⚠",
                   "none": "✖", "missing": "✖"}.get(st, "")
            parts.append(f"{lang} {sym} {self.t('s_' + st)}")
        if not it.langs:
            tag = "present"
        elif any(it.status.get(l) in ("none", "missing") for l in it.langs) and \
                not any(it.status.get(l) in ("found", "synced", "suspect", "unsynced") for l in it.langs):
            tag = "none"
        else:
            tag = "ok"
        return "   ".join(parts), tag

    def _fill_table(self):
        self.table.delete(*self.table.get_children())
        self._row_items = {}
        if not self.scan:
            return
        for it in self.scan.items:
            subs, tag = self._row_text(it)
            rec = it.recognized or ("—" if it.langs else "")
            if it.imdb_id:
                rec += f"  [{it.imdb_id}]"
            iid = self.table.insert("", "end", values=(it.video.name, rec, subs), tags=(tag,))
            self._row_items[iid] = it

    def _refresh_rows(self, items: list):
        for iid, it in self._row_items.items():
            if it in items:
                subs, tag = self._row_text(it)
                rec = it.recognized or "—"
                if it.imdb_id:
                    rec += f"  [{it.imdb_id}]"
                self.table.item(iid, values=(it.video.name, rec, subs), tags=(tag,))

    def apply_imdb(self, all_missing: bool = False):
        """IMDb-ID auf markierte Zeilen anwenden und diese Zeilen nachsuchen."""
        if not self.scan or (self.worker and self.worker.is_alive()):
            return
        raw = self.imdb_var.get().strip()
        m = IMDB_RE.search(raw)
        if not m:
            messagebox.showwarning("SuperSubber", self.t("c_imdb_invalid", val=raw)); return
        ttid = m.group(0)
        if all_missing:
            items = [it for it in self.scan.items if it.langs and not all(it.found.get(l) for l in it.langs)]
        else:
            items = [self._row_items[i] for i in self.table.selection() if i in self._row_items]
            items = [it for it in items if it.langs]
        if not items:
            messagebox.showwarning("SuperSubber", self.t("warn_select")); return
        self.cancel.clear()
        ui = self.ui

        def work():
            core.rescan(items, ttid, self.cfg, log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                        tr=lambda key, **kw: i18n.tr(ui, key, **kw))
            self.q.put(("rescan_done", items))

        self.worker = threading.Thread(target=work, daemon=True)
        self._busy(True)
        self.worker.start()

    def _rescan_finished(self, items: list):
        self._busy(False)
        self.spinner.config(text="")
        self._refresh_rows(items)
        if self.scan:
            n, f, p = len(self.scan.items), len(self.scan.runnable), self.scan.skipped
            self.status.config(text=self.t("scan_summary", n=n, f=f, m=n - f - p, p=p))
            self.start_btn.state(["!disabled"] if f else ["disabled"])
        self.bar.idle(self.t("ready"))

    # ---- Aktionen -----------------------------------------------------------
    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.folder_var.set(d.replace("/", "\\"))
            self._trigger_scan()

    def on_drop(self, event):
        paths = list(self.tk.splitlist(event.data))
        subs = [p for p in paths if os.path.splitext(p)[1].lower() in core.SUB_EXT]
        vids = [p for p in paths if os.path.splitext(p)[1].lower() in core.VIDEO_EXT]
        if subs:
            # Untertitel-File → lokalen Sync starten (Video ggf. automatisch/per Dialog)
            self._local_sync(subs[0], vids[0] if vids else None)
            return
        if paths:
            p = paths[0]
            self.folder_var.set(p if os.path.isdir(p) else os.path.dirname(p))
            self._trigger_scan()

    def _local_sync(self, sub: str, video: str | None):
        if self.worker and self.worker.is_alive():
            return
        if not video:
            folder = os.path.dirname(sub)
            vids = [v for v in core.find_videos(folder, int(self.cfg.get("min_size_mb", 50)))
                    if str(v.parent) == folder]
            if len(vids) == 1:
                video = str(vids[0])
            else:
                exts = " ".join(f"*{e}" for e in sorted(core.VIDEO_EXT))
                video = filedialog.askopenfilename(title=self.t("pick_video"),
                                                   filetypes=[("Video", exts)], initialdir=folder)
                if not video:
                    return
                video = video.replace("/", "\\")
        m = re.search(r"\.([a-z]{2}(?:-[a-z]{2})?)\.(?:srt|ass|ssa)$", os.path.basename(sub), re.IGNORECASE)
        # Regionalcodes normalisieren: pt-br → pt-BR
        lang = (m.group(1)[:2].lower() + m.group(1)[2:].upper()) if m \
            else next((c for c, v in self.lang_sel.items() if v.get()), None)
        if not lang:
            messagebox.showwarning("SuperSubber", self.t("warn_lang")); return
        self.folder_var.set(os.path.dirname(video))
        self.cancel.clear()
        self._log_clear()
        ui = self.ui

        def work():
            res = core.run_local(video, sub, lang, self.cfg,
                                 progress=lambda m2, i, n: self.q.put(("progress", m2, i, n)),
                                 log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                                 tr=lambda key, **kw: i18n.tr(ui, key, **kw),
                                 frac=lambda v: self.q.put(("frac", v)))
            self.q.put(("done", res))

        self.worker = threading.Thread(target=work, daemon=True)
        self._busy(True)
        self.worker.start()

    def _busy(self, on: bool):
        self.start_btn.config(text=self.t("cancel_run") if on else self.t("start"))
        if on:
            self.start_btn.state(["!disabled"])   # als Abbrechen immer erreichbar
            self._set_result("", "")
            self.after(100, self._poll)
            self.after(90, self._animate)

    def start(self):
        if self.worker and self.worker.is_alive():
            self.cancel.set(); self.status.config(text=self.t("cancelling")); return
        if not self.scan or not self.scan.runnable:
            self._trigger_scan(); return
        self.cancel.clear()
        self._log_clear()
        self.worker = threading.Thread(target=self._work, daemon=True)
        self._busy(True)
        self.worker.start()

    def _work(self):
        ui = self.ui
        res = core.run_scan(self.scan, self.cfg,
                            progress=lambda m, i, n: self.q.put(("progress", m, i, n)),
                            log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                            tr=lambda key, **kw: i18n.tr(ui, key, **kw),
                            frac=lambda v: self.q.put(("frac", v)))
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
                elif item[0] == "frac":
                    v = item[1]
                    self.bar.set(v, f"{int(v * 100)} %")
                elif item[0] == "progress":
                    _, m, i, n = item
                    if n:
                        self.status.config(text=f"[{i}/{n}] {m}")
                    else:
                        self.bar.pulse()
                        self.status.config(text=m)
                elif item[0] == "scan_done":
                    self._scan_finished(item[1], item[2]); return
                elif item[0] == "rescan_done":
                    self._rescan_finished(item[1]); return
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
            self._set_result(f"✖  {res.error}", ERR_LIGHT); self.status.config(text=""); return
        self.bar.set(1.0, "100 %")
        self.status.config(text=self.t("done"))
        if self.scan:
            self._refresh_rows(self.scan.items)
            self.start_btn.state(["disabled"])   # erledigt — neuer Lauf erst nach neuem Vorlauf
        if not res.synced and not res.unsynced and not res.suspect and not res.missing and not res.noaccess and not res.cancelled:
            self._set_result(self.t("res_all_have", n=res.skipped), OK_LIGHT)
            return
        parts = [self.t("p_synced", n=len(res.synced))]
        if res.skipped: parts.append(self.t("p_existing", n=res.skipped))
        if res.suspect: parts.append(self.t("p_suspect", n=len(res.suspect)))
        if res.unsynced: parts.append(self.t("p_unsynced", n=len(res.unsynced)))
        if res.missing: parts.append(self.t("p_missing", n=len(res.missing)))
        if res.noaccess: parts.append(self.t("p_noaccess", n=len(res.noaccess)))
        ok = not res.missing and not res.unsynced and not res.suspect and not res.noaccess and not res.cancelled
        head = self.t("res_cancelled") if res.cancelled else self.t("res_done")
        self._set_result(("✔  " if ok else "⚠  ") + head + ", ".join(parts), OK_LIGHT if ok else WARN_LIGHT)
        if res.missing:
            self._log(self.t("missing_hint"))
            for m in res.missing: self._log("  " + m)
        if res.suspect:
            self._log(self.t("suspect_hint"))
            for m in res.suspect: self._log("  " + m)
        if res.noaccess:
            self._log(self.t("noaccess_hint"))
            for d in res.noaccess: self._log("  " + d)

    # ---- Einstellungen ------------------------------------------------------
    def settings(self):
        win = tk.Toplevel(self); win.title(self.t("st_title")); win.resizable(False, False); win.grab_set()
        win.configure(bg=BG)
        try:
            win.iconbitmap(str(asset("icon.ico")))
        except tk.TclError:
            pass
        outer = ttk.Frame(win, padding=14, style="Bg.TFrame"); outer.pack(fill="both", expand=True)

        def card(heading: str) -> tk.Frame:
            f = tk.Frame(outer, bg=CARD)
            f.pack(fill="x", pady=(0, 14))
            tk.Label(f, text=heading, bg=CARD, fg="white", font=("Segoe UI", 10, "bold"))\
                .pack(anchor="w", padx=10, pady=(8, 4))
            return f

        # -- App-Sprache
        f1 = card(self.t("sec_app_lang"))
        ui_box = ttk.Combobox(f1, state="readonly", width=18, values=list(i18n.UI_LANGS.values()))
        ui_box.set(i18n.UI_LANGS.get(self.ui, "English"))
        ui_box.pack(anchor="w", padx=10, pady=(0, 10))

        # -- OpenSubtitles-Account
        f2 = card(self.t("sec_account"))
        g = ttk.Frame(f2); g.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(g, text=self.t("st_user")).grid(row=0, column=0, sticky="w", pady=3)
        user = tk.StringVar(value=self.cfg["opensubtitles_user"])
        ttk.Entry(g, textvariable=user, width=30).grid(row=0, column=1, sticky="w", pady=3, padx=(8, 0))
        ttk.Label(g, text=self.t("st_pw")).grid(row=1, column=0, sticky="w", pady=3)
        pw = tk.StringVar(value=config.decrypt(self.cfg["opensubtitles_password"]))
        ttk.Entry(g, textvariable=pw, width=30, show="•").grid(row=1, column=1, sticky="w", pady=3, padx=(8, 0))
        reg = tk.Label(g, text="🔗 " + self.t("st_register"), fg="#bfffff", bg=CARD,
                       cursor="hand2", font=("Segoe UI", 9, "underline"))
        reg.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        reg.bind("<Button-1>", lambda e: webbrowser.open(OPENSUBTITLES_URL))
        ttk.Label(g, text=self.t("st_pw_note"), foreground=GREY,
                  font=("Segoe UI", 8)).grid(row=3, column=0, columnspan=2, sticky="w")

        def ok():
            self.cfg["opensubtitles_user"] = user.get().strip()
            self.cfg["opensubtitles_password"] = config.encrypt(pw.get())
            self.cfg["ui_language"] = next((c for c, n in i18n.UI_LANGS.items() if n == ui_box.get()), "en")
            config.save(self.cfg)
            win.destroy()
            self._build()
        b = ttk.Frame(outer, style="Bg.TFrame"); b.pack(pady=(2, 0))
        ttk.Button(b, text=self.t("st_save"), command=ok, style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=win.destroy).pack(side="left", padx=4)
        foot = tk.Label(outer, text=f"SuperSubber {__version__}  ·  github.com/Cosmopolyte/supersubber",
                        bg=BG, fg=GREY, cursor="hand2", font=("Segoe UI", 8))
        foot.pack(pady=(10, 0))
        foot.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/Cosmopolyte/supersubber"))

    # ---- Log ----------------------------------------------------------------
    def _log(self, s: str):
        tags: tuple[str, ...] = ()
        txt = s
        if s.startswith("    ") or s.startswith("  "):
            txt = s.lstrip(" ")
            tags = ("sub",)
        elif s.startswith("[") or s.startswith(("Suche per IMDb", "Searching via IMDb", "Поиск по IMDb")):
            tags = ("head",)
        if "⚠" in s:
            tags = tags + ("warn",)
        self.log.config(state="normal"); self.log.insert("end", txt + "\n", tags); self.log.see("end"); self.log.config(state="disabled")

    def _log_clear(self):
        self.log.config(state="normal"); self.log.delete("1.0", "end"); self.log.config(state="disabled")


def main():
    """supersubber.exe [Ordner] [--lang ru,de]  — mit Ordner wird sofort gestartet."""
    args = sys.argv[1:]
    langs = None
    if "--lang" in args:
        i = args.index("--lang")
        langs = [x.strip()[:2].lower() + x.strip()[2:].upper() for x in args[i + 1].split(",") if x.strip()] \
            if i + 1 < len(args) else None
        del args[i:i + 2]
    folder = args[0] if args else None
    App(folder, langs).mainloop()
