"""Konfiguration: Windows %APPDATA%\\supersubber\\config.json, Linux $XDG_CONFIG_HOME/supersubber bzw. ~/.config/supersubber.
Passwort: Windows per DPAPI (nur dieser User/Rechner); Linux im Schlüsselbund (keyring: Secret Service/KWallet),
ohne Schlüsselbund als Datei `secret` mit Rechten 0600 — config.json trägt dann nur einen Marker."""
import base64
import json
import os
import sys

WIN = sys.platform == "win32"
if WIN:
    import ctypes
    import ctypes.wintypes as wt

APP_NAME = "supersubber"
if WIN:
    _BASE = os.environ.get("APPDATA", os.path.expanduser("~"))
else:
    _BASE = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
CONFIG_DIR = os.path.join(_BASE, APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SECRET_FILE = os.path.join(CONFIG_DIR, "secret")          # Linux-Rückfall ohne Schlüsselbund
_OLD_CONFIG = os.path.join(_BASE, "subsync", "config.json")   # Vorgängername der App

DEFAULTS = {
    "languages": ["en"],                 # vorausgewählte Sprachen; erster Start: Systemsprache
    "known_languages": ["en", "fr", "es", "de", "pt", "ru", "uk", "zh", "ko", "ja"],  # Dropdown-Angebot
    "opensubtitles_user": "",
    "opensubtitles_password": "",        # Windows: DPAPI-Blob base64; Linux: Marker "keyring:" oder "file:"
    "min_size_mb": 50,
    "ui_language": "en",                 # Default Englisch; beim ersten Start Systemsprache erkannt
    "window": "",                        # letzte Fenstergeometrie „WxH+X+Y" (leer = nach Bildschirm berechnet)
    "check_updates_on_start": True,      # GitHub-Release-Abfrage beim Start, Hinweis nur bei neuerer Version
    "embedded_counts": True,             # eingebettete Untertitelspuren gelten als vorhanden
    "video_extensions_extra": "",        # zusätzliche Video-Endungen, z. B. „hevc, vp9"
    "log_max_mb": 20,                    # Obergrenze der Logdatei im Config-Ordner
    "theme": "green",                    # Farbschema: green | light | dark
    "show_present": False,               # Tabelle: auch Videos zeigen, die alle Sprachen schon haben
}

# Windows-Primary-LANGID → ISO-Kürzel, nur für die Default-known_languages relevant
_LANGID = {0x09: "en", 0x0c: "fr", 0x0a: "es", 0x07: "de", 0x16: "pt",
           0x19: "ru", 0x22: "uk", 0x04: "zh", 0x12: "ko", 0x11: "ja"}


def _system_language() -> str:
    """Primäre Systemsprache als ISO-639-1: Windows-Anzeigesprache, sonst LC_ALL/LC_MESSAGES/LANG. Unbekannt → en."""
    if WIN:
        try:
            return _LANGID.get(ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, "en")
        except Exception:  # noqa: BLE001
            return "en"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        val = os.environ.get(var, "")
        if val and val not in ("C", "POSIX"):
            code = val.split(":")[0].split(".")[0].split("@")[0].split("_")[0].lower()
            if len(code) == 2:
                return code
    return "en"


def _detect_ui_language() -> str:
    """Systemsprache → de/ru wenn passend, sonst en."""
    code = _system_language()
    return code if code in ("de", "ru") else "en"


def _detect_sub_language() -> str:
    """Systemsprache → vorausgewählte Untertitel-Sprache (nur erster Start)."""
    code = _system_language()
    return code if code in DEFAULTS["known_languages"] else "en"


# ---- Passwort: Windows DPAPI ---------------------------------------------------------------------
if WIN:
    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    inp = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _DATA_BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI-Fehler")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


# ---- Passwort: Linux Schlüsselbund oder Datei --------------------------------------------------
_KEYRING_MARK = "keyring:"
_FILE_MARK = "file:"
_SERVICE, _ACCOUNT = APP_NAME, "opensubtitles"
_kr_cache: list = []      # [Modul oder None], einmal pro Prozess ermittelt


def _keyring():
    """keyring-Modul, wenn ein echter Schlüsselbund erreichbar ist (Secret Service, KWallet), sonst None."""
    if not _kr_cache:
        mod = None
        try:
            import keyring
            from keyring.backends.fail import Keyring as _Fail
            if not isinstance(keyring.get_keyring(), _Fail):
                mod = keyring
        except Exception:  # noqa: BLE001 — kein keyring installiert, kein D-Bus, kein Daemon
            mod = None
        _kr_cache.append(mod)
    return _kr_cache[0]


def secret_backend() -> str:
    """Wie das Passwort abgelegt wird: dpapi (Windows), keyring oder file (Linux) — für den Hinweis im Dialog."""
    if WIN:
        return "dpapi"
    return "keyring" if _keyring() else "file"


def _forget_linux() -> None:
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(_SERVICE, _ACCOUNT)
        except Exception:  # noqa: BLE001 — kein Eintrag vorhanden
            pass
    try:
        os.remove(SECRET_FILE)
    except OSError:
        pass


def encrypt(text: str) -> str:
    """Passwort sicher ablegen; Rückgabe = Wert für config.json (DPAPI-Blob oder Marker)."""
    if WIN:
        return base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode("ascii") if text else ""
    if not text:
        _forget_linux()
        return ""
    kr = _keyring()
    if kr:
        try:
            kr.set_password(_SERVICE, _ACCOUNT, text)
            try:
                os.remove(SECRET_FILE)
            except OSError:
                pass
            return _KEYRING_MARK
        except Exception:  # noqa: BLE001 — Schlüsselbund gesperrt oder abgelehnt → Datei
            pass
    os.makedirs(CONFIG_DIR, exist_ok=True)
    fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(SECRET_FILE, 0o600)
    return _FILE_MARK


def decrypt(blob: str) -> str:
    if not blob:
        return ""
    if WIN:
        try:
            return _dpapi(base64.b64decode(blob), False).decode("utf-8")
        except Exception:  # noqa: BLE001
            return ""
    if blob == _KEYRING_MARK:
        kr = _keyring()
        try:
            return (kr.get_password(_SERVICE, _ACCOUNT) if kr else "") or ""
        except Exception:  # noqa: BLE001
            return ""
    if blob == _FILE_MARK:
        try:
            with open(SECRET_FILE, encoding="utf-8") as f:
                return f.read().rstrip("\r\n")
        except OSError:
            return ""
    return ""    # unbekanntes Format, z. B. DPAPI-Blob aus einer kopierten Windows-Config


def load() -> dict:
    cfg = dict(DEFAULTS)
    if not os.path.exists(CONFIG_FILE) and os.path.exists(_OLD_CONFIG):
        # Migration von der Vorgänger-Version (App hieß früher subsync)
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            import shutil
            shutil.copyfile(_OLD_CONFIG, CONFIG_FILE)
        except OSError:
            pass
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        cfg["ui_language"] = _detect_ui_language()   # erster Start: Systemsprache übernehmen
        cfg["languages"] = [_detect_sub_language()]
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
