"""Kernablauf: Videos finden → fehlende Subs via subliminal laden → mit alass gegen die Tonspur syncen."""
from __future__ import annotations

import logging
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

_LOG = logging.getLogger("supersubber.core")   # Details für die Logdatei, nicht fürs Fenster
VIDEO_EXT = frozenset({".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv"})
SUB_EXT = (".srt", ".ass", ".ssa")
# Provider ohne Zugangsdaten; opensubtitlescom kommt dazu, sobald ein Login konfiguriert ist
# podnapisi seit März 2026 tot; napiprojekt (pl), subtitulamos (es/en, Serien) und subtis (es, Filme) kosten nichts —
# subliminal fragt einen Provider nur, wenn er eine der gewählten Sprachen führt
BASE_PROVIDERS = ["gestdown", "tvsubtitles", "bsplayer", "opensubtitles", "napiprojekt", "subtitulamos", "subtis"]
LOGIN_PROVIDERS = ["opensubtitlescom"]                                       # nur mit Zugangsdaten
# Host + Port, den jeder Provider anspricht — für die Erreichbarkeitsprüfung
PROVIDER_HOSTS = {
    "opensubtitles": ("api.opensubtitles.org", 443),
    "opensubtitlescom": ("api.opensubtitles.com", 443),
    "gestdown": ("api.gestdown.info", 443),
    "tvsubtitles": ("www.tvsubtitles.net", 443),
    "bsplayer": ("s1.api.bsplayer-subtitles.com", 80),
    "napiprojekt": ("napiprojekt.pl", 443),
    "subtitulamos": ("www.subtitulamos.tv", 443),
    "subtis": ("api.subt.is", 443),
}
PROVIDER_ALT_HOSTS = {"bsplayer": ["s3.api.bsplayer-subtitles.com", "s102.api.bsplayer-subtitles.com"]}  # Provider würfelt Subdomains
PROVIDER_LABELS = {"opensubtitles": "OpenSubtitles.org", "opensubtitlescom": "OpenSubtitles.com",
                   "gestdown": "Gestdown (Addic7ed)", "tvsubtitles": "TVsubtitles", "bsplayer": "BSplayer",
                   "napiprojekt": "NapiProjekt (pl)", "subtitulamos": "Subtitulamos (es)", "subtis": "Subtis (es)"}
PROBE_TTL = 600           # Sekunden, die ein Prüfergebnis gilt
_probe_cache: dict = {"time": 0.0, "status": {}}
_probe_lock = threading.Lock()


def probe_providers(timeout: float = 4.0) -> dict[str, tuple[bool, str]]:
    """Erreichbarkeit aller bekannten Provider parallel prüfen: DNS + TCP-Verbindung. Ergebnis
    name → (erreichbar, Detail) und im Cache abgelegt; ein toter Provider kostet sonst je Video die Timeouts."""
    import socket
    import time as _time
    result: dict[str, tuple[bool, str]] = {}

    def check(name: str, host: str, port: int) -> None:
        last = "no address"
        for h in [host] + PROVIDER_ALT_HOSTS.get(name, []):
            try:
                infos = socket.getaddrinfo(h, port, type=socket.SOCK_STREAM)
            except socket.gaierror as e:
                last = f"DNS: {e.strerror or e}"
                continue
            for family, stype, proto, _, addr in infos[:2]:
                try:
                    with socket.socket(family, stype, proto) as s:
                        s.settimeout(timeout)
                        s.connect(addr)
                    result[name] = (True, addr[0])
                    return
                except OSError as e:
                    last = f"connect: {e.strerror or e}"
        result[name] = (False, last)

    threads = [threading.Thread(target=check, args=(n, h, p), daemon=True) for n, (h, p) in PROVIDER_HOSTS.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 1)
    for n in PROVIDER_HOSTS:
        result.setdefault(n, (False, "timeout"))
    with _probe_lock:
        _probe_cache["time"] = _time.time()
        _probe_cache["status"] = dict(result)
    _LOG.info("provider probe: %s", {k: ("ok" if v[0] else v[1]) for k, v in result.items()})
    return result


def provider_status(max_age: float = PROBE_TTL) -> dict[str, tuple[bool, str]]:
    """Letztes Prüfergebnis; älter als max_age → neu prüfen (dauert höchstens ein paar Sekunden)."""
    import time as _time
    with _probe_lock:
        fresh = _probe_cache["status"] and _time.time() - _probe_cache["time"] < max_age
        status = dict(_probe_cache["status"])
    return status if fresh else probe_providers()

MIN_CUES_PER_MIN = 3     # darunter gilt ein Sub als Forced/unvollständig (Serien liegen bei 10–15/min)
MAX_ATTEMPTS = 3         # Kandidaten pro Sprache, bevor aufgegeben wird
RELEASE_GROUP_BONUS = 40 # Sub-Release-Name enthält die Release-Gruppe des Videos (< Jahr-Gewicht 54)

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
    insync: list[str] = field(default_factory=list)     # hineingezogen und schon synchron → nichts angefasst
    failed: list[str] = field(default_factory=list)     # hineingezogen, Sync mit Fehler abgebrochen: „Name — Fehler"
    novideo: list[str] = field(default_factory=list)    # hineingezogen, aber kein Video mit diesem Namen
    suspect_items: list[tuple[str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_items: list[tuple[str, str]] = field(default_factory=list)   # (Videopfad, Sprachkürzel)
    noaccess: list[str] = field(default_factory=list)   # Ordner ohne Schreibrecht
    skipped: int = 0
    cancelled: bool = False
    error: str | None = None


_SAMPLE_RE = re.compile(r"(^|[.\-_ ])sample([.\-_ ]|$)", re.IGNORECASE)


def video_exts(cfg: dict | None) -> frozenset:
    """Standard-Endungen plus die aus den Settings („hevc, .vp9" → .hevc, .vp9)."""
    extra = str((cfg or {}).get("video_extensions_extra", "") or "")
    more = {"." + t.strip().lstrip(".").lower() for t in re.split(r"[,\s;]+", extra) if t.strip().lstrip(".")}
    return VIDEO_EXT | frozenset(more)


def _is_video(p: Path, min_size_mb: int, exts: frozenset = VIDEO_EXT) -> bool:
    """Videodatei ab Mindestgröße; Release-Samples („…-sample.mkv", „Sample\…") werden übersprungen —
    die wären bei 2160p groß genug, bekämen aber die Subs der ganzen Folge."""
    if p.suffix.lower() not in exts:
        return False
    if _SAMPLE_RE.search(p.stem) or p.parent.name.lower() == "sample":
        return False
    try:
        return p.stat().st_size >= min_size_mb * 1024 * 1024
    except OSError:
        return False


def find_videos(folder: str, min_size_mb: int, exts: frozenset = VIDEO_EXT) -> list[Path]:
    out = []
    for root, _, files in os.walk(folder):
        for f in files:
            p = Path(root) / f
            if _is_video(p, min_size_mb, exts):
                out.append(p)
    return sorted(out)


def video_for_sub(sub: Path, exts: frozenset = VIDEO_EXT, extra: tuple = ()) -> Path | None:
    """Das Video im selben Ordner, zu dem ein Untertitel dem Namen nach gehört: `Film.en.srt`, `Film.srt`,
    `Film.en.sdh.unsynced.srt` → `Film.mkv`. Bei mehreren passenden Stämmen gewinnt der längste —
    `Show.S01E01.Part.2.en.srt` gehört zu `Show.S01E01.Part.2.mkv`, nicht zu `Show.S01E01.mkv`.
    None, wenn keines passt oder derselbe Stamm mit zwei Endungen vorliegt; dann entscheidet der Nutzer.
    Ohne Mindestgröße: der Name ist eindeutig genug, auch für kurze Clips (Testkees, 2026-10-03)."""
    name = sub.name.lower()
    best: list[Path] = []
    try:
        # extra: mit hineingezogene Videos, die auch in einem anderen Ordner liegen dürfen
        pool = {Path(os.path.normcase(str(p))): p for p in list(sub.parent.iterdir()) + [Path(x) for x in extra]}
        for p in pool.values():
            if p.suffix.lower() not in exts or not p.is_file():
                continue
            stem = p.stem.lower()
            if not name.startswith(stem + "."):
                continue
            if not best or len(stem) > len(best[0].stem):
                best = [p]
            elif len(stem) == len(best[0].stem):
                best.append(p)
    except OSError:
        return None
    return best[0] if len(best) == 1 else None


def count_videos(folder: str, min_size_mb: int, limit: int = 2, exts: frozenset = VIDEO_EXT) -> int:
    """Zählt Videos, bricht bei `limit` ab (fürs GUI: „genau eines?")."""
    n = 0
    for root, _, files in os.walk(folder):
        for f in files:
            if _is_video(Path(root) / f, min_size_mb, exts):
                n += 1
                if n >= limit:
                    return n
    return n


_SKIP_TOKENS = {"forced", "hi", "sdh", "cc", "default", "unsynced"}   # Zusätze in Sub-Dateinamen, keine Sprachen
_SDH_TOKENS = {"sdh", "hi", "cc"}                         # Kennzeichen für Untertitel für Hörgeschädigte
IN_SYNC_MAX_SHIFT = 0.1                                   # Sekunden; darunter gilt ein hineingezogener Untertitel als schon synchron
UNSYNCED_TAG = "unsynced"                                 # <Video>.<lang>.unsynced.srt = roher Download, zählt nie als vorhanden
SDH_TAG = "sdh"                                           # <Video>.<lang>.sdh.srt


def _lang_from_token(tok: str) -> str | None:
    """Sprachkürzel aus einem Dateinamens-Token: en, eng, English, pt-BR … → alpha2 bzw. xx-XX; sonst None."""
    from babelfish import Language
    t = tok.strip()
    if not t or t.lower() in _SKIP_TOKENS:
        return None
    for fn in (Language.fromietf, Language.fromalpha3b, Language.fromname):
        try:
            lang = fn(t if fn is not Language.fromname else t.capitalize())
            if lang.alpha3 == "und":
                return None
            return lang.alpha2 + (f"-{lang.country.alpha2}" if lang.country else "")
        except Exception:  # noqa: BLE001
            continue
    return None


def _detect_language(sub: Path) -> str | None:
    """Sprache aus dem Text erkennen (charset-normalizer, für Untertitel-Längen zuverlässig)."""
    try:
        from babelfish import Language
        from charset_normalizer import from_path
        best = from_path(str(sub)).best()
        name = getattr(best, "language", "") if best else ""
        if not name or name == "Unknown":
            return None
        return Language.fromname(name).alpha2
    except Exception:  # noqa: BLE001
        return None


def external_subs(video: Path, kind: str = "any") -> dict[str, tuple[Path, str]]:
    """Untertitel-Dateien neben dem Video: lang → (Datei, Quelle). Quelle „tag" bei `Film.en.srt`, `Film.eng.srt`,
    `Film.English.srt`; „detected" bei `Film.srt` ohne Kürzel, dann per Textanalyse. Forced-Subs und der
    aufbewahrte rohe Download (`Film.en.unsynced.srt`) zählen nicht.
    kind: „any" = jede Datei zählt; „normal" = nur ohne SDH-Kennzeichen; „sdh" = nur mit `sdh`, `hi` oder `cc`."""
    out: dict[str, tuple[Path, str]] = {}
    stem = video.stem
    try:
        entries = list(video.parent.iterdir())
    except OSError:
        return out
    for p in sorted(entries):
        if p.suffix.lower() not in SUB_EXT or not p.name.startswith(stem):
            continue
        rest = p.name[len(stem):-len(p.suffix)]
        tokens = [t for t in re.split(r"[.\-_ ]+", rest) if t]
        low = {t.lower() for t in tokens}
        if low & {"forced", UNSYNCED_TAG}:
            continue
        lang = next((l for l in (_lang_from_token(t) for t in tokens) if l), None)
        sdh = bool(lang) and bool(low & _SDH_TOKENS)
        if kind != "any" and sdh != (kind == "sdh"):
            continue
        if lang:
            out.setdefault(lang, (p, "tag"))
        elif not tokens:
            det = _detect_language(p)
            if det:
                out.setdefault(det, (p, "detected"))
            else:
                out.setdefault("?", (p, "unknown"))
    return out


def embedded_subs(video: Path, kind: str = "any") -> dict[str, str]:
    """Eingebettete Untertitelspuren: lang → Codec. Forced-Spuren und Spuren ohne Sprachkennung zählen nicht.
    kind wie bei external_subs; SDH = Disposition hearing_impaired oder „SDH" im Spurtitel."""
    return _embedded_pick(_embedded_streams(video), kind)


def _embedded_streams(video: Path) -> list:
    """Rohdaten der Untertitelspuren aus ffprobe — einmal lesen, mehrfach auswerten."""
    import json
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run([_bin("ffprobe"), "-v", "error", "-select_streams", "s", "-show_entries",
                            "stream=codec_name,disposition:stream_tags=language,title", "-of", "json", str(video)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags)
        return json.loads(r.stdout or "{}").get("streams", [])
    except (OSError, ValueError):
        return []


def _embedded_pick(streams: list, kind: str = "any") -> dict[str, str]:
    from babelfish import Language
    out: dict[str, str] = {}
    for s in streams:
        tags = s.get("tags") or {}
        title = str(tags.get("title", "")).lower()
        if (s.get("disposition") or {}).get("forced") or "forced" in title:
            continue
        sdh = bool((s.get("disposition") or {}).get("hearing_impaired")) or bool(re.search(r"\bsdh\b", title))
        if kind != "any" and sdh != (kind == "sdh"):
            continue
        code = str(tags.get("language", "")).strip()
        if not code or code == "und":
            continue
        try:
            lang = Language.fromalpha3b(code).alpha2
        except Exception:  # noqa: BLE001
            continue
        out.setdefault(lang, str(s.get("codec_name", "")))
    return out


def has_sub(video: Path, lang: str) -> bool:
    return lang in external_subs(video)


def can_write(directory: Path) -> bool:
    probe = directory / f".supersubber-{uuid.uuid4().hex[:8]}.tmp"
    try:
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def _bin(name: str) -> str:
    """Pfad zum gebündelten Programm: Windows mit .exe, Linux ohne — dort wird das Ausführungsrecht sichergestellt,
    falls es beim Entpacken verloren ging."""
    p = bin_dir() / (name + ".exe" if sys.platform == "win32" else name)
    if sys.platform != "win32" and p.exists() and not os.access(p, os.X_OK):
        try:
            p.chmod(p.stat().st_mode | 0o755)
        except OSError:
            pass
    return str(p)


def _duration_min(video: Path) -> float:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run([_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(video)], capture_output=True, text=True, creationflags=flags)
        return float(r.stdout.strip()) / 60
    except (OSError, ValueError):
        return 0.0


def _cue_count(sub: Path) -> int:
    try:
        return sub.read_text(encoding="utf-8", errors="replace").count("-->")
    except OSError:
        return 0


def _kill_tree(proc: subprocess.Popen) -> None:
    """alass samt seinem ffmpeg beenden — ein verwaistes ffmpeg hielte sonst die Videodatei offen."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _alass(video: Path, sub: Path, out: Path, log: Log, tr: Tr = _tr_fallback,
           subprog: Callable[[float], None] | None = None,
           cancel: threading.Event | None = None, info: dict | None = None) -> tuple[bool, bool]:
    """Sync ausführen; alass-Fortschritt (Audio-Analyse) wird live an subprog (0..1) gemeldet.
    info bekommt, was alass getan hat: blocks, max_shift in Sekunden, ratio_one.
    Rückgabe: (erfolgreich, verdächtig) — verdächtig = mehrere Blöcke um Minuten verschoben.
    Wird cancel gesetzt, endet alass sofort; eine dabei entstandene Ausgabedatei wird entfernt."""
    env = dict(os.environ, ALASS_FFMPEG_PATH=_bin("ffmpeg"), ALASS_FFPROBE_PATH=_bin("ffprobe"))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    existed = out.exists()
    try:
        proc = subprocess.Popen([_bin("alass-cli"), str(video), str(sub), str(out)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", creationflags=flags,
                                start_new_session=sys.platform != "win32")
    except OSError as e:
        log(f"    alass: {e}")
        return False, False
    if cancel is not None:
        def watch():
            while proc.poll() is None:
                if cancel.wait(0.2):
                    _kill_tree(proc)
                    return
        threading.Thread(target=watch, daemon=True).start()
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
    if cancel is not None and cancel.is_set():
        _LOG.info("alass %s: cancelled by user", video.name)
        if not existed:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass
        return False, False
    _LOG.debug("alass %s <- %s (exit %s): %s", video.name, sub.name, proc.returncode,
               " | ".join(l.strip() for l in lines if not re.match(r"\s*\d+ / \d+ \[", l)))
    big_shifts = 0
    blocks, max_shift, ratio_one = 0, 0.0, False
    for line in lines:
        if re.search(r"shifted|ratio is|error", line):
            log("    " + line.strip())
        r = re.search(r"ratio is ([\d.]+)", line)
        if r:
            ratio_one = float(r.group(1).rstrip(".") or 0) == 1.0
        m = re.search(r"by (-?)(\d+):(\d\d):(\d\d)\.(\d+)", line)
        if m:
            blocks += 1
            shift = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4)) + float("0." + m.group(5))
            max_shift = max(max_shift, shift)
        if m and int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4)) > 300:
            big_shifts += 1
    if info is not None:
        info.update(blocks=blocks, max_shift=max_shift, ratio_one=ratio_one)
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
    disabled = set(cfg.get("providers_disabled") or [])
    off = [p for p in providers if p in disabled]
    providers = [p for p in providers if p not in disabled]
    status = provider_status()
    down = []
    for p in list(providers):
        ok, detail = status.get(p, (True, ""))
        if not ok:
            _LOG.info("provider %s unreachable (%s): %s", p, PROVIDER_HOSTS[p][0], detail)
            down.append(p)
            providers.remove(p)
    # gleich gebaute Zeilen für alle Fälle; auch nennen, was funktioniert — nur die Ausfälle zu zeigen
    # sieht aus, als ginge gar nichts (Cosmo, 2026-10-01). Der Host steht in der Logdatei
    label = lambda p: PROVIDER_LABELS.get(p, p).split(" (")[0]   # noqa: E731 — ohne Zusatz in Klammern
    for key, group in (("c_providers_on", providers), ("c_providers_down", down), ("c_providers_off", off)):
        if group:
            log(tr(key, names=", ".join(label(p) for p in group)))
    _LOG.debug("providers: %s (disabled=%s)", providers, sorted(disabled))
    return providers, provider_configs


_IMDB_RE = re.compile(r"tt\d{7,10}")


def _imdb_from_nfo(video: Path, episode: bool, exts: frozenset = VIDEO_EXT) -> str | None:
    """IMDb-ID aus NFO-Dateien neben dem Video (Release-NFOs enthalten fast immer den IMDb-Link,
    Kodi-NFOs die ID strukturiert). Filme: NFO mit gleichem Stamm bevorzugt, sonst jede NFO im Ordner.
    Serien: nur tvshow.nfo (Ordner oder Elternordner) — Episoden-NFOs tragen die Episoden-ID, nicht die Serie."""
    if episode:
        cands = [video.parent / "tvshow.nfo", video.parent.parent / "tvshow.nfo"]
    else:
        same = video.with_suffix(".nfo")
        cands = [same]
        # andere NFOs nur, wenn das Video allein im Ordner liegt — sonst bekäme jeder Film die ID des Nachbarn
        try:
            alone = sum(1 for p in video.parent.iterdir() if p.suffix.lower() in exts) == 1
        except OSError:
            alone = False
        if alone:
            cands += sorted(p for p in video.parent.glob("*.nfo") if p != same)
    for nfo in cands:
        try:
            if not nfo.is_file() or nfo.stat().st_size > 512_000:
                continue
            m = _IMDB_RE.search(nfo.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(0)
        except OSError:
            continue
    return None


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


@dataclass
class Item:
    """Ein Video im Vorlauf: erkannt, gesucht, bewertet — noch nichts geladen."""
    video: Path
    langs: list[str]                                  # Sprachen, die noch fehlen (leer = alles vorhanden)
    v: object = None                                  # subliminal-Video (guessit + Hash)
    recognized: str = ""                              # „Whistle · 2025" / „Silo · S03E10"
    imdb_id: str | None = None
    imdb_source: str = ""                             # "nfo" | "manual" | ""
    candidates: list = field(default_factory=list)    # Provider-Kandidaten aller Sprachen
    min_score: int = 0
    group: str = ""                                   # Release-Gruppe des Rips
    found: dict = field(default_factory=dict)         # lang → True/False (Kandidat über Schwelle)
    status: dict = field(default_factory=dict)        # lang → present|embedded|found|none|synced|suspect|unsynced|missing
    existing: dict = field(default_factory=dict)      # lang → Herkunft: "file", "detected", "embedded"
    error: str | None = None
    # Nur mit der Option „SDH zusätzlich": normal und SDH werden je Sprache getrennt geführt
    split: bool = False
    streams: list | None = None                       # ffprobe-Daten der Untertitelspuren, einmal gelesen
    sdh_langs: list = field(default_factory=list)     # Sprachen, für die eine SDH-Fassung gesucht wird
    sdh_found: dict = field(default_factory=dict)     # lang → True/False
    sdh_status: dict = field(default_factory=dict)    # lang → present|embedded|found|synced|suspect|unsynced; fehlt = nichts zu melden
    hit_films: dict = field(default_factory=dict)     # lang oder „lang SDH" → (Titel, Jahr) des besten Treffers

    @property
    def wanted(self) -> bool:
        """Für dieses Video wird gesucht — normal oder SDH."""
        return bool(self.langs or self.sdh_langs)

    @property
    def settled(self) -> bool:
        """Nichts zu tun: alle Sprachen vorhanden und keine SDH-Fassung in Aussicht."""
        return not self.langs and not any(self.sdh_found.get(l) for l in self.sdh_langs)


@dataclass
class Scan:
    folder: str
    languages: list[str]
    items: list = field(default_factory=list)         # list[Item]
    noaccess: list[str] = field(default_factory=list)
    cancelled: bool = False
    error: str | None = None
    use_embedded: bool = True                         # Einstellungen, mit denen der Vorlauf lief
    split: bool = False

    @property
    def skipped(self) -> int:
        return sum(1 for it in self.items if it.settled)

    @property
    def runnable(self) -> list:
        return [it for it in self.items if any(it.found.get(l) for l in it.langs)
                or any(it.sdh_found.get(l) for l in it.sdh_langs)]


def _se(v) -> str:
    """„S04E10", bei Doppelfolgen „S04E10E11" — guessit liefert die Nummern als Liste."""
    if getattr(v, "season", None) is None or getattr(v, "episode", None) is None:
        return ""
    eps = getattr(v, "episodes", None) or [v.episode]
    return f"S{v.season:02d}" + "".join(f"E{e:02d}" for e in eps)


def _recognized(v) -> str:
    from subliminal.video import Episode
    if isinstance(v, Episode):
        return " · ".join(x for x in (v.series, _se(v)) if x)
    year = getattr(v, "year", None)
    return " · ".join(x for x in (getattr(v, "title", None), str(year) if year else "") if x)


ID_PROVIDERS = {"opensubtitles", "opensubtitlescom"}   # suchen bei gesetzter IMDb-ID gezielt nach dieser ID


def _imdb_num(x) -> int | None:
    m = re.search(r"(\d+)", str(x or ""))
    return int(m.group(1)) if m else None


def _id_match(sub, imdb_id: str, episode: bool) -> bool:
    """Stammt dieser Treffer wirklich von der IMDb-ID? Die ID-Provider mischen ID-Suche und Namenssuche —
    „The Whispers S01E06 The Archer" kam bei Archer S01E06 aus der Namenssuche (Testkees, 2026-09-26).
    .org markiert ID-Treffer mit matched_by=imdbid; .com trägt movie_imdb_id bzw. series_imdb_id."""
    want = _imdb_num(imdb_id)
    if sub.provider_name == "opensubtitles":
        if getattr(sub, "matched_by", "") == "imdbid":
            return True
        return not episode and _imdb_num(getattr(sub, "movie_imdb_id", None)) == want
    if sub.provider_name == "opensubtitlescom":
        field = "series_imdb_id" if episode else "movie_imdb_id"
        return _imdb_num(getattr(sub, field, None)) == want
    return False


def _score_fn(v, imdb_id: str | None = None):
    """Bewertung wie subliminal, plus Bonus für die Release-Gruppe des Rips (…-SHORTBREHD im
    Sub-Release-Namen → für exakt diesen Schnitt getimt). Bonus < Jahr-Gewicht, hebt also keinen
    Kandidaten mit falschem Jahr über die Schwelle.
    Mit IMDb-ID: Bei Providern, die per ID suchen, gilt der Titel-/Serien-Treffer als erfüllt — der aus
    dem Dateinamen geratene Titel darf dann nicht mehr blockieren (Ordner „Leonor…" mit MobLand-Folgen)."""
    from subliminal.score import compute_score, episode_scores, movie_scores
    from subliminal.video import Episode
    group = (getattr(v, "release_group", None) or "").lower()

    def score(sub, vid, **kw):
        s_ = compute_score(sub, vid, **kw)
        rel = str(getattr(sub, "release", None) or getattr(sub, "info", None) or "").lower()
        if group and len(group) >= 3 and group in rel:
            s_ += RELEASE_GROUP_BONUS
        if imdb_id and sub.provider_name in ID_PROVIDERS and _id_match(sub, imdb_id, isinstance(vid, Episode)):
            matches = sub.get_matches(vid)
            if "hash" in matches:
                return s_
            if isinstance(vid, Episode):
                if "series" not in matches and {"season", "episode"} <= matches:
                    s_ += episode_scores["series"]
            elif "title" not in matches:
                s_ += movie_scores["title"] + movie_scores["year"]
        return s_
    return score


def _release_name(s) -> str:
    """Lesbarer Name eines Treffers fürs Log. gestdown klebt in subliminal 2.7.1 den Episodentitel ohne
    Leerzeichen an „s01e03" (Testkees, 2026-09-26) — dort selbst zusammensetzen."""
    if s.provider_name == "gestdown":
        parts = [f"{getattr(s, 'series', '')} S{int(getattr(s, 'season', 0) or 0):02d}E{int(getattr(s, 'episode', 0) or 0):02d}".strip()]
        parts += [str(x) for x in (getattr(s, "title", None), getattr(s, "release_group", None)) if x]
        return " · ".join(parts)
    return str(getattr(s, "release", None) or getattr(s, "info", None) or s.id)


def _pick(cands: list, split: bool, sdh: bool) -> list:
    """Kandidaten nach Art: ohne die SDH-Option zählt jeder; mit ihr trennt das Kennzeichen des Providers.
    Das Kennzeichen setzt der Uploader — ein Treffer ohne Kennzeichen gilt als normal."""
    if not split:
        return list(cands)
    return [s for s in cands if bool(getattr(s, "hearing_impaired", False)) == sdh]


def _hits(it: "Item") -> str:
    hits = [l for l in it.langs if it.found.get(l)] + [f"{l} SDH" for l in it.sdh_langs if it.sdh_found.get(l)]
    return ", ".join(hits) if hits else "—"


def _film_of(s) -> tuple[str, int] | None:
    """Titel und Jahr des Films, zu dem ein Treffer gehört — nur die OpenSubtitles-Provider liefern das."""
    title = getattr(s, "movie_title", None) or ""
    if not title:
        mn = str(getattr(s, "movie_name", "") or "")
        title = "" if mn.startswith('"') else mn
    year = getattr(s, "movie_year", None)
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    return (title.strip(), year) if title.strip() and year else None


def _apply_hit_year(it: "Item") -> None:
    """Film ohne Jahr im Dateinamen: das Jahr des Films nennen, dessen Untertitel geholt würde. „Die Hard"
    allein sagt nicht, welcher Film gemeint ist, Remakes tragen denselben Titel (Cosmo, 2026-10-01).
    Ein Treffer-Film für alle Sprachen: dessen Titel und Jahr. Verschiedene Filme je Sprache: alle Jahre —
    genau das soll man sehen, um es per IMDb-ID zu korrigieren. Mit IMDb-ID gilt deren Titel, wie bisher."""
    from subliminal.video import Episode
    v = it.v
    if v is None or isinstance(v, Episode) or it.imdb_id or getattr(v, "year", None):
        return
    films = {f for f in it.hit_films.values() if f}
    base = _recognized(v)
    if len(films) == 1:
        title, year = next(iter(films))
        it.recognized = f"{title} · {year}"
    elif films:
        it.recognized = f"{base} · " + " / ".join(str(y) for y in sorted({y for _, y in films}))
    else:
        it.recognized = base


def _title_from_candidates(cands: list, episode: bool) -> str:
    """Titel aus den Provider-Treffern (häufigster Wert) — die kennen den Film/die Serie zur IMDb-ID.
    opensubtitlescom: series_title/movie_title; opensubtitles: movie_name („\"MobLand\" Stick or Twist");
    gestdown: series."""
    from collections import Counter
    names: Counter = Counter()
    for s in cands:
        n = ""
        if episode:
            if s.provider_name == "opensubtitles":
                # .org: series_title ist hier irreführend der Episodentitel — der Serienname steht in movie_name
                m = re.match(r'^"([^"]+)"', str(getattr(s, "movie_name", "") or ""))
                n = m.group(1) if m else ""
            elif s.provider_name == "opensubtitlescom":
                n = getattr(s, "series_title", None) or ""
            else:
                n = getattr(s, "series", None) or ""
        else:
            n = getattr(s, "movie_title", None) or ""
            if not n:
                mn = str(getattr(s, "movie_name", "") or "")
                n = "" if mn.startswith('"') else mn
        if n:
            y = getattr(s, "movie_year", None)
            names[(n.strip(), y if not episode else None)] += 1
    if not names:
        return ""
    (name, year), _ = names.most_common(1)[0]
    return f"{name} · {year}" if year else name


def _name_complete(name: str) -> bool:
    """Sagt der Dateiname für sich schon alles? Serie: Titel, Staffel und Folge, der Titel vor der Folgenkennung —
    bei `S03E03 Alles auf Sieg.mkv` ist der Text dahinter der Episodentitel, nicht die Serie. Film: Titel und Jahr.
    Dann zählt nur der Dateiname, sonst der ganze Pfad: `S03E03.mkv`, `myMovie.mkv` und Scene-Kurznamen
    brauchen den Ordner."""
    try:
        from guessit import guessit
        g = guessit(name, {"advanced": True})
        title = g.get("title")
        if title is None or isinstance(title, list) or not str(title.value).strip():
            return False
        if g.get("type") is not None and g["type"].value == "episode":
            marks = [g.get("season"), g.get("episode")]
        else:
            marks = [g.get("year")]
        if any(m is None for m in marks):
            return False
        starts = [(m[0] if isinstance(m, list) else m).start for m in marks]
        return title.start < min(starts)
    except Exception:  # noqa: BLE001
        return False


def _scan_video(path: Path):
    """Wie subliminal.scan_video, aber auch für Endungen, die subliminal nicht kennt (z. B. .hevc, .vp9 aus den
    Settings): dann Erkennung aus dem Namen plus Dateigröße — der Hash rechnet ohnehin auf jeder Datei.
    Erkannt wird aus dem Dateinamen, wenn er vollständig ist, sonst aus dem ganzen Pfad. Ein Ordner mit eigenem
    Titel überstimmt die Datei sonst: For.All.Mankind.S03E03 im Ordner Leonor.Will.Never.Die.2022 (Cosmo, 2026-09-28)."""
    from subliminal import scan_video
    from subliminal.core import scan_name
    from subliminal.video import VIDEO_EXTENSIONS
    name = path.name if _name_complete(path.name) else None
    _LOG.debug("%s: recognized from %s", path.name, "file name" if name else "full path")
    if path.name.lower().endswith(VIDEO_EXTENSIONS):
        v = scan_video(str(path), name=name)
    else:
        v = scan_name(str(path), name=name)
        v.size = path.stat().st_size
    if name and not getattr(v, "release_group", None):
        # die Release-Gruppe steht oft nur im Ordner — übernehmen, wenn der Ordner dasselbe Werk meint
        whole = scan_name(str(path))
        same = lambda a, b: str(getattr(a, "series", None) or getattr(a, "title", "")).lower() == \
            str(getattr(b, "series", None) or getattr(b, "title", "")).lower()  # noqa: E731
        if type(whole) is type(v) and same(whole, v):
            v.release_group = getattr(whole, "release_group", None)
    return v


def _search_item(pool, it: Item, log: Log, tr: Tr, manual_id: str | None = None,
                 exts: frozenset = VIDEO_EXT, only: list | None = None) -> None:
    """Erkennen + NFO + Provider-Suche + Bewertung für ein Item. Lädt nichts herunter.
    only: nur diese Sprachen suchen und bewerten, alles Übrige am Item bleibt stehen — für Sprachen, die
    nach dem Vorlauf dazugewählt werden. Die Erkennung läuft dann nur, wenn sie noch fehlt."""
    from babelfish import Language
    from subliminal import refine
    from subliminal.score import episode_scores, movie_scores
    from subliminal.video import Episode

    fresh = only is None or it.v is None
    langs = [l for l in it.langs if only is None or l in only]
    sdh_langs = [l for l in it.sdh_langs if only is None or l in only]
    if only is None:
        it.candidates, it.found, it.sdh_found, it.hit_films = [], {}, {}, {}
    it.error = None
    for lang in sdh_langs:
        it.sdh_status.pop(lang, None)
    try:
        if fresh:
            v = _scan_video(it.video)
            refine(v, refiners=("hash",))
            it.v = v
            it.recognized = _recognized(v)
            _LOG.debug("%s: guessed %s %r size=%s hashes=%s", it.video.name, type(v).__name__, it.recognized,
                       getattr(v, "size", None), sorted((getattr(v, "hashes", None) or {}).keys()))
            if manual_id:
                it.imdb_id, it.imdb_source = manual_id, "manual"
            elif not it.imdb_id:
                nfo = _imdb_from_nfo(it.video, isinstance(v, Episode), exts)
                if nfo:
                    it.imdb_id, it.imdb_source = nfo, "nfo"
                    log(tr("c_imdb_nfo", id=nfo))
            if it.imdb_id:
                v.imdb_id = it.imdb_id
                if isinstance(v, Episode):
                    v.series_imdb_id = it.imdb_id
            # Mindest-Score: Serien Serie+Staffel+Episode, Filme Titel+Jahr (ohne Jahr im Namen nur Titel).
            # Hash- und IMDb-Treffer liegen darüber. Ohne Schwelle gewinnt jeder Titel-Teilstring.
            if isinstance(v, Episode):
                it.min_score = episode_scores["series"] + episode_scores["season"] + episode_scores["episode"]
            else:
                it.min_score = movie_scores["title"] + (movie_scores["year"] if getattr(v, "year", None) else 0)
        v = it.v
        want = {Language.fromietf(l) for l in langs + sdh_langs}
        it.candidates = list(it.candidates) + (list(pool.list_subtitles(v, want)) if want else [])
        if fresh and it.imdb_id:
            # mit ID zählt, was die Provider zur ID sagen — nicht der aus dem Pfad geratene Titel
            se = _se(v) if isinstance(v, Episode) else ""
            by_id = [s for s in it.candidates if _id_match(s, it.imdb_id, isinstance(v, Episode))]
            title = _title_from_candidates(by_id, isinstance(v, Episode)) or f"IMDb {it.imdb_id}"
            it.recognized = " · ".join(x for x in (title, se) if x)
            if manual_id and not it.recognized.startswith("IMDb "):
                it.recognized += f" · IMDb {manual_id}"
        score = _score_fn(v, it.imdb_id)
        _LOG.debug("%s: imdb=%s (%s) min_score=%d candidates=%d", it.video.name, it.imdb_id or "-",
                   it.imdb_source or "-", it.min_score, len(it.candidates))
        for s in sorted(it.candidates, key=lambda s: -score(s, v)):
            _LOG.debug("  cand %s %s id=%s score=%d matches=%s sdh=%s release=%r", s.provider_name, s.language,
                       s.id, score(s, v), sorted(s.get_matches(v)), bool(getattr(s, "hearing_impaired", False)),
                       _release_name(s))
        normal, sdh = _pick(it.candidates, it.split, False), _pick(it.candidates, it.split, True)
        def top(pool_, L):
            scored = [(score(s, v), s) for s in pool_ if s.language == L]
            return max(scored, key=lambda t: t[0], default=(0, None))

        for lang in langs:
            best, s_best = top(normal, Language.fromietf(lang))
            it.found[lang] = best >= it.min_score
            it.status[lang] = "found" if it.found[lang] else "none"
            it.hit_films[lang] = _film_of(s_best) if it.found[lang] else None
            _LOG.debug("%s: %s best=%d -> %s film=%s", it.video.name, lang, best, it.status[lang], it.hit_films[lang])
        for lang in sdh_langs:
            # eine fehlende SDH-Fassung ist kein Fehler: kein Status, keine Zeile
            best, s_best = top(sdh, Language.fromietf(lang))
            it.sdh_found[lang] = best >= it.min_score
            if it.sdh_found[lang]:
                it.sdh_status[lang] = "found"
            it.hit_films[f"{lang} SDH"] = _film_of(s_best) if it.sdh_found[lang] else None
            _LOG.debug("%s: %s SDH best=%d -> %s", it.video.name, lang, best, it.sdh_found[lang])
        _apply_hit_year(it)
    except Exception as e:  # noqa: BLE001
        _LOG.exception("%s: search failed", it.video.name)
        it.error = f"{type(e).__name__}: {e}"
        for lang in langs:
            it.found[lang] = False
            it.status[lang] = "none"
        for lang in sdh_langs:
            it.sdh_found[lang] = False
        log(tr("c_dl_err", err=it.error))


def _presence(it: Item, languages: list, use_embedded: bool, log: Log, tr: Tr, announce: bool = True) -> None:
    """Für diese Sprachen festhalten, was schon da ist — Datei neben dem Video oder eingebettete Spur — und was
    gesucht werden muss. Die ffprobe-Daten bleiben am Item, eine später dazugewählte Sprache braucht sie wieder."""
    v = it.video
    kind = "normal" if it.split else "any"
    ext = external_subs(v, kind)
    if it.streams is None:
        it.streams = _embedded_streams(v) if use_embedded else []
    emb = _embedded_pick(it.streams, kind)
    if it.split:
        ext_sdh, emb_sdh = external_subs(v, "sdh"), _embedded_pick(it.streams, "sdh")
        for l in languages:
            if l in ext_sdh:
                it.sdh_status[l] = "present"
            elif l in emb_sdh:
                it.sdh_status[l] = "embedded"
            else:
                it.sdh_langs.append(l)
        _LOG.debug("%s: sdh external=%s embedded=%s", v.name,
                   {k: p.name for k, (p, _) in ext_sdh.items()}, emb_sdh)
    _LOG.debug("%s: external=%s embedded=%s", v.name, {k: (p.name, how) for k, (p, how) in ext.items()}, emb)
    if announce:
        for lang, (p, how) in ext.items():
            if how == "detected":
                log(tr("c_detected", file=p.name, lang=lang))
            elif how == "unknown":
                log(tr("c_undetected", file=p.name))
    for l in languages:
        if l in ext and ext[l][1] != "unknown":
            it.existing[l] = ext[l][1] if ext[l][1] == "detected" else "file"
            it.status[l] = "present"
        elif l in emb:
            it.existing[l] = "embedded"
            it.status[l] = "embedded"
        else:
            it.langs.append(l)


def settle_done(sc: Scan) -> None:
    """Nach einem Lauf: was geladen wurde, liegt jetzt als Datei da — wie es ein neuer Vorlauf sähe.
    Übrig bleibt in runnable nur, was noch nicht geholt ist."""
    done = ("synced", "suspect", "unsynced")
    for it in sc.items:
        for langs_, found, status in ((it.langs, it.found, it.status), (it.sdh_langs, it.sdh_found, it.sdh_status)):
            for l in [l for l in langs_ if status.get(l) in done]:
                langs_.remove(l)
                found.pop(l, None)
                status[l] = "present"


def update_languages(sc: Scan, languages: list[str], cfg: dict, progress: Progress, log: Log,
                     cancel: threading.Event, tr: Tr = _tr_fallback) -> Scan:
    """Sprachauswahl nach dem Vorlauf geändert: abgewählte Sprachen fallen nur weg; für dazugewählte wird
    geprüft, was schon da ist, und nur für sie bei den Providern gesucht. Erkennung, Hash und die Treffer der
    übrigen Sprachen bleiben stehen. Bricht der Nutzer ab, ist sc.cancelled gesetzt und der Vorlauf unvollständig."""
    try:
        from subliminal import ProviderPool
        removed = [l for l in sc.languages if l not in languages]
        added = [l for l in languages if l not in sc.languages]
        _LOG.info("languages changed: added=%s removed=%s", added, removed)
        settle_done(sc)
        for it in sc.items:
            for l in removed:
                for d in (it.found, it.status, it.existing, it.sdh_found, it.sdh_status):
                    d.pop(l, None)
                it.hit_films.pop(l, None)
                it.hit_films.pop(f"{l} SDH", None)
                for lst in (it.langs, it.sdh_langs):
                    if l in lst:
                        lst.remove(l)
            if removed:
                _apply_hit_year(it)
        sc.languages = [l for l in sc.languages if l not in removed]
        if added:
            _region_setup()
            for it in sc.items:
                _presence(it, added, sc.use_embedded, log, tr, announce=False)
            todo = [it for it in sc.items if any(l in added for l in it.langs + it.sdh_langs)]
            log(tr("c_found", v=len(sc.items), t=sum(1 for it in todo if any(l in added for l in it.langs)),
                   langs=", ".join(added)))
            if todo:
                exts = video_exts(cfg)
                providers, provider_configs = _providers(cfg, log, tr)
                with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
                    for i, it in enumerate(todo, 1):
                        if cancel.is_set():
                            sc.cancelled = True
                            return sc
                        progress(it.video.name, i, len(todo))
                        _search_item(pool, it, log, tr, manual_id=it.imdb_id if it.imdb_source == "manual" else None,
                                     exts=exts, only=added)
                        log(tr("c_scan_item", name=it.video.name, rec=it.recognized or "?", hits=_hits(it)))
        sc.languages = list(languages)
        for it in sc.items:
            it.langs.sort(key=languages.index)
            it.sdh_langs.sort(key=languages.index)
    except Exception as e:  # noqa: BLE001
        _LOG.exception("language update failed")
        sc.error = f"{type(e).__name__}: {e}"
    return sc


def scan(folder: str, languages: list[str], cfg: dict, progress: Progress, log: Log,
         cancel: threading.Event, tr: Tr = _tr_fallback, files: list | None = None) -> Scan:
    """Vorlauf: Videos finden, erkennen, bei den Providern suchen, bewerten. Kein Download, kein Sync.
    files: nur diese Videodateien statt des ganzen Ordners — wer einzelne Dateien hineinzieht, meint nur sie.
    Eine Datei als folder gilt genauso."""
    if files is None and os.path.isfile(folder):
        files = [folder]
    sc = Scan(folder=folder, languages=list(languages))
    try:
        from subliminal import ProviderPool
        _region_setup()
        progress(tr("c_scan"), 0, 0)
        exts = video_exts(cfg)
        _LOG.info("scan %s files=%s languages=%s exts=%s", folder, files, languages, sorted(exts))
        if files is not None:
            # ausdrücklich gewählte Dateien: nur die Endung zählt, Mindestgröße und Sample-Filter gelten nicht
            videos = sorted({Path(f) for f in files if Path(f).suffix.lower() in exts and Path(f).is_file()})
        else:
            videos = find_videos(folder, int(cfg.get("min_size_mb", 50)), exts)
        if not videos:
            sc.error = tr("c_none")
            return sc
        writable: dict[Path, bool] = {}
        for v in videos:
            d = v.parent
            if d not in writable:
                writable[d] = can_write(d)
                if not writable[d]:
                    sc.noaccess.append(str(d))
                    log(tr("c_no_write", folder=d.name or str(d)))
        use_embedded = bool(cfg.get("embedded_counts", True))
        split = bool(cfg.get("sdh_extra", False))
        sc.use_embedded, sc.split = use_embedded, split
        for v in videos:
            if not writable[v.parent]:
                continue
            it = Item(video=v, langs=[], split=split)
            _presence(it, languages, use_embedded, log, tr)
            sc.items.append(it)
        todo = [it for it in sc.items if it.wanted]
        log(tr("c_found", v=len(videos), t=sum(1 for it in sc.items if it.langs), langs=", ".join(languages)))
        if not todo:
            return sc
        providers, provider_configs = _providers(cfg, log, tr)
        with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
            for i, it in enumerate(todo, 1):
                if cancel.is_set():
                    sc.cancelled = True
                    break
                progress(it.video.name, i, len(todo))
                _search_item(pool, it, log, tr, exts=exts)
                log(tr("c_scan_item", name=it.video.name, rec=it.recognized or "?", hits=_hits(it)))
    except Exception as e:  # noqa: BLE001
        sc.error = f"{type(e).__name__}: {e}"
    return sc


def rescan(items: list, imdb_id: str | None, cfg: dict, log: Log, cancel: threading.Event,
           tr: Tr = _tr_fallback, on_item: Callable | None = None) -> None:
    """Nachsuche für einzelne Items (aus der Tabelle): mit manueller IMDb-ID, oder ohne (ID entfernt →
    wieder Erkennung aus Dateiname/NFO). on_item meldet jedes fertige Item."""
    from subliminal import ProviderPool
    _region_setup()
    providers, provider_configs = _providers(cfg, log, tr)
    with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
        for it in items:
            if cancel.is_set():
                break
            if imdb_id:
                log(tr("c_imdb_via", id=imdb_id, name=it.video.name))
            else:
                it.imdb_id, it.imdb_source = None, ""
                log(tr("c_research", name=it.video.name))
            _search_item(pool, it, log, tr, manual_id=imdb_id, exts=video_exts(cfg))
            log(tr("c_scan_item", name=it.video.name, rec=it.recognized or "?", hits=_hits(it)))
            if on_item:
                on_item(it)


def _download_item(pool, it: Item, tmp: Path, log: Log, tr: Tr, sdh: bool = False) -> dict:
    """Beste Kandidaten laden (Qualitätsprüfung inklusive). Liefert lang → Datei.
    sdh=True lädt die SDH-Fassungen, in einen eigenen Unterordner — die Dateinamen wären sonst gleich."""
    from babelfish import Language
    from subliminal import save_subtitles

    got: dict[str, Path] = {}
    v = it.v
    langs, found = (it.sdh_langs, it.sdh_found) if sdh else (it.langs, it.found)
    want = {Language.fromietf(l) for l in langs if found.get(l)}
    if not want or v is None:
        return got
    cands = _pick(it.candidates, it.split, sdh)
    mark = " SDH" if sdh else ""
    if sdh:
        tmp = tmp / "sdh"
        tmp.mkdir(exist_ok=True)
    score = _score_fn(v, it.imdb_id)
    minutes = _duration_min(it.video)
    ignore: list[str] = []
    try:
        for _attempt in range(MAX_ATTEMPTS):
            if not want:
                break
            best = pool.download_best_subtitles(cands, v, want, min_score=it.min_score,
                                                subtitle_categories="n,hi,fo", ignore_subtitles=ignore,
                                                compute_score=score)
            if not best:
                break
            for s in save_subtitles(v, best, directory=str(tmp)):
                p = tmp / Path(s.get_path(v)).name
                cues = _cue_count(p)
                if minutes and cues / minutes < MIN_CUES_PER_MIN:
                    log(tr("c_discard", lang=s.language.alpha2 + mark, cues=cues,
                           mins=f"{minutes:.0f}", prov=s.provider_name))
                    ignore.append(s.id)
                    p.unlink(missing_ok=True)
                    continue
                rel = _release_name(s)
                log(tr("c_got", lang=s.language.alpha2 + mark, rel=rel, prov=s.provider_name))
                _LOG.info("%s: downloaded %s%s from %s id=%s score=%d cues=%d release=%r", it.video.name,
                          s.language, mark, s.provider_name, s.id, score(s, v), cues, rel)
                _ensure_utf8(p)
                got[s.language.alpha2] = p
                want.discard(s.language)
    except Exception as e:  # noqa: BLE001
        log(tr("c_dl_err", err=f"{type(e).__name__}: {e}"))
    return got


def run_scan(sc: Scan, cfg: dict, progress: Progress, log: Log, cancel: threading.Event,
             tr: Tr = _tr_fallback, frac: Frac | None = None) -> Result:
    """Phase 2: Download + Sync für alle Items mit Treffern. Items ohne Treffer werden als fehlend gezählt."""
    from subliminal import ProviderPool
    res = Result()
    res.noaccess = list(sc.noaccess)
    res.skipped = sc.skipped
    try:
        _region_setup()
        todo = [it for it in sc.items if it.langs]
        for it in todo:
            for lang in it.langs:
                if not it.found.get(lang):
                    it.status[lang] = "missing"
                    res.missing.append(f"{it.video.name}  [{lang}]")
                    res.missing_items.append((str(it.video), lang))
        work = sc.runnable
        if not work:
            return res
        providers, provider_configs = _providers(cfg, log, tr)
        keep_unsynced = bool(cfg.get("keep_unsynced", False))
        tmp = Path(tempfile.mkdtemp(prefix="supersubber-"))
        try:
            with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
                total = len(work)
                for i, it in enumerate(work, 1):
                    if cancel.is_set():
                        res.cancelled = True
                        break
                    # (Sprache, SDH?) — erst die normalen Fassungen, dann die SDH-Fassungen
                    jobs = [(l, False) for l in it.langs if it.found.get(l)] + \
                           [(l, True) for l in it.sdh_langs if it.sdh_found.get(l)]
                    progress(it.video.name, i, total)
                    log(f"[{i}/{total}] {it.video.name}  [{', '.join(l + (' SDH' if s else '') for l, s in jobs)}]")
                    sp = (lambda base: (lambda f: frac(min(1.0, (base + f) / total))))(i - 1) if frac else (lambda f: None)
                    sp(0.05)
                    got = {False: _download_item(pool, it, tmp, log, tr),
                           True: _download_item(pool, it, tmp, log, tr, sdh=True)}
                    sp(0.35)
                    for lang, sdh in jobs:
                        if cancel.is_set():
                            break
                        status = it.sdh_status if sdh else it.status
                        label = f"{lang} SDH" if sdh else lang
                        dl = got[sdh].get(lang)
                        if not dl or not dl.exists():
                            if sdh:
                                # keine SDH-Fassung ladbar: neutral vermerken, zählt nicht als fehlend
                                log(tr("c_sdh_none", lang=lang))
                                status.pop(lang, None)
                                continue
                            log(tr("c_not_found", lang=lang))
                            status[lang] = "missing"
                            res.missing.append(f"{it.video.name}  [{lang}]")
                            res.missing_items.append((str(it.video), lang))
                            continue
                        mid = f".{lang}.{SDH_TAG}" if sdh else f".{lang}"
                        out = it.video.with_name(f"{it.video.stem}{mid}{dl.suffix.lower()}")
                        if keep_unsynced:
                            raw = it.video.with_name(f"{it.video.stem}{mid}.{UNSYNCED_TAG}{dl.suffix.lower()}")
                            try:
                                shutil.copyfile(dl, raw)
                                log(tr("c_kept_unsynced", name=raw.name))
                            except OSError as e:
                                log(tr("c_dl_err", err=f"{type(e).__name__}: {e}"))
                        log(tr("c_syncing"))
                        ok, suspect = _alass(it.video, dl, out, log, tr, subprog=lambda f: sp(0.4 + 0.58 * f),
                                             cancel=cancel)
                        if cancel.is_set() and not ok:
                            # mitten im Sync abgebrochen: nichts Halbes hinterlassen
                            if keep_unsynced:
                                try:
                                    raw.unlink(missing_ok=True)
                                except OSError:
                                    pass
                            break
                        if ok and suspect:
                            status[lang] = "suspect"
                            res.suspect.append(f"{it.video.name}  [{label}]")
                            res.suspect_items.append((str(it.video), lang))
                        elif ok:
                            status[lang] = "synced"
                            res.synced.append(f"{it.video.name}  [{label}]")
                        else:
                            shutil.copyfile(dl, out)
                            status[lang] = "unsynced"
                            res.unsynced.append(f"{it.video.name}  [{label}]")
                            log(tr("c_sync_fail"))
                    if cancel.is_set():
                        res.cancelled = True
                        break
                    sp(1.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"
    return res


def run(folder: str, languages: list[str], cfg: dict, progress: Progress, log: Log,
        cancel: threading.Event, tr: Tr = _tr_fallback, frac: Frac | None = None,
        imdb_id: str | None = None) -> Result:
    """Kommandozeile/Headless: Vorlauf + Lauf in einem. imdb_id gilt für alle Videos."""
    sc = scan(folder, languages, cfg, progress, log, cancel, tr)
    if sc.error:
        res = Result(); res.error = sc.error
        return res
    if imdb_id:
        rescan([it for it in sc.items if it.wanted], imdb_id, cfg, log, cancel, tr)
    if sc.cancelled:
        res = Result(); res.cancelled = True
        return res
    return run_scan(sc, cfg, progress, log, cancel, tr, frac)


def run_local_many(pairs: list, cfg: dict, progress: Progress, log: Log, cancel: threading.Event,
                   tr: Tr = _tr_fallback, frac: Frac | None = None) -> Result:
    """Mehrere hineingezogene Untertitel nacheinander syncen. pairs: (Video, Untertitel, Sprache).
    Ein Fehler bei einem Paar hält die übrigen nicht auf; ein Abbruch beendet den Rest."""
    total, res = len(pairs), Result()
    for i, (video, sub, lang) in enumerate(pairs, 1):
        if cancel.is_set():
            res.cancelled = True
            break
        one = run_local(video, sub, lang, cfg, progress, log, cancel, tr,
                        frac=(lambda f, i=i: frac((i - 1 + f) / total)) if frac else None, pos=(i, total))
        for name in ("synced", "unsynced", "suspect", "suspect_items", "insync", "noaccess", "failed"):
            getattr(res, name).extend(getattr(one, name))
        if one.error:
            log(tr("c_dl_err", err=one.error))
            res.failed.append(f"{Path(sub).name}  —  {one.error}")
        if one.cancelled:
            res.cancelled = True
            break
    return res


def run_local(video_path: str, sub_path: str, lang: str, cfg: dict, progress: Progress, log: Log,
              cancel: threading.Event, tr: Tr = _tr_fallback, frac: Frac | None = None,
              pos: tuple = (1, 1)) -> Result:
    """Vorhandenes Untertitel-File gegen ein Video syncen (kein Download).
    Ziel ist immer <Video>.<lang>.<ext>; ein dort liegendes File wird einmalig als *.orig gesichert.
    pos: Platz in einer Reihe mehrerer Dateien, nur für die Anzeige."""
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
            # die Datei liegt schon unter dem Zielnamen: erst syncen, dann entscheiden — bis dahin bleibt sie unberührt
            same = os.path.normcase(str(sub)) == os.path.normcase(str(target))
            if same:
                pass
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
            recoded = _ensure_utf8(src)
            progress(video.name, *pos)
            log(f"[{pos[0]}/{pos[1]}] {video.name}  [{lang}]  ←  {sub.name}")
            log(tr("c_syncing"))
            sp = (lambda f: frac(min(1.0, 0.03 + 0.97 * f))) if frac else None
            info: dict = {}
            out = tmpdir / f"synced{sub.suffix.lower()}" if same else target
            ok, suspect = _alass(video, src, out, log, tr, subprog=sp, cancel=cancel, info=info)
            if cancel.is_set() and not ok:
                res.cancelled = True
                return res
            if same:
                # schon synchron: alass hat bei gleicher Bildrate keinen Block merklich verschoben. Dann bleibt
                # die Datei, wie sie ist — keine Sicherung, keine neue Datei (Cosmo, 2026-10-04). Eine fremd
                # kodierte Datei wird trotzdem ersetzt, das UTF-8 ist der Gewinn
                if ok and not recoded and info.get("ratio_one") and info.get("blocks") \
                        and info.get("max_shift", 1.0) < IN_SYNC_MAX_SHIFT:
                    log(tr("c_in_sync"))
                    res.insync.append(f"{video.name}  [{lang}]")
                    if frac:
                        frac(1.0)
                    return res
                orig = Path(str(target) + ".orig")
                if orig.exists():
                    import time
                    orig = Path(str(target) + f".orig-{time.strftime('%Y%m%d-%H%M%S')}")
                sub.rename(orig)
                log(tr("c_backup", name=orig.name))
                if ok:
                    shutil.move(str(out), str(target))
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
