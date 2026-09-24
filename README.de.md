# SuperSubber — findet, lädt und synchronisiert Untertitel im Stapel

+ Open Source, portables Tool für Windows und Linux
+ Verarbeitet einzelne Videos oder ganze Ordner auf einmal — ein Film, eine Staffel oder eine komplette Serie
+ Lädt automatisch fehlende Untertitel für jedes Video
+ Synchronisiert die Untertitel gegen die Tonspur des Videos
+ Behebt Framerate-Drift wie 23,976 zu 25 fps, konstante Offsets und Werbeschnitt-Sprünge
+ Ergebnis liegt als `<Video>.<lang>.srt` neben dem Video — Kodi & Co. laden es automatisch

<p align="center"><img src="assets/screenshot-main.png" alt="Hauptfenster nach einem Lauf" width="640"></p>

## Benutzung

1. **Windows:** Release-Zip herunterladen, irgendwohin entpacken, `supersubber.exe` starten — portabel, keine Installation. Mit Scoop: `scoop bucket add cosmopolyte https://github.com/Cosmopolyte/scoop-bucket` und `scoop install supersubber`.<br>
   **Linux:** AppImage herunterladen, mit `chmod +x` ausführbar machen und starten — oder das tar.gz entpacken und `./supersubber` aufrufen.
2. Video oder Ordner hineinziehen oder wählen. SuperSubber sucht sofort bei den Providern und listet jedes Video in einer Tabelle: als was es erkannt wurde und ob je Sprache Untertitel gefunden wurden. Geladen wird noch nichts.
3. **Start** drücken, sobald die Suche fertig ist. Fortschritt pro Video im Fenster; am Ende eine Zusammenfassung. Videos, die schon Untertitel in der Sprache haben, werden übersprungen — mehrfaches Ausführen ist unkritisch.
4. Kommandozeile: `supersubber <Ordner> [--lang ru,de]` startet direkt mit diesem Ordner — `supersubber.exe` unter Windows, `./supersubber` oder das AppImage unter Linux.

Die Oberfläche ist auf Deutsch, Russisch und Englisch umschaltbar. Das Sprachen-Dropdown startet mit den zehn häufigsten Sprachen — der Button „Sprachen…" öffnet eine durchsuchbare Liste mit ~40 weiteren, angezeigt in ihrer Eigenschreibweise.

**Eigenes Untertitel-File syncen:** Ein `.srt` oder `.ass` in die Drop-Zone ziehen, allein oder zusammen mit dem Video. Liegt genau ein Video im selben Ordner, wird es automatisch genommen, sonst fragt ein Dateidialog. Ein verdrängtes File bleibt erhalten und bekommt die Endung `.orig`, die Player ignorieren.

**NFO-Dateien:** Liegt neben dem Video eine `.nfo` mit IMDb-Link, sucht SuperSubber sofort über diese ID — Originaltitel, Jahr oder Schreibweise im Dateinamen spielen dann keine Rolle mehr.

**IMDb-Suche:** Zeigt die Tabelle für ein Video keine Treffer oder ist die Erkennung falsch, in der IMDb-Spalte auf **SET** klicken und IMDb-ID oder -Link einfügen — die Zeile wird sofort neu gesucht und zeigt den Titel, den die Provider zu dieser ID melden. Bei einer Folge lässt sich die Serien-ID in einem Schritt auf alle Folgen dieser Serie übernehmen. **EDIT** ändert die ID, **✕** entfernt sie.

**„Kein Untertitel gefunden":** Die Erkennung läuft über den kompletten Pfad plus OpenSubtitles-Datei-Hash. Serien brauchen den Original-Serientitel irgendwo im Pfad und `SxxExx` im Dateinamen — der Ordnername reicht, z. B. `The.Expanse\S02\S02E05.Home.mp4`, und die Sprache des Episodentitels ist egal. Filme: Originaltitel + Jahr im Dateinamen. Es wird nicht geraten.

## Einstellungen

Die freien Quellen haben kein festes Tageskontingent; ein optionaler, kostenloser OpenSubtitles.com-Login bringt zusätzlich 20 Downloads pro Tag. Unter Windows wird das Passwort per DPAPI verschlüsselt in `%APPDATA%\supersubber\config.json` abgelegt. Unter Linux landet es im Schlüsselbund des Systems, die Config liegt in `~/.config/supersubber`; ohne Schlüsselbund bleibt das Passwort in einer Datei, die nur der eigene Benutzer lesen kann — der Dialog weist darauf hin. **Auf Updates prüfen** fragt GitHub nach dem neuesten Release — installiert wird nichts automatisch.

<p align="center"><img src="assets/screenshot-settings.png" alt="Einstellungen" width="380"></p>

## Hinweise

- **Linux-Builds** entstehen und laufen auf Debian 13 mit glibc 2.41 und brauchen eine ähnlich aktuelle Distribution; ältere Systeme bauen aus dem Quellcode. Das AppImage braucht wie jedes AppImage FUSE — ohne FUSE mit `--appimage-extract-and-run` starten oder das tar.gz nehmen.
- **SmartScreen-Warnung:** Die Exe ist nicht signiert, das ist ein kostenloses Hobby-Tool. Windows warnt ggf. beim ersten Start — „Weitere Informationen" → „Trotzdem ausführen", oder aus dem Quellcode bauen.
- **Provided as-is.** Keine Support-Zusagen; Issues und PRs sind willkommen, Antworten können dauern.
- **Unter der Haube:** [subliminal](https://github.com/Diaoul/subliminal) sucht und lädt von mehreren Providern, [alass](https://github.com/kaegi/alass) synchronisiert per Sprachaktivitäts-Analyse. Siehe `THIRD-PARTY.md`.

## Aus dem Quellcode bauen

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\fetch-bins.ps1          # alass + ffmpeg nach bin\
.\.venv\Scripts\python -m supersubber [Ordner]
.\build.ps1               # dist\supersubber\ + dist\supersubber-<version>-win64.zip
```

```bash
# Linux — braucht python3, python3-venv und python3-tk aus der Distribution
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./fetch-bins.sh           # lädt alass + ein statisches ffmpeg nach bin/
.venv/bin/python -m supersubber [Ordner]
./build.sh                # dist/supersubber/, .tar.gz und .AppImage
```

## Lizenz

MIT — siehe [LICENSE](LICENSE). Gebündelte Drittkomponenten behalten ihre eigenen Lizenzen, siehe [THIRD-PARTY.md](THIRD-PARTY.md).
