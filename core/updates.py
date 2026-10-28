"""Avviso di nuova versione: una volta al giorno (se attivo) si chiede a GitHub qual è l'ultima versione
pubblicata. Si manda solo una richiesta anonima a api.github.com: nessun dato dell'app esce dal computer."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from core import db
from core.version import APP_VERSION, GITHUB_REPO, RELEASES_URL

ENABLED_KEY = "update_check"         # "1" (predefinito) / "0"
CACHE_KEY = "update_cache"           # {"checked": iso, "latest": "1.3.0", "url": "..."}
EVERY = timedelta(hours=20)
API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def enabled() -> bool:
    return (db.get_setting(ENABLED_KEY, "1") or "1") == "1"


def parse(v: str | None) -> tuple[int, ...] | None:
    """'v1.2.0' / '1.2' -> (1, 2, 0); None se non è una versione."""
    m = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?\s*$", str(v or ""))
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def is_newer(latest: str | None, current: str = APP_VERSION) -> bool:
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


def _cache() -> dict:
    try:
        v = json.loads(db.get_setting(CACHE_KEY, "{}") or "{}")
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


def fetch(timeout: float = 6.0) -> dict | None:
    """Ultima release pubblicata su GitHub: {"latest": "1.3.0", "url": ...}; None se non si riesce a saperlo."""
    import requests
    try:
        r = requests.get(API, timeout=timeout, headers={"Accept": "application/vnd.github+json",
                                                        "User-Agent": f"MoneyBoard/{APP_VERSION}"})
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None
    tag = str(data.get("tag_name") or "")
    if not parse(tag) or data.get("draft") or data.get("prerelease"):
        return None
    url = str(data.get("html_url") or RELEASES_URL)
    if not url.startswith("https://github.com/"):
        url = RELEASES_URL
    return {"latest": tag.lstrip("vV"), "url": url}


def check(force: bool = False, now: datetime | None = None) -> dict | None:
    """Nuova versione disponibile ({"latest", "url"}) oppure None. Chiede a GitHub al massimo una volta ogni
    20 ore (il risultato resta salvato); con il controllo disattivato non fa nessuna richiesta."""
    if not enabled():
        return None
    now = now or datetime.now()
    c = _cache()
    try:
        checked = datetime.fromisoformat(str(c.get("checked")))
    except (TypeError, ValueError):
        checked = None
    if force or checked is None or now - checked >= EVERY or checked > now:
        res = fetch()
        c = {"checked": now.isoformat(timespec="seconds")}
        if res:
            c.update(res)
        db.set_setting(CACHE_KEY, json.dumps(c))
    if is_newer(c.get("latest")):
        return {"latest": c["latest"], "url": c.get("url") or RELEASES_URL}
    return None
