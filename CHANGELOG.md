# Changelog

## 1.6.2 — unreleased
- "Recognized as" names the year for films whose file name has none, taken from the subtitle that would be downloaded: `Die Hard.mp4` shows `Die Hard · 1988`. If the hits for different languages belong to different films, all years are shown, for example `Batman · 1989 / 2010` — a sign to set the IMDb ID.
- The history names the sources in use, not only the ones that are unreachable.

## 1.6.1 — 2026-10-01
- Drop zone: dotted border on Linux like on Windows, and a little more room below the text.
- Fix: in the IMDb column the EDIT and ✕ buttons covered the ID and cut off their own labels with larger fonts, as on many Linux desktops. Buttons and column now take their width from the actual font.
- Cancel stops at once: a running sync is ended instead of finished first, nothing half done is left next to the video, and the history says that the user cancelled.
- Fix: after a cancelled run the button turned back to "Start" but stayed disabled. It is enabled now and continues with what is left; what was already fetched counts as present.
- While download and sync are running, dropped files and folders are ignored with a hint in the status line. During the search a new drop still replaces the running search.

## 1.6.0 — 2026-09-28
- Fix: a new search requested while another one was still running was dropped without a word — a second language ticked right after the first, or a folder dropped during a search. The request is now remembered; a running search is cancelled and restarted with the current selection.
- Dropping video files now means those files: one video or several marked ones are searched on their own, no longer the whole folder around them. Dropping a folder works as before. The command line accepts a single video as well.
- Changing the subtitle languages no longer starts the search over. A language that is unticked just disappears from the table; for an added one only that language is looked up, recognition and the hits of the other languages are kept.
- Recognition trusts the file name when it says everything: show, season and episode, or movie title and year. Until now a folder with a title of its own won, so `For.All.Mankind.S03E03…` inside a folder named after another release was taken for that release. Files like `S03E03.mkv` or `myMovie.mkv` still get their title from the folder.
- Fix: confirming the IMDb dialog with an unchanged ID no longer searches again.
- New option "Start automatically after the search", off by default. It never fires after a mere change of the language selection.
- New option "Clear the history when a new search starts", on by default. Only the window is cleared, the log file keeps everything.
- The sync line in the history no longer claims "~1–2 min"; the progress bar shows how far it is.
- New option "Also keep the unsynced download", off by default: the subtitle with its original timing is saved next to the video as `<video>.<lang>.unsynced.srt`, in addition to the synced one. Handy for a manual sync when the automatic one fails. Players list it as a second track; SuperSubber never counts it as a present subtitle.
- New option "Also get SDH subtitles", off by default: a second subtitle per language for the deaf and hard of hearing, saved as `<video>.<lang>.sdh.srt` and shown in a row of its own below the video. SDH subtitles mostly exist in English, so finding none is not an error and leaves no mark in the table. With the option off nothing changes: an SDH subtitle counts as a present subtitle like before.
- History and log: Gestdown hits are named `Show S01E03 · Episode title · release` instead of the run-together `Show s01e03Episode title` that subliminal produces.

## 1.5.3 — 2026-09-26
- Providers are checked for reachability at start and before every search; a dead provider is skipped with one line in the history instead of a timeout per video. Podnapisi is gone from the default list, the site has been offline since March 2026.
- Providers dialog in the settings: which sources are used, whether they are reachable right now, and a checkbox to leave one out. The OpenSubtitles.com login moved into the same Sources section.
- Three more free sources from subliminal: NapiProjekt (Polish), Subtitulamos (Spanish and English TV shows) and Subtis (Spanish movies). They are only queried when one of the selected languages fits.

## 1.5.2 — 2026-09-26
- Fix: with an IMDb ID set, subtitles of a different show could slip through when its episode title contained the show's name — Archer S01E06 got "The Whispers: The Archer". The ID bonus now applies only to hits that really carry that ID.
- Checkbox below the table to hide videos that already have every requested language, useful for big shows. Shown by default; the summary line counts them either way.

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
