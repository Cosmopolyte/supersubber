"""Optionaler Explorer-Kontextmenü-Eintrag (HKCU, nur aktueller User) auf Ordnern: "Find & Sync Subtitles"."""
import os
import sys

KEY = r"Software\Classes\Directory\shell\SubSync"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    return f'"{sys.executable}" -m subsync "%1"'


def is_installed() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY + r"\command") as k:
            return winreg.QueryValue(k, None) == _command()
    except OSError:
        return False


def install() -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Find && Sync Subtitles")
        exe = sys.executable if getattr(sys, "frozen", False) else ""
        if exe:
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY + r"\command") as k:
        winreg.SetValue(k, None, winreg.REG_SZ, _command())


def uninstall() -> None:
    import winreg
    for sub in (KEY + r"\command", KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            pass
