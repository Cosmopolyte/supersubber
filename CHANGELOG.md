# Changelog

## 1.0.0 — 2026-09-22
First stable release after a month of daily use on ~60 videos.
- Version is shown in the title bar and in the settings dialog (with a link to this repository).
- Subtitles whose release name contains the video's release group (e.g. `-SHORTBREHD`) get a scoring bonus — they are timed for exactly that cut.

## 0.9.1 — 2026-09-18
- Release sample files (`*-sample.*`, `Sample` folders) are skipped — large 2160p samples used to pass the size filter and received the subtitles of the whole episode.

## 0.9.0 — 2026-09-18
- IMDb ID is read from `.nfo` files next to the video (release NFOs and Kodi/Jellyfin `movie.nfo`/`tvshow.nfo`) and used for the search right away; a manually entered ID still wins.

## 0.8.2 — 2026-09-18
- Candidates need a minimum match score: movies title + year, episodes series + season + episode. Previously any partial title match could win (a 2025 movie received subtitles of a 1991 film with a similar title).

## 0.8.1 — 2026-09-08
- Subtitles in non-UTF-8 encodings (cp1252, cp1251, …) are transcoded before syncing; they used to fail the sync step and were saved unsynced.
- Local-file sync always works on a temp copy and never modifies the original file.
- README screenshots.

## 0.8.0 — 2026-09-04
- First public release on GitHub, renamed from subsync to supersubber. MIT license, English README, configuration migrates automatically from the old name.

## Before 0.8.0 (private development, Sept 2026)
- 0.7: searchable language picker (~40 languages, native names), persistent language selection, ten default languages, first start picks the Windows display language.
- 0.6: sync your own subtitle file by dropping it into the window.
- 0.5: live sync progress, IMDb field for single-video folders, grouped log.
- 0.4: IMDb lookup for unrecognized videos, "questionable" detection for subtitles that probably belong to a different cut, GUI in English/German/Russian.
- 0.1–0.3: drag & drop GUI, subliminal download + alass sync pipeline, quality check against forced/incomplete subtitles, portable PyInstaller build.
