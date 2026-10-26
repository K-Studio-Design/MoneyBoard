"""Collegamento agli exchange di criptovalute tramite ccxt (solo lettura dei saldi)."""
from __future__ import annotations

import pandas as pd

from core import db, fx

POPULAR = ["binance", "kraken", "coinbase", "bitstamp", "bitvavo", "bitfinex", "kucoin", "okx",
           "bybit", "cryptocom", "gateio", "htx", "bitget", "mexc"]
STABLE_USD = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "USDP"}
# ccxt usa alcune sigle diverse dalle valute ufficiali
CCXT_FIAT = {"ZEUR": "EUR", "ZUSD": "USD", "ZGBP": "GBP", "XXBT": "BTC", "XBT": "BTC", "XETH": "ETH"}


def available_exchanges() -> list[str]:
    import ccxt

    present = set(ccxt.exchanges)
    return [e for e in POPULAR if e in present] + sorted(present - set(POPULAR))


def needs_password(exchange_id: str) -> bool:
    import ccxt

    ex = getattr(ccxt, exchange_id)()
    return bool(ex.requiredCredentials.get("password"))


def _client(row: dict):
    import ccxt

    cls = getattr(ccxt, row["exchange_id"])
    params = {"apiKey": row["api_key"], "secret": row["secret"], "enableRateLimit": True, "timeout": 20000}
    if row.get("password"):
        params["password"] = row["password"]
    return cls(params)


def exchanges_df() -> pd.DataFrame:
    with db.connect() as con:
        return pd.read_sql_query("SELECT id, exchange_id, label, last_sync FROM exchanges ORDER BY id", con)


def add_exchange(exchange_id, label, api_key, secret, password="") -> None:
    with db.connect() as con:
        con.execute(
            "INSERT INTO exchanges(exchange_id, label, api_key, secret, password) VALUES (?,?,?,?,?)",
            (exchange_id, label or exchange_id, api_key.strip(), secret.strip(), (password or "").strip()),
        )


def delete_exchange(row_id: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM exchanges WHERE id=?", (int(row_id),))


def _asset_price_in(client, asset: str, base: str) -> float | None:
    """Prezzo di 1 asset in valuta base, usando prima lo stesso exchange poi Yahoo/BCE."""
    asset = CCXT_FIAT.get(asset, asset)
    if asset == base:
        return 1.0
    if asset in fx.COMMON_CURRENCIES:
        try:
            return fx.get_rate(asset, base)
        except fx.FxError:
            return None
    try:
        markets = client.load_markets()
        for quote in [base, "USDT", "USDC", "USD", "EUR"]:
            sym = f"{asset}/{quote}"
            if sym in markets:
                last = client.fetch_ticker(sym).get("last")
                if last:
                    q = "USD" if quote in STABLE_USD else quote
                    return float(last) * (1.0 if q == base else fx.get_rate(q, base))
    except Exception:
        pass
    if asset in STABLE_USD:
        try:
            return fx.get_rate("USD", base)
        except fx.FxError:
            return None
    try:  # Yahoo, es. BTC-EUR
        return fx._yahoo_rate(fx.date.today(), asset, base)
    except Exception:
        return None


def sync_exchange(row_id: int) -> pd.DataFrame:
    base = db.base_currency()
    with db.connect() as con:
        row = dict(con.execute("SELECT * FROM exchanges WHERE id=?", (int(row_id),)).fetchone())
    client = _client(row)
    bal = client.fetch_balance()
    totals = {k: v for k, v in (bal.get("total") or {}).items() if v and float(v) > 0}
    now = db.now_str()
    out = []
    with db.connect() as con:
        con.execute("DELETE FROM exchange_balances WHERE exchange_row=?", (int(row_id),))
    for asset, amount in totals.items():
        price = _asset_price_in(client, asset, base)
        value = float(amount) * price if price is not None else None
        out.append({"asset": CCXT_FIAT.get(asset, asset), "amount": float(amount), "value_base": value})
        with db.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO exchange_balances(exchange_row, asset, amount, value_base, updated) VALUES (?,?,?,?,?)",
                (int(row_id), CCXT_FIAT.get(asset, asset), float(amount), value, now),
            )
    with db.connect() as con:
        con.execute("UPDATE exchanges SET last_sync=? WHERE id=?", (now, int(row_id)))
    return pd.DataFrame(out)


def balances_df() -> pd.DataFrame:
    with db.connect() as con:
        return pd.read_sql_query(
            """SELECT e.label AS exchange, b.asset, b.amount, b.value_base, b.updated
               FROM exchange_balances b JOIN exchanges e ON e.id = b.exchange_row
               ORDER BY b.value_base DESC""",
            con,
        )
