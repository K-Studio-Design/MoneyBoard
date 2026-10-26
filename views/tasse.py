"""Tasse USA (alpha): stima delle tasse sugli stipendi per chi risiede negli Stati Uniti.
Si attiva dal Profilo → Funzioni in prova. Calcoli in core/tax_us.py, parametri in core/tax_us_data.py."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import db, fx, goals, i18n, payslip, tax_invest, tax_us
from core import tax_us_data as D
from core.i18n import t
from views import nav, style, ui

STATUS_LABELS = {"single": "Single (non sposato)", "mfj": "Sposati, dichiarazione congiunta",
                 "mfs": "Sposati, dichiarazioni separate", "hoh": "Capofamiglia (Head of household)"}
VER = "_tax_rows_ver"
GOAL_COLOR = "#F5A524"


def _usd(x: float) -> str:
    return ui.money(x, "USD")


def _d(x) -> str:
    return f"{pd.Timestamp(x):{i18n.strf()}}"


def _state_label(code: str) -> str:
    return f"{D.all_states().get(code, code)} ({code})"


def _save(cfg: dict) -> None:
    tax_us.save_cfg(cfg)


def render():
    style.header(t("Tasse USA"), t("Stima delle tasse sugli stipendi per chi risiede negli Stati Uniti"))
    st.warning(t("**Funzione in prova (alpha).** Il calcolo è una stima e può contenere errori: non sostituisce un "
                 "commercialista o un software fiscale. Usalo per sapere quanto mettere da parte e controlla sempre "
                 "i numeri prima di decidere."), icon=":material/science:")
    cfg = tax_us.load_cfg()
    tx = db.transactions_df()
    today = date.today()

    flash = st.session_state.pop("tax_flash", None)
    if flash:
        st.success(ui.esc(flash), icon=":material/check_circle:")

    # ---------------------------------------------------------------- impostazioni
    with style.card("tax_settings"):
        st.subheader(t("Impostazioni"))
        cats_all = tax_us.salary_categories(tx) if not tx.empty else [tax_us.SALARY_CATEGORY]
        cats_sel = [c for c in cfg["categories"] if c in cats_all] or [tax_us.SALARY_CATEGORY]
        years = set()
        if not tx.empty:
            years = set(tx.loc[tx["category"].isin(cats_sel) & (tx["amount"] > 0), "date"].dt.year.dropna().astype(int))
        years = sorted(years | {today.year}, reverse=True)
        c1, c2 = st.columns(2)
        year = c1.selectbox(t("Anno fiscale"), years, key="tax_year")
        status = c2.selectbox(t("Stato civile ai fini fiscali"), list(D.FILING), index=D.FILING.index(cfg["status"]),
                              format_func=lambda s: t(STATUS_LABELS[s]), key="tax_status",
                              help=t("Come presenterai la dichiarazione federale. Con la dichiarazione congiunta "
                                     "vengono usati gli scaglioni per le coppie: in quel caso considera anche gli "
                                     "stipendi del coniuge, se sono nell'app."))
        cats = st.multiselect(t("Categorie che contano come stipendio"), cats_all, default=cats_sel, key="tax_cats",
                              format_func=ui.cat,
                              help=t("Di solito solo «Stipendio». Le tasse vengono calcolate solo su queste entrate."))
        c1, c2, c3 = st.columns(3)
        margin = c1.number_input(t("Margine di sicurezza (%)"), 0.0, 100.0, float(cfg["margin"]), 1.0,
                                 format="%.0f", key="tax_margin",
                                 help=t("Percentuale aggiunta all'importo calcolato, per stare tranquillo di non "
                                        "trovarti a corto quando paghi le tasse."))
        paid = c2.number_input(t("Già pagate o trattenute (USD)"), 0.0, None,
                               float(cfg["paid"].get(str(year), 0.0)), 100.0, format="%.2f", key=f"tax_paid_{year}",
                               help=t("Tasse dell'anno già trattenute in busta paga o già versate (acconti): "
                                      "vengono tolte da quanto resta da mettere da parte."))
        with c3:
            with_fica = st.toggle(t("Includi Social Security e Medicare"), value=bool(cfg["fica"]), key="tax_fica",
                                  help=t("Contributi FICA: 6,2% fino a {base} e 1,45% su tutto lo stipendio (più "
                                         "0,9% oltre la soglia). Li paga chi lavora per un datore di lavoro "
                                         "americano, di solito trattenuti in busta paga. Chi è pagato da un datore "
                                         "estero può esserne esente (per esempio con il certificato di copertura "
                                         "dell'accordo Italia–USA sulla sicurezza sociale).",
                                         base=_usd(D.SS_WAGE_BASE)))
        new = dict(cfg, status=status, categories=cats or [tax_us.SALARY_CATEGORY], margin=float(margin),
                   fica=bool(with_fica))
        new["paid"] = dict(cfg["paid"], **{str(year): float(paid)})
        if new != cfg:
            cfg = new
            _save(cfg)
        if year != D.YEAR:
            st.info(t("Per il {y} vengono usati gli scaglioni e le deduzioni del {d}: i valori reali possono essere "
                      "diversi.", y=year, d=D.YEAR), icon=":material/info:")

    # ---------------------------------------------------------------- residenza
    with style.card("tax_residence"):
        st.subheader(t("Residenza"))
        _residence(cfg, year)
    periods = cfg["periods"]

    # ---------------------------------------------------------------- buste paga
    with style.card("tax_payslips"):
        st.subheader(t("Buste paga"))
        slip_us, slip_social = _payslips(cfg, tx, year)

    # ---------------------------------------------------------------- stipendi
    with style.card("tax_salaries"):
        st.subheader(t("Stipendi del {y}", y=year))
        rows = tax_us.salary_rows(tx, year, cfg) if periods else pd.DataFrame()
        if not periods:
            st.caption(t("Indica prima lo stato di residenza qui sopra."))
            return
        project = False
        if rows.empty:
            st.info(t("Nessuno stipendio nel {y} nelle categorie scelte.", y=year))
        else:
            _start_picker(cfg, rows, year)
            rows = _rows_editor(cfg, tx, rows, year)
        if year == today.year and not rows.empty:
            project = st.toggle(t("Aggiungi gli stipendi previsti fino a fine anno"), value=bool(cfg["project"]),
                                key="tax_project",
                                help=t("Stima l'anno intero: aggiunge uno stipendio al mese fino a dicembre, pari "
                                       "alla mediana degli ultimi tre, nello stato in cui risiedi oggi. Utile per "
                                       "mettere da parte già adesso la quota giusta."))
            if project != cfg["project"]:
                cfg["project"] = project
                _save(cfg)
        proj = _projection(cfg, rows, year, periods, today) if project else []

    # ---------------------------------------------------------------- investimenti (moduli 1099)
    with style.card("tax_invest"):
        st.subheader(t("Redditi da investimenti (moduli 1099)"))
        inv = _investments(cfg, year)

    used = rows[rows["inc"].astype(bool) & rows["usd"].notna()] if not rows.empty else rows
    calc_rows = [{"usd": float(r.usd), "state": r.state} for r in used.itertuples()]
    calc_rows += [{"usd": p["usd"], "state": p["state"]} for p in proj]
    if not calc_rows and not inv:
        st.info(t("Nessuno stipendio incluso nel calcolo."))
        return
    res = tax_us.compute(calc_rows, cfg["status"], periods, cfg["fica"], inv, year)
    inv_paid = float(inv.get("fed_withheld", 0.0)) if inv else 0.0
    paid_all = float(cfg["paid"].get(str(year), 0.0)) + slip_us + inv_paid   # a mano + buste paga + moduli 1099
    gross, remaining = tax_us.with_margin(res["total"], cfg["margin"], paid_all)

    # ---------------------------------------------------------------- risultato
    with style.card("tax_result"):
        st.subheader(t("Stima delle tasse {y}", y=year))
        n_proj = len(proj)
        note_w = (t("1 stipendio") if len(used) == 1 else t("{n} stipendi", n=len(used))) + (
            t(" + {n} previsti", n=n_proj) if n_proj else "")
        fed = res["federal"]
        st_names = ", ".join(s["code"] for s in res["states"])
        if inv:
            first = (t("Redditi considerati"), _usd(res["wages"] + res["inv_income"]),
                     t("stipendi {w} + investimenti {i}", w=_usd(res["wages"]), i=_usd(res["inv_income"])))
        else:
            first = (t("Stipendi considerati"), _usd(res["wages"]), note_w)
        fed_note = t("aliquota marginale {r}%", r=ui.fmt_num(fed["marginal"], 0))
        if fed.get("niit"):
            fed_note += t(", di cui {v} NIIT", v=_usd(fed["niit"]))
        style.kpis([
            first,
            (t("Imposta federale"), _usd(fed["tax"]), fed_note),
            (t("Imposta statale e locale"), _usd(res["state_tax"] + res["local_tax"]), st_names),
            (t("Social Security e Medicare"), _usd(res["fica"]["total"]) if cfg["fica"] else "–",
             "" if cfg["fica"] else t("non incluse")),
            (t("Totale stimato"), _usd(res["total"]),
             t("{p}% dei redditi", p=ui.fmt_num(res["effective"], 1)) if inv else
             t("{p}% degli stipendi", p=ui.fmt_num(res["effective"], 1))),
            (t("Da mettere da parte"), _usd(remaining),
             t("con margine del {m}%: {g}", m=ui.fmt_num(cfg["margin"], 0), g=_usd(gross))
             + (t(", meno {p} già pagati", p=_usd(paid_all)) if paid_all else ""),
             "neg" if remaining > 0 else "pos"),
        ], cols=3)
        if cfg["fica"] and slip_social > 0:
            st.info(t("Le buste paga dell'anno hanno contributi INPS italiani. Se hai il certificato di distacco "
                      "(accordo Italia–USA sulla sicurezza sociale) di solito non si pagano anche Social Security e "
                      "Medicare: in quel caso togli l'opzione nelle impostazioni qui sopra."), icon=":material/info:")
        base = db.base_currency()
        rate = _usd_to_base(tx)
        if base != "USD" and rate:
            st.caption(ui.esc(t("In {ccy}: circa {v} da mettere da parte, cioè {u} margine compreso convertiti al "
                                "cambio di oggi (1 $ = {r}).", ccy=base, v=ui.money(remaining * rate, base),
                                u=_usd(remaining), r=ui.money(rate, base, 4))))
        with_inv = any(abs(s.get("inv", 0.0)) > 0.004 for s in res["states"])
        srows = []
        for s in res["states"]:
            row = {t("Stato USA"): _state_label(s["code"]), t("Stipendi nello stato"): s["wages"]}
            if with_inv:
                row[t("Investimenti attribuiti")] = s.get("inv", 0.0)
            row.update({t("Quota del reddito"): s["share"] * 100, t("Imposta statale"): s["tax"],
                        t("Imposta locale"): s["local"]})
            srows.append(row)
        style.table(pd.DataFrame(srows), fmt={t("Stipendi nello stato"): ("money", "USD"),
                                              t("Investimenti attribuiti"): ("money", "USD"),
                                              t("Quota del reddito"): "bar", t("Imposta statale"): ("money", "USD"),
                                              t("Imposta locale"): ("money", "USD")}, neg=(t("Investimenti attribuiti"),))
        if with_inv:
            st.caption(t("I redditi da investimenti sono attribuiti agli stati in proporzione ai giorni di residenza "
                         "nell'anno."))
        if any(s["notax"] for s in res["states"]):
            st.caption(t("Gli stati senza imposta sul reddito da lavoro risultano a zero."))
        _federal_detail(res)
        _goal_box(year, remaining, rate, tx)
    _notes()


# ---------------------------------------------------------------- residenza
def _residence(cfg: dict, year: int) -> None:
    periods = tax_us.sorted_periods(cfg["periods"])
    if not periods:
        st.info(t("Questa funzione vale solo per chi risiede negli Stati Uniti. Indica lo stato in cui risiedi per "
                  "iniziare."), icon=":material/home:")
    for i, p in enumerate(periods):
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        when = t("Dal {d}", d=_d(p["from"])) if i else t("Dal {d} (e prima)", d=_d(p["from"]))
        loc = float(p.get("local") or 0)
        extra = t(" · imposta locale {r}%", r=ui.fmt_num(loc, 2)) if loc else ""
        c1.markdown(f"**{ui.esc(_state_label(p['state']))}** · {ui.esc(when)}{ui.esc(extra)}")
        if c2.button("", icon=":material/delete:", key=f"tax_del_{p['from']}_{p['state']}",
                     help=t("Togli questo periodo")):
            cfg["periods"] = [q for q in cfg["periods"] if (q["from"], q["state"]) != (p["from"], p["state"])]
            _save(cfg)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.rerun()
    codes = list(D.all_states())
    with st.form("tax_add_period", clear_on_submit=True, border=False):
        st.caption(t("Ti sei trasferito in un altro stato? Aggiungi la data del trasloco e il nuovo stato: gli "
                     "stipendi da quel giorno vengono assegnati al nuovo stato.") if periods else
                   t("Lo stato vale per tutti gli stipendi; se poi ti trasferisci aggiungerai la data del trasloco."))
        c1, c2, c3 = st.columns([2, 3, 2])
        start = c1.date_input(t("Dal"), value=date(year, 1, 1) if not periods else date.today(),
                              format=i18n.date_fmt(), key="tax_new_from")
        code = c2.selectbox(t("Stato di residenza"), codes, format_func=_state_label, key="tax_new_state",
                            index=codes.index("IL") if "IL" in codes else 0)
        local = c3.number_input(t("Imposta locale (%)"), 0.0, 10.0, 0.0, 0.1, format="%.2f", key="tax_new_local",
                                help=t("Imposta della città o della contea, se c'è (per esempio New York City, le "
                                       "contee del Maryland e dell'Indiana, molte città dell'Ohio e della "
                                       "Pennsylvania). Lascia 0 se non c'è."))
        if st.form_submit_button(t("Aggiungi trasloco") if periods else t("Salva residenza"), type="primary",
                                 icon=":material/add_home:"):
            iso = start.isoformat()
            cfg["periods"] = [q for q in cfg["periods"] if q["from"] != iso] + [
                {"from": iso, "state": code, "local": float(local)}]
            _save(cfg)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.rerun()


# ---------------------------------------------------------------- buste paga
SLIP_NEW = "_tax_slip_new"      # busta appena letta, da controllare prima di salvarla
SLIP_SEEN = "_tax_slip_seen"    # file già letto (per non rileggerlo a ogni ricarica della pagina)
SLIP_ERR = {
    "PDF_LIB": "Per leggere i PDF serve un componente nuovo: chiudi l'app e riaprila con avvia_app.bat, che lo "
               "installa da solo. Intanto puoi inserire la busta a mano qui sotto.",
    "PDF_SCAN": "Il PDF è una scansione (un'immagine): non riesco a leggerne il testo. Inserisci la busta a mano qui "
                "sotto.",
    "PDF_FORMAT": "Non riconosco il formato di questa busta paga: per ora leggo in automatico le buste Zucchetti. "
                  "Inserisci la busta a mano qui sotto.",
    "PDF_PERIOD": "Non trovo il mese della busta paga. Inserisci la busta a mano qui sotto.",
    "PDF_READ": "Il file non sembra un PDF valido.",
}


def _period_label(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    return f"{i18n.month(m)} {y}"


def _tx_label(tx: pd.DataFrame, tx_id) -> str:
    if tx_id is None or pd.isna(tx_id):
        return t("Nessun accredito")
    r = tx[tx["id"] == int(tx_id)]
    if r.empty:
        return t("Nessun accredito")
    r = r.iloc[0]
    return f"{_d(r['date'])} · {ui.money(float(r['amount']), r['currency'])} · {str(r['description'])[:40]}"


def _payslips(cfg: dict, tx: pd.DataFrame, year: int) -> tuple[float, float]:
    """Caricamento, controllo e archivio delle buste paga. Ritorna (tasse USA trattenute, contributi italiani)
    delle buste dell'anno."""
    st.caption(t("Facoltativo. Con la busta paga il calcolo parte dal lordo tassabile del mese invece che "
                 "dall'accredito in banca: conta i compensi e i benefit tassabili anche se non sono arrivati sul "
                 "conto, e lascia fuori gli importi figurativi e i rimborsi. Ogni voce ha una proposta che puoi "
                 "cambiare; la scelta viene ricordata per le buste dei mesi dopo. I file restano sul tuo computer."))
    use = st.toggle(t("Usa le buste paga per il calcolo"), value=bool(cfg.get("use_payslips", True)),
                    key="tax_use_slips",
                    help=t("Spento: il calcolo usa solo gli accrediti in banca, anche per i mesi con la busta paga."))
    if use != cfg.get("use_payslips", True):
        cfg["use_payslips"] = use
        _save(cfg)
        st.session_state[VER] = st.session_state.get(VER, 0) + 1
    df = payslip.all_df()
    ver = st.session_state.get(VER, 0)
    up = st.file_uploader(t("Carica una busta paga (PDF)"), type=["pdf"], key=f"tax_slip_up_{ver}")
    if up is not None:
        sig = (up.name, up.size)
        if st.session_state.get(SLIP_SEEN) != sig:
            st.session_state[SLIP_SEEN] = sig
            try:
                p = payslip.parse_pdf(up.getvalue(), up.name)
                taken = {int(x) for x in df["tx_id"].dropna()} if not df.empty else set()
                st.session_state[SLIP_NEW] = {"p": p, "tx": payslip.match_tx(tx, p.period, p.net, p.currency, taken),
                                              "id": None}
                st.session_state.pop("tax_slip_err", None)
            except payslip.PayslipError as e:
                st.session_state["tax_slip_err"] = str(e)
                st.session_state.pop(SLIP_NEW, None)
    err = st.session_state.get("tax_slip_err")
    if err:
        st.warning(t(SLIP_ERR.get(err, SLIP_ERR["PDF_FORMAT"])), icon=":material/description:")
    new = st.session_state.get(SLIP_NEW)
    if new:
        _review(new, tx, df)
    _manual_form(tx, df)
    if not df.empty:
        _saved_list(df, tx)
    yr = df[df["period"].str.startswith(str(year))] if not df.empty else df
    if yr.empty:
        return 0.0, 0.0
    tax_it = float(yr["tax_it"].fillna(0).sum())
    if tax_it:
        st.caption(t("Imposte italiane trattenute nelle buste del {y}: {v}. Possono dare diritto al credito per le "
                     "imposte pagate all'estero: non sono tolte dal calcolo.", y=year,
                     v=ui.money(tax_it, str(yr.iloc[0]["currency"]))))
    return float(yr["tax_us"].fillna(0).sum()), float(yr["social_it"].fillna(0).sum())


def _slip_amount(v, fig: bool, ccy: str) -> str:
    """Importo di una voce come nella busta: vuoto se non c'è, tra parentesi se figurativo."""
    if v is None or pd.isna(v):
        return ""
    s = ui.money(float(v), ccy)
    return f"({s})" if fig else s


def _review(new: dict, tx: pd.DataFrame, df: pd.DataFrame) -> None:
    """Controllo di una busta letta dal PDF (nuova o già salvata): classi delle voci, accredito abbinato, salva."""
    p: payslip.Payslip = new["p"]
    labels = {k: t(v[0]) for k, v in payslip.CLASSES.items()}
    back = {v: k for k, v in labels.items()}
    with st.container(border=True, key="tax_slip_review"):
        st.markdown("**" + ui.esc(t("Busta paga di {m}", m=_period_label(p.period))
                                  + (f" · {p.employer}" if p.employer else "")) + "**")
        for w in p.warnings:
            kind, got, want = w.split(":")
            st.warning(t("Le voci lette ({a}) non tornano con il totale {k} della busta ({b}): controlla la tabella.",
                         a=ui.money(float(got), p.currency), b=ui.money(float(want), p.currency),
                         k=t("delle competenze") if kind == "COMP" else t("delle trattenute")),
                       icon=":material/warning:")
        C_CODE, C_DESC, C_DED, C_COMP, C_FIG, C_CLS = (t("Codice"), t("Voce"), t("Trattenute"), t("Competenze"),
                                                      t("Figurativo"), t("Per le tasse USA"))
        items = p.items
        ed_df = pd.DataFrame({C_CODE: [i.code for i in items], C_DESC: [i.desc for i in items],
                              C_DED: [_slip_amount(i.ded, i.fig, p.currency) for i in items],
                              C_COMP: [_slip_amount(i.comp, i.fig, p.currency) for i in items],
                              C_FIG: [bool(i.fig) for i in items], C_CLS: [labels[i.cls] for i in items]})
        ed = st.data_editor(ed_df, key=f"tax_slip_items_{new.get('id')}_{st.session_state.get(VER, 0)}",
                            hide_index=True, width="stretch", num_rows="fixed",
                            disabled=[C_CODE, C_DESC, C_DED, C_COMP, C_FIG],
                            column_config={
                                C_CODE: st.column_config.TextColumn(C_CODE, width="small"),
                                C_DESC: st.column_config.TextColumn(C_DESC, width="medium"),
                                C_DED: st.column_config.TextColumn(C_DED),
                                C_COMP: st.column_config.TextColumn(C_COMP),
                                C_FIG: st.column_config.CheckboxColumn(C_FIG, width="small"),
                                C_CLS: st.column_config.SelectboxColumn(C_CLS, options=list(labels.values()),
                                                                        required=True, width="medium")})
        for i, it in enumerate(items):
            it.cls = back.get(ed.iloc[i][C_CLS], it.cls)
        cur = p.currency
        style.kpis([(t("Netto del mese"), ui.money(p.net, cur) if p.net is not None else "–", ""),
                    (t("Lordo tassabile USA"), ui.money(p.taxable(), cur), t("compensi e benefit tassabili")),
                    (t("Imposte italiane"), ui.money(p.tax_it(), cur), t("trattenute, meno i rimborsi")),
                    (t("Contributi italiani"), ui.money(p.social_it(), cur), "INPS")], cols=4)
        taken = {int(x) for x in df["tx_id"].dropna()} if not df.empty else set()
        if new.get("tx") is not None:
            taken.discard(int(new["tx"]))
        y, m = (int(x) for x in p.period.split("-"))
        lo = pd.Timestamp(date(y, m, 1)) - pd.Timedelta(days=40)
        hi = pd.Timestamp(date(y, m, 1)) + pd.Timedelta(days=75)
        cand = tx[(tx["amount"] > 0) & (tx["date"] >= lo) & (tx["date"] <= hi) & ~tx["id"].isin(list(taken))] \
            if not tx.empty else tx
        opts = [None] + [int(i) for i in cand.sort_values("date")["id"]]
        cur_tx = new.get("tx") if new.get("tx") in opts else None
        pick = st.selectbox(t("Accredito in banca di questa busta"), opts, index=opts.index(cur_tx),
                            format_func=lambda i: _tx_label(tx, i), key=f"tax_slip_tx_{new.get('id')}",
                            help=t("Lo stipendio arrivato sul conto per questa busta. Nel calcolo delle tasse, al "
                                   "posto dell'accredito viene usato il lordo tassabile della busta."))
        if pick is None:
            st.caption(t("Senza accredito abbinato la busta resta in archivio ma non entra nel calcolo."))
        c1, c2, c3 = st.columns([2, 2, 3])
        if c1.button(t("Salva busta paga") if new.get("id") is None else t("Salva le modifiche"), type="primary",
                     icon=":material/save:", key=f"tax_slip_save_{new.get('id')}"):
            pid = payslip.save(p, pick, new.get("id"))
            payslip.remember(p.items)
            cfg = tax_us.load_cfg()
            if pick is not None:   # la busta prende il posto di un importo corretto a mano sull'accredito
                o = cfg["rows"].get(str(pick), {})
                o.pop("usd", None)
                cfg["rows"] = {k: v for k, v in {**cfg["rows"], str(pick): o}.items() if v}
                tax_us.save_cfg(cfg)
            for k in (SLIP_NEW, SLIP_SEEN, "tax_slip_edit"):
                st.session_state.pop(k, None)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.session_state["tax_flash"] = t("Busta paga di {m} salvata (n. {n}).", m=_period_label(p.period), n=pid)
            st.rerun()
        if c2.button(t("Annulla"), key=f"tax_slip_cancel_{new.get('id')}", icon=":material/close:"):
            for k in (SLIP_NEW, SLIP_SEEN, "tax_slip_edit"):
                st.session_state.pop(k, None)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.rerun()


def _manual_form(tx: pd.DataFrame, df: pd.DataFrame) -> None:
    with st.expander(t("Inserisci una busta paga a mano"), icon=":material/edit_note:"):
        st.caption(t("Per le buste che non vengono lette in automatico, o per le buste americane: scrivi i totali del "
                     "mese."))
        with st.form("tax_slip_manual", clear_on_submit=True, border=False):
            today = date.today()
            c1, c2, c3 = st.columns(3)
            month = c1.selectbox(t("Mese"), list(range(1, 13)), index=today.month - 1, format_func=i18n.month,
                                 key="tax_man_m")
            year = c2.number_input(t("Anno"), 2000, 2100, today.year, 1, key="tax_man_y")
            ccys = list(dict.fromkeys([db.base_currency(), "USD", "EUR"]))
            ccy = c3.selectbox(t("Valuta della busta"), ccys, key="tax_man_ccy")
            c1, c2 = st.columns(2)
            net = c1.number_input(t("Netto del mese"), 0.0, None, 0.0, 10.0, format="%.2f", key="tax_man_net")
            taxable = c2.number_input(t("Lordo tassabile"), 0.0, None, 0.0, 10.0, format="%.2f", key="tax_man_tax",
                                      help=t("Compensi e benefit tassabili prima delle trattenute (nelle buste "
                                             "americane: «Gross pay» o «Federal taxable wages»)."))
            c1, c2 = st.columns(2)
            tax_it = c1.number_input(t("Imposte italiane trattenute"), 0.0, None, 0.0, 10.0, format="%.2f",
                                     key="tax_man_it")
            tax_us_ = c2.number_input(t("Tasse USA trattenute (USD)"), 0.0, None, 0.0, 10.0, format="%.2f",
                                      key="tax_man_us",
                                      help=t("Federal, state e local income tax trattenute nella busta americana: "
                                             "vengono tolte da quanto resta da mettere da parte."))
            if st.form_submit_button(t("Salva busta paga"), icon=":material/save:"):
                if taxable <= 0:
                    st.error(t("Scrivi almeno il lordo tassabile."))
                else:
                    period = f"{int(year):04d}-{int(month):02d}"
                    p = payslip.manual(period, ccy, float(net) or None, float(taxable), float(tax_it),
                                       float(tax_us_))
                    taken = {int(x) for x in df["tx_id"].dropna()} if not df.empty else set()
                    match = payslip.match_tx(tx, period, p.net, ccy, taken)
                    pid = payslip.save(p, match, tax_us=float(tax_us_))
                    st.session_state[VER] = st.session_state.get(VER, 0) + 1
                    st.session_state["tax_flash"] = (
                        t("Busta paga di {m} salvata (n. {n}).", m=_period_label(period), n=pid)
                        + ("" if match else " " + t("Nessun accredito con lo stesso netto: abbinala tu dall'elenco "
                                                    "delle buste.")))
                    st.rerun()


def _saved_list(df: pd.DataFrame, tx: pd.DataFrame) -> None:
    st.markdown("**" + t("Buste paga salvate") + "**")
    rows = [{t("Mese"): _period_label(r.period), t("Netto"): ui.money(r.net, r.currency) if r.net is not None
             and not pd.isna(r.net) else "–",
             t("Lordo tassabile USA"): ui.money(float(r.taxable or 0), r.currency),
             t("Imposte italiane"): ui.money(float(r.tax_it or 0), r.currency),
             t("Accredito abbinato"): _tx_label(tx, r.tx_id)} for r in df.itertuples()]
    style.table(pd.DataFrame(rows), fmt={k: "text" for k in rows[0]})
    ids = [int(i) for i in df["id"]]
    by_id = {int(r.id): r for r in df.itertuples()}
    c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
    pick = c1.selectbox(t("Busta da modificare"), ids, format_func=lambda i: _period_label(by_id[i].period)
                        + f" · {ui.money(float(by_id[i].taxable or 0), by_id[i].currency)}", key="tax_slip_pick")
    if c2.button(t("Modifica"), icon=":material/edit:", key="tax_slip_edit_btn", width="stretch"):
        p, row = payslip.load(pick)
        if row["source"] == "manuale":
            st.session_state["tax_flash"] = t("Le buste inserite a mano si correggono eliminandole e inserendole di "
                                              "nuovo.")
        else:
            tx_id = None if row["tx_id"] is None or pd.isna(row["tx_id"]) else int(row["tx_id"])
            st.session_state[SLIP_NEW] = {"p": p, "tx": tx_id, "id": int(pick)}
        st.rerun()
    if c3.button(t("Elimina"), icon=":material/delete:", key="tax_slip_del", width="stretch"):
        payslip.delete(pick)
        st.session_state.pop(SLIP_NEW, None)
        st.session_state[VER] = st.session_state.get(VER, 0) + 1
        st.session_state["tax_flash"] = t("Busta paga eliminata.")
        st.rerun()


# ---------------------------------------------------------------- investimenti (moduli 1099)
INV_NEW = "_tax_inv_new"     # file del broker appena letto, da controllare prima di salvarlo
INV_SEEN = "_tax_inv_seen"
INV_ERR = {
    "TXF_FORMAT": "Il file non sembra un TXF valido (deve iniziare con «V042»).",
    "TXF_EMPTY": "Nel file TXF non ci sono vendite, dividendi o interessi.",
    "CSV_COLUMNS": "Nel CSV non trovo le colonne delle vendite (servono almeno incasso/«Proceeds» e costo/«Cost "
                   "basis» o guadagno/«Gain/Loss»).",
    "CSV_EMPTY": "Nel CSV non ci sono vendite leggibili.",
}
INV_KIND_LABELS = {"1099-B": "1099-B · vendite di titoli", "1099-DIV": "1099-DIV · dividendi",
                   "1099-INT": "1099-INT · interessi"}


def _investments(cfg: dict, year: int) -> dict | None:
    """Moduli 1099 dell'anno: caricamento (TXF o CSV del broker, oppure a mano), elenco e totali. Ritorna i totali
    da usare nel calcolo (None se non ce ne sono o se l'opzione è spenta)."""
    st.caption(t("Facoltativo, per chi ha un conto titoli presso un broker americano: le vendite di azioni (1099-B), "
                 "i dividendi (1099-DIV) e gli interessi (1099-INT) si aggiungono agli stipendi. Carica il file "
                 "«TXF» (l'esportazione per TurboTax o altri programmi fiscali che quasi tutti i broker offrono) "
                 "oppure il CSV delle vendite realizzate; in alternativa scrivi a mano i riquadri del modulo."))
    use = st.toggle(t("Includi i redditi da investimenti nel calcolo"), value=bool(cfg.get("use_invest", True)),
                    key="tax_use_inv")
    if use != cfg.get("use_invest", True):
        cfg["use_invest"] = use
        _save(cfg)
    ver = st.session_state.get(VER, 0)
    up = st.file_uploader(t("Carica un file del broker (TXF o CSV delle vendite)"), type=["txf", "csv", "txt"],
                          key=f"tax_inv_up_{ver}")
    if up is not None:
        sig = (up.name, up.size)
        if st.session_state.get(INV_SEEN) != sig:
            st.session_state[INV_SEEN] = sig
            try:
                parsed = tax_invest.parse_file(up.getvalue(), up.name)
                st.session_state[INV_NEW] = {"p": parsed, "file": up.name}
                st.session_state.pop("tax_inv_err", None)
            except tax_invest.InvestError as e:
                st.session_state["tax_inv_err"] = str(e)
                st.session_state.pop(INV_NEW, None)
            except Exception:
                st.session_state["tax_inv_err"] = "CSV_COLUMNS"
                st.session_state.pop(INV_NEW, None)
    err = st.session_state.get("tax_inv_err")
    if err:
        st.warning(t(INV_ERR.get(err, INV_ERR["CSV_COLUMNS"])), icon=":material/description:")
    new = st.session_state.get(INV_NEW)
    if new:
        _inv_review(new, year)
    _inv_manual(year)
    docs = tax_invest.docs(year)
    if not docs:
        return None
    _inv_list(docs)
    tot = tax_invest.totals(docs)
    style.kpis([
        (t("Interessi"), _usd(tot["interest"]),
         t("di cui {v} da titoli del Tesoro USA", v=_usd(tot["us_gov"])) if tot["us_gov"] else ""),
        (t("Dividendi"), _usd(tot["ordinary_div"]), t("di cui qualificati {v}", v=_usd(tot["qualified_div"]))),
        (t("Plus/minusvalenze a breve"), _usd(tot["st"]), t("titoli tenuti fino a un anno")),
        (t("Plus/minusvalenze a lungo"), _usd(tot["lt"] + tot["cg_dist"]),
         t("comprese distribuzioni {v}", v=_usd(tot["cg_dist"])) if tot["cg_dist"] else t("titoli tenuti più di un anno")),
        (t("Ritenute federali"), _usd(tot["fed_withheld"]), t("tolte da quanto resta da pagare")),
        (t("Imposte estere"), _usd(tot["foreign_tax"]), t("credito d'imposta (semplificato)")),
    ], cols=3)
    if not use or not (tax_invest.has_income(tot) or tot["fed_withheld"] or tot["foreign_tax"]):
        return None
    return tot


def _inv_review(new: dict, year: int) -> None:
    p, fname = new["p"], new["file"]
    lots, other = tax_invest.lots_year(p["lots"], year)
    with st.container(border=True, key="tax_inv_review"):
        st.markdown("**" + ui.esc(t("File «{f}»", f=fname)) + "**")
        st_gain = sum(tax_invest.lot_gain(x) for x in lots if x["term"] == "S")
        lt_gain = sum(tax_invest.lot_gain(x) for x in lots if x["term"] == "L")
        items = [(t("Vendite del {y}", y=year), str(len(lots)),
                  t("breve {a} · lungo {b}", a=_usd(st_gain), b=_usd(lt_gain)))]
        if p["div"]:
            items.append((t("Dividendi"), _usd(p["div"].get("ordinary", 0.0)),
                          t("di cui qualificati {v}", v=_usd(p["div"].get("qualified", 0.0)))))
        if p["int"]:
            items.append((t("Interessi"), _usd(p["int"].get("interest", 0.0) + p["int"].get("us_gov", 0.0)), ""))
        style.kpis(items, cols=3)
        if other:
            st.caption(t("{n} vendite di altri anni non vengono considerate per il {y}.", n=other, y=year))
        if p.get("skipped"):
            st.caption(t("{n} righe del file senza importi leggibili sono state saltate.", n=p["skipped"]))
        if "TXF_LOT" in p.get("warnings", []):
            st.caption(t("Alcune vendite del file TXF non avevano costo o incasso e sono state saltate."))
        if lots:
            show = pd.DataFrame([{t("Titolo"): x["desc"], t("Acquisto"): x["acquired"], t("Vendita"): x["sold"],
                                  t("Incasso"): x["proceeds"], t("Costo"): x["basis"], t("Wash sale"): x["wash"],
                                  t("Risultato"): tax_invest.lot_gain(x),
                                  t("Durata"): t("lungo") if x["term"] == "L" else t("breve")} for x in lots[:200]])
            style.table(show, fmt={t("Titolo"): "text", t("Acquisto"): "text", t("Vendita"): "text",
                                   t("Incasso"): ("money", "USD"), t("Costo"): ("money", "USD"),
                                   t("Wash sale"): ("money", "USD"), t("Risultato"): ("money", "USD"),
                                   t("Durata"): "text"}, height=320, neg=(t("Risultato"),))
        broker = st.text_input(t("Broker"), value="", key="tax_inv_broker", placeholder=t("es. Schwab, Fidelity…"))
        c1, c2 = st.columns([1, 1])
        if c1.button(t("Salva"), type="primary", icon=":material/save:", key="tax_inv_save",
                     disabled=not (lots or p["div"] or p["int"])):
            src = "txf" if fname.lower().endswith(".txf") or p.get("skipped") is None else "csv"
            if lots:
                tax_invest.save(year, "1099-B", {"lots": lots}, broker, src, fname)
            if p["div"]:
                tax_invest.save(year, "1099-DIV", p["div"], broker, src, fname)
            if p["int"]:
                tax_invest.save(year, "1099-INT", p["int"], broker, src, fname)
            for k in (INV_NEW, INV_SEEN):
                st.session_state.pop(k, None)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.session_state["tax_flash"] = t("Dati del broker salvati per il {y}.", y=year)
            st.rerun()
        if c2.button(t("Annulla"), icon=":material/close:", key="tax_inv_cancel"):
            for k in (INV_NEW, INV_SEEN, "tax_inv_err"):
                st.session_state.pop(k, None)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.rerun()


def _inv_manual(year: int) -> None:
    with st.expander(t("Inserisci un modulo 1099 a mano"), icon=":material/edit_note:"):
        kind = st.selectbox(t("Modulo"), list(tax_invest.KINDS), format_func=lambda k: t(INV_KIND_LABELS[k]),
                            key="tax_inv_kind")
        with st.form(f"tax_inv_form_{kind}", clear_on_submit=True, border=False):
            broker = st.text_input(t("Broker o banca"), key=f"tax_inv_mb_{kind}")

            def money(label, key, help_=None):
                return st.number_input(label, 0.0, None, 0.0, 10.0, format="%.2f", key=f"tax_inv_{kind}_{key}",
                                       help=help_)

            data: dict = {}
            if kind == "1099-INT":
                c1, c2 = st.columns(2)
                with c1:
                    data["interest"] = money(t("Interessi (riquadro 1)"), "interest")
                    data["fed_withheld"] = money(t("Ritenuta federale (riquadro 4)"), "fw")
                    data["tax_exempt"] = money(t("Interessi esenti (riquadro 8)"), "te",
                                               t("Solo informativo: non sono tassati a livello federale."))
                with c2:
                    data["us_gov"] = money(t("Interessi su titoli del Tesoro USA (riquadro 3)"), "usg",
                                           t("Tassati a livello federale, esenti dalle tasse statali."))
                    data["foreign_tax"] = money(t("Imposte estere pagate (riquadro 6)"), "ft")
            elif kind == "1099-DIV":
                c1, c2 = st.columns(2)
                with c1:
                    data["ordinary"] = money(t("Dividendi ordinari totali (riquadro 1a)"), "ord")
                    data["cg_dist"] = money(t("Distribuzioni di plusvalenze (riquadro 2a)"), "cgd",
                                            t("Tassate come plusvalenze a lungo termine."))
                    data["foreign_tax"] = money(t("Imposte estere pagate (riquadro 7)"), "ft")
                with c2:
                    data["qualified"] = money(t("Di cui dividendi qualificati (riquadro 1b)"), "qual",
                                              t("Parte del riquadro 1a tassata con le aliquote ridotte (0/15/20%)."))
                    data["fed_withheld"] = money(t("Ritenuta federale (riquadro 4)"), "fw")
            else:
                st.caption(t("Copia i totali dal riepilogo del 1099-B (di solito una riga per i titoli a breve e una "
                             "per quelli a lungo termine)."))
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**" + t("A breve termine (fino a un anno)") + "**")
                    data["st_proceeds"] = money(t("Incasso (1d)"), "stp")
                    data["st_basis"] = money(t("Costo (1e)"), "stb")
                    data["st_wash"] = money(t("Perdita non deducibile per wash sale (1g)"), "stw")
                with c2:
                    st.markdown("**" + t("A lungo termine (più di un anno)") + "**")
                    data["lt_proceeds"] = money(t("Incasso (1d)"), "ltp")
                    data["lt_basis"] = money(t("Costo (1e)"), "ltb")
                    data["lt_wash"] = money(t("Perdita non deducibile per wash sale (1g)"), "ltw")
                data["fed_withheld"] = money(t("Ritenuta federale (riquadro 4)"), "fw")
            if st.form_submit_button(t("Salva il modulo"), icon=":material/save:"):
                if not any(v for v in data.values() if isinstance(v, (int, float))):
                    st.error(t("Scrivi almeno un importo."))
                elif kind == "1099-DIV" and data["qualified"] > data["ordinary"]:
                    st.error(t("I dividendi qualificati non possono superare i dividendi ordinari totali."))
                else:
                    if kind == "1099-B":
                        fw = data.pop("fed_withheld")
                        data = {"summary": data, "fed_withheld": fw}
                    tax_invest.save(year, kind, data, broker, "manuale")
                    st.session_state[VER] = st.session_state.get(VER, 0) + 1
                    st.session_state["tax_flash"] = t("Modulo {k} salvato per il {y}.", k=kind, y=year)
                    st.rerun()


def _inv_doc_summary(doc: dict) -> str:
    kind = doc["kind"]
    one = tax_invest.totals([doc])
    if kind == "1099-B":
        n = one["n_lots"]
        txt = t("breve {a} · lungo {b}", a=_usd(one["st"]), b=_usd(one["lt"]))
        return (t("{n} vendite", n=n) + " · " + txt) if n else txt
    if kind == "1099-DIV":
        return t("dividendi {a} (qualificati {b})", a=_usd(one["ordinary_div"]), b=_usd(one["qualified_div"]))
    return t("interessi {a}", a=_usd(one["interest"]))


def _inv_list(docs: list[dict]) -> None:
    rows = [{t("Modulo"): d["kind"], t("Broker"): d["broker"] or "–",
             t("Origine"): t("a mano") if d["source"] == "manuale" else (d["file_name"] or d["source"]),
             t("Importi"): _inv_doc_summary(d)} for d in docs]
    style.table(pd.DataFrame(rows), fmt={k: "text" for k in rows[0]})
    by_id = {int(d["id"]): d for d in docs}
    c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
    pick = c1.selectbox(t("Modulo da eliminare"), list(by_id), key="tax_inv_pick",
                        format_func=lambda i: f"{by_id[i]['kind']} · {by_id[i]['broker'] or '–'} · "
                                              f"{_inv_doc_summary(by_id[i])}")
    if c2.button(t("Elimina"), icon=":material/delete:", key="tax_inv_del", width="stretch"):
        tax_invest.delete(pick)
        st.session_state[VER] = st.session_state.get(VER, 0) + 1
        st.session_state["tax_flash"] = t("Modulo eliminato.")
        st.rerun()


# ---------------------------------------------------------------- stipendi
def _start_picker(cfg: dict, rows: pd.DataFrame, year: int) -> None:
    ids = [None] + [int(i) for i in rows["id"]]
    by_id = {int(r.id): r for r in rows.itertuples()}

    def label(i):
        if i is None:
            return t("Dal primo stipendio dell'anno")
        r = by_id[i]
        return f"{_d(r.date)} · {r.desc[:40]} · {ui.money(r.amount, r.ccy)}"

    cur = cfg["start"].get(str(year))
    cur = int(cur) if cur is not None and int(cur) in by_id else None
    pick = st.selectbox(t("Calcola le tasse a partire da questo stipendio"), ids, index=ids.index(cur),
                        format_func=label, key=f"tax_start_{year}",
                        help=t("Per esempio il primo stipendio dopo il trasferimento negli Stati Uniti: quelli "
                               "precedenti non vengono considerati."))
    if pick != cur:
        if pick is None:
            cfg["start"].pop(str(year), None)
        else:
            cfg["start"][str(year)] = int(pick)
        for i in by_id:   # le inclusioni scelte a mano per quest'anno ripartono dalla nuova data
            cfg["rows"].get(str(i), {}).pop("inc", None)
        cfg["rows"] = {k: v for k, v in cfg["rows"].items() if v}
        _save(cfg)
        st.session_state[VER] = st.session_state.get(VER, 0) + 1
        st.rerun()


def _rows_editor(cfg: dict, tx: pd.DataFrame, rows: pd.DataFrame, year: int) -> pd.DataFrame:
    codes = list(D.all_states())
    labels = [_state_label(c) for c in codes]
    to_code = dict(zip(labels, codes))
    C_INC, C_DATE, C_DESC, C_AMT, C_USD, C_STATE = (t("Incluso"), t("Data"), t("Descrizione"), t("Importo"),
                                                    t("Importo in USD"), t("Stato USA"))
    C_SRC = t("Calcolato da")
    df = pd.DataFrame({
        C_INC: rows["inc"].astype(bool).values,
        C_DATE: rows["date"].dt.date.values,
        C_DESC: rows["desc"].values,
        C_AMT: [ui.money(a, c) for a, c in zip(rows["amount"], rows["ccy"])],
        C_USD: rows["usd"].astype(float).round(2).values,
        C_STATE: [_state_label(s) if s else None for s in rows["state"]],
        C_SRC: [t("Busta paga") if s == "payslip" else t("Accredito") for s in rows["src"]],
    }, index=rows["id"].values)
    key = f"tax_rows_{year}_{st.session_state.get(VER, 0)}"
    st.caption(t("Togli la spunta agli stipendi da non considerare, correggi l'importo in dollari (per esempio con "
                 "il lordo della busta paga) o assegna uno stipendio a un altro stato."))
    ed = st.data_editor(
        df, key=key, hide_index=True, width="stretch", num_rows="fixed",
        disabled=[C_DATE, C_DESC, C_AMT, C_SRC],
        column_config={
            C_INC: st.column_config.CheckboxColumn(C_INC, width="small"),
            C_DATE: st.column_config.DateColumn(C_DATE, format=i18n.date_fmt(), width="small"),
            C_DESC: st.column_config.TextColumn(C_DESC, width="medium"),
            C_AMT: st.column_config.TextColumn(C_AMT, width="small"),
            C_USD: st.column_config.NumberColumn(C_USD, min_value=0.0, format="dollar", step=0.01, width="small"),
            C_STATE: st.column_config.SelectboxColumn(C_STATE, options=labels, required=True, width="medium"),
            C_SRC: st.column_config.TextColumn(C_SRC, width="small",
                                               help=t("Busta paga: lordo tassabile della busta abbinata. Accredito: "
                                                      "l'importo arrivato sul conto.")),
        })
    if not ed.equals(df):
        defaults = tax_us.salary_rows(tx, year, dict(cfg, rows={})).set_index("id")
        changed = False
        for rid in df.index:
            o = dict(cfg["rows"].get(str(rid), {}))
            new_inc, new_usd, new_state = bool(ed.at[rid, C_INC]), ed.at[rid, C_USD], to_code.get(ed.at[rid, C_STATE])
            dflt = defaults.loc[rid]
            if new_inc != bool(df.at[rid, C_INC]):
                o["inc"] = new_inc
                if new_inc == bool(dflt["inc"]):
                    o.pop("inc")
            if not (pd.isna(new_usd) and pd.isna(df.at[rid, C_USD])) and new_usd != df.at[rid, C_USD]:
                if pd.isna(new_usd) or (dflt["auto_usd"] is not None and abs(float(new_usd) - float(dflt["auto_usd"])) < 0.005):
                    o.pop("usd", None)
                else:
                    o["usd"] = round(float(new_usd), 2)
            if new_state and new_state != to_code.get(df.at[rid, C_STATE]):
                o["state"] = new_state
                if new_state == dflt["state"]:
                    o.pop("state")
            if o != cfg["rows"].get(str(rid), {}):
                changed = True
                if o:
                    cfg["rows"][str(rid)] = o
                else:
                    cfg["rows"].pop(str(rid), None)
        if changed:
            _save(cfg)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.rerun()
    if (~rows["conv_ok"]).any():
        st.warning(t("Per alcuni stipendi non è stato possibile ottenere il cambio in dollari: scrivi tu l'importo "
                     "in USD, altrimenti restano fuori dal calcolo."), icon=":material/currency_exchange:")
    mine = [str(i) for i in rows["id"]]
    if any(k in cfg["rows"] for k in mine):
        if st.button(t("Annulla le modifiche fatte a mano"), key=f"tax_reset_{year}", type="tertiary",
                     icon=":material/undo:"):
            cfg["rows"] = {k: v for k, v in cfg["rows"].items() if k not in mine}
            _save(cfg)
            st.session_state[VER] = st.session_state.get(VER, 0) + 1
            st.rerun()
    other = rows["ccy"].ne("USD").any()
    if other:
        st.caption(t("Gli stipendi in altre valute sono convertiti in dollari al cambio BCE del giorno di accredito."))
    return rows


def _projection(cfg: dict, rows: pd.DataFrame, year: int, periods: list[dict], today: date) -> list[dict]:
    """Importo mensile degli stipendi previsti (proposto: mediana degli ultimi tre, modificabile) e righe previste."""
    dflt = tax_us.projection_default(rows)
    if dflt is None:
        return []
    saved = cfg["proj_amount"].get(str(year))
    cur = float(saved) if isinstance(saved, (int, float)) else dflt
    amt = st.number_input(t("Stipendio mensile previsto (USD)"), 0.0, None, round(cur, 2), 100.0, format="%.2f",
                          key=f"tax_proj_amt_{year}_{round(dflt, 2)}",   # nuova proposta → campo nuovo
                          help=ui.esc(t("Proposto: la mediana degli ultimi stipendi considerati ({v}). Correggilo se "
                                        "gli ultimi stipendi erano più alti o più bassi del solito (bonus, "
                                        "arretrati, tredicesima…).", v=_usd(dflt))))
    new = None if abs(amt - dflt) < 0.005 else round(float(amt), 2)
    if new != (round(float(saved), 2) if isinstance(saved, (int, float)) else None):
        if new is None:
            cfg["proj_amount"].pop(str(year), None)
        else:
            cfg["proj_amount"][str(year)] = new
        _save(cfg)
    proj = tax_us.projected_rows(rows, year, periods, today, amt)
    if proj:
        st.caption(ui.esc(t("Previsti {n} stipendi da {v}, da {m} a dicembre.", n=len(proj), v=_usd(amt),
                            m=i18n.month(proj[0]["date"].month))))
    return proj


# ---------------------------------------------------------------- dettagli
def _federal_detail(res: dict) -> None:
    fed = res["federal"]
    with st.expander(t("Come si arriva all'imposta federale"), icon=":material/calculate:"):
        if res.get("inv_income"):
            st.markdown(ui.esc(t("Stipendi {w} + redditi da investimenti {i} − deduzione standard {sd} = "
                                 "**imponibile {x}**.", w=_usd(res["wages"]), i=_usd(res["inv_income"]),
                                 sd=_usd(fed["sd"]), x=_usd(fed["taxable"]))))
        else:
            st.markdown(ui.esc(t("Stipendi {w} − deduzione standard {sd} = **imponibile {x}**.", w=_usd(res["wages"]),
                                 sd=_usd(fed["sd"]), x=_usd(fed["taxable"]))))
        ord_taxable = fed.get("ordinary_taxable", fed["taxable"])
        ord_tax = fed.get("ordinary_tax", fed["tax"])
        if fed["rows"]:
            rows = [{t("Scaglione"): f"{_usd(r['from'])} – {_usd(r['to']) if r['to'] is not None else '…'}",
                     t("Aliquota"): r["rate"], t("Parte tassata"): r["taxed"], t("Imposta"): r["tax"]}
                    for r in fed["rows"]]
            rows.append({t("Scaglione"): t("Totale"), t("Aliquota"): None, t("Parte tassata"): ord_taxable,
                         t("Imposta"): ord_tax})
            style.table(pd.DataFrame(rows), fmt={t("Scaglione"): "text", t("Aliquota"): ("pct", 0),
                                                 t("Parte tassata"): ("money", "USD"), t("Imposta"): ("money", "USD")},
                        total_last=True)
        if fed.get("pref"):
            z, f15, f20 = fed["pref_parts"]
            st.markdown(ui.esc(t("Dividendi qualificati e plusvalenze a lungo termine: {p}, tassati a parte "
                                 "(0% su {a}, 15% su {b}, 20% su {c}) = {v}.", p=_usd(fed["pref"]), a=_usd(z),
                                 b=_usd(f15), c=_usd(f20), v=_usd(fed["pref_tax"]))))
        if fed.get("niit"):
            st.markdown(ui.esc(t("Net Investment Income Tax (3,8% oltre la soglia): {v}.", v=_usd(fed["niit"]))))
        if fed.get("ftc"):
            st.markdown(ui.esc(t("Credito per le imposte estere dei moduli 1099: −{v}.", v=_usd(fed["ftc"]))))
        if fed.get("carryover"):
            st.markdown(ui.esc(t("Perdita di capitale dedotta quest'anno: {a}; da riportare agli anni dopo: {b}.",
                                 a=_usd(-fed["cap_in_income"]), b=_usd(-fed["carryover"]))))
        if res["fica"]["total"]:
            f = res["fica"]
            st.markdown(ui.esc(t("Social Security {ss} + Medicare {m} = {tot}.", ss=_usd(f["ss"]), m=_usd(f["medicare"]),
                                 tot=_usd(f["total"]))))


def _notes() -> None:
    with st.expander(t("Come viene fatto il calcolo e cosa non è incluso"), icon=":material/help:"):
        st.markdown(t(
            "- **Federale:** stipendi dell'anno meno la deduzione standard, poi gli scaglioni {y} dell'IRS per lo "
            "stato civile scelto.\n"
            "- **Stati:** per ogni stato l'imposta è calcolata come se tutto il reddito dell'anno fosse suo e poi "
            "ridotta alla quota degli stipendi ricevuti mentre risiedevi lì (il metodo usato da molti stati per chi "
            "risiede solo una parte dell'anno). Scaglioni, deduzioni ed esenzioni {y} (Tax Foundation, aggiornati con "
            "le leggi approvate nel {y}).\n"
            "- **Imposta locale:** la percentuale che indichi per lo stato, sugli stipendi di quel periodo.\n"
            "- **Non inclusi:** detrazioni analitiche (mutuo, donazioni…), contributi pensionistici prima delle tasse "
            "(401k, assicurazione sanitaria), crediti d'imposta (figli, credito per le tasse pagate all'estero), "
            "altri redditi (interessi, dividendi, plusvalenze), le nuove deduzioni federali per mance e straordinari, "
            "la deduzione delle tasse federali in Oregon, il «recapture» dei redditi alti di New York e Connecticut "
            "e le riduzioni legate al reddito non elencate.\n"
            "- **Coppie:** con la dichiarazione congiunta le soglie sono quelle delle coppie, ma il reddito è solo "
            "quello degli stipendi nelle categorie scelte.\n"
            "- **Italia–USA:** chi ha redditi anche in Italia può avere diritto al credito per le imposte estere o "
            "all'esenzione dai contributi: qui non è considerato.\n\n"
            "Per questo c'è il margine di sicurezza: aggiungi qualche punto percentuale e confronta la stima con la "
            "dichiarazione vera quando la fai.", y=D.YEAR))
        st.markdown(ui.esc(t(
            "**Redditi da investimenti (moduli 1099):**\n"
            "- interessi e dividendi ordinari si sommano agli stipendi; i dividendi qualificati e le plusvalenze nette "
            "a lungo termine (titoli tenuti più di un anno, più le distribuzioni di plusvalenze) hanno le aliquote "
            "ridotte 0/15/20% sopra il resto del reddito; le plusvalenze a breve termine sono tassate come lo "
            "stipendio;\n"
            "- una perdita netta si deduce fino a 3.000 $ l'anno (1.500 $ per i coniugi con dichiarazioni separate), "
            "il resto si riporta agli anni dopo (qui non viene riportato in automatico);\n"
            "- Net Investment Income Tax del 3,8% sulla parte di reddito oltre 200.000 $ (250.000 $ in coppia);\n"
            "- le imposte estere dei 1099 diventano un credito (versione semplificata, senza il modulo 1116); le "
            "ritenute federali dei 1099 vengono tolte da quanto resta da pagare;\n"
            "- negli stati i redditi da investimenti sono tassati come gli stipendi e divisi in proporzione ai giorni "
            "di residenza; gli interessi dei titoli del Tesoro USA sono esenti. Non sono considerate le riduzioni "
            "sulle plusvalenze di alcuni stati (per esempio Arkansas, Dakota del Nord, Carolina del Sud, Wisconsin) "
            "né l'imposta sulle plusvalenze dello stato di Washington.\n"
            "- I conti titoli fuori dagli Stati Uniti (per esempio Fineco) non mandano il 1099, ma per chi risiede "
            "negli USA anche quelle vendite, dividendi e interessi vanno dichiarati: inseriscili a mano come "
            "riepilogo, con gli importi convertiti in dollari.")))


# ---------------------------------------------------------------- obiettivo
def _usd_to_base(tx: pd.DataFrame) -> float | None:
    base = db.base_currency()
    if base == "USD":
        return 1.0
    try:
        return fx.get_rate("USD", base)
    except Exception:
        return goals.rate_to_base("USD", tx) if not tx.empty else None


def _goal_box(year: int, remaining: float, rate: float | None, tx: pd.DataFrame) -> None:
    st.divider()
    name = t("Tasse {y} (USA)", y=year)
    base = db.base_currency()
    deadline = date(year + 1, 4, 15)
    gdf = db.goals_df()
    cfg = tax_us.load_cfg()
    gid = cfg["goal"].get(str(year))
    ids = {int(i) for i in gdf["id"]} if not gdf.empty else set()
    existing = int(gid) if gid is not None and int(gid) in ids else None
    if existing is None and not gdf.empty:     # obiettivo creato prima con lo stesso nome
        hit = gdf[gdf["name"] == name]
        existing = int(hit.iloc[0]["id"]) if not hit.empty else None
    if existing is not None:
        name = str(gdf.loc[gdf["id"] == existing, "name"].iloc[0])
    st.markdown("**" + t("Vuoi mettere da parte questa cifra?") + "**")
    if rate is None:
        st.caption(t("Non riesco a ottenere il cambio da dollari a {ccy}: l'obiettivo non può essere creato ora.",
                     ccy=base))
        return
    target = round(remaining * rate, 2)
    st.caption(ui.esc(t("Crea un obiettivo di {v} ({u} margine compreso, convertiti in {ccy}) con scadenza {d} (il "
                        "termine di solito per pagare le tasse dell'anno): lo trovi nella pagina Obiettivi e puoi "
                        "segnare lì quanto accantoni.", v=ui.money(target, base), u=_usd(remaining), ccy=base,
                        d=_d(deadline))
                      if base != "USD" else
                      t("Crea un obiettivo di {v} (margine compreso) con scadenza {d} (il termine di solito per "
                        "pagare le tasse dell'anno): lo trovi nella pagina Obiettivi e puoi segnare lì quanto "
                        "accantoni.", v=ui.money(target, base), d=_d(deadline))))
    c1, c2 = st.columns([1, 1])
    label = (t("Aggiorna l'obiettivo «{n}»", n=name) if existing else t("Crea l'obiettivo «{n}»", n=name))
    if c1.button(label, type="primary", icon=":material/savings:", key="tax_goal", disabled=target <= 0):
        fields = {"name": name, "target": target, "deadline": deadline.isoformat()}
        if existing is None:
            fields.update(start_date=date.today().isoformat(), mode="manuale", initial=0.0, color=GOAL_COLOR,
                          archived=0)
        gid = db.save_goal(fields, existing)
        cfg["goal"][str(year)] = int(gid)
        tax_us.save_cfg(cfg)
        st.session_state["tax_flash"] = (t("Obiettivo «{n}» aggiornato: {v}.", n=name, v=ui.money(target, base))
                                         if existing else
                                         t("Obiettivo «{n}» creato: {v}.", n=name, v=ui.money(target, base)))
        st.rerun()
    if existing and "obiettivi" in nav.PAGES:
        c2.page_link(nav.PAGES["obiettivi"], label=t("Apri gli obiettivi"), icon=":material/arrow_forward:")
