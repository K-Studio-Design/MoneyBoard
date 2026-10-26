"""Import delle posizioni titoli da un export «portafoglio» (Fineco o altre banche/broker, Excel o CSV).

Il formato esatto dell'export portafoglio di Fineco non è documentato, quindi il lettore è flessibile: cerca la
riga di intestazione con una colonna ISIN e una colonna quantità, poi riconosce per nome le altre colonne
(titolo/descrizione, prezzo medio di carico, divisa, prezzo). Le righe senza un ISIN valido (totali, intestazioni
di sezione) vengono ignorate.

Sincronizzazione con il portafoglio dell'app:
- titolo nuovo -> si registra il titolo e un acquisto «iniziale» con quantità e prezzo medio dell'export;
- quantità diversa -> un'operazione di allineamento (acquisto o vendita della differenza al prezzo medio);
- quantità uguale -> niente.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from core import i18n, importers, securities

NOTE = "Allineamento da export portafoglio"
_COLS = {
    "isin": ["isin", "codice isin"],
    "qty": ["quantita", "quantità", "qta", "q.ta", "q.tà", "quantity", "nominale", "n. titoli", "numero"],
    "name": ["titolo", "descrizione", "strumento", "nome", "denominazione", "prodotto", "name"],
    "pmc": ["prezzo medio di carico", "prezzo medio carico", "prezzo di carico", "prezzo medio", "pmc", "p.m.c.",
            "costo medio", "prezzo carico", "average price", "avg price"],
    "ccy": ["divisa", "valuta", "currency"],
    "price": ["ultimo prezzo", "prezzo di mercato", "quotazione", "prezzo attuale", "prezzo", "last price"],
}


def _clean(c) -> str:
    return re.sub(r"[\s_]+", " ", str(c)).strip().lower()


def _find(cols: list[str], key: str, used: set) -> str | None:
    for alias in _COLS[key]:
        for c in cols:
            if c == alias and c not in used:
                return c
    for alias in _COLS[key]:
        for c in cols:
            if alias in c and c not in used:
                if key == "price" and any(x in c for x in ("medio", "carico", "pmc")):
                    continue
                return c
    return None


def is_positions_file(raw: pd.DataFrame) -> bool:
    return _header_row(raw) is not None


def _header_row(raw: pd.DataFrame) -> int | None:
    for i in range(min(len(raw), 40)):
        vals = [_clean(v) for v in raw.iloc[i].tolist()]
        has_isin = any(v in ("isin", "codice isin") for v in vals)
        has_qty = any(any(a in v for a in _COLS["qty"]) for v in vals)
        if has_isin and has_qty and not any(v.startswith("data") for v in vals[:2]):
            return i
    return None


def parse(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Colonne in uscita: isin, nome, quantita, pmc, valuta, prezzo."""
    raw = importers.read_any(file_bytes, filename, header=None)
    h = _header_row(raw)
    if h is None:
        raise ValueError(i18n.t("non trovo l'intestazione con le colonne ISIN e Quantità"))
    df = raw.iloc[h + 1:].copy()
    df.columns = [_clean(c) for c in raw.iloc[h].tolist()]
    cols = list(df.columns)
    used: set = set()
    found = {}
    for key in ("isin", "qty", "pmc", "name", "ccy", "price"):
        c = _find(cols, key, used)
        found[key] = c
        if c:
            used.add(c)
    out = []
    for _, r in df.iterrows():
        isin = str(r.get(found["isin"], "")).strip().upper()
        if not securities.is_valid_isin(isin):
            continue
        q = importers.parse_number(r.get(found["qty"]))
        if q is None:
            continue
        pmc = importers.parse_number(r.get(found["pmc"])) if found["pmc"] else None
        price = importers.parse_number(r.get(found["price"])) if found["price"] else None
        ccy = str(r.get(found["ccy"], "") or "").strip().upper()[:3] if found["ccy"] else ""
        out.append({"isin": isin, "nome": str(r.get(found["name"], "") or isin).strip() if found["name"] else isin,
                    "quantita": float(q), "pmc": pmc, "valuta": ccy if re.fullmatch(r"[A-Z]{3}", ccy) else "EUR",
                    "prezzo": price})
    res = pd.DataFrame(out)
    res.attrs["columns"] = found
    return res


def current_quantities() -> dict[str, float]:
    t = securities.trades_df()
    if t.empty:
        return {}
    sign = t["side"].map(lambda s: 1 if s == "acquisto" else -1)
    return (t["quantity"] * sign).groupby(t["isin"]).sum().to_dict()


def plan(pos: pd.DataFrame) -> pd.DataFrame:
    """Cosa verrebbe fatto per ogni riga: 'nuovo', 'allinea' (con la differenza) o 'ok'."""
    cur = current_quantities()
    rows = []
    for r in pos.itertuples():
        have = float(cur.get(r.isin, 0.0))
        diff = round(r.quantita - have, 6)
        if r.isin not in cur or have == 0:
            action = "nuovo"
        elif abs(diff) < 1e-6:
            action = "ok"
        else:
            action = "allinea"
        rows.append({"isin": r.isin, "nome": r.nome, "quantita": r.quantita, "nell_app": have, "differenza": diff,
                     "pmc": r.pmc, "valuta": r.valuta, "azione": action})
    return pd.DataFrame(rows)


def apply(pos: pd.DataFrame, on: date | None = None, lookup_tickers: bool = True) -> dict[str, int]:
    """Applica il piano. Ritorna i conteggi per azione. Le righe senza prezzo medio non creano operazioni
    (servirebbe il prezzo di carico): il titolo viene solo registrato."""
    on = on or date.today()
    p = plan(pos)
    inst = securities.instruments_df()
    known = set(inst["isin"]) if not inst.empty else set()
    counts = {"nuovo": 0, "allinea": 0, "ok": 0, "senza prezzo": 0}
    for r in p.itertuples():
        if r.isin not in known:
            ticker, name, atype, qccy = "", r.nome, "Altro", r.valuta
            if lookup_tickers:
                try:
                    found = securities.search_isin(r.isin)
                    if found:
                        f = found[0]
                        ticker = f.get("symbol", "")
                        name = r.nome or f.get("name", r.isin)
                        atype = securities.guess_asset_type(f.get("type", ""))
                except Exception:
                    pass
            securities.save_instrument(r.isin, ticker, name, atype, qccy, NOTE)
            known.add(r.isin)
        if r.azione == "ok":
            counts["ok"] += 1
            continue
        if r.pmc is None or pd.isna(r.pmc):
            counts["senza prezzo"] += 1
            continue
        qty = r.quantita if r.azione == "nuovo" else abs(r.differenza)
        side = "acquisto" if (r.azione == "nuovo" or r.differenza > 0) else "vendita"
        securities.add_trade(r.isin, on, side, qty, float(r.pmc), 0, r.valuta, "", NOTE)
        counts[r.azione] += 1
    return counts
