"""Tema chiaro / scuro / automatico selezionabile dall'app (scelta salvata nel database).

Streamlit invia il tema al browser all'inizio di ogni esecuzione, leggendo la configurazione:
qui la si imposta a runtime. Per «Auto» si definiscono entrambe le varianti (theme.light / theme.dark)
e il browser sceglie in base a Windows; per Chiaro/Scuro si fissa theme.base.
"""
import streamlit as st
from streamlit import config as _st_config

from core import db
from core.i18n import t
from views.style import FONT_BODY, FONT_DISPLAY, GLASS_THEME_COLORS, PALETTE

# font installati su Windows (nessun download da internet)
FONT = FONT_BODY
HEADING_FONT = FONT_DISPLAY


def _colors(p: dict) -> dict:
    return {
        "primaryColor": p["accent"],
        "backgroundColor": p["bg"],
        "secondaryBackgroundColor": p["field"],
        "textColor": p["ink"],
        "borderColor": p["line"],
        "linkColor": p["accent"],
        "dataframeHeaderBackgroundColor": p["field"],
        "sidebar.backgroundColor": p["surface"],
        "sidebar.secondaryBackgroundColor": p["field"],
        "font": FONT,
        "headingFont": HEADING_FONT,
        "baseRadius": "0.75rem",
        "showWidgetBorder": True,
    }


VARIANTS = {"light": _colors(PALETTE["light"]), "dark": _colors(PALETTE["dark"]),
            "glass": _colors(GLASS_THEME_COLORS)}
KEYS = list(VARIANTS["light"])
MODES = ["chiaro", "scuro", "auto", "glass"]
LABELS = {"chiaro": ":material/light_mode:", "scuro": ":material/dark_mode:", "auto": ":material/contrast:",
          "glass": ":material/blur_on:"}
HELP = "Tema: chiaro, scuro, automatico (segue Windows) oppure Liquid Glass"
# per i widget nativi il tema glass è una variante scura
_BASE = {"chiaro": "light", "scuro": "dark", "glass": "dark"}


def _target(mode: str) -> dict:
    """Valori desiderati per ogni opzione di configurazione del tema."""
    want = {}
    fixed = _BASE.get(mode)
    for k in ["base"] + KEYS:
        want[f"theme.{k}"] = None
    for variant in ("light", "dark"):
        for k in KEYS:
            want[f"theme.{variant}.{k}"] = None if fixed else VARIANTS[variant][k]
    if fixed:
        want["theme.base"] = fixed
        colors = VARIANTS["glass"] if mode == "glass" else VARIANTS[fixed]
        for k in KEYS:
            want[f"theme.{k}"] = colors[k]
    return want


def _safe_get(key):
    try:
        return _st_config.get_option(key)
    except Exception:
        return "__missing__"


def _apply(mode: str) -> None:
    for k, v in _target(mode).items():
        if _safe_get(k) != "__missing__":
            _st_config.set_option(k, v)


def current_mode() -> str:
    mode = db.get_setting("theme", "scuro")
    return mode if mode in MODES else "scuro"


def _is_applied(mode: str) -> bool:
    return all(_safe_get(k) in ("__missing__", v) for k, v in _target(mode).items())


def ensure_theme() -> None:
    """Da chiamare dopo st.navigation: se la configurazione era diversa la aggiorna e riesegue una volta."""
    mode = current_mode()
    if not _is_applied(mode):
        _apply(mode)
        st.rerun()


def theme_switcher() -> None:
    mode = current_mode()
    choice = st.segmented_control(
        t("Tema"), MODES, default=mode, format_func=lambda m: LABELS[m], key="theme_switch",
        label_visibility="collapsed", help=t(HELP),
    )
    if choice and choice != mode:
        db.set_setting("theme", choice)
        _apply(choice)
        st.rerun()
