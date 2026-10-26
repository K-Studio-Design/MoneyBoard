import pandas as pd
import streamlit as st

from core import db, i18n, importers
from core.i18n import t
from core.categorize import Categorizer
from views import style, ui


def _preview_and_import(rows: list[dict], account: str, source: str, key: str):
    if not rows:
        st.warning(t("Nessun movimento valido trovato nel file."))
        return
    cat = Categorizer()
    prev = pd.DataFrame([{
        "Data": r["date"], "Descrizione": r["description"], "Importo": r["amount"], "Valuta": r["currency"],
        "Categoria prevista": ui.cat(r.get("_force_category") or cat.categorize(
            r["description"], r["amount"], r.get("_bank_category"), r.get("_counterparty"), r.get("_reversal", False))),
    } for r in rows])
    per_ccy = "; ".join(
        t("{ccy}: uscite {out}, entrate {inc}", ccy=c, out=ui.fmt_num(-g.loc[g["Importo"] < 0, "Importo"].sum()),
          inc=ui.fmt_num(g.loc[g["Importo"] > 0, "Importo"].sum()))
        for c, g in prev.groupby("Valuta"))
    st.write(t("**{n} movimenti** dal {a} al {b} — {per_ccy} (giroconti inclusi)", n=len(prev),
               a=f"{pd.to_datetime(prev['Data']).min():{i18n.strf()}}", b=f"{pd.to_datetime(prev['Data']).max():{i18n.strf()}}",
               per_ccy=per_ccy))
    show = prev.assign(Data=pd.to_datetime(prev["Data"], errors="coerce")).rename(columns={c: t(c) for c in prev.columns})
    style.table(show, {t("Data"): "date", t("Importo"): "num"}, height=320, neg=(t("Importo"),))
    if st.button(t("Importa {n} movimenti in «{acc}»", n=len(prev), acc=account), icon=":material/download_done:",
                 type="primary", key=f"imp_{key}"):
        with st.spinner(t("Categorizzo e converto le valute…")):
            final = importers.finalize(rows, account, source)
            ins, skip = db.insert_transactions(final)
        missing = sum(1 for r in final if r.get("amount_base") is None)
        st.success(t("Importati {n} movimenti nuovi", n=ins) + (t(", {n} già presenti saltati", n=skip) if skip else "") + ".")
        if missing:
            st.warning(t("{n} movimenti senza cambio disponibile: ricalcolali da Impostazioni quando sei online.", n=missing))


COUNTRIES = {"IT": "Italia", "EU": "Europa", "DE": "Germania", "AT": "Austria", "CH": "Svizzera", "FR": "Francia",
             "ES": "Spagna", "GB": "Regno Unito", "IE": "Irlanda", "NL": "Paesi Bassi", "BE": "Belgio",
             "US": "Stati Uniti"}


def _label(pid: str) -> str:
    from core import banks
    p = banks.BY_ID[pid]
    if p.id == "auto":
        return "🏦 " + t(p.name)
    country = COUNTRIES.get(p.country)
    return f"{p.name} · {t(country)}" if country else p.name


def _short(name: str) -> str:
    """Nome conto proposto: «Lloyds / Halifax / …» → «Lloyds», «BancoPosta (Poste Italiane)» → «BancoPosta»."""
    return name.split(" / ")[0].split(" (")[0].strip()


def render():
    from core import banks

    style.header(t("Importa estratti"), t("I movimenti già presenti vengono riconosciuti e saltati, anche con periodi sovrapposti"))
    ids = [p.id for p in banks.ordered()]
    saved = db.get_setting("import_bank") or "fineco"
    pid = st.selectbox(t("La tua banca"), ids, index=ids.index(saved) if saved in ids else 0, format_func=_label,
                       key="imp_bank",
                       help=t("Scrivi per cercare. Se la tua banca non c'è, scegli «Altra banca» in fondo all'elenco: "
                              "l'app prova a riconoscere il file da sola, oppure indichi tu le colonne."))
    if pid != saved:
        db.set_setting("import_bank", pid)
    p = banks.BY_ID[pid]
    if p.special == "fineco":
        _fineco()
    elif p.special == "revolut":
        _revolut()
    elif p.special == "chase":
        _chase_tab()
    else:
        _bank_panel(p)


def _fineco() -> None:
    st.markdown(t(
        "**Come esportare da Fineco:** sito web Fineco → *Conto* → *Movimenti* → imposta il periodo → "
        "icona **Esporta in Excel**. Carica qui il file `.xlsx`/`.xls` così com'è."))
    account = st.text_input(t("Nome conto"), value="Fineco", key="fin_acc")
    pend = st.checkbox(t("Includi movimenti non ancora contabilizzati («Autorizzato»)"), value=False, key="fin_pend",
                       help=t("Sconsigliato: quando vengono contabilizzati cambiano descrizione e risulterebbero doppi."))
    f = st.file_uploader(t("File movimenti Fineco"), type=["xlsx", "xls", "csv"], key="fin_file")
    if f:
        try:
            df = importers.parse_fineco(f.getvalue(), f.name, include_pending=pend)
            owner = df.attrs.get("owner")
            if owner and db.add_owner_name(owner):
                st.info(t("Intestatario rilevato: **{owner}**. I bonifici verso/da questo nome saranno "
                          "considerati giroconti tra i tuoi conti (modificabile in Impostazioni).", owner=owner))
            _preview_and_import(importers.fineco_rows(df), account, "fineco", "fin")
        except Exception as e:
            st.error(t("Lettura non riuscita: {err}. Scegli «Altra banca» nell'elenco per indicare le colonne a mano.",
                       err=e))


def _revolut() -> None:
    st.markdown(t(
        "**Come esportare da Revolut:** app → *Profilo* → *Documenti ed estratti conto* → "
        "**Estratto conto consolidato** → formato **Excel** → scegli il periodo. "
        "Contiene in un solo file tutti i conti (EUR, USD, …) e gli interessi del conto deposito. "
        "Va bene anche il classico estratto CSV di un singolo conto."))
    account = st.text_input(t("Nome conto"), value="Revolut", key="rev_acc")
    pending = st.checkbox(t("Includi movimenti in sospeso (solo CSV)"), value=False, key="rev_pend")
    f = st.file_uploader(t("File Revolut"), type=["csv", "xlsx"], key="rev_file")
    if f:
        try:
            kind, df = importers.parse_revolut_any(f.getvalue(), f.name, include_pending=pending)
            if kind == "consolidato":
                st.info(t("Estratto **consolidato** riconosciuto. Movimenti per conto/valuta: ") + ", ".join(
                    f"{sez}: {len(g)} ({' '.join(sorted(g['currency'].unique()))})"
                    for sez, g in df.groupby("section")))
                st.caption(t("Gli importi restano nella valuta originale; il controvalore in euro è quello "
                             "applicato da Revolut. Gli interessi giornalieri del conto deposito sono "
                             "raggruppati per mese. Ricariche da Fineco, cambi valuta e spostamenti sul conto "
                             "deposito sono «Trasferimenti tra conti» e non contano come spese."))
                rows = importers.revolut_consolidated_rows(df, account)
            else:
                rows = importers.revolut_rows(df, account)
            _preview_and_import(rows, account, "revolut", "rev")
        except Exception as e:
            st.error(t("Lettura non riuscita: {err}. Scegli «Altra banca» nell'elenco per indicare le colonne a mano.",
                       err=e))


def _bank_panel(p) -> None:
    """Qualsiasi banca preconfigurata (e «Altra banca»): istruzioni, nome conto, file, anteprima e import."""
    from core import banks

    if p.id != "auto":
        st.markdown(f"**{t('Come esportare da {bank}:', bank=p.name)}** " + t(p.how))
    else:
        st.markdown(t(p.how))
    extra = [x for x in ("OFX/QFX", "QIF", "CAMT", "MT940") if x.split("/")[0] not in p.files]
    note = t("Formati accettati: {f}.", f=p.files)
    if extra:
        note += " " + t("Se la banca li offre, vanno bene anche {f}.", f=", ".join(extra))
    st.caption(note + " " + t("Gli estratti PDF non si possono leggere."))
    if p.card:
        st.caption(t("Estratto della carta: i pagamenti della carta dal conto corrente sono «Trasferimenti tra conti» "
                     "e non contano come entrate."))
    default = t("Altro conto") if p.id == "auto" else _short(p.name)
    account = st.text_input(t("Nome conto"), value=default, key=f"bank_acc_{p.id}",
                            help=t("Usa sempre lo stesso nome per lo stesso conto: così i movimenti già importati "
                                   "vengono riconosciuti e non duplicati. Per conto e carta usa nomi diversi."))
    f = st.file_uploader(t("File dell'estratto"), type=banks.UPLOAD_TYPES, key=f"bank_file_{p.id}")
    if not f:
        return
    data = f.getvalue()
    try:
        res = banks.parse(p, data, f.name, base_ccy=db.base_currency())
    except Exception as e:
        if p.id == "auto":
            st.error(t("Non riesco a riconoscere da solo questo file: {err}. Indica tu le colonne qui sotto.", err=e),
                     icon=":material/error:")
        else:
            st.error(t("Non riesco a leggere questo file come estratto {bank}: {err}. Indica tu le colonne qui sotto.",
                       bank=p.name, err=e), icon=":material/error:")
        _manual(data, f.name, f"man_{p.id}", account)
        return
    q1, q2 = ("“", "”") if i18n.is_en() else ("«", "»")
    cols = ", ".join(f"{k} = {q1}{v}{q2}" for k, v in res.columns.items() if v)
    msg = t("File {fmt} letto: **{n} movimenti**.", fmt=res.fmt, n=len(res.rows))
    if cols:
        msg += " " + t("Colonne usate: {cols}.", cols=cols)
    if res.sheet and res.fmt == "Excel":
        msg += " " + t("Foglio: «{sheet}».", sheet=res.sheet)
    st.info(msg, icon=":material/task:")
    if res.auto:
        st.warning(t("Il file non ha i nomi di colonna che mi aspettavo per {bank}: le ho riconosciute in "
                     "automatico. Controlla l'anteprima prima di importare.", bank=p.name),
                   icon=":material/warning:")
    notes = []
    if res.skipped_pending == 1:
        notes.append(t("1 movimento non ancora contabilizzato (o rifiutato) saltato: lo importerai quando sarà "
                       "definitivo."))
    elif res.skipped_pending:
        notes.append(t("{n} movimenti non ancora contabilizzati (o rifiutati) saltati: li importerai quando "
                       "saranno definitivi.", n=res.skipped_pending))
    if res.skipped_invalid == 1:
        notes.append(t("1 riga senza data o importo validi non letta."))
    elif res.skipped_invalid:
        notes.append(t("{n} righe senza data o importo validi non lette.", n=res.skipped_invalid))
    if notes:
        st.caption(" ".join(notes))
    _preview_and_import(res.rows, account, p.id, f"bank_{p.id}")
    if st.toggle(t("Le colonne non sono giuste? Indicale tu"), key=f"man_on_{p.id}"):
        _manual(data, f.name, f"man_{p.id}", account)


def _manual(data: bytes, filename: str, key: str, account_default: str) -> None:
    """Import di un CSV/Excel indicando a mano le colonne."""
    skip = st.number_input(t("Righe da saltare prima dell'intestazione"), min_value=0, max_value=50, value=0,
                           key=f"{key}_skip")
    try:
        raw = importers.read_any(data, filename, header=None)
        df = raw.iloc[skip + 1:].copy()
        df.columns = [str(c) if pd.notna(c) else f"col{i}" for i, c in enumerate(raw.iloc[skip].tolist())]
        df = df.dropna(how="all")
    except Exception as e:
        st.error(t("Impossibile leggere il file: {err}", err=e))
        return
    style.table(df.head(8).fillna("").astype(str), {c: "text" for c in df.columns})
    cols = list(df.columns)
    none = "—"
    c1, c2, c3 = st.columns(3)
    c_date = c1.selectbox(t("Colonna data"), cols, key=f"{key}_date")
    c_desc = c2.selectbox(t("Colonna descrizione"), cols, index=min(1, len(cols) - 1), key=f"{key}_desc")
    mode = c3.radio(t("Importi"), ["Una colonna con segno", "Colonne separate entrate/uscite"], format_func=t,
                    key=f"{key}_mode")
    c4, c5, c6 = st.columns(3)
    if mode == "Una colonna con segno":
        c_amt = c4.selectbox(t("Colonna importo"), cols, index=min(2, len(cols) - 1), key=f"{key}_amt")
        c_in = c_out = None
        invert = c5.checkbox(t("Le spese sono positive (inverti segno)"), key=f"{key}_inv")
    else:
        c_amt = None
        c_in = c4.selectbox(t("Colonna entrate"), [none] + cols, key=f"{key}_in")
        c_out = c5.selectbox(t("Colonna uscite"), [none] + cols, key=f"{key}_out")
        c_in = None if c_in == none else c_in
        c_out = None if c_out == none else c_out
        invert = False
    c_ccy = c6.selectbox(t("Colonna valuta"), [none] + cols, key=f"{key}_ccy")
    c7, c8, c9 = st.columns(3)
    fixed = c7.text_input(t("Valuta fissa (se nessuna colonna)"), value=db.base_currency(), max_chars=3,
                          key=f"{key}_fix")
    dayfirst = c8.checkbox(t("Date nel formato giorno/mese/anno"), value=not i18n.is_en(), key=f"{key}_df")
    account = c9.text_input(t("Nome conto"), value=account_default, key=f"{key}_acc")
    try:
        rows = importers.generic_rows(df, c_date, c_desc, c_amt, c_in, c_out,
                                      None if c_ccy == none else c_ccy, fixed.upper(), dayfirst, invert)
        _preview_and_import(rows, account, "file", key)
    except Exception as e:
        st.error(t("Mappatura non valida: {err}", err=e))


def _chase_tab() -> None:
    from core import chase

    st.markdown(t(
        "**Come esportare da Chase:** sito chase.com → apri il conto o la carta → icona **Download account activity** "
        "(freccia verso il basso sopra l'elenco movimenti) → *File type* **Spreadsheet (Excel, CSV)** → scegli il "
        "periodo → *Download*. Vanno bene anche i file **QFX/OFX** (Quicken). Gli estratti PDF non servono: "
        "lo stesso periodo in CSV contiene gli stessi movimenti."))
    st.caption(t("Riconosco da solo se il file è del conto corrente (checking/savings) o della carta di credito. "
                 "Gli importi restano in dollari; il controvalore in euro usa il cambio BCE del giorno. "
                 "I pagamenti della carta dal conto, i trasferimenti tra conti Chase e gli Zelle verso te stesso sono "
                 "«Trasferimenti tra conti»; i resi della carta riducono la spesa della categoria originale."))
    f = st.file_uploader(t("File Chase"), type=["csv", "qfx", "ofx"], key="chase_file")
    if not f:
        return
    try:
        kind, rows = chase.parse(f.getvalue(), f.name)
    except Exception as e:
        st.error(t("Lettura non riuscita: {err}. Se è un CSV di un'altra banca scegli «Altra banca» nell'elenco.",
                   err=e))
        return
    label = {"checking": t("conto corrente Chase"), "card": t("carta di credito Chase")}[kind]
    fmt = "QFX/OFX" if f.name.lower().endswith((".qfx", ".ofx")) else "CSV"
    st.info(t("File {fmt} riconosciuto: **{label}**.", fmt=fmt, label=label))
    default = "Chase" if kind == "checking" else "Chase carta"
    account = st.text_input(t("Nome conto"), value=default, key=f"chase_acc_{kind}",
                            help=t("Usa sempre lo stesso nome per lo stesso conto: così i movimenti già importati "
                                   "vengono riconosciuti e non duplicati. Per conto e carta usa nomi diversi."))
    if fmt == "QFX/OFX":
        st.caption(t("Consiglio: per lo stesso conto usa sempre lo stesso formato (sempre CSV o sempre QFX), "
                     "perché le descrizioni sono leggermente diverse e i duplicati non verrebbero riconosciuti."))
    _preview_and_import(rows, account, "chase", f"chase_{kind}")
