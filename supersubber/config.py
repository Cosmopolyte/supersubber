"""Konfiguration in %APPDATA%\\supersubber\\config.json. Passwort per Windows DPAPI verschlüsselt (nur dieser User/Rechner)."""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys

APP_NAME = "supersubber"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
_OLD_CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "subsync", "config.json")

DEFAULTS = {
    "languages": ["en"],                 # vorausgewählte Sprachen; erster Start: Systemsprache
    "known_languages": ["en", "fr", "es", "de", "pt", "ru", "uk", "zh", "ko", "ja"],  # Dropdown-Angebot
    "opensubtitles_user": "",
    "opensubtitles_password": "",        # DPAPI-verschlüsselt, base64
    "min_size_mb": 50,
    "ui_language": "en",                 # Default Englisch; beim ersten Start Systemsprache erkannt
}

# Windows-Primary-LANGID → ISO-Kürzel, nur für die Default-known_languages relevant
_LANGID = {0x09: "en", 0x0c: "fr", 0x0a: "es", 0x07: "de", 0x16: "pt",
           0x19: "ru", 0x22: "uk", 0x04: "zh", 0x12: "ko", 0x11: "ja"}


def _detect_ui_language() -> str:
    """Windows-Anzeigesprache → de/ru wenn passend, sonst en."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x07: "de", 0x19: "ru"}.get(lang_id, "en")
    except Exception:  # noqa: BLE001
        return "en"


def _detect_sub_language() -> str:
    """Windows-Anzeigesprache → vorausgewählte Untertitel-Sprache (nur erster Start)."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return _LANGID.get(lang_id, "en")
    except Exception:  # noqa: BLE001
        return "en"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    if sys.platform != "win32":
        return data
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


def encrypt(text: str) -> str:
    return base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode("ascii") if text else ""


def decrypt(blob: str) -> str:
    try:
        return _dpapi(base64.b64decode(blob), False).decode("utf-8") if blob else ""
    except Exception:
        return ""


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
