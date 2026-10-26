from datetime import date

import pandas as pd
import streamlit as st

from core import db, fx, i18n
from core.i18n import t
from core.categorize import Categorizer, recategorize_all
from views import focus, style, ui

TIPI = {"Uscita": "uscita", "Entrata": "entrata", "Trasferimento/Investimento": "neutro"}


def _add_form():
    base = db.base_currency()
    with st.expander(t("Aggiungi movimento"), icon=":material/add:", expanded=False):
        tipo = st.segmented_control(t("Tipo"), list(TIPI), default="Uscita", key="tx_tipo", format_func=t)
        tipo = tipo or "Uscita"
        cats = db.category_names(TIPI[tipo])
        with st.form("add_tx", clear_on_submit=True):
            c1, c2, c3 = st.columns([1, 1, 1])
            d = c1.date_input(t("Data"), value=date.today(), format=i18n.date_fmt())
            amount = c2.number_input(t("Importo"), min_value=0.0, step=1.0, format="%.2f")
            ccy_opts = fx.COMMON_CURRENCIES + ["Altra…"]
            ccy = c3.selectbox(t("Valuta"), ccy_opts, index=ccy_opts.index(base) if base in ccy_opts else 0,
                               format_func=lambda c: t("Altra…") if c == "Altra…" else c)
            c4, c5 = st.columns([2, 1])
            desc = c4.text_input(t("Descrizione"), placeholder=t("es. Spesa Esselunga"))
            other_ccy = c5.text_input(t("Codice valuta (se 'Altra…')"), max_chars=3, placeholder=t("es. VND"))
            c6, c7, c8 = st.columns([1, 1, 1])
            auto = "__auto__"
            category = c6.selectbox(t("Categoria"), [auto] + cats,
                                    format_func=lambda c: t("Automatica (dalla descrizione)") if c == auto else ui.cat(c))
            accounts = db.accounts_list()
            new_acc = "__nuovo__"
            account = c7.selectbox(t("Conto"), accounts + [new_acc],
                                   format_func=lambda a: t("Nuovo conto…") if a == new_acc else a)
            new_account = c8.text_input(t("Nome nuovo conto"), placeholder=t("solo se 'Nuovo conto…'"))
            c9, c10 = st.columns([2, 1])
            notes = c9.text_input(t("Note"))
            manual_rate = c10.number_input(t("Cambio manuale →{base} (0 = automatico)", base=base), min_value=0.0,
                                           step=0.0001, format="%.6f")
            submitted = st.form_submit_button(t("Salva movimento"), type="primary")

        if submitted:
            currency = (other_ccy.strip().upper() if ccy == "Altra…" else ccy)
            if len(currency) != 3:
                st.error(t("Indica un codice valuta di 3 lettere."))
                return
            if amount <= 0:
                st.error(t("L'importo deve essere maggiore di zero."))
                return
            acc = new_account.strip() if account == new_acc else account
            if not acc:
                st.error(t("Indica il nome del nuovo conto."))
                return
            signed = -amount if tipo == "Uscita" else amount
            if tipo == "Trasferimento/Investimento":
                signed = -amount  # uscita dal conto indicato
            if category == auto:
                cat = Categorizer().categorize(desc, signed)
                if TIPI[tipo] == "neutro" and cat not in cats:
                    cat = cats[0] if cats else cat
                locked = 0
            else:
                cat, locked = category, 1
            if manual_rate > 0:
                rate = manual_rate
            else:
                try:
                    rate = fx.get_rate(currency, base, d)
                except fx.FxError as e:
                    st.error(t("Cambio non disponibile ({err}). Inserisci un cambio manuale e riprova.", err=e))
                    return
            row = {
                "date": d.isoformat(), "description": desc.strip(), "amount": signed, "currency": currency,
                "fx_rate": rate, "amount_base": round(signed * rate, 2), "base_currency": base,
                "category": cat, "category_locked": locked, "account": acc, "source": "manuale",
                "notes": notes, "external_id": None,
            }
            db.insert_transactions([row])
            extra = (t(" = {v} (cambio {r})", v=ui.money(row["amount_base"], base), r=f"{rate:.4f}")
                     if currency != base else "")
            st.success(ui.esc(t("Salvato: {what} {v}{extra} → {cat}", what=desc or cat, v=ui.money(signed, currency),
                                extra=extra, cat=ui.cat(cat))))


def _rule_box():
    with st.expander(t("Crea una regola di categorizzazione"), icon=":material/auto_fix_high:"):
        st.caption(t("Ogni movimento la cui descrizione contiene la parola indicata riceverà la categoria scelta "
                     "(per i nuovi import e, se vuoi, anche per quelli già presenti non modificati a mano)."))
        c1, c2, c3 = st.columns([2, 2, 1])
        kw = c1.text_input(t("Parola chiave"), key="rule_kw", placeholder=t("es. netflix"))
        cat = c2.selectbox(t("Categoria"), db.category_names(), key="rule_cat", format_func=ui.cat)
        apply_all = c3.checkbox(t("Applica anche ai vecchi"), value=True, key="rule_apply")
        if st.button(t("Aggiungi regola"), key="rule_add"):
            if not kw.strip():
                st.error(t("Scrivi una parola chiave."))
            else:
                db.add_rule(kw, cat, priority=10)
                msg = t("Regola aggiunta: '{kw}' → {cat}.", kw=kw.strip().lower(), cat=ui.cat(cat))
                if apply_all:
                    msg += t(" Movimenti ricategorizzati: {n}.", n=recategorize_all())
                st.success(msg)


def render():
    style.header(t("Movimenti"), ui.view_summary())
    base = db.base_currency()
    if msg := st.session_state.pop("mov_msg", None):
        st.success(msg)
    _add_form()
    _rule_box()

    df = ui.prepared_transactions()
    if df.empty:
        st.info(t("Nessun movimento registrato."))
        return

    with style.card("elenco"):
        st.subheader(t("Elenco movimenti"))
        first = df["date"].min().date() if df["date"].notna().any() else None
        start, end = ui.period_picker("mov", default="Ultimi 3 mesi", first_date=first)
        f1, f3, f4 = st.columns([2, 1, 2])
        cats_sel = f1.multiselect(t("Categorie"), db.category_names(), placeholder=t("Tutte"), format_func=ui.cat)
        tipo_sel = f3.selectbox(t("Tipo"), ["Tutti", "Uscite", "Entrate", "Neutri"], format_func=t)
        text = f4.text_input(t("Cerca nella descrizione"))

        view = ui.filter_period(df, start, end)
        if cats_sel:
            view = view[view["category"].isin(cats_sel)]
        if tipo_sel != "Tutti":
            view = view[view["kind"] == {"Uscite": "uscita", "Entrate": "entrata", "Neutri": "neutro"}[tipo_sel]]
        if text:
            view = view[view["description"].str.contains(text, case=False, na=False, regex=False)]

        summary = ui.esc(t("{n} movimenti, spese {s}, entrate {e}. ", n=len(view), s=ui.money(view["spesa"].sum()),
                           e=ui.money(view["entrata"].sum())))
        mode = st.segmented_control(t("Vista"), ["Elenco", "Modifica in tabella"], default="Elenco", key="mov_mode",
                                    label_visibility="collapsed", format_func=t)
        if mode != "Modifica in tabella":
            st.caption(summary + t("Clicca su un movimento per vederne il dettaglio."))
            n_show = st.session_state.get("mov_n", 50)
            sel = style.tx_list(view.head(n_show), lambda v, c: ui.money(v, c), ui.color_map(), base, key="mov_tx")
            if sel is not None:
                focus.open_focus(sel)
            if len(view) > n_show:
                if st.button(t("Mostra altri {n}", n=min(50, len(view) - n_show)), key="mov_more"):
                    st.session_state["mov_n"] = n_show + 50
                    st.rerun()
            return
        st.caption(summary + t("Modifica le celle e premi **Salva modifiche**; spunta «Elimina» per cancellare."))
        edit = view[["id", "date", "description", "amount", "currency", "valore_base", "category", "account", "notes"]].copy()
        edit["date"] = edit["date"].dt.date
        # in tabella la categoria si vede (e si sceglie) con il nome nella lingua dell'app
        labels = db.category_labels()
        to_key = {v: k for k, v in labels.items()}
        orig_cat = dict(zip(edit["id"], edit["category"]))
        edit["category"] = edit["category"].map(lambda c: labels.get(c, c) if isinstance(c, str) else None)
        edit.insert(0, "elimina", False)
        edited = st.data_editor(
            edit, hide_index=True, width="stretch", key="tx_editor", num_rows="fixed",
            column_config={
                "elimina": st.column_config.CheckboxColumn(t("Elimina"), width="small"),
                "id": None,
                "date": st.column_config.DateColumn(t("Data"), format=i18n.date_fmt()),
                "description": st.column_config.TextColumn(t("Descrizione"), width="large"),
                "amount": st.column_config.NumberColumn(t("Importo"), format="%.2f", help=t("Negativo = uscita")),
                "currency": st.column_config.TextColumn(t("Valuta"), width="small"),
                "valore_base": st.column_config.NumberColumn(t("In {base}", base=base), format="%.2f", disabled=True),
                "category": st.column_config.SelectboxColumn(t("Categoria"), options=[labels.get(n, n) for n in db.category_names()],
                                                             width="medium"),
                "account": st.column_config.TextColumn(t("Conto")),
                "notes": st.column_config.TextColumn(t("Note")),
            },
        )
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button(t("Salva modifiche"), type="primary"):
            orig = edit.set_index("id")
            changed = deleted = 0
            to_delete = edited.loc[edited["elimina"], "id"].tolist()
            if to_delete:
                db.delete_transactions(to_delete)
                deleted = len(to_delete)
            for _, r in edited[~edited["elimina"]].iterrows():
                o = orig.loc[r["id"]]
                fields = {}
                for col in ["description", "account", "notes"]:
                    if (r[col] or "") != (o[col] or ""):
                        fields[col] = r[col]
                if (r["category"] or "") != (o["category"] or ""):   # nome mostrato → categoria salvata
                    new_cat = to_key.get(r["category"], r["category"]) if r["category"] else None
                    if (new_cat or "") != (orig_cat.get(r["id"]) or ""):
                        fields.update(category=new_cat, category_locked=1)
                if r["date"] is None or pd.isna(r["amount"]):
                    continue
                money_changed = (r["date"] != o["date"] or float(r["amount"]) != float(o["amount"])
                                 or str(r["currency"]).upper() != str(o["currency"]).upper())
                if money_changed:
                    ccy = str(r["currency"]).upper().strip()
                    fields.update({"date": r["date"].isoformat(), "amount": float(r["amount"]), "currency": ccy})
                    try:
                        rate = fx.get_rate(ccy, base, r["date"])
                        fields.update({"fx_rate": rate, "amount_base": round(float(r["amount"]) * rate, 2),
                                       "base_currency": base})
                    except fx.FxError:
                        fields.update({"fx_rate": None, "amount_base": None})
                if fields:
                    db.update_transaction(int(r["id"]), **fields)
                    changed += 1
            st.session_state["mov_msg"] = t("Aggiornati {n} movimenti, eliminati {d}.", n=changed, d=deleted)
            st.rerun()
        out = view[["date", "description", "amount", "currency", "valore_base", "category", "account", "notes", "source"]].copy()
        out["category"] = out["category"].map(lambda c: ui.cat(c) if isinstance(c, str) else "")
        out = out.rename(columns={"valore_base": f"importo_{base}"})
        out["date"] = out["date"].dt.strftime(i18n.strf())
        sep, dec = (",", ".") if i18n.is_en() else (";", ",")  # come se lo aspetta Excel nella lingua scelta
        c2.download_button(t("Esporta CSV"), out.to_csv(index=False, sep=sep, decimal=dec).encode("utf-8-sig"),
                           file_name=t("movimenti_{a}_{b}.csv", a=start, b=end), mime="text/csv",
                           icon=":material/download:")
