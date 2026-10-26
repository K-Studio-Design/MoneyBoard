"""Obiettivi di risparmio: quanto hai messo da parte, quanto manca, se sei in linea con la scadenza."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, goals, i18n
from core.i18n import t
from views import cerca, style, ui

STATUS = {
    "raggiunto": ("Raggiunto", "pos"),
    "in_linea": ("In linea con la scadenza", "pos"),
    "in_ritardo": ("In ritardo sulla scadenza", "neg"),
    "fermo": ("Fermo: negli ultimi mesi non è cresciuto", "neg"),
    "in_calo": ("In calo negli ultimi mesi", "neg"),
    "senza_scadenza": ("Senza scadenza", ""),
    "nuovo": ("Appena creato", ""),
}
COLOR_NAMES = {"#7C5CFC": "Viola", "#14AE9E": "Verde acqua", "#F0627E": "Corallo", "#F5A524": "Arancio",
               "#3B82F6": "Blu", "#EC4899": "Fucsia", "#22C55E": "Verde", "#8B5CF6": "Lavanda"}
COLORS = list(COLOR_NAMES)
def _month_year(d) -> str:
    d = pd.Timestamp(d)
    return f"{i18n.month(d.month)} {d.year}"


def _ring(pct: float, color: str) -> str:
    """Anello di avanzamento in SVG (0-100%)."""
    p = max(0.0, min(100.0, pct))
    r, c = 34, 2 * 3.14159 * 34
    return (f'<svg viewBox="0 0 80 80" class="ring" aria-hidden="true">'
            f'<circle cx="40" cy="40" r="{r}" fill="none" stroke="var(--as-track)" stroke-width="8"/>'
            f'<circle cx="40" cy="40" r="{r}" fill="none" stroke="{color}" stroke-width="8" stroke-linecap="round"'
            f' stroke-dasharray="{c * p / 100:.1f} {c:.1f}" transform="rotate(-90 40 40)"/>'
            f'<text x="40" y="45" text-anchor="middle">{p:.0f}%</text></svg>')


def _plan_text(g: dict, p: goals.Progress, ccy: str) -> str:
    if p.status == "raggiunto":
        return t("Obiettivo raggiunto.")
    parts = []
    if p.needed is not None:
        parts.append(t("Per arrivarci entro {d} servono {v} al mese.", d=_month_year(g["deadline"]),
                       v=ui.money(p.needed, ccy)))
    if p.pace is not None:
        if p.pace > 0 and p.projected is not None:
            parts.append(t("Al ritmo attuale ({v} al mese) lo raggiungi a {d}.", v=ui.money(p.pace, ccy),
                           d=_month_year(p.projected)))
        elif p.pace < 0:
            parts.append(t("Negli ultimi 3 mesi è sceso in media di {v} al mese.", v=ui.money(-p.pace, ccy)))
        else:
            parts.append(t("Negli ultimi 3 mesi non è cresciuto."))
    return " ".join(parts) or t("Aggiungi versamenti per vedere a che punto sei.")


def render():
    style.header(t("Obiettivi"), t("Quanto metti da parte per le cose che ti interessano"))
    base = db.base_currency()
    tx = db.transactions_df()
    gl = db.goals_df()
    progresses = {int(g["id"]): goals.progress(g, tx) for g in gl.to_dict("records")}

    if not gl.empty:
        # totali in valuta base (gli obiettivi su un conto in altra valuta vengono convertiti)
        rates = {int(g["id"]): goals.rate_to_base(goals.goal_currency(g), tx) or 0.0 for g in gl.to_dict("records")}
        saved = sum(p.current * rates[i] for i, p in progresses.items())
        target = sum(p.target * rates[i] for i, p in progresses.items())
        needed = sum((p.needed or 0) * rates[i] for i, p in progresses.items())
        avg = goals.monthly_savings(tx)
        items = [
            dict(label=t("Messi da parte"), sub=t("1 obiettivo") if len(gl) == 1 else t("{n} obiettivi", n=len(gl)),
                 value=ui.money(saved, base), variant="entrate",
                 pct=(max(saved, 0) / target * 100 if target > 0 else None),
                 pct_label=t("{p}% del totale", p=f"{max(saved, 0) / target * 100:.0f}") if target > 0 else ""),
            dict(label=t("Totale obiettivi"), sub=t("Mancano {v}", v=ui.money(max(target - saved, 0), base)),
                 value=ui.money(target, base), variant="saldo"),
            dict(label=t("Servono al mese"), sub=t("Per rispettare tutte le scadenze"), value=ui.money(needed, base),
                 variant="spese"),
        ]
        if avg is not None:
            ok = avg >= needed
            items.append(dict(label=t("Risparmio medio al mese"), sub=t("Entrate meno spese, ultimi 6 mesi"),
                              value=ui.money(avg, base), variant="media",
                              pct=(min(avg / needed * 100, 100) if needed > 0 and avg > 0 else None),
                              pct_label=(t("basta per gli obiettivi") if ok else t("non basta per gli obiettivi"))))
        style.gradient_cards(items)

        cols = st.columns(2, gap="medium")
        for i, g in enumerate(gl.to_dict("records")):
            p = progresses[int(g["id"])]
            with cols[i % 2], style.card(f"goal_{g['id']}"):
                _goal_card(g, p, goals.goal_currency(g))

    with st.expander(t("Nuovo obiettivo"), icon=":material/add:", expanded=gl.empty or cerca.is_open("nuovo_obiettivo")):
        _goal_form(tx, base, None)

    archived = db.goals_df(include_archived=True)
    archived = archived[archived["archived"] == 1]
    if not archived.empty:
        with st.expander(t("Archiviati ({n})", n=len(archived)), icon=":material/inventory_2:"):
            for g in archived.to_dict("records"):
                c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="center")
                c1.write(f"{ui.esc(g['name'])}: {ui.esc(ui.money(g['target'], base))}")
                if c2.button(t("Ripristina"), key=f"g_unarch_{g['id']}"):
                    db.save_goal({"archived": 0}, int(g["id"]))
                    st.rerun()
                if c3.button(t("Elimina"), key=f"g_del_{g['id']}", type="tertiary"):
                    db.delete_goal(int(g["id"]))
                    st.rerun()


def _goal_card(g: dict, p: goals.Progress, ccy: str) -> None:
    color = style.safe_color(g.get("color") or COLORS[0])
    label, cls = STATUS.get(p.status, ("", ""))
    label = t(label) if label else ""
    dl = t("entro {d}", d=_month_year(g["deadline"])) if g.get("deadline") else t("senza scadenza")
    how = t(goals.MODES.get(g.get("mode") or "manuale", "")) if goals.MODES.get(g.get("mode") or "manuale") else ""
    if g.get("mode") == "conto":
        how = t("saldo {acc} {ccy}", acc=g.get("account"), ccy=g.get("account_ccy"))
    st.html(f'''<div class="as-goal">{_ring(p.pct, color)}
  <div class="info"><div class="n">{style.e(g["name"])}</div>
  <div class="v">{style.e(ui.money(p.current, ccy))} <span>{style.e(t("di {v}", v=ui.money(p.target, ccy)))}</span></div>
  <div class="m">{style.e(dl)}, {style.e(how)}</div>
  <div class="st {cls}">{style.e(label)}</div></div></div>
<p class="as-goal-plan">{style.e(_plan_text(g, p, ccy))}</p>''')
    c1, c2 = st.columns(2)
    if g.get("mode") != "conto":
        if c1.button(t("Versamento"), key=f"g_add_{g['id']}", icon=":material/add_card:", width="stretch"):
            st.dialog(t("Versamento: {name}", name=ui.esc(g["name"])))(_move_dialog)(int(g["id"]))
    if c2.button(t("Dettagli"), key=f"g_open_{g['id']}", icon=":material/open_in_full:", width="stretch"):
        st.dialog(ui.esc(g["name"]), width="large")(_goal_dialog)(int(g["id"]))


def _move_dialog(goal_id: int) -> None:
    c1, c2 = st.columns(2)
    kind = c1.segmented_control(t("Tipo"), ["Versamento", "Prelievo"], default="Versamento", key=f"gm_kind_{goal_id}",
                                format_func=t)
    amount = c2.number_input(t("Importo"), min_value=0.0, step=10.0, format="%.2f", key=f"gm_amt_{goal_id}")
    day = st.date_input(t("Data"), value=date.today(), format=i18n.date_fmt(), key=f"gm_day_{goal_id}")
    note = st.text_input(t("Nota (facoltativa)"), key=f"gm_note_{goal_id}")
    if st.button(t("Salva"), type="primary", key=f"gm_save_{goal_id}", disabled=amount <= 0):
        db.add_goal_move(goal_id, day.isoformat(), amount if kind != "Prelievo" else -amount, note)
        st.rerun()


def _goal_dialog(goal_id: int) -> None:
    gl = db.goals_df(include_archived=True)
    if goal_id not in set(gl["id"]):
        return
    g = gl[gl["id"] == goal_id].iloc[0].to_dict()
    base = goals.goal_currency(g)
    tx = db.transactions_df()
    p = goals.progress(g, tx)
    color = style.safe_color(g.get("color"))
    label, cls = STATUS.get(p.status, ("", ""))
    label = t(label) if label else ""
    dl = t("entro {d}", d=_month_year(g["deadline"])) if g.get("deadline") else t("senza scadenza")
    st.html(f'''<div class="as-focus-top" style="background:linear-gradient(135deg,{color},{style.rgba(color, 0.55)})">
  <div><div class="amt">{style.e(ui.money(p.current, base))}</div>
  <div class="conv">{style.e(t("di {v}", v=ui.money(p.target, base)))}, {p.pct:.0f}%</div></div>
  <div class="when"><b>{style.e(label)}</b><br>{style.e(dl)}<br>
  {style.e(t("mancano {v}", v=ui.money(p.remaining, base)) if p.remaining > 0 else "")}</div></div>''')
    items = [(t("Al mese, finora"), ui.money(p.pace, base) if p.pace is not None else "–", t("ultimi 3 mesi"))]
    if p.needed is not None:
        items.append((t("Servono al mese"), ui.money(p.needed, base),
                      t("{n} mesi alla scadenza", n=f"{p.months_left:.0f}") if p.months_left else t("scadenza passata")))
    items.append((t("Previsione"), _month_year(p.projected) if p.projected is not None else "–", t("al ritmo attuale")))
    style.kpis(items, cols=len(items))

    h = p.history
    if len(h) > 1:
        fig = go.Figure()
        fig.add_scatter(x=h.index, y=h.values, name=t("Messi da parte"), mode="lines", line=dict(color=color, width=3),
                        fill="tozeroy", fillcolor=style.rgba(color, 0.12),
                        hovertemplate="%{x|" + i18n.strf() + "}<br>%{y:,.2f} " + base + "<extra></extra>")
        if g.get("deadline"):
            dl = pd.Timestamp(g["deadline"])
            fig.add_scatter(x=[h.index[-1], dl], y=[h.values[-1], p.target], name=t("Percorso per la scadenza"),
                            mode="lines", line=dict(color="#8B95A1", dash="dot", width=2),
                            hovertemplate="%{x|" + i18n.strf() + "}<br>%{y:,.2f} " + base + "<extra></extra>")
        fig.add_hline(y=p.target, line_dash="dash", line_color=color, opacity=0.6,
                      annotation_text=t("obiettivo {v}", v=ui.money(p.target, base)), annotation_position="top left")
        style.chart(fig, height=260)

    if g.get("mode") != "conto":
        moves = db.goal_moves_df(goal_id)
        st.subheader(t("Versamenti"))
        if moves.empty:
            st.caption(t("Nessun versamento registrato."))
        else:
            for m in moves.sort_values("date", ascending=False).head(30).to_dict("records"):
                c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="center")
                c1.write(f"{m['date']:{i18n.strf()}}" + (f", {ui.esc(m['note'])}" if m.get("note") else ""))
                c2.write(ui.esc(ui.money(m["amount"], base)))
                if c3.button("", icon=":material/delete:", key=f"gmd_{m['id']}", help=t("Elimina questo versamento")):
                    db.delete_goal_move(int(m["id"]))
                    st.rerun(scope="fragment")
        with st.popover(t("Aggiungi versamento"), icon=":material/add_card:"):
            _move_dialog(goal_id)

    st.subheader(t("Modifica"))
    _goal_form(tx, db.base_currency(), g)
    c1, c2 = st.columns(2)
    if c1.button(t("Archivia"), key=f"g_arch_{goal_id}", icon=":material/inventory_2:"):
        db.save_goal({"archived": 1}, goal_id)
        st.rerun()
    if c2.toggle(t("Voglio eliminarlo"), key=f"g_delask_{goal_id}"):
        if st.button(t("Elimina definitivamente"), key=f"g_delok_{goal_id}", icon=":material/delete:"):
            db.delete_goal(goal_id)
            st.rerun()


def _goal_form(tx: pd.DataFrame, base: str, g: dict | None) -> None:
    k = f"gf_{g['id'] if g else 'new'}"
    c1, c2 = st.columns([2, 1])
    name = c1.text_input(t("Nome"), value=(g or {}).get("name", ""),
                         placeholder=t("Es. Fondo emergenza, Vacanza in Giappone"), key=f"{k}_name")
    target = c2.number_input(t("Obiettivo ({ccy})", ccy=base), min_value=0.0, step=100.0, format="%.2f",
                             value=float((g or {}).get("target") or 0.0), key=f"{k}_target")
    c1, c2 = st.columns(2)
    has_dl = c1.toggle(t("Con scadenza"), value=bool((g or {}).get("deadline")) if g else True, key=f"{k}_hasdl")
    deadline = None
    if has_dl:
        default_dl = pd.Timestamp((g or {}).get("deadline") or (pd.Timestamp(date.today()) + pd.DateOffset(years=1))).date()
        deadline = c2.date_input(t("Entro il"), value=default_dl, min_value=date.today() if not g else None,
                                 format=i18n.date_fmt(), key=f"{k}_dl")
    modes = list(goals.MODES)
    mode = st.radio(t("Come misurare i soldi messi da parte"), modes, format_func=lambda m: t(goals.MODES[m]),
                    index=modes.index((g or {}).get("mode") or "manuale"), horizontal=True, key=f"{k}_mode",
                    captions=[t("Registri tu ogni versamento"), t("Es. il conto deposito o un conto dedicato"),
                              t("Entrate meno spese da una certa data")])
    fields = {}
    if mode == "conto":
        opts = goals.account_options(tx)
        if not opts:
            st.caption(t("Non ci sono ancora conti: importa prima un estratto."))
            return
        cur = ((g or {}).get("account"), (g or {}).get("account_ccy"))
        c1, c2 = st.columns(2)
        acc = c1.selectbox(t("Conto"), opts, index=opts.index(cur) if cur in opts else 0,
                           format_func=lambda o: f"{o[0]} {o[1]}", key=f"{k}_acc")
        computed = goals.account_balance(tx, *acc)
        offset0 = float((g or {}).get("balance_offset") or 0.0) if cur == acc else 0.0
        bank_off = goals.bank_offset(tx, *acc)
        if bank_off is not None:  # conto collegato: il saldo arriva dalla banca, non si scrive a mano
            real = computed + bank_off
            c2.markdown(f"**{ui.esc(ui.money(real, acc[1]))}**  \n"
                        f":green-badge[:material/sync: {t('Sincronizzato dalla banca')}]")
        else:
            real = None
        real = real if real is not None else c2.number_input(t("Saldo attuale reale ({ccy})", ccy=acc[1]), value=round(computed + offset0, 2), step=100.0,
                               format="%.2f", key=f"{k}_real_{acc[0]}_{acc[1]}",
                               help=t("Il saldo che vedi nell'app della banca. Se gli estratti importati non partono "
                                      "dall'apertura del conto, la differenza viene usata per tarare il calcolo."))
        if bank_off is None and computed < 0 and abs(real - computed) < 0.005:
            st.caption(t("Il saldo calcolato dai movimenti importati è negativo, perché gli estratti non partono "
                         "dall'apertura del conto: scrivi qui sopra il saldo reale che vedi nell'app della banca."))
        fields.update(account=acc[0], account_ccy=acc[1], balance_offset=real - computed, initial=0)
        if acc[1] != base:
            st.caption(t("Il saldo è in {ccy}: obiettivo e importi di questo obiettivo sono da intendere in {ccy}.", ccy=acc[1]))
    else:
        fields.update(account=None, account_ccy=None, balance_offset=0)
        fields["initial"] = st.number_input(t("Già messo da parte all'inizio"), min_value=0.0, step=50.0, format="%.2f",
                                            value=float((g or {}).get("initial") or 0.0), key=f"{k}_init")
    start_default = pd.Timestamp((g or {}).get("start_date") or date.today()).date()
    start = st.date_input(t("Inizio (da quando contare entrate e spese)") if mode == "risparmio" else t("Inizio"),
                          value=start_default, format=i18n.date_fmt(), key=f"{k}_start")
    cur_color = (g or {}).get("color") if (g or {}).get("color") in COLORS else COLORS[0]
    color = st.selectbox(t("Colore"), COLORS, index=COLORS.index(cur_color), format_func=lambda c: t(COLOR_NAMES[c]),
                         key=f"{k}_color")
    if st.button(t("Salva obiettivo") if g else t("Crea obiettivo"), type="primary", key=f"{k}_save",
                 disabled=not name.strip() or target <= 0):
        fields.update(name=name.strip(), target=target, deadline=deadline.isoformat() if deadline else None,
                      start_date=start.isoformat(), mode=mode, color=color or COLORS[0])
        db.save_goal(fields, int(g["id"]) if g else None)
        st.rerun()
