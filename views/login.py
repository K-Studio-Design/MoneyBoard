"""Schermata di accesso e gestione della sessione (accesso, «resta connesso», uscita)."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from core import auth, db, i18n, users
from core.i18n import t

AUTH_KEY = "_auth_ok"
SET_COOKIE_KEY = "_auth_set_cookie"
CLEAR_COOKIE_KEY = "_auth_clear_cookie"
LOGGED_OUT_KEY = "_auth_logged_out"
VERSION_KEY = "_auth_version"
_BG = Path(__file__).resolve().parent.parent / "assets" / "login_bg.svg"

_MARK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="56" height="56">
<defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7C5CFC"/>
<stop offset="1" stop-color="#F0627E"/></linearGradient></defs>
<rect x="2" y="2" width="40" height="40" rx="12" fill="url(#lg)"/>
<rect x="11" y="13" width="22" height="16" rx="4" fill="none" stroke="#fff" stroke-width="2.6"/>
<path d="M11 18h22" stroke="#fff" stroke-width="2.6"/><circle cx="27.5" cy="24" r="1.9" fill="#fff"/></svg>"""


def is_authenticated() -> bool:
    """Accesso già fatto in questa sessione, oppure cookie «resta connesso» valido (se non si è appena usciti).
    Imposta anche l'utente della sessione (st.session_state[db.USER_KEY]), che decide quale database si usa."""
    if st.session_state.get(AUTH_KEY):
        user = st.session_state.get(db.USER_KEY)
        if auth.exists(user) and st.session_state.get(VERSION_KEY) == auth.version(user):
            return True
        # utente eliminato o password cambiata dall'Admin: la sessione si chiude
        logout()
        return False
    if st.session_state.get(LOGGED_OUT_KEY):
        return False
    try:
        token = st.context.cookies.get(auth.COOKIE_NAME)
    except Exception:
        token = None
    user = auth.token_user(token) if token else None
    if user:
        _start_session(user)
        return True
    return False


def _start_session(user: str) -> None:
    st.session_state[db.USER_KEY] = user
    st.session_state[VERSION_KEY] = auth.version(user)
    st.session_state[AUTH_KEY] = True


def logout() -> None:
    """Esce: svuota tutta la sessione (nessun dato dell'utente resta in memoria) e cancella il «resta connesso»."""
    code = st.session_state.get(i18n.LANG_KEY)
    st.session_state.clear()
    if code:
        st.session_state[i18n.LANG_KEY] = code  # la schermata di accesso resta nella lingua in uso
    st.session_state[AUTH_KEY] = False
    st.session_state[LOGGED_OUT_KEY] = True
    st.session_state[CLEAR_COOKIE_KEY] = True


def cookie_scripts() -> None:
    """Scrive o cancella il cookie «resta connesso» nel browser (da chiamare a ogni esecuzione)."""
    tok = st.session_state.pop(SET_COOKIE_KEY, None)
    if tok:
        st.html(f"<script>document.cookie = '{auth.COOKIE_NAME}={tok}; max-age={auth.REMEMBER_DAYS * 86400}; "
                "path=/; SameSite=Strict';</script>", unsafe_allow_javascript=True)
    if st.session_state.pop(CLEAR_COOKIE_KEY, None):
        st.html(f"<script>document.cookie = '{auth.COOKIE_NAME}=; max-age=0; path=/; SameSite=Strict';</script>",
                unsafe_allow_javascript=True)


def _background_css() -> str:
    try:
        svg = base64.b64encode(_BG.read_bytes()).decode()
        art = f'url("data:image/svg+xml;base64,{svg}") center / cover no-repeat,'
    except OSError:
        art = ""
    mark = base64.b64encode(_MARK.encode()).decode()
    return f"""<style>
.as-login-mark {{ width: 60px; height: 60px; margin: 0 auto; background: url("data:image/svg+xml;base64,{mark}")
  center / contain no-repeat; filter: drop-shadow(0 10px 18px rgba(124,92,252,0.45)); }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{
  display: none !important; }}
.stApp, [data-testid="stAppViewContainer"] {{
  background: {art}
    radial-gradient(circle at 12% 18%, rgba(240,98,126,0.55), transparent 42%),
    radial-gradient(circle at 88% 82%, rgba(20,174,158,0.50), transparent 45%),
    linear-gradient(135deg, #3B1FA8 0%, #6A3DE8 45%, #B5459A 100%) !important;
  background-attachment: fixed !important; }}
[data-testid="stMain"], [data-testid="stHeader"] {{ background: transparent !important; }}
.block-container {{ padding-top: max(7vh, 2.5rem) !important; }}
.st-key-login_card {{ width: 100% !important; max-width: 430px; margin: 0 auto; padding: 2.1rem 2rem 1.6rem;
  border-radius: 26px; border: 1px solid rgba(255,255,255,0.35);
  background: color-mix(in srgb, var(--as-surface) 90%, transparent);
  -webkit-backdrop-filter: blur(28px) saturate(160%); backdrop-filter: blur(28px) saturate(160%);
  box-shadow: 0 30px 80px rgba(20,10,60,0.45), inset 0 1px 0 rgba(255,255,255,0.35);
  animation: as-login-in .45s ease-out both; }}
@keyframes as-login-in {{ from {{ opacity: 0; transform: translateY(14px) scale(.985); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{ .st-key-login_card {{ animation: none; }} }}
.as-login-head {{ text-align: center; margin-bottom: .6rem; }}
.as-login-head h1 {{ font-size: 1.65rem !important; font-weight: 800 !important; margin: .7rem 0 .15rem 0 !important;
  padding: 0 !important; letter-spacing: -0.02em; }}
.as-login-head p {{ color: var(--as-muted); margin: 0; font-size: .92rem; }}
.st-key-login_card [data-testid="stForm"] {{ border: none; padding: 0; }}
.st-key-login_card [data-testid="stFormSubmitButton"] button {{ min-height: 2.9rem; font-weight: 700;
  background: linear-gradient(135deg, #7C5CFC, #F0627E) !important; border: none !important; color: #fff !important;
  box-shadow: 0 10px 24px rgba(124,92,252,0.35); }}
.st-key-login_card [data-testid="stFormSubmitButton"] button:hover {{ filter: brightness(1.06); }}
.as-login-foot {{ text-align: center; color: var(--as-muted); font-size: .78rem; margin-top: .9rem; }}
.as-login-foot span {{ display: inline-flex; align-items: center; gap: .35rem; }}
@media (max-width: 640px) {{ .st-key-login_card {{ padding: 1.6rem 1.2rem 1.2rem; border-radius: 22px; }}
  .block-container {{ padding-top: 4vh !important; }} }}
</style>"""


def _setup() -> None:
    """Prima apertura: si crea l'amministratore (il proprietario dell'app) con nome e password a scelta."""
    st.html('<div class="as-login-head"><div class="as-login-mark" role="img" aria-label="MoneyBoard"></div>'
            f'<h1>{t("Benvenuto in MoneyBoard")}</h1>'
            f'<p>{t("Prima di iniziare crea il tuo account: sarai l’amministratore dell’app.")}</p></div>')
    with st.form("setup_form", border=False, enter_to_submit=True):
        name = st.text_input(t("Nome utente"), key="setup_user", autocomplete="username", icon=":material/person:",
                             placeholder=t("es. Marco"), help=t("Serve per entrare. Maiuscole e minuscole non contano."))
        p1 = st.text_input("Password", type="password", key="setup_p1", autocomplete="new-password",
                           icon=":material/lock:", placeholder="Password",
                           help=t("Almeno {n} caratteri.", n=users.MIN_PASSWORD))
        p2 = st.text_input(t("Ripeti la password"), type="password", key="setup_p2", autocomplete="new-password",
                           icon=":material/lock:", placeholder=t("Ripeti la password"))
        remember = st.checkbox(t("Resta connesso su questo browser per 30 giorni"), key="setup_remember")
        sent = st.form_submit_button(t("Crea l'account"), type="primary", width="stretch",
                                     icon=":material/person_add:")
    if sent:
        try:
            name = users.create_admin(name, p1, p2)
        except users.UserError as e:
            st.error(str(e), icon=":material/error:")
            if not auth.needs_setup():   # creato nel frattempo da un'altra finestra
                st.rerun()
            return
        for k in ("setup_p1", "setup_p2"):
            st.session_state.pop(k, None)
        st.session_state.pop(LOGGED_OUT_KEY, None)
        _start_session(users.ADMIN)
        db.set_setting("profile_name", name)
        if remember:
            st.session_state[SET_COOKIE_KEY] = auth.make_token(users.ADMIN)
        st.rerun()
    st.caption(t("La password non si può recuperare: salvala in un posto sicuro. Dopo potrai creare altri "
                 "utenti (menu dell'avatar → Utenti), ognuno con i suoi dati separati."))


def render() -> None:
    """Disegna la schermata di accesso (da chiamare quando is_authenticated() è False, poi st.stop()).
    Alla prima apertura, invece dell'accesso, chiede di creare l'account dell'amministratore."""
    st.html(_background_css())
    with st.container(key="login_card"):
        from views import lingua
        with st.container(key="login_lang", horizontal=True, horizontal_alignment="right"):
            lingua.selector("login_lang_sel", save=False, compact=True)
        if auth.needs_setup():
            _setup()
            st.html(f'<div class="as-login-foot"><span>🔒 {t("I tuoi dati restano solo su questo computer")}</span></div>')
            return
        st.html('<div class="as-login-head"><div class="as-login-mark" role="img" aria-label="MoneyBoard"></div><h1>MoneyBoard</h1>'
                f'<p>{t("Bentornato! Accedi per vedere le tue finanze.")}</p></div>')
        wait = auth.locked_for()
        with st.form("login_form", border=False, enter_to_submit=True):
            user = st.text_input(t("Nome utente"), key="login_user", autocomplete="username", icon=":material/person:",
                                 placeholder=t("Nome utente"))
            pwd = st.text_input("Password", type="password", key="login_pwd", autocomplete="current-password",
                                icon=":material/lock:", placeholder="Password")
            remember = st.checkbox(t("Resta connesso su questo browser per 30 giorni"), key="login_remember")
            sent = st.form_submit_button(t("Accedi"), type="primary", width="stretch", icon=":material/login:")
        if sent:
            wait = auth.locked_for()
            if wait:
                st.error(t("Troppi tentativi sbagliati: riprova tra {s} secondi.", s=wait), icon=":material/timer:")
            elif (who := auth.check(user, pwd)):
                auth.register_success()
                st.session_state.pop(LOGGED_OUT_KEY, None)
                st.session_state.pop("login_pwd", None)
                _start_session(who)
                users.touch_login(who)
                if remember:
                    st.session_state[SET_COOKIE_KEY] = auth.make_token(who)
                st.rerun()
            else:
                left = auth.register_failure()
                if left:
                    st.error(t("Nome utente o password non corretti. Tentativi rimasti: {n}.", n=left),
                             icon=":material/error:")
                else:
                    st.error(t("Troppi tentativi sbagliati: accesso bloccato per {s} secondi.", s=auth.LOCK_SECONDS),
                             icon=":material/timer:")
        elif wait:
            st.warning(t("Accesso bloccato per troppi tentativi: riprova tra {s} secondi.", s=wait),
                       icon=":material/timer:")
        st.html(f'<div class="as-login-foot"><span>🔒 {t("I tuoi dati restano solo su questo computer")}</span></div>')
