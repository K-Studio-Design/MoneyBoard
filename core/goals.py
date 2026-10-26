"""Calcoli per gli obiettivi di risparmio.

Tre modi di misurare quanto è stato messo da parte:
- manuale:   importo iniziale + versamenti/prelievi registrati a mano;
- conto:     saldo di un conto (in una valuta) calcolato dai movimenti, tarato sul saldo reale;
- risparmio: importo iniziale + (entrate - spese) dalla data di inizio, + eventuali correzioni a mano.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from core import db

MODES = {"manuale": "Versamenti a mano", "conto": "Saldo di un conto", "risparmio": "Risparmio da una data"}
DAYS_MONTH = 30.44


@dataclass
class Progress:
    current: float
    target: float
    pct: float
    remaining: float
    history: pd.Series            # valore giorno per giorno, dalla data di inizio a oggi
    pace: float | None            # crescita media al mese (ultimi 3 mesi o da quando esiste)
    needed: float | None          # quanto serve al mese per arrivare in tempo (se c'è una scadenza)
    months_left: float | None
    projected: pd.Timestamp | None  # data prevista al ritmo attuale
    status: str                   # raggiunto | in_linea | in_ritardo | fermo | senza_scadenza


def account_options(df: pd.DataFrame) -> list[tuple[str, str]]:
    if df.empty:
        return []
    return sorted({(a, c) for a, c in zip(df["account"], df["currency"])})


def account_balance(df: pd.DataFrame, account: str, ccy: str) -> float:
    m = (df["account"] == account) & (df["currency"] == ccy)
    return float(df.loc[m, "amount"].sum())


def bank_offset(tx: pd.DataFrame, account: str, ccy: str) -> float | None:
    """Taratura del saldo di un conto collegato alla banca (saldo della banca − movimenti), oppure None."""
    from core import forecast

    b = forecast.bank_balances().get(f"{account}|{ccy}")
    if b is None:
        return None
    return forecast.effective_offsets(tx, {f"{account}|{ccy}": b}).get(f"{account}|{ccy}", b["balance"])


def account_offset(goal: dict, tx: pd.DataFrame) -> float:
    """Per un obiettivo «conto»: il saldo della banca se il conto è collegato, altrimenti quello scritto a mano."""
    off = bank_offset(tx, goal.get("account"), goal.get("account_ccy"))
    return float(goal.get("balance_offset") or 0) if off is None else off


def _daily(values: pd.Series, start: pd.Timestamp, end: pd.Timestamp, initial: float) -> pd.Series:
    """Somma cumulata giorno per giorno di `values` (indicizzati per data), partendo da `initial`."""
    idx = pd.date_range(start, end, freq="D")
    if values.empty:
        return pd.Series(initial, index=idx, dtype=float)
    per_day = values.groupby(values.index.normalize()).sum()
    before = per_day[per_day.index < start].sum()
    per_day = per_day[(per_day.index >= start) & (per_day.index <= end)].reindex(idx, fill_value=0.0)
    return initial + before + per_day.cumsum()


def progress(goal: dict, tx: pd.DataFrame, today: date | None = None) -> Progress:
    today_ts = pd.Timestamp(today or date.today())
    start = pd.Timestamp(goal["start_date"])
    start = min(start, today_ts)
    target = float(goal["target"])
    mode = goal.get("mode") or "manuale"
    moves = db.goal_moves_df(int(goal["id"])) if goal.get("id") is not None else pd.DataFrame(columns=["date", "amount"])
    mv = pd.Series(moves["amount"].to_numpy(dtype=float), index=pd.to_datetime(moves["date"])) if not moves.empty \
        else pd.Series(dtype=float)

    if mode == "conto" and goal.get("account"):
        m = (tx["account"] == goal["account"]) & (tx["currency"] == goal.get("account_ccy"))
        vals = pd.Series(tx.loc[m, "amount"].to_numpy(dtype=float), index=pd.to_datetime(tx.loc[m, "date"]))
        # il saldo prima dell'inizio conta tutto (è il saldo del conto), più la taratura sul saldo reale
        # per un conto si mostra anche l'andamento dei 6 mesi prima dell'inizio (il saldo esisteva già)
        first = vals.index.min() if len(vals) else today_ts
        h_start = max(min(start, today_ts - pd.Timedelta(days=180)), first.normalize())
        hist = _daily(vals, min(h_start, start), today_ts, account_offset(goal, tx))
    elif mode == "risparmio":
        base = db.base_currency()
        t = tx[tx["kind"].isin(["uscita", "entrata"])]
        v = t["amount_base"].where(t["amount_base"].notna() | (t["currency"] != base), t["amount"])
        vals = pd.Series(v.to_numpy(dtype=float), index=pd.to_datetime(t["date"]))
        vals = vals[vals.index >= start]
        hist = _daily(pd.concat([vals, mv]), start, today_ts, float(goal.get("initial") or 0))
    else:
        hist = _daily(mv, start, today_ts, float(goal.get("initial") or 0))

    current = float(hist.iloc[-1]) if len(hist) else 0.0
    pct = max(0.0, current / target * 100) if target > 0 else 0.0
    remaining = max(target - current, 0.0)

    # ritmo: variazione degli ultimi 90 giorni (o da quando esiste, se meno, ma almeno 30 giorni)
    span = min(90, len(hist) - 1)
    pace = None
    if span >= 30:
        pace = (current - float(hist.iloc[-1 - span])) / span * DAYS_MONTH

    needed = months_left = None
    deadline = pd.Timestamp(goal["deadline"]) if goal.get("deadline") else None
    if deadline is not None:
        months_left = max((deadline - today_ts).days / DAYS_MONTH, 0.0)
        needed = remaining / max(months_left, 0.5) if remaining > 0 else 0.0

    projected = None
    if remaining <= 0:
        status = "raggiunto"
    elif pace is not None and pace > 0:
        projected = today_ts + pd.Timedelta(days=float(np.ceil(remaining / pace * DAYS_MONTH)))
        if deadline is None:
            status = "senza_scadenza"
        else:
            status = "in_linea" if projected <= deadline else "in_ritardo"
    else:
        if pace is None:
            status = "nuovo"
        else:
            status = "in_calo" if pace < 0 else "fermo"
    return Progress(current, target, pct, remaining, hist, pace, needed, months_left, projected, status)


def monthly_savings(tx: pd.DataFrame, months: int = 6, today: date | None = None) -> float | None:
    """Risparmio medio al mese (entrate - spese, valuta base) negli ultimi `months` mesi interi."""
    if tx.empty:
        return None
    today_ts = pd.Timestamp(today or date.today())
    end = today_ts.to_period("M") - 1
    start = end - (months - 1)
    base = db.base_currency()
    t = tx[tx["kind"].isin(["uscita", "entrata"])].copy()
    t["v"] = t["amount_base"].where(t["amount_base"].notna() | (t["currency"] != base), t["amount"])
    t["m"] = pd.to_datetime(t["date"]).dt.to_period("M")
    t = t[(t["m"] >= start) & (t["m"] <= end)]
    first = pd.to_datetime(tx["date"]).min().to_period("M")
    n = len(pd.period_range(max(start, first), end, freq="M")) if max(start, first) <= end else 0
    return float(t["v"].sum()) / n if n else None


def goal_currency(goal: dict) -> str:
    if (goal.get("mode") == "conto") and goal.get("account_ccy"):
        return str(goal["account_ccy"])
    return db.base_currency()


def rate_to_base(ccy: str, tx: pd.DataFrame) -> float | None:
    """Cambio verso la valuta base preso dall'ultimo movimento in quella valuta (nessuna connessione)."""
    base = db.base_currency()
    if ccy == base:
        return 1.0
    t = tx[(tx["currency"] == ccy) & tx["amount_base"].notna() & (tx["amount"] != 0)]
    if t.empty:
        return None
    r = t.sort_values("date").iloc[-1]
    return abs(float(r["amount_base"]) / float(r["amount"]))
