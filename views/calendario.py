"""Calendario delle spese: ogni giorno colorato in base a quanto hai speso, con gli addebiti previsti."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n, recurring
from core.i18n import t
from views import focus, mese, style, ui


_CAL_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const old = parentElement.querySelector('.as-cal');
  if (old) old.remove();
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls;
                                    if (text !== undefined) n.textContent = text; return n; };
  const root = el('div', 'as-cal');
  for (const h of data.head) root.appendChild(el('div', 'h', h));
  for (const c of data.cells) {
    if (!c.day) { root.appendChild(el('div', 'd empty')); continue; }
    const d = el('div', 'd' + (c.today ? ' today' : '') + (c.future ? ' future' : '') + (c.weekend ? ' we' : ''));
    if (c.level > 0) d.style.setProperty('--lv', c.level);
    d.appendChild(el('div', 'n', String(c.day)));
    if (c.spent) d.appendChild(el('div', 'a', c.spent));
    if (c.income) d.appendChild(el('div', 'i', c.income));
    for (const x of c.expected) d.appendChild(el('div', 'x', x));
    if (c.more) d.appendChild(el('div', 'x more', c.more));
    d.tabIndex = 0; d.setAttribute('role', 'button'); d.setAttribute('aria-label', c.label);
    d.title = c.label;
    const open = () => setTriggerValue('selected', c.iso);
    d.addEventListener('click', open);
    d.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    root.appendChild(d);
  }
  parentElement.appendChild(root);
}
"""
_cal = None


def _component():
    global _cal
    if _cal is None:
        import streamlit.components.v2 as v2
        _cal = v2.component("as_calendar", js=_CAL_JS, isolate_styles=False)
    return _cal


def _compact(v: float) -> str:
    """Importo breve per le celle: 1.234 €, 56 €, 7,50 €."""
    return ui.money(v, decimals=0 if abs(v) >= 100 else 2)


def render():
    style.header(t("Calendario"), ui.view_summary())
    df = ui.prepared_transactions()
    today = date.today()
    if "cal_month" not in st.session_state:
        st.session_state["cal_month"] = today.replace(day=1)
    m0: date = st.session_state["cal_month"]

    c1, c2, c3, c4 = st.columns([0.55, 0.55, 6, 1.1], vertical_alignment="center")
    if c1.button("", icon=":material/chevron_left:", key="cal_prev", help=t("Mese precedente"), width="stretch"):
        st.session_state["cal_month"] = (m0 - timedelta(days=1)).replace(day=1)
        st.rerun()
    if c2.button("", icon=":material/chevron_right:", key="cal_next", help=t("Mese successivo"), width="stretch"):
        st.session_state["cal_month"] = (m0 + timedelta(days=32)).replace(day=1)
        st.rerun()
    c3.markdown(f"### {i18n.month(m0.month).capitalize()} {m0.year}")
    if c4.button(t("Oggi"), key="cal_today", width="stretch", disabled=m0 == today.replace(day=1)):
        st.session_state["cal_month"] = today.replace(day=1)
        st.rerun()

    m_end = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    month = ui.filter_period(df, m0, m_end) if not df.empty else df
    spent = month.groupby(month["date"].dt.date)["spesa"].sum() if not month.empty else pd.Series(dtype=float)
    income = month.groupby(month["date"].dt.date)["entrata"].sum() if not month.empty else pd.Series(dtype=float)
    series = [s for s in ui.recurring_series() if s.active]
    names = recurring.custom_names()
    expected: dict[date, list[recurring.Series]] = {}
    for d, s in recurring.upcoming(series, max(m0, today), m_end):
        expected.setdefault(d.date(), []).append(s)

    # intensità del colore: rispetto al giorno più costoso degli ultimi 3 mesi (radice: meno "tutto o niente")
    ref_start = m0 - timedelta(days=92)
    ref = ui.filter_period(df, ref_start, m_end) if not df.empty else df
    ref_days = ref.groupby(ref["date"].dt.date)["spesa"].sum() if not ref.empty else pd.Series(dtype=float)
    top = float(ref_days.quantile(0.95)) if len(ref_days) else 0.0

    cells = [{"day": 0}] * m0.weekday()
    for i in range(m_end.day):
        d = m0 + timedelta(days=i)
        sp = float(spent.get(d, 0.0))
        inc = float(income.get(d, 0.0))
        ex = expected.get(d, [])
        level = round(min((max(sp, 0) / top) ** 0.5, 1.0), 3) if top > 0 and sp > 0 else 0
        label = _day_title(d, year=False)
        if sp:
            label += t(", spese {v}", v=ui.money(sp))
        if inc:
            label += t(", entrate {v}", v=ui.money(inc))
        if ex:
            label += t(", previsti: ") + "; ".join(recurring.display_name(s, names) for s in ex)
        cells.append({
            "day": d.day, "iso": d.isoformat(), "today": d == today, "future": d > today, "weekend": d.weekday() >= 5,
            "spent": _compact(sp) if sp > 0.005 else "", "income": "+" + _compact(inc) if inc > 0.005 else "",
            "level": level, "label": label,
            "expected": [recurring.display_name(s, names) for s in ex[:2]],
            "more": f"+{len(ex) - 2}" if len(ex) > 2 else "",
        })
    while len(cells) % 7:
        cells.append({"day": 0})

    left, right = st.columns([5, 2], gap="medium")
    with left, style.card("calendario"):
        res = _component()(data={"head": [i18n.weekday(i, short=True) for i in range(7)], "cells": json.loads(json.dumps(cells))}, key=f"cal_{m0}",
                           on_selected_change=lambda: None)
        sel = getattr(res, "selected", None) if res is not None else None
        st.caption(t("Più è intenso il colore, più hai speso quel giorno. In corsivo gli addebiti previsti. "
                     "Clicca su un giorno per vedere i movimenti."))
        if sel:
            st.dialog(_day_title(date.fromisoformat(sel)), width="large")(_day_body)(sel)

    with right:
        with style.card("cal_stats"):
            st.subheader(t("Il mese"))
            last_day = min(m_end, today) if m0 <= today else m_end
            n_days = (last_day - m0).days + 1 if m0 <= today else 0
            tot = float(month["spesa"].sum()) if not month.empty else 0.0
            zero = sum(1 for i in range(n_days) if spent.get(m0 + timedelta(days=i), 0.0) <= 0.005)
            items = [(t("Spese"), ui.money(tot), t("in {n} giorni", n=n_days) if n_days else t("mese futuro"))]
            ids = ["spese" if n_days else None]
            dmax = None
            if n_days:
                items.append((t("Giorni senza spese"), f"{zero}", t("su {n}", n=n_days)))
                ids.append("zero")
                if len(spent) and spent.max() > 0:
                    dmax = spent.idxmax()
                    items.append((t("Giorno più costoso"), ui.money(float(spent.max())), _day_title(dmax, year=False)))
                    ids.append("max")
            exp_out = [s for v in expected.values() for s in v if s.kind == "uscita"]
            if exp_out:
                n = len(exp_out)
                items.append((t("Addebiti previsti"), ui.money(sum(s.typical_base for s in exp_out), db.base_currency()),
                              t("da oggi a fine mese, 1 pagamento") if n == 1
                              else t("da oggi a fine mese, {n} pagamenti", n=n)))
                ids.append("previsti")
            pick = style.kpis(items, cols=1, key=f"cal_stats_{m0}", ids=ids)
            if pick == "spese":
                mese.open_detail("spese", m0, last_day)
            elif pick == "zero":
                mese.open_detail("media", m0, last_day)
            elif pick == "max" and dmax is not None:
                open_day(dmax)
            elif pick == "previsti":
                from views import abbonamenti
                abbonamenti.open_upcoming(max(m0, today), m_end, "uscita", t("Addebiti previsti"))
        with style.card("cal_week"):
            st.subheader(t("Per giorno della settimana"))
            last90 = ui.filter_period(df, today - timedelta(days=90), today) if not df.empty else df
            if not last90.empty:
                per_day = last90.groupby(last90["date"].dt.date)["spesa"].sum()
                full = pd.Series(0.0, index=pd.date_range(today - timedelta(days=90), today, freq="D").date)
                full.update(per_day)
                avg = full.groupby([pd.Timestamp(d).weekday() for d in full.index]).mean()
                fig = go.Figure(go.Bar(x=[i18n.weekday(i, short=True) for i in range(7)], y=[float(avg.get(i, 0)) for i in range(7)],
                                       marker_color=[style.SPESA if i < 5 else style.ACCENT for i in range(7)],
                                       hovertemplate="%{x}<br>%{y:,.2f} " + ui.display_ccy() + "<extra></extra>"))
                style.chart(fig, height=200, legend=False)
                st.caption(t("Spesa media per giorno della settimana, ultimi 90 giorni."))


def open_day(d: date) -> None:
    """Finestra con i movimenti (e gli addebiti previsti) di un giorno."""
    st.dialog(_day_title(d), width="large")(_day_body)(d.isoformat())


def _day_title(d: date, year: bool = True) -> str:
    """'Mercoledì 21 ottobre 2026' / 'Wednesday, October 21, 2026' (senza anno: 'Mercoledì 21 ottobre')."""
    wd = i18n.weekday(d.weekday())
    if i18n.is_en():
        return f"{wd}, {i18n.month(d.month)} {d.day}" + (f", {d.year}" if year else "")
    return f"{wd} {d.day} {i18n.month(d.month)}" + (f" {d.year}" if year else "")


def _day_body(iso: str) -> None:
    d = date.fromisoformat(iso)
    base = db.base_currency()
    df = ui.prepared_transactions()
    rows = df[df["date"].dt.date == d] if not df.empty else df
    sp, inc = (float(rows["spesa"].sum()), float(rows["entrata"].sum())) if not rows.empty else (0.0, 0.0)
    style.kpis([(t("Spese"), ui.money(sp)), (t("Entrate"), ui.money(inc)), (t("Movimenti"), f"{len(rows)}")], cols=3)
    if not rows.empty:
        sel = style.tx_list(rows.sort_values("valore"), lambda v, c: ui.money(v, c), ui.color_map(), base,
                            key=f"cal_day_{iso}")
        if sel is not None:
            st.session_state[focus.PENDING] = sel
            st.rerun()
    elif d <= date.today():
        st.caption(t("Nessun movimento in questo giorno."))
    series = [s for s in ui.recurring_series() if s.active]
    exp = [s for x, s in recurring.upcoming(series, d, d)]
    if exp and d >= date.today():
        st.subheader(t("Previsti"))
        names = recurring.custom_names()
        mini = "".join(f'<div><span>{style.e(recurring.display_name(s, names))}, {style.e(t(s.cadence))}</span>'
                       f'<span>{style.e((t("circa ") if s.variable else "") + ui.money(s.typical_base if s.variable else s.amount, base if s.variable else s.currency))}</span></div>'
                       for s in exp)
        st.html(f'<div class="as-mini">{mini}</div>')
