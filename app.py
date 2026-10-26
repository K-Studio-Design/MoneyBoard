"""MoneyBoard — gestione spese, entrate e investimenti.
Avvio:  streamlit run app.py   (oppure doppio clic su avvia_app.bat)
"""
from datetime import timedelta
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="MoneyBoard", page_icon=":material/account_balance_wallet:", layout="wide")

from core import autoimport, autosync, db, demo, i18n, securities, storage, version  # noqa: E402
from core.i18n import t  # noqa: E402
from views import (abbonamenti, analisi, avvisi, banche, calendario, carte, cartelle, dashboard, focus, importa,  # noqa: E402
                   impostazioni, investimenti, lingua, login, nav, obiettivi, profilo, spese, style, tasse, theme, ui,
                   utenti, valute)

db.init_db()

# accesso con nome utente e password: finché non si entra, nessun dato viene letto o mostrato e non partono
# né il backup né l'import automatico
_authed = login.is_authenticated()
lingua.init(_authed)  # lingua dell'interfaccia (italiano / inglese)
if _authed and not db.is_admin():
    # utente creato dall'Admin: database tutto suo (creato al primo accesso); un account di prova parte con i
    # dati fittizi, uno normale vuoto, con il suo nome nel profilo
    db.init_db()
    if db.is_demo():
        demo.ensure_seeded()
    elif not db.get_setting("user_initialized", ""):
        from core import auth
        db.set_setting("profile_name", auth.display_name(db.current_user()))
        db.set_setting("user_initialized", "1")

# all'avvio: backup automatico (se è ora) e import degli estratti messi nella cartella.
# Va fatto prima di costruire il menu, così il numero di avvisi tiene conto dei movimenti appena importati.
# Gli avvisi a comparsa si mostrano dopo il tema (che può far ripartire la pagina una volta).
_notices = st.session_state.setdefault("_startup_notices", [])
if _authed and "startup_done" not in st.session_state:
    st.session_state["startup_done"] = True
    try:
        _bk = storage.maybe_auto_backup()
        if _bk:
            _notices.append(("backup", str(_bk.parent)))
    except Exception as _e:  # un backup non riuscito non deve bloccare l'app
        _notices.append(("backup_err", str(_e)))
if _authed:
    try:
        # ogni 30 secondi al massimo (il primo giro è all'avvio): i file nuovi vengono importati da soli
        _imported = autoimport.run()
        if _imported:
            st.cache_data.clear()
            _notices.append(("import", _imported))
    except Exception as _e:
        _notices.append(("import_err", str(_e)))



def update_prices(show_toast: bool = True) -> None:
    with st.spinner(t("Aggiorno le quotazioni dei titoli…")):
        try:
            ok, errors = securities.update_all_prices()
            if show_toast:
                st.toast(t("Quotazioni aggiornate: {ok}", ok=ok)
                         + (t(" — {n} errori", n=len(errors)) if errors else ""), icon=":material/trending_up:")
            st.session_state["price_errors"] = errors
        except Exception as e:  # rete assente ecc.
            st.toast(t("Aggiornamento quotazioni non riuscito: {err}", err=e), icon=":material/error:")


try:
    _n_alerts = len(ui.active_alerts()) if _authed else 0
except Exception:  # gli avvisi non devono mai impedire l'avvio dell'app
    _n_alerts = 0
nav.PAGES["avvisi"] = st.Page(avvisi.render, title=t("Avvisi ({n})", n=_n_alerts) if _n_alerts else t("Avvisi"),
                              icon=":material/notifications:", url_path="avvisi")
nav.PAGES["calendario"] = st.Page(calendario.render, title=t("Calendario"), icon=":material/calendar_month:",
                                 url_path="calendario")
nav.PAGES.update(
    dashboard=st.Page(dashboard.render, title=t("Panoramica"), icon=":material/space_dashboard:", url_path="panoramica",
                      default=True),
    spese=st.Page(spese.render, title=t("Movimenti"), icon=":material/receipt_long:", url_path="movimenti"),
    analisi=st.Page(analisi.render, title=t("Analisi"), icon=":material/insights:", url_path="analisi"),
    abbonamenti=st.Page(abbonamenti.render, title=t("Abbonamenti"), icon=":material/autorenew:", url_path="abbonamenti"),
    obiettivi=st.Page(obiettivi.render, title=t("Obiettivi"), icon=":material/savings:", url_path="obiettivi"),
    investimenti=st.Page(investimenti.render, title=t("Investimenti"), icon=":material/show_chart:",
                         url_path="investimenti"),
    valute=st.Page(valute.render, title=t("Valute e cambi"), icon=":material/currency_exchange:", url_path="valute"),
)
pages = {
    t("Spese"): [nav.PAGES[k] for k in ("dashboard", "spese", "analisi", "calendario", "abbonamenti", "avvisi")],
    t("Patrimonio"): [nav.PAGES[k] for k in ("obiettivi", "investimenti", "valute")],
}
# funzione in prova (alpha), attivata dal Profilo: la pagina esiste solo se è accesa
nav.PAGES.pop("tasse", None)
try:
    from core import tax_us
    _tax_on = _authed and tax_us.enabled()
except Exception:  # un problema qui non deve impedire l'avvio dell'app
    _tax_on = False
if _tax_on:
    nav.PAGES["tasse"] = st.Page(tasse.render, title=t("Tasse USA (alpha)"), icon=":material/request_quote:",
                                 url_path="tasse")
    pages[t("Patrimonio")].append(nav.PAGES["tasse"])
# pagine del profilo: non compaiono nel menu laterale (le nasconde il CSS), si aprono dall'avatar in alto a destra
nav.PAGES.update(
    profilo=st.Page(profilo.render, title=t("Profilo"), icon=":material/person:", url_path="profilo"),
    carte=st.Page(carte.render, title=t("Carte"), icon=":material/credit_card:", url_path="carte"),
    importa=st.Page(importa.render, title=t("Importa estratti"), icon=":material/upload_file:", url_path="importa"),
    banche=st.Page(banche.render, title=t("Collega banche"), icon=":material/account_balance:", url_path="banche"),
    impostazioni=st.Page(impostazioni.render, title=t("Impostazioni"), icon=":material/tune:", url_path="impostazioni"),
)
nav.PAGES["utenti"] = st.Page(utenti.render, title=t("Utenti"), icon=":material/group:", url_path="utenti")
# «Utenti» compare nel menu dell'avatar solo per l'amministratore; per gli altri la pagina dice che non è accessibile
pages[t("Profilo")] = [nav.PAGES[k] for k in ("profilo", "carte", "importa", "banche", "impostazioni", "utenti")]
# senza accesso il menu è nascosto: l'indirizzo della pagina richiesta resta e la pagina si apre dopo l'accesso
pg = st.navigation(pages, expanded=True, position="sidebar" if _authed else "hidden")  # tutte le voci
theme.ensure_theme()  # applica il tema salvato (dopo navigation, così un eventuale rerun resta sulla pagina)
style.inject_css(theme.current_mode())
login.cookie_scripts()
lingua.cookie_script()
if not _authed:
    login.render()
    st.stop()
for _kind, _val in st.session_state.pop("_startup_notices", []):
    if _kind == "backup":
        st.toast(t("Backup automatico salvato in {path}", path=_val), icon=":material/backup:")
    elif _kind == "import":
        cartelle.startup_notice(_val)
    else:
        st.toast(t("Backup automatico non riuscito: {err}", err=_val) if _kind == "backup_err"
                 else t("Import automatico non riuscito: {err}", err=_val), icon=":material/error:")
_auto = st.session_state.pop("_autosync_notice", None)   # esito della sincronizzazione automatica con la banca
if _auto:
    if _auto.get("synced") or _auto.get("expired"):
        st.toast(t("Sincronizzazione automatica con la banca: {s}", s=autosync.summary(_auto)),
                 icon=":material/sync:")
    for _msg, _soft in _auto.get("errors", []):
        st.toast(_msg, icon=":material/schedule:" if _soft else ":material/error:")
_logo = "logo_glass.svg" if theme.current_mode() == "glass" else "logo.svg"
st.logo(str(Path(__file__).parent / "assets" / _logo), size="large")

# aggiornamento automatico all'apertura (una volta per sessione)
if "prices_checked" not in st.session_state:
    st.session_state["prices_checked"] = True
    if db.get_setting("auto_update_prices") == "1" and not securities.instruments_df().empty:
        update_prices()


with st.sidebar:
    ui.view_filters()
    st.divider()
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    with c1:
        theme.theme_switcher()
    if c2.button("", icon=":material/refresh:", help=t("Aggiorna le quotazioni di titoli e crypto")):
        update_prices()
    last = db.get_setting("prices_last_update")
    if db.is_demo():
        st.caption(":material/science: " + t("Account di prova: tutti i dati sono fittizi."))
    _when = ""
    if last:
        from datetime import datetime as _dt
        try:
            _w = _dt.fromisoformat(last)
            _when = t(", quotazioni del {day} alle {time}", day=f"{_w:%m/%d}" if i18n.is_en() else f"{_w:%d/%m}",
                      time=f"{_w:%H:%M}")
        except ValueError:
            _when = ""
    st.caption(t("Valuta base {ccy}", ccy=db.base_currency()) + _when)


@st.fragment(run_every=timedelta(minutes=15))
def _bank_autosync() -> None:
    """Sincronizzazione automatica dei conti collegati alla banca, una volta al giorno: alla prima apertura del
    giorno e, se l'app resta aperta, al cambio di giorno (il controllo si ripete ogni 15 minuti e costa pochissimo:
    finché il giro di oggi è fatto non succede niente). Parte dopo la pagina, così l'app si vede subito."""
    try:
        if not autosync.due():
            return
        with st.spinner(t("Sincronizzo i conti con la banca…")):
            res = autosync.run()
    except Exception as e:  # la sincronizzazione automatica non deve mai bloccare l'app
        st.toast(t("Sincronizzazione automatica non riuscita: {err}", err=e), icon=":material/error:")
        return
    if res is None or not (res.get("synced") or res.get("errors") or res.get("expired")):
        return                  # niente da fare (es. conti già sincronizzati a mano oggi)
    if res.get("synced"):
        st.cache_data.clear()   # saldi e movimenti nuovi: si ricalcola tutto
    st.session_state["_autosync_notice"] = res
    st.rerun()                  # ridisegna l'app con i dati aggiornati e mostra l'esito


pg.run()
focus.handle_pending()  # movimento cliccato dentro il dettaglio di una categoria
with st.sidebar:
    _bank_autosync()
    st.caption(version.credit_markdown())  # versione dell'app e autore
