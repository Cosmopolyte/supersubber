# Changelog

## 1.5.1 — 2026-09-26
- Layout follows the font size: table rows, the drop zone and the language columns scale with the system font, so nothing overlaps or gets cut on high-DPI screens.
- The table grows with the window instead of staying at eight rows; the log shares the remaining space.
- Double episodes such as `S04E10E11` are shown with both numbers.

## 1.5.0 — 2026-09-26
- Log file: everything the window shows plus the details behind it — candidates per provider with scores, the subtitle that was chosen and why, IMDb lookups, alass output, crashes. Rotating, capped at 20 MB by default, size and an "Open log folder" button in the settings. When something goes wrong, send that file.
- More video extensions: a list in the settings for extensions beyond mkv, mp4, avi, m4v, mov and wmv, e.g. hevc or vp9 for renamed containers.
- Color themes: green as before, plus light and dark, chosen in the settings. On Windows the title bars follow the theme.
- The "Save log" button is now "Copy history": the window text goes to the clipboard, ready for a forum post or mail. The history survives a theme or language change.
- Dialogs use the app's own style instead of the system message box.

## 1.4.2 — 2026-09-25
- Settings dialog reordered: app language, OpenSubtitles account, then a Program section with the two checkboxes, the update button and the version. GitHub link at the bottom.

## 1.4.1 — 2026-09-25
- Subtitle tracks embedded in the video now count as present: the table shows "embedded" and the language is skipped. A setting turns this off for people who want external files anyway. Forced-only tracks don't count.
- Subtitle files next to the video are recognized with more name variants: `movie.eng.srt`, `movie.English.srt`, and files without any language tag like `movie.srt`, whose language is detected from the text and noted in the log. Forced files are ignored.
- Tooltips on the folder, languages, settings and save-log buttons and on the IMDb buttons, so the ✕ no longer looks like it removes rows.
- Settings: "Check for updates on start" checkbox, on by default. The start-up check only speaks up when a newer release exists; the manual button stays.
- Windows package is a third smaller: PyInstaller had copied the ffmpeg DLLs twice.

## 1.4.0 — 2026-09-24
- Linux release: the same app as a tar.gz and as an AppImage, built on Debian 13. alass and a static ffmpeg build are bundled, nothing needs to be installed.
- Linux stores the OpenSubtitles password in the system keyring. Without a keyring it falls back to a file only the user can read and says so in the settings dialog.
- Config on Linux lives in `~/.config/supersubber`; the UI language follows `LANG` on first start.
- Windows build unchanged apart from the shared code paths.

## 1.3.0 — 2026-09-22
- Real buttons in the IMDb column: SET when empty, EDIT and a clear button once an ID is set. Clearing returns to the recognition from filename and NFO.
- With an IMDb ID, Recognized-as shows the title the providers report for that ID, plus episode and ID.
- Check for updates in the settings dialog: asks GitHub for the latest release and offers the download page.
- Browse button sits before the folder field so it stays visible on wide windows.
- Tips at the end of the log are set apart from the result lines and only appear when a video was not recognized at all.

## 1.2.1 — 2026-09-22
- Fix: a manually set IMDb ID no longer loses against the title guessed from the folder name. Subtitles found via the ID were rejected by the minimum score when the folder was named after a different title.
- Searching via IMDb ID now shows immediately: the ID appears in the row, language cells show "...", the status line and progress bar animate, rows update one by one.
- Language names in the dropdown and the language list are shown in the app language, the native spelling next to them.
- "Recognized as" shows the IMDb ID once one is set manually.
- IMDb cell reads "set" with a pencil, hand cursor and a hint on hover.
- Save log button moved below the log.

## 1.2.0 — 2026-09-22
- Table: one column per language with the language names in the app language, visible column separators, striped rows, tooltips for truncated cells.
- IMDb ID is set per row by clicking its IMDb cell; for episodes the same ID can be applied to all episodes of that show in one go. The field and buttons below the table are gone.
- Start button moved below the table, in reading order: folder, table, Start, progress.
- Log is kept across runs with separator lines, ends with a colored per-video result block, and can be saved. The large result line above the log is gone; the short summary sits in the status line.
- Window opens at a size derived from the screen and remembers its last size and position.
- Disabled Start button is greyed instead of showing grey text.
- NFO lookup: a foreign NFO is only used when the video is alone in its folder.

## 1.1.0 — 2026-09-22
- New pre-run table: dropping or choosing a folder immediately searches the providers and lists every video with what was recognized and whether subtitles were found per language — before anything is downloaded. Start becomes active once the search is done.
- IMDb IDs are entered per row in that table, for selected rows or for all rows without hits, and the rows are searched again right away. The global IMDb field and the post-run dialog are gone.
- English UI says "TV show" instead of "series".

## 1.0.1 — 2026-09-22
- Display name is now SuperSubber (title bar, dialogs, docs); file, package and config names stay lowercase.

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
