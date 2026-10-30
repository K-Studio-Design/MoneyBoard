"""Carte: le carte di pagamento trovate nei movimenti (e quelle collegate via Open Banking), con il saldo
sincronizzato dalla banca e, cliccando, le spese fatte con ogni carta.

I conti collegati di cui non si possono separare le carte (Revolut non indica con quale carta è stato fatto un
pagamento) compaiono come conto, con il loro saldo e le loro spese."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import cards, db, enablebanking as eb, i18n
from core.i18n import t
from views import focus, style, ui

VARIANTS = ["saldo", "blu", "spese", "entrate", "media", "grafite"]
CREDIT = "Carta di credito"


def _dd(iso) -> str:
    """Data del saldo (ISO) in formato leggibile."""
    try:
        return i18n.date_short(pd.Timestamp(str(iso)[:10]))
    except (ValueError, TypeError):
        return "–"


def _digits_of(text) -> str:
    """Ultime 4 cifre dal nome che la banca dà alla carta, es. «5100 **** **** 1234» → «1234»."""
    import re
    m = re.search(r"(\d{4})\D*$", str(text or ""))
    return m.group(1) if m else ""


def _linked() -> pd.DataFrame:
    try:
        return eb.accounts_df()
    except Exception:
        return pd.DataFrame()


def _same(a, b) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def _card_list(tx: pd.DataFrame) -> list[dict]:
    """Carte da mostrare: quelle riconosciute nei movimenti e le carte collegate via Open Banking.
    Ogni voce: id, title, kind, digits, account, rows (movimenti), balance (saldo dalla banca o None)."""
    meta = cards.cards_df()
    linked = _linked()
    out: list[dict] = []
    for m in meta.itertuples():
        if int(m.hidden or 0):
            continue
        rows = tx[(tx["account"] == m.account) & (tx["card"] == m.digits)] if not tx.empty else tx
        out.append({"id": f"c|{m.account}|{m.digits}", "digits": m.digits, "account": m.account,
                    "kind": m.kind or "", "name": m.name or "", "rows": rows, "balance": None, "balance_ccy": None,
                    "balance_date": None, "uid": None})
    for a in linked.to_dict("records") if not linked.empty else []:
        if not eb.is_card(a):
            continue
        rows = tx[tx["bank_uid"] == a["uid"]] if not tx.empty else tx
        digits = rows["card"].dropna().unique().tolist() if not rows.empty else []
        if len(digits) != 1:  # nessun movimento con la carta: le cifre dal nome che le dà la banca
            d = _digits_of(a.get("product")) or _digits_of(a.get("account_name"))
            digits = [d] if d else digits
        target = None
        if len(digits) == 1:
            target = next((c for c in out if c["account"] == (a["label"] or a["aspsp_name"])
                           and c["digits"] == digits[0]), None)
        if target is not None:  # stessa carta già trovata nei movimenti: un'unica voce con il saldo della banca
            if not rows.empty:
                target["rows"] = pd.concat([target["rows"], rows]).drop_duplicates("id")
            target["kind"] = target.get("kind") or CREDIT
        else:
            target = {"id": f"a|{a['uid']}", "digits": digits[0] if len(digits) == 1 else "", "uid": a["uid"],
                      "account": a["label"] or a["aspsp_name"], "kind": t("Carta di credito"),
                      "name": a.get("product") or a.get("account_name") or "", "rows": rows}
            out.append(target)
        target["uid"] = a["uid"]
        if pd.notna(a.get("balance")):
            target.update(balance=float(a["balance"]), balance_ccy=a.get("balance_currency") or a.get("currency"),
                          balance_date=str(a.get("balance_date") or "")[:10])
    # saldo del conto a cui è legata la carta (carte di debito): dal collegamento con la banca.
    # Una carta di credito ha un saldo suo, non quello del conto: senza collegamento della carta resta senza saldo.
    for c in out:
        if c.get("balance") is not None or linked.empty or c.get("kind") == CREDIT:
            continue
        acc = linked[(linked["label"].fillna(linked["aspsp_name"]) == c["account"]) & linked["balance"].notna()]
        acc = acc[[not eb.is_card(r) for r in acc.to_dict("records")]]
        if not acc.empty:
            base = db.base_currency()
            # prima il conto principale (con IBAN), non un pocket o salvadanaio della stessa banca
            acc = acc.assign(_main=acc["iban"].fillna("").astype(str).str.strip() != "").sort_values(
                "_main", ascending=False, kind="stable")
            main = acc[acc["balance_currency"].fillna(acc["currency"]) == base]
            r = (main if not main.empty else acc).iloc[0]
            c.update(account_balance=float(r["balance"]), account_balance_ccy=r["balance_currency"] or r["currency"],
                     balance_date=str(r["balance_date"] or "")[:10])
    # conti collegati senza carte riconoscibili (es. Revolut): compaiono come conto, con saldo e spese
    with_cards = {c["account"] for c in out}
    plain = [a for a in (linked.to_dict("records") if not linked.empty else []) if not eb.is_card(a)]

    def _key(a):
        return (a["label"] or a["aspsp_name"], str(a.get("balance_currency") or a.get("currency") or "").upper())

    groups: dict = {}
    for a in plain:
        groups.setdefault(_key(a), []).append(a)
    for a in plain:
        acc, ccy = _key(a)
        if acc in with_cards:
            continue
        rows = tx[(tx["account"] == acc) & (tx["currency"] == ccy)] if not tx.empty else tx
        name = t("Conto {acc} {ccy}", acc=acc, ccy=ccy).strip()
        same = groups[(acc, ccy)]
        if len(same) > 1 and not rows.empty:
            # stesso conto nell'app e stessa valuta (es. conto Revolut e un suo pocket): ognuno i suoi movimenti.
            # Il conto con l'IBAN tiene anche quelli senza collegamento (estratti importati)
            others = {o["uid"] for o in same if o["uid"] != a["uid"]}
            has_iban = bool(str(a.get("iban") or "").strip())
            mask = rows["bank_uid"] == a["uid"]
            if has_iban:
                mask |= ~rows["bank_uid"].isin(others)
            rows = rows[mask]
        if len(same) > 1:
            extra = str(a.get("iban") or "").strip()
            extra = ("IBAN …" + extra[-4:]) if extra else (t("pocket / salvadanaio") + (
                f" «{a.get('account_name')}»" if a.get("account_name") and not any(
                    _same(a.get("account_name"), o.get("account_name")) for o in same if o["uid"] != a["uid"]) else ""))
            name = f"{name} · {extra}"
        has_bal = pd.notna(a.get("balance"))
        if not has_bal and rows.empty:
            continue
        out.append({"id": f"k|{a['uid']}", "digits": "", "account": acc, "kind": "", "uid": a["uid"],
                    "is_account": True, "ccy": ccy, "name": name, "rows": rows,
                    "balance": float(a["balance"]) if has_bal else None, "balance_ccy": ccy or None,
                    "balance_date": str(a.get("balance_date") or "")[:10] if has_bal else None})
    out += _pocket_items(tx)
    return out


def _pocket_items(tx: pd.DataFrame) -> list[dict]:
    """Pocket Revolut seguiti dai giroconti (Collega banche → Pocket e salvadanai), se non nascosti."""
    try:
        from core import forecast, pockets
        pk = pockets.pockets()
    except Exception:
        return []
    out = []
    for pid, p in pk.items():
        if not pockets.shown(p):
            continue
        name, ccy = p.get("name") or "", str(p.get("currency") or "").upper()
        rows = tx[(tx["account"] == name) & (tx["currency"] == ccy)] if not tx.empty else tx
        try:
            bal = forecast.account_balance(name, ccy, tx) if not tx.empty else None
        except Exception:
            bal = None
        out.append({"id": f"p|{pid}", "digits": "", "account": p.get("bank") or name, "kind": "", "uid": None,
                    "is_account": True, "is_pocket": True, "pid": pid, "ccy": ccy, "name": name, "rows": rows,
                    "balance": bal, "balance_ccy": ccy or None, "balance_date": date.today().isoformat()})
    return out


def _balance(c: dict) -> tuple[float, str, str] | None:
    """(saldo, valuta, da dove viene e a che data) della voce, oppure None se non è sincronizzato."""
    base = db.base_currency()
    try:
        d = i18n.day_month(pd.Timestamp(str(c.get("balance_date") or "")[:10]))
    except (ValueError, TypeError):
        d = "–"
    if c.get("is_pocket"):
        if c.get("balance") is None:
            return None
        return c["balance"], c.get("balance_ccy") or base, t("pocket, saldo dai giroconti")
    if c.get("balance") is not None:
        src = t("saldo al {d}", d=d) if c.get("is_account") else t("saldo della carta al {d}", d=d)
        return c["balance"], c.get("balance_ccy") or base, src
    if c.get("account_balance") is not None:
        return c["account_balance"], c.get("account_balance_ccy") or base, t("saldo del conto al {d}", d=d)
    return None


def title_of(c: dict) -> str:
    if c.get("name"):
        return c["name"]
    kind = t(c["kind"]) if c.get("kind") else t("Carta")
    return f"{kind} •••• {c['digits']}" if c.get("digits") else kind


def _spent(rows: pd.DataFrame, start: date, end: date) -> float:
    if rows.empty:
        return 0.0
    return float(ui.filter_period(rows, start, end)["spesa_base"].sum())


def render() -> None:
    style.header(t("Carte"), t("Le tue carte, il saldo sincronizzato dalla banca e le spese fatte con ognuna"))
    tx = ui.prepared_transactions(apply_view=False)
    if not tx.empty and "card" not in tx.columns:
        tx["card"] = None
    items = _card_list(tx)
    base = db.base_currency()
    today = date.today()
    som = today.replace(day=1)
    if msg := st.session_state.pop("cards_flash", None):
        st.success(msg, icon=":material/check_circle:")
    if not items:
        st.info(t("Non ho ancora trovato carte. Le riconosco dal numero scritto nella descrizione dei movimenti "
                  "(per esempio «Carta N. ***** 123» negli estratti e nel collegamento Fineco) e dalle carte "
                  "collegate via Open Banking. Se hai importato gli estratti Fineco prima di questa versione, "
                  "importa di nuovo l'ultimo file (anche lo stesso): i movimenti già presenti non si duplicano e "
                  "le carte vengono riconosciute anche nello storico."), icon=":material/credit_card:")
        _hidden_box()
        return

    grads = []
    for i, c in enumerate(items):
        month = _spent(c["rows"], som, today)
        bal = _balance(c)
        sub = f"{c['account']} · {bal[2] if bal is not None else t('saldo non sincronizzato')}"
        grads.append(dict(id=c["id"], label=title_of(c), sub=sub,
                          value=ui.money(bal[0], bal[1]) if bal is not None else "–",
                          foot=(t("Speso questo mese:"), ui.money(month, base)),
                          variant=VARIANTS[i % len(VARIANTS)], pct=None))
    st.caption(t("Saldo sincronizzato dalla banca e, sotto, quanto hai speso questo mese. Clicca su una carta o "
                 "su un conto per vedere i movimenti."))
    sel = style.gradient_cards(grads, key="cards_grid")
    if sel:
        c = next((x for x in items if x["id"] == sel), None)
        if c:
            st.dialog(ui.esc(title_of(c)), width="large")(_card_body)(c["id"])

    rows = []
    for c in items:
        r = c["rows"]
        last = r["date"].max() if not r.empty else None
        if c.get("is_pocket"):
            synced = (t("{v} (pocket, dai giroconti)", v=ui.money(c["balance"], c["balance_ccy"] or base))
                      if c.get("balance") is not None else "–")
        elif c.get("balance") is not None and c.get("is_account"):
            synced = t("{v} (conto, {d})", v=ui.money(c["balance"], c["balance_ccy"] or base),
                       d=_dd(c["balance_date"]))
        elif c.get("balance") is not None:
            synced = t("{v} (carta, {d})", v=ui.money(c["balance"], c["balance_ccy"] or base),
                       d=_dd(c["balance_date"]))
        elif c.get("account_balance") is not None:
            synced = t("{v} (conto {acc}, {d})", v=ui.money(c["account_balance"], c["account_balance_ccy"] or base),
                       acc=c["account"], d=_dd(c["balance_date"]))
        else:
            synced = t("non collegata")
        rows.append({t("Carta o conto"): title_of(c), t("Conto"): c["account"],
                     t("Questo mese"): ui.money(_spent(r, som, today), base),
                     t("Ultimi 12 mesi"): ui.money(_spent(r, today - timedelta(days=365), today), base),
                     t("Movimenti"): int(len(r)),
                     t("Ultimo utilizzo"): f"{last:{i18n.strf()}}" if last is not None and pd.notna(last) else "–",
                     t("Saldo sincronizzato"): synced})
    with style.card("cards_table"):
        st.subheader(t("Riepilogo"))
        style.table(pd.DataFrame(rows), {t("Movimenti"): "int"})
        st.caption(t("Il saldo sincronizzato arriva dal collegamento con la banca (Collega banche → Sincronizza): "
                     "per una carta di credito è quello della carta, per una carta di debito quello del conto a cui è "
                     "collegata. Revolut non indica con quale carta è stato fatto un pagamento, quindi le sue carte "
                     "non si possono separare: compare il conto, con il suo saldo e tutte le sue spese."))
    _hidden_box()


def _find(card_id: str) -> dict | None:
    tx = ui.prepared_transactions(apply_view=False)
    if not tx.empty and "card" not in tx.columns:
        tx["card"] = None
    return next((c for c in _card_list(tx) if c["id"] == card_id), None)


def _card_body(card_id: str) -> None:
    c = _find(card_id)
    if c is None:
        st.caption(t("Carta non trovata."))
        return
    base = db.base_currency()
    today = date.today()
    som = today.replace(day=1)
    prev_end = som - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    rows = c["rows"].sort_values("date", ascending=False)
    spent_rows = rows[rows["spesa_base"] != 0]
    items = [(t("Questo mese"), ui.money(_spent(rows, som, today), base)),
             (t("Mese scorso"), ui.money(_spent(rows, prev_start, prev_end), base)),
             (t("Ultimi 12 mesi"), ui.money(_spent(rows, today - timedelta(days=365), today), base)),
             (t("Movimenti"), f"{len(rows)}", t("dal {d}", d=f"{rows['date'].min():{i18n.strf()}}") if not rows.empty
              else None)]
    if c.get("is_pocket"):
        if c.get("balance") is not None:
            items.insert(0, (t("Saldo del pocket"), ui.money(c["balance"], c["balance_ccy"] or base),
                             t("dai giroconti con {acc}", acc=c["account"])))
    elif c.get("balance") is not None:
        items.insert(0, (t("Saldo del conto") if c.get("is_account") else t("Saldo della carta"),
                         ui.money(c["balance"], c["balance_ccy"] or base),
                         t("dalla banca, {d}", d=_dd(c["balance_date"]))))
    elif c.get("account_balance") is not None:
        items.insert(0, (t("Saldo del conto"), ui.money(c["account_balance"], c["account_balance_ccy"] or base),
                         t("{acc}, dalla banca, {d}", acc=c["account"], d=_dd(c["balance_date"]))))
    style.kpis(items, cols=len(items))

    if not spent_rows.empty:
        months = pd.period_range(end=pd.Timestamp(today).to_period("M"), periods=12, freq="M")
        by = spent_rows.groupby("mese")["spesa_base"].sum().reindex(months, fill_value=0)
        fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in months], y=by.values,
                               marker_color=[style.SPESA if p == months[-1] else style.rgba(style.SPESA, 0.45)
                                             for p in months],
                               hovertemplate="%{x}<br>%{y:,.2f} " + base + "<extra></extra>"))
        st.subheader(t("Spese mese per mese"))
        style.chart(fig, height=200, legend=False)
        left, right = st.columns([2, 3], gap="medium")
        fkey = f"card_catf_{card_id}"
        with left:
            st.subheader(t("Per categoria"))
            last12 = ui.filter_period(spent_rows, today - timedelta(days=365), today)
            cats = last12.groupby("cat_label")["spesa_base"].sum().sort_values(ascending=False)
            cmap = ui.color_map()
            sel = style.category_bars([(k, float(v), cmap.get(k, "#A3A0B5")) for k, v in cats.items()],
                                      lambda v: ui.money(v, base), limit=7, key=f"card_cats_{card_id}")
            if sel:  # clic sulla stessa categoria: torna a tutte
                st.session_state[fkey] = None if st.session_state.get(fkey) == sel else sel
                st.session_state.pop(f"card_n_{card_id}", None)
            st.caption(t("Ultimi 12 mesi. Clicca su una categoria per vedere solo i suoi movimenti."))
        with right:
            cat = st.session_state.get(fkey)
            if cat and cat not in set(rows["cat_label"]):
                cat = st.session_state[fkey] = None
            _tx_section(rows[rows["cat_label"] == cat] if cat else rows, base, card_id, cat=cat)
    else:
        _tx_section(rows, base, card_id)

    st.subheader(t("Gestisci"))
    if card_id.startswith("c|"):
        _p, account, digits = card_id.split("|", 2)
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        new = c1.text_input(t("Nome della carta"), value=c.get("name") or "", key=f"card_name_{card_id}",
                            placeholder=title_of({**c, "name": ""}))
        if c2.button(t("Salva nome"), key=f"card_save_{card_id}"):
            cards.set_name(account, digits, new)
            st.session_state["cards_flash"] = t("Nome della carta salvato.")
            st.rerun()
        if st.button(t("Nascondi questa carta"), key=f"card_hide_{card_id}", icon=":material/visibility_off:",
                     help=t("Per esempio una carta scaduta o sostituita. I movimenti restano.")):
            cards.set_hidden(account, digits, True)
            st.rerun()
    elif c.get("is_pocket"):
        st.caption(t("Pocket seguito dai giroconti con {acc}: il nome si cambia in Collega banche → Pocket e "
                     "salvadanai, dove puoi anche farlo ricomparire qui.", acc=c["account"]))
        if st.button(t("Nascondi questo pocket da Carte"), key=f"pk_hide_{card_id}", icon=":material/visibility_off:",
                     help=t("Il saldo resta comunque nei totali.")):
            from core import pockets
            pockets.set_show(c["pid"], False)
            st.rerun()
    elif c.get("is_account"):
        st.caption(t("Conto collegato via Open Banking: il conto dell'app si sceglie in Collega banche."))
    else:
        st.caption(t("Carta collegata via Open Banking: il nome si cambia in Collega banche."))


def _tx_section(rows: pd.DataFrame, base: str, card_id: str, cat: str | None = None) -> None:
    st.subheader(t("Movimenti"))
    if cat:
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        c1.markdown(t("Solo **{cat}**: {n} movimenti, {v} di spese", cat=ui.esc(cat), n=len(rows),
                      v=ui.esc(ui.money(float(rows["spesa_base"].sum()), base))))
        if c2.button(t("Tutte le categorie"), key=f"crd_catall_{card_id}", icon=":material/filter_alt_off:",
                     width="stretch"):
            st.session_state[f"card_catf_{card_id}"] = None
            st.session_state.pop(f"card_n_{card_id}", None)
            st.rerun(scope="fragment")
    if rows.empty:
        st.caption(t("Nessun movimento con questa carta."))
        return
    shown = st.session_state.get(f"card_n_{card_id}", 15)
    sel = style.tx_list(rows.head(shown), lambda v, ccy: ui.money(v, ccy), ui.color_map(), base,
                        key=f"card_tx_{card_id}")
    if len(rows) > shown and st.button(t("Mostra altri ({n})", n=len(rows) - shown), key=f"card_more_{card_id}",
                                       icon=":material/expand_more:"):
        st.session_state[f"card_n_{card_id}"] = shown + 30
        st.rerun(scope="fragment")
    if sel is not None:
        st.session_state[focus.PENDING] = sel
        st.rerun()


def _hidden_box() -> None:
    meta = cards.cards_df()
    hid = meta[meta["hidden"].fillna(0).astype(int) == 1] if not meta.empty else meta
    if hid.empty:
        return
    with st.expander(t("Carte nascoste ({n})", n=len(hid)), icon=":material/visibility_off:"):
        for m in hid.itertuples():
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.write(f"{title_of({'name': m.name, 'kind': m.kind, 'digits': m.digits})} · {m.account}")
            if c2.button(t("Mostra"), key=f"card_unhide_{m.account}_{m.digits}", width="stretch"):
                cards.set_hidden(m.account, m.digits, False)
                st.rerun()
