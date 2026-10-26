"""Lingua dell'interfaccia: italiano (predefinita) o inglese.

Uso: ``t("Testo in italiano")`` oppure, con valori, ``t("{n} movimenti", n=5)``.
Il testo italiano fa da chiave: le traduzioni inglesi stanno in core/i18n_en.py. Se una traduzione manca si
mostra l'italiano (mai un errore).

La lingua scelta da ogni utente è salvata nel suo database (impostazione «language»); quella della sessione in
corso sta in st.session_state[LANG_KEY]. Prima dell'accesso vale quella scelta nella schermata di login
(ricordata in un cookie del browser).

Restano in italiano solo i dati: nomi delle categorie, dei conti e le descrizioni dei movimenti (si possono
rinominare dall'app), e gli indirizzi delle pagine.
"""
from __future__ import annotations

LANGS = {"it": "Italiano", "en": "English"}
DEFAULT = "it"
LANG_KEY = "_mb_lang"
SETTING_KEY = "language"
COOKIE_NAME = "moneyboard_lang"
_forced: str | None = None

MONTHS = {"it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
                 "ottobre", "novembre", "dicembre"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"]}
MONTHS_SHORT = {"it": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"],
                "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
WEEKDAYS = {"it": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
            "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
WEEKDAYS_SHORT = {"it": ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
                  "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}


def set_override(code: str | None) -> None:
    """Per test e script fuori da Streamlit."""
    global _forced
    _forced = code if code in LANGS else None


def lang() -> str:
    if _forced:
        return _forced
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx(suppress_warning=True) is None:
            return DEFAULT
        import streamlit as st
        code = st.session_state.get(LANG_KEY)
    except Exception:
        return DEFAULT
    return code if code in LANGS else DEFAULT


def is_en() -> bool:
    return lang() == "en"


def t(text: str, /, **values) -> str:
    """Traduce `text` (italiano) nella lingua attuale e, se ci sono, inserisce i valori ({nome})."""
    out = text
    if lang() == "en":
        from core.i18n_en import EN
        out = EN.get(text, text)
    return out.format(**values) if values else out


def month(m: int, short: bool = False) -> str:
    return (MONTHS_SHORT if short else MONTHS)[lang()][m - 1]


def weekday(d: int, short: bool = False) -> str:
    return (WEEKDAYS_SHORT if short else WEEKDAYS)[lang()][d]


def date_long(d) -> str:
    """'21 ottobre 2026' / 'October 21, 2026'."""
    if lang() == "en":
        return f"{MONTHS['en'][d.month - 1]} {d.day}, {d.year}"
    return f"{d.day} {MONTHS['it'][d.month - 1]} {d.year}"


def date_short(d) -> str:
    """'21 ott 2026' / 'Oct 21, 2026'."""
    if lang() == "en":
        return f"{MONTHS_SHORT['en'][d.month - 1]} {d.day}, {d.year}"
    return f"{d.day} {MONTHS_SHORT['it'][d.month - 1].lower()} {d.year}"


def day_month(d, short: bool = True) -> str:
    """'21 ott' / 'Oct 21' (con short=False: '21 ottobre' / 'October 21')."""
    names = (MONTHS_SHORT if short else MONTHS)[lang()]
    if lang() == "en":
        return f"{names[d.month - 1]} {d.day}"
    return f"{d.day} {names[d.month - 1].lower()}"


def ordinal(n: int) -> str:
    """'3ª' / '3rd'."""
    if lang() == "en":
        suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"
    return f"{n}ª"


def date_fmt() -> str:
    """Formato delle date nei campi data e nelle tabelle: GG/MM/AAAA in italiano, MM/DD/YYYY in inglese."""
    return "MM/DD/YYYY" if lang() == "en" else "DD/MM/YYYY"


def strf() -> str:
    """Formato strftime equivalente a date_fmt()."""
    return "%m/%d/%Y" if lang() == "en" else "%d/%m/%Y"
