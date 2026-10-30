"""Pocket e salvadanai di Revolut seguiti dai giroconti.

Revolut (almeno per i conti italiani) non mostra i pocket alle app collegate via Open Banking: li autorizzi, ma
la banca manda solo i conti con IBAN. Nel conto principale però ogni spostamento ha un riferimento al pocket
(«To EUR MB:<id>» quando metti soldi nel pocket, «From EUR MB:<id>» quando li riprendi). Da questi l'app tiene
un conto a parte per ogni pocket: a ogni giroconto aggiunge il movimento opposto nel conto del pocket, così il
totale dei tuoi soldi torna giusto e lo spostamento non conta né come spesa né come entrata.

Il saldo del pocket parte da zero e segue i giroconti; se nel pocket c'erano già soldi (o maturano interessi in
un salvadanaio) si corregge da Profilo → saldi dei conti, come per un conto non collegato.
"""
from __future__ import annotations

import json
import re

from core import db

SOURCE = "pocket"
KEY = "pockets"              # {id pocket: {"name": nome del conto nell'app, "bank": conto di origine, "currency": valuta}}
LINKS = "pockets_links"      # {external_id del giroconto: external_id del movimento nel pocket}
RE_MB = re.compile(r"\b(to|from)\s+([a-z]{3})\s+mb:\s*([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.I)


class PocketError(ValueError):
    """Operazione non possibile: il messaggio si mostra così com'è."""


def detect(description: str) -> tuple[str, str, str] | None:
    """(«to»/«from», valuta, id del pocket) se la descrizione è un giroconto con un pocket Revolut."""
    m = RE_MB.search(str(description or ""))
    if not m:
        return None
    return m.group(1).lower(), m.group(2).upper(), m.group(3).lower()


def _load(key: str) -> dict:
    try:
        v = json.loads(db.get_setting(key, "{}") or "{}")
    except (ValueError, TypeError):
        v = {}
    return v if isinstance(v, dict) else {}


def _save(key: str, value: dict) -> None:
    db.set_setting(key, json.dumps(value, ensure_ascii=False))


def pockets() -> dict[str, dict]:
    return _load(KEY)


def _new_name(bank: str, taken: set[str]) -> str:
    base = f"{bank} Pocket"
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    return name


def _set_zero_balance(name: str, ccy: str) -> None:
    """Il conto del pocket parte da zero: il saldo è la somma dei giroconti (correggibile dal Profilo)."""
    from core import forecast
    offs = forecast.balance_offsets()
    key = f"{name}|{ccy}"
    if key not in offs:
        offs[key] = 0.0
        db.set_setting(forecast.BALANCES_KEY, json.dumps(offs))


def _desc(bank: str, name: str, direction: str) -> str:
    return f"{bank} → {name}" if direction == "to" else f"{name} → {bank}"


def sync() -> int:
    """Aggiunge nel conto di ogni pocket i giroconti nuovi e toglie quelli il cui movimento d'origine non c'è più.
    Ritorna quanti movimenti sono stati aggiunti o tolti."""
    from core.categorize import TRANSFER_CAT
    from core.importers import finalize

    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            """SELECT id, date, description, amount, currency, account, external_id, category, category_locked
               FROM transactions WHERE source LIKE 'openbanking%' AND description LIKE '%MB:%' AND split_of IS NULL
               ORDER BY date, id""")]
    pk, links = pockets(), _load(LINKS)
    changed = 0
    taken = set(db.accounts_list()) | {p["name"] for p in pk.values()}
    new_rows: list[tuple[str, dict, dict]] = []
    for r in rows:
        hit = detect(r["description"])
        if not hit or abs(float(r["amount"] or 0)) < 0.005:
            continue
        direction, _ccy, pid = hit
        orig = r["external_id"] or f"id:{r['id']}"
        if pid not in pk:
            name = _new_name(r["account"], taken)
            taken.add(name)
            pk[pid] = {"name": name, "bank": r["account"], "currency": str(r["currency"]).upper()}
            _save(KEY, pk)
        if not r["category_locked"] and r["category"] != TRANSFER_CAT:
            with db.connect() as con:
                con.execute("UPDATE transactions SET category=? WHERE id=?", (TRANSFER_CAT, r["id"]))
            changed += 1
        if orig in links:
            continue
        p = pk[pid]
        mirror = {"date": str(r["date"])[:10], "description": _desc(r["account"], p["name"], direction),
                  "amount": -float(r["amount"]), "currency": str(r["currency"]).upper(),
                  "external_id": db.make_external_id(SOURCE, orig), "_force_category": TRANSFER_CAT}
        new_rows.append((orig, mirror, p))
    for orig, mirror, p in new_rows:
        _set_zero_balance(p["name"], mirror["currency"])
        rows_f = finalize([mirror], p["name"], SOURCE)
        ins, _skip = db.insert_transactions(rows_f, match_sources=False)
        links[orig] = rows_f[0]["external_id"]
        changed += ins
    # giroconti che non ci sono più (cancellati a mano): via anche la loro copia nel pocket
    if links:
        with db.connect() as con:
            for orig, mext in list(links.items()):
                if orig.startswith("id:"):
                    alive = con.execute("SELECT 1 FROM transactions WHERE id=?", (int(orig[3:]),)).fetchone()
                else:
                    alive = con.execute("SELECT 1 FROM transactions WHERE external_id=? UNION ALL SELECT 1 FROM "
                                        "tx_links WHERE external_id=? AND tx_id IS NOT NULL", (orig, orig)).fetchone()
                if not alive:
                    changed += con.execute("DELETE FROM transactions WHERE external_id=? AND source=?",
                                           (mext, SOURCE)).rowcount
                    links.pop(orig)
    _save(LINKS, links)
    return changed


def set_show(pid: str, show: bool) -> None:
    """Mostra o nasconde il pocket nella pagina Carte (il conto e il saldo restano comunque nei totali)."""
    pk = pockets()
    if pid in pk:
        pk[pid]["show"] = bool(show)
        _save(KEY, pk)


def shown(p: dict) -> bool:
    return p.get("show", True) is not False


def balance(pid: str) -> float | None:
    from core import forecast
    p = pockets().get(pid)
    if not p:
        return None
    tx = db.transactions_df()
    return forecast.account_balance(p["name"], p["currency"], tx)


def rename(pid: str, new_name: str) -> None:
    """Cambia il nome del conto del pocket nell'app (movimenti e saldo seguono)."""
    from core import forecast
    new_name = " ".join((new_name or "").split())
    pk = pockets()
    p = pk.get(pid)
    if p is None:
        raise PocketError("pocket?")
    old = p["name"]
    if not new_name or new_name == old:
        return
    others = (set(db.accounts_list()) | {q["name"] for k, q in pk.items() if k != pid}) - {old}
    if new_name in others:
        from core.i18n import t
        raise PocketError(t("C'è già un conto che si chiama «{n}»: scegli un altro nome.", n=new_name))
    with db.connect() as con:
        for r in con.execute("SELECT id, description FROM transactions WHERE source=? AND account=?",
                             (SOURCE, old)).fetchall():
            parts = [new_name if x == old else x for x in str(r["description"]).split(" → ")]
            con.execute("UPDATE transactions SET account=?, description=? WHERE id=?",
                        (new_name, " → ".join(parts), r["id"]))
    offs = forecast.balance_offsets()
    key_old, key_new = f"{old}|{p['currency']}", f"{new_name}|{p['currency']}"
    if key_old in offs:
        offs[key_new] = offs.pop(key_old)
        db.set_setting(forecast.BALANCES_KEY, json.dumps(offs))
    p["name"] = new_name
    _save(KEY, pk)
