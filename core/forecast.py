"""Previsione di fine mese: quanto ti resterà, dati gli accrediti e addebiti attesi e la spesa quotidiana tipica.

- Eventi attesi: dalle serie ricorrenti attive (stipendio, abbonamenti, rate…), con le loro regole sulle date.
- Spesa quotidiana «libera»: media degli ultimi 90 giorni senza i pagamenti ricorrenti (già contati come eventi)
  e senza le singole spese eccezionali (sopra il 98° percentile, es. un mobile o un volo).
- Se si conoscono i saldi reali dei conti, si proietta il saldo dei conti; altrimenti il risultato del mese
  (entrate meno spese dal 1° del mese). Il saldo reale di un conto viene:
  · dalla banca, se il conto è collegato (Collega banche) e la banca ha dato il saldo: si aggiorna a ogni
    sincronizzazione e il saldo scritto a mano per quel conto non conta;
  · altrimenti dal saldo scritto a mano nel Profilo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from core import db, recurring

BALANCES_KEY = "account_balances"   # {"conto|valuta": scostamento tra saldo reale e somma dei movimenti}


@dataclass
class Forecast:
    mode: str                        # 'saldo' (saldi dei conti) oppure 'mese' (entrate - spese del mese)
    today: date
    month_end: date
    actual: pd.Series                # valore giorno per giorno fino a oggi
    projected: pd.Series             # da oggi a fine mese
    events: list = field(default_factory=list)   # (data, nome, importo con segno, serie)
    daily: float = 0.0               # spesa quotidiana libera stimata
    expected_in: float = 0.0
    expected_out: float = 0.0
    start_value: float = 0.0
    end_value: float = 0.0
    min_value: float = 0.0
    min_date: date | None = None
    accounts: list = field(default_factory=list)  # conti inclusi nel saldo


# ---------------------------------------------------------------- saldi reali dei conti
def balance_offsets() -> dict[str, float]:
    try:
        v = json.loads(db.get_setting(BALANCES_KEY, "{}") or "{}")
        return {str(k): float(x) for k, x in v.items()} if isinstance(v, dict) else {}
    except (ValueError, TypeError, AttributeError):
        return {}


def set_real_balance(account: str, ccy: str, real: float | None, tx: pd.DataFrame) -> None:
    """Salva il saldo reale di oggi (None = non usare questo conto nella previsione del saldo)."""
    cur = balance_offsets()
    key = f"{account}|{ccy}"
    if real is None:
        cur.pop(key, None)
    else:
        computed = float(tx.loc[(tx["account"] == account) & (tx["currency"] == ccy), "amount"].sum())
        cur[key] = float(real) - computed
    db.set_setting(BALANCES_KEY, json.dumps(cur))


def bank_balances() -> dict[str, dict]:
    """Saldi dati dalla banca per conto dell'app e valuta: {"conto|valuta": {"balance", "date", "type"}}.
    Solo conti (le carte di credito hanno il loro saldo, che non è denaro del conto) già sincronizzati."""
    try:
        from core import enablebanking as eb
        accs = eb.accounts_df()
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for a in accs.to_dict("records"):
        if eb.is_card(a):
            continue
        bal = a.get("balance")
        if bal is None or pd.isna(bal):
            continue
        ccy = str(a.get("balance_currency") or a.get("currency") or "").upper()
        acc = a.get("label") or a.get("aspsp_name")
        if not acc or not ccy:
            continue
        d = str(a.get("balance_date") or a.get("last_sync") or "")[:10]
        e = out.setdefault(f"{acc}|{ccy}", {"balance": 0.0, "date": d, "type": a.get("balance_type") or ""})
        e["balance"] += float(bal)
        e["date"] = max(e["date"], d)
    return out


def effective_offsets(tx: pd.DataFrame, banks: dict | None = None) -> dict[str, float]:
    """Scostamento (saldo reale − somma dei movimenti) di ogni conto usato per il saldo: quello calcolato dal saldo
    della banca per i conti collegati (vince sempre su quello scritto a mano), quello scritto a mano per gli altri.
    Per un conto collegato si sommano i movimenti fino al giorno del saldo della banca: quelli successivi lo
    aggiornano da soli."""
    offs = balance_offsets()
    banks = bank_balances() if banks is None else banks
    for key, b in banks.items():
        offs.pop(key, None)
        acc, ccy = key.split("|", 1)
        m = (tx["account"] == acc) & (tx["currency"] == ccy) if not tx.empty else None
        if m is not None and b["date"]:
            try:
                m &= tx["date"].dt.normalize() <= pd.Timestamp(b["date"])
            except (ValueError, TypeError):
                pass
        known = float(tx.loc[m, "amount"].sum()) if m is not None else 0.0
        has_tx = m is not None and bool(((tx["account"] == acc) & (tx["currency"] == ccy)).any())
        if not has_tx and abs(b["balance"]) < 0.005:
            continue  # sottoconto vuoto e senza movimenti (es. valuta mai usata): non serve
        offs[key] = b["balance"] - known
    return offs


def balance_source(key: str, banks: dict | None = None) -> str | None:
    """'banca', 'manuale' oppure None (saldo non conosciuto) per un conto «conto|valuta»."""
    banks = bank_balances() if banks is None else banks
    if key in banks:
        return "banca"
    return "manuale" if key in balance_offsets() else None


def account_balance(account: str, ccy: str, tx: pd.DataFrame, upto=None,
                    offsets: dict[str, float] | None = None) -> float | None:
    offs = effective_offsets(tx) if offsets is None else offsets
    off = offs.get(f"{account}|{ccy}")
    if off is None:
        return None
    m = (tx["account"] == account) & (tx["currency"] == ccy)
    if upto is not None:
        m &= tx["date"] <= pd.Timestamp(upto)
    return float(tx.loc[m, "amount"].sum()) + off


# ---------------------------------------------------------------- previsione
def daily_free_spending(df: pd.DataFrame, series: list, today: date, days: int = 90) -> float:
    """Spesa media al giorno negli ultimi `days` giorni, senza ricorrenti e senza spese eccezionali."""
    start = pd.Timestamp(today - timedelta(days=days))
    x = df[(df["date"] >= start) & (df["date"] < pd.Timestamp(today)) & (df["spesa_base"] != 0)]
    rec_ids = {i for s in series for i in s.ids}
    x = x[~x["id"].isin(rec_ids)]
    if x.empty:
        return 0.0
    cap = float(x.loc[x["spesa_base"] > 0, "spesa_base"].quantile(0.98)) if (x["spesa_base"] > 0).any() else 0.0
    vals = x["spesa_base"].where(x["spesa_base"] <= cap, 0.0) if cap > 0 else x["spesa_base"]
    first = max(start, df["date"].min())
    n = max((pd.Timestamp(today) - first).days, 1)
    return max(float(vals.sum()) / n, 0.0)


def build(df: pd.DataFrame, tx: pd.DataFrame, series: list, today: date | None = None,
          accounts: list[str] | None = None) -> Forecast:
    """df: movimenti preparati (ui.prepared_transactions, valori in valuta base);
    tx: movimenti grezzi (db.transactions_df) per i saldi; series: serie ricorrenti visibili;
    accounts: conti selezionati (None = tutti)."""
    from core import goals

    today = today or date.today()
    m0 = today.replace(day=1)
    month_end = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    active = [s for s in series if s.active and (not accounts or s.account in accounts)]

    days = pd.date_range(m0, month_end, freq="D")
    cur = df[(df["date"] >= pd.Timestamp(m0)) & (df["date"] <= pd.Timestamp(today))]
    net_by_day = (cur["entrata_base"] - cur["spesa_base"]).groupby(cur["date"].dt.normalize()).sum()
    net_by_day = net_by_day.reindex(days[days <= pd.Timestamp(today)], fill_value=0.0)

    # saldo dei conti, se si conoscono i saldi reali (dalla banca o scritti a mano)
    offsets = effective_offsets(tx)
    acc_keys = [k for k in offsets if not accounts or k.split("|")[0] in accounts]
    mode, start_value, included = "mese", 0.0, []
    if acc_keys and not tx.empty:
        total_before = 0.0
        for k in acc_keys:
            acc, ccy = k.split("|", 1)
            bal = account_balance(acc, ccy, tx, upto=pd.Timestamp(m0) - pd.Timedelta(days=1), offsets=offsets)
            rate = goals.rate_to_base(ccy, tx)
            if bal is None or rate is None:
                continue
            total_before += bal * rate
            included.append(f"{acc} {ccy}")
        if included:
            mode, start_value = "saldo", total_before
            # nel saldo contano anche i giroconti e gli investimenti dei conti inclusi: si usano i movimenti grezzi
            inc = tx[[f"{a}|{c}" in acc_keys for a, c in zip(tx["account"], tx["currency"])]]
            inc = inc[(inc["date"] >= pd.Timestamp(m0)) & (inc["date"] <= pd.Timestamp(today))]
            base = db.base_currency()
            v = inc["amount_base"].where(inc["amount_base"].notna() | (inc["currency"] != base), inc["amount"])
            net_by_day = v.groupby(inc["date"].dt.normalize()).sum().reindex(
                days[days <= pd.Timestamp(today)], fill_value=0.0)

    # nel saldo dei conti contano solo accrediti, addebiti e spese di quei conti
    if mode == "saldo":
        keys_in = {k for k in acc_keys if f"{k.split('|')[0]} {k.split('|')[1]}" in included}
        active = [s for s in active if f"{s.account}|{s.currency}" in keys_in]
        df = df[[f"{a}|{c}" in keys_in for a, c in zip(df["account"], df["currency"])]]

    # eventi attesi da oggi (escluso ciò che è già arrivato oggi) a fine mese
    events = []
    for d, s in recurring.upcoming(active, today, month_end):
        if s.last.date() == d.date() == today:
            continue
        sign = 1 if s.kind == "entrata" else -1
        events.append((d.date(), recurring.display_name(s), sign * s.typical_base, s))
    daily = daily_free_spending(df, active, today) if not df.empty else 0.0

    actual = start_value + net_by_day.cumsum()
    now_value = float(actual.iloc[-1]) if len(actual) else start_value
    fut = days[days > pd.Timestamp(today)]
    ev_by_day: dict = {}
    for d, _n, a, _s in events:
        ev_by_day[pd.Timestamp(d)] = ev_by_day.get(pd.Timestamp(d), 0.0) + a
    # gli eventi di oggi non ancora arrivati contano subito
    today_ev = ev_by_day.pop(pd.Timestamp(today), 0.0)
    vals, v = [now_value + today_ev], now_value + today_ev
    for d in fut:
        v += ev_by_day.get(d, 0.0) - daily
        vals.append(v)
    projected = pd.Series(vals, index=[pd.Timestamp(today)] + list(fut))
    exp_in = sum(a for _d, _n, a, _s in events if a > 0)
    exp_out = -sum(a for _d, _n, a, _s in events if a < 0)
    mn = projected.idxmin()
    return Forecast(mode=mode, today=today, month_end=month_end, actual=actual, projected=projected,
                    events=events, daily=daily, expected_in=exp_in, expected_out=exp_out, start_value=now_value,
                    end_value=float(projected.iloc[-1]), min_value=float(projected.min()), min_date=mn.date(),
                    accounts=included)
