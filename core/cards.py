"""Carte di pagamento: riconoscimento della carta dalla descrizione del movimento e dati delle carte.

Le banche scrivono il numero (parziale) della carta nella descrizione dei movimenti, per esempio Fineco:
«BAR CENTRALE MILANO IT Carta N. ***** 123 Data operazione 05/03/26» oppure, per la carta di credito,
«... POSIZIONE N 5100********1234». Da qui si ricavano le ultime cifre e, quando si capisce, il tipo di carta.
I movimenti hanno la colonna `card` (ultime cifre); la tabella `cards` tiene tipo e nome scelto per ogni carta.
Revolut non indica nei suoi file (né via Open Banking) con quale carta è stato fatto un pagamento: per Revolut le
carte non si possono separare.
"""
from __future__ import annotations

import re

from core import db

RE_CARD = [
    re.compile(r"\bcarta\s*n\.?\s*[*•x]{2,}\s*(\d{3,4})\b", re.I),
    re.compile(r"\bcard\s*(?:n\.?|no\.?|number|ending(?:\s+in)?)\s*[*•x]*\s*(\d{4})\b", re.I),
    re.compile(r"\b\d{4}\s*[*•]{4,8}\s*(?:[*•]{4}\s*)?(\d{4})\b"),
]
# testo aggiunto dalla banca alla descrizione: si toglie (la carta resta nella colonna `card`)
RE_CARD_TAIL = re.compile(r"\s*\bcarta\s*n\.?\s*[*•x]{2,}\s*\d{3,4}\b(?:\s*data operazione:?\s*\d{1,2}/\d{1,2}/\d{2,4})?",
                          re.I)
KINDS = [  # (testo nella descrizione, tipo)
    ("visa debit", "Visa Debit"),
    ("mastercard debit", "Mastercard Debit"),
    ("bancomat", "Bancomat"),
    ("carta di credito", "Carta di credito"),
    ("credit card", "Carta di credito"),
    ("prepagata", "Prepagata"),
    ("mastercard", "Mastercard"),
    ("visa", "Visa"),
]


def detect(text: str) -> tuple[str | None, str]:
    """(ultime cifre della carta o None, tipo di carta o '') dal testo di un movimento."""
    s = str(text or "")
    digits = None
    for rx in RE_CARD:
        m = rx.search(s)
        if m:
            digits = m.group(1)
            break
    if not digits:
        return None, ""
    low = s.lower()
    kind = ""
    if re.search(r"\b5\d{3}\s*[*•]{4,8}", s) or "carta di credito" in low or "posizione n" in low:
        kind = "Carta di credito"
    else:
        for needle, k in KINDS:
            if needle in low:
                kind = k
                break
    return digits, kind


def strip_card(text: str) -> str:
    """Toglie «Carta N. ***** 123 Data operazione 05/03/26» dalla descrizione."""
    out = RE_CARD_TAIL.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", out).strip(" -")


# ---------------------------------------------------------------- dati delle carte
def remember(con, account: str, digits: str, kind: str = "") -> None:
    """Registra la carta (se nuova) e il suo tipo (se non era noto). `con`: connessione aperta."""
    if not digits or not account:
        return
    con.execute("INSERT OR IGNORE INTO cards(account, digits, kind, name) VALUES (?,?,?,'')",
                (account, digits, kind or ""))
    if kind:
        con.execute("UPDATE cards SET kind=? WHERE account=? AND digits=? AND (kind IS NULL OR kind='')",
                    (kind, account, digits))


def cards_df():
    import pandas as pd
    with db.connect() as con:
        return pd.read_sql_query("SELECT * FROM cards ORDER BY account, digits", con)


def set_name(account: str, digits: str, name: str) -> None:
    with db.connect() as con:
        con.execute("UPDATE cards SET name=? WHERE account=? AND digits=?", (name.strip(), account, digits))


def set_hidden(account: str, digits: str, hidden: bool) -> None:
    with db.connect() as con:
        con.execute("UPDATE cards SET hidden=? WHERE account=? AND digits=?", (1 if hidden else 0, account, digits))


def backfill() -> int:
    """Riconosce la carta nei movimenti già presenti che non l'hanno ancora (dalla descrizione)."""
    n = 0
    with db.connect() as con:
        rows = con.execute("SELECT id, description, account FROM transactions WHERE card IS NULL").fetchall()
        for r in rows:
            digits, kind = detect(r["description"])
            if digits:
                con.execute("UPDATE transactions SET card=? WHERE id=?", (digits, r["id"]))
                remember(con, r["account"], digits, kind)
                n += 1
    return n
