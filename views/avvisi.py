"""Avvisi: addebiti doppi, spese insolite, categorie sopra la media, abbonamenti che cambiano."""
from __future__ import annotations

from datetime import date

import streamlit as st

from core import alerts
from core.i18n import t
from views import abbonamenti, focus, style, ui


def alert_html(a: alerts.Alert) -> str:
    return (f'<div class="as-alert"><div class="ic {a.level}">{style.e(a.icon)}</div>'
            f'<div><div class="t">{style.e(a.title)}</div><div class="x">{style.e(a.text)}</div></div></div>')


def open_alert(a: alerts.Alert) -> None:
    if a.kind == "budget" and not a.category:
        from views import nav
        if "budget" in nav.PAGES:
            st.switch_page(nav.PAGES["budget"])
    elif a.tx_id is not None:
        focus.open_focus(a.tx_id)
    elif a.sid:
        abbonamenti.open_series(a.sid)
    elif a.category:
        today = date.today()
        focus.open_category(a.category, today.replace(day=1), today)


def _row(a: alerts.Alert, key: str, dismissed: bool = False) -> None:
    if dismissed:
        c1, c2, c3, c4 = st.columns([8, 1.3, 1.3, 1.3], vertical_alignment="center")
    else:
        c1, c2, c3 = st.columns([8, 1.3, 1.3], vertical_alignment="center")
    c1.html(alert_html(a))
    if c2.button(t("Apri"), key=f"{key}_open", icon=":material/open_in_full:", width="stretch"):
        open_alert(a)
    if dismissed:
        if c3.button(t("Ripristina"), key=f"{key}_back", width="stretch"):
            alerts.dismiss(a.aid, False)
            st.rerun()
        if c4.button(t("Elimina"), key=f"{key}_del", icon=":material/delete:", width="stretch"):
            alerts.delete(a.aid)
            st.rerun()
    elif c3.button(t("Ignora"), key=f"{key}_hide", icon=":material/done:", width="stretch",
                   help=t("Segna come visto: non comparirà più")):
        alerts.dismiss(a.aid)
        st.rerun()


def render():
    style.header(t("Avvisi"), ui.view_summary())
    items = ui.active_alerts()
    every = ui.active_alerts(include_dismissed=True)
    gone = [a for a in every if a.aid in alerts.dismissed()]
    important = [a for a in items if a.level in ("alta", "media")]
    info = [a for a in items if a.level == "info"]

    if not items:
        st.success(t("Nessun avviso: niente addebiti doppi, spese fuori dal solito o abbonamenti cambiati."),
                   icon=":material/verified:")
    if important:
        with style.card("avvisi_imp"):
            st.subheader(t("Da controllare"))
            for i, a in enumerate(important):
                _row(a, f"al_imp_{a.aid}")
                if i < len(important) - 1:
                    st.divider()
    if info:
        with style.card("avvisi_info"):
            st.subheader(t("Da sapere"))
            for i, a in enumerate(info):
                _row(a, f"al_info_{a.aid}")
                if i < len(info) - 1:
                    st.divider()
    st.caption(t("Controllo gli ultimi 60 giorni: addebiti doppi nello stesso giorno, spese molto più alte del solito "
                 "presso lo stesso negozio, le spese più alte dell'anno, categorie già sopra la media del mese, "
                 "abbonamenti nuovi, cambiati di prezzo o non più addebitati. In più: gli addebiti in arrivo nei "
                 "prossimi giorni e i budget all'80% o superati (si regola in Impostazioni → Email e promemoria)."))
    if gone:
        with st.expander(t("Ignorati ({n})", n=len(gone)), icon=":material/done_all:"):
            st.caption(t("«Elimina» li toglie anche da qui. Possono ricomparire solo se i movimenti vengono "
                         "caricati di nuovo (per esempio dopo averli cancellati e reimportati)."))
            for a in gone:
                _row(a, f"al_gone_{a.aid}", dismissed=True)
            if len(gone) > 1 and st.button(t("Elimina tutti gli ignorati ({n})", n=len(gone)), key="al_del_all",
                                           icon=":material/delete_sweep:", type="tertiary"):
                alerts.delete([a.aid for a in gone])
                st.rerun()


def dashboard_card(page) -> None:
    """Riquadro per la Panoramica: i primi avvisi e il collegamento alla pagina."""
    items = ui.active_alerts()
    if not items:
        return
    with style.card("dash_alerts"):
        st.subheader(t("Avvisi ({n})", n=len(items)))
        st.html("".join(f'<div style="margin-bottom:.7rem">{alert_html(a)}</div>' for a in items[:3]))
        st.page_link(page, label=t("Vedi tutti gli avvisi") if len(items) > 3 else t("Apri gli avvisi"),
                     icon=":material/arrow_forward:")
