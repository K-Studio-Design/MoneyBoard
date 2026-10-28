"""Impostazioni → Email e promemoria: promemoria degli addebiti in arrivo (nell'app e via email) e riepilogo
mensile via email, con il proprio server di posta."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import db, demo_mode, i18n, notify
from core.i18n import t

VER = "_mail_ver"


def render_tab() -> None:
    st.markdown("**" + t("Promemoria delle scadenze") + "**")
    days = st.slider(t("Avvisami degli addebiti ricorrenti (bollette, abbonamenti, rate…) con questo anticipo"),
                     0, 14, notify.reminder_days(), key="rem_days", format="%d " + t("giorni"),
                     help=t("Compaiono tra gli Avvisi e, se attivi le email, ti arriva un promemoria. 0 = spenti."))
    if days != notify.reminder_days():
        db.set_setting(notify.REMINDER_DAYS, str(days))
        st.rerun()
    st.caption(t("Le date arrivano dai pagamenti ricorrenti trovati in Abbonamenti."))
    st.divider()

    st.markdown("**" + t("Email") + "**")
    if demo_mode.enabled():
        st.info(t("Nella demo online le email sono disattivate."), icon=":material/block:")
        return
    cfg = notify.config()
    ver = st.session_state.setdefault(VER, 0)
    enabled = st.toggle(t("Mandami le email"), value=cfg["enabled"], key=f"mail_on_{ver}")
    c1, c2 = st.columns(2)
    monthly = c1.checkbox(t("Riepilogo del mese appena finito (il giorno 1)"), value=cfg["monthly"],
                          key=f"mail_monthly_{ver}")
    reminders = c2.checkbox(t("Promemoria degli addebiti in arrivo"), value=cfg["reminders"], key=f"mail_rem_{ver}",
                            disabled=days == 0)
    presets = list(notify.PRESETS)
    preset = st.selectbox(t("Il tuo servizio di posta"), presets, key=f"mail_preset_{ver}",
                          index=next((i for i, k in enumerate(presets) if notify.PRESETS[k][1] == cfg["host"]),
                                     len(presets) - 1),
                          format_func=lambda k: t(notify.PRESETS[k][0]))
    p_name, p_host, p_port, p_sec = notify.PRESETS[preset]
    use_preset = preset != "altro"
    c1, c2, c3 = st.columns([3, 1, 1.4])
    host = c1.text_input(t("Server SMTP"), value=p_host if use_preset else cfg["host"], key=f"mail_host_{ver}_{preset}",
                         disabled=use_preset)
    port = c2.number_input(t("Porta"), 1, 65535, value=int(p_port if use_preset else cfg["port"]),
                           key=f"mail_port_{ver}_{preset}", disabled=use_preset)
    secs = list(notify.SECURITY)
    sec = c3.selectbox(t("Sicurezza"), secs, index=secs.index(p_sec if use_preset else cfg["security"]),
                       format_func=lambda k: t(notify.SECURITY[k]), key=f"mail_sec_{ver}_{preset}", disabled=use_preset)
    c1, c2 = st.columns(2)
    user = c1.text_input(t("Indirizzo (utente)"), value=cfg["user"], key=f"mail_user_{ver}",
                         placeholder="nome@gmail.com", autocomplete="off")
    pwd = c2.text_input(t("Password per le app"), type="password", key=f"mail_pwd_{ver}", autocomplete="new-password",
                        placeholder=t("già salvata") if cfg["password"] else "",
                        help=t("Lascia vuoto per tenere quella già salvata."))
    to = st.text_input(t("Manda le email a"), value=cfg["to"] or cfg["user"], key=f"mail_to_{ver}",
                       help=t("Uno o più indirizzi, separati da virgola."))
    if use_preset:
        st.caption(t("Con {s} serve la verifica in due passaggi e una «password per le app», creata dalle impostazioni "
                     "di sicurezza del tuo account: la password normale non funziona.", s=p_name))
    st.caption(t("La password resta solo nel database su questo computer. Le email partono quando l'app è aperta "
                 "(o alla prima apertura utile): se l'app gira sempre, per esempio su un NAS, arrivano puntuali."))
    new = {"enabled": enabled, "monthly": monthly, "reminders": reminders, "host": host.strip(), "port": int(port),
           "security": sec, "user": user.strip(), "sender": user.strip(), "to": to.strip(),
           "password": pwd if pwd else cfg["password"]}
    b1, b2, b3 = st.columns(3)
    if b1.button(t("Salva"), type="primary", icon=":material/check:", key=f"mail_save_{ver}", width="stretch"):
        errs = notify.problems(new) if enabled else []
        if errs:
            st.error(" ".join(errs))
        else:
            notify.save_config(new)
            st.session_state[VER] = ver + 1
            st.toast(t("Impostazioni email salvate"), icon=":material/check_circle:")
            st.rerun()
    if b2.button(t("Manda un'email di prova"), icon=":material/send:", key=f"mail_test_{ver}", width="stretch"):
        try:
            with st.spinner(t("Invio…")):
                notify.send(new, t("MoneyBoard: email di prova"),
                            notify._page(t("Funziona!"), t("Le email di MoneyBoard arriveranno qui."), []),
                            t("Le email di MoneyBoard arriveranno qui."))
            st.success(t("Email di prova inviata a {to}.", to=", ".join(notify.recipients(new))))
        except notify.NotifyError as e:
            st.error(str(e))
    prev = pd.Period(pd.Timestamp.today(), freq="M") - 1
    if b3.button(t("Manda ora il riepilogo di {m}", m=i18n.month(prev.month)), icon=":material/summarize:",
                 key=f"mail_month_{ver}", width="stretch"):
        try:
            content = notify.monthly_summary(prev.year, prev.month)
            if content is None:
                st.warning(t("Nel mese scorso non ci sono movimenti."))
            else:
                with st.spinner(t("Invio…")):
                    notify.send(new, *content)
                st.success(t("Riepilogo inviato."))
        except notify.NotifyError as e:
            st.error(str(e))
    err = notify.last_error()
    if err and cfg["enabled"]:
        st.caption(t("Ultimo errore ({d}): {e}", d=str(err.get("when", ""))[:16].replace("T", " "), e=err.get("error")))
