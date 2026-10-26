"""Abbonamenti e pagamenti ricorrenti, trovati in automatico nei movimenti."""
from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n, recurring
from core.i18n import t
from views import focus, style, ui

def short_date(d) -> str:
    d = pd.Timestamp(d)
    if d.year != date.today().year:
        return i18n.date_short(d)
    return i18n.day_month(d)


def days_to(d) -> str:
    n = (pd.Timestamp(d).normalize() - pd.Timestamp(date.today())).days
    return (t("oggi") if n == 0 else t("domani") if n == 1 else t("tra {n} giorni", n=n) if n > 1
            else t("{n} giorni fa", n=-n))


def _ini(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9]+", name) if len(w) > 2 or name.count(" ") == 0]
    return ("".join(w[0] for w in words[:2]) or name[:1] or "•").upper()


def _rows(series: list[recurring.Series], colors: dict, names: dict, base: str, inactive: bool = False) -> list[dict]:
    rows = []
    for s in series:
        per = t(recurring.CADENCE_ADJ[s.cadence])
        if inactive:
            meta = t("{cad}, ultimo addebito il {d}, {acc}", cad=t(s.cadence), d=short_date(s.last), acc=s.account)
        else:
            rule = {"ultimo_lav": t(", ultimo giorno lavorativo"), "primo_lav": t(", primo giorno lavorativo")}.get(s.day_rule, "")
            meta = t("{cad}{rule}, prossimo {d} ({when}), {acc}", cad=t(s.cadence), rule=rule, d=short_date(s.next_date),
                     when=days_to(s.next_date), acc=s.account)
        amt = ui.money(s.amount, s.currency)
        if s.variable:
            amt = t("circa ") + ui.money(s.typical_base, base)
        sub = (t("{v} all'anno", v=ui.money(s.yearly_base, base)) if s.cadence != "annuale"
               else t("{v} al mese", v=ui.money(s.monthly_base, base)))
        nm = recurring.display_name(s, names)
        rows.append(dict(id=s.sid, desc=nm, ini=_ini(nm), meta=meta, cat="",
                         color=colors.get(s.category, "#A3A0B5"), amount=f"{amt} {per}", sub=sub,
                         cls="pos" if s.kind == "entrata" else ""))
    return rows


def render():
    style.header(t("Abbonamenti"), t("Pagamenti e accrediti che si ripetono, trovati in automatico nei movimenti"))
    base = db.base_currency()
    all_series = ui.recurring_series(include_hidden=True)
    hidden = recurring.hidden()
    series = [s for s in all_series if s.sid not in hidden]
    if not series:
        st.info(t("Non ho ancora trovato pagamenti ricorrenti: servono almeno 3 addebiti simili a intervalli regolari "
                  "(per esempio 3 mesi di Netflix). Importa gli estratti dei mesi passati per trovarne di più."))
        _hidden_box(all_series, hidden)
        return

    out_active = [s for s in series if s.kind == "uscita" and s.active]
    out_old = [s for s in series if s.kind == "uscita" and not s.active]
    inc_active = [s for s in series if s.kind == "entrata" and s.active]
    monthly = sum(s.monthly_base for s in out_active)
    today = date.today()
    nxt30 = [(d, s) for d, s in recurring.upcoming(out_active, today, today + timedelta(days=30))]
    tot30 = sum(s.typical_base for _, s in nxt30)
    subs = [s for s in out_active if s.category == "Abbonamenti e servizi digitali"]
    sel = style.gradient_cards([
        dict(id="mese", label=t("Costo al mese"), sub=t("{n} pagamenti attivi", n=len(out_active)),
             value=ui.money(monthly, base), variant="spese"),
        dict(id="anno", label=t("Costo all'anno"), sub=t("Se restano tutti attivi"), value=ui.money(monthly * 12, base),
             variant="media"),
        dict(id="prossimi", label=t("Prossimi 30 giorni"), sub=t("{n} addebiti previsti", n=len(nxt30)),
             value=ui.money(tot30, base), variant="saldo"),
        dict(id="digitali", label=t("Servizi digitali al mese"), sub=t("{n} abbonamenti (streaming, app…)", n=len(subs)),
             value=ui.money(sum(s.monthly_base for s in subs), base), variant="entrate"),
    ], key="abb_cards")
    if sel == "prossimi":
        open_upcoming(today, today + timedelta(days=30), "uscita", t("Prossimi 30 giorni"))
    elif sel in ("mese", "anno", "digitali"):
        open_cost(sel)

    from core import alerts as _alerts
    changed = [s for s in out_active if s.price_change and (pd.Timestamp(today) - s.price_change_date).days <= 90
               and s.category not in _alerts._NO_PRICE]
    names = recurring.custom_names()
    for s in changed:
        a, b = s.price_change
        msg = ("**{name}**: importo aumentato da {a} a {b} il {d}." if b > a
               else "**{name}**: importo diminuito da {a} a {b} il {d}.")
        st.warning(t(msg, name=ui.esc(recurring.display_name(s, names)), a=ui.esc(ui.money(a, s.currency)),
                     b=ui.esc(ui.money(b, s.currency)), d=f"{s.price_change_date:{i18n.strf()}}"),
                   icon=":material/trending_up:" if b > a else ":material/trending_down:")

    colors = ui.color_map()
    left, right = st.columns([3, 2], gap="medium")
    with left:
        with style.card("abb_attivi"):
            st.subheader(t("Attivi"))
            st.caption(t("Ordinati per costo mensile. Clicca per il dettaglio, per rinominarli o per nasconderli."))
            sel = style.item_list(_rows(out_active, colors, names, base), key="abb_list") if out_active else None
            if not out_active:
                st.caption(t("Nessun pagamento ricorrente attivo."))
            if sel:
                open_series(sel)
        if out_old:
            with style.card("abb_old"):
                st.subheader(t("Non più addebitati"))
                st.caption(t("Erano regolari ma l'ultimo addebito atteso non è arrivato: forse li hai disdetti."))
                sel = style.item_list(_rows(out_old, colors, names, base, inactive=True), key="abb_old_list")
                if sel:
                    open_series(sel)
    with right:
        with style.card("abb_next"):
            st.subheader(t("In arrivo"))
            if nxt30:
                rows = "".join(
                    f'<div><span>{style.e(short_date(d))}, {style.e(recurring.display_name(s, names))}</span>'
                    f'<span>{style.e((t("circa ") if s.variable else "") + ui.money(s.amount if not s.variable else s.typical_base, s.currency if not s.variable else base))}</span></div>'
                    for d, s in nxt30)
                st.html(f'<div class="as-mini">{rows}</div>')
                st.caption(t("Previsione in base alla cadenza abituale di ogni pagamento."))
            else:
                st.caption(t("Nessun addebito previsto nei prossimi 30 giorni."))
        if subs or out_active:
            with style.card("abb_cat"):
                st.subheader(t("Per categoria"))
                by = {}
                for s in out_active:
                    by[ui.cat(s.category)] = by.get(ui.cat(s.category), 0) + s.monthly_base
                style.category_bars([(c, v, colors.get(c, "#A3A0B5")) for c, v in
                                     sorted(by.items(), key=lambda x: -x[1])], lambda v: ui.money(v, base) + t("/mese"))
        if inc_active:
            with style.card("abb_inc"):
                st.subheader(t("Entrate ricorrenti"))
                sel = style.item_list(_rows(inc_active, colors, names, base), key="abb_inc_list")
                if sel:
                    open_series(sel)
    _hidden_box(all_series, hidden)


def _hidden_box(all_series, hidden: set[str]) -> None:
    hid = [s for s in all_series if s.sid in hidden]
    if not hid:
        return
    names = recurring.custom_names()
    with st.expander(t("Nascosti ({n})", n=len(hid)), icon=":material/visibility_off:"):
        st.caption(t("«Elimina» li toglie anche da qui. Possono ricomparire solo se cambiano i movimenti "
                     "(per esempio dopo un nuovo import con nuovi addebiti)."))
        for s in hid:
            c1, c2, c3 = st.columns([5, 1.2, 1.2], vertical_alignment="center")
            c1.write(f"{ui.esc(recurring.display_name(s, names))}, {t(s.cadence)}, {ui.esc(ui.money(s.amount, s.currency))}")
            if c2.button(t("Ripristina"), key=f"abb_unhide_{s.sid}", width="stretch"):
                recurring.set_hidden(s.sid, False)
                st.rerun()
            if c3.button(t("Elimina"), key=f"abb_del_{s.sid}", icon=":material/delete:", width="stretch"):
                recurring.delete(s.sid)
                st.rerun()
        if len(hid) > 1 and st.button(t("Elimina tutti i nascosti ({n})", n=len(hid)), key="abb_del_all",
                                      icon=":material/delete_sweep:", type="tertiary"):
            recurring.delete([s.sid for s in hid])
            st.rerun()


# ---------------------------------------------------------------- finestre dei riquadri in alto
DIGITAL = "Abbonamenti e servizi digitali"


def _pick_series(sel) -> None:
    """Pagamento cliccato dentro una finestra: si apre il suo dettaglio (dopo aver chiuso questa finestra)."""
    if sel:
        st.session_state[focus.PENDING_SERIES] = str(sel)
        st.rerun()


def open_cost(which: str) -> None:
    """which: 'mese' (costo al mese), 'anno' (costo all'anno), 'digitali' (servizi digitali al mese)."""
    title = {"mese": t("Costo al mese"), "anno": t("Costo all'anno"), "digitali": t("Servizi digitali al mese")}[which]
    st.dialog(title, width="large")(_cost_body)(which)


def _cost_body(which: str) -> None:
    base = db.base_currency()
    series = [s for s in ui.recurring_series() if s.kind == "uscita" and s.active]
    if which == "digitali":
        series = [s for s in series if s.category == DIGITAL]
    if not series:
        st.caption(t("Nessun pagamento ricorrente attivo."))
        return
    yearly = which == "anno"
    value = (lambda s: s.monthly_base * 12) if yearly else (lambda s: s.monthly_base)
    series = sorted(series, key=value, reverse=True)
    total = sum(value(s) for s in series)
    top = series[0]
    names = recurring.custom_names()
    style.kpis(cols=3, items=[
        (t("Totale all'anno") if yearly else t("Totale al mese"), ui.money(total, base),
         t("se restano tutti attivi") if yearly else t("in media")),
        (t("Pagamenti"), f"{len(series)}", t("attivi")),
        (t("Il più caro"), recurring.display_name(top, names),
         ui.money(value(top), base) + (t("/anno") if yearly else t("/mese"))),
    ])
    if which != "digitali":
        by: dict[str, float] = {}
        for s in series:
            by[ui.cat(s.category)] = by.get(ui.cat(s.category), 0.0) + value(s)
        st.subheader(t("Per categoria"))
        colors = ui.color_map()
        style.category_bars([(c, v, colors.get(c, "#A3A0B5")) for c, v in sorted(by.items(), key=lambda x: -x[1])],
                            lambda v: ui.money(v, base) + (t("/anno") if yearly else t("/mese")))
    st.subheader(t("Pagamenti"))
    st.caption(t("Clicca su un pagamento per il dettaglio."))
    colors = ui.color_map()
    rows = []
    for s in series:
        nm = recurring.display_name(s, names)
        share = value(s) / total * 100 if total else 0
        rows.append(dict(id=s.sid, desc=nm, ini=_ini(nm), color=colors.get(s.category, "#A3A0B5"),
                         meta=f"{t(s.cadence)}, {s.account}",
                         amount=ui.money(value(s), base) + (t("/anno") if yearly else t("/mese")),
                         sub=t("{p}% del totale", p=f"{share:.0f}")))
    _pick_series(style.item_list(rows, key=f"abb_cost_{which}"))


def open_upcoming(start: date, end: date, kind: str, title: str) -> None:
    """Accrediti (kind='entrata') o addebiti ('uscita') previsti tra start ed end, con le date."""
    st.dialog(title, width="large")(_upcoming_body)(start.isoformat(), end.isoformat(), kind)


def _upcoming_body(start_iso: str, end_iso: str, kind: str) -> None:
    base = db.base_currency()
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    series = [s for s in ui.recurring_series() if s.kind == kind and s.active]
    items = sorted(recurring.upcoming(series, start, end), key=lambda x: pd.Timestamp(x[0]))
    if not items:
        st.caption(t("Nessun accredito previsto nel periodo.") if kind == "entrata"
                   else t("Nessun addebito previsto nel periodo."))
        return
    total = sum(s.typical_base for _d, s in items)
    style.kpis(cols=3, items=[
        (t("Totale previsto"), ui.money(total, base), t("dal {a} al {b}", a=short_date(start), b=short_date(end))),
        (t("Accrediti") if kind == "entrata" else t("Addebiti"), f"{len(items)}"),
        (t("Il prossimo"), short_date(items[0][0]), days_to(items[0][0])),
    ])
    st.caption(t("Date previste in base alla cadenza abituale di ogni pagamento. Clicca per il dettaglio."))
    names = recurring.custom_names()
    colors = ui.color_map()
    rows = []
    for d, s in items:
        nm = recurring.display_name(s, names)
        amt = (t("circa ") + ui.money(s.typical_base, base)) if s.variable else ui.money(s.amount, s.currency)
        rows.append(dict(id=s.sid, desc=nm, ini=_ini(nm), color=colors.get(s.category, "#A3A0B5"),
                         meta=f"{short_date(d)} ({days_to(d)}), {s.account}", amount=amt, sub=t(s.cadence),
                         cls="pos" if kind == "entrata" else ""))
    _pick_series(style.item_list(rows, key=f"abb_next_{kind}_{start_iso}_{end_iso}"))


def find(sid: str):
    for s in ui.recurring_series(include_hidden=True):
        if s.sid == sid:
            return s
    return None


def open_series(sid: str) -> None:
    s = find(sid)
    if s is None:
        st.toast(t("Pagamento non trovato"), icon=":material/error:")
        return
    st.dialog(ui.esc(recurring.display_name(s)), width="large")(_series_body)(sid)


def _series_body(sid: str) -> None:
    s = find(sid)
    if s is None:
        return
    base = db.base_currency()
    df = ui.prepared_transactions(apply_view=False)
    rows = df[df["id"].isin(s.ids)].sort_values("date")
    variant = "entrata" if s.kind == "entrata" else "spesa"
    amt = (t("circa ") + ui.money(s.typical_base, base)) if s.variable else ui.money(s.amount, s.currency)
    when = (t("Prossimo: {d}", d=focus._fmt_date_long(s.next_date)) if s.active
            else t("Ultimo: {d}, poi non più addebitato", d=focus._fmt_date_long(s.last)))
    st.html(f'''<div class="as-focus-top {variant}">
  <div><div class="amt">{style.e(amt)}</div><div class="conv">{style.e(t(recurring.CADENCE_ADJ[s.cadence]))}, {style.e(s.description[:60])}</div></div>
  <div class="when"><b>{style.e(when)}</b><br>{style.e(s.account)}<br>{style.e(ui.cat(s.category))}</div>
</div>''')
    col = "spesa_base" if s.kind == "uscita" else "entrata_base"
    total = rows[col].sum()
    style.kpis(cols=4, items=[
        (t("Volte"), f"{len(rows)}", t("dal {d}", d=f"{rows['date'].iloc[0]:{i18n.strf()}}") if not rows.empty else None),
        (t("Totale pagato") if s.kind == "uscita" else t("Totale ricevuto"), ui.money(total, base)),
        (t("Al mese"), ui.money(s.monthly_base, base), t("in media")),
        (t("All'anno"), ui.money(s.yearly_base, base), t("se resta attivo") if s.active else t("quando era attivo")),
    ])
    if s.price_change:
        a, b = s.price_change
        st.caption(t("Importo cambiato da {a} a {b} il {d}.", a=ui.esc(ui.money(a, s.currency)),
                     b=ui.esc(ui.money(b, s.currency)), d=f"{s.price_change_date:{i18n.strf()}}"))
    if not rows.empty:
        colr = style.ENTRATA if s.kind == "entrata" else style.SPESA
        fig = go.Figure(go.Bar(x=rows["date"], y=rows["amount"].abs(), marker_color=colr,
                               hovertemplate="%{x|" + i18n.strf() + "}<br>%{y:,.2f} " + s.currency + "<extra></extra>"))
        fig.update_layout(bargap=0.35)
        style.chart(fig, height=190, legend=False)
        last = rows.sort_values("date", ascending=False).head(12)
        mini = "".join(f'<div><span>{x["date"]:{i18n.strf()}}, {style.e(x["account"])}</span>'
                       f'<span>{style.e(ui.money(x["amount"], x["currency"]))}</span></div>' for _, x in last.iterrows())
        st.html(f'<div class="as-mini">{mini}</div>')
        if len(rows) > 12:
            st.caption(t("Gli ultimi 12 di {n}.", n=len(rows)))

    st.subheader(t("Gestisci"))
    if s.months:
        manual = recurring.day_rules().get(sid)
        is_salary = s.kind == "entrata" and s.months == 1 and s.category == recurring.SALARY_CATEGORY
        opts = list(recurring.DAY_RULES)
        labels = {k: t(v) for k, v in recurring.DAY_RULES.items()}
        labels["auto"] = (t("Come impostato nel Profilo ({r})", r=t(recurring.DAY_RULES[recurring.salary_rule()]).lower())
                          if is_salary else
                          t("Automatico: {r}", r=t(recurring.DAY_RULES[s.day_rule_detected]).lower())
                          + (t(" (il {d})", d=s.anchor_day) if s.day_rule_detected == "giorno" else ""))
        choice = st.selectbox(t("Giorno dell'accredito") if s.kind == "entrata" else t("Giorno dell'addebito"), opts,
                              index=opts.index(manual) if manual in opts else 0,
                              format_func=labels.get, key=f"abb_rule_{sid}",
                              help=t("Serve a prevedere le prossime date (calendario, «In arrivo»). "
                                     "Il giorno lavorativo esclude sabati, domeniche e festività nazionali italiane."))
        if choice != (manual or "auto"):
            recurring.set_day_rule(sid, choice)
            st.rerun()
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    new = c1.text_input(t("Nome"), value=recurring.display_name(s), key=f"abb_name_{sid}")
    if c2.button(t("Salva nome"), key=f"abb_save_{sid}"):
        recurring.set_name(sid, new if new != recurring.pretty_name_of(s) else "")
        st.rerun()
    if s.sid in recurring.hidden():
        if st.button(t("Mostra di nuovo tra i ricorrenti"), key=f"abb_show_{sid}", icon=":material/visibility:"):
            recurring.set_hidden(sid, False)
            st.rerun()
    elif st.button(t("Non è un pagamento ricorrente: nascondi"), key=f"abb_hide_{sid}", icon=":material/visibility_off:"):
        recurring.set_hidden(sid, True)
        st.rerun()
    if st.button(t("Elimina"), key=f"abb_delete_{sid}", icon=":material/delete:",
                 help=t("Lo toglie da tutte le liste (anche dai nascosti). Può ricomparire solo se cambiano i movimenti.")):
        recurring.delete(sid)
        st.rerun()
