# Drittkomponenten

subsync ruft alass und ffmpeg als separate Prozesse auf (keine Verlinkung); subliminal wird als Python-Bibliothek eingebunden.

| Komponente | Version | Lizenz | Quelle |
|---|---|---|---|
| alass (alass-cli) | 2.0.0 | GPL-3.0 | https://github.com/kaegi/alass |
| ffmpeg / ffprobe (aus alass-windows64.zip) | 4.x (Build aus dem alass-Release) | GPL-2.0+ (Build mit GPL-Komponenten) | https://ffmpeg.org — Lizenztext in `bin/LICENSE-ffmpeg.txt` |
| subliminal | 2.7.1 | MIT | https://github.com/Diaoul/subliminal |
| guessit, babelfish | (Abhängigkeiten von subliminal) | LGPL-3.0 / BSD-3 | |
| tkinterdnd2 | 0.6.x | MIT | https://github.com/pmgagne/tkinterdnd2 |
| PyInstaller (nur Build) | 6.x | GPL-2.0 mit Bootloader-Ausnahme | https://pyinstaller.org |

Bei Weitergabe des Pakets: Lizenztexte in `bin/` mitliefern; der Quellcode der GPL-Binaries ist über die genannten Upstream-Repos in der jeweiligen Version verfügbar.
