# SuperSubber — finds, downloads and syncs subtitles in bulk

+ Open source, portable tool for Windows and Linux
+ Works on single video files or whole folders at once — a movie, a season or an entire show
+ Automatically downloads missing subtitles for every video
+ Synchronizes subtitles against the audio track of the video
+ Fixes framerate drift such as 23.976 vs 25 fps, constant offsets and ad-break jumps
+ The resulting subtitles are saved as `<video>.<lang>.srt` next to the video

*Deutsche Anleitung: [README.de.md](README.de.md)*

<p align="center"><img src="assets/screenshot-main.png" alt="Main window after a finished run" width="640"></p>

## Usage

1. **Windows:** download the release zip, unpack it anywhere, run `supersubber.exe` — portable, no installation. Scoop users: `scoop bucket add cosmopolyte https://github.com/Cosmopolyte/scoop-bucket` and `scoop install supersubber`.<br>
   **Linux:** download the AppImage, make it executable with `chmod +x` and start it — or unpack the tar.gz and run `./supersubber`.
2. Drag a video or folder into the window or pick one. SuperSubber searches the providers right away and lists every video in a table: what it was recognized as, and whether subtitles were found for each language. Nothing is downloaded yet.
3. Hit **Start** once the search is done. Watch the per-video progress; a summary appears at the end. Videos that already have subtitles in a language are skipped, so re-running is always safe. That covers external files like `movie.en.srt`, `movie.eng.srt` or `movie.srt` with the language detected from the text, and subtitle tracks embedded in the video, which show as "embedded" in the table. Embedded tracks can be ignored via a setting if you want external files anyway.
4. CLI usage: `supersubber <folder> [--lang ru,de]` starts processing that folder right away — `supersubber.exe` on Windows, `./supersubber` or the AppImage on Linux.

The UI speaks English, German and Russian. The subtitle-language dropdown starts with the ten most common languages — the **Languages…** button opens a searchable list of ~40 more, shown in their native names.

**Sync your own subtitle file:** drag a `.srt` or `.ass` into the drop zone, alone or together with the video. If exactly one video sits in the same folder it is picked automatically, otherwise a file dialog asks. A displaced file is kept and renamed with the extension `.orig`, which media players ignore.

**NFO files:** if a `.nfo` next to the video contains an IMDb link, SuperSubber searches by that ID right away — original title, year or wording in the filename no longer matter.

**IMDb lookup:** if the table shows no hits for a video, or the recognition is wrong, click **SET** in its IMDb column and paste the IMDb ID or link — the row is searched again immediately and shows the title the providers report for that ID. For an episode you can apply the show's ID to all episodes of that show in one go. **EDIT** changes the ID, **✕** removes it.

**"No subtitles found":** detection uses the full path plus the OpenSubtitles file hash. TV shows need the original show title somewhere in the path and `SxxExx` in the filename — the folder name is enough, e.g. `The.Expanse\S02\S02E05.Home.mp4`, and the episode title's language doesn't matter. Movies need original title + year in the filename. SuperSubber never guesses.

## Settings

The free providers have no fixed daily quota; an optional free OpenSubtitles.com login adds 20 downloads per day on top. On Windows the password is stored encrypted with DPAPI in `%APPDATA%\supersubber\config.json`. On Linux it goes into the system keyring and the config lives in `~/.config/supersubber`; without a keyring the password is kept in a file only your user can read, and the dialog says so. **Check for updates** asks GitHub for the latest release — nothing is installed automatically.

<p align="center"><img src="assets/screenshot-settings.png" alt="Settings dialog" width="380"></p>

## Notes

- **Linux builds** are made and tested on Debian 13 with glibc 2.41 and need a similarly current distribution; older systems build from source. The AppImage needs FUSE like every AppImage — without it, run it with `--appimage-extract-and-run` or use the tar.gz.
- **SmartScreen warning:** the executable is not code-signed, this is a free hobby tool. Windows may warn on first start — "More info" → "Run anyway", or build from source below.
- **Provided as-is.** No support promises; issues and PRs are welcome but may take a while.
- **Under the hood:** [subliminal](https://github.com/Diaoul/subliminal) searches and downloads from multiple providers, [alass](https://github.com/kaegi/alass) syncs via voice-activity analysis. See `THIRD-PARTY.md`.

## Building from source

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\fetch-bins.ps1          # downloads alass + ffmpeg into bin\
.\.venv\Scripts\python -m supersubber [folder]
.\build.ps1               # dist\supersubber\ + dist\supersubber-<version>-win64.zip
```

```bash
# Linux — needs python3, python3-venv and python3-tk from the distribution
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./fetch-bins.sh           # downloads alass + a static ffmpeg into bin/
.venv/bin/python -m supersubber [folder]
./build.sh                # dist/supersubber/, .tar.gz and .AppImage
```

Project layout: `supersubber/core.py` is the pipeline, `supersubber/app.py` the Tkinter GUI, plus `config.py` and `i18n.py`.

Note: `subliminal` is pinned to an exact version because SuperSubber patches the OpenSubtitles.com provider to pass the show's IMDb ID for episode searches — an upstream TODO. Bump the pin only after checking that patch in `core.py`.

## License

MIT — see [LICENSE](LICENSE). Bundled third-party binaries keep their own licenses, see [THIRD-PARTY.md](THIRD-PARTY.md).
