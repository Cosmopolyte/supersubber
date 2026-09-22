# supersubber — Untertitel automatisch laden & synchronisieren

+ Open Source, portables Windows-Tool
+ Lädt automatisch fehlende Untertitel für alle Videos in einem Ordner (rekursiv)
+ Synchronisiert die Untertitel gegen die Tonspur des Videos
+ Behebt Framerate-Drift (23,976 ↔ 25 fps), konstante Offsets und Werbeschnitt-Sprünge
+ Ergebnis liegt als `<Video>.<lang>.srt` neben dem Video — Kodi & Co. laden es automatisch

<p align="center"><img src="assets/screenshot-main.png" alt="Hauptfenster nach einem Lauf" width="560"></p>

## Benutzung

1. Release-Zip herunterladen, irgendwohin entpacken, `supersubber.exe` starten — portabel, keine Installation.
2. Video oder Ordner hineinziehen (oder wählen), Untertitel-Sprachen anhaken, **Start**.
3. Fortschritt pro Episode im Fenster; am Ende eine Zusammenfassung. Videos, die schon Untertitel in der Sprache haben, werden übersprungen — mehrfaches Ausführen ist unkritisch.
4. Kommandozeile: `supersubber.exe <Ordner> [--lang ru,de]` startet direkt mit diesem Ordner.

Die Oberfläche ist auf Deutsch, Russisch und Englisch umschaltbar (⚙ → App-Sprache; beim ersten Start wird die Windows-Anzeigesprache übernommen). Das Sprachen-Dropdown startet mit den zehn häufigsten Sprachen — der Button „Sprachen…" öffnet eine durchsuchbare Liste mit ~40 weiteren, angezeigt in ihrer Eigenschreibweise.

**Eigenes Untertitel-File syncen:** Ein `.srt`/`.ass` in die Drop-Zone ziehen (allein oder zusammen mit dem Video) — liegt genau ein Video im selben Ordner, wird es automatisch genommen, sonst fragt ein Dateidialog. Ein verdrängtes File wird einmalig als `*.orig` gesichert (diese Endung ignorieren Player).

**NFO-Dateien:** Liegt neben dem Video eine `.nfo` mit IMDb-Link (Release-NFOs haben ihn fast immer, Kodi/Jellyfin-`movie.nfo`/`tvshow.nfo` ebenso), sucht supersubber sofort über diese ID — Originaltitel, Jahr oder Schreibweise im Dateinamen spielen dann keine Rolle mehr.

**IMDb-Nachsuche:** Wird ein Video nicht erkannt, erscheint nach dem Lauf der Button „IMDb-ID angeben…" — IMDb-ID oder -Link eintragen (bei Serien die ID der Serie) und erneut suchen lassen.

**„Kein Untertitel gefunden":** Die Erkennung läuft über den kompletten Pfad (guessit) plus OpenSubtitles-Datei-Hash. Serien: Original-Serientitel irgendwo im Pfad (Ordnername reicht, z. B. `The.Expanse\S02\S02E05.Home.mp4`) + `SxxExx` im Dateinamen — die Sprache des Episodentitels ist egal. Filme: Originaltitel + Jahr im Dateinamen. Es wird nicht geraten.

## Einstellungen

Zusätzlich zu den freien Quellen (kein festes Tageskontingent) bringt ein optionaler, kostenloser OpenSubtitles.com-Login 20 Downloads pro Tag. Das Passwort wird per Windows DPAPI verschlüsselt in `%APPDATA%\supersubber\config.json` abgelegt.

<p align="center"><img src="assets/screenshot-settings.png" alt="Einstellungen" width="380"></p>

## Hinweise

- **Nur Windows.** Nutzt DPAPI und bündelt Windows-Binaries; andere Plattformen sind derzeit nicht geplant.
- **SmartScreen-Warnung:** Die Exe ist nicht signiert (kostenloses Hobby-Tool). Windows warnt ggf. beim ersten Start — „Weitere Informationen" → „Trotzdem ausführen", oder aus dem Quellcode bauen.
- **Provided as-is.** Keine Support-Zusagen; Issues und PRs sind willkommen, Antworten können dauern.
- **Unter der Haube:** die Open-Source-Tools [subliminal](https://github.com/Diaoul/subliminal) (Suche & Download von mehreren Providern) + [alass](https://github.com/kaegi/alass) (Sync per Sprachaktivitäts-Analyse). Siehe `THIRD-PARTY.md`.

## Aus dem Quellcode bauen

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\fetch-bins.ps1          # alass + ffmpeg nach bin\
.\.venv\Scripts\python -m supersubber [Ordner]
.\build.ps1               # dist\supersubber\ + dist\supersubber-<version>-win64.zip
```

## Lizenz

MIT — siehe [LICENSE](LICENSE). Gebündelte Drittkomponenten behalten ihre eigenen Lizenzen, siehe [THIRD-PARTY.md](THIRD-PARTY.md).
