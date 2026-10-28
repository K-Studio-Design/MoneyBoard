"""Avvisi su movimenti o andamenti insoliti, calcolati dai movimenti (niente tabelle in più).

Tipi:
- doppio:     due addebiti uguali (stesso conto, importo, esercente) a distanza di 0-1 giorni;
- insolita:   una spesa molto più alta del solito presso lo stesso esercente;
- grande:     una delle spese più alte dell'ultimo anno;
- categoria:  una categoria che questo mese è già molto sopra la sua media;
- prezzo:     un abbonamento che ha cambiato importo;
- nuovo:      un nuovo pagamento ricorrente;
- disdetto:   un pagamento ricorrente che non è più arrivato;
- scadenza:   un addebito ricorrente in arrivo nei prossimi giorni (promemoria);
- budget:     una categoria (o il totale) arrivata all'80% del budget del mese, o oltre (core/budgets.py).
Gli avvisi ignorati sono salvati nelle impostazioni (per id) e non ricompaiono.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date

import pandas as pd

from core import db, i18n, recurring
from core.i18n import t
from core.merchants import _TRANSFER_PREFIX, merchant_key

DISMISSED_KEY = "alerts_dismissed"
DELETED_KEY = "alerts_deleted"      # eliminati: non compaiono più da nessuna parte
LEVEL_ORDER = {"alta": 0, "media": 1, "info": 2}
ICONS = {"doppio": "content_copy", "insolita": "priority_high", "grande": "payments", "categoria": "trending_up",
         "prezzo": "sell", "nuovo": "autorenew", "disdetto": "event_busy", "scadenza": "event_upcoming",
         "budget": "account_balance_wallet"}
_NO_PRICE = {"Tasse e imposte", "Interessi e dividendi", "Stipendio", "Rimborsi", "Altre entrate"}
# categorie in cui gli importi variano per natura: niente avviso "spesa insolita" per esercente
_NO_UNUSUAL = {"Contanti e prelievi", "Regali e donazioni", "Trasferimenti tra conti", "Investimenti",
               "Tasse e imposte", "Commissioni bancarie"}


@dataclass
class Alert:
    aid: str
    kind: str
    level: str          # alta | media | info
    title: str
    text: str
    date: pd.Timestamp
    tx_id: int | None = None
    category: str | None = None
    sid: str | None = None

    @property
    def icon(self) -> str:
        return ICONS.get(self.kind, "info")


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:14]


def _fmt(x: float, ccy: str) -> str:
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(ccy, ccy)
    if i18n.is_en():
        return f"{'-' if x < 0 else ''}{sym}{' ' if len(sym) > 1 else ''}{abs(x):,.2f}"
    s = f"{abs(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if x < 0 else ''}{s} {sym}"


def _d(x) -> str:
    return f"{x:{i18n.strf()}}"


def compute(df: pd.DataFrame, series=None, today: date | None = None, horizon_days: int = 60,
            reminder_days: int = 0) -> list[Alert]:
    """df: transazioni come da db.transactions_df(); series: serie ricorrenti (core.recurring.detect);
    reminder_days: promemoria per gli addebiti ricorrenti attesi da oggi ai prossimi giorni (0 = nessuno)."""
    out: list[Alert] = []
    if df.empty:
        return out
    today_ts = pd.Timestamp(today or date.today())
    since = today_ts - pd.Timedelta(days=horizon_days)
    base = db.base_currency()
    d = df.copy()
    d["v"] = d["amount_base"].where(d["amount_base"].notna() | (d["currency"] != base), d["amount"])
    exp = d[(d["kind"] == "uscita") & (d["amount"] < 0) & d["v"].notna()].copy()
    exp["cost"] = -exp["v"]
    exp["mkey"] = exp["description"].map(merchant_key)
    refunds = d[d["amount"] > 0]

    # ---- addebito doppio
    # inseriti a mano: li hai scritti tu, non sono addebiti della banca
    recent = exp[(exp["date"] >= since) & (exp["source"] != "manuale")].sort_values("date")
    # movimenti divisi: le parti non sono addebiti a sé, il movimento diviso vale per il suo importo originale
    if "split_of" in recent.columns:
        recent = recent[recent["split_of"].isna()].copy()
        recent["amount"] = recent["split_total"].where(recent["split_total"].notna(), recent["amount"])
    for (_acc, _ccy, _amt, _mk), g in recent.groupby(["account", "currency", recent["amount"].round(2), "mkey"]):
        if len(g) < 2 or abs(_amt) < 10:
            continue
        g = g.sort_values("date")
        for a, b in zip(g.iloc[:-1].itertuples(), g.iloc[1:].itertuples()):
            if (b.date - a.date).days > 0:
                continue
            # rimborsato? un accredito dello stesso importo nei 15 giorni dopo
            back = refunds[(refunds["account"] == a.account) & (refunds["amount"].round(2) == round(-a.amount, 2))
                           & (refunds["date"] >= a.date) & (refunds["date"] <= a.date + pd.Timedelta(days=15))]
            if not back.empty:
                continue
            out.append(Alert(_id("doppio", a.id, b.id), "doppio", "alta", t("Possibile addebito doppio"),
                             t("{desc}: due addebiti da {v} lo stesso giorno ({d}) sul conto {acc}, e nessun rimborso "
                               "finora.", desc=a.description[:60], v=_fmt(-a.amount, a.currency), d=_d(a.date),
                               acc=a.account),
                             b.date, tx_id=int(b.id), category=a.category))

    # ---- spesa insolita per esercente (non per bonifici a persone, che variano per natura)
    for r in exp[exp["date"] >= since].itertuples():
        if r.category in _NO_UNUSUAL or str(r.description).lower().startswith(_TRANSFER_PREFIX):
            continue
        prev = exp[(exp["mkey"] == r.mkey) & (exp["date"] < r.date)]
        if len(prev) < 3:
            continue
        med = float(prev["cost"].median())
        # molto sopra il solito e sopra anche il massimo visto finora (esercenti con importi vari, es. Amazon, no)
        if med > 0 and r.cost >= 2.5 * med and r.cost >= 1.3 * float(prev["cost"].max()) and r.cost - med >= 20:
            out.append(Alert(_id("insolita", r.id), "insolita", "media", t("Spesa più alta del solito"),
                             t("{desc}: {v}, di solito spendi circa {med} (prima di oggi, al massimo {mx}).",
                               desc=r.description[:60], v=_fmt(r.cost, base), med=_fmt(med, base),
                               mx=_fmt(float(prev["cost"].max()), base)),
                             r.date, tx_id=int(r.id), category=r.category))

    # ---- tra le spese più alte dell'anno
    year = exp[exp["date"] >= today_ts - pd.Timedelta(days=365)]
    if len(year) >= 50:
        thr = max(float(year["cost"].quantile(0.99)), 100.0)
        # i pagamenti ricorrenti (affitto, rate…) sono previsti: non sono «spese importanti» da segnalare
        flagged = {a.tx_id for a in out} | {i for sr in (series or []) for i in sr.ids}
        for r in exp[(exp["date"] >= today_ts - pd.Timedelta(days=30)) & (exp["cost"] >= thr)].itertuples():
            if int(r.id) in flagged:
                continue
            rank = int((year["cost"] > r.cost).sum()) + 1
            out.append(Alert(_id("grande", r.id), "grande", "info", t("Spesa importante"),
                             (t("{desc}: {v}, la più alta degli ultimi 12 mesi.", desc=r.description[:60],
                                v=_fmt(r.cost, base)) if rank == 1 else
                              t("{desc}: {v}, la {rank} più alta degli ultimi 12 mesi.", desc=r.description[:60],
                                v=_fmt(r.cost, base), rank=i18n.ordinal(rank))),
                             r.date, tx_id=int(r.id), category=r.category))

    # ---- categoria sopra la media, nel mese in corso
    cur_p = today_ts.to_period("M")
    exp_all = d[d["kind"] == "uscita"].copy()
    exp_all["cost"] = -exp_all["v"]
    exp_all["m"] = exp_all["date"].dt.to_period("M")
    hist = exp_all[(exp_all["m"] < cur_p) & (exp_all["m"] >= cur_p - 6)]
    first_m = exp_all["m"].min()
    n_months = len(pd.period_range(max(cur_p - 6, first_m), cur_p - 1, freq="M")) if first_m < cur_p else 0
    if n_months >= 3:
        avg = hist.groupby("category")["cost"].sum() / n_months
        now = exp_all[exp_all["m"] == cur_p].groupby("category")["cost"].sum()
        for cat, val in now.items():
            a = float(avg.get(cat, 0.0))
            if cat in ("Contanti e prelievi", "Trasferimenti tra conti", "Investimenti"):
                continue
            if val >= 50 and val >= 1.5 * a and val - a >= 50:
                if a > 0:
                    txt = t("Questo mese sei già a {v}, di solito {a} al mese (+{p}%).", v=_fmt(val, base),
                            a=_fmt(a, base), p=f"{(val - a) / a * 100:.0f}")
                else:
                    txt = t("Questo mese sei a {v}; negli ultimi {n} mesi non avevi spese qui.", v=_fmt(val, base),
                            n=n_months)
                out.append(Alert(_id("categoria", cat, cur_p), "categoria", "media", t("{cat}: sopra la media", cat=db.category_label(cat)),
                                 txt, today_ts, category=cat))

    # ---- promemoria: addebiti ricorrenti in arrivo
    names = recurring.custom_names()
    if reminder_days > 0 and series:
        active = [s for s in series if s.active and s.kind == "uscita"]
        end = (today_ts + pd.Timedelta(days=reminder_days)).date()
        for d, s in recurring.upcoming(active, today_ts.date(), end):
            nm = recurring.display_name(s, names)
            n = (d.normalize() - today_ts.normalize()).days
            when = t("oggi") if n == 0 else t("domani") if n == 1 else t("tra {n} giorni", n=n)
            amt = (t("circa ") + _fmt(s.typical_base, base)) if s.variable else _fmt(s.amount, s.currency)
            out.append(Alert(_id("scadenza", s.sid, d.date()), "scadenza", "media",
                             t("{nm}: addebito {when}", nm=nm, when=when),
                             t("{amt} il {d} sul conto {acc} ({cad}).", amt=amt, d=_d(d), acc=s.account,
                               cad=t(s.cadence)),
                             d, sid=s.sid, category=s.category))

    # ---- abbonamenti
    for s in series or []:
        nm = recurring.display_name(s, names)
        if s.kind != "uscita":
            continue
        # cambio di prezzo: solo per ciò che si paga (non per tasse/ritenute, che variano con il reddito)
        if s.active and s.price_change and s.price_change_date >= since and s.category not in _NO_PRICE:
            a, b = s.price_change
            out.append(Alert(_id("prezzo", s.sid, s.price_change_date.date()), "prezzo", "media" if b > a else "info",
                             t("{nm}: aumento di prezzo", nm=nm) if b > a else t("{nm}: riduzione di prezzo", nm=nm),
                             t("Da {a} a {b} il {d} ({cad}).", a=_fmt(a, s.currency), b=_fmt(b, s.currency),
                               d=_d(s.price_change_date), cad=t(s.cadence)),
                             s.price_change_date, sid=s.sid, category=s.category))
        if s.active and s.first >= today_ts - pd.Timedelta(days=100):
            out.append(Alert(_id("nuovo", s.sid), "nuovo", "info", t("Nuovo pagamento ricorrente: {nm}", nm=nm),
                             t("{v} {cad}, dal {d}: circa {y} all'anno.", v=_fmt(s.amount, s.currency),
                               cad=t(recurring.CADENCE_ADJ[s.cadence]), d=_d(s.first), y=_fmt(s.yearly_base, base)),
                             s.first, sid=s.sid, category=s.category))
        if not s.active and s.count >= 3 and s.last >= today_ts - pd.Timedelta(days=120):
            out.append(Alert(_id("disdetto", s.sid, s.last.date()), "disdetto", "info",
                             t("{nm} non è più stato addebitato", nm=nm),
                             t("Era {cad} ({v}), l'ultimo il {d}. Se l'hai disdetto, tutto a posto; altrimenti "
                               "controlla il metodo di pagamento.", cad=t(s.cadence), v=_fmt(s.amount, s.currency),
                               d=_d(s.last)),
                             s.last, sid=s.sid, category=s.category))

    out.sort(key=lambda a: (LEVEL_ORDER[a.level], -a.date.value))
    # un solo avviso per movimento (il più importante)
    seen, res = set(), []
    for a in out:
        if a.tx_id is not None and a.tx_id in seen:
            continue
        if a.tx_id is not None:
            seen.add(a.tx_id)
        res.append(a)
    return res


def dismissed() -> set[str]:
    try:
        v = json.loads(db.get_setting(DISMISSED_KEY, "[]") or "[]")
        return {str(x) for x in v} if isinstance(v, list) else set()
    except (ValueError, TypeError):
        return set()


def deleted() -> set[str]:
    try:
        v = json.loads(db.get_setting(DELETED_KEY, "[]") or "[]")
        return {str(x) for x in v} if isinstance(v, list) else set()
    except (ValueError, TypeError):
        return set()


def delete(aids) -> None:
    """Elimina uno o più avvisi (anche dalla lista degli ignorati)."""
    aids = {aids} if isinstance(aids, str) else set(aids)
    db.set_setting(DELETED_KEY, json.dumps(sorted(deleted() | aids)[-5000:]))
    db.set_setting(DISMISSED_KEY, json.dumps(sorted(dismissed() - aids)))


def dismiss(aid: str, value: bool = True) -> None:
    cur = dismissed()
    cur.add(aid) if value else cur.discard(aid)
    db.set_setting(DISMISSED_KEY, json.dumps(sorted(cur)[-2000:]))

