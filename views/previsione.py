"""Riquadro «Previsione a fine mese» della Panoramica."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, forecast, i18n
from core.i18n import t
from views import focus, nav, style, ui


def _d(d) -> str:
    d = pd.Timestamp(d)
    wd = i18n.weekday(d.weekday(), short=True)
    return f"{wd} {i18n.day_month(d)}" if i18n.is_en() else f"{wd.lower()} {i18n.day_month(d)}"


def card() -> None:
    base = db.base_currency()
    with style.card("previsione"):
        st.subheader(t("Previsione a fine mese"))
        if ui.display_ccy() != base:
            st.caption(t("Disponibile con la valuta «Tutte, convertite in {base}» (filtro nella barra laterale).", base=base))
            return
        built = _build()
        if built is None:
            st.caption(t("Servono dei movimenti per fare una previsione."))
            return
        f, _tx = built
        saldo = f.mode == "saldo"
        label_now = t("Saldo dei conti oggi") if saldo else t("Risultato del mese finora")
        label_end = t("Saldo previsto a fine mese") if saldo else t("Risultato previsto a fine mese")
        pick = style.kpis(cols=4, key="prev_kpis", ids=["oggi", "in", "out", "fine"], items=[
            (label_now, ui.money(f.start_value), t("entrate meno spese dal 1°") if not saldo else ", ".join(f.accounts),
             "pos" if f.start_value >= 0 else "neg"),
            (t("Accrediti attesi"), ui.money(f.expected_in), t("entro fine mese"), "pos" if f.expected_in else ""),
            (t("Addebiti previsti"), ui.money(f.expected_out), t("abbonamenti, rate…")),
            (label_end, ui.money(f.end_value),
             t("con circa {v} di spese al giorno", v=ui.money(f.daily)), "pos" if f.end_value >= 0 else "neg"),
        ])
        if pick == "oggi":
            if saldo:
                st.dialog(label_now, width="large")(_now_body)()
            else:
                from views import mese
                mese.open_detail("saldo", f.today.replace(day=1), f.today)
        elif pick in ("in", "out"):
            st.dialog(t("Accrediti attesi") if pick == "in" else t("Addebiti previsti"),
                      width="large")(_events_body)(pick)
        elif pick == "fine":
            st.dialog(label_end, width="large")(_end_body)()
        dm = "%m/%d" if i18n.is_en() else "%d/%m"
        fig = go.Figure()
        fig.add_scatter(x=f.actual.index, y=f.actual.values, name=t("Finora"), mode="lines",
                        line=dict(color=style.ACCENT, width=3),
                        hovertemplate="%{x|" + dm + "}<br>%{y:,.2f} " + base + "<extra></extra>")
        fig.add_scatter(x=f.projected.index, y=f.projected.values, name=t("Previsione"), mode="lines",
                        line=dict(color=style.ACCENT, width=3, dash="dot"),
                        hovertemplate="%{x|" + dm + "}<br>%{y:,.2f} " + base + f"<extra>{t('previsto')}</extra>")
        if f.events:
            xs = [pd.Timestamp(d) for d, _n, _a, _s in f.events]
            ys = [float(f.projected.get(x, f.projected.iloc[0])) for x in xs]
            fig.add_scatter(x=xs, y=ys, mode="markers", name=t("Accrediti e addebiti"),
                            marker=dict(size=10, color=[style.ENTRATA if a > 0 else style.SPESA
                                                        for _d, _n, a, _s in f.events],
                                        line=dict(width=2, color="white")),
                            customdata=[[n, ui.money(a)] for _d, n, a, _s in f.events],
                            hovertemplate="%{x|" + dm + "}<br><b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>")
        fig.add_hline(y=0, line_color="#8B95A1", line_width=1, opacity=0.5)
        fig.update_xaxes(tickformat="%b %d" if i18n.is_en() else "%d %b")
        style.chart(fig, height=250)
        if saldo and f.min_value < 0:
            st.warning(t("Rischi di andare in rosso: il saldo previsto scende a {v} {d}, prima dei prossimi accrediti.",
                         v=ui.esc(ui.money(f.min_value)), d=_d(f.min_date)), icon=":material/warning:")
        if f.events:
            rows = "".join(f'<div><span>{style.e(_d(d))}, {style.e(n)}</span>'
                           f'<span class="{"pos" if a > 0 else ""}">{style.e(("+" if a > 0 else "") + ui.money(a))}</span></div>'
                           for d, n, a, _s in f.events)
            st.html(f'<div class="as-mini">{rows}</div>')
        tip = t("Previsione: accrediti e addebiti ricorrenti alle loro date, più la tua spesa quotidiana tipica degli "
                "ultimi 90 giorni (senza ricorrenti e spese eccezionali).")
        if not saldo:
            tip += t(" Per vedere il saldo vero dei conti, indica i saldi reali nel Profilo.")
        st.caption(tip)
        if not saldo and "profilo" in nav.PAGES:
            st.page_link(nav.PAGES["profilo"], label=t("Indica i saldi dei conti"), icon=":material/account_balance_wallet:")



# ---------------------------------------------------------------- finestre dei riquadri
def _build():
    """(previsione, movimenti grezzi dei conti scelti) oppure None se non ci sono movimenti."""
    df = ui.prepared_transactions()
    if df.empty:
        return None
    tx = db.transactions_df()
    accs = ui.selected_accounts()
    if accs:
        tx = tx[tx["account"].isin(accs)]
    return forecast.build(df, tx, ui.recurring_series(), accounts=accs or None), tx


def _now_body() -> None:
    built = _build()
    if built is None:
        return
    f, tx = built
    base = db.base_currency()
    from core import goals
    rows = []
    banks = forecast.bank_balances()
    offs = forecast.effective_offsets(tx, banks)
    for key in offs:
        acc, ccy = key.split("|", 1)
        if f"{acc} {ccy}" not in f.accounts:
            continue
        bal = forecast.account_balance(acc, ccy, tx, offsets=offs)
        rate = goals.rate_to_base(ccy, tx)
        if bal is None:
            continue
        src = (t("Banca, al {d}", d=i18n.date_short(pd.Timestamp(banks[key]["date"]))) if key in banks and banks[key]["date"]
               else t("Banca") if key in banks else t("Scritto a mano"))
        rows.append({t("Conto"): acc, t("Valuta"): ccy, t("Saldo"): ui.money(bal, ccy),
                     t("In {base}", base=base): ui.money(bal * rate, base) if rate is not None else "–",
                     t("Fonte del saldo"): src})
    style.kpis(cols=2, items=[
        (t("Saldo dei conti oggi"), ui.money(f.start_value, base), (t("1 conto incluso") if len(f.accounts) == 1
                                                         else t("{n} conti inclusi", n=len(f.accounts))),
         "pos" if f.start_value >= 0 else "neg"),
        (t("Saldo previsto a fine mese"), ui.money(f.end_value, base), _d(f.month_end),
         "pos" if f.end_value >= 0 else "neg"),
    ])
    if rows:
        style.table(pd.DataFrame(rows))
    st.caption(t("Per i conti collegati il saldo arriva dalla banca (si aggiorna a ogni sincronizzazione); per gli "
                 "altri parte da quello scritto nel Profilo. In entrambi i casi si aggiorna da solo con i nuovi "
                 "movimenti."))
    if "profilo" in nav.PAGES:
        st.page_link(nav.PAGES["profilo"], label=t("Modifica i saldi nel Profilo"),
                     icon=":material/account_balance_wallet:")


def _events_body(which: str) -> None:
    built = _build()
    if built is None:
        return
    f, _tx = built
    base = db.base_currency()
    ev = [e for e in f.events if (e[2] > 0) == (which == "in")]
    if not ev:
        st.caption(t("Nessun accredito atteso da qui a fine mese.") if which == "in"
                   else t("Nessun addebito previsto da qui a fine mese."))
        return
    total = sum(abs(a) for _d0, _n, a, _s in ev)
    style.kpis(cols=2, items=[
        (t("Totale"), ui.money(total, base), t("da oggi al {d}", d=_d(f.month_end))),
        (t("Accrediti") if which == "in" else t("Addebiti"), f"{len(ev)}"),
    ])
    st.caption(t("Date previste in base alla cadenza abituale di ogni pagamento. Clicca per il dettaglio."))
    colors = ui.color_map()
    rows = []
    for d, name, a, s in ev:
        rows.append(dict(id=s.sid, desc=name, color=colors.get(s.category, "#A3A0B5"),
                         meta=f"{_d(d)}, {s.account}", amount=("+" if a > 0 else "") + ui.money(a, base),
                         sub=t(s.cadence), cls="pos" if a > 0 else ""))
    sel = style.item_list(rows, key=f"prev_ev_{which}")
    if sel:
        st.session_state[focus.PENDING_SERIES] = str(sel)
        st.rerun()


def _end_body() -> None:
    built = _build()
    if built is None:
        return
    f, _tx = built
    base = db.base_currency()
    n_fut = max((f.month_end - f.today).days, 0)
    spend = f.daily * n_fut
    saldo = f.mode == "saldo"
    lines = [
        (t("Saldo dei conti oggi") if saldo else t("Risultato del mese finora"), ui.money(f.start_value, base), ""),
        (t("+ accrediti attesi"), ui.money(f.expected_in, base), "pos"),
        (t("− addebiti previsti"), ui.money(-f.expected_out, base), ""),
        (t("− spesa quotidiana: {v} × {n} giorni", v=ui.money(f.daily, base), n=n_fut), ui.money(-spend, base), ""),
    ]
    rows = "".join(f'<div><span>{style.e(a)}</span><span class="{c}">{style.e(b)}</span></div>' for a, b, c in lines)
    rows += (f'<div><span><b>{style.e(t("= previsto a fine mese"))}</b></span>'
             f'<span><b>{style.e(ui.money(f.end_value, base))}</b></span></div>')
    st.subheader(t("Come si arriva al numero"))
    st.html(f'<div class="as-mini">{rows}</div>')
    style.kpis(cols=3, items=[
        (t("Punto più basso"), ui.money(f.min_value, base), _d(f.min_date) if f.min_date else "",
         "neg" if f.min_value < 0 else ""),
        (t("Spesa quotidiana tipica"), ui.money(f.daily, base), t("ultimi 90 giorni")),
        (t("Giorni rimanenti"), f"{n_fut}", t("fino al {d}", d=_d(f.month_end))),
    ])
    st.caption(t("La spesa quotidiana tipica è la media degli ultimi 90 giorni senza i pagamenti ricorrenti (già "
                 "contati tra accrediti e addebiti) e senza le spese eccezionali, come un mobile o un volo."))
