"""Budget mensili per categoria: un tetto di spesa al mese (in valuta base) per le categorie che vuoi tenere
d'occhio, più un tetto facoltativo per il totale delle spese. La spesa conta tutti i conti; i rimborsi sulla
stessa categoria la riducono (come nel resto dell'app)."""
from __future__ import annotations

import math
from datetime import date

import pandas as pd

from core import db
from core.i18n import t

TOTAL_KEY = "budget_total"
WARN_PCT = 80          # avviso quando si arriva a questa percentuale del budget


def get() -> dict[str, float]:
    """Budget per categoria (categoria salvata -> importo al mese)."""
    with db.connect() as con:
        rows = con.execute("SELECT category, amount FROM budgets WHERE amount > 0").fetchall()
    return {r["category"]: float(r["amount"]) for r in rows}


def total() -> float | None:
    try:
        v = float(db.get_setting(TOTAL_KEY, "") or 0)
    except ValueError:
        return None
    return v if v > 0 else None


def save(values: dict[str, float | None], total_amount: float | None = None) -> None:
    """Sostituisce tutti i budget per categoria (importi vuoti o zero = nessun budget) e quello totale."""
    clean = {}
    for cat, v in values.items():
        try:
            x = round(float(v), 2)
        except (TypeError, ValueError):
            continue
        if x > 0 and not math.isnan(x):
            clean[cat] = x
    with db.connect() as con:
        con.execute("DELETE FROM budgets")
        con.executemany("INSERT INTO budgets(category, amount) VALUES (?, ?)", list(clean.items()))
    try:
        tot = round(float(total_amount or 0), 2)
    except (TypeError, ValueError):
        tot = 0.0
    db.set_setting(TOTAL_KEY, str(tot) if tot > 0 and not math.isnan(tot) else "")


def signature() -> str:
    """Impronta dei budget (per le cache degli avvisi)."""
    return repr(sorted(get().items())) + "|" + str(total())


def spent(frame: pd.DataFrame, year: int, month: int) -> pd.Series:
    """Spesa del mese per categoria (valuta base). frame: core.report.frame()."""
    if frame.empty:
        return pd.Series(dtype=float)
    p = pd.Period(year=year, month=month, freq="M")
    m = frame[frame["mese"] == p]
    return m.groupby("category")["spesa_base"].sum()


def status(frame: pd.DataFrame, year: int, month: int, today: date | None = None) -> list[dict]:
    """Per ogni budget: categoria, budget, speso, rimasto, percentuale, previsione a fine mese (solo per il mese
    in corso), quanto si può spendere al giorno da qui a fine mese. La riga del totale ha category=None."""
    today = today or date.today()
    p = pd.Period(year=year, month=month, freq="M")
    days = p.days_in_month
    current = (today.year, today.month) == (year, month)
    elapsed = today.day if current else days
    left_days = days - today.day + 1 if current else 0
    by_cat = spent(frame, year, month)
    rows = []
    items = list(get().items())
    tot = total()
    if tot:
        items.append((None, tot))
    for cat, budget in items:
        s = float(by_cat.sum()) if cat is None else float(by_cat.get(cat, 0.0))
        left = budget - s
        rows.append({
            "category": cat, "budget": budget, "spent": s, "left": left,
            "pct": s / budget * 100 if budget else 0.0,
            "projected": s / elapsed * days if current and elapsed else s,
            "per_day": left / left_days if current and left_days and left > 0 else 0.0,
            "days_left": left_days,
        })
    return rows


def suggest(frame: pd.DataFrame, months: int = 3, today: date | None = None) -> dict[str, float]:
    """Proposta di budget: la spesa media al mese di ogni categoria negli ultimi `months` mesi completi,
    arrotondata per eccesso ai 10 (solo categorie di spesa con almeno qualcosa speso)."""
    today = today or date.today()
    if frame.empty:
        return {}
    cur = pd.Period(today, freq="M")
    window = [cur - i for i in range(1, months + 1)]
    m = frame[frame["mese"].isin(window) & (frame["kind"] == "uscita")]
    if m.empty:
        return {}
    first = frame["mese"].min()
    n = max(1, len([w for w in window if w >= first]))
    avg = m.groupby("category")["spesa_base"].sum() / n
    return {c: float(math.ceil(v / 10) * 10) for c, v in avg.items() if v >= 1}


def alerts(frame: pd.DataFrame, today: date | None = None) -> list:
    """Avvisi del mese in corso: categoria (o totale) arrivata all'80% del budget, oppure superata."""
    from core.alerts import Alert, _fmt, _id
    today = today or date.today()
    out = []
    base = db.base_currency()
    labels = db.category_labels()
    for r in status(frame, today.year, today.month, today):
        if r["pct"] < WARN_PCT:
            continue
        over = r["pct"] >= 100
        name = labels.get(r["category"], r["category"]) if r["category"] else t("Spese totali")
        kind = "budget_over" if over else "budget_warn"
        title = (t("{cat}: budget superato", cat=name) if over
                 else t("{cat}: {p}% del budget", cat=name, p=f"{r['pct']:.0f}"))
        if over:
            text = t("Questo mese hai speso {s} su un budget di {b} ({d} in più).", s=_fmt(r["spent"], base),
                     b=_fmt(r["budget"], base), d=_fmt(-r["left"], base))
        else:
            text = t("Questo mese hai speso {s} su {b}: restano {l}, circa {g} al giorno fino a fine mese.",
                     s=_fmt(r["spent"], base), b=_fmt(r["budget"], base), l=_fmt(r["left"], base),
                     g=_fmt(r["per_day"], base))
        out.append(Alert(_id(kind, r["category"] or "__totale__", today.year, today.month), "budget",
                         "alta" if over else "media", title, text, pd.Timestamp(today), category=r["category"]))
    return out
