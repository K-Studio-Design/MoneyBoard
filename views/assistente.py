"""Assistente IA: una chat per fare domande sui propri conti («quanto ho speso al ristorante quest'anno?»).

Usa Claude di Anthropic con la chiave API dell'utente (vedi ``core.assistant``). Senza chiave la pagina spiega come
averne una; prima del primo uso chiede il consenso a mandare ad Anthropic il riassunto dei dati.
"""
from __future__ import annotations

import time
from datetime import date

import streamlit as st

from core import assistant, db, demo_mode, i18n
from core.i18n import t
from views import style

HISTORY = "_ai_history"     # [{"role", "content", "error"?: bool, "failed"?: bool}]
CONTEXT = "_ai_context"     # (firma dei dati, riassunto)
PENDING = "_ai_pending"     # domanda scelta tra i suggerimenti o da riprovare

SUGGESTIONS = [
    "Dove ho speso di più questo mese?",
    "Come vanno i budget del mese?",
    "Quanto spendo al mese in abbonamenti?",
    "Confronta questo mese con il mese scorso",
    "Riuscirò a raggiungere i miei obiettivi?",
    "Dammi 3 idee concrete per risparmiare",
]


# ---------------------------------------------------------------- impostazioni (pagina e Impostazioni)
def settings_panel(prefix: str = "set_ai") -> None:
    """Chiave API, modello, cosa si condivide. Usato in Impostazioni → Assistente IA e nella pagina
    dell'assistente quando manca la chiave."""
    if demo_mode.enabled():
        st.info(t("Nella versione dimostrativa online l'assistente IA è spento: funziona nell'app installata sul "
                  "tuo computer, con la tua chiave API di Anthropic."), icon=":material/info:")
        return
    has = assistant.has_key()
    if has:
        st.success(t("Chiave API salvata ({key}), cifrata in questo computer.", key=assistant.masked_key()),
                   icon=":material/key:")
    else:
        _how_to()
    n = st.session_state.get(f"{prefix}_n", 0)   # cambia dopo il salvataggio: il campo torna vuoto
    with st.form(f"{prefix}_form_{n}", border=False, enter_to_submit=True):
        key = st.text_input(t("Sostituisci la chiave API") if has else t("Chiave API di Anthropic"),
                            type="password", placeholder="sk-ant-…", key=f"{prefix}_key_{n}",
                            help=t("Si crea nella Claude Console, alla voce API keys. Resta cifrata nel database."))
        ok = st.form_submit_button(t("Salva e prova"), icon=":material/check:", type="primary")
    if ok:
        key = (key or "").strip()
        if not assistant.key_looks_valid(key):
            st.error(t("Questa non sembra una chiave API di Anthropic: deve iniziare con «sk-ant-»."))
        else:
            with st.spinner(t("Provo la chiave…")):
                try:
                    assistant.test_key(key)
                except assistant.AssistantError as ex:
                    st.error(str(ex))
                else:
                    assistant.set_api_key(key)
                    st.session_state[f"{prefix}_n"] = n + 1
                    st.session_state.pop(CONTEXT, None)
                    st.toast(t("Chiave funzionante e salvata."), icon=":material/check_circle:")
                    st.rerun()
    if not has:
        return

    ids = [m for m, _ in assistant.MODELS]
    names = dict(assistant.MODELS)
    cur = assistant.model()
    if cur not in ids:
        ids.append(cur)
    hints = {"claude-sonnet-5-5": t("consigliato"), "claude-haiku-5-5": t("il più economico"),
             "claude-opus-5-5": t("il più capace, costa di più")}
    sel = st.selectbox(t("Modello"), ids, index=ids.index(cur), key=f"{prefix}_model",
                       format_func=lambda m: names.get(m, m) + (f" · {hints[m]}" if m in hints else ""))
    if sel != cur:
        assistant.set_model(sel)
        st.toast(t("Modello impostato: {m}", m=names.get(sel, sel)), icon=":material/check:")
    share = st.toggle(t("Includi gli ultimi movimenti (data, descrizione, importo)"),
                      value=assistant.share_transactions(), key=f"{prefix}_share",
                      help=t("Spento, l'assistente vede solo i totali (per mese, categoria, esercente, budget, "
                             "obiettivi, ricorrenti, saldi) e non le descrizioni dei singoli movimenti."))
    if share != assistant.share_transactions():
        assistant.set_share_transactions(share)
        st.session_state.pop(CONTEXT, None)
    row = st.container(horizontal=True, gap="small")
    if assistant.consented() and row.button(t("Revoca il consenso"), key=f"{prefix}_revoke", icon=":material/block:",
                                           help=t("L'assistente non manderà più dati finché non lo riattivi.")):
        assistant.set_consent(False)
        st.rerun()
    if row.button(t("Rimuovi la chiave API"), key=f"{prefix}_del", icon=":material/delete:"):
        assistant.clear_api_key()
        st.session_state.pop(HISTORY, None)
        st.rerun()


def _how_to() -> None:
    st.markdown(t(
        "**Come attivarlo** (servono pochi minuti):\n"
        "1. Crea un account nella **Claude Console** di Anthropic (è diverso dall'abbonamento a Claude.ai).\n"
        "2. In **Billing** aggiungi un po' di credito: si paga a consumo, di solito pochi centesimi a domanda.\n"
        "3. In **API keys** crea una chiave e copiala.\n"
        "4. Incollala qui sotto: l'app la prova e la salva cifrata."))
    st.link_button(t("Apri la Claude Console"), assistant.KEY_PAGE, icon=":material/open_in_new:")


# ---------------------------------------------------------------- pagina
def _context() -> str:
    """Riassunto dei dati, rifatto solo quando i dati cambiano (così resta in cache anche presso Anthropic)."""
    sig = (db.data_signature(), date.today().isoformat(), assistant.share_transactions(), i18n.lang())
    cached = st.session_state.get(CONTEXT)
    if cached and cached[0] == sig:
        return cached[1]
    from core import recurring, report
    from views import ui
    frame = report.frame()
    try:
        series = recurring.visible(ui.recurring_series_all())
    except Exception:
        series = []
    ctx = assistant.build_context(frame, series, include_tx=assistant.share_transactions())
    st.session_state[CONTEXT] = (sig, ctx)
    return ctx


def _consent() -> None:
    with style.card("ai_consent"):
        st.subheader(t("Prima di iniziare"))
        st.markdown(t(
            "Per rispondere, a ogni domanda l'app manda ad **Anthropic** (l'azienda che fa Claude) la conversazione "
            "e un riassunto dei tuoi dati: totali per mese e per categoria, esercenti principali, budget, obiettivi, "
            "spese ricorrenti, saldi dei conti e, se lo lasci attivo, gli ultimi {n} movimenti con la descrizione.\n\n"
            "Non vengono mandati il database, i file, le password né le chiavi degli altri servizi. Secondo le "
            "condizioni commerciali di Anthropic per l'API, i dati non vengono usati per addestrare i modelli.", n=assistant.RECENT_TX))
        share = st.toggle(t("Includi gli ultimi movimenti (data, descrizione, importo)"),
                          value=assistant.share_transactions(), key="ai_consent_share")
        if st.button(t("Ho capito, attiva l'assistente"), type="primary", icon=":material/auto_awesome:"):
            assistant.set_share_transactions(share)
            assistant.set_consent(True)
            st.rerun()


def _intro() -> None:
    st.html(f'''<div class="as-ai-hero"><div class="orb"><i></i><i></i><i></i></div>
<h3>{style.e(t("Ciao! Chiedimi qualcosa sui tuoi conti"))}</h3>
<p>{style.e(t("Rispondo con i dati di MoneyBoard: spese, entrate, budget, obiettivi e ricorrenti."))}</p></div>''')


def _api_messages(hist: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in hist if not m.get("error") and not m.get("failed")]


def _render_message(m: dict) -> None:
    avatar = ":material/auto_awesome:" if m["role"] == "assistant" else ":material/person:"
    with st.chat_message(m["role"], avatar=avatar):
        if m.get("error"):
            st.error(m["content"], icon=":material/error:")
        else:
            st.markdown(assistant.safe_markdown(m["content"]))


def _answer(hist: list[dict]) -> None:
    """Fa la domanda (l'ultimo messaggio di hist) e mostra la risposta mentre arriva."""
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        box = st.empty()
        box.html('<div class="as-ai-typing"><i></i><i></i><i></i></div>')
        text, last = "", 0.0
        try:
            for piece in assistant.stream_chat(_api_messages(hist), _context(), lang=i18n.lang()):
                text += piece
                now = time.monotonic()
                if now - last > 0.06:
                    box.markdown(assistant.safe_markdown(text) + " ▌")
                    last = now
        except assistant.AssistantError as ex:
            box.error(str(ex), icon=":material/error:")
            hist[-1]["failed"] = True
            hist.append({"role": "assistant", "content": str(ex), "error": True})
            return
        except Exception:
            msg = t("Qualcosa è andato storto durante la risposta: riprova.")
            box.error(msg, icon=":material/error:")
            hist[-1]["failed"] = True
            hist.append({"role": "assistant", "content": msg, "error": True})
            return
        if not text.strip():
            text = t("(Nessuna risposta: riprova.)")
        box.markdown(assistant.safe_markdown(text))
        hist.append({"role": "assistant", "content": text})


def render():
    style.header(t("Assistente"), t("Domande sui tuoi conti, in parole semplici"),
                 badge=dict(assistant.MODELS).get(assistant.model(), assistant.model())
                 if assistant.has_key() and not demo_mode.enabled() else None, ask=False)
    if demo_mode.enabled():
        _intro()
        st.info(t("Nella versione dimostrativa online l'assistente IA è spento: funziona nell'app installata sul "
                  "tuo computer, con la tua chiave API di Anthropic."), icon=":material/info:")
        return
    if not assistant.has_key():
        _intro()
        with style.card("ai_setup"):
            st.subheader(t("Collega Claude"))
            settings_panel("ai_setup")
        return
    if not assistant.consented():
        _intro()
        _consent()
        return

    hist: list[dict] = st.session_state.setdefault(HISTORY, [])
    typed = st.chat_input(t("Fai una domanda sui tuoi conti…"), max_chars=assistant.MAX_QUESTION, key="ai_input")
    question = (typed or st.session_state.pop(PENDING, None) or "").strip()[: assistant.MAX_QUESTION]
    if question:
        hist.append({"role": "user", "content": question})

    if hist:
        with st.container(key="ai_tools", horizontal=True, horizontal_alignment="right"):
            st.button(t("Nuova chat"), key="ai_new", icon=":material/add_comment:", type="tertiary",
                      on_click=lambda: st.session_state.update({HISTORY: []}))
    else:
        _intro()
        with st.container(key="ai_sugg", horizontal=True, horizontal_alignment="center", gap="small"):
            for i, s in enumerate(SUGGESTIONS):
                st.button(t(s), key=f"ai_sug_{i}", on_click=_ask, args=(t(s),))

    with st.container(key="ai_chat"):
        for m in hist[:-1] if question else hist:
            _render_message(m)
        if question:
            _render_message(hist[-1])
            _answer(hist)
        elif hist and hist[-1].get("error") and len(hist) >= 2 and hist[-2].get("failed"):
            st.button(t("Riprova"), key="ai_retry", icon=":material/refresh:", on_click=_retry)
    st.caption(t("Le risposte sono generate da un'IA a partire dai tuoi dati e possono contenere errori: per le "
                 "decisioni importanti controlla i numeri nelle pagine dell'app."))


def _ask(q: str) -> None:
    st.session_state[PENDING] = q


def _retry() -> None:
    """Rifà l'ultima domanda non riuscita (toglie la domanda e il messaggio d'errore e la rimanda)."""
    hist = st.session_state.get(HISTORY) or []
    if len(hist) >= 2 and hist[-1].get("error") and hist[-2].get("failed"):
        q = hist[-2]["content"]
        del hist[-2:]
        st.session_state[PENDING] = q
