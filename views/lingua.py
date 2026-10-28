"""Scelta della lingua (italiano / inglese): all'avvio, nella schermata di accesso e nelle impostazioni."""
from __future__ import annotations

import streamlit as st

from core import db, i18n
from core.i18n import t

_SET_COOKIE = "_lang_set_cookie"
_CHOSEN_AT_LOGIN = "_lang_chosen_login"   # lingua cambiata nella schermata di accesso: vale anche dopo
_SYNCED = "_lang_cookie_synced"


def _cookie_lang() -> str | None:
    try:
        v = st.context.cookies.get(i18n.COOKIE_NAME)
    except Exception:
        v = None
    return v if v in i18n.LANGS else None


def init(authed: bool) -> None:
    """Da chiamare a ogni esecuzione, subito dopo il controllo dell'accesso: decide la lingua della sessione.
    Dopo l'accesso vale quella salvata nel profilo dell'utente (se non l'ha mai scelta, quella usata nella
    schermata di accesso, che viene salvata); prima dell'accesso quella scelta lì (ricordata in un cookie)."""
    from core import demo_mode
    current = st.session_state.get(i18n.LANG_KEY)
    default = "en" if demo_mode.enabled() else i18n.DEFAULT    # la demo online parte in inglese
    if authed:
        saved = db.get_setting(i18n.SETTING_KEY, "") or ""
        chosen = st.session_state.pop(_CHOSEN_AT_LOGIN, None)
        if chosen in i18n.LANGS:
            code = chosen
            db.set_setting(i18n.SETTING_KEY, code)
        elif saved in i18n.LANGS:
            code = saved
        else:
            code = current if current in i18n.LANGS else (_cookie_lang() or default)
            db.set_setting(i18n.SETTING_KEY, code)
    else:
        code = current if current in i18n.LANGS else (_cookie_lang() or default)
    st.session_state[i18n.LANG_KEY] = code
    if authed and not st.session_state.get(_SYNCED):
        # il browser ricorda la lingua dell'ultimo utente: la schermata di accesso si apre già in quella lingua
        st.session_state[_SYNCED] = True
        if _cookie_lang() != code:
            st.session_state[_SET_COOKIE] = code


def set_language(code: str, save: bool = True) -> None:
    if code not in i18n.LANGS:
        return
    st.session_state[i18n.LANG_KEY] = code
    st.session_state[_SET_COOKIE] = code
    if save:
        db.set_setting(i18n.SETTING_KEY, code)
    else:
        st.session_state[_CHOSEN_AT_LOGIN] = code
    st.cache_data.clear()  # alcuni testi (avvisi, ricorrenze) sono calcolati e messi in cache


def cookie_script() -> None:
    """Ricorda la lingua nel browser (vale anche per la schermata di accesso)."""
    code = st.session_state.pop(_SET_COOKIE, None)
    if code:
        st.html(f"<script>document.cookie = '{i18n.COOKIE_NAME}={code}; max-age={400 * 86400}; path=/; "
                "SameSite=Strict';</script>", unsafe_allow_javascript=True)


def _on_change(key: str, save: bool) -> None:
    code = st.session_state.get(key)
    if code:  # un clic sulla lingua già scelta la «deseleziona»: in quel caso non cambia nulla
        set_language(code, save=save)


def selector(key: str, save: bool = True, label: str | None = None, compact: bool = False) -> None:
    """Interruttore Italiano / English."""
    st.session_state[key] = i18n.lang()
    st.segmented_control(
        label if label is not None else t("Lingua"), list(i18n.LANGS),
        format_func=(lambda c: c.upper()) if compact else i18n.LANGS.get,
        key=key, on_change=_on_change, args=(key, save), selection_mode="single",
        label_visibility="collapsed" if compact or label == "" else "visible",
        help=None if compact else t("Lingua dell'app: vale per te, su tutti i dispositivi."))
