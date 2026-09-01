# subsync — Find & Sync Subtitles

Portable Windows-Tool: lädt fehlende Untertitel für alle Videos in einem Ordner (rekursiv) und synchronisiert sie gegen die Tonspur — behebt Framerate-Drift (23,976 ↔ 25 fps), Offsets und Werbeschnitt-Sprünge. Ergebnis liegt als `<Video>.<lang>.srt` neben dem Video, Kodi & Co. laden es automatisch.

Unter der Haube: [subliminal](https://github.com/Diaoul/subliminal) (Download, Provider: Podnapisi, OpenSubtitles.com mit Login, u. a.) + [alass](https://github.com/kaegi/alass) (Sync per Sprachaktivitäts-Analyse). Siehe `THIRD-PARTY.md`.

## Benutzung

1. `subsync.exe` starten (portabel, keine Installation).
2. Ordner hineinziehen oder wählen, Sprachen ankreuzen, **Start**.
3. Fortschritt pro Episode im Fenster; am Ende ✔ mit Zusammenfassung. Videos, die schon Untertitel in der Sprache haben, werden übersprungen — mehrfaches Ausführen ist unkritisch.
4. `subsync.exe <Ordner>` startet direkt mit diesem Ordner (dafür gibt es optional den Explorer-Kontextmenü-Eintrag, siehe Einstellungen).

**Einstellungen:** OpenSubtitles.com-Login (Free-Account reicht, ~20 Downloads/Tag; Passwort per Windows DPAPI verschlüsselt in `%APPDATA%\subsync\config.json`), Sprachauswahl, Kontextmenü an/aus.

**„Kein Untertitel gefunden":** Die Erkennung braucht Serienname + `SxxExx` bzw. Filmtitel + Jahr im Dateinamen. Es wird nicht geraten.

## Entwicklung

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\fetch-bins.ps1          # alass + ffmpeg nach bin\
.\.venv\Scripts\python -m subsync [Ordner]
.\build.ps1               # dist\subsync\ + dist\subsync-<ver>-win64.zip
```

Projektstruktur: `subsync/core.py` (Ablauf), `subsync/app.py` (GUI), `subsync/config.py`, `subsync/contextmenu.py`. Vorgänger: `legacy/subsync.ps1` (PowerShell-Wrapper um die CLI-Tools).
