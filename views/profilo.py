"""Profilo: nome, avatar, intestatari dei conti, riepilogo dei conti importati e collegamenti alle impostazioni."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from core import db, i18n
from core.i18n import t
from views import cerca, nav, style, ui

COLOR_LABELS = {"viola": "Viola", "blu": "Blu", "verde": "Verde", "arancio": "Arancio", "rosa": "Rosa",
                "grafite": "Grafite"}
def _d(x) -> str:
    return i18n.date_short(pd.Timestamp(x))


def render():
    style.header(t("Profilo"), t("Le tue informazioni e i tuoi conti, salvati solo su questo computer"))
    tx = db.transactions_df()
    name = style.profile_name()
    a, b = style.avatar_colors()

    since = _d(tx["date"].min()) if not tx.empty else "–"
    n_acc = tx["account"].nunique() if not tx.empty else 0
    st.html(f'''<div class="as-profile" style="--g1:{a};--g2:{b}">
  <div class="as-avatar xl">{style.e(style.initials_of(name))}</div>
  <div class="who"><div class="n">{style.e(name or t("Il tuo profilo"))}</div>
  <div class="m">{style.e(t("{n} movimenti su 1 conto, dal {d}", n=ui.fmt_num(len(tx), 0), d=since) if n_acc == 1 else
                          t("{n} movimenti su {a} conti, dal {d}", n=ui.fmt_num(len(tx), 0), a=n_acc, d=since))}</div></div>
</div>''')

    left, right = st.columns([2, 3], gap="medium")
    with left, style.card("prof_dati"):
        st.subheader(t("I tuoi dati"))
        new_name = st.text_input(t("Nome"), value=name, placeholder=t("Es. Mario Rossi"), key="prof_name")
        colors = list(COLOR_LABELS)
        cur = db.get_setting("profile_color", "viola") or "viola"
        color = st.segmented_control(t("Colore dell'avatar"), colors, default=cur if cur in colors else "viola",
                                     format_func=lambda c: t(COLOR_LABELS[c]), key="prof_color")
        owners = st.text_area(
            t("Intestatari dei conti (uno per riga)"), value="\n".join(db.owner_names()), height=90, key="prof_owners",
            help=t("I bonifici verso o da questi nomi (es. dal conto Fineco al tuo Revolut) diventano "
                   "«Trasferimenti tra conti» e non contano come spese o entrate. Va bene anche «Cognome Nome»."))
        from core import recurring
        salary, sched_raw = _salary_inputs(tx)
        bad_sched = salary in recurring.SCHEDULE_MODES and recurring.clean_schedule(sched_raw, salary) is None
        from views import lingua
        lingua.selector("prof_lang")
        save = st.button(t("Salva"), type="primary", key="prof_save", icon=":material/check:")
        if save and bad_sched:
            st.error(t("Scegli almeno un giorno del mese in cui arriva lo stipendio."), icon=":material/event_busy:")
        if save and not bad_sched:
            db.set_setting(recurring.SALARY_KEY, salary)
            if salary in recurring.SCHEDULE_MODES:
                db.set_setting(recurring.SALARY_SCHED_KEY, json.dumps(sched_raw))
            db.set_setting("profile_name", new_name.strip())
            db.set_setting("profile_color", color or "viola")
            db.set_setting("owner_names", "\n".join(n.strip() for n in owners.splitlines() if n.strip()))
            st.toast(t("Profilo salvato"), icon=":material/check_circle:")
            st.rerun()
        st.caption(t("Gli intestatari valgono per i prossimi import. La lingua cambia subito."))

    with right:
        with style.card("prof_conti"):
            st.subheader(t("I tuoi conti"))
            if tx.empty:
                st.caption(t("Nessun conto: importa un estratto conto per iniziare."))
            else:
                g = tx.groupby(["account", "currency"]).agg(
                    n=("id", "count"), first=("date", "min"), last=("date", "max"),
                    added=("created_at", "max"), src=("source", lambda s: ", ".join(sorted(set(map(str, s))))))
                rows = []
                for (acc, ccy), r in g.sort_values("n", ascending=False).iterrows():
                    added = pd.to_datetime(r["added"], errors="coerce")
                    sub = t("aggiornato il {d}", d=_d(added)) if pd.notna(added) else ""
                    rows.append(dict(id=f"{acc}|{ccy}", desc=f"{acc} {ccy}", ini=acc[:2].upper(),
                                     meta=t("{n} movimenti, dal {a} al {b}", n=r["n"], a=_d(r["first"]), b=_d(r["last"])),
                                     amount=_source_label(r["src"]), sub=sub, color=_acc_color(acc)))
                style.item_list(rows, key="prof_acc_list", clickable=False)
            if not tx.empty:
                _balances(tx)
            c1, c2 = st.columns(2)
            if "importa" in nav.PAGES:
                c1.page_link(nav.PAGES["importa"], label=t("Importa estratti"), icon=":material/upload_file:",
                             width="stretch")
            if "banche" in nav.PAGES:
                c2.page_link(nav.PAGES["banche"], label=t("Collega banche"), icon=":material/account_balance:",
                             width="stretch")
            if "carte" in nav.PAGES:
                st.page_link(nav.PAGES["carte"], label=t("Le tue carte"), icon=":material/credit_card:")
        with style.card("prof_app"):
            st.subheader(t("App"))
            items = [(t("Valuta base"), db.base_currency(), t("totali e grafici")),
                     (t("Categorie"), f"{len(db.categories_df())}", t("{n} regole automatiche", n=len(db.rules_df()))),
                     (t("Obiettivi"), f"{len(db.goals_df())}", t("di risparmio attivi"))]
            style.kpis(items, cols=3)
            st.caption(t("Dati salvati in {path}", path=ui.esc(str(db.db_path()))))
            if "impostazioni" in nav.PAGES:
                st.page_link(nav.PAGES["impostazioni"], label=t("Impostazioni: valuta, categorie, regole, backup"),
                             icon=":material/tune:")
        _alpha()


def _salary_inputs(tx: pd.DataFrame) -> tuple[str, dict]:
    """Quando arriva lo stipendio: ultimo/primo giorno lavorativo, giorni del mese a scelta (anche più d'uno),
    ogni settimana o ogni 2 settimane, oppure riconosciuto dai movimenti. Ritorna (modalità, dettagli)."""
    from core import recurring
    modes = list(recurring.SALARY_MODES)
    cur = recurring.salary_rule()
    salary = st.selectbox(t("Lo stipendio arriva"), modes, index=modes.index(cur),
                          format_func=lambda m: t(recurring.SALARY_MODES[m]), key="prof_salary",
                          help=t("Serve a prevedere i prossimi accrediti (calendario, abbonamenti, previsione di fine "
                                 "mese). Per l'ultimo e il primo giorno lavorativo valgono le festività italiane; "
                                 "con le altre scelte puoi indicare tu il calendario delle festività."))
    try:
        saved = json.loads(db.get_setting(recurring.SALARY_SCHED_KEY, "{}") or "{}")
        saved = saved if isinstance(saved, dict) else {}
    except (ValueError, TypeError):
        saved = {}
    raw: dict = {}
    if salary == "giorni":
        old = [int(x) for x in saved.get("days") or [] if str(x).isdigit() and 1 <= int(x) <= 31]
        raw["days"] = st.multiselect(
            t("Giorni del mese"), list(range(1, 32)), default=old or [27], key="prof_sal_days",
            format_func=lambda d: t("{d} (o l'ultimo del mese)", d=d) if d >= 29 else str(d),
            placeholder=t("Scegli uno o più giorni"),
            help=t("Tutti i giorni in cui arriva, per esempio 15 e 31 se ti pagano due volte al mese. Nei mesi più "
                   "corti il 29, il 30 e il 31 diventano l'ultimo giorno del mese."))
    elif salary in ("bisettimanale", "settimanale"):
        try:
            ref = pd.Timestamp(saved["ref"]).date()
        except (KeyError, TypeError, ValueError):
            sal = tx[(tx["category"] == recurring.SALARY_CATEGORY) & (tx["amount"] > 0)] if not tx.empty else tx
            ref = sal["date"].max().date() if not sal.empty else date.today()
        ref = st.date_input(t("Un giorno in cui è arrivato (o arriverà)"), value=ref, format=i18n.date_fmt(),
                            key="prof_sal_ref",
                            help=t("Da qui si contano le settimane: va bene qualsiasi giorno di paga, passato o futuro."))
        raw["ref"] = ref.isoformat() if ref else ""
    if salary in recurring.SCHEDULE_MODES:
        shifts, cals = list(recurring.SHIFTS), list(recurring.CALENDARS)
        raw["shift"] = st.selectbox(t("Se cade di sabato, domenica o festivo"), shifts,
                                    index=shifts.index(saved.get("shift")) if saved.get("shift") in shifts else 0,
                                    format_func=lambda k: t(recurring.SHIFTS[k]), key="prof_sal_shift")
        default_cal = saved.get("cal") if saved.get("cal") in cals else "IT"
        raw["cal"] = st.selectbox(t("Festività"), cals, index=cals.index(default_cal),
                                  format_func=lambda k: t(recurring.CALENDARS[k]), key="prof_sal_cal")
        sched = recurring.clean_schedule(raw, salary)
        if sched:
            nxt = recurring.schedule_dates(sched, date.today(), pd.Timestamp(date.today()) + pd.Timedelta(days=70))[:4]
            st.caption(t("Prossimi accrediti: {d}", d=", ".join(_d(x) for x in nxt)))
        else:
            st.caption(t("Scegli almeno un giorno del mese in cui arriva lo stipendio."))
    return salary, raw


def _alpha() -> None:
    """Funzioni in prova: nascoste finché l'utente non le attiva qui."""
    from core import tax_us

    with style.card("prof_alpha"):
        st.subheader(t("Funzioni in prova"))
        st.caption(t("Funzioni nuove ancora in sviluppo (alpha): possono contenere errori. Attivale solo se ti "
                     "servono; si possono spegnere quando vuoi."))
        on = st.toggle(t("Calcolo delle tasse USA (alpha)"), value=tax_us.enabled(), key="prof_alpha_tax",
                       help=t("Solo per chi risiede negli Stati Uniti: stima le tasse federali, statali e i contributi "
                              "sugli stipendi, con un margine di sicurezza, e può creare un obiettivo per mettere da "
                              "parte la cifra. Attivandola compare la pagina «Tasse USA» nel menu a sinistra."))
        if on != tax_us.enabled():
            tax_us.set_enabled(on)
            st.rerun()
        if on and tax_us.enabled() and "tasse" in nav.PAGES:
            st.page_link(nav.PAGES["tasse"], label=t("Apri Tasse USA"), icon=":material/request_quote:")


def _source_label(src: str) -> str:
    names = {"fineco": t("Estratto Fineco"), "revolut": t("Estratto Revolut"), "chase": t("Estratto Chase"),
             "manuale": t("A mano"), "openbanking": t("Collegamento banca"), "enablebanking": t("Collegamento banca")}
    from core import banks

    def one(p: str) -> str:
        key = p.strip().lower()
        if key in names:
            return names[key]
        if key in banks.BY_ID and key != "auto":
            return t("Estratto {bank}", bank=banks.BY_ID[key].name)
        return p.strip().capitalize()

    parts = [one(p) for p in src.split(",") if p.strip()]
    return ", ".join(dict.fromkeys(parts))


def _acc_color(acc: str) -> str:
    low = acc.lower()
    if "fineco" in low:
        return "#3B82F6"
    if "revolut" in low:
        return "#7C5CFC"
    if "chase" in low:
        return "#117ACA"
    return "#14AE9E"


def _bank_refresh() -> None:
    """Pulsante che scarica dalla banca saldi e nuovi movimenti di tutti i conti collegati."""
    from core import enablebanking as eb

    if not eb.is_configured():
        return
    if st.button(t("Aggiorna i saldi dalla banca"), icon=":material/sync:", key="bal_bank_sync"):
        errors = []
        with st.spinner(t("Sincronizzazione con la banca…")):
            for a in eb.accounts_df().to_dict("records"):
                try:
                    eb.sync_account(a["uid"])
                except Exception as e:  # un conto che non risponde non blocca gli altri
                    errors.append(eb.sync_error(a, e))
        st.cache_data.clear()
        st.session_state["bal_bank_msg"] = errors
        st.rerun()
    msg = st.session_state.pop("bal_bank_msg", None)
    if msg is not None:
        if msg:
            for m, soft in msg:
                if soft:
                    st.warning(m, icon=":material/schedule:")
                else:
                    st.error(m)
        else:
            st.success(t("Saldi e movimenti aggiornati dalla banca."), icon=":material/check_circle:")


def _balances(tx: pd.DataFrame) -> None:
    """Saldi reali dei conti: servono alla previsione del saldo a fine mese."""
    from core import forecast

    offs = forecast.balance_offsets()          # scritti a mano
    banks = forecast.bank_balances()           # dalla banca (conti collegati): vincono su quelli a mano
    eff = forecast.effective_offsets(tx, banks)
    done = [k for k in eff]
    label = ((t("Saldi reali dei conti (1 impostato)") if len(done) == 1
              else t("Saldi reali dei conti ({n} impostati)", n=len(done))) if done
             else t("Saldi reali dei conti (per la previsione a fine mese)"))
    with st.expander(label, icon=":material/account_balance_wallet:", expanded=cerca.is_open("saldi")):
        st.caption(t("Per i conti collegati alla banca (Collega banche) il saldo arriva dalla banca e si aggiorna a ogni "
                     "sincronizzazione: non va scritto a mano. Per gli altri scrivi il saldo che vedi oggi nell'app "
                     "della banca: gli estratti spesso non partono dall'apertura del conto, quindi la somma dei "
                     "movimenti non coincide con il saldo; la differenza viene ricordata e da qui in poi il saldo si "
                     "aggiorna da solo con i nuovi movimenti."))
        if banks:
            from core import autosync
            st.caption(":material/schedule: " + autosync.status_text())
            _bank_refresh()
        pairs = {(a, c) for a, c in zip(tx["account"], tx["currency"])}
        pairs |= {tuple(k.split("|", 1)) for k in eff}
        for acc, ccy in sorted(pairs):
            key = f"{acc}|{ccy}"
            computed = float(tx.loc[(tx["account"] == acc) & (tx["currency"] == ccy), "amount"].sum())
            if key in banks:
                b = banks[key]
                cur = computed + eff[key] if key in eff else b["balance"]
                c1, c2 = st.columns([2, 3], vertical_alignment="center")
                c1.markdown(f"**{ui.esc(acc)} {ccy}**  \n" + t("saldo attuale {v}", v=ui.esc(ui.money(cur, ccy)).replace(" ", "\u00a0")))
                c2.markdown(f":green-badge[:material/sync: {t('Sincronizzato dalla banca')}]  \n"
                            + t("saldo della banca {v} al {d}", v=ui.esc(ui.money(b["balance"], ccy)).replace(" ", "\u00a0"),
                                d=_d(b["date"]) if b["date"] else "–"))
                continue
            cur = computed + offs[key] if key in offs else None
            c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
            c1.markdown(f"**{ui.esc(acc)} {ccy}**  \n" + (t("saldo attuale {v}", v=ui.esc(ui.money(cur, ccy)).replace(" ", "\u00a0"))
                                                         if cur is not None else t("non impostato")))
            val = c2.number_input(t("Saldo reale {acc} {ccy}", acc=acc, ccy=ccy), value=round(cur if cur is not None else computed, 2),
                                  step=10.0, format="%.2f", key=f"bal_{key}", label_visibility="collapsed")
            if c3.button(t("Salva"), key=f"bal_save_{key}", width="stretch"):
                forecast.set_real_balance(acc, ccy, val, tx)
                st.rerun()
            if key in offs and st.button(t("Non usare {acc} {ccy} nella previsione", acc=acc, ccy=ccy), key=f"bal_del_{key}",
                                         type="tertiary"):
                forecast.set_real_balance(acc, ccy, None, tx)
                st.rerun()
