from datetime import date

import pandas as pd
import streamlit as st

from core import autosync, db, enablebanking as eb, i18n
from core.i18n import t
from views import cerca, style, ui

GUIDE = """
**Perché serve un intermediario?** Fineco e Revolut (conto personale) non danno API dirette ai privati:
l'accesso automatico passa dall'**Open Banking PSD2** tramite un aggregatore autorizzato.
Qui si usa **Enable Banking**, gratuito per collegare *i propri* conti (modalità "restricted").
GoCardless/Nordigen non accetta più nuove iscrizioni dal 2025.

**Configurazione (una volta sola, ~10 minuti):**
1. Registrati su [enablebanking.com](https://enablebanking.com) e apri il **Control Panel**.
2. *API applications* → **Add a new application** → ambiente **Production**, lascia la generazione della chiave
   nel browser. Come *Redirect URL* inserisci esattamente l'indirizzo indicato qui sotto
   (non deve esistere davvero). Per privacy/terms puoi mettere lo stesso URL.
3. Alla creazione il browser scarica un file **`.pem`** (chiave privata): conservalo.
4. Nel Control Panel, sulla tua applicazione premi **Link accounts** e collega Fineco e Revolut
   (in modalità restricted si possono leggere **solo** i conti collegati lì).
5. Copia l'**Application ID** e carica qui sotto il file `.pem`.

**Collegamento dall'app:** scegli la banca → *Avvia collegamento* → accedi sul sito della banca →
alla fine il browser va su una pagina che **non si carica** (è normale): copia l'intero indirizzo dalla barra
e incollalo qui. Il consenso PSD2 dura in genere 90–180 giorni, poi va rinnovato.
"""


def _settings():
    with st.expander(t("Configurazione Enable Banking"), expanded=not eb.is_configured() or cerca.is_open("eb_config")):
        st.markdown(t(GUIDE))
        c1, c2 = st.columns(2)
        app_id = c1.text_input("Application ID", value=db.get_setting("eb_app_id") or "")
        redirect = c2.text_input(t("Redirect URL (identico a quello registrato)"),
                                 value=db.get_setting("eb_redirect_url") or "https://localhost/callback")
        pem = st.file_uploader(t("Chiave privata (.pem)"), type=["pem", "key", "txt"])
        if st.button(t("Salva configurazione")):
            db.set_setting("eb_app_id", app_id.strip())
            db.set_setting("eb_redirect_url", redirect.strip())
            if pem:
                try:
                    eb.save_private_key(pem.getvalue())
                except eb.EBError as e:
                    st.error(str(e))
                    return
            st.success(t("Configurazione salvata."))
        st.caption(t("Chiave privata: {state} (salvata in {path})",
                     state="✅ " + t("presente") if eb.key_path().exists() else "❌ " + t("mancante"),
                     path=f"`{eb.key_path()}`"))


def _link():
    st.subheader(t("Collega un nuovo conto"))
    c1, c2 = st.columns([1, 3])
    country = c1.selectbox(t("Paese della banca"), ["IT", "LT", "IE", "DE", "FR", "ES", "NL", "GB"],
                           help=t("Revolut può comparire sotto IT o LT (Lituania) a seconda del conto."))
    if c2.button(t("Carica elenco banche"), key="eb_load"):
        try:
            st.session_state["eb_aspsps"] = eb.list_aspsps(country)
            st.session_state["eb_country"] = country
        except Exception as e:
            st.error(t("Errore: {err}", err=e))
    aspsps = st.session_state.get("eb_aspsps")
    if not aspsps:
        return
    names = [a["name"] for a in aspsps]
    default = next((i for i, n in enumerate(names) if "fineco" in n.lower()), 0)
    bank = st.selectbox(t("Banca ({n} disponibili)", n=len(names)), names, index=default)
    info = next(a for a in aspsps if a["name"] == bank)
    max_days = int((info.get("maximum_consent_validity") or 90 * 86400) // 86400)
    max_days = max(max_days, 2)
    days = st.slider(t("Durata del consenso (giorni)"), 1, max_days, min(90, max_days))
    if st.button(t("Avvia collegamento"), icon=":material/link:", type="primary"):
        try:
            url = eb.start_auth(bank, st.session_state["eb_country"], days, info.get("maximum_consent_validity"))
            st.session_state["eb_pending"] = {"bank": bank, "country": st.session_state["eb_country"], "url": url}
        except Exception as e:
            st.error(t("Errore: {err}", err=e))
    pend = st.session_state.get("eb_pending")
    if pend:
        st.link_button(t("Apri il login di {bank}", bank=pend["bank"]), pend["url"], icon=":material/open_in_new:")
        back = st.text_input(t("Incolla qui l'indirizzo completo della pagina di ritorno (contiene `code=`)"))
        if st.button(t("Completa collegamento")):
            try:
                code = eb.extract_code(back)
                accs = eb.create_session(code, pend["bank"], pend["country"])
                st.session_state.pop("eb_pending", None)
                st.success(t("Collegati {n} conti: ", n=len(accs)) + ", ".join(a["name"] for a in accs))
            except Exception as e:
                st.error(t("Errore: {err}", err=e))


_NEW = "__nuovo__"


def _label_picker(col, a, app_accounts: list[str]) -> None:
    """Conto dell'app in cui finiscono i movimenti di questo collegamento (di solito quello degli estratti)."""
    current = a["label"] or a["aspsp_name"]
    opts = list(dict.fromkeys(app_accounts + [current])) + [_NEW]
    key = f"lbl_{a['uid']}"
    choice = col.selectbox(t("Conto nell'app"), opts, index=opts.index(current), key=key,
                           format_func=lambda o: t("Nuovo nome…") if o == _NEW else o,
                           help=t("Scegli lo stesso conto in cui importi gli estratti di questa banca: così i "
                                  "movimenti non risultano doppi."))
    if choice == _NEW:
        new = col.text_input(t("Nome del conto"), key=f"{key}_new")
        if new.strip() and col.button(t("Usa questo nome"), key=f"{key}_ok"):
            choice = new.strip()
        else:
            return
    if choice != current:
        moved = eb.set_label(a["uid"], choice)
        st.cache_data.clear()
        st.session_state["eb_flash"] = t("Conto cambiato in «{acc}»: spostati {n} movimenti.", acc=choice, n=moved)
        st.rerun()


def _duplicates_box() -> None:
    """Movimenti presenti due volte (estratto + collegamento): anteprima e sistemazione con un clic."""
    from core import dedup, storage

    msg = st.session_state.pop("eb_flash", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")
    mapping = dedup.suggested_mapping()
    try:
        prev = dedup.run(mapping, apply=False)
    except Exception as e:
        st.error(t("Controllo dei doppioni non riuscito: {err}", err=e))
        return
    if not prev["removed"] and not prev["moved"]:
        return
    with st.container(border=True, key="eb_dups"):
        st.subheader(t("Movimenti doppi"))
        st.markdown(t("Alcuni movimenti arrivano sia dagli estratti importati sia dal collegamento con la banca. "
                      "Tengo quelli degli estratti (storico completo, descrizioni e categorie già sistemate) e tolgo "
                      "le copie del collegamento; prima faccio un backup."))
        rows = [{t("Conto"): acc, t("Dal collegamento"): v["api"], t("Doppi da togliere"): v["doppi"],
                 t("A importo zero"): v["zero"], t("Nuovi (restano)"): v["nuovi"]}
                for acc, v in prev["accounts"].items()]
        if rows:
            style.table(pd.DataFrame(rows))
        if prev["moved"]:
            st.caption(t("I movimenti del collegamento vengono anche spostati nel conto dell'app corrispondente "
                         "({n} movimenti).", n=prev["moved"]))
        if st.button(t("Togli i doppioni ({n})", n=prev["removed"]), type="primary", icon=":material/cleaning_services:",
                     key="eb_dedup"):
            try:
                storage.backup_now()
                res = dedup.run(mapping, apply=True)
                st.cache_data.clear()
                st.session_state["eb_flash"] = t("Fatto: tolti {n} movimenti doppi. Il backup di prima è nella "
                                                 "cartella dei backup.", n=res["removed"])
                st.rerun()
            except Exception as e:
                st.error(t("Sistemazione non riuscita: {err}", err=e))


def _auto_sync_box() -> None:
    """Interruttore della sincronizzazione automatica giornaliera e stato dell'ultimo giro."""
    on = st.toggle(t("Sincronizza i conti in automatico una volta al giorno"), value=autosync.enabled(),
                   key="eb_auto_sync",
                   help=t("Alla prima apertura dell'app di ogni giorno (e, se l'app resta aperta, al cambio di giorno) "
                          "i conti collegati si sincronizzano da soli: movimenti nuovi e saldi. I conti già "
                          "sincronizzati oggi, anche a mano, vengono saltati: al massimo una lettura automatica al "
                          "giorno per conto, ben sotto il limite della banca (di solito 4 al giorno)."))
    if on != autosync.enabled():
        autosync.set_enabled(on)
    st.caption(":material/schedule: " + autosync.status_text())
    res = autosync.last_result()
    if on and res and str(res.get("at", ""))[:10] == date.today().isoformat():
        for msg, soft in res.get("errors", []):
            if soft:
                st.warning(msg, icon=":material/schedule:")
            else:
                st.error(msg)


def render():
    style.header(t("Collega banche"), t("Sincronizzazione automatica dei movimenti tramite Open Banking"))
    _settings()
    if not eb.is_configured():
        st.info(t("Completa la configurazione qui sopra per collegare Fineco e Revolut. "
                  "In alternativa usa **📥 Importa estratti** con i file esportati dalle banche."))
        return

    accs = eb.accounts_df()
    if not accs.empty:
        _duplicates_box()
    st.subheader(t("Conti collegati"))
    if accs.empty:
        st.caption(t("Nessun conto collegato."))
    else:
        _auto_sync_box()
        since = st.date_input(t("Scarica movimenti dal (vuoto = dall'ultima sincronizzazione)"), value=None,
                              format=i18n.date_fmt(), max_value=date.today())
        if st.button(t("Sincronizza tutti"), icon=":material/sync:", type="primary"):
            for _, a in accs.iterrows():
                try:
                    ins, skip = eb.sync_account(a["uid"], since)
                    st.success(t("{label} · {name}: {n} nuovi movimenti ({s} già presenti)", label=a["label"],
                                 name=a["account_name"], n=ins, s=skip))
                except Exception as e:
                    m, soft = eb.sync_error(a.to_dict(), e)
                    if soft:
                        st.warning(m, icon=":material/schedule:")
                    else:
                        st.error(m)
            st.cache_data.clear()
        app_accounts = db.accounts_list()
        for _, a in accs.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                kind = t("Carta") if eb.is_card(a) else t("Conto")
                iban = a["iban"] if isinstance(a["iban"], str) and a["iban"].strip() else a["uid"][:8]
                ccy = a["currency"] if isinstance(a["currency"], str) else ""
                c1.markdown(f"**{a['aspsp_name']}** — {a['account_name']}  \n`{iban}` {ccy} · {kind}")
                if pd.notna(a.get("balance")):
                    c1.caption(t("Saldo dalla banca: {v} ({d})", v=ui.money(float(a["balance"]),
                                                                              a["balance_currency"] or a["currency"]),
                                 d=str(a["balance_date"] or "")[:10]))
                exp = (a["valid_until"] or "")[:10]
                expired = bool(exp) and exp < date.today().isoformat()
                c2.markdown(t("Consenso fino al: **{d}**", d=exp or "?") + (t(" (scaduto, ricollega)") if expired else ""))
                c2.caption(t("Ultima sync: {d}", d=a["last_sync"] or t("mai")))
                _label_picker(c3, a, app_accounts)
                if c4.button("", icon=":material/delete:", key=f"del_{a['uid']}", help=t("Rimuovi il collegamento (i movimenti restano)")):
                    eb.remove_account(a["uid"])
                    st.rerun()
        st.caption(t("I movimenti già scaricati non vengono duplicati, nemmeno quelli già importati dagli estratti "
                     "(stesso conto, importo e data entro 4 giorni). Primo scarico: ultimi 90 giorni (molte banche via "
                     "PSD2 non forniscono più di 90 giorni di storico; per lo storico precedente usa l'import file)."))
    st.divider()
    _link()
