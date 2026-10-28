import streamlit as st

from core import db, fx
from core.i18n import t
from core.categorize import recategorize_all
from views import cerca, lingua, style, ui

KINDS = ["uscita", "entrata", "neutro"]


def render():
    style.header(t("Impostazioni"))
    tab1, tab2, tab3, tab4, tab5 = st.tabs([t("Generali"), t("Categorie"), t("Regole automatiche"),
                                            t("Cartelle e backup"), t("Email e promemoria")],
                                           default=cerca.tab_default("impostazioni"))

    with tab1:
        lingua.selector("set_lang")
        base = db.base_currency()
        opts = fx.COMMON_CURRENCIES
        new_base = st.selectbox(t("Valuta base (totali e grafici)"), opts, index=opts.index(base) if base in opts else 0,
                                key="base_ccy")
        if new_base != base:
            db.set_setting("base_currency", new_base)
            with st.spinner(t("Ricalcolo i controvalori…")):
                ok, fail = fx.recompute_missing_or_all(all_rows=True)
            st.success(t("Valuta base impostata a {ccy}. Ricalcolati {n} movimenti", ccy=new_base, n=ok)
                       + (t(", {n} senza cambio.", n=fail) if fail else "."))
        st.caption(t("Nome, colore dell'avatar e intestatari dei conti si modificano nel Profilo (clic sull'avatar in alto a destra)."))
        auto = st.toggle(t("Aggiorna le quotazioni dei titoli all'apertura dell'app"),
                         value=db.get_setting("auto_update_prices") == "1")
        db.set_setting("auto_update_prices", "1" if auto else "0")
        from core import demo_mode, updates
        if not demo_mode.enabled():
            upd = st.toggle(t("Avvisami quando esce una nuova versione"), value=updates.enabled(), key="set_upd",
                            help=t("Una volta al giorno chiede a GitHub qual è l'ultima versione pubblicata. Non "
                                   "manda nessun dato dell'app."))
            if upd != updates.enabled():
                db.set_setting(updates.ENABLED_KEY, "1" if upd else "0")
                st.session_state.pop("_update_notice", None)
        if st.button(t("Ricalcola cambi mancanti")):
            with st.spinner(t("Ricalcolo…")):
                ok, fail = fx.recompute_missing_or_all(all_rows=False)
            st.success(t("Aggiornati {n} movimenti", n=ok) + (t(", {n} ancora senza cambio.", n=fail) if fail else "."))

    with tab2:
        st.caption(t("Tipo: **uscita** (conta nelle spese), **entrata** (conta nelle entrate), "
                     "**neutro** (escluso dai totali: giroconti, acquisto titoli…)."))
        st.caption(t("Ogni categoria ha un nome in italiano e uno in inglese: l'app mostra quello della lingua scelta. "
                     "Se il nome inglese è vuoto si usa quello italiano (e viceversa per una categoria nuova)."))
        cats = db.categories_df()
        src = cats[["name", "icon", "name", "name_en", "kind", "color"]].copy()
        src.columns = ["orig", "icon", "name", "name_en", "kind", "color"]
        src["name_en"] = src["name_en"].map(lambda v: v if isinstance(v, str) else "")
        ed = st.data_editor(
            src, hide_index=True, width="stretch", num_rows="dynamic", key="cat_editor",
            column_config={
                "orig": None,
                "icon": st.column_config.TextColumn(t("Icona"), width="small"),
                "name": st.column_config.TextColumn(t("Nome in italiano")),
                "name_en": st.column_config.TextColumn(t("Nome in inglese")),
                "kind": st.column_config.SelectboxColumn(t("Tipo"), options=KINDS, required=True, format_func=t),
                "color": st.column_config.TextColumn(t("Colore (#RRGGBB)")),
            },
        )
        names = db.category_names()
        fallback = st.selectbox(t("Se elimini una categoria, sposta i suoi movimenti in"), names,
                                index=names.index("Altre spese") if "Altre spese" in names else 0, format_func=ui.cat)
        if st.button(t("Salva categorie"), type="primary"):
            errors = []

            def _txt(v) -> str:
                return str(v).strip() if isinstance(v, str) else ""

            # nome della categoria (la chiave salvata): quello italiano, oppure l'inglese per una categoria nuova
            ed = ed.copy()
            ed["name"] = [_txt(n) or _txt(e) for n, e in zip(ed["name"], ed["name_en"])]
            ed["name_en"] = [_txt(e) for e in ed["name_en"]]
            ed = ed[ed["name"] != ""]
            final_names = [n.lower() for n in ed["name"]]
            shown_en = [(e or n).lower() for n, e in zip(ed["name"], ed["name_en"])]
            if len(final_names) != len(set(final_names)):
                st.error(t("Ci sono nomi di categoria duplicati: correggili prima di salvare."))
            elif len(shown_en) != len(set(shown_en)):
                st.error(t("Ci sono nomi inglesi duplicati (o uguali al nome di un'altra categoria): correggili prima "
                           "di salvare."))
            else:
                remaining_orig = {o for o in ed["orig"].tolist() if isinstance(o, str) and o}
                # 1) eliminazioni
                for old in cats["name"]:
                    if old not in remaining_orig:
                        if old == fallback:
                            errors.append(t("«{cat}» è la categoria di destinazione: non eliminata.", cat=ui.cat(old)))
                        else:
                            db.delete_category(old, fallback)
                # 2) rinomine, modifiche e nuove categorie
                for _, r in ed.iterrows():
                    name = r["name"]
                    kind = r["kind"] if r["kind"] in KINDS else "uscita"
                    orig = r["orig"] if isinstance(r["orig"], str) and r["orig"] else None
                    if orig and orig != name:
                        db.rename_category(orig, name)
                    db.upsert_category(name, kind, r["icon"] or "", r["color"] or "#888888",
                                       name_en=r["name_en"] if r["name_en"] != name else "")
                for e in errors:
                    st.warning(e)
                st.success(t("Categorie salvate."))
                if not errors:
                    st.rerun()

    with tab3:
        st.caption(t("Le regole assegnano la categoria quando la descrizione contiene la parola chiave (parola intera, "
                     "maiuscole indifferenti). Vince la priorità più alta, poi la parola più lunga. "
                     "Una regola su categoria di uscita vale solo per importi negativi, di entrata solo per positivi."))
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        kw = c1.text_input(t("Parola chiave"))
        cat = c2.selectbox(t("Categoria"), db.category_names(), format_func=ui.cat)
        prio = c3.number_input(t("Priorità"), value=10, step=1)
        c4.write("")
        if c4.button(t("Aggiungi")):
            if kw.strip():
                db.add_rule(kw, cat, int(prio))
                st.rerun()
        rules = db.rules_df()
        rules["category"] = rules["category"].map(ui.cat)     # nome della categoria nella lingua dell'app
        search = st.text_input(t("Filtra regole"))
        view = rules
        if search:
            view = rules[rules["keyword"].str.contains(search, case=False, regex=False)
                         | rules["category"].str.contains(search, case=False, regex=False)]
        view = view.copy()
        view.insert(0, "elimina", False)
        ed = st.data_editor(view, hide_index=True, width="stretch", key="rules_ed",
                            disabled=["id", "keyword", "category", "priority"],
                            column_config={"id": None, "elimina": st.column_config.CheckboxColumn("🗑️"),
                                           "keyword": t("Parola chiave"), "category": t("Categoria"),
                                           "priority": t("Priorità")})
        b1, b2 = st.columns(2)
        if b1.button(t("Elimina regole selezionate")):
            db.delete_rules(ed.loc[ed["elimina"], "id"].tolist())
            st.rerun()
        if b2.button("🔁 " + t("Riapplica regole ai movimenti (non modificati a mano)")):
            st.success(t("Movimenti ricategorizzati: {n}", n=recategorize_all()))

    with tab5:
        from views import notifiche
        notifiche.render_tab()

    with tab4:
        from views import cartelle
        cartelle.render_tab()
        st.divider()
        st.markdown("**" + t("Zona pericolosa") + "**")
        word = t("CANCELLA")
        confirm = st.text_input(t("Scrivi {w} per eliminare tutti i movimenti", w=word))
        if st.button(t("Elimina tutti i movimenti"), disabled=confirm != word):
            with db.connect() as con:
                con.execute("DELETE FROM transactions")
                con.execute("DELETE FROM tx_links")
            st.success(t("Movimenti eliminati."))
