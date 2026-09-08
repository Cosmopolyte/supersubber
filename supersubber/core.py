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
Frac = Callable[[float], None]               # Gesamt-Fortschritt 0..1 für den Balken


def _tr_fallback(key: str, **kw) -> str:
    return f"{key} {kw}" if kw else key


def bin_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "bin"


@dataclass
class Result:
    synced: list[str] = field(default_factory=list)
    unsynced: list[str] = field(default_factory=list)   # geladen, alass gescheitert → roh übernommen
    suspect: list[str] = field(default_factory=list)    # gesynct, aber Untertitel passt vermutlich nicht
    suspect_items: list[tuple[str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_items: list[tuple[str, str]] = field(default_factory=list)   # (Videopfad, Sprachkürzel)
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


def count_videos(folder: str, min_size_mb: int, limit: int = 2) -> int:
    """Zählt Videos, bricht bei `limit` ab (fürs GUI: „genau eines?")."""
    n = 0
    for root, _, files in os.walk(folder):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in VIDEO_EXT:
                try:
                    if p.stat().st_size >= min_size_mb * 1024 * 1024:
                        n += 1
                        if n >= limit:
                            return n
                except OSError:
                    pass
    return n


def has_sub(video: Path, lang: str) -> bool:
    return any((video.with_name(f"{video.stem}.{lang}{ext}")).exists() for ext in SUB_EXT)


def can_write(directory: Path) -> bool:
    probe = directory / f".supersubber-{uuid.uuid4().hex[:8]}.tmp"
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


def _alass(video: Path, sub: Path, out: Path, log: Log, tr: Tr = _tr_fallback,
           subprog: Callable[[float], None] | None = None) -> tuple[bool, bool]:
    """Sync ausführen; alass-Fortschritt (Audio-Analyse) wird live an subprog (0..1) gemeldet.
    Rückgabe: (erfolgreich, verdächtig) — verdächtig = mehrere Blöcke um Minuten verschoben."""
    b = bin_dir()
    env = dict(os.environ, ALASS_FFMPEG_PATH=str(b / "ffmpeg.exe"), ALASS_FFPROBE_PATH=str(b / "ffprobe.exe"))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen([str(b / "alass-cli.exe"), str(video), str(sub), str(out)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", creationflags=flags)
    except OSError as e:
        log(f"    alass: {e}")
        return False, False
    lines: list[str] = []
    buf = ""
    while True:
        chunk = proc.stdout.read(256) if proc.stdout else ""
        if not chunk:
            break
        buf += chunk
        while True:
            m = re.search(r"[\r\n]", buf)
            if not m:
                break
            line, buf = buf[:m.start()], buf[m.end():]
            if line.strip():
                lines.append(line)
                if subprog:
                    pm = re.match(r"\s*(\d+) / (\d+) \[", line)
                    if pm and int(pm.group(2)):
                        subprog(int(pm.group(1)) / int(pm.group(2)))
    if buf.strip():
        lines.append(buf)
    proc.wait()
    big_shifts = 0
    for line in lines:
        if re.search(r"shifted|ratio is|error", line):
            log("    " + line.strip())
        m = re.search(r"by (-?)(\d+):(\d\d):(\d\d)\.", line)
        if m and int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4)) > 300:
            big_shifts += 1
    suspect = big_shifts >= 2
    if suspect:
        log(tr("c_sync_suspect"))
    return proc.returncode == 0 and out.exists(), suspect


def _region_setup():
    from subliminal import region
    if not region.is_configured:
        region.configure("dogpile.cache.memory")
    _patch_opensubtitlescom()


def _patch_opensubtitlescom():
    """subliminal 2.7 schickt die Serien-IMDb-ID nicht an die API (TODO im Provider).
    Patch: series_imdb_id wird als show_imdb_id durchgereicht und als präzises Kriterium
    parent_imdb_id + Staffel + Episode VOR die anderen Suchkriterien gestellt."""
    from subliminal.providers import opensubtitlescom as osc

    if getattr(osc.OpenSubtitlesComProvider, "_supersubber_patched", False):
        return
    from subliminal.video import Episode, Movie

    def list_subtitles(self, video, languages):
        query = season = episode = show_imdb_id = None
        if isinstance(video, Episode):
            query, season, episode = video.series, video.season, video.episode
            show_imdb_id = video.series_imdb_id
        elif isinstance(video, Movie):
            query = video.title
        return self.query(
            languages,
            moviehash=video.hashes.get('opensubtitles'),
            imdb_id=video.imdb_id,
            show_imdb_id=show_imdb_id,
            query=query,
            season=season,
            episode=episode,
            allow_machine_translated=False,
            sort_by_download_count=True,
        )

    orig_make = osc.OpenSubtitlesComProvider._make_query

    def _make_query(self, *, show_imdb_id=None, season=None, episode=None, **kw):
        try:
            criteria = orig_make(self, show_imdb_id=show_imdb_id, season=season, episode=episode, **kw)
        except ValueError:
            criteria = []
        if show_imdb_id and season is not None and episode is not None:
            criteria.insert(0, {'parent_imdb_id': osc.sanitize_id(show_imdb_id),
                                'season_number': season, 'episode_number': episode})
        if not criteria:
            raise ValueError('Not enough information')
        return criteria

    osc.OpenSubtitlesComProvider.list_subtitles = list_subtitles
    osc.OpenSubtitlesComProvider._make_query = _make_query
    osc.OpenSubtitlesComProvider._supersubber_patched = True


def _providers(cfg: dict, log: Log, tr: Tr):
    providers = list(BASE_PROVIDERS)
    provider_configs = {}
    from . import config as cfgmod
    user, pw = cfg.get("opensubtitles_user", ""), cfgmod.decrypt(cfg.get("opensubtitles_password", ""))
    if user and pw:
        providers.append("opensubtitlescom")
        provider_configs["opensubtitlescom"] = {"username": user, "password": pw}
    else:
        log(tr("c_no_login"))
    return providers, provider_configs


def _ensure_utf8(path: Path) -> bool:
    """alass liest nur UTF-8 — fremdkodierte Subs (cp1252, cp1251 …) in-place transkodieren.
    Liefert True, wenn die Datei umgeschrieben wurde."""
    raw = path.read_bytes()
    try:
        raw.decode("utf-8-sig")
        return False
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        text = str(best) if best else raw.decode("cp1252", errors="replace")
    except ImportError:
        text = raw.decode("cp1252", errors="replace")
    path.write_text(text, encoding="utf-8")
    return True


def _process_video(pool, video: Path, langs: list[str], tmp: Path, res: Result,
                   log: Log, tr: Tr, cancel: threading.Event, imdb_id: str | None = None,
                   subprog: Callable[[float], None] | None = None):
    from babelfish import Language
    from subliminal import refine, save_subtitles, scan_video
    from subliminal.video import Episode

    sp = subprog or (lambda f: None)
    got: dict[str, Path] = {}
    try:
        sp(0.03)
        v = scan_video(str(video))
        refine(v, refiners=("hash",))
        sp(0.1)
        if imdb_id:
            # imdb_id geht in die Provider-Query; bei Episoden zusätzlich als Serien-ID fürs Matching
            v.imdb_id = imdb_id
            if isinstance(v, Episode):
                v.series_imdb_id = imdb_id
        want = {Language.fromietf(l) for l in langs}
        found = pool.list_subtitles(v, want)
        sp(0.25)
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
                rel = getattr(s, "release", None) or getattr(s, "info", None) or s.id
                log(tr("c_got", lang=s.language.alpha2, rel=rel, prov=s.provider_name))
                _ensure_utf8(p)
                got[s.language.alpha2] = p
                want.discard(s.language)
        sp(0.35)
    except Exception as e:  # noqa: BLE001
        log(tr("c_dl_err", err=f"{type(e).__name__}: {e}"))

    for lang in langs:
        if cancel.is_set():
            break
        dl = got.get(lang)
        if not dl or not dl.exists():
            if imdb_id:
                log(tr("c_imdb_none", name=video.name, lang=lang))
            else:
                log(tr("c_not_found", lang=lang))
            res.missing.append(f"{video.name}  [{lang}]")
            res.missing_items.append((str(video), lang))
            continue
        out = video.with_name(f"{video.stem}.{lang}{dl.suffix.lower()}")
        log(tr("c_syncing"))
        ok, suspect = _alass(video, dl, out, log, tr, subprog=lambda f: sp(0.4 + 0.58 * f))
        if ok and suspect:
            res.suspect.append(f"{video.name}  [{lang}]")
            res.suspect_items.append((str(video), lang))
        elif ok:
            res.synced.append(f"{video.name}  [{lang}]")
        else:
            shutil.copyfile(dl, out)
            res.unsynced.append(f"{video.name}  [{lang}]")
            log(tr("c_sync_fail"))
    sp(1.0)


def run(folder: str, languages: list[str], cfg: dict, progress: Progress, log: Log,
        cancel: threading.Event, tr: Tr = _tr_fallback, frac: Frac | None = None,
        imdb_id: str | None = None) -> Result:
    res = Result()
    try:
        return _run(folder, languages, cfg, progress, log, cancel, tr, frac, imdb_id, res)
    except Exception as e:  # noqa: BLE001 — alles in der GUI anzeigen statt stumm sterben
        res.error = f"{type(e).__name__}: {e}"
        return res


def _run(folder, languages, cfg, progress, log, cancel, tr, frac, imdb_id, res: Result) -> Result:
    from subliminal import ProviderPool

    _region_setup()
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

    providers, provider_configs = _providers(cfg, log, tr)
    tmp = Path(tempfile.mkdtemp(prefix="supersubber-"))
    try:
        with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
            total = len(todo)
            for i, (video, langs) in enumerate(todo, 1):
                if cancel.is_set():
                    res.cancelled = True
                    break
                progress(f"{video.name}", i, total)
                log(f"[{i}/{total}] {video.name}  [{', '.join(langs)}]")
                sp = (lambda base: (lambda f: frac(min(1.0, (base + f) / total))))(i - 1) if frac else None
                _process_video(pool, video, langs, tmp, res, log, tr, cancel,
                               imdb_id=imdb_id, subprog=sp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return res


def run_local(video_path: str, sub_path: str, lang: str, cfg: dict, progress: Progress, log: Log,
              cancel: threading.Event, tr: Tr = _tr_fallback, frac: Frac | None = None) -> Result:
    """Vorhandenes Untertitel-File gegen ein Video syncen (kein Download).
    Ziel ist immer <Video>.<lang>.<ext>; ein dort liegendes File wird einmalig als *.orig gesichert."""
    res = Result()
    try:
        video, sub = Path(video_path), Path(sub_path)
        if not can_write(video.parent):
            res.noaccess.append(str(video.parent))
            log(tr("c_no_write", folder=video.parent.name or str(video.parent)))
            return res
        target = video.with_name(f"{video.stem}.{lang}{sub.suffix.lower()}")
        tmpdir: Path | None = None
        try:
            source = sub
            if os.path.normcase(str(sub)) == os.path.normcase(str(target)):
                orig = Path(str(target) + ".orig")
                if orig.exists():
                    import time
                    orig = Path(str(target) + f".orig-{time.strftime('%Y%m%d-%H%M%S')}")
                sub.rename(orig)
                log(tr("c_backup", name=orig.name))
                source = orig
            elif target.exists():
                orig = Path(str(target) + ".orig")
                if not orig.exists():
                    target.rename(orig)
                    log(tr("c_backup", name=orig.name))
            # alass erkennt das Format an der Endung und liest nur UTF-8 → immer über eine
            # temporäre Kopie mit echter Endung gehen, nötigenfalls transkodiert (Original bleibt unberührt)
            tmpdir = Path(tempfile.mkdtemp(prefix="supersubber-"))
            src = tmpdir / sub.name
            shutil.copyfile(source, src)
            _ensure_utf8(src)
            progress(video.name, 1, 1)
            log(f"[1/1] {video.name}  [{lang}]  ←  {sub.name}")
            log(tr("c_syncing"))
            sp = (lambda f: frac(min(1.0, 0.03 + 0.97 * f))) if frac else None
            ok, suspect = _alass(video, src, target, log, tr, subprog=sp)
            if ok and suspect:
                res.suspect.append(f"{video.name}  [{lang}]")
                res.suspect_items.append((str(video), lang))
            elif ok:
                res.synced.append(f"{video.name}  [{lang}]")
            else:
                shutil.copyfile(src, target)
                res.unsynced.append(f"{video.name}  [{lang}]")
                log(tr("c_sync_fail"))
            if frac:
                frac(1.0)
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"
    return res


def run_imdb(entries: list[tuple[str, list[str], str]], cfg: dict, progress: Progress, log: Log,
             cancel: threading.Event, tr: Tr = _tr_fallback, frac: Frac | None = None) -> Result:
    """Nachsuche per IMDb-ID: entries = [(Videopfad, Sprachen, tt-ID), …]."""
    res = Result()
    try:
        from subliminal import ProviderPool
        _region_setup()
        providers, provider_configs = _providers(cfg, log, tr)
        tmp = Path(tempfile.mkdtemp(prefix="supersubber-"))
        try:
            with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
                total = len(entries)
                for i, (path, langs, ttid) in enumerate(entries, 1):
                    if cancel.is_set():
                        res.cancelled = True
                        break
                    video = Path(path)
                    progress(f"{video.name}", i, total)
                    log(tr("c_imdb_via", id=ttid, name=video.name))
                    sp = (lambda base: (lambda f: frac(min(1.0, (base + f) / total))))(i - 1) if frac else None
                    _process_video(pool, video, langs, tmp, res, log, tr, cancel,
                                   imdb_id=ttid, subprog=sp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"
    return res
