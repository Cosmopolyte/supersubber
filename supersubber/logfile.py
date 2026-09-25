"""Logdatei im Config-Ordner: rotierend, Obergrenze aus den Settings. Enthält alles, was das Fenster-Log zeigt,
plus Details, die dort nur stören würden: Kandidaten je Provider mit Score, gewählter Release-Name, IMDb-Abfragen,
alass-Ausgabe, unbehandelte Ausnahmen. Für Fehlermeldungen gilt damit: „schick das Log"."""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import threading

from . import __version__, config

LOG_FILE = os.path.join(config.CONFIG_DIR, "supersubber.log")
log = logging.getLogger("supersubber")
_QUIET = ("urllib3", "requests", "charset_normalizer", "chardet", "rebulk", "guessit", "dogpile", "PIL",
          "subliminal.score")   # score-Details stehen kompakter in den eigenen „cand"-Zeilen


def setup(max_mb: float) -> None:
    """Handler neu setzen (auch nach Änderung der Obergrenze). Zwei Dateien à max/2 → Gesamtgröße ≤ max."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_supersubber", False):
            root.removeHandler(h)
            h.close()
    try:
        os.makedirs(config.CONFIG_DIR, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=max(65536, int(float(max_mb) * 1024 * 1024 / 2)), backupCount=1, encoding="utf-8")
    except OSError:
        return
    handler._supersubber = True  # type: ignore[attr-defined]
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname).1s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)               # subliminal & Co. auf INFO: Provider-Aufrufe, Treffer, Downloads
    log.setLevel(logging.DEBUG)               # eigene Details
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    def excepthook(exc_type, exc, tb):
        log.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    def thread_hook(args):
        log.error("Unhandled exception in thread %s", args.thread.name if args.thread else "?",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    log.info("SuperSubber %s start on %s %s, Python %s, config %s",
             __version__, platform.system(), platform.release(), platform.python_version(), config.CONFIG_DIR)


def open_folder() -> None:
    """Config-Ordner im Dateimanager öffnen — dort liegt die Logdatei."""
    import subprocess
    d = config.CONFIG_DIR
    os.makedirs(d, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(d)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", d])
    else:
        subprocess.Popen(["xdg-open", d])
