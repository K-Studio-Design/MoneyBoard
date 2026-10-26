from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core import db, fx, i18n
from core.i18n import t
from views import style, ui

ALL = fx.COMMON_CURRENCIES + fx.CRYPTO


@st.cache_data(ttl=1800, show_spinner=False)
def _rates_table(base: str) -> dict:
    return fx.latest_table(base, [c for c in fx.COMMON_CURRENCIES if c != base][:20])


@st.cache_data(ttl=3600, show_spinner=False)
def _series(base: str, quote: str, days: int) -> pd.DataFrame:
    start = date.today() - timedelta(days=days)
    if base in fx.CRYPTO or quote in fx.CRYPTO:
        import yfinance as yf

        inverse = quote in fx.CRYPTO and base not in fx.CRYPTO
        sym = f"{quote}-{base}" if inverse else f"{base}-{quote}"
        h = yf.Ticker(sym).history(start=start.isoformat(), auto_adjust=False)
        if h.empty:
            return pd.DataFrame()
        s = h["Close"]
        s = 1 / s if inverse else s
        return pd.DataFrame({"Data": s.index.tz_localize(None), "Cambio": s.values})
    data = fx._frankfurter(f"{start.isoformat()}..", {"base": base, "symbols": quote})
    rows = [(pd.Timestamp(d), v[quote]) for d, v in data.get("rates", {}).items() if quote in v]
    return pd.DataFrame(rows, columns=["Data", "Cambio"])


def render():
    style.header(t("Valute e cambi"), t("Cambi ufficiali BCE e, per valute non BCE e crypto, Yahoo Finance"))
    base = db.base_currency()

    st.subheader(t("Convertitore"))
    c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
    amount = c1.number_input(t("Importo"), value=100.0, min_value=0.0, step=10.0, format="%.2f")
    frm = c2.selectbox(t("Da"), ALL, index=ALL.index("USD"))
    to = c3.selectbox(t("A"), ALL, index=ALL.index(base) if base in ALL else 0)
    on = c4.date_input(t("Alla data"), value=date.today(), max_value=date.today(), format=i18n.date_fmt())
    try:
        res, rate = fx.convert(amount, frm, to, on)
        st.markdown(f"### {ui.fmt_num(amount)} {frm} = **{ui.fmt_num(res, 4 if to in fx.CRYPTO else 2)} {to}**")
        st.caption(f"1 {frm} = {rate:.6f} {to} · 1 {to} = {1 / rate:.6f} {frm}")
    except Exception as e:
        st.error(t("Cambio non disponibile: {err}", err=e))

    days = st.select_slider(t("Storico"), options=[30, 90, 180, 365, 730, 1825], value=365,
                            format_func=lambda d: t({30: "1 mese", 90: "3 mesi", 180: "6 mesi", 365: "1 anno",
                                                     730: "2 anni", 1825: "5 anni"}[d]))
    if frm != to:
        try:
            s = _series(frm, to, days)
            if not s.empty:
                fig = px.line(s, x="Data", y="Cambio", title=f"{frm}/{to}",
                              labels={"Data": t("Data"), "Cambio": t("Cambio")})
                fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
                style.chart(fig)
        except Exception as e:
            st.caption(t("Storico non disponibile: {err}", err=e))

    st.subheader(t("Cambi attuali rispetto a 1 {base}", base=base))
    try:
        rates = _rates_table(base)
        if rates:
            c_a, c_b = f"1 {base} =", t("1 unità = {base}", base=base)
            tab = pd.DataFrame([{t("Valuta"): k, c_a: v, c_b: 1 / v} for k, v in rates.items() if v])
            style.table(tab, {c_a: ("num", 4), c_b: ("num", 4)}, height=420)
    except Exception as e:
        st.caption(t("Tabella non disponibile: {err}", err=e))
