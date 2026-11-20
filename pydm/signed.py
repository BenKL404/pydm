# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Date limite annoncée par un lien signé.

Un lien temporaire porte presque toujours son échéance en clair : la lire permet de dire « ce lien
a expiré, rechargez la page » au lieu d'un 403 opaque, et d'éviter de planifier à 2 h du matin un
téléchargement dont le lien ne vit qu'un quart d'heure. Rien n'est vérifié
cryptographiquement : ce qui est lu ici est une indication, pas une preuve.
"""
import base64
import binascii
import calendar
import json
import re
import time
import urllib.parse

# paramètres portant une date limite absolue (X-Amz-Expires est une durée, traité à part)
EPOCH_KEYS = ("expires", "expire", "exp", "e", "oe", "se", "token_expire", "valid_until", "ttl_end")
_ISO = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})[T ](\d{2}):?(\d{2}):?(\d{2})Z?$")
_TOKEN_EXP = re.compile(r"[~&?](?:exp|st)=(\d{9,11})")


def _as_epoch(value):
    """Secondes Unix depuis un entier (s ou ms) ou une date ISO 8601, sinon None."""
    value = (value or "").strip()
    if re.fullmatch(r"\d{13}", value):
        return int(value) / 1000.0
    if re.fullmatch(r"\d{9,11}", value):
        return float(value)
    m = _ISO.match(value)
    if m:
        return float(calendar.timegm(tuple(int(g) for g in m.groups()) + (0, 0, 0)))
    return None


def _jwt_exp(token):
    """Champ exp de la charge utile d'un JWT (signature non vérifiée)."""
    parts = token.split(".")
    if len(parts) != 3 or not parts[1]:
        return None
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        exp = json.loads(raw).get("exp")
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError, AttributeError):
        return None
    return float(exp) if isinstance(exp, (int, float)) else None


def _cloudfront_policy(encoded):
    """Condition DateLessThan d'une politique CloudFront (base64 « URL-safe » maison)."""
    pad = encoded.replace("-", "+").replace("_", "=").replace("~", "/")
    try:
        policy = json.loads(base64.b64decode(pad + "=" * (-len(pad) % 4)))
        return float(policy["Statement"][0]["Condition"]["DateLessThan"]["AWS:EpochTime"])
    except (ValueError, TypeError, KeyError, IndexError, binascii.Error):
        return None


def expiry_of(url):
    """Instant d'expiration du lien en secondes Unix, ou None s'il n'en annonce pas."""
    parsed = urllib.parse.urlparse(url)
    query = {k.lower(): v[0] for k, v in urllib.parse.parse_qs(parsed.query).items() if v}

    if "x-amz-expires" in query and "x-amz-date" in query:      # AWS SigV4 : début + durée
        start = _as_epoch(query["x-amz-date"])
        try:
            return start + float(query["x-amz-expires"]) if start else None
        except ValueError:
            return None

    for key in EPOCH_KEYS:
        if key in query:
            found = _as_epoch(query[key])
            if found:
                return found

    for value in list(query.values()) + parsed.path.split("/"):
        if value.count(".") == 2:
            found = _jwt_exp(urllib.parse.unquote(value))
            if found:
                return found

    for raw in (parsed.query, parsed.path):     # Akamai : hdnts/__token__/hdnea …~exp=…
        m = _TOKEN_EXP.search(raw)
        if m:
            return float(m.group(1))

    if "policy" in query:
        return _cloudfront_policy(query["policy"])
    return None


def freshness(url, margin=120):
    """(« ok » | « soon » | « expired » | « unknown », secondes restantes ou None)."""
    when = expiry_of(url)
    if when is None:
        return "unknown", None
    left = when - time.time()
    if left <= 0:
        return "expired", left
    return ("soon" if left < margin else "ok"), left
