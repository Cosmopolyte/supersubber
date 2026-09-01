# subsync — Find & Sync Subtitles

Portable Windows-Tool: lädt fehlende Untertitel für alle Videos in einem Ordner (rekursiv) und synchronisiert sie gegen die Tonspur — behebt Framerate-Drift (23,976 ↔ 25 fps), Offsets und Werbeschnitt-Sprünge. Ergebnis liegt als `<Video>.<lang>.srt` neben dem Video, Kodi & Co. laden es automatisch.

Unter der Haube: [subliminal](https://github.com/Diaoul/subliminal) (Download, Provider: Podnapisi, OpenSubtitles.com mit Login, u. a.) + [alass](https://github.com/kaegi/alass) (Sync per Sprachaktivitäts-Analyse). Siehe `THIRD-PARTY.md`.

## Benutzung

1. `subsync.exe` starten (portabel, keine Installation).
2. Ordner hineinziehen oder wählen, Untertitel-Sprachen im Dropdown anhaken, **Start**.
3. Fortschritt pro Episode im Fenster; am Ende ✔ mit Zusammenfassung. Videos, die schon Untertitel in der Sprache haben, werden übersprungen — mehrfaches Ausführen ist unkritisch.
4. `subsync.exe <Ordner> [--lang ru,de]` startet direkt mit diesem Ordner.

Die Oberfläche ist auf Deutsch, Russisch und Englisch umschaltbar (Auswahl oben rechts).

**Einstellungen:** OpenSubtitles.com-Login (Free-Account = 20 Downloads/Tag, „?" öffnet die Registrierung; Passwort per Windows DPAPI verschlüsselt in `%APPDATA%\subsync\config.json`), Liste der angebotenen Untertitel-Sprachen (ISO-Kürzel, werden validiert).

**„Kein Untertitel gefunden":** Die Erkennung läuft über den kompletten Pfad (guessit) plus OpenSubtitles-Datei-Hash. Serien: Original-Serienname irgendwo im Pfad (Ordnername reicht, z. B. `Animal.Kingdom\S01\S01E09.Der große Coup.mp4`) + `SxxExx` im Dateinamen — die Sprache des Episodentitels ist egal. Filme: Originaltitel + Jahr in den Dateinamen. Es wird nicht geraten.

## Entwicklung

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\fetch-bins.ps1          # alass + ffmpeg nach bin\
.\.venv\Scripts\python -m subsync [Ordner]
.\build.ps1               # dist\subsync\ + dist\subsync-<ver>-win64.zip
```

Projektstruktur: `subsync/core.py` (Ablauf), `subsync/app.py` (GUI), `subsync/config.py`, `subsync/contextmenu.py`. Vorgänger: `legacy/subsync.ps1` (PowerShell-Wrapper um die CLI-Tools).
