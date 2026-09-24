# Third-party components

SuperSubber invokes alass and ffmpeg as separate processes (no linking); subliminal is used as a Python library.

| Component | Version | License | Source |
|---|---|---|---|
| alass (alass-cli) | 2.0.0 | GPL-3.0 | https://github.com/kaegi/alass — license text in `bin/LICENSE-alass.txt` |
| ffmpeg / ffprobe, Windows package (from alass-windows64.zip) | 4.x (build shipped with the alass release) | GPL-2.0+ (build includes GPL components) | https://ffmpeg.org — license text in `bin/LICENSE-ffmpeg.txt` |
| ffmpeg / ffprobe, Linux package (static build by John Van Sickle) | 7.0.2 | GPL-3.0 (static build includes GPL components) | https://johnvansickle.com/ffmpeg/ — license text in `bin/LICENSE-ffmpeg-linux.txt`, build details in `bin/ffmpeg-linux-build-info.txt` |
| subliminal | 2.7.1 | MIT | https://github.com/Diaoul/subliminal |
| guessit, babelfish | (subliminal dependencies) | LGPL-3.0 / BSD-3 | |
| tkinterdnd2 | 0.6.x | MIT | https://github.com/pmgagne/tkinterdnd2 |
| keyring, SecretStorage, jeepney (Linux package only) | 25.x / 3.x / 0.9 | MIT / BSD-3 / MIT | https://github.com/jaraco/keyring |
| AppImage runtime (Linux AppImage only) | type-2 runtime, embedded by appimagetool | MIT | https://github.com/AppImage/type2-runtime |
| PyInstaller (build only) | 6.x | GPL-2.0 with bootloader exception | https://pyinstaller.org |

The release packages redistribute the alass and ffmpeg binaries unchanged, together with their license texts in `bin/`. Source code for the GPL binaries is available from the upstream sites listed above in the exact versions used; `fetch-bins.ps1` (Windows) and `fetch-bins.sh` (Linux) document how the binaries are obtained.
