from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import crypto_ex, db, i18n, securities
from core.i18n import t
from views import avvisi, focus, nav, previsione, style, ui
from views import mese as dettaglio_mese

def _cat_colors() -> dict[str, str]:
    c = db.categories_df()
    return dict(zip(c["name"], c["color"]))


def render():
    base = db.base_currency()
    disp = ui.display_ccy()
    today = date.today()
    style.header(t("Panoramica"), ui.view_summary())
    df = ui.prepared_transactions()

    if df.empty:
        st.info(t("Non ci sono ancora movimenti. Importa gli estratti di Fineco e Revolut (menu dell'avatar in alto "
                  "a destra, «Importa estratti»), oppure aggiungi una spesa da «Movimenti»."))
        if "importa" in nav.PAGES:
            st.page_link(nav.PAGES["importa"], label=t("Importa estratti"), icon=":material/upload_file:")
        _patrimonio(base)
        return

    cur_start = today.replace(day=1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    # mese scorso confrontato fino allo stesso giorno, per un paragone equo
    prev_same = prev_start + timedelta(days=min(today.day, prev_end.day) - 1)
    cur = ui.filter_period(df, cur_start, today)
    prev = ui.filter_period(df, prev_start, prev_same)
    spese_m, entrate_m = cur["spesa"].sum(), cur["entrata"].sum()
    spese_p, entrate_p = prev["spesa"].sum(), prev["entrata"].sum()
    mese, mese_prev = i18n.month(today.month), i18n.month(prev_start.month)
    saldo = entrate_m - spese_m

    def vs(cur_v, prev_v):
        if not prev_v:
            return None, ""
        diff = (cur_v - prev_v) / prev_v * 100
        return min(cur_v / prev_v * 100, 100), t("{diff}% vs {mese}", diff=f"{diff:+.0f}", mese=mese_prev)

    p_sp, l_sp = vs(spese_m, spese_p)
    p_en, l_en = vs(entrate_m, entrate_p)
    next_month = (cur_start + timedelta(days=32)).replace(day=1)
    giorni_mese = (next_month - timedelta(days=1)).day
    sel = style.gradient_cards(key="dash_cards", items=[
        dict(id="spese", label=t("Spese"), sub=t("{mese}, primi {n} giorni", mese=mese.capitalize(), n=today.day),
             value=ui.money(spese_m),
             variant="spese", pct=p_sp, pct_label=l_sp),
        dict(id="entrate", label=t("Entrate"), sub=f"{mese.capitalize()}", value=ui.money(entrate_m), variant="entrate",
             pct=p_en, pct_label=l_en),
        dict(id="saldo", label=t("Saldo del mese"),
             sub=t("Entrate meno spese") if saldo >= 0 else t("Le spese superano le entrate"),
             value=ui.money(saldo), variant="saldo",
             pct=(saldo / entrate_m * 100 if entrate_m > 0 and saldo >= 0 else None),
             pct_label=(t("{p}% delle entrate", p=f"{saldo / entrate_m * 100:.0f}") if entrate_m > 0 and saldo >= 0
                        else "")),
        dict(id="media", label=t("Media al giorno"),
             sub=t("A fine mese circa {v}", v=ui.money(spese_m / max(today.day, 1) * giorni_mese)),
             value=ui.money(spese_m / max(today.day, 1)), variant="media",
             pct=today.day / giorni_mese * 100, pct_label=t("giorno {d} di {n}", d=today.day, n=giorni_mese)),
    ])
    if sel:
        dettaglio_mese.open_detail(sel, cur_start, today)

    left, right = st.columns([3, 2], gap="medium")
    with left, style.card("andamento"):
        st.subheader(t("Andamento ultimi 12 mesi"))
        last12 = ui.filter_period(df, *ui.preset_range("Ultimi 12 mesi"))
        m = last12.groupby("mese")[["spesa", "entrata"]].sum().reset_index()
        if not m.empty:
            # etichette brevi (solo il mese); l'anno compare a gennaio e nel tooltip
            m["Mese"] = [i18n.month(p.month, short=True) + (f" {str(p.year)[2:]}" if p.month == 1 or i == 0 else "")
                         for i, p in enumerate(m["mese"])]
            fig = go.Figure()
            fig.add_bar(x=m["Mese"], y=m["entrata"], name=t("Entrate"), marker_color=style.ENTRATA,
                        hovertemplate="%{y:,.0f} " + disp + f"<extra>{t('Entrate')}</extra>")
            fig.add_bar(x=m["Mese"], y=m["spesa"], name=t("Spese"), marker_color=style.SPESA,
                        hovertemplate="%{y:,.0f} " + disp + f"<extra>{t('Spese')}</extra>")
            fig.update_layout(barmode="group", bargroupgap=0.12)
            style.chart(fig, height=330)
    with right, style.card("categorie"):
        st.subheader(t("Categorie di {mese}", mese=mese))
        cats = cur[cur["spesa"] != 0].groupby("cat_label")["spesa"].sum().sort_values(ascending=False)
        if (cats > 0).any():
            colors = ui.color_map()
            sel = style.donut([(n, float(v), colors.get(n, "#A3A0B5")) for n, v in cats.items()],
                              t("Totale spese"), ui.money(spese_m), lambda v: ui.money(v), key="dash_cat")
            st.caption(t("Clicca su una categoria per il dettaglio."))
            if sel:
                focus.open_category(sel, cur_start, today)
        else:
            st.caption(t("Nessuna spesa questo mese."))

    previsione.card()

    left, right = st.columns([2, 1], gap="medium")
    with left, style.card("movimenti"):
        st.subheader(t("Ultimi movimenti"))
        st.caption(t("Clicca su un movimento per il dettaglio."))
        sel = style.tx_list(df.head(8), lambda v, c: ui.money(v, c), _cat_colors(), base, key="dash_tx")
        if sel is not None:
            focus.open_focus(sel)
        ui.missing_fx_warning(df)
    with right:
        if "avvisi" in nav.PAGES:
            avvisi.dashboard_card(nav.PAGES["avvisi"])
        with style.card("conti"):
            st.subheader(t("Per conto a {mese}", mese=mese))
            by_acc = cur.groupby("account")[["spesa", "entrata"]].sum()
            if by_acc.empty:
                st.caption(t("Nessun movimento questo mese."))
            else:
                style.kpis([(acc, ui.money(r.spesa), t("spese del mese, entrate {v}", v=ui.money(r.entrata)))
                            for acc, r in by_acc.sort_values("spesa", ascending=False).iterrows()], cols=1)
        _patrimonio(base)


def _patrimonio(base: str) -> None:
    pf, _ = securities.portfolio(base)
    crypto = crypto_ex.balances_df()
    if pf.empty and crypto.empty:
        return
    with style.card("patrimonio"):
        st.subheader(t("Patrimonio investito"))
        items = []
        if not pf.empty:
            items.append((t("Titoli"), ui.money(pf[f"Valore {base}"].sum(), base)))
            if pd.notna(pf[f"P/L {base}"]).any():
                pl = pf[f"P/L {base}"].sum()
                items.append((t("Plus/minus titoli"), ui.money(pl, base), None, "pos" if pl >= 0 else "neg"))
        if not crypto.empty:
            items.append((t("Exchange crypto"), ui.money(crypto["value_base"].sum(), base)))
        style.kpis(items, cols=1)
