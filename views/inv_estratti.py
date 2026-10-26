"""Investimenti ricavati dagli estratti: dividendi, ritenute, bollo, capital gain; import del portafoglio titoli."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n, inv_income, positions, securities
from core.i18n import t
from views import style, ui


def _income() -> pd.DataFrame:
    return inv_income.extract(db.transactions_df())


def net_summary(base: str, pf: pd.DataFrame, realized: float) -> None:
    """Rendimento netto complessivo: plus/minus + dividendi netti − bollo − imposte sul capital gain."""
    inc = _income()
    if inc.empty and pf.empty:
        return
    div_net = float(inc.loc[inc["tipo"].isin(["dividendo", "ritenuta"]), "importo"].sum()) if not inc.empty else 0.0
    bollo = float(inc.loc[inc["tipo"] == "bollo", "importo"].sum()) if not inc.empty else 0.0
    cgt = float(inc.loc[inc["tipo"] == "capital gain", "importo"].sum()) if not inc.empty else 0.0
    pcol = f"P/L {base}"
    latent = float(pf[pcol].sum()) if not pf.empty and pcol in pf and pf[pcol].notna().any() else 0.0
    total = latent + realized + div_net + bollo + cgt
    since = t("dal {d}", d=f"{inc['date'].min():%m/%Y}") if not inc.empty else ""
    style.kpis(cols=4, items=[
        (t("Dividendi netti incassati"), ui.money(div_net, base), since, "pos" if div_net > 0 else ""),
        (t("Imposta di bollo"), ui.money(bollo, base), t("sul dossier titoli"), "neg" if bollo < 0 else ""),
        (t("Imposte sul capital gain"), ui.money(cgt, base), t("imposta sostitutiva"), "neg" if cgt < 0 else ""),
        (t("Rendimento netto complessivo"), ui.money(total, base), t("plus/minus + dividendi − tasse"),
         "pos" if total >= 0 else "neg"),
    ])


def income_tab(base: str) -> None:
    inc = _income()
    if inc.empty:
        st.info(t("Nei movimenti importati non ci sono ancora dividendi, ritenute, bollo o imposte sui titoli. "
                  "Compaiono da soli importando l'estratto del conto collegato al dossier titoli (es. Fineco)."))
        return
    st.caption(t("Ricavati in automatico dai movimenti del conto: dividendi («Div.su…»), ritenute («Rit.div.su…»), "
                 "imposta di bollo sul dossier e imposta sostitutiva sul capital gain."))
    sec = inv_income.per_security(inc)
    year_ago = pd.Timestamp.today() - pd.DateOffset(years=1)
    last12 = inc[inc["date"] >= year_ago]
    style.kpis(cols=4, items=[
        (t("Dividendi lordi"), ui.money(float(inc.loc[inc["tipo"] == "dividendo", "importo"].sum()), base),
         t("{n} stacchi", n=int((inc["tipo"] == "dividendo").sum()))),
        (t("Ritenute"), ui.money(float(inc.loc[inc["tipo"] == "ritenuta", "importo"].sum()), base), t("trattenute alla fonte")),
        (t("Netto ultimi 12 mesi"), ui.money(float(last12.loc[last12["tipo"].isin(["dividendo", "ritenuta"]), "importo"].sum()), base),
         t("dividendi meno ritenute")),
        (t("Costi ultimi 12 mesi"), ui.money(float(last12.loc[last12["tipo"].isin(["bollo", "capital gain"]), "importo"].sum()), base),
         t("bollo e capital gain")),
    ])

    years = inv_income.per_year(inc)
    if not years.empty:
        fig = go.Figure()
        for col, name, color in (("dividendo", t("Dividendi"), style.ENTRATA), ("ritenuta", t("Ritenute"), "#F5A524"),
                                 ("bollo", t("Bollo"), "#8B95A1"), ("capital gain", "Capital gain", style.SPESA)):
            fig.add_bar(x=years["Anno"].astype(str), y=years[col], name=name, marker_color=color,
                        hovertemplate="%{x}<br>%{y:,.2f} " + base + "<extra>" + name + "</extra>")
        fig.add_scatter(x=years["Anno"].astype(str), y=years["netto"], name=t("Netto"), mode="lines+markers",
                        line=dict(color=style.ACCENT, width=3),
                        hovertemplate="%{x}<br>%{y:,.2f} " + base + f"<extra>{t('Netto')}</extra>")
        fig.update_layout(barmode="relative")
        fig.update_xaxes(type="category")
        st.subheader(t("Anno per anno"))
        style.chart(fig, height=260)

    st.subheader(t("Per titolo"))
    inst = securities.instruments_df()
    show = sec.drop(columns=["chiave"]).copy()
    show["Nel portafoglio"] = [(t("sì") if inv_income.match_instrument(k, inst) else t("no")) for k in sec["chiave"]]
    show = show.rename(columns={c: t(c) for c in ("Titolo", "Lordo", "Ritenute", "Netto", "Stacchi", "Nel portafoglio")})
    show = show.rename(columns={"Quote": t("Quote (ultimo stacco)"), "Al": t("Data"),
                                "Ultimo anno": t("Netto ultimi 12 mesi")})
    style.table(show, {t("Lordo"): "num", t("Ritenute"): "num", t("Netto"): "num",
                       t("Quote (ultimo stacco)"): ("num", 3), t("Data"): "date", t("Netto ultimi 12 mesi"): "num",
                       t("Stacchi"): "int"})
    missing = [r for r in sec.itertuples() if not inv_income.match_instrument(r.chiave, inst)]
    if missing:
        st.markdown("**" + t("Titoli che possiedi ma non sono nel portafoglio dell'app") + "**")
        st.caption(t("Le quote sono quelle dell'ultimo dividendo. Cercali per nome, scegli quello giusto e indica il "
                     "prezzo medio di carico (lo trovi nell'app Fineco, sezione Portafoglio): così entrano nel "
                     "calcolo di valore e rendimento."))
        for r in missing:
            with st.expander(t("{name}: {q} quote al {d}", name=r.Titolo, q=ui.fmt_num(r.Quote, 3),
                               d=f"{r.Al:{i18n.strf()}}")):
                _register_form(r)


def _register_form(r) -> None:
    key = f"reg_{abs(hash(r.chiave))}"
    q = st.text_input(t("Cerca il titolo (nome, ISIN o ticker)"), value=r.Titolo, key=f"{key}_q")
    if st.button(t("Cerca"), key=f"{key}_s", icon=":material/search:"):
        try:
            st.session_state[f"{key}_res"] = securities.search_isin(q)
        except Exception as e:
            st.error(t("Ricerca non riuscita (serve internet): {err}", err=e))
    res = st.session_state.get(f"{key}_res") or []
    if not res:
        return
    opts = {f"{x.get('name', '')} — {x.get('symbol', '')} ({x.get('exchange_name') or x.get('exchange', '')})": x
            for x in res}
    choice = opts[st.selectbox(t("Risultato"), list(opts), key=f"{key}_c")]
    c1, c2, c3 = st.columns(3)
    isin = c1.text_input("ISIN", value=choice.get("isin", "") or "", key=f"{key}_isin",
                         help=t("Lo trovi nell'app della banca accanto al titolo"))
    qty = c2.number_input(t("Quote"), value=float(r.Quote or 0), min_value=0.0, step=1.0, key=f"{key}_qty")
    pmc = c3.number_input(t("Prezzo medio di carico"), min_value=0.0, step=0.01, format="%.4f", key=f"{key}_pmc")
    c1, c2 = st.columns(2)
    when = c1.date_input(t("Data"), value=date.today(), format=i18n.date_fmt(), key=f"{key}_d")
    ccy = c2.text_input(t("Valuta"), value="EUR", max_chars=3, key=f"{key}_ccy")
    ok = securities.is_valid_isin(isin) and qty > 0 and pmc > 0
    if st.button(t("Aggiungi al portafoglio"), key=f"{key}_add", type="primary", disabled=not ok):
        securities.save_instrument(isin, choice.get("symbol", ""), choice.get("name", r.Titolo),
                                   securities.guess_asset_type(choice.get("type", "")), ccy.upper(),
                                   "Registrato dai dividendi dell'estratto")
        securities.add_trade(isin, when, "acquisto", qty, pmc, 0, ccy.upper(), "", positions.NOTE)
        st.success(t("Aggiunto. Aggiorna le quotazioni per vederne il valore."))
        st.rerun()
    if not securities.is_valid_isin(isin):
        st.caption(t("Serve un ISIN valido (12 caratteri, es. IE00B5BMR087)."))


def positions_import() -> None:
    st.markdown("**" + t("Importa il portafoglio da un file") + "**")
    st.caption(t("Esporta il portafoglio titoli dalla tua banca (es. Fineco: sezione *Portafoglio* → *Esporta*) in "
                 "Excel o CSV: servono almeno le colonne **ISIN** e **Quantità**, meglio anche il **prezzo medio di "
                 "carico**. L'app registra i titoli nuovi e allinea le quantità. Puoi anche metterlo nella cartella "
                 "degli estratti: viene importato da solo."))
    f = st.file_uploader(t("File del portafoglio"), type=["xlsx", "xls", "csv"], key="pos_file")
    if not f:
        return
    try:
        pos = positions.parse(f.getvalue(), f.name)
    except Exception as e:
        st.error(t("Lettura non riuscita: {err}", err=e))
        return
    if pos.empty:
        st.warning(t("Nessuna riga con un ISIN valido nel file."))
        return
    p = positions.plan(pos)
    label = {"nuovo": t("titolo nuovo"), "allinea": t("allinea la quantità"), "ok": t("già allineato")}
    view = p.assign(azione=p["azione"].map(label))
    view.columns = ["ISIN", t("Titolo"), t("Quantità nel file"), t("Nell'app"), t("Differenza"), t("Prezzo medio"),
                    t("Valuta"), t("Cosa faccio")]
    style.table(view, {t("Quantità nel file"): ("num", 4), t("Nell'app"): ("num", 4), t("Differenza"): ("num", 4),
                       t("Prezzo medio"): ("num", 4)})
    cols = pos.attrs.get("columns", {})
    if not cols.get("pmc"):
        st.warning(t("Nel file non c'è il prezzo medio di carico: registro i titoli ma non le quantità "
                     "(aggiungile da «Operazioni»)."))
    todo = int((p["azione"] != "ok").sum())
    when = st.date_input(t("Data delle operazioni di allineamento"), value=date.today(), format=i18n.date_fmt(),
                         key="pos_d")
    if st.button(t("Applica ({n} titoli da aggiornare)", n=todo), type="primary", disabled=todo == 0, key="pos_apply"):
        with st.spinner(t("Registro i titoli e cerco i ticker…")):
            c = positions.apply(pos, on=when)
        st.success(t("Fatto: {n} titoli nuovi, {m} quantità allineate", n=c["nuovo"], m=c["allinea"])
                   + (t(", {n} senza prezzo medio.", n=c["senza prezzo"]) if c["senza prezzo"] else "."))
