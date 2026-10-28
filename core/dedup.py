"""Doppioni tra estratti importati e collegamento banca (Open Banking).

Lo stesso movimento può arrivare due volte: dall'estratto (file) e dal collegamento con la banca. Con i
movimenti nuovi l'app se ne accorge da sola (db.insert_transactions); qui si sistemano quelli già presenti:
- i movimenti del collegamento vengono spostati nel conto dell'app scelto (es. «FinecoBank» → «Fineco»);
- ogni movimento del collegamento uguale a uno dell'estratto (stesso conto, valuta e importo, data entro pochi
  giorni) viene tolto: resta quello dell'estratto (descrizione e categoria più precise, storico completo),
  completato con la carta usata; l'abbinamento è ricordato, così il prossimo aggiornamento non lo reinserisce;
- i movimenti a importo zero del collegamento (preautorizzazioni, verifiche della carta) vengono tolti.
`run(mapping, apply=False)` fa un'anteprima: esegue tutto e poi annulla.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date

from core import db


def run(mapping: dict[str, str] | None = None, apply: bool = False) -> dict:
    """mapping: uid del conto collegato → nome del conto nell'app. Ritorna il riepilogo per conto:
    {"moved": n, "accounts": {conto: {"api": n, "doppi": n, "zero": n, "nuovi": n}}, "removed": n}."""
    from core import cards, enablebanking as eb

    report = {"moved": 0, "accounts": {}, "removed": 0}
    with closing(sqlite3.connect(db.db_path(), timeout=30)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            for uid, label in (mapping or {}).items():
                report["moved"] += eb.relabel(con, uid, label)
            # i movimenti divisi a mano (e le loro parti) si lasciano come sono
            rows = con.execute("SELECT * FROM transactions WHERE source LIKE 'openbanking%' AND split_of IS NULL "
                               "AND split_total IS NULL ORDER BY date, id").fetchall()
            for r in rows:
                acc = report["accounts"].setdefault(r["account"], {"api": 0, "doppi": 0, "zero": 0, "nuovi": 0})
                acc["api"] += 1
                row = dict(r)
                if abs(float(r["amount"] or 0)) < 0.005:
                    if r["external_id"]:
                        con.execute("INSERT OR IGNORE INTO tx_links(external_id, tx_id, family) VALUES (?,?,?)",
                                    (r["external_id"], None, "api"))
                    con.execute("DELETE FROM transactions WHERE id=?", (r["id"],))
                    acc["zero"] += 1
                    report["removed"] += 1
                    continue
                # i movimenti scaricati con la versione precedente hanno la data contabile e la carta nel testo:
                # si usano la data dell'operazione e la descrizione pulita (come per i nuovi)
                fixed = {}
                try:
                    booked = date.fromisoformat(str(r["date"])[:10])
                    real = eb.op_date(r["description"], booked)
                    if real and real != booked:
                        fixed["date"] = real.isoformat()
                except ValueError:
                    pass
                digits, kind = cards.detect(r["description"])
                if digits:
                    fixed["description"] = cards.strip_card(r["description"]) or r["description"]
                    if not r["card"]:
                        fixed["card"] = digits
                row.update(fixed)
                twin = db.find_twin(con, row, "api")
                if twin is None:
                    acc["nuovi"] += 1
                    if fixed:
                        con.execute(f"UPDATE transactions SET {', '.join(k + '=?' for k in fixed)} WHERE id=?",
                                    [*fixed.values(), r["id"]])
                    if digits:
                        cards.remember(con, r["account"], digits, kind)
                    continue
                if r["external_id"]:
                    con.execute("INSERT OR REPLACE INTO tx_links(external_id, tx_id, family) VALUES (?,?,?)",
                                (r["external_id"], twin, "api"))
                keep = con.execute("SELECT * FROM transactions WHERE id=?", (twin,)).fetchone()
                sets = {}
                card = row.get("card")
                if card and not keep["card"]:
                    sets["card"] = card
                if r["bank_uid"] and not keep["bank_uid"]:
                    sets["bank_uid"] = r["bank_uid"]
                if r["category_locked"] and not keep["category_locked"]:
                    sets.update(category=r["category"], category_locked=1)
                if (r["notes"] or "").strip() and not (keep["notes"] or "").strip():
                    sets["notes"] = r["notes"]
                if sets:
                    con.execute(f"UPDATE transactions SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
                                [*sets.values(), twin])
                if card:
                    cards.remember(con, keep["account"], card, kind)
                con.execute("DELETE FROM transactions WHERE id=?", (r["id"],))
                acc["doppi"] += 1
                report["removed"] += 1
            if apply:
                con.commit()
            else:
                con.rollback()
        except Exception:
            con.rollback()
            raise
    return report


def suggested_mapping() -> dict[str, str]:
    """Per ogni conto collegato, il conto dell'app che sembra lo stesso (es. «FinecoBank» → «Fineco»)."""
    from core import enablebanking as eb

    accs = eb.accounts_df()
    file_accounts = file_account_names()
    out = {}
    for a in accs.itertuples():
        cur = a.label or a.aspsp_name
        if cur in file_accounts:
            out[a.uid] = cur
            continue
        low = str(a.aspsp_name or "").lower().replace(" ", "")
        match = next((f for f in file_accounts if f.lower().replace(" ", "") in low
                      or low in f.lower().replace(" ", "")), None)
        out[a.uid] = match or cur
    return out


def file_account_names() -> list[str]:
    with db.connect() as con:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT account FROM transactions WHERE source NOT LIKE 'openbanking%' AND account <> '' "
            "ORDER BY account")]
