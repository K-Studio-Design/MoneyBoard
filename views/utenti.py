"""Profilo → Utenti (solo l'amministratore): crea, rinomina ed elimina gli utenti e cambia la loro password;
cambia anche il nome e la password dell'amministratore."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import auth, db, i18n, users
from core.i18n import t
from views import login, style, ui


def _when(iso: str | None) -> str:
    if not iso:
        return t("mai")
    try:
        return f"{datetime.fromisoformat(iso):{i18n.strf()} %H:%M}"
    except ValueError:
        return "–"


def _flash(msg: str) -> None:
    st.session_state["ut_flash"] = msg


def _edit(uid: str) -> None:
    st.dialog(t("Modifica utente"))(_edit_body)(uid)


def _edit_body(uid: str) -> None:
    u = users.get(uid)
    if not u:
        st.error(t("Utente non trovato."))
        return
    st.markdown(t("**Nome utente** (serve per entrare; maiuscole e minuscole non contano)"))
    with st.form(f"ut_name_{uid}", border=False):
        name = st.text_input(t("Nome utente"), value=u["name"], key=f"ut_e_name_{uid}", label_visibility="collapsed")
        if st.form_submit_button(t("Salva il nome"), icon=":material/badge:"):
            try:
                users.rename(uid, name)
                _flash(t("Nome cambiato in «{name}».", name=users.get(uid)["name"]))
                st.rerun()
            except users.UserError as e:
                st.error(str(e))
    st.divider()
    st.markdown("**" + t("Nuova password") + "**")
    with st.form(f"ut_pwd_{uid}", border=False):
        p1 = st.text_input(t("Nuova password"), type="password", key=f"ut_e_p1_{uid}", autocomplete="new-password")
        p2 = st.text_input(t("Ripeti la password"), type="password", key=f"ut_e_p2_{uid}", autocomplete="new-password")
        if st.form_submit_button(t("Cambia la password"), icon=":material/key:"):
            try:
                users.set_password(uid, p1, p2)
                _flash(t("Password di «{name}» cambiata: se era collegato dovrà rientrare con quella nuova.", name=u["name"]))
                st.rerun()
            except users.UserError as e:
                st.error(str(e))
    st.caption(t("Minimo {n} caratteri. Le password non si possono rileggere (sono salvate solo "
                 "come impronta): se l'utente la dimentica, qui ne imposti una nuova.", n=users.MIN_PASSWORD))


def _edit_admin() -> None:
    st.dialog(t("Il tuo account"))(_edit_admin_body)()


def _keep_session() -> None:
    """Dopo aver cambiato il proprio nome o la propria password l'amministratore resta collegato in questa finestra
    (e il suo «resta connesso», se c'era, viene rinnovato); le altre sessioni si chiudono."""
    st.session_state[login.VERSION_KEY] = auth.version(users.ADMIN)
    try:
        had_cookie = bool(st.context.cookies.get(auth.COOKIE_NAME))
    except Exception:
        had_cookie = False
    if had_cookie:
        st.session_state[login.SET_COOKIE_KEY] = auth.make_token(users.ADMIN)


def _edit_admin_body() -> None:
    st.markdown(t("**Nome utente** (serve per entrare; maiuscole e minuscole non contano)"))
    with st.form("ut_name_admin", border=False):
        name = st.text_input(t("Nome utente"), value=users.admin_name(), key="ut_e_name_admin",
                             label_visibility="collapsed")
        if st.form_submit_button(t("Salva il nome"), icon=":material/badge:"):
            try:
                users.rename_admin(name)
                _keep_session()
                _flash(t("Nome cambiato in «{name}».", name=users.admin_name()))
                st.rerun()
            except users.UserError as e:
                st.error(str(e))
    st.divider()
    st.markdown("**" + t("Nuova password") + "**")
    with st.form("ut_pwd_admin", border=False):
        p1 = st.text_input(t("Nuova password"), type="password", key="ut_e_p1_admin", autocomplete="new-password")
        p2 = st.text_input(t("Ripeti la password"), type="password", key="ut_e_p2_admin", autocomplete="new-password")
        if st.form_submit_button(t("Cambia la password"), icon=":material/key:"):
            try:
                users.set_admin_password(p1, p2)
                _keep_session()
                _flash(t("La tua password è cambiata: sugli altri browser dovrai rientrare con quella nuova."))
                st.rerun()
            except users.UserError as e:
                st.error(str(e))
    st.caption(t("Minimo {n} caratteri. La password non si può recuperare: se la dimentichi non c'è modo di "
                 "rientrare come amministratore, quindi salvala in un posto sicuro.", n=users.MIN_PASSWORD))


def _delete(uid: str) -> None:
    st.dialog(t("Elimina utente"))(_delete_body)(uid)


def _delete_body(uid: str) -> None:
    u = users.get(uid)
    if not u:
        st.error(t("Utente non trovato."))
        return
    st.markdown(t("Vuoi eliminare **{name}**? Non potrà più entrare.", name=ui.esc(u["name"])))
    wipe = st.checkbox(t("Cancella anche i suoi dati (database, backup ed estratti nella sua cartella)"),
                       key=f"ut_d_wipe_{uid}")
    if u.get("data_dir"):
        st.caption(t("Il suo database è in una cartella scelta da lui ({path}): quella non viene toccata.",
                     path=u["data_dir"]))
    sure = st.checkbox(t("Sì, sono sicuro"), key=f"ut_d_sure_{uid}")
    if st.button(t("Elimina"), type="primary", icon=":material/person_remove:", disabled=not sure, key=f"ut_d_go_{uid}"):
        _flash(users.delete(uid, delete_data=wipe))
        st.rerun()


def _user_card(uid: str, u: dict) -> None:
    with st.container(border=True, key=f"ut_card_{uid}"):
        badge = (f":violet-badge[:material/science: {t('Prova: dati fittizi')}]" if u.get("demo")
                 else f":blue-badge[:material/person: {t('Utente')}]")
        st.markdown(f"**{ui.esc(u['name'])}** &nbsp; {badge}")
        n = users.db_count(uid)
        st.caption(t("Movimenti: {n} · ultimo accesso: {last} · creato il {created}",
                     n=t("ancora nessuno") if n is None else ui.fmt_num(n, 0), last=_when(u.get("last_login")),
                     created=_when(u.get("created"))[:10]))
        st.caption(t("Cartella dati: {path}", path=f"`{users.data_dir(uid)}`"))
        with st.container(horizontal=True, gap="small"):
            if st.button(t("Modifica nome o password"), key=f"ut_edit_{uid}", icon=":material/edit:"):
                _edit(uid)
            if st.button(t("Elimina"), key=f"ut_del_{uid}", icon=":material/delete:"):
                _delete(uid)


def render() -> None:
    style.header(t("Utenti"), t("Chi può usare MoneyBoard: ognuno vede e modifica solo i propri dati"))
    if not db.is_admin():
        st.error(t("Solo l'amministratore può gestire gli utenti."), icon=":material/block:")
        return
    msg = st.session_state.pop("ut_flash", None)
    if msg:
        st.success(msg, icon=":material/check_circle:")

    left, right = st.columns([3, 2], gap="large")
    with right:
        st.subheader(t("Nuovo utente"))
        n = st.session_state.setdefault("ut_form_n", 0)  # cambia dopo ogni creazione: il modulo si svuota
        with st.form(f"ut_new_{n}", clear_on_submit=False):
            name = st.text_input(t("Nome utente"), key=f"ut_n_name_{n}", placeholder=t("es. Marco"),
                                 help=t("Serve per entrare. Maiuscole e minuscole non contano."))
            p1 = st.text_input("Password", type="password", key=f"ut_n_p1_{n}", autocomplete="new-password",
                               help=t("Almeno {n} caratteri.", n=users.MIN_PASSWORD))
            p2 = st.text_input(t("Ripeti la password"), type="password", key=f"ut_n_p2_{n}", autocomplete="new-password")
            demo = st.checkbox(t("Account di prova con dati fittizi"), key=f"ut_n_demo_{n}",
                               help=t("Parte con circa 450 movimenti inventati, utile per far provare l'app. "
                                      "Altrimenti l'utente parte vuoto e importa i suoi estratti."))
            sent = st.form_submit_button(t("Crea utente"), type="primary", icon=":material/person_add:",
                                         width="stretch")
        if sent:
            try:
                uid = users.create(name, p1, p2, demo=demo)
                st.session_state["ut_form_n"] = n + 1
                _flash(t("Utente «{name}» creato: può entrare subito con il nome e la password che hai scelto.",
                         name=users.get(uid)["name"]))
                st.rerun()
            except users.UserError as e:
                st.error(str(e))
        st.caption(t("Ogni utente può fare tutto quello che fai tu (importare, modificare, spostare il suo database "
                     "in una cartella a scelta), ma solo sui propri dati: le cartelle degli altri utenti e quelle "
                     "dell'app non si possono usare. Solo tu puoi creare, rinominare ed eliminare gli utenti."))

    with left:
        listing = users.all_users()
        st.subheader(t("Utenti ({n})", n=len(listing) + 1))
        with st.container(border=True, key="ut_card_admin"):
            st.markdown(f"**{ui.esc(users.admin_name())}** &nbsp; "
                        f":orange-badge[:material/shield_person: {t('Amministratore')}]")
            st.caption(t("Cartella dati: {path}", path=f"`{users.admin_data_dir()}`"))
            if st.button(t("Modifica nome o password"), key="ut_edit_admin", icon=":material/edit:"):
                _edit_admin()
        for uid, u in sorted(listing.items(), key=lambda kv: kv[1].get("name", "").casefold()):
            _user_card(uid, u)
