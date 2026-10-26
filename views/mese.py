"""Dettagli che si aprono dalle card colorate della Panoramica: spese, entrate, saldo e media al giorno del mese."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n
from core.i18n import t
from core.merchants import merchant_key, pretty_name
from views import focus, style, ui

TITLES = {"spese": "Spese di {m}", "entrate": "Entrate di {m}", "saldo": "Saldo di {m}", "media": "Spesa al giorno, {m}"}


def open_detail(kind: str, month_start: date, today: date) -> None:
    m = i18n.month(month_start.month)
    st.dialog(t(TITLES[kind], m=m), width="large")(_body)(kind, month_start.isoformat(), today.isoformat())


def _open_tx(tx_id: int) -> None:
    st.session_state[focus.PENDING] = int(tx_id)
    st.rerun()


def _open_cat(cat: str, start: date, end: date) -> None:
    st.session_state[focus.PENDING_CAT] = (cat, start.isoformat(), end.isoformat())
    st.rerun()


def _body(kind: str, start_iso: str, today_iso: str) -> None:
    start, today = date.fromisoformat(start_iso), date.fromisoformat(today_iso)
    df = ui.prepared_transactions()
    if df.empty:
        st.caption(t("Nessun movimento."))
        return
    month_end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end = min(today, month_end)
    prev_start = (start - timedelta(days=1)).replace(day=1)
    prev_end_full = start - timedelta(days=1)
    prev_same = prev_start + timedelta(days=min(end.day, prev_end_full.day) - 1)
    cur = ui.filter_period(df, start, end)
    prev = ui.filter_period(df, prev_start, prev_same)
    # ultimi 12 mesi interi prima di questo, per le medie
    h_start = (pd.Timestamp(start) - pd.DateOffset(months=12)).date()
    hist = ui.filter_period(df, h_start, prev_end_full)
    n_hist = max(len(pd.period_range(max(pd.Timestamp(h_start), df["date"].min()).to_period("M"),
                                     pd.Timestamp(prev_end_full).to_period("M"), freq="M")), 1)
    {"spese": _spese, "entrate": _entrate, "saldo": _saldo, "media": _media}[kind](
        df, cur, prev, hist, n_hist, start, end, month_end, prev_start, today)


def _vs(cur_v: float, prev_v: float) -> str | None:
    return (t("{p}% sullo stesso periodo del mese scorso", p=f"{(cur_v - prev_v) / prev_v * 100:+.0f}")
            if prev_v else None)


def _cumulative(df, start: date, end: date, col: str, days: int) -> list[float]:
    x = ui.filter_period(df, start, end)
    per_day = x.groupby(x["date"].dt.day)[col].sum()
    return per_day.reindex(range(1, days + 1), fill_value=0).cumsum().tolist()


# ---------------------------------------------------------------- spese
def _spese(df, cur, prev, hist, n_hist, start, end, month_end, prev_start, today):
    tot, tot_prev = cur["spesa"].sum(), prev["spesa"].sum()
    avg_m = hist["spesa"].sum() / n_hist
    n = int((cur["spesa"] > 0).sum())
    style.kpis(cols=4, items=[
        (t("Spese del mese") if end >= month_end else t("Spese finora"), ui.money(tot), _vs(tot, tot_prev),
         "neg" if tot > tot_prev and tot_prev else ""),
        (t("Mese scorso, stessi giorni"), ui.money(tot_prev), t("dal 1 al {d}", d=min(end.day, 31))),
        (t("Media mensile"), ui.money(avg_m), t("ultimi {n} mesi", n=n_hist)),
        (t("Movimenti"), f"{n}", t("in media {v}", v=ui.money(tot / n)) if n else None),
    ])
    # andamento cumulato: questo mese contro il mese scorso
    days = month_end.day
    cum = _cumulative(df, start, end, "spesa", end.day)
    prev_days = (start - timedelta(days=1)).day
    cum_prev = _cumulative(df, prev_start, start - timedelta(days=1), "spesa", prev_days)
    fig = go.Figure()
    fig.add_scatter(x=list(range(1, prev_days + 1)), y=cum_prev, name=i18n.month(prev_start.month).capitalize(),
                    mode="lines", line=dict(color="#8B95A1", width=2, dash="dot"),
                    hovertemplate=t("giorno") + " %{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>")
    fig.add_scatter(x=list(range(1, end.day + 1)), y=cum, name=i18n.month(start.month).capitalize(), mode="lines",
                    line=dict(color=style.SPESA, width=3), fill="tozeroy", fillcolor=style.rgba(style.SPESA, 0.10),
                    hovertemplate=t("giorno") + " %{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>")
    if avg_m:
        fig.add_hline(y=avg_m, line_dash="dash", line_color=style.ACCENT, opacity=0.6,
                      annotation_text=t("media mensile {v}", v=ui.money(avg_m)), annotation_position="top left")
    fig.update_xaxes(range=[0.5, days + 0.5], dtick=5)
    st.subheader(t("Spesa accumulata nel mese"))
    style.chart(fig, height=250)

    left, right = st.columns(2, gap="medium")
    with left:
        st.subheader(t("Per categoria"))
        cats = cur[cur["spesa"] != 0].groupby("cat_label")["spesa"].sum().sort_values(ascending=False)
        cmap = ui.color_map()
        sel = style.category_bars([(c, float(v), cmap.get(c, "#A3A0B5")) for c, v in cats.items()],
                                  lambda v: ui.money(v), limit=7, key="mese_spese_cat")
        if sel:
            _open_cat(sel, start, end)
    with right:
        st.subheader(t("Dove"))
        x = cur[cur["spesa"] > 0].copy()
        if not x.empty:
            x["k"] = x["description"].map(merchant_key)
            g = x.groupby("k").agg(v=("spesa", "sum"), n=("id", "count"), d=("description", "last"))
            g = g.sort_values("v", ascending=False)
            style.category_bars([(f"{pretty_name(r.d, k)} ({r.n})", float(r.v), style.SPESA) for k, r in g.iterrows()],
                                lambda v: ui.money(v), limit=7, others=t("Altri {n} esercenti", n="{n}"))
    st.subheader(t("Le spese più alte"))
    top = cur[cur["spesa"] > 0].sort_values("spesa", ascending=False).head(8)
    sel = style.tx_list(top, lambda v, c: ui.money(v, c), ui.color_map(), db.base_currency(), key="mese_spese_top")
    if sel is not None:
        _open_tx(sel)


# ---------------------------------------------------------------- entrate
def _entrate(df, cur, prev, hist, n_hist, start, end, month_end, prev_start, today):
    tot, tot_prev = cur["entrata"].sum(), prev["entrata"].sum()
    avg_m = hist["entrata"].sum() / n_hist
    style.kpis(cols=3, items=[
        (t("Entrate del mese") if end >= month_end else t("Entrate finora"), ui.money(tot), _vs(tot, tot_prev)),
        (t("Mese scorso, stessi giorni"), ui.money(tot_prev)),
        (t("Media mensile"), ui.money(avg_m), t("ultimi {n} mesi", n=n_hist)),
    ])
    st.subheader(t("Ultimi 12 mesi"))
    m = ui.filter_period(df, (pd.Timestamp(start) - pd.DateOffset(months=11)).date(), end)
    by = m.groupby("mese")["entrata"].sum()
    months = pd.period_range(end=pd.Timestamp(start).to_period("M"), periods=12, freq="M")
    by = by.reindex(months, fill_value=0)
    fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in months], y=by.values,
                           marker_color=[style.ENTRATA if p == months[-1] else style.rgba(style.ENTRATA, 0.4) for p in months],
                           hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    if avg_m:
        fig.add_hline(y=avg_m, line_dash="dot", line_color="#8B95A1")
    style.chart(fig, height=220, legend=False)
    st.caption(t("Il mese in corso è evidenziato; la linea tratteggiata è la media mensile."))
    left, right = st.columns([2, 3], gap="medium")
    with left:
        st.subheader(t("Per categoria"))
        cats = cur[cur["entrata"] > 0].groupby("cat_label")["entrata"].sum().sort_values(ascending=False)
        cmap = ui.color_map()
        if cats.empty:
            st.caption(t("Nessuna entrata questo mese."))
        sel = style.category_bars([(c, float(v), cmap.get(c, "#A3A0B5")) for c, v in cats.items()],
                                  lambda v: ui.money(v), key="mese_ent_cat")
        if sel:
            _open_cat(sel, start, end)
    with right:
        st.subheader(t("Movimenti"))
        rows = cur[cur["entrata"] > 0].sort_values("date", ascending=False)
        if rows.empty:
            st.caption(t("Nessuna entrata questo mese."))
        sel = style.tx_list(rows.head(10), lambda v, c: ui.money(v, c), ui.color_map(), db.base_currency(),
                            key="mese_ent_tx")
        if sel is not None:
            _open_tx(sel)


# ---------------------------------------------------------------- saldo
def _saldo(df, cur, prev, hist, n_hist, start, end, month_end, prev_start, today):
    ent, spe = cur["entrata"].sum(), cur["spesa"].sum()
    saldo = ent - spe
    m = ui.filter_period(df, (pd.Timestamp(start) - pd.DateOffset(months=11)).date(), end)
    by = m.groupby("mese")[["entrata", "spesa"]].sum()
    months = pd.period_range(end=pd.Timestamp(start).to_period("M"), periods=12, freq="M")
    by = by.reindex(months, fill_value=0)
    by["saldo"] = by["entrata"] - by["spesa"]
    past = by.iloc[:-1]
    past = past[(past["entrata"] != 0) | (past["spesa"] != 0)]
    avg = float(past["saldo"].mean()) if len(past) else 0.0
    rate = (saldo / ent * 100) if ent > 0 else None
    style.kpis(cols=4, items=[
        (t("Saldo del mese"), ui.money(saldo), t("entrate meno spese"), "pos" if saldo >= 0 else "neg"),
        (t("Tasso di risparmio"), f"{rate:.0f}%" if rate is not None and rate >= 0 else "–",
         t("sulle entrate del mese") if rate is not None and rate >= 0 else t("spese oltre le entrate")),
        (t("Saldo medio al mese"), ui.money(avg), t("ultimi {n} mesi", n=len(past)), "pos" if avg >= 0 else "neg"),
        (t("Risparmiato in 12 mesi"), ui.money(float(by["saldo"].sum())), t("somma dei saldi mensili"),
         "pos" if by["saldo"].sum() >= 0 else "neg"),
    ])
    fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in months], y=by["saldo"].values,
                           marker_color=[style.ENTRATA if v >= 0 else style.SPESA for v in by["saldo"].values],
                           hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    st.subheader(t("Saldo mese per mese"))
    style.chart(fig, height=230, legend=False)
    st.caption(t("Verde: hai risparmiato; rosso: hai speso più di quanto è entrato. "
                 "I trasferimenti tra i tuoi conti e gli investimenti non contano."))
    if saldo < 0 or (ent == 0 and spe > 0):
        st.subheader(t("Perché è negativo"))
        hist_m = (hist.groupby("cat_label")["spesa"].sum() / n_hist)
        now_c = cur.groupby("cat_label")["spesa"].sum()
        diff = (now_c - hist_m.reindex(now_c.index, fill_value=0)).sort_values(ascending=False)
        items = []
        typical_in = float(past["entrata"].median()) if len(past) else 0.0  # mediana: un premio non la sposta
        if typical_in > ent:
            items.append((t("Entrate più basse del solito"), ui.money(ent),
                          t("di solito circa {v} al mese", v=ui.money(typical_in)), "neg"))
        for cat, d in diff.head(3).items():
            if d > 20:
                items.append((f"{cat}", ui.money(float(now_c[cat])),
                              t("{v} sopra la sua media mensile", v=ui.money(d)), "neg"))
        if items:
            style.kpis(items, cols=min(len(items), 4))
        else:
            st.caption(t("Nessuna categoria fuori dal solito: semplicemente le entrate del mese non sono ancora arrivate."))
    left, right = st.columns(2, gap="medium")
    with left:
        st.subheader(t("Entrate"))
        st.html(_mini(cur[cur["entrata"] > 0].groupby("cat_label")["entrata"].sum().sort_values(ascending=False)))
    with right:
        st.subheader(t("Spese"))
        st.html(_mini(cur[cur["spesa"] > 0].groupby("cat_label")["spesa"].sum().sort_values(ascending=False).head(8)))


def _mini(s: pd.Series) -> str:
    if s.empty:
        return f'<p class="as-goal-plan">{style.e(t("Nessun movimento."))}</p>'
    rows = "".join(f'<div><span>{style.e(k)}</span><span>{style.e(ui.money(float(v)))}</span></div>' for k, v in s.items())
    return f'<div class="as-mini">{rows}</div>'


# ---------------------------------------------------------------- media al giorno
def _media(df, cur, prev, hist, n_hist, start, end, month_end, prev_start, today):
    days = end.day
    tot = cur["spesa"].sum()
    per_day = cur.groupby(cur["date"].dt.day)["spesa"].sum().reindex(range(1, days + 1), fill_value=0)
    avg = tot / max(days, 1)
    hist_avg = hist["spesa"].sum() / (n_hist * 30.44) if not hist.empty else None
    median = float(per_day.median())
    zero = int((per_day <= 0.005).sum())
    style.kpis(cols=4, items=[
        (t("Media al giorno"), ui.money(avg), t("{n} giorni", n=days)),
        ((t("Totale del mese"), ui.money(tot), t("mese concluso")) if end >= month_end else
         (t("Stima a fine mese"), ui.money(avg * month_end.day), t("se continui così fino al {d}", d=month_end.day))),
        (t("Di solito"), ui.money(hist_avg) if hist_avg is not None else "–", t("al giorno, ultimi 12 mesi"),
         ("neg" if hist_avg and avg > hist_avg else "pos") if hist_avg else ""),
        (t("Giorno tipico"), ui.money(median), t("mediana; {n} giorni senza spese", n=zero)),
    ])
    st.subheader(t("Giorno per giorno"))
    fig = go.Figure()
    fig.add_bar(x=list(per_day.index), y=per_day.values, name=t("Spesa"),
                marker_color=[style.SPESA if v > avg else style.rgba(style.SPESA, 0.45) for v in per_day.values],
                hovertemplate=t("giorno") + " %{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>")
    fig.add_hline(y=avg, line_dash="dash", line_color=style.ACCENT,
                  annotation_text=t("media {v}", v=ui.money(avg)), annotation_position="top left")
    fig.update_xaxes(range=[0.5, month_end.day + 0.5], dtick=5)
    style.chart(fig, height=240, legend=False)
    st.caption(t("In colore pieno i giorni sopra la media. Pochi giorni costosi alzano molto la media: "
                 "per questo trovi anche il giorno tipico (mediana)."))
    left, right = st.columns(2, gap="medium")
    with left:
        st.subheader(t("Giorni più costosi"))
        top = per_day.sort_values(ascending=False).head(5)
        rows = []
        for d, v in top.items():
            if v <= 0:
                continue
            day = start.replace(day=int(d))
            x = cur[cur["date"].dt.date == day].sort_values("spesa", ascending=False)
            names = list(dict.fromkeys(pretty_name(r, merchant_key(r)) for r in x["description"]))
            what = ", ".join(names[:2]) + (t(" e altri {n}", n=len(names) - 2) if len(names) > 2 else "")
            rows.append(f'<div><span>{i18n.weekday(day.weekday(), short=True)} {day.day}: {style.e(what[:48])}</span>'
                        f'<span>{style.e(ui.money(float(v)))}</span></div>')
        st.html(f'<div class="as-mini">{"".join(rows)}</div>' if rows
                else f'<p class="as-goal-plan">{style.e(t("Nessuna spesa."))}</p>')
    with right:
        st.subheader(t("Per giorno della settimana"))
        wd = [per_day[[d for d in per_day.index if start.replace(day=int(d)).weekday() == w]].mean() for w in range(7)]
        fig = go.Figure(go.Bar(x=[i18n.weekday(i, short=True) for i in range(7)], y=[0 if pd.isna(v) else float(v) for v in wd],
                               marker_color=[style.SPESA if i < 5 else style.ACCENT for i in range(7)],
                               hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
        style.chart(fig, height=200, legend=False)
        st.caption(t("Media di questo mese per giorno della settimana."))
