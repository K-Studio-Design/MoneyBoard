"""Funzioni di supporto condivise dalle pagine."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import db, i18n
from core.i18n import t

MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "JPY": "¥"}


def fmt_num(x: float | None, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    s = f"{x:,.{decimals}f}"
    if i18n.is_en():
        return s  # 1,234.56
    return s.replace(",", "X").replace(".", ",").replace("X", ".")  # 1.234,56


def money(x: float | None, ccy: str | None = None, decimals: int = 2) -> str:
    ccy = ccy or display_ccy()
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    sym = SYMBOLS.get(ccy, ccy)
    if i18n.is_en():
        # €1,234.56 / -€12.00 (codici di più lettere: CHF 1,234.56)
        sep = " " if len(sym) > 1 else ""
        return ("-" if x < 0 else "") + f"{sym}{sep}{fmt_num(abs(x), decimals)}"
    return f"{fmt_num(x, decimals)} {sym}"


def esc(text: str) -> str:
    """Testo sicuro per markdown: il simbolo $ altrimenti viene letto come formula matematica."""
    return str(text).replace("$", "\\$")


def month_label(period: pd.Period) -> str:
    return f"{i18n.month(period.month, short=True)} {period.year}"


def month_short(period: pd.Period) -> str:
    """Etichetta compatta per gli assi dei grafici: 'Ott 26'."""
    return f"{i18n.month(period.month, short=True)} {str(period.year)[2:]}"


PRESETS = ["Mese corrente", "Mese scorso", "Ultimi 3 mesi", "Ultimi 6 mesi", "Ultimi 12 mesi",
           "Anno corrente", "Anno scorso", "Tutto", "Personalizzato"]


def preset_range(preset: str, first_date: date | None = None) -> tuple[date, date]:
    today = date.today()
    som = today.replace(day=1)
    if preset == "Mese corrente":
        return som, today
    if preset == "Mese scorso":
        end = som - timedelta(days=1)
        return end.replace(day=1), end
    if preset in ("Ultimi 3 mesi", "Ultimi 6 mesi", "Ultimi 12 mesi"):
        n = int(preset.split()[1])
        start = (pd.Timestamp(som) - pd.DateOffset(months=n - 1)).date()
        return start, today
    if preset == "Anno corrente":
        return date(today.year, 1, 1), today
    if preset == "Anno scorso":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    return (first_date or date(today.year, 1, 1)), today


def period_picker(key: str, default: str = "Ultimi 6 mesi", first_date: date | None = None) -> tuple[date, date]:
    c1, c2 = st.columns([1, 2])
    preset = c1.selectbox(t("Periodo"), PRESETS, index=PRESETS.index(default), key=f"{key}_preset", format_func=t)
    start, end = preset_range(preset, first_date)
    if preset == "Personalizzato":
        rng = c2.date_input(t("Dal / al"), value=(start, end), format=i18n.date_fmt(), key=f"{key}_range")
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            start, end = rng
        else:
            c2.info(t("Seleziona anche la data di fine."))
    else:
        c2.markdown("<div style='padding-top:2.1rem'>" + t("dal <b>{a}</b> al <b>{b}</b>", a=f"{start:{i18n.strf()}}",
                                                                b=f"{end:{i18n.strf()}}") + "</div>",
                    unsafe_allow_html=True)
    return start, end


ALL_CCY = "ALL"


def selected_accounts() -> list[str]:
    return list(st.session_state.get("view_accounts") or [])


def selected_ccy() -> str:
    return st.session_state.get("view_ccy") or ALL_CCY


def display_ccy() -> str:
    """Valuta in cui sono mostrati gli importi: la valuta base, oppure quella scelta nel filtro."""
    c = selected_ccy()
    return db.base_currency() if c == ALL_CCY else c


def view_filters() -> None:
    """Filtri globali nella barra laterale: conti e valuta. Valgono per Panoramica, Movimenti e Analisi."""
    with db.connect() as con:
        accs = [r[0] for r in con.execute(
            "SELECT DISTINCT account FROM transactions WHERE account IS NOT NULL AND account <> '' ORDER BY account")]
        ccys = [r[0] for r in con.execute(
            "SELECT currency FROM transactions GROUP BY currency ORDER BY COUNT(*) DESC")]
    if not accs:
        return
    # alla prima apertura tutti i conti selezionati; i conti nuovi (es. dopo un import) si aggiungono da soli
    known = st.session_state.get("_view_known_accounts")
    if "view_accounts" not in st.session_state or known is None:
        # nuova sessione (apertura o ricarica della pagina): riprende l'ultima scelta salvata
        saved = _load_json("view_accounts")
        saved_known = _load_json("view_known_accounts")
        if isinstance(saved, list) and isinstance(saved_known, list):
            st.session_state["view_accounts"] = [a for a in saved if a in accs] + \
                [a for a in accs if a not in saved_known]
        else:
            st.session_state["view_accounts"] = list(accs)
    elif set(known) != set(accs):
        current = [a for a in (st.session_state.get("view_accounts") or []) if a in accs]
        st.session_state["view_accounts"] = current + [a for a in accs if a not in known]
    st.session_state["_view_known_accounts"] = list(accs)
    st.pills(t("Conti"), accs, selection_mode="multi", key="view_accounts",
             help=t("Scegli quali conti considerare in Panoramica, Movimenti e Analisi."))
    if not st.session_state.get("view_accounts"):
        st.caption(t("Nessun conto selezionato: mostro tutti."))
    base = db.base_currency()
    opts = [ALL_CCY] + ccys
    if "view_ccy" not in st.session_state:
        st.session_state["view_ccy"] = db.get_setting("view_ccy", ALL_CCY) or ALL_CCY
    if st.session_state.get("view_ccy") not in opts:
        st.session_state["view_ccy"] = ALL_CCY
    st.selectbox(t("Valuta"), opts, key="view_ccy",
                 format_func=lambda c: (t("Tutte, convertite in {base}", base=base) if c == ALL_CCY
                                        else t("Solo {ccy} (importi originali)", ccy=c)),
                 help=t("«Tutte»: ogni importo è convertito nella valuta base. Scegliendo una valuta vedi solo "
                        "i movimenti in quella valuta, con gli importi originali non convertiti."))
    # salva la scelta, così resta anche ricaricando la pagina o riaprendo l'app
    _save_json("view_accounts", list(st.session_state.get("view_accounts") or []))
    _save_json("view_known_accounts", list(accs))
    if db.get_setting("view_ccy") != st.session_state["view_ccy"]:
        db.set_setting("view_ccy", st.session_state["view_ccy"])


def _load_json(key: str):
    import json

    try:
        return json.loads(db.get_setting(key) or "null")
    except ValueError:
        return None


def _save_json(key: str, value) -> None:
    import json

    raw = json.dumps(value, ensure_ascii=False)
    if db.get_setting(key) != raw:
        db.set_setting(key, raw)


def prepared_transactions(apply_view: bool = True, ignore_currency: bool = False) -> pd.DataFrame:
    """Transazioni con colonne comode per le analisi.
    'valore' = importo nella valuta di visualizzazione (base, oppure originale se è filtrata una valuta);
    'valore_base' = importo convertito nella valuta base;
    'spesa' = importo di spesa positivo (i rimborsi su categorie di spesa lo riducono);
    'entrata' = importo di entrata. Le categorie 'neutro' (giroconti, investimenti) sono escluse.
    Con apply_view applica i filtri globali di conto e valuta della barra laterale."""
    df = db.transactions_df()
    if df.empty:
        return df
    base = db.base_currency()
    val = df["amount_base"].copy()
    same = df["currency"].str.upper() == base
    val = val.where(val.notna() | ~same, df["amount"])
    df["valore_base"] = val
    df["valore"] = val
    if apply_view:
        accs = selected_accounts()
        if accs:
            df = df[df["account"].isin(accs)]
        ccy = selected_ccy()
        if ccy != ALL_CCY and not ignore_currency:
            df = df[df["currency"] == ccy].copy()
            df["valore"] = df["amount"]
    df = df.copy()
    df["spesa"] = (-df["valore"]).where(df["kind"] == "uscita", 0.0)
    df["entrata"] = df["valore"].where(df["kind"] == "entrata", 0.0)
    df["spesa_base"] = (-df["valore_base"]).where(df["kind"] == "uscita", 0.0)
    df["entrata_base"] = df["valore_base"].where(df["kind"] == "entrata", 0.0)
    df["mese"] = df["date"].dt.to_period("M")
    df["giorno_sett"] = df["date"].dt.weekday
    labels = db.category_labels()
    df["cat_label"] = df["category"].map(lambda c: labels.get(c, c) if isinstance(c, str) else None)
    df["cat_label"] = df["cat_label"].fillna(t("Senza categoria"))
    return df


def view_summary() -> str:
    """Descrizione in parole dei filtri globali, per il sottotitolo delle pagine."""
    known = st.session_state.get("_view_known_accounts") or []
    sel = selected_accounts() or known
    if not known:
        acc = t("Nessun conto ancora")
    elif set(sel) == set(known):
        acc = t("Tutti i conti") if len(known) > 2 else t(" e ").join(known)
    else:
        acc = t("Solo {conti}", conti=t(" e ").join(sel))
    ccy = selected_ccy()
    cur = (t("importi convertiti in {base}", base=db.base_currency()) if ccy == ALL_CCY
           else t("solo movimenti in {ccy}, importi originali", ccy=ccy))
    return f"{acc}, {cur}"


def view_caption() -> None:
    st.caption(view_summary())


def filter_period(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]


def months_in(start: date, end: date) -> float:
    """Numero di mesi (anche frazionari) del periodo, per le medie mensili."""
    days = (end - start).days + 1
    return max(days / 30.4375, 1e-9)


def color_map() -> dict[str, str]:
    """Colore di ogni categoria, cercabile sia per nome sia per nome mostrato (es. il nome inglese)."""
    cats = db.categories_df()
    labels = db.category_labels()
    out = {}
    for r in cats.itertuples():
        out.setdefault(labels.get(r.name, r.name), r.color)
    for r in cats.itertuples():
        out[r.name] = r.color
    return out


def cat(name) -> str:
    """Nome da mostrare di una categoria nella lingua dell'app (la chiave salvata resta il nome italiano)."""
    if name is None or (isinstance(name, float) and pd.isna(name)) or name == "":
        return t("Senza categoria")
    return db.category_labels().get(str(name), str(name))


def cat_key(value):
    """Dal nome mostrato (o dal nome stesso) alla categoria salvata; None se non esiste."""
    if value is None:
        return None
    labels = db.category_labels()
    if value in labels:
        return value
    for k, v in labels.items():
        if v == value:
            return k
    return None


def missing_fx_warning(df: pd.DataFrame) -> None:
    if df.empty:
        return
    n = int(df["valore"].isna().sum())
    if n:
        st.warning(t("{n} transazioni non hanno il cambio in {base} e sono escluse dai totali. "
                     "Vai in Impostazioni (menu dell'avatar in alto a destra) → 'Ricalcola cambi' quando sei online.",
                     n=n, base=db.base_currency()))


# ---------------------------------------------------------------- pagamenti ricorrenti (con cache)
@st.cache_data(show_spinner=False, max_entries=8)
def _series_cached(signature: str, accounts: tuple[str, ...], today: date, rules_json: str = "{}"):
    import json

    from core import recurring
    df = db.transactions_df()
    if accounts and not df.empty:
        df = df[df["account"].isin(accounts)]
    return recurring.detect(df, today=today, rules=json.loads(rules_json or "{}"))


def recurring_series(include_hidden: bool = False):
    """Serie ricorrenti dei conti selezionati nella barra laterale (tutte le valute)."""
    from core import recurring
    out = _series_cached(db.data_signature(), tuple(sorted(selected_accounts())), date.today(), _rules_json())
    return recurring.not_deleted(out) if include_hidden else recurring.visible(out)


@st.cache_data(show_spinner=False, max_entries=8)
def _alerts_cached(signature: str, accounts: tuple[str, ...], today: date, hidden_series: tuple[str, ...],
                   names_sig: str, rules_json: str = "{}", lang: str = "it", budgets_sig: str = "",
                   reminder_days: int = 0):
    from core import alerts, budgets, report
    full = db.transactions_df()
    df = full[full["account"].isin(accounts)] if accounts and not full.empty else full
    series = [s for s in _series_cached(signature, accounts, today, rules_json) if s.sid not in set(hidden_series)]
    out = alerts.compute(df, series, today=today, reminder_days=reminder_days)
    # i budget contano tutti i conti, qualunque sia la scelta nella barra laterale
    out += budgets.alerts(report.frame(full), today=today)
    out.sort(key=lambda a: (alerts.LEVEL_ORDER[a.level], -a.date.value))
    return out


def active_alerts(include_dismissed: bool = False):
    """Avvisi per i conti selezionati nella barra laterale (esclusi quelli ignorati)."""
    from core import alerts, budgets, notify, recurring
    out = _alerts_cached(db.data_signature(), tuple(sorted(selected_accounts())), date.today(),
                         tuple(sorted(recurring.hidden() | recurring.deleted())),
                         db.get_setting(recurring.NAMES_KEY, "") or "", _rules_json(), i18n.lang(),
                         budgets.signature(), notify.reminder_days())
    out = [a for a in out if a.aid not in alerts.deleted()]
    if include_dismissed:
        return out
    gone = alerts.dismissed()
    return [a for a in out if a.aid not in gone]


def _rules_json() -> str:
    import json

    from core import recurring
    rules = recurring.day_rules()
    rules.update(recurring.salary_rules())
    return json.dumps(rules, sort_keys=True)
