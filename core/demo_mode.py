"""Demo online (per esempio su Streamlit Community Cloud): con la variabile MONEYBOARD_DEMO=1 l'app non chiede
nessun accesso, ogni visitatore riceve un account di prova tutto suo con dati inventati (che si cancellano da soli
dopo qualche ora) e le funzioni che toccano il computer o servizi esterni (cartelle, banche, email) sono spente."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

ENV = "MONEYBOARD_DEMO"
MAX_AGE = timedelta(hours=6)
PREFIX = "Demo "
_cached: bool | None = None


def _secret_value():
    """Valore nei «Secrets» di Streamlit (per esempio quelli impostati su Streamlit Community Cloud).
    Senza nessun secret Streamlit solleva un errore: vuol dire semplicemente che la demo non è attiva."""
    try:
        import streamlit as st
        return st.secrets.get(ENV)
    except Exception:
        return None


def enabled() -> bool:
    global _cached
    if _cached is None:
        v = os.environ.get(ENV)
        if v is None:
            v = _secret_value()
        _cached = str(v or "").strip().lower() in ("1", "true", "yes", "on")
    return _cached


def cleanup(now: datetime | None = None) -> int:
    """Cancella i visitatori della demo più vecchi di qualche ora (con i loro dati). Ritorna quanti."""
    from core import users
    now = now or datetime.now()
    n = 0
    for uid, u in users.all_users().items():
        if not (u.get("demo") and str(u.get("name", "")).startswith(PREFIX)):
            continue
        try:
            created = datetime.fromisoformat(str(u.get("created")))
        except ValueError:
            continue
        if now - created > MAX_AGE:
            try:
                users.delete(uid, delete_data=True)
                n += 1
            except users.UserError:
                pass
    return n


def new_visitor() -> str:
    """Crea l'account di prova di un nuovo visitatore e ne ritorna l'id."""
    from core import users
    cleanup()
    pwd = secrets.token_urlsafe(24)
    for _ in range(5):
        try:
            return users.create(PREFIX + secrets.token_hex(3), pwd, pwd, demo=True)
        except users.UserError:
            continue
    raise RuntimeError("demo: impossibile creare l'account del visitatore")
