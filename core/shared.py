"""Spese condivise: chi ti deve dei soldi e a chi li devi tu.

Ogni persona ha un saldo per valuta: le voci positive sono soldi che ti deve, quelle negative soldi che devi tu.
- «quota»: hai pagato tu una spesa anche per qualcun altro. La sua parte viene staccata dal movimento (diviso)
  con la categoria «Spese condivise», che non conta nelle spese: così nelle tue spese resta solo la tua parte.
- «rimborso»: un movimento con cui una persona ti restituisce dei soldi (o tu li dai a lei). Volendo il movimento
  diventa «Spese condivise», così non conta come entrata (o come spesa).
- «manuale»: una voce scritta a mano (es. ha pagato lei la cena per te).
- «saldo»: chiusura del conto a mano (vi siete messi in pari in contanti).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from core import db
from core.i18n import t


class SharedError(ValueError):
    """Operazione non possibile: il messaggio si mostra così com'è."""


def people(include_archived: bool = False) -> pd.DataFrame:
    with db.connect() as con:
        q = "SELECT * FROM people" + ("" if include_archived else " WHERE archived=0") + " ORDER BY name COLLATE NOCASE"
        return pd.read_sql_query(q, con)


def add_person(name: str) -> int:
    """Aggiunge una persona (se esiste già con lo stesso nome, maiuscole a parte, ritorna quella)."""
    name = " ".join((name or "").split())
    if not name:
        raise SharedError(t("Scrivi il nome della persona."))
    if len(name) > 40:
        raise SharedError(t("Il nome è troppo lungo (al massimo 40 caratteri)."))
    with db.connect() as con:
        r = con.execute("SELECT id FROM people WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if r:
            con.execute("UPDATE people SET archived=0 WHERE id=?", (r["id"],))
            return int(r["id"])
        return int(con.execute("INSERT INTO people(name) VALUES (?)", (name,)).lastrowid)


def rename_person(person_id: int, name: str) -> None:
    name = " ".join((name or "").split())
    if not name:
        raise SharedError(t("Scrivi il nome della persona."))
    with db.connect() as con:
        r = con.execute("SELECT id FROM people WHERE name=? COLLATE NOCASE AND id<>?", (name, person_id)).fetchone()
        if r:
            raise SharedError(t("C'è già una persona che si chiama «{n}».", n=name))
        con.execute("UPDATE people SET name=? WHERE id=?", (name, person_id))


def archive_person(person_id: int, value: bool = True) -> None:
    with db.connect() as con:
        con.execute("UPDATE people SET archived=? WHERE id=?", (1 if value else 0, person_id))


def delete_person(person_id: int) -> None:
    """Elimina la persona e le sue voci. Le parti di spesa già staccate dai movimenti restano (si possono
    riunire dal dettaglio del movimento)."""
    with db.connect() as con:
        con.execute("DELETE FROM shared WHERE person_id=?", (person_id,))
        con.execute("DELETE FROM people WHERE id=?", (person_id,))


def entries(person_id: int | None = None) -> pd.DataFrame:
    with db.connect() as con:
        q = ("SELECT s.*, p.name AS person FROM shared s JOIN people p ON p.id = s.person_id"
             + (" WHERE s.person_id=?" if person_id is not None else "") + " ORDER BY s.date DESC, s.id DESC")
        df = pd.read_sql_query(q, con, params=(person_id,) if person_id is not None else ())
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def balances() -> pd.DataFrame:
    """Saldo per persona e valuta: person_id, name, archived, currency, balance (> 0 ti deve, < 0 devi tu)."""
    with db.connect() as con:
        return pd.read_sql_query(
            """SELECT p.id AS person_id, p.name, p.archived, s.currency, round(TOTAL(s.amount), 2) AS balance,
                      COUNT(s.id) AS n, MAX(s.date) AS last
               FROM people p LEFT JOIN shared s ON s.person_id = p.id
               GROUP BY p.id, s.currency ORDER BY p.name COLLATE NOCASE""", con)


def add_entry(person_id: int, day, description: str, amount: float, currency: str, kind: str = "manuale",
              tx_id: int | None = None) -> int:
    amount = round(float(amount), 2)
    if abs(amount) < 0.01:
        raise SharedError(t("L'importo deve essere maggiore di zero."))
    day = pd.Timestamp(day).date().isoformat()
    with db.connect() as con:
        return int(con.execute(
            "INSERT INTO shared(person_id, date, description, amount, currency, kind, tx_id) VALUES (?,?,?,?,?,?,?)",
            (int(person_id), day, (description or "").strip(), amount, (currency or db.base_currency()).upper(),
             kind, tx_id)).lastrowid)


def delete_entry(entry_id: int) -> None:
    """Elimina una voce. Se era una quota staccata da un movimento, la quota torna nel movimento."""
    with db.connect() as con:
        r = con.execute("SELECT kind, tx_id FROM shared WHERE id=?", (int(entry_id),)).fetchone()
        con.execute("DELETE FROM shared WHERE id=?", (int(entry_id),))
    if r and r["kind"] == "quota" and r["tx_id"] is not None:
        db.delete_transactions([int(r["tx_id"])])   # la parte staccata torna nel movimento originale


def linked(tx_id: int) -> pd.DataFrame:
    """Voci legate a un movimento o alle parti in cui è diviso."""
    ids = db.split_family(tx_id) or [int(tx_id)]
    with db.connect() as con:
        q = ",".join("?" * len(ids))
        df = pd.read_sql_query(f"SELECT s.*, p.name AS person FROM shared s JOIN people p ON p.id = s.person_id "
                               f"WHERE s.tx_id IN ({q}) ORDER BY s.id", con, params=tuple(ids))
    return df


def _tx(tx_id: int):
    with db.connect() as con:
        r = con.execute("SELECT * FROM transactions WHERE id=?", (int(tx_id),)).fetchone()
    if r is None:
        raise SharedError(t("Movimento non trovato."))
    return r


def share_transaction(tx_id: int, person_id: int, share: float, description: str | None = None,
                      note: str | None = None) -> int:
    """Hai pagato tu una spesa anche per un'altra persona: la sua parte (`share`, positivo, nella valuta del
    movimento) viene staccata dal movimento come «Spese condivise» e risulta come soldi che ti deve."""
    r = _tx(tx_id)
    if float(r["amount"]) >= 0:
        raise SharedError(t("Si può dividere con altri solo una spesa (un addebito)."))
    with db.connect() as con:
        name = con.execute("SELECT name FROM people WHERE id=?", (int(person_id),)).fetchone()
    if name is None:
        raise SharedError(t("Persona non trovata."))
    part = db.split_off(tx_id, abs(float(share)), db.SHARED_CATEGORY, note or t("Quota di {n}", n=name["name"]))
    return add_entry(person_id, r["date"], description or r["description"], abs(float(share)), r["currency"],
                     "quota", part)


def settle_with_transaction(tx_id: int, person_id: int, neutral: bool = True) -> int:
    """Il movimento è un rimborso tra te e la persona: un accredito riduce quello che ti deve, un addebito
    (soldi dati a lei) riduce quello che devi tu. Con neutral il movimento passa a «Spese condivise»."""
    r = _tx(tx_id)
    with db.connect() as con:
        if con.execute("SELECT 1 FROM shared WHERE tx_id=?", (int(tx_id),)).fetchone():
            raise SharedError(t("Questo movimento è già collegato alle spese condivise."))
    eid = add_entry(person_id, r["date"], r["description"], -float(r["amount"]), r["currency"], "rimborso", int(tx_id))
    if neutral:
        db.update_transaction(int(tx_id), category=db.SHARED_CATEGORY, category_locked=1)
    return eid


def settle_manual(person_id: int, currency: str, day: date | None = None) -> int | None:
    """Vi siete messi in pari (es. in contanti): una voce che azzera il saldo in quella valuta."""
    b = balances()
    row = b[(b["person_id"] == person_id) & (b["currency"] == currency)]
    bal = float(row["balance"].iloc[0]) if not row.empty else 0.0
    if abs(bal) < 0.01:
        return None
    return add_entry(person_id, day or date.today(), t("Saldato"), -bal, currency, "saldo")
