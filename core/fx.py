"""Tassi di cambio.

Fonte principale: Frankfurter (tassi ufficiali BCE, gratuito, senza chiave API).
Riserva: Yahoo Finance (coppie tipo EURUSD=X, copre anche valute non BCE e crypto).
I tassi vengono salvati in cache nel database.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import requests

from core import db, i18n

FRANKFURTER_URLS = ["https://api.frankfurter.dev/v1", "https://api.frankfurter.app"]
TIMEOUT = 15

# Valute più comuni (BCE + qualche extra). L'utente può scriverne altre a mano.
COMMON_CURRENCIES = [
    "EUR", "USD", "GBP", "CHF", "JPY", "CNY", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK", "PLN",
    "CZK", "HUF", "RON", "BGN", "TRY", "ISK", "HKD", "SGD", "KRW", "INR", "IDR", "THB", "MYR",
    "PHP", "MXN", "BRL", "ZAR", "ILS", "AED", "SAR", "EGP", "MAD", "RSD", "ALL", "HRK",
]
CRYPTO = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "LTC", "USDT", "USDC", "BNB", "AVAX", "LINK"]


class FxError(Exception):
    pass


def _to_date(d) -> date:
    if d is None:
        return date.today()
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.fromisoformat(str(d)[:10]).date()


def _cache_get(d: date, base: str, quote: str) -> float | None:
    with db.connect() as con:
        row = con.execute(
            "SELECT rate FROM fx_cache WHERE date=? AND base=? AND quote=?", (d.isoformat(), base, quote)
        ).fetchone()
    return float(row["rate"]) if row else None


def _cache_put(d: date, base: str, quote: str, rate: float) -> None:
    with db.connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO fx_cache(date, base, quote, rate) VALUES (?,?,?,?)",
            (d.isoformat(), base, quote, float(rate)),
        )


def _frankfurter(path: str, params: dict) -> dict:
    last_err = None
    for root in FRANKFURTER_URLS:
        try:
            r = requests.get(f"{root}/{path}", params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            last_err = FxError(f"Frankfurter HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            last_err = e
    raise FxError(str(last_err))


def _yahoo_rate(d: date, base: str, quote: str) -> float:
    import yfinance as yf

    symbol = f"{base}-{quote}" if base in CRYPTO else f"{base}{quote}=X"
    start = d - timedelta(days=7)
    end = d + timedelta(days=1)
    hist = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
    if hist is None or hist.empty:
        raise FxError(i18n.t("Nessun dato Yahoo per {s}", s=symbol))
    return float(hist["Close"].dropna().iloc[-1])


def get_rate(base: str, quote: str, on=None) -> float:
    """Quanti `quote` vale 1 `base` alla data `on` (default oggi).
    Per date senza quotazione (weekend/festivi) usa l'ultimo giorno lavorativo precedente."""
    base, quote = base.upper().strip(), quote.upper().strip()
    if base == quote:
        return 1.0
    d = _to_date(on)
    if d > date.today():
        d = date.today()
    is_today = d == date.today()

    if not is_today:
        cached = _cache_get(d, base, quote)
        if cached:
            return cached

    rate = None
    errors = []
    if base not in CRYPTO and quote not in CRYPTO:
        try:
            path = "latest" if is_today else d.isoformat()
            data = _frankfurter(path, {"base": base, "symbols": quote})
            rate = float(data["rates"][quote])
        except Exception as e:  # valuta non BCE o rete assente
            errors.append(i18n.t("BCE: {err}", err=e))
    if rate is None:
        try:
            if quote in CRYPTO and base not in CRYPTO:
                rate = 1.0 / _yahoo_rate(d, quote, base)  # es. EUR->BTC = 1 / (BTC-EUR)
            else:
                rate = _yahoo_rate(d, base, quote)
        except Exception as e:
            errors.append(f"Yahoo: {e}")
    if rate is None:
        # ultimo tentativo: cache del giorno più vicino
        with db.connect() as con:
            row = con.execute(
                "SELECT rate FROM fx_cache WHERE base=? AND quote=? AND date<=? ORDER BY date DESC LIMIT 1",
                (base, quote, d.isoformat()),
            ).fetchone()
        if row:
            return float(row["rate"])
        raise FxError(i18n.t("Impossibile ottenere il cambio {pair} al {d}: ", pair=f"{base}/{quote}", d=d)
                      + " | ".join(errors))
    _cache_put(d, base, quote, rate)
    return rate


def prefetch_range(base: str, quote: str, start, end) -> None:
    """Scarica in un colpo solo la serie storica (utile per import di molte righe)."""
    base, quote = base.upper(), quote.upper()
    if base == quote or base in CRYPTO or quote in CRYPTO:
        return
    s, e = _to_date(start), min(_to_date(end), date.today())
    try:
        data = _frankfurter(f"{s.isoformat()}..{e.isoformat()}", {"base": base, "symbols": quote})
    except Exception:
        return
    rates = data.get("rates", {})
    known = {}
    for ds, vals in rates.items():
        if quote in vals:
            known[ds] = float(vals[quote])
    if not known:
        return
    # riempie weekend e festivi con l'ultimo tasso disponibile
    cur = s
    last = None
    first_key = min(known)
    while cur <= e:
        k = cur.isoformat()
        if k in known:
            last = known[k]
        elif last is None and k < first_key:
            cur += timedelta(days=1)
            continue
        if last is not None:
            _cache_put(cur, base, quote, last)
        cur += timedelta(days=1)


def convert(amount: float, base: str, quote: str, on=None) -> tuple[float, float]:
    """Ritorna (importo convertito, tasso usato)."""
    rate = get_rate(base, quote, on)
    return amount * rate, rate


def latest_table(base: str, quotes: list[str]) -> dict[str, float]:
    """Tassi attuali di `base` verso più valute (una chiamata BCE)."""
    base = base.upper()
    out = {}
    ecb_quotes = [q for q in quotes if q != base and q not in CRYPTO]
    if ecb_quotes:
        try:
            data = _frankfurter("latest", {"base": base, "symbols": ",".join(ecb_quotes)})
            out.update({k: float(v) for k, v in data.get("rates", {}).items()})
        except Exception:
            pass
    for q in quotes:
        if q == base:
            out[q] = 1.0
        elif q not in out:
            try:
                out[q] = get_rate(base, q)
            except Exception:
                pass
    return out


def to_base_rows(rows: list[dict], base: str) -> list[dict]:
    """Aggiunge fx_rate / amount_base / base_currency a righe con date, amount, currency."""
    # controvalore già fornito dalla banca (es. Revolut indica l'importo in EUR al cambio applicato)
    for r in rows:
        given = r.pop("_amount_eur", None)
        if given is not None and base == "EUR" and r["amount"]:
            r["currency"] = r["currency"].upper()
            r["base_currency"] = base
            r["amount_base"] = round(float(given), 2)
            r["fx_rate"] = abs(float(given) / float(r["amount"]))
            r["_done"] = True
    by_ccy: dict[str, list[str]] = {}
    for r in rows:
        if r.get("_done"):
            continue
        if r["currency"].upper() != base:
            by_ccy.setdefault(r["currency"].upper(), []).append(r["date"])
    for ccy, dates in by_ccy.items():
        if len(dates) > 3:
            prefetch_range(ccy, base, min(dates), max(dates))
    for r in rows:
        if r.pop("_done", False):
            continue
        ccy = r["currency"].upper()
        r["currency"] = ccy
        r["base_currency"] = base
        try:
            rate = get_rate(ccy, base, r["date"])
            r["fx_rate"] = rate
            r["amount_base"] = round(float(r["amount"]) * rate, 2)
        except FxError:
            r["fx_rate"] = None
            r["amount_base"] = None
    return rows


def recompute_missing_or_all(all_rows: bool = False) -> tuple[int, int]:
    """Ricalcola il controvalore in valuta base (dopo un cambio di valuta base o righe senza cambio)."""
    base = db.base_currency()
    df = db.transactions_df()
    if not all_rows:
        df = df[df["amount_base"].isna() | (df["base_currency"] != base)]
    ok = fail = 0
    for _, r in df.iterrows():
        try:
            rate = get_rate(r["currency"], base, r["date"].date())
            db.update_transaction(
                int(r["id"]), fx_rate=rate, amount_base=round(float(r["amount"]) * rate, 2), base_currency=base
            )
            ok += 1
        except FxError:
            fail += 1
    return ok, fail
