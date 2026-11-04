"""Immagine degli obiettivi: una delle illustrazioni dell'app (scelta in automatico dal nome dell'obiettivo o a mano)
oppure una foto dell'utente.

Campi dell'obiettivo: image_mode = 'auto' (predefinito) | 'preset' | 'custom' | 'none'; image_preset = chiave
dell'illustrazione per 'preset'. La foto dell'utente sta nella tabella images con chiave «goal:<id>».
"""
from __future__ import annotations

import base64
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from core import images

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "goals"

# chiave → nome mostrato (tradotto con t())
PRESETS = {
    "risparmio": "Risparmio",
    "emergenza": "Fondo emergenza",
    "vacanza": "Vacanza al mare",
    "viaggio": "Viaggio",
    "casa": "Casa",
    "auto": "Auto e moto",
    "studio": "Studio",
    "pensione": "Pensione",
    "matrimonio": "Matrimonio",
    "tecnologia": "Tecnologia",
    "regali": "Regali e feste",
    "tasse": "Tasse",
    "famiglia": "Famiglia e figli",
    "animali": "Animali",
    "salute": "Salute",
}
DEFAULT = "risparmio"
MODES = ["auto", "preset", "custom", "none"]

# parole (italiano e inglese, senza accenti) che fanno scegliere un'illustrazione; vince la prima che compare
KEYWORDS = [
    ("tasse", ["tass", "impost", "tax", "taxes", "irs", "f24", "irpef", "imu", "730"]),
    ("emergenza", ["emergenz", "imprevist", "emergency", "rainy day", "cuscinetto", "riserva", "safety"]),
    ("matrimonio", ["matrimon", "nozze", "sposa", "wedding", "fedi", "anello", "ring"]),
    ("pensione", ["pension", "retire", "vecchiaia", "401k", "ira "]),
    ("studio", ["studi", "univers", "master", "corso", "scuola", "laurea", "college", "school", "education",
                "tuition", "libri"]),
    ("famiglia", ["bimb", "bebe", "figli", "neonat", "baby", "kid", "child", "famiglia", "family"]),
    ("animali", ["cane", "gatto", "cucciol", "veterinar", "animal", "dog", "cat ", "pet", "puppy"]),
    ("salute", ["salute", "dentist", "medic", "health", "ospedal", "cure", "terapia", "occhiali"]),
    ("auto", ["auto", "macchina", "moto", "scooter", "car ", "vehicle", "bici", "bike", "tesla", "patente"]),
    ("casa", ["casa", "mutuo", "anticipo", "appartament", "affitto", "trasloc", "arred", "cucina", "home", "house",
              "down payment", "mortgage", "rent", "furniture"]),
    ("tecnologia", ["computer", "laptop", "portatil", "telefon", "iphone", "smartphone", "tablet", "ipad", "mac",
                    "console", "playstation", "tv", "tech", "pc"]),
    ("regali", ["regal", "natale", "compleann", "festa", "gift", "christmas", "birthday", "party", "anniversar"]),
    ("vacanza", ["vacanz", "mare", "spiaggia", "estate", "holiday", "vacation", "beach", "summer", "crociera",
                 "cruise", "hawaii", "maldive", "sardegna"]),
    ("viaggio", ["viagg", "trip", "travel", "volo", "flight", "giappone", "japan", "america", "usa", "new york",
                 "londra", "london", "parigi", "paris", "tour", "weekend", "montagna", "sci", "ski"]),
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " " + re.sub(r"\s+", " ", text.lower()) + " "


def auto_preset(name: str) -> str:
    """Illustrazione adatta al nome dell'obiettivo (es. «Vacanza in Giappone» → vacanza)."""
    n = _norm(name)
    for key, words in KEYWORDS:
        for w in words:
            w = w.strip().lower()
            # parole brevi (pc, tv, usa, sci…) solo come parola intera; le altre anche come inizio di parola
            pattern = rf"\b{re.escape(w)}\b" if len(w) <= 3 else rf"\b{re.escape(w)}"
            if re.search(pattern, n):
                return key
    return DEFAULT


@lru_cache(maxsize=64)
def preset_url(key: str) -> str:
    key = key if key in PRESETS else DEFAULT
    data = (ASSETS / f"{key}.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")


def image_key(goal_id) -> str:
    return f"goal:{int(goal_id)}"


def mode_of(goal: dict) -> str:
    m = (goal or {}).get("image_mode") or "auto"
    return m if m in MODES else "auto"


def url_for(goal: dict) -> str | None:
    """Immagine da mostrare per l'obiettivo, oppure None (nessuna immagine)."""
    mode = mode_of(goal)
    if mode == "none":
        return None
    if mode == "custom" and goal.get("id") is not None:
        url = images.data_url(image_key(goal["id"]))
        if url:
            return url
        mode = "auto"  # la foto non c'è più: si torna all'illustrazione automatica
    if mode == "preset" and goal.get("image_preset") in PRESETS:
        return preset_url(goal["image_preset"])
    return preset_url(auto_preset(goal.get("name") or ""))
