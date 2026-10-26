from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from core import crypto_ex, db, i18n, securities
from core.i18n import t
from views import cerca, inv_estratti, style, ui


def pf_columns(base: str) -> dict:
    """Nomi delle colonne della tabella del portafoglio nella lingua attuale."""
    return {"Nome": t("Nome"), "Tipo": t("Tipo"), "Quantità": t("Quantità"), "PMC": t("Prezzo medio"),
            "Valuta": t("Valuta"), "Ultimo prezzo": t("Ultimo prezzo"), "Valore": t("Valore"),
            f"Valore {base}": t("Valore {ccy}", ccy=base), f"Costo {base}": t("Costo {ccy}", ccy=base),
            "Aggiornato": t("Aggiornato")}


def _portfolio_tab(base: str):
    pf, realized = securities.portfolio(base)
    if pf.empty:
        st.info(t("Nessuna posizione aperta. Importa il portafoglio da un file (scheda «Aggiungi titolo»), registra "
                  "i titoli trovati nei dividendi (scheda «Dagli estratti») oppure aggiungi un titolo per ISIN."))
        inv_estratti.net_summary(base, pf, realized)
        return
    vcol, ccol, pcol = f"Valore {base}", f"Costo {base}", f"P/L {base}"
    # i totali di valore e plus/minus contano solo i titoli con una quotazione (gli altri non hanno un valore)
    priced = pf[pf[vcol].notna() & pf[ccol].notna()]
    tot_v = priced[vcol].sum(min_count=1)
    tot_c = pf[ccol].sum(min_count=1)
    c_priced = priced[ccol].sum(min_count=1)
    pl = (tot_v - c_priced) if pd.notna(tot_v) and pd.notna(c_priced) else None
    n_missing = len(pf) - len(priced)
    k = st.columns(4)
    k[0].metric(t("Valore di mercato"), ui.money(tot_v),
                help=t("{n} titoli senza quotazione non sono inclusi", n=n_missing) if n_missing else None)
    k[1].metric(t("Capitale investito"), ui.money(tot_c))
    k[2].metric(t("Plus/minus latente"), ui.money(pl), f"{pl / c_priced * 100:+.2f}%" if pl is not None and c_priced else None,
                help=t("Solo sui titoli con una quotazione") if n_missing else None)
    k[3].metric(t("Plus/minus realizzate"), ui.money(realized))
    inv_estratti.net_summary(base, pf, realized)
    if pf["Ultimo prezzo"].isna().any():
        st.warning(t("Alcuni titoli non hanno ancora una quotazione: premi «🔄 Aggiorna quotazioni» nella barra laterale."))
    for err in dict.fromkeys(st.session_state.get("price_errors", [])):
        st.caption(f"⚠️ {err}")

    cols = pf_columns(base)
    show = pf.assign(Tipo=pf["Tipo"].map(lambda x: t(x) if x else x)).rename(columns=cols)
    style.table(show, {cols["Quantità"]: ("num", 4), cols["PMC"]: ("num", 4), cols["Ultimo prezzo"]: ("num", 4),
                       cols["Valore"]: "num", cols[vcol]: "num", cols[ccol]: "num", pcol: "num", "P/L %": ("pct", 2)},
                neg=(pcol, "P/L %"))
    c1, c2 = st.columns(2)
    valued = pf.dropna(subset=[vcol]).copy()
    valued["Tipo"] = valued["Tipo"].map(lambda x: t(x) if x else x)
    if not valued.empty:
        with c1:
            fig = px.pie(valued, names="Nome", values=vcol, hole=0.5, title=t("Allocazione per titolo"))
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0))
            style.chart(fig)
        with c2:
            fig = px.pie(valued.groupby("Tipo")[vcol].sum().reset_index(), names="Tipo", values=vcol, hole=0.5,
                         title=t("Allocazione per tipo"))
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0))
            style.chart(fig)

    st.subheader(t("Andamento prezzo"))
    opts = {f"{r.Nome} ({r.Ticker})": r.Ticker for r in pf.itertuples() if r.Ticker}
    if opts:
        c1, c2 = st.columns([3, 1])
        sel = c1.selectbox(t("Titolo"), list(opts))
        periods = {"1mo": "1 mese", "3mo": "3 mesi", "6mo": "6 mesi", "1y": "1 anno", "2y": "2 anni", "5y": "5 anni",
                   "max": "Tutto"}
        period = c2.selectbox(t("Periodo"), list(periods), index=3, format_func=lambda p: t(periods[p]))
        try:
            h = _history(opts[sel], period)
            if h.empty:
                st.caption(t("Storico non disponibile."))
            else:
                fig = px.line(h, x="Data", y="Prezzo", labels={"Data": t("Data"), "Prezzo": t("Prezzo")})
                pmc = float(pf.loc[pf["Ticker"] == opts[sel], "PMC"].iloc[0])
                fig.add_hline(y=pmc, line_dash="dot", annotation_text=t("tuo prezzo medio {v}", v=ui.fmt_num(pmc, 4)))
                fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0))
                style.chart(fig)
        except Exception as e:
            st.caption(t("Storico non disponibile: {err}", err=e))


@st.cache_data(ttl=3600, show_spinner=False)
def _history(ticker: str, period: str) -> pd.DataFrame:
    return securities.price_history(ticker, period)


def _add_instrument_tab():
    st.markdown(t("Inserisci l'**ISIN**: l'app cerca il ticker su Yahoo Finance e ti propone le borse dove è quotato "
                  "(preferibilmente Borsa Italiana / Xetra). Se non lo trova puoi scrivere il ticker a mano "
                  "(es. `SWDA.MI`, `VWCE.DE`, `ENI.MI`, `AAPL`)."))
    c1, c2 = st.columns([3, 1])
    isin = c1.text_input("ISIN", placeholder=t("es. IE00B4L5Y983"), key="new_isin").strip().upper()
    if c2.button(t("Cerca"), icon=":material/search:", key="isin_search") and isin:
        if not securities.is_valid_isin(isin):
            st.warning(t("Il codice di controllo dell'ISIN non torna: verifica di averlo scritto bene."))
        try:
            st.session_state["isin_results"] = (isin, securities.search_isin(isin))
        except Exception as e:
            st.session_state["isin_results"] = (isin, [])
            st.error(t("Ricerca non riuscita: {err}", err=e))
    results = st.session_state.get("isin_results")
    choice = None
    if results and results[0] == isin:
        found = results[1]
        if found:
            labels = [f"{r['symbol']} — {r['name']} · {r['exchange_name']} ({r['type']})" for r in found]
            idx = st.radio(t("Quotazioni trovate"), range(len(found)), format_func=lambda i: labels[i])
            choice = found[idx]
        else:
            st.info(t("Nessun risultato: inserisci il ticker Yahoo manualmente."))
    with st.form("save_instr"):
        c1, c2, c3 = st.columns(3)
        ticker = c1.text_input(t("Ticker Yahoo"), value=choice["symbol"] if choice else "")
        name = c2.text_input(t("Nome"), value=choice["name"] if choice else "")
        types = securities.ASSET_TYPES
        guessed = securities.guess_asset_type(choice["type"]) if choice else "ETF"
        a_type = c3.selectbox(t("Tipo"), types, index=types.index(guessed), format_func=t)
        notes = st.text_input(t("Note"))
        if st.form_submit_button(t("Salva titolo"), type="primary"):
            if not isin:
                st.error(t("Inserisci l'ISIN."))
            elif not ticker:
                st.error(t("Serve un ticker per scaricare le quotazioni."))
            else:
                try:
                    price, ccy = securities.fetch_quote(ticker.strip())
                    securities.save_instrument(isin, ticker.strip(), name.strip() or ticker, a_type, ccy, notes)
                    with db.connect() as con:
                        con.execute("UPDATE instruments SET last_price=?, last_update=? WHERE isin=?",
                                    (price, db.now_str(), isin))
                    st.success(t("Salvato {name}: ultimo prezzo {p} {ccy}", name=name or ticker, p=ui.fmt_num(price, 4),
                                 ccy=ccy))
                except Exception as e:
                    securities.save_instrument(isin, ticker.strip(), name.strip() or ticker, a_type, None, notes)
                    st.warning(t("Titolo salvato, ma quotazione non disponibile ora ({err}). Riprova con «Aggiorna quotazioni».",
                                 err=e))

    inst = securities.instruments_df()
    if not inst.empty:
        st.subheader(t("Titoli registrati"))
        reg = inst[["isin", "ticker", "name", "asset_type", "quote_currency", "last_price", "last_update"]].copy()
        reg["asset_type"] = reg["asset_type"].map(lambda x: t(x) if x else x)
        style.table(reg.rename(columns={"isin": "ISIN", "ticker": "Ticker", "name": t("Nome"), "asset_type": t("Tipo"),
                                        "quote_currency": t("Valuta"), "last_price": t("Ultimo prezzo"),
                                        "last_update": t("Aggiornato")}), {t("Ultimo prezzo"): ("num", 4),
                                                                          t("Aggiornato"): "text"})
        c1, c2 = st.columns([3, 1])
        rm = c1.selectbox(t("Elimina titolo (cancella anche le sue operazioni)"), ["—"] + inst["isin"].tolist())
        if c2.button(t("Elimina"), disabled=rm == "—"):
            securities.delete_instrument(rm)
            st.rerun()


def _trades_tab(base: str):
    inst = securities.instruments_df()
    if inst.empty:
        st.info(t("Prima aggiungi un titolo nella scheda «Aggiungi titolo»."))
        return
    labels = {f"{r.name} · {r.isin}": r for r in inst.itertuples()}
    with st.form("add_trade", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        sel = c1.selectbox(t("Titolo"), list(labels))
        side = c2.selectbox(t("Operazione"), ["acquisto", "vendita"], format_func=t)
        d = c3.date_input(t("Data"), value=date.today(), format=i18n.date_fmt())
        c4, c5, c6, c7 = st.columns(4)
        qty = c4.number_input(t("Quantità"), min_value=0.0, step=1.0, format="%.6f")
        price = c5.number_input(t("Prezzo unitario"), min_value=0.0, step=0.01, format="%.4f")
        fees = c6.number_input(t("Commissioni"), min_value=0.0, step=0.5, format="%.2f")
        ccy = c7.text_input(t("Valuta"), value="", max_chars=3, placeholder="auto")
        account = st.text_input(t("Conto/broker"), value="Fineco")
        if st.form_submit_button(t("Registra operazione"), type="primary"):
            r = labels[sel]
            if qty <= 0 or price <= 0:
                st.error(t("Quantità e prezzo devono essere maggiori di zero."))
            else:
                currency = (ccy or r.quote_currency or base).upper()
                if side == "vendita":
                    pf, _ = securities.portfolio(base)
                    held = float(pf.loc[pf["ISIN"] == r.isin, "Quantità"].sum()) if not pf.empty else 0.0
                    if qty > held + 1e-9:
                        st.error(t("Stai vendendo {q} ma in portafoglio ne hai {h}.", q=ui.fmt_num(qty, 4),
                                   h=ui.fmt_num(held, 4)))
                        return
                securities.add_trade(r.isin, d, side, qty, price, fees, currency, account)
                st.success(t("Registrato {side} di {q} {name} a {p} {ccy}.", side=t(side), q=ui.fmt_num(qty, 4),
                             name=r.name, p=ui.fmt_num(price, 4), ccy=currency))
    tr = securities.trades_df()
    if not tr.empty:
        st.subheader(t("Storico operazioni"))
        show = tr[["id", "date", "name", "isin", "side", "quantity", "price", "fees", "currency", "account"]].copy()
        show["date"] = show["date"].dt.date
        show["side"] = show["side"].map(t)
        show.insert(0, "elimina", False)
        ed = st.data_editor(show, hide_index=True, width="stretch", disabled=[c for c in show.columns if c != "elimina"],
                            column_config={"id": None, "elimina": st.column_config.CheckboxColumn(t("Elimina")),
                                           "date": st.column_config.DateColumn(t("Data"), format=i18n.date_fmt()),
                                           "name": t("Nome"), "isin": "ISIN", "side": t("Operazione"),
                                           "quantity": t("Quantità"), "price": t("Prezzo"), "fees": t("Commissioni"),
                                           "currency": t("Valuta"), "account": t("Conto")})
        if st.button(t("Elimina operazioni selezionate")):
            ids = ed.loc[ed["elimina"], "id"].tolist()
            securities.delete_trades(ids)
            st.rerun()


def _crypto_tab(base: str):
    st.markdown(t("Collega un exchange con una **chiave API in sola lettura** (mai con permessi di prelievo o trading). "
                  "Le chiavi restano solo nel database locale sul tuo PC."))
    with st.expander(t("Aggiungi exchange")):
        try:
            exs = crypto_ex.available_exchanges()
        except Exception as e:
            st.error(t("Libreria ccxt non disponibile: {err}", err=e))
            return
        c1, c2 = st.columns(2)
        ex_id = c1.selectbox("Exchange", exs)
        label = c2.text_input(t("Nome"), value=ex_id.capitalize())
        c3, c4 = st.columns(2)
        key = c3.text_input("API key", type="password")
        secret = c4.text_input("API secret", type="password")
        pwd = ""
        try:
            if crypto_ex.needs_password(ex_id):
                pwd = st.text_input(t("Passphrase (richiesta da questo exchange)"), type="password")
        except Exception:
            pass
        if st.button(t("Salva exchange")):
            if not key or not secret:
                st.error(t("Servono API key e secret."))
            else:
                crypto_ex.add_exchange(ex_id, label, key, secret, pwd)
                st.success(t("Exchange salvato. Premi «Aggiorna saldi exchange»."))
    exs = crypto_ex.exchanges_df()
    if exs.empty:
        return
    if st.button(t("Aggiorna saldi exchange"), icon=":material/sync:", type="primary"):
        for r in exs.itertuples():
            try:
                with st.spinner(t("Leggo {name}…", name=r.label)):
                    crypto_ex.sync_exchange(r.id)
                st.success(t("{name}: saldi aggiornati", name=r.label))
            except Exception as e:
                st.error(f"{r.label}: {e}")
    bal = crypto_ex.balances_df()
    if not bal.empty:
        st.metric(t("Totale exchange in {ccy}", ccy=base), ui.money(bal["value_base"].sum()))
        c_q, c_v = t("Quantità"), t("Valore {ccy}", ccy=base)
        style.table(bal.rename(columns={"exchange": "Exchange", "asset": "Asset", "amount": c_q,
                                        "value_base": c_v, "updated": t("Aggiornato")}),
                    {c_q: ("num", 8), c_v: "num", t("Aggiornato"): "text"})
    c1, c2 = st.columns([3, 1])
    rm = c1.selectbox(t("Rimuovi exchange"), ["—"] + [f"{r.id} · {r.label}" for r in exs.itertuples()])
    if c2.button(t("Rimuovi"), disabled=rm == "—"):
        crypto_ex.delete_exchange(int(rm.split(" · ")[0]))
        st.rerun()


def render():
    style.header(t("Investimenti"), t("Titoli per ISIN e saldi degli exchange crypto"))
    base = db.base_currency()
    st.caption(t("Quotazioni da Yahoo Finance (Google Finance non offre un'API pubblica), aggiornate all'apertura "
                 "e con il pulsante «Quotazioni» nella barra laterale. Valori in {base} ai cambi BCE.", base=base))
    tab1, tab5, tab2, tab3, tab4 = st.tabs([t("Portafoglio"), t("Dagli estratti"), t("Aggiungi titolo"), t("Operazioni"),
                                            t("Exchange crypto")], default=cerca.tab_default("investimenti"))
    with tab1:
        _portfolio_tab(base)
    with tab5:
        inv_estratti.income_tab(base)
    with tab2:
        inv_estratti.positions_import()
        st.divider()
        _add_instrument_tab()
    with tab3:
        _trades_tab(base)
    with tab4:
        _crypto_tab(base)
