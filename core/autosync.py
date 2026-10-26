"""Sincronizzazione automatica dei conti collegati (Enable Banking), una volta al giorno.

Quando parte:
- alla prima apertura dell'app di ogni giorno;
- se l'app resta aperta, al cambio di giorno (l'app controlla ogni 15 minuti), quindi mai più di 24 ore di fila
  senza sincronizzare.
Il tentativo del giorno viene segnato prima di iniziare: se la banca non risponde o ha raggiunto il suo limite
giornaliero non si riprova a ripetizione (si riprova il giorno dopo, oppure con «Sincronizza tutti»).
Un conto già sincronizzato oggi (anche a mano) viene saltato, e uno con il consenso scaduto anche: così si
consuma al massimo una lettura al giorno per conto, ben sotto il limite PSD2 (di solito 4 al giorno).
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime

from core import db, enablebanking as eb, i18n
from core.i18n import t

ENABLED_KEY = "eb_auto_sync"            # "1" (predefinito) / "0"
LAST_KEY = "eb_auto_sync_at"            # quando è partito l'ultimo giro automatico ("AAAA-MM-GG HH:MM:SS")
RESULT_KEY = "eb_auto_sync_result"      # esito dell'ultimo giro (JSON)

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock() -> threading.Lock:
    """Un lucchetto per database: due schede aperte insieme non sincronizzano due volte."""
    key = str(db.db_path())
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def enabled() -> bool:
    return (db.get_setting(ENABLED_KEY, "1") or "1") != "0"


def set_enabled(on: bool) -> None:
    db.set_setting(ENABLED_KEY, "1" if on else "0")


def _day(value) -> str:
    return str(value or "")[:10]


def due(today: date | None = None) -> bool:
    """C'è da fare il giro di oggi? (attivo, banca configurata, almeno un conto collegato, non ancora fatto oggi)."""
    today = today or date.today()
    if not enabled() or not eb.is_configured():
        return False
    if _day(db.get_setting(LAST_KEY)) == today.isoformat():
        return False
    return not eb.accounts_df().empty


def _name(acc: dict) -> str:
    return f"{acc.get('label') or acc.get('aspsp_name') or ''} · {acc.get('account_name') or ''}".strip(" ·")


def run(today: date | None = None) -> dict | None:
    """Fa il giro di oggi se serve. Ritorna l'esito, oppure None se non c'era niente da fare (o se un'altra
    scheda lo sta già facendo)."""
    lock = _lock()
    if not lock.acquire(blocking=False):
        return None
    try:
        today = today or date.today()
        if not due(today):
            return None
        db.set_setting(LAST_KEY, db.now_str())   # segnato subito: niente tentativi ripetuti nello stesso giorno
        res = {"at": db.now_str(), "synced": [], "errors": [], "fresh": 0, "expired": []}
        for acc in eb.accounts_df().to_dict("records"):
            if _day(acc.get("last_sync")) == today.isoformat():
                res["fresh"] += 1                 # già sincronizzato oggi (anche a mano)
                continue
            exp = _day(acc.get("valid_until"))
            if exp and exp < today.isoformat():
                res["expired"].append(_name(acc))  # consenso scaduto: va ricollegato dalla pagina Collega banche
                continue
            try:
                ins, skip = eb.sync_account(acc["uid"])
                res["synced"].append({"name": _name(acc), "new": int(ins), "known": int(skip)})
            except Exception as e:             # un conto che non risponde non blocca gli altri
                msg, soft = eb.sync_error(acc, e)
                res["errors"].append([msg, bool(soft)])
        db.set_setting(RESULT_KEY, json.dumps(res, ensure_ascii=False))
        return res
    finally:
        lock.release()


def last_result() -> dict | None:
    raw = db.get_setting(RESULT_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def new_count(res: dict) -> int:
    return sum(s["new"] for s in res.get("synced", []))


def summary(res: dict) -> str:
    """Frase breve sull'esito di un giro (per l'avviso a comparsa e la pagina Collega banche)."""
    n_ok, n_new = len(res.get("synced", [])), new_count(res)
    parts = []
    if n_ok:
        parts.append(t("1 conto sincronizzato") if n_ok == 1 else t("{n} conti sincronizzati", n=n_ok))
        parts.append(t("1 nuovo movimento") if n_new == 1 else t("{n} nuovi movimenti", n=n_new))
    if res.get("fresh"):
        parts.append(t("1 conto già aggiornato oggi") if res["fresh"] == 1
                     else t("{n} conti già aggiornati oggi", n=res["fresh"]))
    if res.get("errors"):
        parts.append(t("1 conto non sincronizzato") if len(res["errors"]) == 1
                     else t("{n} conti non sincronizzati", n=len(res["errors"])))
    if res.get("expired"):
        parts.append(t("consenso scaduto: {names}", names=", ".join(res["expired"])))
    return ", ".join(parts)


def status_text() -> str:
    """Riga di stato: quando è stata fatta l'ultima sincronizzazione automatica e com'è andata."""
    if not enabled():
        return t("Sincronizzazione automatica disattivata.")
    res = last_result()
    when = db.get_setting(LAST_KEY)
    if not when:
        return t("Sincronizzazione automatica: la prima parte alla prossima apertura dell'app.")
    try:
        w = datetime.fromisoformat(when)
        stamp = t("{day} alle {time}", day=i18n.date_short(w.date()), time=f"{w:%H:%M}")
    except ValueError:
        stamp = when
    txt = t("Ultima sincronizzazione automatica: {when}", when=stamp)
    if res and _day(res.get("at")) == _day(when):
        s = summary(res)
        if s:
            txt += f" — {s}"
    return txt
