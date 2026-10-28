"""Dettaglio di un singolo movimento: si apre cliccando su una riga degli elenchi."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, i18n
from core.i18n import t
from core.merchants import merchant_key, rule_keyword  # noqa: F401  (usati anche da altre pagine)
from views import style, ui

def _fmt_date_long(d: pd.Timestamp) -> str:
    if i18n.is_en():
        return f"{i18n.weekday(d.weekday())}, {i18n.date_long(d)}"
    return f"{i18n.weekday(d.weekday()).lower()} {i18n.date_long(d)}"


def _fmt_date_short(d: pd.Timestamp) -> str:
    return f"{d:{i18n.strf()}}"


def open_focus(tx_id: int) -> None:
    df = ui.prepared_transactions(apply_view=False)
    if df.empty or tx_id not in set(df["id"]):
        st.toast(t("Movimento non trovato"), icon=":material/error:")
        return
    r = df[df["id"] == tx_id].iloc[0]
    title = str(r["description"] or t("Movimento"))
    st.dialog(ui.esc(title[:70] + ("…" if len(title) > 70 else "")), width="large")(_body)(tx_id)


def _body(tx_id: int) -> None:
    base = db.base_currency()
    df = ui.prepared_transactions(apply_view=False)
    r = df[df["id"] == tx_id].iloc[0]
    d = r["date"]
    kind = r["kind"]

    # ---- intestazione: importo, data, conto, categoria
    conv = ""
    if r["currency"] != base and pd.notna(r["valore_base"]):
        rate = t(", cambio {r}", r=f"{r['fx_rate']:.4f}") if pd.notna(r.get("fx_rate")) else ""
        conv = f'<div class="conv">{style.e(ui.money(r["valore_base"], base))}{style.e(rate)}</div>'
    variant = {"uscita": "spesa", "entrata": "entrata"}.get(kind, "")
    st.html(f'''<div class="as-focus-top {variant}">
  <div><div class="amt">{style.e(ui.money(r["amount"], r["currency"]))}</div>{conv}</div>
  <div class="when"><b>{style.e(_fmt_date_long(d))}</b><br>{style.e(r["account"])}<br>{style.e(ui.cat(r["category"]))}</div>
</div>''')
    if kind == "neutro":
        st.caption(t("Movimento neutro (trasferimento tra conti o investimento): non conta nelle spese né nelle entrate."))
    if r.get("notes"):
        st.caption(t("Nota: {nota}", nota=r["notes"]))

    # ---- stesso esercente
    key = merchant_key(r["description"])
    same = df[df["description"].map(merchant_key) == key].sort_values("date")
    st.subheader(t("Da «{k}»", k=key) if kind != "entrata" else t("Da «{k}» (entrate)", k=key))
    n = len(same)
    val = "spesa_base" if kind == "uscita" else ("entrata_base" if kind == "entrata" else None)
    if n <= 1:
        st.caption(t("È l'unico movimento con questo esercente."))
    else:
        tot = same[val].sum() if val else same["valore_base"].sum()
        last12 = same[same["date"] >= pd.Timestamp(date.today() - timedelta(days=365))]
        tot12 = last12[val].sum() if val else last12["valore_base"].sum()
        gaps = same["date"].drop_duplicates().diff().dt.days.dropna()
        freq = t("in media ogni {n} giorni", n=f"{gaps.mean():.0f}") if len(gaps) >= 2 else None
        if n >= 3 and same["amount"].round(2).nunique() == 1 and len(gaps) >= 2 and 26 <= gaps.mean() <= 35:
            freq = t("ogni mese, stesso importo: sembra un pagamento ricorrente")
        style.kpis(cols=4, items=[
            (t("Volte"), f"{n}", freq),
            (t("Totale"), ui.money(tot, base), t("dal {d}", d=_fmt_date_short(same["date"].iloc[0]))),
            (t("Media a movimento"), ui.money(tot / n, base)),
            (t("Ultimi 12 mesi"), ui.money(tot12, base), t("{n} movimenti", n=len(last12))),
        ])
        by_month = same.groupby("mese")[val if val else "valore_base"].sum()
        # sempre 12 mesi, fino al mese del movimento (o a oggi se più recente): barre di larghezza costante
        end_p = max(d.to_period("M"), pd.Timestamp(date.today()).to_period("M"))
        months = pd.period_range(end=end_p, periods=12, freq="M")
        by_month = by_month.reindex(months, fill_value=0)
        if by_month.abs().sum() > 0:
            base_col = style.SPESA if kind == "uscita" else (style.ENTRATA if kind == "entrata" else style.NEUTRO)
            faded = {style.SPESA: "rgba(209,77,114,0.38)", style.ENTRATA: "rgba(43,165,130,0.38)",
                     style.NEUTRO: "rgba(139,149,161,0.38)"}[base_col]
            cur_p = d.to_period("M")
            fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in by_month.index], y=by_month.values,
                                   marker_color=[base_col if p == cur_p else faded for p in by_month.index],
                                   hovertemplate="%{y:,.2f} " + base + "<extra></extra>"))
            style.chart(fig, height=190, legend=False)
            st.caption(t("Ultimi 12 mesi; in evidenza {m}, il mese di questo movimento.",
                         m=f"{i18n.month(d.month)} {d.year}"))
        recent = same.sort_values("date", ascending=False).head(8)
        rows = "".join(
            f'<div class="{"cur" if int(x["id"]) == tx_id else ""}"><span>{_fmt_date_short(x["date"])}, '
            f'{style.e(x["account"])}</span><span>{style.e(ui.money(x["amount"], x["currency"]))}</span></div>'
            for _, x in recent.iterrows())
        st.html(f'<div class="as-mini">{rows}</div>')
        if n > 8:
            st.caption(t("Gli ultimi 8 di {n}. In grassetto quello aperto.", n=n))

    # ---- contesto nel mese
    if kind == "uscita" and r["spesa_base"] > 0:
        m_start = d.replace(day=1)
        month_df = df[(df["date"] >= m_start) & (df["date"] < m_start + pd.offsets.MonthBegin(1))]
        month_tot = month_df["spesa_base"].sum()
        cat_month = month_df[month_df["category"] == r["category"]]["spesa_base"].sum()
        hist = df[(df["category"] == r["category"]) & (df["date"] < m_start)
                  & (df["date"] >= m_start - pd.DateOffset(months=12))]
        n_months = max(hist["mese"].nunique(), 1) if not hist.empty else 0
        avg_cat = hist["spesa_base"].sum() / n_months if n_months else None
        st.subheader(t("Nel mese di {m}", m=i18n.month(d.month)))
        items = [(t("Peso sulle spese del mese"),
                  f"{ui.fmt_num(r['spesa_base'] / month_tot * 100, 1)}%" if month_tot else "–",
                  t("su {v}", v=ui.money(month_tot, base))),
                 (t("{cat} nel mese", cat=ui.cat(r["category"])), ui.money(cat_month, base),
                  t("media mensile {v}", v=ui.money(avg_cat, base)) if avg_cat else None)]
        if avg_cat:
            diff = (cat_month - avg_cat) / avg_cat * 100
            items.append((t("Rispetto alla media"), f"{diff:+.0f}%", t("ultimi 12 mesi"), "neg" if diff > 0 else "pos"))
        style.kpis(items, cols=3)

    # ---- modifica
    st.subheader(t("Modifica"))
    names = db.category_names()
    c1, c2 = st.columns([1, 1])
    new_cat = c1.selectbox(t("Categoria"), names, index=names.index(r["category"]) if r["category"] in names else 0,
                           format_func=ui.cat, key=f"fx_cat_{tx_id}")
    new_note = c2.text_input(t("Nota"), value=r.get("notes") or "", key=f"fx_note_{tx_id}")
    others = same[same["id"] != tx_id]
    apply_all = False
    if not others.empty:
        apply_all = st.checkbox(
            t("Applica la categoria anche agli altri {n} movimenti di «{k}» e ai prossimi import", n=len(others), k=key),
            key=f"fx_all_{tx_id}")
    b1, b2 = st.columns([1, 3])
    if b1.button(t("Salva"), type="primary", key=f"fx_save_{tx_id}"):
        fields = {"notes": new_note}
        if new_cat != r["category"]:
            fields.update(category=new_cat, category_locked=1)
        db.update_transaction(tx_id, **fields)
        if apply_all:
            for oid in others["id"]:
                db.update_transaction(int(oid), category=new_cat, category_locked=1)
            db.add_rule(rule_keyword(r["description"], key), new_cat, priority=10)
        st.rerun()

    with st.expander(t("Dividi il movimento"), icon=":material/call_split:", expanded=bool(db.split_family(tx_id))):
        _split_section(r, tx_id)
    with st.expander(t("Spese condivise"), icon=":material/group:"):
        _shared_section(r, tx_id)


# ---------------------------------------------------------------- dividere e condividere
def _split_section(r, tx_id: int) -> None:
    """Dividere il movimento in più categorie, oppure riunire le parti di un movimento già diviso."""
    fam = db.split_family(tx_id)
    if fam:
        df = db.transactions_df()
        parts = df[df["id"].isin(fam)].set_index("id").loc[fam]
        total = parts["amount"].sum()
        st.caption(t("Questo movimento è diviso in {n} parti (totale {v}):", n=len(fam),
                     v=ui.money(total, r["currency"])))
        lines = "".join(f'<div class="{"cur" if int(i) == tx_id else ""}"><span>{style.e(ui.cat(p["category"]))}'
                        f'{style.e(" · " + str(p["notes"])) if p["notes"] else ""}</span>'
                        f'<span>{style.e(ui.money(p["amount"], p["currency"]))}</span></div>'
                        for i, p in parts.iterrows())
        st.html(f'<div class="as-mini">{lines}</div>')
        if st.button(t("Riunisci le parti"), key=f"fx_unsplit_{tx_id}", icon=":material/call_merge:",
                     help=t("Annulla la divisione: le parti tornano un solo movimento (e le quote delle spese "
                            "condivise legate spariscono).")):
            db.unsplit(tx_id)
            st.toast(t("Parti riunite"), icon=":material/call_merge:")
            st.rerun()
        return
    total = round(abs(float(r["amount"])), 2)
    if total < 0.02:
        return
    st.caption(t("Per esempio un acquisto online con cose di categorie diverse: ogni parte conta nella sua "
                 "categoria, il totale resta quello della banca."))
    names = db.category_names()
    labels = {n: ui.cat(n) for n in names}
    to_key = {v: k for k, v in labels.items()}
    src = pd.DataFrame({"categoria": [labels.get(r["category"], r["category"]), None],
                        "importo": [total, None], "nota": ["", ""]})
    ed = st.data_editor(
        src, hide_index=True, num_rows="dynamic", width="stretch", key=f"fx_split_{tx_id}",
        column_config={
            "categoria": st.column_config.SelectboxColumn(t("Categoria"), options=list(labels.values()), width="medium"),
            "importo": st.column_config.NumberColumn(t("Importo ({ccy})", ccy=r["currency"]), min_value=0.0,
                                                     step=1.0, format="%.2f"),
            "nota": st.column_config.TextColumn(t("Nota")),
        })
    rows = ed.dropna(subset=["categoria", "importo"])
    rows = rows[rows["importo"] > 0]
    used = round(float(rows["importo"].sum()), 2)
    rest = round(total - used, 2)
    if abs(rest) >= 0.005:
        st.caption(t("Da assegnare: {v}", v=ui.money(rest if float(r["amount"]) >= 0 else -rest, r["currency"]))
                   if rest > 0 else t("Le parti superano il totale di {v}.", v=ui.money(-rest, r["currency"])))
    ok = len(rows) >= 2 and abs(rest) < 0.005
    if st.button(t("Dividi"), key=f"fx_split_go_{tx_id}", type="primary", icon=":material/call_split:", disabled=not ok):
        try:
            db.split_transaction(tx_id, [(to_key.get(x["categoria"], x["categoria"]), float(x["importo"]),
                                          str(x["nota"] or "")) for _, x in rows.iterrows()])
            st.toast(t("Movimento diviso in {n} parti", n=len(rows)), icon=":material/call_split:")
            st.rerun()
        except db.SplitError as e:
            st.error(str(e))


def _person_picker(key: str):
    """Persona esistente o nuova: ritorna (id o None, nome nuovo)."""
    from core import shared
    pe = shared.people()
    opts = [str(i) for i in pe["id"]] + ["__new__"]
    names = dict(zip([str(i) for i in pe["id"]], pe["name"]))
    who = st.selectbox(t("Persona"), opts, format_func=lambda k: names.get(k, t("Nuova persona…")), key=f"{key}_who")
    if who == "__new__":
        return None, st.text_input(t("Nome della persona"), key=f"{key}_new", placeholder=t("es. Marco"))
    return int(who), ""


def _shared_section(r, tx_id: int) -> None:
    """Spese condivise: la quota di un'altra persona su una spesa che hai pagato tu, oppure un rimborso."""
    from core import shared
    from views import condivise
    lk = shared.linked(tx_id)
    if not lk.empty:
        for _, e in lk.iterrows():
            c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
            c1.markdown(f"**{ui.esc(e['person'])}**: {ui.esc(condivise.balance_text(float(e['amount']), e['currency']))}"
                        f"  \n:gray[{ui.esc(t(condivise.KIND_LABELS.get(e['kind'], e['kind'])))}]")
            if c2.button(t("Scollega"), key=f"fx_unlink_{int(e['id'])}", width="stretch",
                         help=t("Toglie la voce dalle spese condivise (una quota torna nella spesa).")):
                shared.delete_entry(int(e["id"]))
                st.rerun()
    amount = float(r["amount"])
    if amount < 0 and abs(amount) >= 0.02:
        st.markdown("**" + t("Dividi con altre persone") + "**")
        st.caption(t("Hai pagato tu anche per qualcun altro: la sua parte non conta nelle tue spese e risulta come "
                     "soldi che ti deve."))
        pid, new = _person_picker(f"fx_share_{tx_id}")
        share = st.number_input(t("La sua parte ({ccy})", ccy=r["currency"]), min_value=0.0,
                                max_value=round(abs(amount) - 0.01, 2), value=round(abs(amount) / 2, 2), step=1.0,
                                format="%.2f", key=f"fx_share_amt_{tx_id}")
        if st.button(t("Aggiungi la sua quota"), key=f"fx_share_go_{tx_id}", icon=":material/group_add:"):
            try:
                pid = pid if pid is not None else shared.add_person(new)
                shared.share_transaction(tx_id, pid, share)
                st.toast(t("Quota aggiunta alle spese condivise"), icon=":material/group:")
                st.rerun()
            except (shared.SharedError, db.SplitError) as e:
                st.error(str(e))
    if lk.empty or int(tx_id) not in set(lk["tx_id"].dropna().astype(int)):
        st.markdown("**" + (t("È un rimborso da una persona") if amount > 0 else t("È un rimborso a una persona")) + "**")
        st.caption(t("Soldi che ti ha restituito (o che hai dato tu) per spese fatte insieme: aggiornano il saldo "
                     "con quella persona."))
        pid2, new2 = _person_picker(f"fx_settle_{tx_id}")
        neutral = st.checkbox(t("Non contarlo tra entrate e spese (diventa «Spese condivise»)"), value=True,
                              key=f"fx_settle_neu_{tx_id}")
        if st.button(t("Collega come rimborso"), key=f"fx_settle_go_{tx_id}", icon=":material/handshake:"):
            try:
                pid2 = pid2 if pid2 is not None else shared.add_person(new2)
                shared.settle_with_transaction(tx_id, pid2, neutral=neutral)
                st.toast(t("Rimborso collegato"), icon=":material/handshake:")
                st.rerun()
            except shared.SharedError as e:
                st.error(str(e))


# ---------------------------------------------------------------- dettaglio categoria
PENDING = "focus_pending_tx"
PENDING_CAT = "focus_pending_cat"
PENDING_SERIES = "focus_pending_series"   # pagamento ricorrente cliccato in un'altra finestra
PENDING_DAY = "focus_pending_day"         # giorno del calendario cliccato in un'altra finestra


def handle_pending() -> None:
    """Un movimento o una categoria cliccati dentro un'altra finestra di dettaglio si aprono qui, dopo la chiusura
    di quella finestra (Streamlit non permette due finestre una dentro l'altra)."""
    tx_id = st.session_state.pop(PENDING, None)
    cat = st.session_state.pop(PENDING_CAT, None)
    sid = st.session_state.pop(PENDING_SERIES, None)
    day = st.session_state.pop(PENDING_DAY, None)
    if tx_id is not None:
        open_focus(int(tx_id))
    elif cat:
        name, start, end = cat
        open_category(name, date.fromisoformat(start), date.fromisoformat(end))
    elif sid:
        from views import abbonamenti
        abbonamenti.open_series(str(sid))
    elif day:
        from views import calendario
        calendario.open_day(date.fromisoformat(str(day)))


def _period_label(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month and start.day == 1:
        last = (pd.Timestamp(start) + pd.offsets.MonthEnd(0)).day
        mese = f"{i18n.month(start.month)} {start.year}"
        return mese if end.day == last else t("1-{d} {mese}", d=end.day, mese=mese)
    return t("dal {a} al {b}", a=_fmt_date_short(pd.Timestamp(start)), b=_fmt_date_short(pd.Timestamp(end)))


def open_category(category: str, start: date, end: date) -> None:
    """Dettaglio di una categoria nel periodo [start, end], con i filtri di conto e valuta della barra laterale.
    `category` può essere il nome salvato o quello mostrato (es. il nome inglese): si usa sempre quello mostrato."""
    if category in db.category_labels():
        category = ui.cat(category)
    st.dialog(ui.esc(category), width="large")(_category_body)(category, start, end)


def _category_body(category: str, start: date, end: date) -> None:
    disp = ui.display_ccy()
    base = db.base_currency()
    df = ui.prepared_transactions()
    allcat = df[df["cat_label"] == category]
    cur_all = ui.filter_period(df, start, end)
    cur = cur_all[cur_all["cat_label"] == category]
    # categoria di spesa o di entrata, a seconda di cosa prevale
    col = "entrata" if cur["entrata"].sum() > cur["spesa"].sum() else "spesa"
    variant = "entrata" if col == "entrata" else "spesa"
    tot = cur[col].sum()
    tot_all = cur_all[col].sum()
    n = int((cur[col] != 0).sum())

    # periodo precedente di pari durata
    length = (end - start).days + 1
    p_end = start - timedelta(days=1)
    p_start = p_end - timedelta(days=length - 1)
    if start.day == 1 and start.month == end.month and start.year == end.year:
        # per un mese: stesso numero di giorni del mese precedente, per un confronto equo
        p_start = (start - timedelta(days=1)).replace(day=1)
        p_end = min(p_start + timedelta(days=length - 1), start - timedelta(days=1))
    prev = ui.filter_period(allcat, p_start, p_end)[col].sum()

    # media mensile dei 12 mesi prima del periodo
    m_start = pd.Timestamp(start).replace(day=1)
    hist = allcat[(allcat["date"] < m_start) & (allcat["date"] >= m_start - pd.DateOffset(months=12))]
    n_months = hist["mese"].nunique()
    first = allcat["date"].min()
    span = 12 if pd.notna(first) and first <= m_start - pd.DateOffset(months=12) else max(n_months, 1)
    avg_month = hist[col].sum() / span if n_months else None

    media = t(", in media {v}", v=ui.money(tot / n)) if n > 1 else ""
    count = t("1 movimento") if n == 1 else t("{n} movimenti", n=n)
    share = ""
    if tot_all:
        p = f"{tot / tot_all * 100:.0f}"
        share = (t("{p}% delle entrate del periodo", p=p) if col == "entrata"
                 else t("{p}% delle spese del periodo", p=p))
    st.html(f'''<div class="as-focus-top {variant}">
  <div><div class="amt">{style.e(ui.money(tot))}</div>
  <div class="conv">{style.e(count)}{style.e(media)}</div></div>
  <div class="when"><b>{style.e(_period_label(start, end).capitalize())}</b><br>
  {style.e(share)}<br>{style.e(ui.view_summary())}</div>
</div>''')

    def tone(x: float) -> str:  # più spesa = rosso, più entrata = verde
        return ("neg" if x > 0 else "pos") if col == "spesa" else ("pos" if x > 0 else "neg")

    items = [(t("Periodo precedente"), ui.money(prev), _period_label(p_start, p_end))]
    if prev:
        dp = (tot - prev) / prev * 100
        items.append((t("Variazione"), f"{dp:+.0f}%", t("sul periodo precedente"), tone(dp)))
    items.append((t("Media mensile"), ui.money(avg_month) if avg_month is not None else "–",
                  t("nei 12 mesi precedenti") if avg_month is not None else t("nessun dato precedente")))
    if avg_month and start.day == 1 and start.month == end.month and start.year == end.year:
        d = (tot - avg_month) / avg_month * 100
        items.append((t("Rispetto alla media"), f"{d:+.0f}%", t("in questo mese"), tone(d)))
    style.kpis(items, cols=len(items))

    # andamento: sempre 12 mesi, fino alla fine del periodo (o a oggi), in evidenza i mesi del periodo
    end_p = max(pd.Timestamp(end).to_period("M"), pd.Timestamp(date.today()).to_period("M"))
    months = pd.period_range(end=end_p, periods=12, freq="M")
    by_month = allcat.groupby("mese")[col].sum().reindex(months, fill_value=0)
    if by_month.abs().sum() > 0:
        st.subheader(t("Ultimi 12 mesi"))
        main = style.ENTRATA if col == "entrata" else style.SPESA
        faded = "rgba(43,165,130,0.38)" if col == "entrata" else "rgba(209,77,114,0.38)"
        p0, p1 = pd.Timestamp(start).to_period("M"), pd.Timestamp(end).to_period("M")
        fig = go.Figure(go.Bar(x=[ui.month_short(p) for p in months], y=by_month.values,
                               marker_color=[main if p0 <= p <= p1 else faded for p in months],
                               hovertemplate="%{x}<br>%{y:,.2f} " + disp + "<extra></extra>"))
        if avg_month:
            fig.add_hline(y=avg_month, line_dash="dot", line_color="#8B95A1")
        style.chart(fig, height=200, legend=False)
        st.caption(t("In evidenza il periodo scelto, la linea tratteggiata è la media mensile.") if avg_month
                   else t("In evidenza il periodo scelto."))

    if cur.empty:
        st.caption(t("Nessun movimento in questa categoria nel periodo."))
        return

    # dove: esercenti principali
    keys = cur["description"].map(merchant_key)
    by_m = cur.groupby(keys)[col].agg(["sum", "count"]).sort_values("sum", ascending=False)
    by_m = by_m[by_m["sum"] > 0]
    if len(by_m) > 1:
        st.subheader(t("Dove"))
        color = style.safe_color(ui.color_map().get(category, "#A3A0B5"))
        style.category_bars([(f"{k.title()} ({int(r['count'])})", float(r["sum"]), color) for k, r in by_m.iterrows()],
                            lambda v: ui.money(v), limit=6, others=t("Altri {n} esercenti", n="{n}"))

    # movimenti: cliccando se ne apre il dettaglio
    st.subheader(t("Movimenti"))
    rows = cur[cur[col] != 0].sort_values("date", ascending=False)
    shown = st.session_state.get(f"catf_n_{category}", 10)
    sel = style.tx_list(rows.head(shown), lambda v, c: ui.money(v, c), ui.color_map(), base,
                        key=f"catf_tx_{category}_{start}_{end}")
    if len(rows) > shown:
        if st.button(t("Mostra altri ({n})", n=len(rows) - shown), key=f"catf_more_{category}", icon=":material/expand_more:"):
            st.session_state[f"catf_n_{category}"] = shown + 20
            st.rerun(scope="fragment")
    if sel is not None:
        st.session_state[PENDING] = sel
        st.rerun()
