"""Budget: quanto vuoi spendere ogni mese, categoria per categoria (e, volendo, in totale)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import budgets, db, i18n, report
from core.i18n import t
from views import style, ui

VER = "_bud_editor_ver"     # cambia per ricaricare la tabella (es. dopo «usa la media»)
PREFILL = "_bud_prefill"


def _month_label(p: pd.Period) -> str:
    return f"{i18n.month(p.month)} {p.year}".capitalize() if not i18n.is_en() else f"{i18n.month(p.month)} {p.year}"


def _color(pct: float) -> str:
    if pct >= 100:
        return style.SPESA
    if pct >= budgets.WARN_PCT:
        return "#F2A541"
    return style.ENTRATA


def _bars(rows: list[dict], base: str, current: bool) -> None:
    labels = db.category_labels()
    colors = ui.color_map()
    items = []
    for r in rows:
        name = labels.get(r["category"], r["category"]) if r["category"] else t("Spese totali")
        dot = style.safe_color(colors.get(r["category"], style.ACCENT)) if r["category"] else style.ACCENT
        col = _color(r["pct"])
        if r["left"] < 0:
            note = t("superato di {v}", v=ui.money(-r["left"], base))
        elif current and r["days_left"]:
            note = t("restano {v}, circa {g} al giorno", v=ui.money(r["left"], base), g=ui.money(r["per_day"], base))
        else:
            note = t("restano {v}", v=ui.money(r["left"], base))
        if current and r["left"] >= 0 and r["projected"] > r["budget"] * 1.02:
            note += t(" · al ritmo attuale arrivi a {v}", v=ui.money(r["projected"], base))
        width = max(0.0, min(r["pct"], 100.0))
        items.append(f'''<div class="as-cat as-budget"><div class="top"><div class="n"><i class="dot" style="background:{dot}"></i>
<span>{style.e(name)}</span></div><div><span class="amt">{style.e(ui.money(r["spent"], base))}</span>
<span class="pct">{style.e(t("di {b}", b=ui.money(r["budget"], base)))}</span></div></div>
<div class="track"><span style="width:{width:.1f}%;background:{col}"></span></div>
<div class="bnote"><span style="color:{col};font-weight:700">{r["pct"]:.0f}%</span> · {style.e(note)}</div></div>''')
    st.html('<style>.as-budget .bnote{font-size:.8rem;color:var(--as-muted);margin-top:.3rem;}</style>'
            f'<div class="as-cats">{"".join(items)}</div>')


def _editor(fr: pd.DataFrame, base: str) -> None:
    labels = db.category_labels()
    cats = db.categories_df()
    cats = cats[cats["kind"] == "uscita"]["name"].tolist()
    cur = budgets.get()
    avg = budgets.suggest(fr, months=3)
    pre = st.session_state.get(PREFILL)        # proposta non ancora salvata: resta finché non salvi
    values = pre if pre is not None else cur
    src = pd.DataFrame({"category": cats, "label": [labels.get(c, c) for c in cats],
                        "budget": [values.get(c) for c in cats],
                        "media": [avg.get(c) for c in cats]})
    src["budget"] = pd.to_numeric(src["budget"], errors="coerce")
    src["media"] = pd.to_numeric(src["media"], errors="coerce")
    ver = st.session_state.setdefault(VER, 0)
    ed = st.data_editor(
        src, hide_index=True, width="stretch", num_rows="fixed", key=f"bud_editor_{ver}",
        column_config={
            "category": None,
            "label": st.column_config.TextColumn(t("Categoria"), disabled=True),
            "budget": st.column_config.NumberColumn(t("Budget al mese ({ccy})", ccy=base), min_value=0.0, step=10.0,
                                                    format="%.2f", help=t("Vuoto = nessun budget per questa categoria")),
            "media": st.column_config.NumberColumn(t("Media ultimi 3 mesi"), format="%.0f", disabled=True),
        })
    tot_cur = budgets.total()
    tot = st.number_input(t("Budget per il totale delle spese ({ccy}, facoltativo)", ccy=base), min_value=0.0,
                          step=50.0, value=float(tot_cur or 0.0), key=f"bud_total_{ver}",
                          help=t("Un tetto per tutte le spese del mese insieme, anche quelle delle categorie "
                                 "senza budget. Lascia 0 per non usarlo."))
    c1, c2, c3 = st.columns([1, 1.6, 1.4])
    if c1.button(t("Salva i budget"), type="primary", icon=":material/check:", key="bud_save", width="stretch"):
        budgets.save({r["category"]: r["budget"] for _, r in ed.iterrows()}, tot)
        st.session_state.pop(PREFILL, None)
        st.session_state[VER] = ver + 1
        st.toast(t("Budget salvati"), icon=":material/check_circle:")
        st.rerun()
    if c2.button(t("Usa la media degli ultimi 3 mesi"), icon=":material/auto_fix_high:", key="bud_avg",
                 width="stretch", disabled=not avg,
                 help=t("Riempie la tabella con quanto hai speso in media; poi correggi e salva.")):
        st.session_state[PREFILL] = dict(avg)
        st.session_state[VER] = ver + 1
        st.rerun()
    if c3.button(t("Togli tutti"), icon=":material/delete_sweep:", key="bud_clear", width="stretch",
                 disabled=not cur and not tot_cur):
        budgets.save({}, None)
        st.session_state.pop(PREFILL, None)
        st.session_state[VER] = ver + 1
        st.rerun()


def render():
    style.header(t("Budget"), t("Quanto vuoi spendere ogni mese, categoria per categoria"))
    base = db.base_currency()
    fr = report.frame()
    today = date.today()
    cur_p = pd.Period(today, freq="M")
    first = fr["mese"].min() if not fr.empty else cur_p
    months = [cur_p - i for i in range(0, 24) if cur_p - i >= min(first, cur_p)]
    has = bool(budgets.get()) or bool(budgets.total())

    if has:
        with style.card("bud_status"):
            keys = [str(m) for m in months]
            p = pd.Period(st.selectbox(t("Mese"), keys, format_func=lambda k: _month_label(pd.Period(k, freq="M")),
                                       key="bud_month"), freq="M")
            current = p == cur_p
            rows = budgets.status(fr, p.year, p.month, today)
            cat_rows = [r for r in rows if r["category"]]
            b_sum = sum(r["budget"] for r in cat_rows)
            s_sum = sum(r["spent"] for r in cat_rows)
            over = sum(1 for r in rows if r["pct"] >= 100)
            items = [(t("Budget delle categorie"), ui.money(b_sum, base), t("{n} categorie", n=len(cat_rows))),
                     (t("Speso"), ui.money(s_sum, base), t("{p:.0f}% del budget", p=s_sum / b_sum * 100) if b_sum else None),
                     (t("Rimasto"), ui.money(b_sum - s_sum, base),
                      (t("{n} giorni alla fine del mese", n=rows[0]["days_left"]) if rows[0]["days_left"] > 1
                       else t("oggi è l'ultimo giorno del mese")) if current and rows else None,
                      "pos" if b_sum - s_sum >= 0 else "neg"),
                     (t("Budget superati"), f"{over}", t("nel mese") if over else t("nessuno, ottimo"),
                      "neg" if over else "pos")]
            style.kpis(items, cols=4)
            st.subheader(_month_label(p))
            _bars(sorted(rows, key=lambda r: (r["category"] is None, -r["pct"])), base, current)
            st.caption(t("Contano tutti i conti, in {ccy}. I rimborsi sulla stessa categoria riducono la spesa. "
                         "All'80% e quando un budget viene superato compare un avviso.", ccy=base))
    else:
        st.info(t("Non hai ancora nessun budget. Scegli quanto vuoi spendere al mese per le categorie che ti "
                  "interessano: puoi partire dalla tua media degli ultimi 3 mesi."), icon=":material/savings:")

    with style.card("bud_edit"):
        st.subheader(t("Imposta i budget"))
        _editor(fr, base)
