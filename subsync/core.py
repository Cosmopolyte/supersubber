"""Kernablauf: Videos finden → fehlende Subs via subliminal laden → mit alass gegen die Tonspur syncen."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv"}
SUB_EXT = (".srt", ".ass", ".ssa")
# Provider ohne Zugangsdaten; opensubtitlescom kommt dazu, sobald ein Login konfiguriert ist
BASE_PROVIDERS = ["podnapisi", "gestdown", "tvsubtitles", "bsplayer", "opensubtitles"]

MIN_CUES_PER_MIN = 3     # darunter gilt ein Sub als Forced/unvollständig (Serien liegen bei 10–15/min)
MAX_ATTEMPTS = 3         # Kandidaten pro Sprache, bevor aufgegeben wird

Progress = Callable[[str, int, int], None]   # (Meldung, aktuell, gesamt)
Log = Callable[[str], None]
Tr = Callable[..., str]                      # tr(key, **kw) — Übersetzung, von der GUI geliefert


def _tr_fallback(key: str, **kw) -> str:
    return f"{key} {kw}" if kw else key


def bin_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "bin"


@dataclass
class Result:
    synced: list[str] = field(default_factory=list)
    unsynced: list[str] = field(default_factory=list)   # geladen, alass gescheitert → roh übernommen
    missing: list[str] = field(default_factory=list)
    noaccess: list[str] = field(default_factory=list)   # Ordner ohne Schreibrecht
    skipped: int = 0
    cancelled: bool = False
    error: str | None = None


def find_videos(folder: str, min_size_mb: int) -> list[Path]:
    out = []
    for root, _, files in os.walk(folder):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in VIDEO_EXT:
                try:
                    if p.stat().st_size >= min_size_mb * 1024 * 1024:
                        out.append(p)
                except OSError:
                    pass
    return sorted(out)


def has_sub(video: Path, lang: str) -> bool:
    return any((video.with_name(f"{video.stem}.{lang}{ext}")).exists() for ext in SUB_EXT)


def can_write(directory: Path) -> bool:
    probe = directory / f".subsync-{uuid.uuid4().hex[:8]}.tmp"
    try:
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def _duration_min(video: Path) -> float:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run([str(bin_dir() / "ffprobe.exe"), "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(video)], capture_output=True, text=True, creationflags=flags)
        return float(r.stdout.strip()) / 60
    except (OSError, ValueError):
        return 0.0


def _cue_count(sub: Path) -> int:
    try:
        return sub.read_text(encoding="utf-8", errors="replace").count("-->")
    except OSError:
        return 0


def _alass(video: Path, sub: Path, out: Path, log: Log) -> bool:
    b = bin_dir()
    env = dict(os.environ, ALASS_FFMPEG_PATH=str(b / "ffmpeg.exe"), ALASS_FFPROBE_PATH=str(b / "ffprobe.exe"))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run([str(b / "alass-cli.exe"), str(video), str(sub), str(out)],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=flags)
    except OSError as e:
        log(f"    alass: {e}")
        return False
    for line in re.split(r"[\r\n]+", (r.stdout or "") + (r.stderr or "")):
        if re.search(r"shifted|ratio is|error", line):
            log("    " + line.strip())
    return r.returncode == 0 and out.exists()


def run(folder: str, languages: list[str], cfg: dict, progress: Progress, log: Log,
        cancel: threading.Event, tr: Tr = _tr_fallback) -> Result:
    res = Result()
    try:
        return _run(folder, languages, cfg, progress, log, cancel, tr, res)
    except Exception as e:  # noqa: BLE001 — alles in der GUI anzeigen statt stumm sterben
        res.error = f"{type(e).__name__}: {e}"
        return res


def _run(folder, languages, cfg, progress, log, cancel, tr, res: Result) -> Result:
    from babelfish import Language
    from subliminal import ProviderPool, refine, region, save_subtitles, scan_video

    if not region.is_configured:
        region.configure("dogpile.cache.memory")

    progress(tr("c_scan"), 0, 0)
    videos = find_videos(folder, int(cfg.get("min_size_mb", 50)))
    if not videos:
        res.error = tr("c_none")
        return res

    # Schreibrechte je Ordner prüfen — ohne Schreibrecht kann kein Sub abgelegt werden
    writable: dict[Path, bool] = {}
    for v in videos:
        d = v.parent
        if d not in writable:
            writable[d] = can_write(d)
            if not writable[d]:
                res.noaccess.append(str(d))
                log(tr("c_no_write", folder=d.name or str(d)))

    todo = [(v, [l for l in languages if not has_sub(v, l)]) for v in videos if writable[v.parent]]
    todo = [(v, ls) for v, ls in todo if ls]
    res.skipped = sum(writable[v.parent] for v in videos) - len(todo)
    log(tr("c_found", v=len(videos), t=len(todo), langs=", ".join(languages)))
    if not todo:
        return res

    providers = list(BASE_PROVIDERS)
    provider_configs = {}
    from . import config as cfgmod
    user, pw = cfg.get("opensubtitles_user", ""), cfgmod.decrypt(cfg.get("opensubtitles_password", ""))
    if user and pw:
        providers.append("opensubtitlescom")
        provider_configs["opensubtitlescom"] = {"username": user, "password": pw}
    else:
        log(tr("c_no_login"))

    tmp = Path(tempfile.mkdtemp(prefix="subsync-"))
    try:
        with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
            for i, (video, langs) in enumerate(todo, 1):
                if cancel.is_set():
                    res.cancelled = True
                    break
                progress(f"{video.name}", i, len(todo))
                log(f"[{i}/{len(todo)}] {video.name}  [{', '.join(langs)}]")
                got = {}
                try:
                    v = scan_video(str(video))
                    refine(v, refiners=("hash",))
                    want = {Language.fromietf(l) for l in langs}
                    found = pool.list_subtitles(v, want)
                    minutes = _duration_min(video)
                    ignore: list[str] = []
                    for _attempt in range(MAX_ATTEMPTS):
                        if not want:
                            break
                        best = pool.download_best_subtitles(found, v, want, subtitle_categories="n,hi,fo",
                                                            ignore_subtitles=ignore)
                        if not best:
                            break
                        for s in save_subtitles(v, best, directory=str(tmp)):
                            p = tmp / Path(s.get_path(v)).name
                            cues = _cue_count(p)
                            if minutes and cues / minutes < MIN_CUES_PER_MIN:
                                log(tr("c_discard", lang=s.language.alpha2, cues=cues,
                                       mins=f"{minutes:.0f}", prov=s.provider_name))
                                ignore.append(s.id)
                                p.unlink(missing_ok=True)
                                continue
                            got[s.language.alpha2] = p
                            want.discard(s.language)
                except Exception as e:  # noqa: BLE001
                    log(tr("c_dl_err", err=f"{type(e).__name__}: {e}"))
                for lang in langs:
                    if cancel.is_set():
                        break
                    dl = got.get(lang)
                    if not dl or not dl.exists():
                        res.missing.append(f"{video.name}  [{lang}]")
                        log(tr("c_not_found", lang=lang))
                        continue
                    out = video.with_name(f"{video.stem}.{lang}{dl.suffix.lower()}")
                    progress(f"{video.name}", i, len(todo))
                    if _alass(video, dl, out, log):
                        res.synced.append(f"{video.name}  [{lang}]")
                    else:
                        shutil.copyfile(dl, out)
                        res.unsynced.append(f"{video.name}  [{lang}]")
                        log(tr("c_sync_fail"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return res
