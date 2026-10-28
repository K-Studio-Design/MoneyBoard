"""Ricerca veloce: casella nella barra in alto di ogni pagina; i risultati si aprono in una finestra."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n
from core.i18n import t
from views import focus, nav, style, ui

INPUT_KEY = "as_search"
QUERY_KEY = "_as_search_q"
JUMP_TAB = "_jump_tab"     # {pagina: scheda da mostrare} dopo un clic su un risultato
JUMP_OPEN = "_jump_open"   # sezioni (expander) da aprire dopo un clic su un risultato

# ---------------------------------------------------------------- pagine e impostazioni cercabili
# (id, pagina, titolo, dove si trova, parole chiave in italiano e inglese, scheda da aprire, sezione da aprire)
APP_INDEX = [
    ("p_dashboard", "dashboard", "Panoramica", "Pagina iniziale",
     "home inizio riepilogo previsione fine mese saldo oggi spese del mese dashboard overview forecast", None, None),
    ("p_spese", "spese", "Movimenti", "Tutti i movimenti, con filtri e modifica",
     "transazioni elenco lista modifica categoria note esporta csv filtri transactions list edit export", None, None),
    ("p_analisi", "analisi", "Analisi", "Spese ed entrate nel periodo",
     "statistiche grafici report confronto periodo analysis charts statistics", None, None),
    ("a_mese", "analisi", "Spese ed entrate per mese", "Analisi → Per mese",
     "mensile mesi risparmio monthly months savings", "Per mese", None),
    ("a_cat", "analisi", "Spese per categoria", "Analisi → Per categoria",
     "categorie media mensile categories breakdown", "Per categoria", None),
    ("a_trend", "analisi", "Andamento delle spese", "Analisi → Andamento",
     "trend cumulato giornaliero settimanale trend over time", "Andamento", None),
    ("a_dove", "analisi", "Dove spendi (esercenti)", "Analisi → Dove spendi",
     "negozi esercenti spese più grandi top merchants biggest expenses", "Dove spendi", None),
    ("a_pivot", "analisi", "Tabella mesi × categorie", "Analisi → Mesi × categorie",
     "tabella pivot scarica csv excel table download", "Mesi × categorie", None),
    ("a_valuta", "analisi", "Spese per valuta", "Analisi → Per valuta",
     "dollari valute estere currencies foreign", "Per valuta", None),
    ("p_budget", "budget", "Budget", "Quanto vuoi spendere al mese per categoria",
     "budget tetto limite spesa mensile categoria avviso superato monthly budget limit spending category",
     None, None),
    ("p_condivise", "condivise", "Spese condivise", "Chi ti deve dei soldi e a chi li devi tu",
     "condivise dividere amici coinquilini partner rimborso debito credito splitwise shared expenses split friends "
     "owe iou roommates", None, None),
    ("m_dividi", "spese", "Dividere un movimento", "Movimenti → apri un movimento → Dividi il movimento",
     "dividi suddividi movimento più categorie split transaction categories", None, None),
    ("p_calendario", "calendario", "Calendario", "Spese giorno per giorno e pagamenti in arrivo",
     "giorni mese scadenze agenda calendar days due", None, None),
    ("p_abbonamenti", "abbonamenti", "Abbonamenti", "Pagamenti e accrediti che si ripetono",
     "ricorrenti rate canoni netflix spotify stipendio subscriptions recurring payments", None, None),
    ("p_avvisi", "avvisi", "Avvisi", "Cose da controllare",
     "notifiche alert anomalie doppioni addebiti insoliti notifications warnings", None, None),
    ("p_obiettivi", "obiettivi", "Obiettivi", "Obiettivi di risparmio",
     "risparmio salvadanaio traguardo goals savings target", None, None),
    ("o_nuovo", "obiettivi", "Nuovo obiettivo", "Obiettivi → Nuovo obiettivo",
     "crea aggiungi obiettivo risparmio new goal create", None, "nuovo_obiettivo"),
    ("p_investimenti", "investimenti", "Investimenti", "Titoli e crypto",
     "portafoglio azioni etf fondi borsa crypto investments portfolio stocks", "Portafoglio", None),
    ("i_estratti", "investimenti", "Dividendi e cedole dagli estratti", "Investimenti → Dagli estratti",
     "dividendi cedole ritenute proventi dividends coupons", "Dagli estratti", None),
    ("i_titolo", "investimenti", "Aggiungi un titolo", "Investimenti → Aggiungi titolo",
     "isin ticker nuovo titolo azione etf add security", "Aggiungi titolo", None),
    ("i_operazioni", "investimenti", "Operazioni sui titoli", "Investimenti → Operazioni",
     "acquisti vendite compravendite trades buy sell", "Operazioni", None),
    ("i_crypto", "investimenti", "Exchange crypto", "Investimenti → Exchange crypto",
     "bitcoin binance coinbase kraken criptovalute crypto exchange api", "Exchange crypto", None),
    ("p_valute", "valute", "Valute e cambi", "Cambi BCE e convertitore",
     "cambio tassi convertitore dollaro sterlina franco bce exchange rates converter currency", None, None),
    ("p_profilo", "profilo", "Profilo", "Le tue informazioni e i tuoi conti",
     "account utente nome avatar colore profile name", None, None),
    ("pr_nome", "profilo", "Nome e colore dell'avatar", "Profilo → I tuoi dati",
     "nome avatar colore iniziali name avatar colour", None, None),
    ("pr_intest", "profilo", "Intestatari dei conti", "Profilo → I tuoi dati",
     "intestatario titolare giroconti bonifici a me stesso owner account holder transfers", None, None),
    ("pr_stip", "profilo", "Giorno dello stipendio", "Profilo → I tuoi dati",
     "stipendio busta paga giorno accredito salary payday", None, None),
    ("pr_lingua", "profilo", "Lingua (italiano / inglese)", "Profilo → I tuoi dati",
     "lingua italiano inglese language english italian", None, None),
    ("pr_saldi", "profilo", "Saldi reali dei conti", "Profilo → I tuoi conti",
     "saldo conto banca sincronizza previsione balance account sync", None, "saldi"),
    ("p_carte", "carte", "Carte", "Le tue carte e le spese fatte con ognuna",
     "carta di credito debito bancomat saldo carta credit debit card", None, None),
    ("p_importa", "importa", "Importa estratti", "Carica i file esportati dalla banca",
     "import carica file csv excel estratto conto ofx qif camt mt940 upload statement", None, None),
    ("p_banche", "banche", "Collega banche", "Sincronizzazione automatica (Open Banking)",
     "open banking enable banking api sincronizza collegamento psd2 sync connect bank", None, None),
    ("p_tasse", "tasse", "Tasse USA (alpha)", "Stima delle tasse sugli stipendi (Stati Uniti)",
     "tasse imposte irs federali statali fica social security medicare stipendio residenza stato taxes federal state "
     "income tax salary 1099 txf dividendi interessi plusvalenze azioni broker dividends capital gains stocks",
     None, None),
    ("pr_alpha", "profilo", "Funzioni in prova (alpha)", "Profilo → Funzioni in prova",
     "alpha sperimentale prova tasse usa attiva experimental beta enable", None, None),
    ("b_auto", "banche", "Sincronizzazione automatica giornaliera", "Collega banche → Conti collegati",
     "sincronizza automatico ogni giorno giornaliera aggiorna saldi movimenti auto daily automatic sync refresh",
     None, None),
    ("b_doppi", "banche", "Movimenti doppi", "Collega banche → Movimenti doppi",
     "doppioni duplicati togli doppi duplicates", None, None),
    ("b_config", "banche", "Configurazione Enable Banking", "Collega banche → Configurazione",
     "application id chiave privata pem redirect url configuration private key", None, "eb_config"),
    ("p_impostazioni", "impostazioni", "Impostazioni", "Valuta, categorie, regole, cartelle e backup",
     "opzioni preferenze configurazione settings preferences options", "Generali", None),
    ("s_valuta", "impostazioni", "Valuta base", "Impostazioni → Generali",
     "euro valuta principale totali conversione base currency", "Generali", None),
    ("s_quot", "impostazioni", "Aggiornamento automatico delle quotazioni", "Impostazioni → Generali",
     "quotazioni prezzi titoli apertura automatico prices quotes update", "Generali", None),
    ("s_cat", "impostazioni", "Categorie", "Impostazioni → Categorie",
     "categoria colori rinomina aggiungi elimina entrate uscite categories rename colors", "Categorie", None),
    ("s_regole", "impostazioni", "Regole automatiche", "Impostazioni → Regole automatiche",
     "regole parole chiave categorizzazione automatica ricategorizza rules keywords auto categorize",
     "Regole automatiche", None),
    ("s_cartelle", "impostazioni", "Cartella dei dati e database", "Impostazioni → Cartelle e backup",
     "cartella database sposta dati onedrive percorso folder data location", "Cartelle e backup", None),
    ("s_backup", "impostazioni", "Backup e ripristino", "Impostazioni → Cartelle e backup",
     "backup copia ripristina salvataggio restore", "Cartelle e backup", None),
    ("s_auto", "impostazioni", "Importazione automatica dalla cartella", "Impostazioni → Cartelle e backup",
     "estratti da importare cartella automatico watch folder auto import", "Cartelle e backup", None),
    ("s_reset", "impostazioni", "Elimina tutti i movimenti", "Impostazioni → Cartelle e backup → Zona pericolosa",
     "cancella elimina tutto reset azzera delete all", "Cartelle e backup", None),
    ("s_email", "impostazioni", "Email e promemoria", "Impostazioni → Email e promemoria",
     "email posta smtp gmail riepilogo mensile promemoria scadenze notifiche bollette mail monthly summary "
     "reminders notifications due bills", "Email e promemoria", None),
    ("s_update", "impostazioni", "Avviso di nuova versione", "Impostazioni → Generali",
     "aggiornamento nuova versione github release update new version", "Generali", None),
    ("p_utenti", "utenti", "Utenti", "Crea e gestisci gli utenti (amministratore)",
     "utente nuovo password account amministratore users admin", None, None),
]


def tab_default(page: str) -> str | None:
    """Scheda da mostrare in una pagina con st.tabs dopo un clic su un risultato della ricerca (tradotta).
    Resta la stessa per tutta la sessione, così le schede non cambiano da sole a ogni interazione."""
    lab = st.session_state.get(JUMP_TAB, {}).get(page)
    return t(lab) if lab else None


def is_open(section: str) -> bool:
    return section in st.session_state.get(JUMP_OPEN, set())


def search_app(q: str) -> list[tuple]:
    """Pagine e impostazioni che contengono tutte le parole cercate (titolo, percorso o parole chiave)."""
    from core import banks

    words = _norm(q).split()
    if not words:
        return []
    out = []
    for item in APP_INDEX:
        iid, page, title, where, kw, _tab, _open = item
        if page not in nav.PAGES or (page == "utenti" and not db.is_admin()):
            continue
        if page == "tasse":
            from core import tax_us
            if not tax_us.enabled():   # funzione in prova: cercabile solo se attivata dal profilo
                continue
        extra = " ".join(p.name for p in banks.PROFILES) if iid == "p_importa" else ""
        hay = _norm(" ".join((title, t(title), where, t(where), kw, extra)))
        if all(w in hay for w in words):
            name = _norm(t(title))
            score = (0 if name.startswith(words[0]) else 1 if words[0] in name else 2, len(title))
            out.append((score, item))
    return [it for _s, it in sorted(out, key=lambda x: x[0])][:8]


def _open_item(iid: str) -> None:
    item = next((i for i in APP_INDEX if i[0] == iid), None)
    if item is None:
        return
    _iid, page, _title, _where, _kw, tab, sect = item
    if tab:
        st.session_state.setdefault(JUMP_TAB, {})[page] = tab
    if sect:
        st.session_state.setdefault(JUMP_OPEN, set()).add(sect)
    st.switch_page(nav.PAGES[page])


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).lower().strip()


def _submit() -> None:
    q = (st.session_state.get(INPUT_KEY) or "").strip()
    if q:
        st.session_state[QUERY_KEY] = q
    st.session_state[INPUT_KEY] = ""


def box() -> None:
    """La casella di ricerca (da mettere nella barra in alto)."""
    st.text_input(t("Cerca"), key=INPUT_KEY, placeholder=t("Cerca nell'app…"), label_visibility="collapsed",
                  on_change=_submit, icon=":material/search:", width=230,
                  help=t("Cerca pagine e impostazioni dell'app (es. «backup», «categorie», «valuta») e i movimenti: "
                         "descrizioni, note, categorie e conti; puoi scrivere anche un importo (es. 6,99). "
                         "Premi Invio per cercare."))
    q = st.session_state.pop(QUERY_KEY, None)
    if q:
        st.dialog(t("Risultati per «{q}»", q=ui.esc(q)), width="large")(_results)(q)


def search(df: pd.DataFrame, q: str) -> pd.DataFrame:
    """Tutte le parole devono comparire (senza distinguere maiuscole e accenti); un numero cerca anche l'importo."""
    labels = db.category_labels()
    shown = df["category"].map(lambda c: labels.get(c, c) if isinstance(c, str) else "")
    text = (df["description"].fillna("") + " " + df["notes"].fillna("") + " " + df["category"].fillna("") + " "
            + shown + " " + df["account"].fillna("")).map(_norm)   # categoria: nome salvato e nome mostrato
    words = _norm(q).split()
    mask = pd.Series(True, index=df.index)
    for w in words:
        num = re.fullmatch(r"-?\d+(?:[.,]\d{1,2})?", w)
        if num:
            val = abs(float(w.replace(",", ".")))
            mask &= text.str.contains(re.escape(w), regex=True) | (df["amount"].abs().round(2) == round(val, 2))
        else:
            mask &= text.str.contains(re.escape(w), regex=True)
    return df[mask]


def _results(q: str) -> None:
    found = search_app(q)
    if found:
        st.subheader(t("Pagine e impostazioni"))
        rows = []
        for iid, page, title, where, _kw, _tab, _sect in found:
            rows.append(dict(id=iid, desc=t(title), meta=t(where), color=style.ACCENT,
                             cat=nav.PAGES[page].title, amount="", sub=""))
        sel = style.item_list(rows, key=f"cerca_app_{q}")
        if sel:
            _open_item(str(sel))
    df = ui.prepared_transactions(apply_view=False)
    res = search(df, q).sort_values("date", ascending=False) if not df.empty else df
    if res.empty:
        if not found:
            st.info(t("Non ho trovato né pagine né movimenti. Prova con una parola sola o con parte del nome."))
        elif not df.empty:
            st.caption(t("Nessun movimento contiene «{q}».", q=q))
        return
    if found:
        st.subheader(t("Movimenti"))
    base = db.base_currency()
    spent, inc = float(res["spesa_base"].sum()), float(res["entrata_base"].sum())
    style.kpis(cols=4, items=[
        (t("Movimenti"), ui.fmt_num(len(res), 0), t("dal {d}", d=f"{res['date'].min():{i18n.strf()}}")),
        (t("Speso"), ui.money(spent, base),
         t("in media {v}", v=ui.money(spent / max((res["spesa_base"] > 0).sum(), 1), base))),
        (t("Entrate"), ui.money(inc, base)),
        (t("Ultimo"), f"{res['date'].max():{i18n.strf()}}", res["account"].iloc[0]),
    ])
    months = pd.period_range(end=pd.Timestamp.today().to_period("M"), periods=12, freq="M")
    by = (res["spesa_base"] - res["entrata_base"]).groupby(res["mese"]).sum().reindex(months, fill_value=0)
    if by.abs().sum() > 0:
        fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in months], y=by.values,
                               marker_color=[style.SPESA if v >= 0 else style.ENTRATA for v in by.values],
                               hovertemplate="%{x}<br>%{y:,.2f} " + base + "<extra></extra>"))
        style.chart(fig, height=180, legend=False)
        st.caption(t("Ultimi 12 mesi (spese meno entrate dei movimenti trovati)."))
    shown = st.session_state.get(f"_cerca_n_{q}", 20)
    sel = style.tx_list(res.head(shown), lambda v, c: ui.money(v, c), ui.color_map(), base, key=f"cerca_{q}")
    if len(res) > shown and st.button(t("Mostra altri ({n})", n=len(res) - shown), key=f"cerca_more_{q}",
                                      icon=":material/expand_more:"):
        st.session_state[f"_cerca_n_{q}"] = shown + 40
        st.rerun(scope="fragment")
    if sel is not None:
        st.session_state[focus.PENDING] = sel
        st.rerun()
