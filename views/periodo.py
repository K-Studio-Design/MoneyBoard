"""Dettagli che si aprono dai riquadri in cima ad Analisi: spese, entrate, risparmio e medie del periodo scelto."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n
from core.i18n import t
from views import focus, style, ui

KINDS = ("spese", "entrate", "risparmio", "media_mese", "media_giorno", "media_spesa")
# fasce di importo per «Media per spesa» (limite superiore escluso)
BUCKETS = [0, 10, 25, 50, 100, 250, 500, float("inf")]


def title(kind: str) -> str:
    return {"spese": t("Spese"), "entrate": t("Entrate"), "risparmio": t("Risparmio"),
            "media_mese": t("Media al mese"), "media_giorno": t("Media al giorno"),
            "media_spesa": t("Media per spesa")}[kind]


def open_detail(kind: str, start: date, end: date, excluded: list[str] | tuple[str, ...] = ()) -> None:
    """Finestra di dettaglio per uno dei riquadri di Analisi (stesso periodo e stesse categorie escluse)."""
    st.dialog(f"{title(kind)} · {_period(start, end)}", width="large")(_body)(
        kind, start.isoformat(), end.isoformat(), tuple(excluded))


def _period(start: date, end: date) -> str:
    return t("dal {a} al {b}", a=f"{start:{i18n.strf()}}", b=f"{end:{i18n.strf()}}")


def _data(start: date, end: date, excluded: tuple[str, ...]):
    df = ui.prepared_transactions()
    if df.empty:
        return df, df, df
    if excluded:
        df = df[~df["category"].isin(list(excluded))]
    length = (end - start).days + 1
    p_end = start - timedelta(days=1)
    p_start = p_end - timedelta(days=length - 1)
    return df, ui.filter_period(df, start, end), ui.filter_period(df, p_start, p_end)


def _months(start: date, end: date) -> pd.PeriodIndex:
    return pd.period_range(pd.Timestamp(start).to_period("M"), pd.Timestamp(end).to_period("M"), freq="M")


def _vs(cur_v: float, prev_v: float) -> str | None:
    return t("{p}% sul periodo precedente", p=f"{(cur_v - prev_v) / prev_v * 100:+.0f}") if prev_v else None


def _open_tx(sel) -> None:
    if sel is not None:
        st.session_state[focus.PENDING] = int(sel)
        st.rerun()


def _open_cat(sel, start: date, end: date) -> None:
    if sel:
        st.session_state[focus.PENDING_CAT] = (sel, start.isoformat(), end.isoformat())
        st.rerun()


def _body(kind: str, start_iso: str, end_iso: str, excluded: tuple[str, ...]) -> None:
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    df, cur, prev = _data(start, end, excluded)
    if cur.empty:
        st.caption(t("Nessun movimento nel periodo."))
        return
    if kind in ("spese", "entrate"):
        _flows(kind, cur, prev, start, end)
    elif kind == "risparmio":
        _savings(cur, prev, start, end)
    elif kind == "media_mese":
        _per_month(cur, start, end)
    elif kind == "media_giorno":
        _per_day(cur, start, end)
    else:
        _per_expense(cur, start, end)


# ---------------------------------------------------------------- spese / entrate
def _flows(kind: str, cur: pd.DataFrame, prev: pd.DataFrame, start: date, end: date) -> None:
    col = "spesa" if kind == "spese" else "entrata"
    tot, tot_prev = float(cur[col].sum()), float(prev[col].sum())
    n = int((cur[col] > 0).sum())
    months = ui.months_in(start, end)
    up_is_bad = col == "spesa"
    style.kpis(cols=4, items=[
        (t("Totale"), ui.money(tot), _vs(tot, tot_prev),
         ("neg" if (tot > tot_prev) == up_is_bad else "pos") if tot_prev else ""),
        (t("Periodo precedente"), ui.money(tot_prev)),
        (t("Media al mese"), ui.money(tot / months)),
        (t("Movimenti"), f"{n}", t("in media {v}", v=ui.money(tot / n)) if n else None),
    ])
    by_m = cur.groupby("mese")[col].sum().reindex(_months(start, end), fill_value=0)
    color = style.SPESA if col == "spesa" else style.ENTRATA
    fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in by_m.index], y=by_m.values, marker_color=color,
                           hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    st.subheader(t("Mese per mese"))
    style.chart(fig, height=210, legend=False)
    left, right = st.columns([2, 3], gap="medium")
    with left:
        st.subheader(t("Per categoria"))
        cats = cur[cur[col] > 0].groupby("cat_label")[col].sum().sort_values(ascending=False)
        cmap = ui.color_map()
        sel = style.category_bars([(c, float(v), cmap.get(c, "#A3A0B5")) for c, v in cats.items()],
                                  lambda v: ui.money(v), limit=8, key=f"per_cat_{kind}_{start}_{end}")
        _open_cat(sel, start, end)
    with right:
        st.subheader(t("Le spese più alte") if col == "spesa" else t("Le entrate più alte"))
        top = cur[cur[col] > 0].sort_values(col, ascending=False).head(10)
        _open_tx(style.tx_list(top, lambda v, c: ui.money(v, c), ui.color_map(), db.base_currency(),
                               key=f"per_top_{kind}_{start}_{end}"))
    st.caption(t("Clicca su una categoria o su un movimento per il dettaglio."))


# ---------------------------------------------------------------- risparmio
def _savings(cur: pd.DataFrame, prev: pd.DataFrame, start: date, end: date) -> None:
    by = cur.groupby("mese")[["entrata", "spesa"]].sum().reindex(_months(start, end), fill_value=0)
    by["saldo"] = by["entrata"] - by["spesa"]
    ent, spe = float(cur["entrata"].sum()), float(cur["spesa"].sum())
    saldo = ent - spe
    saldo_prev = float(prev["entrata"].sum() - prev["spesa"].sum())
    rate = saldo / ent * 100 if ent > 0 else None
    best, worst = by["saldo"].idxmax(), by["saldo"].idxmin()
    style.kpis(cols=4, items=[
        (t("Risparmio"), ui.money(saldo), _vs(saldo, saldo_prev) if saldo_prev > 0 else None,
         "pos" if saldo >= 0 else "neg"),
        (t("Tasso di risparmio"), f"{rate:.0f}%" if rate is not None else "–", t("sulle entrate del periodo")),
        (t("Mese migliore"), ui.month_label(best), ui.money(float(by.loc[best, "saldo"])), "pos"),
        (t("Mese peggiore"), ui.month_label(worst), ui.money(float(by.loc[worst, "saldo"])),
         "neg" if by.loc[worst, "saldo"] < 0 else ""),
    ])
    fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in by.index], y=by["saldo"].values,
                           marker_color=[style.ENTRATA if v >= 0 else style.SPESA for v in by["saldo"].values],
                           hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    st.subheader(t("Saldo mese per mese"))
    style.chart(fig, height=220, legend=False)
    tab = pd.DataFrame({
        t("Mese"): [ui.month_label(p) for p in by.index],
        t("Entrate"): by["entrata"].values, t("Spese"): by["spesa"].values, t("Risparmio"): by["saldo"].values,
        t("Tasso di risparmio"): [(s / e * 100) if e > 0 else None for s, e in zip(by["saldo"], by["entrata"])],
    })
    style.table(tab, {t("Entrate"): "num", t("Spese"): "num", t("Risparmio"): "num",
                      t("Tasso di risparmio"): ("pct", 0)}, neg=(t("Risparmio"), t("Tasso di risparmio")))
    st.caption(t("Verde: hai risparmiato; rosso: hai speso più di quanto è entrato. "
                 "I trasferimenti tra i tuoi conti e gli investimenti non contano."))


# ---------------------------------------------------------------- media al mese
def _per_month(cur: pd.DataFrame, start: date, end: date) -> None:
    by = cur.groupby("mese")["spesa"].sum().reindex(_months(start, end), fill_value=0)
    avg = float(cur["spesa"].sum()) / ui.months_in(start, end)
    hi, lo = by.idxmax(), by.idxmin()
    style.kpis(cols=4, items=[
        (t("Media al mese"), ui.money(avg), t("{n} mesi", n=len(by))),
        (t("Mese tipico"), ui.money(float(by.median())), t("mediana")),
        (t("Mese più caro"), ui.month_label(hi), ui.money(float(by.loc[hi])), "neg"),
        (t("Mese più leggero"), ui.month_label(lo), ui.money(float(by.loc[lo])), "pos"),
    ])
    fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in by.index], y=by.values,
                           marker_color=[style.SPESA if v > avg else style.rgba(style.SPESA, 0.45) for v in by.values],
                           hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    fig.add_hline(y=avg, line_dash="dash", line_color=style.ACCENT,
                  annotation_text=t("media {v}", v=ui.money(avg)), annotation_position="top left")
    st.subheader(t("Spese mese per mese"))
    style.chart(fig, height=240, legend=False)
    st.caption(t("In colore pieno i mesi sopra la media. Se il primo o l'ultimo mese non sono interi, la media "
                 "tiene conto dei giorni effettivi del periodo."))
    st.subheader(t("Dove cambia di più"))
    piv = cur[cur["spesa"] != 0].pivot_table(index="cat_label", columns="mese", values="spesa", aggfunc="sum",
                                              fill_value=0)
    if not piv.empty:
        spread = (piv.max(axis=1) - piv.min(axis=1)).sort_values(ascending=False).head(6)
        cmap = ui.color_map()
        style.category_bars([(c, float(v), cmap.get(c, "#A3A0B5")) for c, v in spread.items()],
                            lambda v: ui.money(v), limit=6)
        st.caption(t("Differenza tra il mese più alto e il più basso di ogni categoria: sono le spese che fanno "
                     "variare di più il totale."))


# ---------------------------------------------------------------- media al giorno
def _per_day(cur: pd.DataFrame, start: date, end: date) -> None:
    days = pd.date_range(start, end, freq="D")
    per_day = cur.groupby(cur["date"].dt.normalize())["spesa"].sum().reindex(days, fill_value=0)
    avg = float(per_day.mean()) if len(per_day) else 0.0
    zero = int((per_day <= 0.005).sum())
    top_day = per_day.idxmax() if len(per_day) and per_day.max() > 0 else None
    items = [
        (t("Media al giorno"), ui.money(avg), t("{n} giorni", n=len(per_day))),
        (t("Giorno tipico"), ui.money(float(per_day.median())), t("mediana")),
        (t("Giorni senza spese"), f"{zero}", t("su {n}", n=len(per_day))),
    ]
    ids = [None, None, None]
    if top_day is not None:
        items.append((t("Giorno più costoso"), ui.money(float(per_day.max())), f"{top_day:{i18n.strf()}}", "neg"))
        ids.append("max")
    pick = style.kpis(items, cols=len(items), key=f"per_day_kpis_{start}_{end}", ids=ids)
    if pick == "max" and top_day is not None:
        st.session_state[focus.PENDING_DAY] = top_day.date().isoformat()
        st.rerun()
    dm = "%m/%d" if i18n.is_en() else "%d/%m"
    fig = go.Figure(go.Bar(x=per_day.index, y=per_day.values,
                           marker_color=[style.SPESA if v > avg else style.rgba(style.SPESA, 0.45)
                                         for v in per_day.values],
                           hovertemplate="%{x|" + dm + "}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    fig.add_hline(y=avg, line_dash="dash", line_color=style.ACCENT,
                  annotation_text=t("media {v}", v=ui.money(avg)), annotation_position="top left")
    st.subheader(t("Giorno per giorno"))
    style.chart(fig, height=230, legend=False)
    st.caption(t("Il giorno più costoso si apre nel calendario: clicca sul suo riquadro."))
    st.subheader(t("Per giorno della settimana"))
    wd = per_day.groupby(per_day.index.weekday).mean().reindex(range(7), fill_value=0)
    fig = go.Figure(go.Bar(x=[i18n.weekday(i, short=True) for i in range(7)], y=wd.values,
                           marker_color=[style.SPESA if i < 5 else style.ACCENT for i in range(7)],
                           hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
    style.chart(fig, height=200, legend=False)


# ---------------------------------------------------------------- media per spesa
def _bucket_label(lo: float, hi: float) -> str:
    if hi == float("inf"):
        return t("oltre {v}", v=ui.money(lo, decimals=0))
    if lo == 0:
        return t("fino a {v}", v=ui.money(hi, decimals=0))
    return f"{ui.money(lo, decimals=0)} – {ui.money(hi, decimals=0)}"


def _per_expense(cur: pd.DataFrame, start: date, end: date) -> None:
    sp = cur[cur["spesa"] > 0].copy()
    if sp.empty:
        st.caption(t("Nessuna spesa nel periodo."))
        return
    n, tot = len(sp), float(sp["spesa"].sum())
    small = sp[sp["spesa"] < 25]
    style.kpis(cols=4, items=[
        (t("Media per spesa"), ui.money(tot / n), t("{n} movimenti di spesa", n=n)),
        (t("Spesa tipica"), ui.money(float(sp["spesa"].median())), t("mediana")),
        (t("Spesa più alta"), ui.money(float(sp["spesa"].max()))),
        (t("Piccole spese (sotto {v})", v=ui.money(25, decimals=0)), f"{len(small) / n * 100:.0f}%",
         t("{v} in tutto", v=ui.money(float(small["spesa"].sum())))),
    ])
    sp["fascia"] = pd.cut(sp["spesa"], BUCKETS, right=False, labels=False)
    g = sp.groupby("fascia")["spesa"].agg(["count", "sum"]).reindex(range(len(BUCKETS) - 1), fill_value=0)
    labels = [_bucket_label(BUCKETS[i], BUCKETS[i + 1]) for i in range(len(BUCKETS) - 1)]
    fig = go.Figure()
    fig.add_bar(x=labels, y=g["count"].values, name=t("Quante spese"), marker_color=style.ACCENT,
                hovertemplate="%{x}<br>%{y}<extra></extra>")
    st.subheader(t("Quante spese per fascia di importo"))
    style.chart(fig, height=220, legend=False)
    share = g["sum"] / tot * 100 if tot else g["sum"] * 0
    st.caption(" · ".join(t("{fascia}: {n} spese, {p}% del totale", fascia=lab, n=int(c), p=f"{s:.0f}")
                          for lab, c, s in zip(labels, g["count"].values, share.values) if c))
    st.subheader(t("Le spese più alte"))
    top = sp.sort_values("spesa", ascending=False).head(10)
    _open_tx(style.tx_list(top, lambda v, c: ui.money(v, c), ui.color_map(), db.base_currency(),
                           key=f"per_exp_{start}_{end}"))
