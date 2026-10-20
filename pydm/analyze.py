# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Analyse d'un lien avant téléchargement : nom, taille, et qualités disponibles d'une vidéo."""
import re
import shutil
import urllib.parse
import urllib.request

from .engine import UA, have_ytdlp, looks_like_video, probe, ytdlp_attempts
from .util import human

THUMB_MAX = 64 * 1024
SEP = " · "


def _clean(msg):
    return re.sub(r"\x1b\[[0-9;]*m", "", str(msg)).replace("ERROR: ", "").strip()


def _result(**kw):
    r = dict(kind="error", name=None, size=None, resumable=False, site=None, title=None, duration=None,
             thumbnail=None, choices=[], selected=0, ffmpeg_missing=False, error=None, drm=False)
    r.update(kw)
    return r


# --- formats ------------------------------------------------------------------
def _has_audio(f):
    return f.get("acodec") not in (None, "none")


def _is_video(f):
    return f.get("vcodec") != "none" and bool(f.get("height"))


def _is_audio_only(f):
    return f.get("vcodec") == "none" and _has_audio(f)


def _size(f, duration):
    if f.get("filesize"):
        return f["filesize"], False
    if f.get("filesize_approx"):
        return f["filesize_approx"], True
    if f.get("tbr") and duration:
        return int(f["tbr"] * duration * 125), True       # kbit/s × s → octets
    return None, False


def _tbr(f):
    return f.get("tbr") or 0


def _best_video(fs):
    """Meilleur débit, mais un flux MP4/H.264 (lu partout) l'emporte s'il atteint 90 % du meilleur."""
    best = max(fs, key=_tbr)
    mp4 = [f for f in fs if f.get("ext") == "mp4" or str(f.get("vcodec", "")).startswith("avc1")]
    if mp4:
        m = max(mp4, key=_tbr)
        if _tbr(m) >= 0.9 * _tbr(best):
            return m
    return best


def _label(head, ext, size, approx):
    text = f"{head}{SEP}{ext.upper()}"
    if size:
        text += f"{SEP}{'≈ ' if approx else ''}{human(size)}"
    return text


def _choice(label, fmt, ext, size=None, approx=False, height=None, audio_only=False):
    return dict(label=label, format=fmt, ext=ext, size=size, approx=approx, height=height,
                audio_only=audio_only)


def build_choices(info, ffmpeg):
    """Choix de qualité proposés pour une vidéo, et vrai si ffmpeg manque pour les meilleurs."""
    duration = info.get("duration")
    formats = [f for f in info.get("formats") or [] if f.get("ext") != "mhtml"]
    videos = [f for f in formats if _is_video(f)]
    audios = [f for f in formats if _is_audio_only(f)]
    usable = videos if ffmpeg else [f for f in videos if _has_audio(f)]
    heights = sorted({f["height"] for f in usable}, reverse=True)
    choices = []
    for h in heights:
        v = _best_video([f for f in usable if f["height"] == h])
        size, approx = _size(v, duration)
        fmt, ext = v["format_id"], v.get("ext") or "mp4"
        if not _has_audio(v) and audios:
            m4a = [a for a in audios if a.get("ext") == "m4a"]
            a = max(m4a if (m4a and ext == "mp4") else audios, key=_tbr)
            asize, aapprox = _size(a, duration)
            fmt = f"{v['format_id']}+{a['format_id']}"
            size = size + asize if size and asize else None
            approx = bool(size) and (approx or aapprox)
            ext = "mp4" if ext == "mp4" and a.get("ext") == "m4a" else (
                "webm" if ext == "webm" and a.get("ext") == "webm" else "mkv")
        choices.append(_choice(_label(f"{h}p", ext, size, approx), fmt, ext, size, approx, h))
    if ffmpeg and (choices or audios):
        choices.append(_choice(f"Audio seul{SEP}MP3", "ba/b", "mp3", audio_only=True))
    elif not ffmpeg and audios:
        a = max(audios, key=_tbr)
        size, approx = _size(a, duration)
        ext = a.get("ext") or "m4a"
        choices.append(_choice(_label("Audio seul", ext, size, approx), a["format_id"], ext, size, approx,
                               audio_only=True))
    if not choices:
        choices.append(_choice("Meilleure disponible", "bv*+ba/b" if ffmpeg else "b", info.get("ext") or "mp4"))
    top_complete = max((f["height"] for f in usable), default=0)
    missing = not ffmpeg and any(not _has_audio(f) and f["height"] > top_complete for f in videos)
    return choices, missing


def preselect(choices, default_quality):
    """Index présélectionné selon la qualité par défaut (menu Qualité de la fenêtre principale)."""
    if default_quality == "Audio MP3":
        return next((i for i, c in enumerate(choices) if c["audio_only"]), 0)
    m = re.match(r"(\d+)p$", default_quality or "")
    if not m:
        return 0
    limit = int(m.group(1))
    sized = [(i, c["height"]) for i, c in enumerate(choices) if c["height"]]
    fitting = [i for i, h in sized if h <= limit]
    if fitting:
        return fitting[0]
    return min(sized, key=lambda x: x[1])[0] if sized else 0


# --- analyse ------------------------------------------------------------------
def _thumbnail(info):
    """Petite miniature (octets) ou None : 64 Ko et 5 s au plus."""
    thumbs = [t for t in info.get("thumbnails") or [] if t.get("url") and t.get("width")]
    small = sorted((t for t in thumbs if t["width"] >= 240), key=lambda t: t["width"])
    url = small[0]["url"] if small else info.get("thumbnail")
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read(THUMB_MAX + 1)
    except Exception:  # noqa: BLE001
        return None
    return data if len(data) <= THUMB_MAX else None


def _video(url, headers, browser, default_quality, ffmpeg):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
            "socket_timeout": 15,
            "http_headers": {k: v for k, v in (headers or {}).items() if k != "Cookie"}}
    info, first_error = None, None
    attempts = ytdlp_attempts(url, headers, browser)
    try:
        for extra in attempts:
            try:
                with yt_dlp.YoutubeDL({**opts, **extra}) as ydl:
                    info = ydl.extract_info(url, download=False)
                break
            except Exception as e:  # noqa: BLE001
                first_error = first_error or e
    finally:
        attempts.close()
    if info is None:
        raise first_error
    choices, missing = build_choices(info, ffmpeg)
    sel = preselect(choices, default_quality)
    title = info.get("title") or url
    stem = title.replace("/", "_").strip() or "video"
    return _result(kind="video", name=f"{stem}.{choices[sel]['ext']}", size=choices[sel]["size"],
                   resumable=True, site=info.get("webpage_url_domain") or urllib.parse.urlparse(url).hostname,
                   title=title, duration=info.get("duration"), thumbnail=_thumbnail(info),
                   choices=choices, selected=sel, ffmpeg_missing=missing)


def analyze(url, headers=None, browser="Aucun", kind="auto", default_quality="Meilleure", ffmpeg=None):
    """Décrit le lien sans le télécharger ; ne lève jamais (kind « error » en cas d'échec)."""
    try:
        if ffmpeg is None:
            ffmpeg = bool(shutil.which("ffmpeg"))
        if (kind == "video" and have_ytdlp()) or (kind == "auto" and looks_like_video(url, headers)):
            return _video(url, headers, browser, default_quality, ffmpeg)
        size, ranges, name = probe(url, headers)
        return _result(kind="file", name=name, size=size, resumable=ranges,
                       site=urllib.parse.urlparse(url).hostname)
    except Exception as e:  # noqa: BLE001
        msg = _clean(e) or "analyse impossible"
        return _result(kind="error", error=msg, drm="DRM" in msg)
