"""Spese condivise: chi ti deve dei soldi e a chi li devi tu (amici, partner, coinquilini)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import db, i18n, shared
from core.i18n import t
from views import style, ui

SEL = "cond_person"
FORM_N = "cond_form_n"
KIND_LABELS = {"quota": "Quota di una spesa che hai pagato tu", "rimborso": "Rimborso",
               "manuale": "Voce a mano", "saldo": "Messi in pari"}
DIRECTIONS = {"io": ("Ho pagato io per questa persona", 1), "lei": ("Questa persona ha pagato per me", -1),
              "ricevuto": ("Mi ha restituito dei soldi", -1), "dato": ("Le ho restituito dei soldi", 1)}


def balance_text(v: float, ccy: str) -> str:
    if v > 0.005:
        return t("ti deve {v}", v=ui.money(v, ccy))
    if v < -0.005:
        return t("devi tu {v}", v=ui.money(-v, ccy))
    return t("siete pari")


def _people_list(bal: pd.DataFrame) -> int | None:
    rows = []
    for pid, g in bal.groupby("person_id", sort=False):
        g = g[g["currency"].notna()]
        name = str(bal[bal["person_id"] == pid]["name"].iloc[0])
        nz = g[g["balance"].abs() >= 0.01]
        if nz.empty:
            amount, cls = t("siete pari"), ""
        else:
            amount = " · ".join(balance_text(float(r["balance"]), r["currency"]) for _, r in nz.iterrows())
            cls = "pos" if (nz["balance"] > 0).all() else ""
        n = int(g["n"].sum()) if not g.empty else 0
        last = pd.to_datetime(g["last"]).max() if not g.empty else None
        meta = (t("{n} voci, l'ultima il {d}", n=n, d=i18n.date_short(last)) if n and pd.notna(last)
                else t("nessuna voce"))
        rows.append(dict(id=str(pid), desc=name, meta=meta, amount=amount, cls=cls, color=style.ACCENT))
    sel = style.item_list(rows, key="cond_people")
    return int(sel) if sel is not None else None


def _detail(pid: int, bal: pd.DataFrame) -> None:
    pe = shared.people(include_archived=True)
    row = pe[pe["id"] == pid]
    if row.empty:
        st.session_state.pop(SEL, None)
        return
    name = str(row["name"].iloc[0])
    st.subheader(name)
    mine = bal[(bal["person_id"] == pid) & bal["currency"].notna()]
    for _, r in mine.iterrows():
        v = float(r["balance"])
        c1, c2 = st.columns([3, 1.4], vertical_alignment="center")
        c1.markdown(f"**{ui.esc(balance_text(v, r['currency']))}** ({r['currency']})")
        if abs(v) >= 0.01 and c2.button(t("Segna come saldato"), key=f"cond_settle_{pid}_{r['currency']}",
                                        icon=":material/handshake:", width="stretch",
                                        help=t("Vi siete messi in pari (per esempio in contanti): aggiunge una voce "
                                               "che azzera il saldo.")):
            shared.settle_manual(pid, r["currency"])
            st.rerun()
    ent = shared.entries(pid)
    if ent.empty:
        st.caption(t("Ancora nessuna voce con questa persona."))
    else:
        for _, e in ent.head(30).iterrows():
            c1, c2, c3 = st.columns([4.2, 1.8, 0.7], vertical_alignment="center")
            c1.markdown(f"{i18n.date_short(e['date'])} · {ui.esc(str(e['description'] or ''))[:60]}  \n"
                        f":gray[{ui.esc(t(KIND_LABELS.get(e['kind'], e['kind'])))}]")
            c2.markdown(f"**{ui.esc(balance_text(float(e['amount']), e['currency']))}**")
            if c3.button("", key=f"cond_del_{int(e['id'])}", icon=":material/delete:",
                         help=t("Elimina la voce. Se era la quota di una spesa, la quota torna nella spesa.")):
                shared.delete_entry(int(e["id"]))
                st.rerun()
        if len(ent) > 30:
            st.caption(t("Le ultime 30 di {n}.", n=len(ent)))
    with st.expander(t("Rinomina o elimina"), icon=":material/edit:"):
        new = st.text_input(t("Nome"), value=name, key=f"cond_ren_{pid}")
        c1, c2 = st.columns(2)
        if c1.button(t("Salva il nome"), key=f"cond_ren_b_{pid}", width="stretch"):
            try:
                shared.rename_person(pid, new)
                st.rerun()
            except shared.SharedError as e:
                st.error(str(e))
        sure = st.checkbox(t("Elimina {n} e tutte le sue voci", n=name), key=f"cond_delp_ok_{pid}")
        if c2.button(t("Elimina"), key=f"cond_delp_{pid}", icon=":material/delete:", disabled=not sure,
                     width="stretch"):
            shared.delete_person(pid)
            st.session_state.pop(SEL, None)
            st.rerun()


def _new_entry() -> None:
    st.subheader(t("Nuova voce"))
    pe = shared.people()
    n = st.session_state.setdefault(FORM_N, 0)
    opts = [str(i) for i in pe["id"]] + ["__new__"]
    names = dict(zip([str(i) for i in pe["id"]], pe["name"]))
    who = st.selectbox(t("Persona"), opts, format_func=lambda k: names.get(k, t("Nuova persona…")),
                       key=f"cond_who_{n}")
    new_name = st.text_input(t("Nome della persona"), key=f"cond_newname_{n}", placeholder=t("es. Marco")) \
        if who == "__new__" else ""
    direction = st.radio(t("Cosa è successo"), list(DIRECTIONS), format_func=lambda k: t(DIRECTIONS[k][0]),
                         key=f"cond_dir_{n}")
    c1, c2 = st.columns([2, 1])
    amount = c1.number_input(t("Importo"), min_value=0.0, step=1.0, format="%.2f", key=f"cond_amt_{n}")
    ccys = sorted({db.base_currency(), "EUR", "USD", "GBP", "CHF"})
    ccy = c2.selectbox(t("Valuta"), ccys, index=ccys.index(db.base_currency()), key=f"cond_ccy_{n}")
    day = st.date_input(t("Data"), value=date.today(), format=i18n.date_fmt(), key=f"cond_day_{n}")
    desc = st.text_input(t("Descrizione"), key=f"cond_desc_{n}", placeholder=t("es. cena, biglietti del concerto"))
    if st.button(t("Aggiungi"), type="primary", icon=":material/add:", key=f"cond_add_{n}", width="stretch"):
        try:
            pid = shared.add_person(new_name) if who == "__new__" else int(who)
            sign = DIRECTIONS[direction][1]
            kind = "rimborso" if direction in ("ricevuto", "dato") else "manuale"
            shared.add_entry(pid, day, desc or t(DIRECTIONS[direction][0]), sign * float(amount), ccy, kind)
            st.session_state[FORM_N] = n + 1
            st.session_state[SEL] = pid
            st.rerun()
        except shared.SharedError as e:
            st.error(str(e))
    st.caption(t("Le voci scritte qui servono solo a tenere il conto. Per una spesa che hai pagato tu sul conto, "
                 "meglio aprire il movimento e usare «Dividi con altre persone»: così nelle tue spese resta solo la "
                 "tua parte."))


def render():
    style.header(t("Spese condivise"), t("Chi ti deve dei soldi e a chi li devi tu"))
    bal = shared.balances()
    left, right = st.columns([3, 2], gap="large")
    with left:
        with style.card("cond_list"):
            st.subheader(t("Persone"))
            if bal.empty:
                st.info(t("Qui tieni il conto con amici, partner o coinquilini. Apri una spesa che hai pagato anche "
                          "per altri e scegli «Dividi con altre persone», oppure aggiungi una voce a mano qui accanto."),
                        icon=":material/group:")
            else:
                sel = _people_list(bal)
                if sel is not None:
                    st.session_state[SEL] = sel
        pid = st.session_state.get(SEL)
        if pid is not None and not bal.empty:
            with style.card("cond_detail"):
                _detail(int(pid), bal)
    with right:
        with style.card("cond_new"):
            _new_entry()
        st.caption(t("Come funziona: quando dividi una spesa con qualcuno, la sua parte diventa «Spese condivise» "
                     "(non conta nelle tue spese) e risulta come soldi che ti deve. Quando ti restituisce i soldi, "
                     "apri l'accredito e scegli «È un rimborso»: il saldo si aggiorna e l'accredito non conta come "
                     "entrata."))
