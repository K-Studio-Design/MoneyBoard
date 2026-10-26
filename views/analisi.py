from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n
from core.i18n import t
from views import cerca, focus, periodo, style, ui


def render():
    style.header(t("Analisi"), ui.view_summary())
    base = ui.display_ccy()  # valuta in cui sono espressi gli importi (base o valuta filtrata)
    df = ui.prepared_transactions()
    df_all_ccy = ui.prepared_transactions(ignore_currency=True)
    if df.empty:
        st.info(t("Nessun dato da analizzare: aggiungi o importa dei movimenti."))
        return

    first = df["date"].min().date()
    start, end = ui.period_picker("an", default="Ultimi 6 mesi", first_date=first)
    cat_excl = st.multiselect(t("Escludi categorie"), db.category_names(), key="an_excl", placeholder=t("Nessuna"),
                              format_func=ui.cat)
    if cat_excl:
        df = df[~df["category"].isin(cat_excl)]
        df_all_ccy = df_all_ccy[~df_all_ccy["category"].isin(cat_excl)]
    cur = ui.filter_period(df, start, end)
    if cur.empty:
        st.warning(t("Nessun movimento nel periodo selezionato."))
        return

    # periodo precedente di pari durata, per il confronto
    length = (end - start).days + 1
    p_end = start - timedelta(days=1)
    p_start = p_end - timedelta(days=length - 1)
    prev = ui.filter_period(df, p_start, p_end)

    spese, entrate = cur["spesa"].sum(), cur["entrata"].sum()
    spese_prev = prev["spesa"].sum()
    n_mesi = ui.months_in(start, end)
    n_spese = int((cur["spesa"] > 0).sum())
    saldo = entrate - spese

    diff = (spese - spese_prev) / spese_prev * 100 if spese_prev else None
    pick = style.kpis(key=f"an_kpis_{start}_{end}", ids=list(periodo.KINDS), items=[
        (t("Spese"), ui.money(spese), t("{p}% sul periodo precedente", p=f"{diff:+.0f}") if diff is not None else None),
        (t("Entrate"), ui.money(entrate)),
        (t("Risparmio"), ui.money(saldo), t("{p}% delle entrate", p=f"{saldo / entrate * 100:.0f}") if entrate > 0 else None,
         "pos" if saldo >= 0 else "neg"),
        (t("Media al mese"), ui.money(spese / n_mesi)),
        (t("Media al giorno"), ui.money(spese / length)),
        (t("Media per spesa"), ui.money(spese / n_spese if n_spese else 0), t("{n} movimenti di spesa", n=n_spese)),
    ])
    if pick:
        periodo.open_detail(pick, start, end, tuple(cat_excl or ()))
    ui.missing_fx_warning(cur)

    with style.card("analisi"):
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
            [t("Per mese"), t("Per categoria"), t("Andamento"), t("Dove spendi"), t("Mesi × categorie"), t("Per valuta")],
            default=cerca.tab_default("analisi"))
        cmap = ui.color_map()

        with tab1:
            m = cur.groupby("mese")[["spesa", "entrata"]].sum()
            m["risparmio"] = m["entrata"] - m["spesa"]
            m = m.reset_index()
            m["Mese"] = m["mese"].map(ui.month_short)
            fig = go.Figure()
            fig.add_bar(x=m["Mese"], y=m["spesa"], name=t("Spese"), marker_color=style.SPESA)
            fig.add_bar(x=m["Mese"], y=m["entrata"], name=t("Entrate"), marker_color=style.ENTRATA)
            fig.add_scatter(x=m["Mese"], y=m["risparmio"], name=t("Risparmio"), mode="lines+markers",
                            line=dict(color="#5B6B7A", width=3))
            avg = m["spesa"].mean()
            fig.add_hline(y=avg, line_dash="dot", line_color="#8B95A1",
                          annotation_text=t("media spese {v}", v=ui.money(avg)), annotation_position="top right")
            fig.update_layout(barmode="group", height=420, margin=dict(l=0, r=0, t=30, b=0), yaxis_title=base)
            style.chart(fig)

            st.markdown("**" + t("Spese mensili per categoria") + "**")
            mc = cur[cur["spesa"] != 0].groupby(["mese", "cat_label"])["spesa"].sum().reset_index()
            mc["Mese"] = mc["mese"].map(ui.month_short)
            fig = px.bar(mc, x="Mese", y="spesa", color="cat_label", color_discrete_map=cmap,
                         labels={"spesa": base, "cat_label": t("Categoria"), "Mese": t("Mese")})
            fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None)
            style.chart(fig)

            tbl = m[["Mese", "spesa", "entrata", "risparmio"]].copy()
            money_cols = [t("Spese"), t("Entrate"), t("Risparmio")]
            tbl.columns = [t("Mese")] + money_cols
            style.table(tbl, {c: "num" for c in money_cols}, neg=(t("Risparmio"),))

        with tab2:
            c = cur.groupby("cat_label")["spesa"].agg(["sum", "count"]).reset_index()
            c = c[c["sum"] > 0].sort_values("sum", ascending=False)
            col_m, col_mov, col_prev = t("Media mensile"), t("Media per movimento"), t("Periodo prec.")
            c["%"] = c["sum"] / c["sum"].sum() * 100
            c[col_m] = c["sum"] / n_mesi
            c[col_mov] = c["sum"] / c["count"]
            prev_c = prev.groupby("cat_label")["spesa"].sum()
            c[col_prev] = c["cat_label"].map(prev_c).fillna(0)
            st.caption(t("Clicca su una categoria per il dettaglio."))
            sel = style.category_bars([(r.cat_label, float(r.sum), cmap.get(r.cat_label, "#9AA3AE"))
                                       for r in c.itertuples()], lambda v: ui.money(v), limit=12, key="an_cat")
            if sel:
                focus.open_category(sel, start, end)
            st.write("")
            show = c.rename(columns={"cat_label": t("Categoria"), "sum": t("Totale"), "count": t("N.")})
            style.table(show, {t("Totale"): "num", t("N."): "int", "%": "bar", col_m: "num", col_mov: "num",
                               col_prev: "num"})
            ent = cur.groupby("cat_label")["entrata"].sum()
            ent = ent[ent > 0].sort_values(ascending=False)
            if not ent.empty:
                st.markdown("**" + t("Entrate per categoria") + "**")
                fig = px.bar(ent.reset_index(), x="cat_label", y="entrata", color="cat_label", color_discrete_map=cmap,
                             labels={"entrata": base, "cat_label": ""})
                fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
                style.chart(fig)

        with tab3:
            days = pd.date_range(start, end, freq="D")
            daily = cur.groupby(cur["date"].dt.normalize())["spesa"].sum().reindex(days, fill_value=0)
            dd = pd.DataFrame({"Data": days, "Spesa": daily.values})
            dd["Cumulata"] = dd["Spesa"].cumsum()
            dd["Media mobile 7gg"] = dd["Spesa"].rolling(7, min_periods=1).mean()
            fig = go.Figure()
            fig.add_bar(x=dd["Data"], y=dd["Spesa"], name=t("Spesa giornaliera"), marker_color="rgba(209,77,114,0.35)")
            fig.add_scatter(x=dd["Data"], y=dd["Media mobile 7gg"], name=t("Media mobile 7 giorni"),
                            line=dict(color=style.SPESA, width=2))
            fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=base)
            style.chart(fig)
            fig = px.area(dd, x="Data", y="Cumulata", labels={"Cumulata": t("Spesa cumulata ({base})", base=base),
                                                             "Data": t("Data")})
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
            style.chart(fig)
            st.markdown("**" + t("Spesa media per giorno della settimana") + "**")
            n_wd = pd.Series(days.weekday).value_counts().reindex(range(7), fill_value=0)
            wd = cur.groupby("giorno_sett")["spesa"].sum().reindex(range(7), fill_value=0) / n_wd.replace(0, 1)
            fig = px.bar(x=[i18n.weekday(i, short=True) for i in range(7)], y=wd.values, labels={"x": "", "y": base})
            fig.update_traces(marker_color="#5B6B7A")
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
            style.chart(fig)

        with tab4:
            s = cur[cur["spesa"] > 0].copy()
            s["Esercente"] = s["description"].str.replace(r"\s+", " ", regex=True).str.strip().str[:60]
            top = s.groupby("Esercente").agg(Totale=("spesa", "sum"), Volte=("spesa", "count"),
                                             Categoria=("cat_label", "first")).sort_values("Totale", ascending=False)
            top = top.head(15).reset_index().rename(columns={"Esercente": t("Esercente"), "Totale": t("Totale"),
                                                             "Volte": t("Volte"), "Categoria": t("Categoria")})
            st.markdown("**" + t("Top 15 per importo") + "**")
            style.table(top, {t("Totale"): "num", t("Volte"): "int"})
            st.markdown("**" + t("Spese più grandi del periodo") + "**")
            big = s.nlargest(10, "spesa")[["date", "description", "spesa", "cat_label", "account"]]
            big.columns = [t("Data"), t("Descrizione"), base, t("Categoria"), t("Conto")]
            style.table(big, {t("Data"): "date", base: "num"})

        with tab5:
            piv = cur[cur["spesa"] != 0].pivot_table(index="cat_label", columns="mese", values="spesa",
                                                     aggfunc="sum", fill_value=0)
            if piv.empty:
                st.caption(t("Nessuna spesa nel periodo."))
            else:
                tot_col, avg_col = t("Totale"), t("Media")
                piv.columns = [ui.month_label(c) for c in piv.columns]
                piv[tot_col] = piv.sum(axis=1)
                piv[avg_col] = piv.drop(columns=tot_col).mean(axis=1)
                piv = piv.sort_values(tot_col, ascending=False)
                piv.loc[t("TOTALE")] = piv.sum()
                piv.index.name = t("Categoria")
                style.table(piv, {c: "num" for c in piv.columns}, index=True, total_last=True)
                sep, dec = (",", ".") if i18n.is_en() else (";", ",")
                st.download_button(t("Scarica tabella (CSV)"), piv.to_csv(sep=sep, decimal=dec).encode("utf-8-sig"),
                                   file_name=t("spese_per_mese_{a}_{b}.csv", a=start, b=end), mime="text/csv",
                                   icon=":material/download:")

        with tab6:
            _per_valuta(ui.filter_period(df_all_ccy, start, end))


def _per_valuta(d):
    """Spese ed entrate divise per valuta: importi originali e controvalore nella valuta base."""
    base = db.base_currency()
    if d.empty:
        st.caption(t("Nessun movimento nel periodo."))
        return
    st.caption(t("Ogni valuta con i suoi importi originali (non convertiti) e, a fianco, il controvalore in "
                 "{base}. Per vedere grafici e movimenti di una sola valuta scegli «Valuta» nella barra laterale.",
                 base=base))
    tab = d.groupby("currency").agg(
        mov=("id", "count"), spese_base=("spesa_base", "sum"), entrate_base=("entrata_base", "sum")).reset_index()
    # totali nella valuta originale di ogni movimento
    orig = d.assign(sp=(-d["amount"]).where(d["kind"] == "uscita", 0.0),
                    en=d["amount"].where(d["kind"] == "entrata", 0.0)).groupby("currency")[["sp", "en"]].sum()
    tab["spese"] = tab["currency"].map(orig["sp"])
    tab["entrate"] = tab["currency"].map(orig["en"])
    tab = tab[["currency", "mov", "spese", "entrate", "spese_base", "entrate_base"]].sort_values("spese_base", ascending=False)
    show = tab.rename(columns={"currency": t("Valuta"), "mov": t("Movimenti"), "spese": t("Spese (valuta originale)"),
                             "entrate": t("Entrate (valuta originale)"), "spese_base": t("Spese in {ccy}", ccy=base),
                             "entrate_base": t("Entrate in {ccy}", ccy=base)})
    style.table(show, {c: ("int" if c == t("Movimenti") else "num") for c in show.columns if c != t("Valuta")})
    c1, c2 = st.columns(2)
    with c1:
        sp = tab[tab["spese_base"] > 0]
        if not sp.empty:
            fig = px.pie(sp, names="currency", values="spese_base", hole=0.5,
                         title=t("Peso delle spese per valuta (in {base})", base=base))
            fig.update_layout(height=340, margin=dict(l=0, r=0, t=40, b=0))
            style.chart(fig)
    with c2:
        cats = (d[d["spesa_base"] != 0].groupby(["currency", "cat_label"])["spesa_base"].sum().reset_index())
        cats = cats[cats["spesa_base"] > 0]
        if not cats.empty:
            fig = px.bar(cats, x="currency", y="spesa_base", color="cat_label", color_discrete_map=ui.color_map(),
                         labels={"spesa_base": base, "currency": "", "cat_label": t("Categoria")},
                         title=t("Categorie di spesa per valuta (in {base})", base=base))
            fig.update_layout(height=340, margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
            style.chart(fig)
    for ccy, g in d.groupby("currency"):
        if ccy == base:
            continue
        sp = g[g["spesa"] != 0]
        if sp.empty:
            continue
        with st.expander(t("Dettaglio spese in {ccy} per categoria (importi originali)", ccy=ccy)):
            c_sp, c_base = t("Spese in {ccy}", ccy=ccy), t("In {base}", base=base)
            tab = sp.assign(orig=-sp["amount"]).groupby("cat_label").agg(
                **{c_sp: ("orig", "sum"), c_base: ("spesa_base", "sum"),
                   t("Movimenti"): ("id", "count")}).sort_values(c_sp, ascending=False).reset_index()
            tab = tab.rename(columns={"cat_label": t("Categoria")})
            style.table(tab, {c_sp: "num", c_base: "num", t("Movimenti"): "int"})
