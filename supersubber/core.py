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
    suspect_items: list[tuple[str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_items: list[tuple[str, str]] = field(default_factory=list)   # (Videopfad, Sprachkürzel)
    noaccess: list[str] = field(default_factory=list)   # Ordner ohne Schreibrecht
    skipped: int = 0
    cancelled: bool = False
    error: str | None = None


_SAMPLE_RE = re.compile(r"(^|[.\-_ ])sample([.\-_ ]|$)", re.IGNORECASE)


def _is_video(p: Path, min_size_mb: int) -> bool:
    """Videodatei ab Mindestgröße; Release-Samples („…-sample.mkv", „Sample\…") werden übersprungen —
    die wären bei 2160p groß genug, bekämen aber die Subs der ganzen Folge."""
    if p.suffix.lower() not in VIDEO_EXT:
        return False
    if _SAMPLE_RE.search(p.stem) or p.parent.name.lower() == "sample":
        return False
    try:
        return p.stat().st_size >= min_size_mb * 1024 * 1024
    except OSError:
        return False


def find_videos(folder: str, min_size_mb: int) -> list[Path]:
    out = []
    for root, _, files in os.walk(folder):
        for f in files:
            p = Path(root) / f
            if _is_video(p, min_size_mb):
                out.append(p)
    return sorted(out)


def count_videos(folder: str, min_size_mb: int, limit: int = 2) -> int:
    """Zählt Videos, bricht bei `limit` ab (fürs GUI: „genau eines?")."""
    n = 0
    for root, _, files in os.walk(folder):
        for f in files:
            if _is_video(Path(root) / f, min_size_mb):
                n += 1
                if n >= limit:
                    return n
    return n


_SKIP_TOKENS = {"forced", "hi", "sdh", "cc", "default"}   # Zusätze in Sub-Dateinamen, keine Sprachen


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


def external_subs(video: Path) -> dict[str, tuple[Path, str]]:
    """Untertitel-Dateien neben dem Video: lang → (Datei, Quelle). Quelle „tag" bei `Film.en.srt`, `Film.eng.srt`,
    `Film.English.srt`; „detected" bei `Film.srt` ohne Kürzel, dann per Textanalyse. Forced-Subs zählen nicht."""
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
        if any(t.lower() == "forced" for t in tokens):
            continue
        lang = next((l for l in (_lang_from_token(t) for t in tokens) if l), None)
        if lang:
            out.setdefault(lang, (p, "tag"))
        elif not tokens:
            det = _detect_language(p)
            if det:
                out.setdefault(det, (p, "detected"))
            else:
                out.setdefault("?", (p, "unknown"))
    return out


def embedded_subs(video: Path) -> dict[str, str]:
    """Eingebettete Untertitelspuren: lang → Codec. Forced-Spuren und Spuren ohne Sprachkennung zählen nicht."""
    import json
    from babelfish import Language
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run([_bin("ffprobe"), "-v", "error", "-select_streams", "s", "-show_entries",
                            "stream=codec_name,disposition:stream_tags=language,title", "-of", "json", str(video)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags)
        streams = json.loads(r.stdout or "{}").get("streams", [])
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for s in streams:
        tags = s.get("tags") or {}
        title = str(tags.get("title", "")).lower()
        if (s.get("disposition") or {}).get("forced") or "forced" in title:
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


def _alass(video: Path, sub: Path, out: Path, log: Log, tr: Tr = _tr_fallback,
           subprog: Callable[[float], None] | None = None) -> tuple[bool, bool]:
    """Sync ausführen; alass-Fortschritt (Audio-Analyse) wird live an subprog (0..1) gemeldet.
    Rückgabe: (erfolgreich, verdächtig) — verdächtig = mehrere Blöcke um Minuten verschoben."""
    env = dict(os.environ, ALASS_FFMPEG_PATH=_bin("ffmpeg"), ALASS_FFPROBE_PATH=_bin("ffprobe"))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen([_bin("alass-cli"), str(video), str(sub), str(out)],
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


_IMDB_RE = re.compile(r"tt\d{7,10}")


def _imdb_from_nfo(video: Path, episode: bool) -> str | None:
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
            alone = sum(1 for p in video.parent.iterdir() if p.suffix.lower() in VIDEO_EXT) == 1
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


@dataclass
class Scan:
    folder: str
    languages: list[str]
    items: list = field(default_factory=list)         # list[Item]
    noaccess: list[str] = field(default_factory=list)
    cancelled: bool = False
    error: str | None = None

    @property
    def skipped(self) -> int:
        return sum(1 for it in self.items if not it.langs)

    @property
    def runnable(self) -> list:
        return [it for it in self.items if any(it.found.get(l) for l in it.langs)]


def _recognized(v) -> str:
    from subliminal.video import Episode
    if isinstance(v, Episode):
        se = f"S{v.season:02d}E{v.episode:02d}" if v.season is not None and v.episode is not None else ""
        return " · ".join(x for x in (v.series, se) if x)
    year = getattr(v, "year", None)
    return " · ".join(x for x in (getattr(v, "title", None), str(year) if year else "") if x)


ID_PROVIDERS = {"opensubtitles", "opensubtitlescom"}   # suchen bei gesetzter IMDb-ID gezielt nach dieser ID


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
        if imdb_id and sub.provider_name in ID_PROVIDERS:
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


def _search_item(pool, it: Item, log: Log, tr: Tr, manual_id: str | None = None) -> None:
    """Erkennen + NFO + Provider-Suche + Bewertung für ein Item. Lädt nichts herunter."""
    from babelfish import Language
    from subliminal import refine, scan_video
    from subliminal.score import episode_scores, movie_scores
    from subliminal.video import Episode

    it.candidates, it.found, it.error = [], {}, None
    try:
        v = scan_video(str(it.video))
        refine(v, refiners=("hash",))
        it.v = v
        it.recognized = _recognized(v)
        if manual_id:
            it.imdb_id, it.imdb_source = manual_id, "manual"
        elif not it.imdb_id:
            nfo = _imdb_from_nfo(it.video, isinstance(v, Episode))
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
        want = {Language.fromietf(l) for l in it.langs}
        it.candidates = list(pool.list_subtitles(v, want))
        if it.imdb_id:
            # mit ID zählt, was die Provider zur ID sagen — nicht der aus dem Pfad geratene Titel
            se = f"S{v.season:02d}E{v.episode:02d}" if isinstance(v, Episode) and v.season is not None \
                and v.episode is not None else ""
            title = _title_from_candidates(it.candidates, isinstance(v, Episode)) or f"IMDb {it.imdb_id}"
            it.recognized = " · ".join(x for x in (title, se) if x)
            if manual_id and not it.recognized.startswith("IMDb "):
                it.recognized += f" · IMDb {manual_id}"
        score = _score_fn(v, it.imdb_id)
        for lang in it.langs:
            L = Language.fromietf(lang)
            best = max((score(s, v) for s in it.candidates if s.language == L), default=0)
            it.found[lang] = best >= it.min_score
            it.status[lang] = "found" if it.found[lang] else "none"
    except Exception as e:  # noqa: BLE001
        it.error = f"{type(e).__name__}: {e}"
        for lang in it.langs:
            it.found[lang] = False
            it.status[lang] = "none"
        log(tr("c_dl_err", err=it.error))


def scan(folder: str, languages: list[str], cfg: dict, progress: Progress, log: Log,
         cancel: threading.Event, tr: Tr = _tr_fallback) -> Scan:
    """Vorlauf: Videos finden, erkennen, bei den Providern suchen, bewerten. Kein Download, kein Sync."""
    sc = Scan(folder=folder, languages=list(languages))
    try:
        from subliminal import ProviderPool
        _region_setup()
        progress(tr("c_scan"), 0, 0)
        videos = find_videos(folder, int(cfg.get("min_size_mb", 50)))
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
        for v in videos:
            if not writable[v.parent]:
                continue
            it = Item(video=v, langs=[])
            ext = external_subs(v)
            emb = embedded_subs(v) if use_embedded else {}
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
            sc.items.append(it)
        todo = [it for it in sc.items if it.langs]
        log(tr("c_found", v=len(videos), t=len(todo), langs=", ".join(languages)))
        if not todo:
            return sc
        providers, provider_configs = _providers(cfg, log, tr)
        with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
            for i, it in enumerate(todo, 1):
                if cancel.is_set():
                    sc.cancelled = True
                    break
                progress(it.video.name, i, len(todo))
                _search_item(pool, it, log, tr)
                hits = [l for l in it.langs if it.found.get(l)]
                log(tr("c_scan_item", name=it.video.name, rec=it.recognized or "?",
                       hits=", ".join(hits) if hits else "—"))
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
            _search_item(pool, it, log, tr, manual_id=imdb_id)
            hits = [l for l in it.langs if it.found.get(l)]
            log(tr("c_scan_item", name=it.video.name, rec=it.recognized or "?",
                   hits=", ".join(hits) if hits else "—"))
            if on_item:
                on_item(it)


def _download_item(pool, it: Item, tmp: Path, log: Log, tr: Tr) -> dict:
    """Beste Kandidaten laden (Qualitätsprüfung inklusive). Liefert lang → Datei."""
    from babelfish import Language
    from subliminal import save_subtitles

    got: dict[str, Path] = {}
    v = it.v
    want = {Language.fromietf(l) for l in it.langs if it.found.get(l)}
    if not want or v is None:
        return got
    score = _score_fn(v, it.imdb_id)
    minutes = _duration_min(it.video)
    ignore: list[str] = []
    try:
        for _attempt in range(MAX_ATTEMPTS):
            if not want:
                break
            best = pool.download_best_subtitles(it.candidates, v, want, min_score=it.min_score,
                                                subtitle_categories="n,hi,fo", ignore_subtitles=ignore,
                                                compute_score=score)
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
        tmp = Path(tempfile.mkdtemp(prefix="supersubber-"))
        try:
            with ProviderPool(providers=providers, provider_configs=provider_configs) as pool:
                total = len(work)
                for i, it in enumerate(work, 1):
                    if cancel.is_set():
                        res.cancelled = True
                        break
                    langs = [l for l in it.langs if it.found.get(l)]
                    progress(it.video.name, i, total)
                    log(f"[{i}/{total}] {it.video.name}  [{', '.join(langs)}]")
                    sp = (lambda base: (lambda f: frac(min(1.0, (base + f) / total))))(i - 1) if frac else (lambda f: None)
                    sp(0.05)
                    got = _download_item(pool, it, tmp, log, tr)
                    sp(0.35)
                    for lang in langs:
                        if cancel.is_set():
                            break
                        dl = got.get(lang)
                        if not dl or not dl.exists():
                            log(tr("c_not_found", lang=lang))
                            it.status[lang] = "missing"
                            res.missing.append(f"{it.video.name}  [{lang}]")
                            res.missing_items.append((str(it.video), lang))
                            continue
                        out = it.video.with_name(f"{it.video.stem}.{lang}{dl.suffix.lower()}")
                        log(tr("c_syncing"))
                        ok, suspect = _alass(it.video, dl, out, log, tr, subprog=lambda f: sp(0.4 + 0.58 * f))
                        if ok and suspect:
                            it.status[lang] = "suspect"
                            res.suspect.append(f"{it.video.name}  [{lang}]")
                            res.suspect_items.append((str(it.video), lang))
                        elif ok:
                            it.status[lang] = "synced"
                            res.synced.append(f"{it.video.name}  [{lang}]")
                        else:
                            shutil.copyfile(dl, out)
                            it.status[lang] = "unsynced"
                            res.unsynced.append(f"{it.video.name}  [{lang}]")
                            log(tr("c_sync_fail"))
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
        rescan([it for it in sc.items if it.langs], imdb_id, cfg, log, cancel, tr)
    if sc.cancelled:
        res = Result(); res.cancelled = True
        return res
    return run_scan(sc, cfg, progress, log, cancel, tr, frac)


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
