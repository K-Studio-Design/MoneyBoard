"""Titoli finanziari: ricerca per ISIN, quotazioni e calcolo del portafoglio.

Le quotazioni arrivano da Yahoo Finance (libreria yfinance): Google Finance non offre
un'API pubblica, quindi non è collegabile in modo affidabile da un'app Python.
"""
from __future__ import annotations

import re
import pandas as pd

from core import db, fx, i18n

# borse preferite quando un ISIN è quotato su più mercati (prima = preferita)
PREFERRED_EXCHANGES = ["MIL", "GER", "AMS", "PAR", "EBS", "LSE", "NMS", "NYQ", "NGM", "PCX", "BTS"]
SUBUNIT_CURRENCIES = {"GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0), "ILA": ("ILS", 100.0), "ZAc": ("ZAR", 100.0)}
ASSET_TYPES = ["ETF", "Azione", "Obbligazione", "Fondo", "ETC/ETN", "Crypto", "Altro"]


def is_valid_isin(isin: str) -> bool:
    isin = (isin or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        return False
    digits = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    # Luhn sulla stringa di cifre, partendo da destra (la cifra di controllo è esclusa)
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(isin[-1])


def search_isin(isin: str) -> list[dict]:
    """Cerca i ticker Yahoo corrispondenti a un ISIN (o a un nome/ticker)."""
    import yfinance as yf

    query = isin.strip().upper()
    s = yf.Search(query, max_results=15, news_count=0, lists_count=0, recommended=0, raise_errors=False)
    out = []
    for q in s.quotes or []:
        sym = q.get("symbol")
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": q.get("longname") or q.get("shortname") or sym,
            "exchange": q.get("exchange", ""),
            "exchange_name": q.get("exchDisp", q.get("exchange", "")),
            "type": q.get("quoteType", ""),
        })

    def rank(c):
        ex = c["exchange"]
        return PREFERRED_EXCHANGES.index(ex) if ex in PREFERRED_EXCHANGES else len(PREFERRED_EXCHANGES)

    out.sort(key=rank)
    return out


def guess_asset_type(yahoo_type: str) -> str:
    return {"ETF": "ETF", "EQUITY": "Azione", "MUTUALFUND": "Fondo", "CRYPTOCURRENCY": "Crypto",
            "BOND": "Obbligazione"}.get((yahoo_type or "").upper(), "Altro")


def fetch_quote(ticker: str) -> tuple[float, str]:
    """Ultimo prezzo disponibile e valuta (già normalizzata, es. GBp -> GBP)."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    hist = t.history(period="7d", auto_adjust=False)
    if hist is None or hist.empty or hist["Close"].dropna().empty:
        raise ValueError(i18n.t("Nessuna quotazione trovata per {ticker}", ticker=ticker))
    price = float(hist["Close"].dropna().iloc[-1])
    currency = None
    try:
        currency = getattr(t.fast_info, "currency", None)
    except Exception:
        pass
    if not currency:
        try:
            currency = t.info.get("currency")
        except Exception:
            currency = None
    currency = currency or "EUR"
    if currency in SUBUNIT_CURRENCIES:
        real, div = SUBUNIT_CURRENCIES[currency]
        price, currency = price / div, real
    return price, currency.upper()


def price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if hist is None or hist.empty:
        return pd.DataFrame(columns=["Data", "Prezzo"])
    df = hist[["Close"]].reset_index()
    df.columns = ["Data", "Prezzo"]
    return df


# ---------------------------------------------------------------- DB helpers
def instruments_df() -> pd.DataFrame:
    with db.connect() as con:
        return pd.read_sql_query("SELECT * FROM instruments ORDER BY name", con)


def trades_df() -> pd.DataFrame:
    with db.connect() as con:
        df = pd.read_sql_query(
            """SELECT t.*, i.name, i.ticker FROM security_trades t
               JOIN instruments i ON i.isin = t.isin ORDER BY t.date, t.id""",
            con,
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def save_instrument(isin, ticker, name, asset_type, quote_currency, notes="") -> None:
    with db.connect() as con:
        con.execute(
            """INSERT INTO instruments(isin, ticker, name, asset_type, quote_currency, notes)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(isin) DO UPDATE SET ticker=excluded.ticker, name=excluded.name,
               asset_type=excluded.asset_type, quote_currency=excluded.quote_currency, notes=excluded.notes""",
            (isin.upper(), ticker, name, asset_type, quote_currency, notes),
        )


def delete_instrument(isin: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM instruments WHERE isin=?", (isin,))


def add_trade(isin, d, side, quantity, price, fees, currency, account="", notes="") -> None:
    with db.connect() as con:
        con.execute(
            """INSERT INTO security_trades(isin, date, side, quantity, price, fees, currency, account, notes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (isin, str(d)[:10], side, float(quantity), float(price), float(fees or 0), currency.upper(), account, notes),
        )


def delete_trades(ids: list[int]) -> None:
    with db.connect() as con:
        con.executemany("DELETE FROM security_trades WHERE id=?", [(int(i),) for i in ids])


def update_all_prices() -> tuple[int, list[str]]:
    """Aggiorna le quotazioni di tutti gli strumenti con ticker. Ritorna (aggiornati, errori)."""
    inst = instruments_df()
    ok, errors = 0, []
    for _, r in inst.iterrows():
        if not r["ticker"]:
            continue
        try:
            price, ccy = fetch_quote(r["ticker"])
            with db.connect() as con:
                con.execute(
                    "UPDATE instruments SET last_price=?, quote_currency=?, last_update=? WHERE isin=?",
                    (price, ccy, db.now_str(), r["isin"]),
                )
            ok += 1
        except Exception as e:
            errors.append(f"{r['name'] or r['isin']} ({r['ticker']}): {e}")
    db.set_setting("prices_last_update", db.now_str())
    return ok, errors


def portfolio(base: str | None = None) -> tuple[pd.DataFrame, float]:
    """Posizioni aperte con metodo del prezzo medio ponderato (PMC).
    Ritorna (tabella posizioni, plusvalenze realizzate in valuta base)."""
    base = base or db.base_currency()
    trades = trades_df()
    inst = instruments_df().set_index("isin")
    rows = []
    realized_total = 0.0
    for isin, g in trades.groupby("isin"):
        qty = cost = cost_base = 0.0
        realized_base = 0.0
        for _, t in g.sort_values(["date", "id"]).iterrows():
            q, p, f = float(t["quantity"]), float(t["price"]), float(t["fees"] or 0)
            try:
                rate = fx.get_rate(t["currency"], base, t["date"].date())
            except fx.FxError:
                rate = None
            if t["side"] == "acquisto":
                qty += q
                cost += q * p + f
                if rate is not None and cost_base is not None:
                    cost_base += (q * p + f) * rate
                else:
                    cost_base = None
            else:
                if qty <= 0:
                    continue
                q = min(q, qty)
                pmc = cost / qty
                pmc_base = (cost_base / qty) if cost_base is not None else None
                proceeds = q * p - f
                if rate is not None and pmc_base is not None:
                    realized_base += proceeds * rate - pmc_base * q
                cost -= pmc * q
                if cost_base is not None:
                    cost_base -= (pmc_base or 0) * q
                qty -= q
        realized_total += realized_base
        if qty <= 1e-9:
            continue
        info = inst.loc[isin] if isin in inst.index else None
        last_price = float(info["last_price"]) if info is not None and pd.notna(info["last_price"]) else None
        q_ccy = (info["quote_currency"] if info is not None and info["quote_currency"] else g["currency"].iloc[-1])
        value = value_base = None
        if last_price is not None:
            value = qty * last_price
            try:
                value_base = value * fx.get_rate(q_ccy, base)
            except fx.FxError:
                value_base = None
        pl_base = (value_base - cost_base) if (value_base is not None and cost_base is not None) else None
        rows.append({
            "ISIN": isin,
            "Nome": info["name"] if info is not None else isin,
            "Ticker": info["ticker"] if info is not None else "",
            "Tipo": info["asset_type"] if info is not None else "",
            "Quantità": qty,
            "PMC": cost / qty,
            "Valuta": q_ccy,
            "Ultimo prezzo": last_price,
            "Valore": value,
            f"Valore {base}": value_base,
            f"Costo {base}": cost_base,
            f"P/L {base}": pl_base,
            "P/L %": (pl_base / cost_base * 100) if (pl_base is not None and cost_base) else None,
            "Aggiornato": info["last_update"] if info is not None else None,
        })
    return pd.DataFrame(rows), realized_total

