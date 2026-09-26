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
from tkinter import filedialog, ttk
from tkinter import font as tkfont

from . import __version__, config, core, i18n, logfile

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Root = TkinterDnD.Tk
except ImportError:  # ohne Drag & Drop trotzdem lauffähig
    DND_FILES, _Root = None, tk.Tk

# Farbschemata: „green" ist das Original (vl-minisync-Töne), „light" und „dark" nutzen dieselbe Struktur.
# apply_theme() schreibt die Werte als Modul-Konstanten, alle Widgets lesen sie beim Aufbau.
THEMES = {
    "green": dict(
        BG="#2c5c4e",         # Fenster-Hintergrund (dunkler) — trennt die Bereiche sichtbar
        CARD="#3d7d69",       # Bereichs-Flächen
        CARD_EDGE="#245043",
        TEAL="#00b0b0",       # Akzent
        TEAL_DARK="#008a8a",
        INK="#1b3a36",        # Schrift auf Eingabeflächen (Tabelle, Felder, Log)
        LIGHT="#dcebe5",      # Schrift auf Karten
        TITLE="white",        # Überschriften auf Karten
        GREY="#8aa79d",       # Nebentexte auf Karten
        LINK="#bfffff",
        FIELD="white",        # Eingabeflächen
        FIELD_ALT="#eef2f0",  # Zebra-Zeilen
        IDLE_BG="#e2e2dd",    # Ladebalken/Log im Ruhezustand
        IDLE_TEXT="#4e5b56",
        HEAD="#e8e8e8",       # Tabellenkopf
        HEAD_EDGE="#b3bfbb",
        BTN="#f2f2f2", BTN_ACTIVE="white", BTN_PRESSED="#d8d8d8",
        ACCENT_DIS="#6f8f86", ACCENT_DIS_FG="#d3ddd9",
        DROP_FG="#3d7d69",    # Pfeil und Text in der Drop-Zone
        TIP_BG="#fffbe6",
        ROW_NONE="#8a3b2a", ROW_PRESENT="#7c8a86",
        LOG_WARN="#7a5c00", LOG_OK="#1e7a45", LOG_FAIL="#a83a2a", LOG_SEP="#8a9a95",
        CHECK_BG="#245043",   # Kästchen der Checkboxen auf Karten (Häkchen in Kartenschrift)
        GEAR="gear.png",
        DARK_TITLEBAR=True,   # Windows: dunkle Titelleiste, Farbe = BG
        EDGE3D="",            # 3D-Kanten von clam: leer = Standard (hell), sonst Farbe
        BORDER="#8fb3a6",     # Umrandung von Knöpfen, Feldern, Tabelle — weicher als CARD_EDGE
    ),
    "light": dict(
        BG="#d9e1dd", CARD="#f3f6f4", CARD_EDGE="#b4c2bc", TEAL="#00a3a3", TEAL_DARK="#007f7f",
        INK="#1b3a36", LIGHT="#20302c", TITLE="#1b3a36", GREY="#5f6f6a", LINK="#006d6d",
        FIELD="white", FIELD_ALT="#eef2f0", IDLE_BG="#e6e9e7", IDLE_TEXT="#5a6663",
        HEAD="#e1e6e4", HEAD_EDGE="#b3bfbb",
        BTN="#ffffff", BTN_ACTIVE="#f0f4f2", BTN_PRESSED="#d8dedb",
        ACCENT_DIS="#9fc4bd", ACCENT_DIS_FG="#eef5f3",
        DROP_FG="#2c5c4e", TIP_BG="#fffbe6",
        ROW_NONE="#8a3b2a", ROW_PRESENT="#7c8a86",
        LOG_WARN="#7a5c00", LOG_OK="#1e7a45", LOG_FAIL="#a83a2a", LOG_SEP="#8a9a95",
        CHECK_BG="white", GEAR="gear.png", DARK_TITLEBAR=False, EDGE3D="", BORDER="#b4c2bc",
    ),
    "dark": dict(
        BG="#1a1c1e", CARD="#26292c", CARD_EDGE="#3b4045", TEAL="#00b0b0", TEAL_DARK="#008a8a",
        INK="#e4e6e5", LIGHT="#d6dad8", TITLE="white", GREY="#8b9398", LINK="#5fd3d3",
        FIELD="#141618", FIELD_ALT="#1d2022", IDLE_BG="#1f2225", IDLE_TEXT="#9aa3a0",
        HEAD="#2f3336", HEAD_EDGE="#4a5054",
        BTN="#3a3f43", BTN_ACTIVE="#4a5054", BTN_PRESSED="#2f3336",
        ACCENT_DIS="#3f5a54", ACCENT_DIS_FG="#8fa39d",
        DROP_FG="#00b0b0", TIP_BG="#403f2e",
        ROW_NONE="#e08a78", ROW_PRESENT="#9aa7a3",
        LOG_WARN="#e2c46a", LOG_OK="#7fd3a0", LOG_FAIL="#f08b7b", LOG_SEP="#7d8a86",
        CHECK_BG="#141618", GEAR="gear_light.png", DARK_TITLEBAR=True, EDGE3D="#3b4045", BORDER="#3b4045",
    ),
}
BG = CARD = CARD_EDGE = TEAL = TEAL_DARK = INK = LIGHT = TITLE = GREY = LINK = FIELD = FIELD_ALT = ""
IDLE_BG = IDLE_TEXT = HEAD = HEAD_EDGE = BTN = BTN_ACTIVE = BTN_PRESSED = ACCENT_DIS = ACCENT_DIS_FG = ""
DROP_FG = TIP_BG = ROW_NONE = ROW_PRESENT = LOG_WARN = LOG_OK = LOG_FAIL = LOG_SEP = CHECK_BG = GEAR = ""
DARK_TITLEBAR = False
EDGE3D = ""
BORDER = ""


def apply_theme(name: str) -> str:
    """Schema als Modul-Konstanten setzen; unbekannter Name → green. Gibt den wirksamen Namen zurück."""
    name = name if name in THEMES else "green"
    globals().update(THEMES[name])
    return name


apply_theme("green")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
OPENSUBTITLES_URL = "https://www.opensubtitles.com"
IMDB_RE = re.compile(r"tt\d{6,10}")
LABEL_W = 19             # Label-Spalte: gemeinsame Startkante der Eingabe-Elemente
WIN = sys.platform == "win32"
UI_FONT = "Segoe UI" if WIN else "DejaVu Sans"   # Linux: wird in App.__init__ durch die Desktop-Schrift von Tk ersetzt
LINK_ICON = "🔗 " if WIN else "↗ "                 # Tk 8.6 unter X11 hat für Emoji außerhalb der BMP meist keine Glyphe


def _desktop_font() -> str:
    """Schriftfamilie der GUI: Segoe UI auf Windows, sonst die Sans, die Tk für den Desktop gewählt hat."""
    if WIN:
        return "Segoe UI"
    try:
        return tkfont.nametofont("TkDefaultFont").actual("family") or "DejaVu Sans"
    except tk.TclError:
        return "DejaVu Sans"


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def style_titlebar(win: tk.Misc) -> None:
    """Windows: Titelleiste in der Fensterfarbe (Windows 11) bzw. dunkel (Windows 10). Andere Systeme: nichts."""
    if not WIN:
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        dwm = ctypes.windll.dwmapi

        def colorref(hex_color: str) -> int:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (b << 16) | (g << 8) | r
        dark = ctypes.c_int(1 if DARK_TITLEBAR else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))        # immersive dark mode
        cap = ctypes.c_int(colorref(BG))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), ctypes.sizeof(cap))          # caption color (Win 11)
        txt = ctypes.c_int(colorref("#ffffff" if DARK_TITLEBAR else "#1b3a36"))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt), ctypes.sizeof(txt))          # caption text color
    except Exception:  # noqa: BLE001 — älteres Windows oder kein DWM: Standard-Titelleiste
        pass


def set_icon(win: tk.Misc, default: bool = False) -> None:
    """Fenstersymbol: .ico auf Windows, sonst PNG per iconphoto — die Bildreferenz bleibt am Fenster hängen,
    sonst räumt Tk sie weg."""
    try:
        if WIN:
            win.iconbitmap(**({"default": str(asset("icon.ico"))} if default else {"bitmap": str(asset("icon.ico"))}))
        else:
            img = tk.PhotoImage(file=str(asset("icon_256.png")))
            win.iconphoto(default, img)
            win._icon_img = img  # type: ignore[attr-defined]
    except tk.TclError:
        pass


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
                                 font=(UI_FONT, 9, "bold"))
        elif self._idle_text:
            self.create_text(w // 2, h // 2, text=self._idle_text, fill=IDLE_TEXT, font=(UI_FONT, 9))


class App(_Root):
    def __init__(self, folder: str | None = None, langs: list[str] | None = None):
        super().__init__()
        global UI_FONT
        UI_FONT = _desktop_font()
        self.cfg = config.load()
        logfile.setup(self.cfg.get("log_max_mb", 20))
        self.cfg["theme"] = apply_theme(str(self.cfg.get("theme", "green")))
        # Fenstergröße: zuletzt gemerkte, sonst nach Bildschirm (etwa 60 % × 80 %, zentriert)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        geo = str(self.cfg.get("window") or "")
        m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geo)
        fit = not m or int(m.group(3)) > sw - 200 or int(m.group(4)) > sh - 200
        if not fit:
            self.geometry(geo)
        self.minsize(640, 620)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        set_icon(self, default=True)
        style_titlebar(self)
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
        self._table_langs: list[str] = []
        self._tip: tk.Toplevel | None = None
        self._tip_cell = None
        self._style()
        self._build()
        if fit:
            # Höhe nach dem Platzbedarf der Widgets, damit auf kleinen Bildschirmen und mit größeren
            # Linux-Schriften nichts abgeschnitten wird; Deckel bleibt der Bildschirm
            self.update_idletasks()
            w = min(int(sw * 0.62), 1180)
            h = min(max(int(sh * 0.82), self.winfo_reqheight() + 8), 1050, sh - 60)
            self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}")
        if folder:
            self.after(200, self._trigger_scan)
        elif self.cfg.get("check_updates_on_start", True):
            self.after(1500, lambda: self.check_updates(silent=True))

    def _on_close(self):
        try:
            self.cfg["window"] = self.geometry()
            config.save(self.cfg)
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

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
        # lightcolor/darkcolor = die 3D-Kanten von clam. Styles sind prozessweit und überleben einen Schema-
        # wechsel, deshalb immer BEIDE Werte setzen: dunkles Schema eigene Farbe, sonst die clam-Vorgabe.
        if not hasattr(self, "_clam_edges"):
            self._clam_edges = (s.lookup(".", "lightcolor") or "#eeebe7", s.lookup(".", "darkcolor") or "#cfcdc8")
        light_edge, dark_edge = (EDGE3D, EDGE3D) if EDGE3D else self._clam_edges
        s.configure(".", background=CARD, foreground=LIGHT, font=(UI_FONT, 10), bordercolor=BORDER,
                    lightcolor=light_edge, darkcolor=dark_edge)
        s.configure("TFrame", background=CARD)
        s.configure("Bg.TFrame", background=BG)
        s.configure("TLabel", background=CARD, foreground=LIGHT)
        s.configure("TButton", background=BTN, foreground=INK, bordercolor=BORDER,
                    focuscolor=BTN, padding=(10, 2))
        s.map("TButton", background=[("active", BTN_ACTIVE), ("pressed", BTN_PRESSED)])
        s.configure("Square.TButton", padding=(6, 1))
        s.configure("Cell.TButton", padding=(5, 0), font=(UI_FONT, 8, "bold"))
        s.configure("Gear.TButton", padding=(5, 4))
        s.configure("Accent.TButton", background=TEAL, foreground="white", bordercolor=TEAL_DARK,
                    font=(UI_FONT, 10, "bold"), padding=(10, 2))
        s.map("Accent.TButton", background=[("disabled", ACCENT_DIS), ("active", TEAL_DARK), ("pressed", TEAL_DARK)],
              foreground=[("disabled", ACCENT_DIS_FG)])
        s.configure("TMenubutton", background=FIELD, foreground=INK, bordercolor=BORDER,
                    arrowcolor=TEAL_DARK, padding=(10, 2))
        s.map("TMenubutton", background=[("active", FIELD), ("pressed", FIELD_ALT)], foreground=[("active", INK)])
        s.configure("TEntry", fieldbackground=FIELD, foreground=INK, bordercolor=BORDER, padding=(4, 2))
        s.configure("TCombobox", fieldbackground=FIELD, foreground=INK, bordercolor=BORDER,
                    background=BTN, arrowcolor=TEAL_DARK)
        s.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", INK)],
              background=[("readonly", BTN)])
        s.configure("TSpinbox", fieldbackground=FIELD, foreground=INK, background=BTN, bordercolor=BORDER,
                    arrowcolor=TEAL_DARK, padding=(4, 2))
        for sb_style in ("TScrollbar", "Vertical.TScrollbar"):
            s.configure(sb_style, background=HEAD, troughcolor=IDLE_BG, bordercolor=BORDER, arrowcolor=INK,
                        lightcolor=HEAD if EDGE3D else light_edge, darkcolor=HEAD if EDGE3D else dark_edge)
            s.map(sb_style, background=[("active", HEAD_EDGE), ("pressed", HEAD_EDGE), ("disabled", IDLE_BG)],
                  arrowcolor=[("disabled", GREY)])
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        row_h = tkfont.Font(font=(UI_FONT, 9)).metrics("linespace") + 8   # statt fest 22: bei großer Schrift überlappten Zeilen
        s.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=INK,
                    rowheight=row_h, font=(UI_FONT, 9), bordercolor=BORDER)
        s.configure("Treeview.Heading", background=HEAD, foreground=INK, font=(UI_FONT, 9, "bold"),
                    relief="solid", borderwidth=1, bordercolor=HEAD_EDGE, padding=(6, 3))
        s.map("Treeview", background=[("selected", TEAL)], foreground=[("selected", "white")])
        s.map("Treeview.Heading", background=[("active", HEAD_EDGE), ("pressed", HEAD_EDGE)],
              foreground=[("active", INK), ("pressed", INK)])

    # ---- Aufbau -------------------------------------------------------------
    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.title(f"SuperSubber {__version__} — Find & Sync Subtitles")

        # Zahnrad in eigener Zeile ganz oben rechts (auf dem Hintergrund)
        gearrow = ttk.Frame(self, style="Bg.TFrame"); gearrow.pack(fill="x", padx=10, pady=(8, 6))
        try:
            self._gear_img = tk.PhotoImage(file=str(asset(GEAR)))
            gear = ttk.Button(gearrow, image=self._gear_img, style="Gear.TButton", command=self.settings)
        except tk.TclError:
            gear = ttk.Button(gearrow, text="⚙", width=3, style="Gear.TButton", command=self.settings)
        gear.pack(side="right")
        self._tooltip(gear, self.t("tt_settings"))

        # ---- Karte 1: Bedienung
        card1 = tk.Frame(self, bg=CARD)
        card1.pack(fill="x", padx=10)
        top = ttk.Frame(card1); top.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(top, text=self.t("folder"), width=LABEL_W).pack(side="left")
        self.folder_var = tk.StringVar(value=getattr(self, "folder_var", None) and self.folder_var.get() or self._pending_folder)
        # Wählen-Knopf VOR dem Pfadfeld — das Feld darf beliebig breit werden, der Knopf bleibt sichtbar
        browse = ttk.Button(top, text="…", width=4, style="Square.TButton", command=self.browse)
        browse.pack(side="left", fill="y", padx=(0, 6))
        self._tooltip(browse, self.t("tt_browse"))
        fe = ttk.Entry(top, textvariable=self.folder_var)
        fe.pack(side="left", fill="x", expand=True)
        fe.bind("<Return>", lambda e: self._trigger_scan())

        drop_h = tkfont.Font(font=(UI_FONT, 11, "bold")).metrics("linespace") * 2 + 64   # Pfeil + zwei Zeilen
        self.drop = tk.Canvas(card1, height=drop_h, bg=CARD, highlightthickness=0, cursor="hand2")
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
        langs_btn = ttk.Button(row, text=self.t("btn_langs"), style="Square.TButton", command=self.lang_picker)
        langs_btn.pack(side="left", padx=(6, 0))
        self._tooltip(langs_btn, self.t("tt_langs"))
        self._build_lang_menu()

        # ---- Karte 2: Vorlauf-Tabelle — Datei · Erkannt als · eine Spalte je Sprache · IMDb; Start darunter
        tcard = tk.Frame(self, bg=CARD)
        tcard.pack(fill="both", expand=True, padx=10, pady=(14, 0))
        tf = ttk.Frame(tcard); tf.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.table = ttk.Treeview(tf, columns=("file",), show="headings", height=6, selectmode="browse")
        self.table.tag_configure("none", foreground=ROW_NONE)
        self.table.tag_configure("present", foreground=ROW_PRESENT)
        self.table.tag_configure("ok", foreground=INK)
        self.table.tag_configure("odd", background=FIELD_ALT)
        self.table.tag_configure("even", background=FIELD)
        self.table.bind("<Button-1>", self._on_table_click)
        self.table.bind("<Motion>", self._on_table_motion)
        self.table.bind("<Leave>", self._tip_hide)
        tsb = ttk.Scrollbar(tf, orient="vertical", command=self.table.yview)
        # Overlay-Buttons in der IMDb-Spalte müssen bei Scroll und Größenänderung mitwandern
        self.table.configure(yscrollcommand=lambda *a: (tsb.set(*a), self._place_imdb_buttons()))
        self.table.bind("<Configure>", lambda e: self.after_idle(self._place_imdb_buttons))
        tsb.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self._row_items: dict[str, core.Item] = {}
        self._imdb_btns: dict[str, tuple] = {}
        self._table_langs = []
        self._setup_columns([c for c, v in self.lang_sel.items() if v.get()])
        foot = ttk.Frame(tcard); foot.pack(fill="x", padx=10, pady=(0, 10))
        self.start_btn = ttk.Button(foot, text=self.t("start"), command=self.start, width=12, style="Accent.TButton")
        self.start_btn.pack(side="right")
        self.start_btn.state(["disabled"])       # erst nach dem Vorlauf
        # Zeilen, bei denen alle Sprachen schon da sind, tragen keine Aktion — bei 500 Folgen nur Ballast
        self.show_present = tk.BooleanVar(value=bool(self.cfg.get("show_present", True)))
        tk.Checkbutton(foot, text=self.t("show_present"), variable=self.show_present, bg=CARD, fg=LIGHT,
                       activebackground=CARD, activeforeground=LIGHT, selectcolor=CHECK_BG, highlightthickness=0,
                       font=(UI_FONT, 9), command=self._toggle_present).pack(side="left")
        # ---- Karte 3: Balken, Statuszeile, Ergebnis, Log (ohne Titel)
        sec = tk.Frame(self, bg=CARD)
        sec.pack(fill="both", expand=True, padx=10, pady=(14, 20))

        self.bar = CanvasBar(sec)
        self.bar.pack(fill="x", padx=10, pady=(10, 2))
        self.bar.idle(self.t("ready"))
        srow = ttk.Frame(sec); srow.pack(fill="x", padx=10)
        self.spinner = tk.Label(srow, text="", font=(UI_FONT, 12), fg=TITLE, width=2, bg=CARD)
        self.spinner.pack(side="left")
        self.status = ttk.Label(srow, text="")
        self.status.pack(side="left", fill="x")

        self._logf = ttk.Frame(sec)
        self._logf.pack(fill="both", expand=True, padx=10, pady=(4, 6))
        self.log = tk.Text(self._logf, height=7, state="disabled", font=("Consolas", 9), wrap="word",
                           relief="flat", highlightthickness=1, highlightbackground=CARD_EDGE,
                           bg=IDLE_BG, fg=INK)
        sb = ttk.Scrollbar(self._logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("head", font=("Consolas", 9, "bold"), spacing1=7)
        self.log.tag_configure("sub", lmargin1=20, lmargin2=20)
        self.log.tag_configure("warn", foreground=LOG_WARN)
        self.log.tag_configure("ok", foreground=LOG_OK)
        self.log.tag_configure("fail", foreground=LOG_FAIL)
        self.log.tag_configure("sep", foreground=LOG_SEP)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        lfoot = ttk.Frame(sec); lfoot.pack(fill="x", padx=10, pady=(0, 10))
        save_btn = ttk.Button(lfoot, text=self.t("save_log"), style="Square.TButton", command=self.save_log)
        save_btn.pack(side="right")
        self._tooltip(save_btn, self.t("tt_save_log"))

    def _set_result(self, text: str, fg: str = ""):
        self.status.config(text=text)

    def _draw_drop(self, _event=None):
        c = self.drop
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        bw = min(380, max(280, w - 240))          # deutlich schmaler als das Fenster
        x0, x1 = (w - bw) // 2, (w + bw) // 2
        y0, y1 = 2, h - 2
        c.create_rectangle(x0, y0, x1, y1, fill=FIELD, width=0)
        c.create_rectangle(x0 + 12, y0 + 10, x1 - 12, y1 - 10, dash=(7, 4), outline=TEAL, width=2)
        cx, cy = w // 2, h // 2 - int(h * 0.2)
        c.create_rectangle(cx - 4, cy - 9, cx + 4, cy + 4, fill=DROP_FG, width=0)
        c.create_polygon(cx - 10, cy + 4, cx + 10, cy + 4, cx, cy + 15, fill=DROP_FG, width=0)
        c.create_text(cx, h // 2 + int(h * 0.17), text=self.t("drop_main"), font=(UI_FONT, 11, "bold"),
                      fill=DROP_FG, justify="center")

    def _build_lang_menu(self):
        menu = tk.Menu(self.lang_btn, tearoff=0, bg=FIELD, fg=INK, activebackground=TEAL,
                       activeforeground="white", selectcolor=INK, relief="flat", borderwidth=0,
                       activeborderwidth=0)
        self.lang_sel = {}
        for code in self.cfg["known_languages"]:
            var = tk.BooleanVar(value=code in self.cfg["languages"])
            self.lang_sel[code] = var
            menu.add_checkbutton(label=i18n.lang_name_ui(self.ui, code), variable=var,
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
        sel = [i18n.lang_name_ui(self.ui, c) for c, v in self.lang_sel.items() if v.get()]
        self.lang_btn.configure(text=", ".join(sel) if sel else "—")

    def lang_picker(self):
        """Scrollbare Checkbox-Liste aller Sprachen mit Filterfeld; angehakt = im Dropdown angeboten."""
        win = tk.Toplevel(self); win.title(self.t("pick_langs_title")); win.grab_set()
        win.configure(bg=BG); win.geometry("380x540"); win.resizable(False, True)
        set_icon(win); style_titlebar(win)
        outer = ttk.Frame(win, padding=12, style="Bg.TFrame"); outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD); card.pack(fill="both", expand=True)
        ttk.Label(card, text=self.t("pick_hint"), wraplength=330).pack(anchor="w", padx=10, pady=(10, 6))

        frow = ttk.Frame(card); frow.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(frow, text="🔍", bg=CARD, fg=LIGHT).pack(side="left", padx=(0, 6))
        filter_var = tk.StringVar()
        ttk.Entry(frow, textvariable=filter_var).pack(side="left", fill="x", expand=True)

        lf = ttk.Frame(card); lf.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(lf, bg=FIELD, highlightthickness=1, highlightbackground=CARD_EDGE)
        sb = ttk.Scrollbar(lf, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=FIELD)
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
                uiname = i18n.lang_name_ui(self.ui, code)
                if q and q not in native.casefold() and q not in english.casefold() \
                        and q not in uiname.casefold() and q not in code.casefold():
                    continue
                # Name in der App-Sprache, dahinter die Eigenschreibweise zum Wiedererkennen
                label = uiname if uiname.casefold() == native.casefold() else f"{uiname}   ·   {native}"
                tk.Checkbutton(inner, text=label, variable=vars_[code], bg=FIELD, fg=INK,
                               activebackground=FIELD, activeforeground=INK, anchor="w", selectcolor=FIELD,
                               highlightthickness=0,
                               font=(UI_FONT, 10), padx=8).pack(fill="x")
            canvas.yview_moveto(0)

        filter_var.trace_add("write", refill)
        refill()

        def close():
            win.unbind_all("<MouseWheel>")
            win.destroy()

        def ok():
            checked = [c for c in entries if vars_[c].get()]
            if not checked:
                self._dialog(win, self.t("warn_lang"))
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
        self._setup_columns(langs)
        self.table.delete(*self.table.get_children())
        self._row_items = {}
        self.start_btn.state(["disabled"])
        self.cancel.clear()
        self._log_sep(folder)
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
            self._log_raw("✖  " + sc.error, ("fail",))
            self.status.config(text=self.t("error")); return
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

    # ---- Tabelle -------------------------------------------------------------
    _SYM = {"present": "✔", "embedded": "✔", "found": "✔", "synced": "✔", "suspect": "⚠", "unsynced": "⚠",
            "none": "✖", "missing": "✖", "pending": "…"}

    def _setup_columns(self, langs: list[str]):
        """Spalten neu aufbauen, wenn sich die Sprachauswahl geändert hat."""
        if langs == self._table_langs and len(self.table["columns"]) > 1:
            return
        self._table_langs = list(langs)
        cols = ["file", "rec"] + [f"l_{l}" for l in langs] + ["imdb"]
        self.table.configure(columns=cols)
        self.table.heading("file", text=self.t("col_file"), anchor="w")
        self.table.column("file", width=220, minwidth=80, stretch=True, anchor="w")
        self.table.heading("rec", text=self.t("col_rec"), anchor="w")
        self.table.column("rec", width=170, minwidth=80, stretch=True, anchor="w")
        f9 = tkfont.Font(font=(UI_FONT, 9))
        lang_w = max(f9.measure(f"{sym} {self.t('s_' + st)}") for st, sym in self._SYM.items() if st != "pending") + 28
        for l in langs:
            self.table.heading(f"l_{l}", text=i18n.lang_name_ui(self.ui, l), anchor="w")
            self.table.column(f"l_{l}", width=max(115, lang_w), minwidth=70, stretch=False, anchor="w")
        self.table.heading("imdb", text=self.t("col_imdb"), anchor="w")
        self.table.column("imdb", width=175, minwidth=120, stretch=False, anchor="w")

    def _row_values(self, it: core.Item) -> tuple[list, str]:
        vals = [it.video.name, it.recognized or ("—" if it.langs else "")]
        for l in self._table_langs:
            st = it.status.get(l)
            vals.append("…" if st == "pending" else (f"{self._SYM.get(st, '')} {self.t('s_' + st)}" if st else ""))
        vals.append(it.imdb_id or "")            # Buttons liegen als Overlay über dieser Zelle
        if not it.langs:
            tag = "present"
        elif not any(it.status.get(l) in ("found", "synced", "suspect", "unsynced") for l in it.langs):
            tag = "none"
        else:
            tag = "ok"
        return vals, tag

    def _toggle_present(self):
        self.cfg["show_present"] = bool(self.show_present.get())
        config.save(self.cfg)
        self._fill_table()

    def _fill_table(self):
        self.table.delete(*self.table.get_children())
        self._row_items = {}
        if not self.scan:
            return
        items = self.scan.items if self.show_present.get() else [it for it in self.scan.items if it.langs]
        for i, it in enumerate(items):
            vals, tag = self._row_values(it)
            iid = self.table.insert("", "end", values=vals, tags=(tag, "odd" if i % 2 else "even"))
            self._row_items[iid] = it
        self.after_idle(self._place_imdb_buttons)

    def _refresh_rows(self, items: list):
        for iid, it in self._row_items.items():
            if it in items:
                vals, tag = self._row_values(it)
                zebra = [t for t in self.table.item(iid, "tags") if t in ("odd", "even")]
                self.table.item(iid, values=vals, tags=(tag, *zebra))
        self.after_idle(self._place_imdb_buttons)

    def _place_imdb_buttons(self):
        """Echte Buttons in der IMDb-Spalte: SET wenn leer, EDIT + ✕ wenn eine ID steht. Als Overlay über
        den sichtbaren Zellen platziert; nicht sichtbare Zeilen bekommen keinen Button."""
        if not self.table.winfo_exists():
            return
        for iid, (b1, b2) in list(self._imdb_btns.items()):
            if iid not in self._row_items:
                b1.destroy(); b2.destroy(); del self._imdb_btns[iid]
        busy = bool(self.worker and self.worker.is_alive())
        for iid, it in self._row_items.items():
            bbox = self.table.bbox(iid, "imdb") if it.langs else None
            if iid not in self._imdb_btns:
                b1 = ttk.Button(self.table, style="Cell.TButton", command=lambda it=it: self._imdb_popup(it))
                b2 = ttk.Button(self.table, text="✕", style="Cell.TButton", width=2,
                                command=lambda it=it: self._clear_imdb(it))
                self._tooltip(b1, lambda it=it: self.t("tt_imdb_edit" if it.imdb_id else "tt_imdb_set"))
                self._tooltip(b2, self.t("tt_imdb_clear"))
                self._imdb_btns[iid] = (b1, b2)
            b1, b2 = self._imdb_btns[iid]
            if not bbox:
                b1.place_forget(); b2.place_forget(); continue
            x, y, w, h = bbox
            state = ["disabled"] if busy else ["!disabled"]
            b1.state(state); b2.state(state)
            if it.imdb_id:
                b1.configure(text=self.t("btn_edit"), width=5)
                b2.place(x=x + w - 26, y=y + 1, height=h - 2)
                b1.place(x=x + w - 26 - 48, y=y + 1, height=h - 2)
            else:
                b1.configure(text=self.t("btn_set"), width=5)
                b2.place_forget()
                b1.place(x=x + 3, y=y + 1, height=h - 2)

    def _clear_imdb(self, it: core.Item):
        if self.worker and self.worker.is_alive():
            return
        self._rescan([it], None)

    def _on_table_click(self, event):
        return

    def _on_table_motion(self, event):
        """Abgeschnittene Zellinhalte als Tooltip zeigen."""
        from tkinter import font as tkfont
        iid, colid = self.table.identify_row(event.y), self.table.identify_column(event.x)
        in_cell = bool(iid and colid) and self.table.identify("region", event.x, event.y) == "cell"
        colname = self.table.column(colid, "id") if colid else ""
        if (iid, colid) == self._tip_cell:
            return
        self._tip_hide()
        self._tip_cell = (iid, colid)
        if not in_cell:
            return
        text = str(self.table.set(iid, colname))
        if colname == "imdb" or not text or \
                tkfont.Font(font=(UI_FONT, 9)).measure(text) + 12 <= int(self.table.column(colid, "width")):
            return
        self._tip = tk.Toplevel(self)
        self._tip.wm_overrideredirect(True)
        tk.Label(self._tip, text=text, bg=TIP_BG, fg=INK, relief="solid", borderwidth=1,
                 font=(UI_FONT, 9), padx=6, pady=3).pack()
        self._tip.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 18}")

    def _tip_hide(self, *_):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
        self._tip_cell = None

    def _tooltip(self, widget, text) -> None:
        """Hinweis beim Verweilen auf einem Widget; text darf auch eine Funktion sein, die den Text liefert."""
        def show(event):
            self._tip_hide()
            s = text() if callable(text) else text
            if not s:
                return
            self._tip = tk.Toplevel(self)
            self._tip.wm_overrideredirect(True)
            tk.Label(self._tip, text=s, bg=TIP_BG, fg=INK, relief="solid", borderwidth=1,
                     font=(UI_FONT, 9), padx=6, pady=3).pack()
            self._tip.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 18}")
        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", self._tip_hide, add="+")
        widget.bind("<ButtonPress>", self._tip_hide, add="+")

    def _imdb_popup(self, it: core.Item):
        """IMDb-ID für genau diese Zeile; bei Serien optional für alle Folgen derselben Serie."""
        win = tk.Toplevel(self); win.title("IMDb"); win.resizable(False, False); win.grab_set()
        win.configure(bg=CARD)
        set_icon(win); style_titlebar(win)
        f = ttk.Frame(win, padding=14); f.pack(fill="both", expand=True)
        ttk.Label(f, text=it.video.name, font=(UI_FONT, 9, "bold"), wraplength=400).pack(anchor="w")
        ttk.Label(f, text=self.t("imdb_popup_hint"), wraplength=400).pack(anchor="w", pady=(4, 8))
        var = tk.StringVar(value=it.imdb_id or "")
        e = ttk.Entry(f, textvariable=var, width=46)
        e.pack(anchor="w"); e.focus_set(); e.select_range(0, "end")
        show = getattr(it.v, "series", None) if it.v is not None else None
        siblings = [o for o in (self.scan.items if self.scan else []) if o is not it and o.langs
                    and o.v is not None and getattr(o.v, "series", None) == show] if show else []
        all_var = tk.BooleanVar(value=bool(siblings))
        if siblings:
            tk.Checkbutton(f, text=self.t("imdb_all_eps", n=len(siblings), show=show), variable=all_var,
                           bg=CARD, fg=LIGHT, activebackground=CARD, activeforeground=LIGHT,
                           selectcolor=CHECK_BG, highlightthickness=0, wraplength=400,
                           justify="left").pack(anchor="w", pady=(8, 0))

        def ok(*_):
            raw = var.get().strip()
            m = IMDB_RE.search(raw)
            if not m:
                self._dialog(win, self.t("c_imdb_invalid", val=raw)); return
            items = [it] + (siblings if all_var.get() else [])
            win.destroy()
            self._rescan(items, m.group(0))

        e.bind("<Return>", ok)
        b = ttk.Frame(f); b.pack(pady=(12, 0))
        ttk.Button(b, text=self.t("st_save"), command=ok, style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=win.destroy).pack(side="left", padx=4)

    def _rescan(self, items: list, ttid: str | None):
        self.cancel.clear()
        ui = self.ui
        # sofort sichtbar: ID in den Zeilen, Sprachzellen auf „…", Statuszeile + pulsierender Balken
        for it in items:
            it.imdb_id, it.imdb_source = (ttid, "manual") if ttid else (None, "")
            for l in it.langs:
                it.status[l] = "pending"
        self._refresh_rows(items)
        self.status.config(text=self.t("rescanning"))
        self.bar.pulse()
        self.start_btn.state(["disabled"])

        def work():
            core.rescan(items, ttid, self.cfg, log=lambda s: self.q.put(("log", s)), cancel=self.cancel,
                        tr=lambda key, **kw: i18n.tr(ui, key, **kw),
                        on_item=lambda it: self.q.put(("rescan_item", it)))
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
            self.folder_var.set(os.path.normpath(d))
            self._trigger_scan()

    def on_drop(self, event):
        paths = list(self.tk.splitlist(event.data))
        subs = [p for p in paths if os.path.splitext(p)[1].lower() in core.SUB_EXT]
        vids = [p for p in paths if os.path.splitext(p)[1].lower() in core.video_exts(self.cfg)]
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
            vids = [v for v in core.find_videos(folder, int(self.cfg.get("min_size_mb", 50)), core.video_exts(self.cfg))
                    if str(v.parent) == folder]
            if len(vids) == 1:
                video = str(vids[0])
            else:
                exts = " ".join(f"*{e}" for e in sorted(core.video_exts(self.cfg)))
                video = filedialog.askopenfilename(title=self.t("pick_video"),
                                                   filetypes=[("Video", exts)], initialdir=folder)
                if not video:
                    return
                video = os.path.normpath(video)
        m = re.search(r"\.([a-z]{2}(?:-[a-z]{2})?)\.(?:srt|ass|ssa)$", os.path.basename(sub), re.IGNORECASE)
        # Regionalcodes normalisieren: pt-br → pt-BR
        lang = (m.group(1)[:2].lower() + m.group(1)[2:].upper()) if m \
            else next((c for c, v in self.lang_sel.items() if v.get()), None)
        if not lang:
            self._dialog(self, self.t("warn_lang")); return
        self.folder_var.set(os.path.dirname(video))
        self.cancel.clear()
        self._log_sep(os.path.basename(sub))
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
        self.after_idle(self._place_imdb_buttons)     # Zell-Buttons während der Arbeit sperren
        if on:
            self.start_btn.state(["!disabled"])   # als Abbrechen immer erreichbar
            self.after(100, self._poll)
            self.after(90, self._animate)

    def start(self):
        if self.worker and self.worker.is_alive():
            self.cancel.set(); self.status.config(text=self.t("cancelling")); return
        if not self.scan or not self.scan.runnable:
            self._trigger_scan(); return
        self.cancel.clear()
        self._log_sep(self.t("start"))
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
                elif item[0] == "rescan_item":
                    self._refresh_rows([item[1]])
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
            self._log_raw("✖  " + res.error, ("fail",))
            self.status.config(text=self.t("error")); return
        self.bar.set(1.0, "100 %")
        if self.scan:
            self._refresh_rows(self.scan.items)
            self.start_btn.state(["disabled"])   # erledigt — neuer Lauf erst nach neuem Vorlauf
        if not any((res.synced, res.unsynced, res.suspect, res.missing, res.noaccess, res.cancelled)):
            self.status.config(text=self.t("res_all_have", n=res.skipped))
            return
        parts = [self.t("p_synced", n=len(res.synced))]
        if res.skipped: parts.append(self.t("p_existing", n=res.skipped))
        if res.suspect: parts.append(self.t("p_suspect", n=len(res.suspect)))
        if res.unsynced: parts.append(self.t("p_unsynced", n=len(res.unsynced)))
        if res.missing: parts.append(self.t("p_missing", n=len(res.missing)))
        if res.noaccess: parts.append(self.t("p_noaccess", n=len(res.noaccess)))
        ok = not res.missing and not res.unsynced and not res.suspect and not res.noaccess and not res.cancelled
        head = self.t("res_cancelled") if res.cancelled else self.t("res_done")
        self.status.config(text=("✔  " if ok else "⚠  ") + head + ", ".join(parts))
        self._log_summary(res)

    def _log_summary(self, res: core.Result):
        """Abschluss-Block im Log: eine farbige Zeile je Video und Sprache, danach die Tipps."""
        self._log_raw("\n" + self.t("sum_head"), ("head",))
        for m in res.synced:
            self._log_raw(f"  ✔ {m}  —  {self.t('s_synced')}", ("ok",))
        for m in res.suspect:
            self._log_raw(f"  ⚠ {m}  —  {self.t('s_suspect')}", ("warn",))
        for m in res.unsynced:
            self._log_raw(f"  ⚠ {m}  —  {self.t('s_unsynced')}", ("warn",))
        for m in res.missing:
            self._log_raw(f"  ✖ {m}  —  {self.t('s_missing')}", ("fail",))
        for d in res.noaccess:
            self._log_raw(f"  ✖ {d}  —  {self.t('p_noaccess', n='')}".replace("  —   ", "  —  "), ("fail",))
        # Tipps mit Abstand und als Hinweis markiert — nicht als Begründung der Zeilen darüber.
        # Der Erkennungs-Tipp nur, wenn ein Video in KEINER Sprache etwas hatte und keine ID gesetzt ist.
        unrecognized = [it for it in (self.scan.items if self.scan else []) if it.langs and not it.imdb_id
                        and not any(it.status.get(l) in ("synced", "suspect", "unsynced", "found") for l in it.langs)]
        tips = []
        if unrecognized:
            tips.append((self.t("missing_hint"), ("sep",)))
        if res.suspect:
            tips.append((self.t("suspect_hint"), ("warn",)))
        if res.noaccess:
            tips.append((self.t("noaccess_hint"), ("sep",)))
        if tips:
            self._log_raw("", ())
            for text, tags in tips:
                self._log_raw("ℹ " + text, tags)

    # ---- Einstellungen ------------------------------------------------------
    def settings(self):
        win = tk.Toplevel(self); win.title(self.t("st_title")); win.resizable(False, False); win.grab_set()
        win.configure(bg=BG)
        set_icon(win); style_titlebar(win)
        outer = ttk.Frame(win, padding=14, style="Bg.TFrame"); outer.pack(fill="both", expand=True)

        def card(heading: str) -> tk.Frame:
            f = tk.Frame(outer, bg=CARD)
            f.pack(fill="x", pady=(0, 14))
            tk.Label(f, text=heading, bg=CARD, fg=TITLE, font=(UI_FONT, 10, "bold"))\
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
        reg = tk.Label(g, text=LINK_ICON + self.t("st_register"), fg=LINK, bg=CARD,
                       cursor="hand2", font=(UI_FONT, 9, "underline"))
        reg.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        reg.bind("<Button-1>", lambda e: webbrowser.open(OPENSUBTITLES_URL))
        pw_note = {"dpapi": "st_pw_note", "keyring": "st_pw_note_keyring"}.get(config.secret_backend(), "st_pw_note_file")
        ttk.Label(g, text=self.t(pw_note), foreground=GREY, wraplength=360,
                  font=(UI_FONT, 8)).grid(row=3, column=0, columnspan=2, sticky="w")

        # -- Programm: Verhalten, Updates, Version
        f3 = card(self.t("sec_program"))

        def check(var_name: str, key: str, pady) -> tk.BooleanVar:
            var = tk.BooleanVar(value=bool(self.cfg.get(var_name, True)))
            tk.Checkbutton(f3, text=self.t(key), variable=var, bg=CARD, fg=LIGHT, activebackground=CARD,
                           activeforeground=LIGHT, selectcolor=CHECK_BG, highlightthickness=0, font=(UI_FONT, 9))\
                .pack(anchor="w", padx=6, pady=pady)
            return var
        emb_var = check("embedded_counts", "st_embedded", (0, 2))
        upd_var = check("check_updates_on_start", "st_upd_on_start", (0, 6))
        g3 = ttk.Frame(f3); g3.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(g3, text=self.t("st_theme")).grid(row=0, column=0, sticky="w", pady=3)
        theme_names = {k: self.t(f"theme_{k}") for k in THEMES}
        theme_box = ttk.Combobox(g3, state="readonly", width=12, values=list(theme_names.values()))
        theme_box.set(theme_names.get(self.cfg.get("theme", "green"), theme_names["green"]))
        theme_box.grid(row=0, column=1, sticky="w", pady=3, padx=(8, 0))
        ttk.Label(g3, text=self.t("st_extra_ext")).grid(row=1, column=0, sticky="w", pady=3)
        ext_var = tk.StringVar(value=str(self.cfg.get("video_extensions_extra", "")))
        ttk.Button(g3, text=self.t("st_ext_edit"), style="Square.TButton",
                   command=lambda: self._ext_dialog(win, ext_var)).grid(row=1, column=1, sticky="w", pady=3, padx=(8, 0))
        ttk.Label(g3, text=self.t("st_log_max")).grid(row=3, column=0, sticky="w", pady=(8, 3))
        log_var = tk.StringVar(value=str(self.cfg.get("log_max_mb", 20)))
        lrow = ttk.Frame(g3); lrow.grid(row=3, column=1, sticky="w", pady=(8, 3), padx=(8, 0))
        ttk.Spinbox(lrow, from_=1, to=500, textvariable=log_var, width=5).pack(side="left")
        ttk.Button(lrow, text=self.t("st_open_log"), style="Square.TButton",
                   command=logfile.open_folder).pack(side="left", padx=(10, 0))
        urow = ttk.Frame(f3); urow.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(urow, text=self.t("st_check_updates"), style="Square.TButton",
                   command=lambda: self.check_updates(win)).pack(side="left")
        tk.Label(urow, text=f"SuperSubber {__version__}", bg=CARD, fg=LIGHT, font=(UI_FONT, 9))\
            .pack(side="left", padx=(12, 0))

        def ok():
            self.cfg["opensubtitles_user"] = user.get().strip()
            self.cfg["opensubtitles_password"] = config.encrypt(pw.get())
            self.cfg["ui_language"] = next((c for c, n in i18n.UI_LANGS.items() if n == ui_box.get()), "en")
            self.cfg["check_updates_on_start"] = bool(upd_var.get())
            self.cfg["embedded_counts"] = bool(emb_var.get())
            self.cfg["video_extensions_extra"] = ext_var.get().strip()
            try:
                self.cfg["log_max_mb"] = max(1, min(500, int(float(log_var.get().replace(",", ".")))))
            except ValueError:
                pass
            self.cfg["theme"] = next((k for k, n in theme_names.items() if n == theme_box.get()), "green")
            config.save(self.cfg)
            logfile.setup(self.cfg["log_max_mb"])
            win.destroy()
            apply_theme(self.cfg["theme"])
            dump = self._log_dump()
            self._style()
            self._build()
            self._log_restore(dump)
            style_titlebar(self)
        b = ttk.Frame(outer, style="Bg.TFrame"); b.pack(pady=(2, 0))
        ttk.Button(b, text=self.t("st_save"), command=ok, style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=win.destroy).pack(side="left", padx=4)
        foot = tk.Label(outer, text="github.com/Cosmopolyte/supersubber", bg=BG, fg=GREY, cursor="hand2",
                        font=(UI_FONT, 8))
        foot.pack(pady=(12, 0))
        foot.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/Cosmopolyte/supersubber"))

    def _ext_dialog(self, parent, ext_var: tk.StringVar) -> None:
        """Video-Endungen als Liste: die Standard-Endungen fest und grau, eigene hinzufügen und entfernen.
        Ergebnis landet als „hevc, vp9" in ext_var."""
        win = tk.Toplevel(parent); win.title(self.t("st_ext_title")); win.resizable(False, False)
        win.configure(bg=BG); win.transient(parent); win.grab_set()
        set_icon(win); style_titlebar(win)
        outer = ttk.Frame(win, padding=14, style="Bg.TFrame"); outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD); card.pack(fill="both", expand=True)
        ttk.Label(card, text=self.t("st_ext_hint"), wraplength=330, foreground=GREY,
                  font=(UI_FONT, 8)).pack(anchor="w", padx=10, pady=(10, 6))
        defaults = sorted(e.lstrip(".") for e in core.VIDEO_EXT)
        extras = sorted(e.lstrip(".") for e in core.video_exts({"video_extensions_extra": ext_var.get()}) - core.VIDEO_EXT)
        lf = ttk.Frame(card); lf.pack(fill="x", padx=10)
        lb = tk.Listbox(lf, height=10, bg=FIELD, fg=INK, selectbackground=TEAL, selectforeground="white",
                        highlightthickness=1, highlightbackground=CARD_EDGE, relief="flat", font=(UI_FONT, 10),
                        activestyle="none", exportselection=False)
        lsb = ttk.Scrollbar(lf, orient="vertical", command=lb.yview); lb.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y"); lb.pack(side="left", fill="x", expand=True)

        def refill():
            lb.delete(0, "end")
            for e in defaults:
                lb.insert("end", e); lb.itemconfig("end", fg=GREY)
            for e in extras:
                lb.insert("end", e)
        refill()
        arow = ttk.Frame(card); arow.pack(fill="x", padx=10, pady=(8, 10))
        new_var = tk.StringVar()
        ent = ttk.Entry(arow, textvariable=new_var, width=12); ent.pack(side="left")

        def add(*_):
            e = new_var.get().strip().lstrip(".").lower()
            if re.fullmatch(r"[a-z0-9]{1,8}", e) and e not in defaults and e not in extras:
                extras.append(e); extras.sort(); refill()
            new_var.set("")

        def remove():
            sel = lb.curselection()
            if not sel:
                return
            e = lb.get(sel[0])
            if e in extras:
                extras.remove(e); refill()
        ent.bind("<Return>", add)
        ttk.Button(arow, text=self.t("st_ext_add"), style="Square.TButton", command=add).pack(side="left", padx=(6, 0))
        ttk.Button(arow, text=self.t("st_ext_remove"), style="Square.TButton", command=remove).pack(side="left", padx=(6, 0))

        def ok():
            ext_var.set(", ".join(extras)); win.destroy()
        b = ttk.Frame(outer, style="Bg.TFrame"); b.pack(pady=(12, 0))
        ttk.Button(b, text=self.t("btn_ok"), style="Accent.TButton", command=ok).pack(side="left", padx=4)
        ttk.Button(b, text=self.t("st_cancel"), command=win.destroy).pack(side="left", padx=4)
        win.update_idletasks()
        win.geometry(f"+{parent.winfo_rootx() + 30}+{parent.winfo_rooty() + 60}")
        ent.focus_set()

    def check_updates(self, parent=None, silent: bool = False):
        """Neuestes GitHub-Release abfragen und mit der eigenen Version vergleichen. Kein Auto-Update.
        silent = Start-Prüfung: nur melden, wenn es etwas Neueres gibt; „aktuell" und Fehler bleiben stumm."""
        import json
        import urllib.request
        url = "https://api.github.com/repos/Cosmopolyte/supersubber/releases/latest"

        def vt(v: str) -> tuple:
            return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": f"supersubber/{__version__}",
                                                           "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.load(r)
                tag = str(data.get("tag_name", "")).lstrip("v")
                page = data.get("html_url") or "https://github.com/Cosmopolyte/supersubber/releases"
                self.after(0, lambda: done(tag, page, None))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: done("", "", f"{type(e).__name__}: {e}"))

        def done(tag, page, err):
            if err:
                if not silent:
                    self._dialog(parent, self.t("upd_err", err=err))
                return
            if tag and vt(tag) > vt(__version__):
                if self._dialog(parent, self.t("upd_new", new=tag, cur=__version__), yes_no=True):
                    webbrowser.open(page)
            elif not silent:
                self._dialog(parent, self.t("upd_latest", cur=__version__))

        threading.Thread(target=work, daemon=True).start()

    # ---- Log ----------------------------------------------------------------
    def _log_raw(self, s: str, tags: tuple[str, ...] = ()):
        if s.strip():
            logfile.log.info(s.strip())
        self.log.config(state="normal"); self.log.insert("end", s + "\n", tags); self.log.see("end"); self.log.config(state="disabled")

    def _log_sep(self, title: str = ""):
        """Trennlinie zwischen den Phasen — das Log wird nie automatisch geleert."""
        if self.log.index("end-1c") != "1.0":
            self._log_raw("\n" + "─" * 60 + (f"  {title}" if title else ""), ("sep",))

    def save_log(self):
        """Verlauf (Fenster-Log) in die Zwischenablage — fürs Forum oder eine Mail. Die Logdatei bleibt davon unberührt."""
        self.clipboard_clear()
        self.clipboard_append(self.log.get("1.0", "end-1c"))
        prev = self.status.cget("text")
        self.status.config(text=self.t("copied"))
        self.after(2500, lambda: self.status.config(text=prev) if self.status.cget("text") == self.t("copied") else None)

    def _log_dump(self) -> list:
        """Verlauf mit Formatierung sichern — _build() baut das Text-Widget neu."""
        try:
            return self.log.dump("1.0", "end-1c", tag=True, text=True)
        except (tk.TclError, AttributeError):
            return []

    def _log_restore(self, dump: list) -> None:
        if not dump:
            return
        self.log.config(state="normal")
        active: list[str] = []
        for kind, value, _index in dump:
            if kind == "tagon":
                active.append(value)
            elif kind == "tagoff" and value in active:
                active.remove(value)
            elif kind == "text":
                self.log.insert("end", value, tuple(active))
        self.log.see("end")
        self.log.config(state="disabled")

    def _dialog(self, parent, text: str, yes_no: bool = False) -> bool:
        """Hinweis im eigenen Stil statt messagebox — die passt farblich in kein Schema. Gibt True bei OK/Ja."""
        win = tk.Toplevel(parent or self); win.title("SuperSubber"); win.resizable(False, False)
        win.configure(bg=BG); win.transient(parent or self); win.grab_set()
        set_icon(win); style_titlebar(win)
        outer = ttk.Frame(win, padding=14, style="Bg.TFrame"); outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD); card.pack(fill="both", expand=True)
        tk.Label(card, text=text, bg=CARD, fg=LIGHT, font=(UI_FONT, 10), wraplength=380, justify="left")\
            .pack(padx=16, pady=14)
        result = {"ok": False}

        def close(ok: bool):
            result["ok"] = ok
            win.destroy()
        b = ttk.Frame(outer, style="Bg.TFrame"); b.pack(pady=(12, 0))
        if yes_no:
            ttk.Button(b, text=self.t("btn_yes"), style="Accent.TButton", command=lambda: close(True)).pack(side="left", padx=4)
            ttk.Button(b, text=self.t("btn_no"), command=lambda: close(False)).pack(side="left", padx=4)
        else:
            ttk.Button(b, text=self.t("btn_ok"), style="Accent.TButton", command=lambda: close(True)).pack()
        win.bind("<Return>", lambda e: close(True)); win.bind("<Escape>", lambda e: close(False))
        win.update_idletasks()
        px, py = (parent or self).winfo_rootx(), (parent or self).winfo_rooty()
        pw, ph = (parent or self).winfo_width(), (parent or self).winfo_height()
        win.geometry(f"+{px + max(0, (pw - win.winfo_width()) // 2)}+{py + max(0, (ph - win.winfo_height()) // 3)}")
        win.wait_window()
        return result["ok"]

    def _log(self, s: str):
        logfile.log.info(s.strip())
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
    """supersubber [Ordner] [--lang ru,de]  — mit Ordner wird sofort gestartet."""
    args = sys.argv[1:]
    langs = None
    if "--lang" in args:
        i = args.index("--lang")
        langs = [x.strip()[:2].lower() + x.strip()[2:].upper() for x in args[i + 1].split(",") if x.strip()] \
            if i + 1 < len(args) else None
        del args[i:i + 2]
    folder = args[0] if args else None
    App(folder, langs).mainloop()
