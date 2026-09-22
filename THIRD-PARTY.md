# Third-party components

SuperSubber invokes alass and ffmpeg as separate processes (no linking); subliminal is used as a Python library.

| Component | Version | License | Source |
|---|---|---|---|
| alass (alass-cli) | 2.0.0 | GPL-3.0 | https://github.com/kaegi/alass |
| ffmpeg / ffprobe (from alass-windows64.zip) | 4.x (build shipped with the alass release) | GPL-2.0+ (build includes GPL components) | https://ffmpeg.org — license text in `bin/LICENSE-ffmpeg.txt` |
| subliminal | 2.7.1 | MIT | https://github.com/Diaoul/subliminal |
| guessit, babelfish | (subliminal dependencies) | LGPL-3.0 / BSD-3 | |
| tkinterdnd2 | 0.6.x | MIT | https://github.com/pmgagne/tkinterdnd2 |
| PyInstaller (build only) | 6.x | GPL-2.0 with bootloader exception | https://pyinstaller.org |

The release zip redistributes the alass and ffmpeg binaries unchanged, together with their license texts in `bin/`. Source code for the GPL binaries is available from the upstream repositories listed above in the exact versions used; `fetch-bins.ps1` documents how the binaries are obtained.
