"""Konfiguration in %APPDATA%\\subsync\\config.json. Passwort per Windows DPAPI verschlüsselt (nur dieser User/Rechner)."""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys

APP_NAME = "subsync"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "languages": ["ru"],                 # vorausgewählte Sprachen
    "known_languages": ["ru", "de", "en"],  # Auswahl in der GUI
    "opensubtitles_user": "",
    "opensubtitles_password": "",        # DPAPI-verschlüsselt, base64
    "min_size_mb": 50,
}


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
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
