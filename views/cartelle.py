"""Impostazioni → Cartelle e backup: posizione del database, cartella degli estratti da importare, backup."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from core import autoimport, db, i18n, storage
from core.i18n import t
from views import style, ui

BANK_LABEL = {"Fineco": "Fineco", "Revolut": "Revolut", "Chase": "Chase"}


def _cap(e: Exception) -> str:
    txt = str(e)
    return txt[:1].upper() + txt[1:]


def _size(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{n / 1024:.0f} KB"


def _open_folder(path: Path, key: str) -> None:
    """Pulsante «Apri cartella» (solo Windows: apre Esplora file sul PC dove gira l'app)."""
    if hasattr(os, "startfile") and st.button(t("Apri cartella"), key=key, icon=":material/folder_open:"):
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))  # noqa: S606 - percorso scelto dall'utente
        except OSError as e:
            st.error(t("Non riesco ad aprirla: {err}", err=e))


def _browse(key: str) -> None:
    picked = storage.pick_folder(st.session_state.get(key) or Path.home())
    if picked:
        st.session_state[key] = picked
    else:
        st.session_state[f"{key}_nopick"] = True


def _folder_input(label: str, key: str, current: Path, help_text: str) -> str:
    if key not in st.session_state:
        st.session_state[key] = str(current)
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    value = c1.text_input(label, key=key, help=help_text)
    c2.button(t("Sfoglia…"), key=f"{key}_browse", on_click=_browse, args=(key,), width="stretch",
              help=t("Apre la finestra di Windows per scegliere la cartella"))
    if st.session_state.pop(f"{key}_nopick", False):
        st.caption(t("Nessuna cartella scelta (oppure la finestra non si può aprire qui): scrivi il percorso a mano."))
    return value


def render_tab() -> None:
    # ---------------------------------------------------------------- database
    st.subheader(t("Database"))
    path = db.db_path()
    try:
        size = _size(path.stat().st_size)
    except OSError:
        size = "–"
    st.markdown(t("In uso: `{path}` ({size})", path=path, size=size))
    if db.is_demo():
        st.info(t("Questo è un account di prova: i dati sono fittizi e separati da quelli degli altri utenti."),
                icon=":material/science:")
        sure = st.checkbox(t("Sì, voglio cancellare le modifiche e ricreare i dati di prova"), key="set_demo_sure")
        if st.button(t("Ripristina i dati di prova"), key="set_demo_reset", icon=":material/restart_alt:",
                     disabled=not sure):
            from core import demo
            n = demo.seed()
            st.cache_data.clear()
            st.success(t("Dati di prova ricreati: {n} movimenti.", n=n))
    from core import demo_mode
    if demo_mode.enabled():
        st.caption(t("Nella demo online cartelle e backup non si possono cambiare: scarica l'app per usarli."))
        return
    if db.is_admin() and os.environ.get("APP_SPESE_DATA"):
        st.info(t("La cartella è fissata dalla variabile d'ambiente APP_SPESE_DATA: per cambiarla da qui, toglila."))
    else:
        new_dir = _folder_input(t("Cartella del database"), "set_db_dir", path.parent,
                                t("Dove salvare il file spese.db con tutti i tuoi dati. Puoi scegliere qualsiasi "
                                  "cartella tranne quelle degli altri utenti."))
        if storage.is_cloud_folder(new_dir):
            st.warning(t("Questa cartella è sincronizzata nel cloud (OneDrive, Dropbox…). Funziona, ma se l'app "
                         "è aperta su due PC insieme o la sincronizzazione è lenta il database può rovinarsi. "
                         "Per il database è meglio una cartella locale e i **backup** su OneDrive."),
                       icon=":material/cloud:")
        target = Path(new_dir.strip().strip('"')).expanduser() if new_dir.strip() else None
        same = target is not None and target.exists() and target.resolve() == path.parent.resolve()
        why = storage.folder_conflict(target) if target is not None and target.is_absolute() and not same else None
        if why:
            st.error(t("Non puoi usare questa cartella: {why}.", why=why), icon=":material/block:")
        use_existing = False
        if target is not None and not same and not why and (target / "spese.db").exists():
            other = target / "spese.db"
            when = pd.Timestamp(other.stat().st_mtime, unit="s").tz_localize("UTC").tz_convert(None)
            choice = st.radio(
                t("In quella cartella c'è già un database"), ["porta", "usa"],
                format_func=lambda k: (t("Porta lì il database attuale (quello che c'è viene conservato come copia)")
                                       if k == "porta" else
                                       t("Usa il database che c'è lì (modificato il {d})",
                                         d=f"{when:{i18n.strf()} %H:%M}")),
                key="set_db_existing")
            use_existing = choice == "usa"
        if st.button(t("Sposta il database qui"), key="set_db_move", disabled=same or target is None or bool(why),
                     icon=":material/drive_file_move:"):
            try:
                storage.backup_now()  # copia di sicurezza prima di spostare
                msg = storage.move_database(target, use_existing=use_existing)
                st.cache_data.clear()
                st.success(msg)
                st.rerun()
            except Exception as e:
                st.error(t("Spostamento non riuscito: {err}", err=e))
        if db.is_admin():
            st.caption(t("La posizione scelta viene ricordata in {path}. Prima di spostare faccio sempre un backup.",
                         path=f"`{db.POINTER_FILE}`"))
        else:
            st.caption(t("La posizione scelta viene ricordata nell'elenco degli utenti dell'app. Prima di spostare "
                         "faccio sempre un backup."))

    st.divider()
    # ---------------------------------------------------------------- import automatico
    st.subheader(t("Estratti da importare"))
    imp = storage.import_dir()
    new_imp = _folder_input(t("Cartella degli estratti"), "set_imp_dir", imp,
                            t("Metti qui i file scaricati da Fineco, Revolut o Chase: l'app li importa da sola."))
    c1, c2 = st.columns([1, 1])
    if c1.button(t("Salva cartella"), key="set_imp_save", icon=":material/save:"):
        try:
            st.success(t("Cartella impostata: {path}", path=storage.set_import_dir(new_imp)))
        except RuntimeError as e:
            st.error(_cap(e))
    with c2:
        _open_folder(imp, "set_imp_open")
    auto = st.toggle(t("Importa in automatico all'avvio dell'app (e mentre è aperta, ogni 30 secondi)"),
                     value=storage.import_auto(), key="set_imp_auto")
    if auto != storage.import_auto():
        db.set_setting(storage.IMPORT_AUTO_KEY, "1" if auto else "0")
    pend = autoimport.pending_files(imp)
    st.caption(t("Formati riconosciuti: Fineco (Excel movimenti), Revolut (estratto consolidato Excel o CSV), "
                 "Chase (CSV conto e carta, QFX/OFX), export del portafoglio titoli (colonne ISIN e Quantità). "
                 "Dopo l'import il file va in «{done}», quelli sconosciuti in «{unknown}». File in attesa ora: {n}.",
                 done=autoimport.DONE_DIR, unknown=autoimport.UNKNOWN_DIR, n=len(pend)))
    if st.button(t("Controlla adesso"), key="set_imp_run", icon=":material/sync:"):
        with st.spinner(t("Importo…")):
            res = autoimport.run(force=True)
        if not res:
            st.info(t("Nessun file nuovo nella cartella."))
        for r in res:
            _show_result(r)
    log = autoimport.load_log()
    if log:
        with st.expander(t("Ultimi import automatici ({n})", n=len(log)), icon=":material/history:"):
            style.table(pd.DataFrame([{
                t("Quando"): pd.Timestamp(r["when"]).strftime(i18n.strf() + " %H:%M"), "File": r["file"],
                t("Conto"): r.get("account") or "–", t("Nuovi"): r.get("inserted", 0),
                t("Già presenti"): r.get("skipped", 0),
                t("Esito"): {"ok": t("importato"), "sconosciuto": t("non riconosciuto"), "in uso": t("file aperto"),
                             "errore": t("errore")}.get(r["status"], r["status"]), t("Note"): autoimport.message_text(r)}
                for r in log]), {"File": "text"}, height=360)

    st.divider()
    # ---------------------------------------------------------------- backup
    st.subheader(t("Backup"))
    bdir = storage.backup_dir()
    new_b = _folder_input(t("Cartella dei backup"), "set_bak_dir", bdir,
                          t("Meglio una cartella sincronizzata (es. OneDrive): così i backup sopravvivono "
                            "anche se il PC si rompe."))
    c1, c2, c3 = st.columns([1, 1, 1.4])
    if c1.button(t("Salva cartella"), key="set_bak_save", icon=":material/save:"):
        try:
            st.success(t("Cartella dei backup: {path}", path=storage.set_backup_dir(new_b)))
        except RuntimeError as e:
            st.error(_cap(e))
    with c2:
        _open_folder(bdir, "set_bak_open")
    od = storage.onedrive_candidates()
    if od and not storage.is_cloud_folder(bdir):
        sugg = od[0] / ("MoneyBoard backup" if db.is_admin() else f"MoneyBoard backup {db.current_user()}")
        if c3.button(t("Usa OneDrive"), key="set_bak_od", icon=":material/cloud_upload:", help=str(sugg)):
            try:
                storage.set_backup_dir(sugg)
                st.session_state.pop("set_bak_dir", None)
                st.rerun()
            except RuntimeError as e:
                st.error(_cap(e))
    elif not storage.is_cloud_folder(bdir):
        st.caption(t("Consiglio: scegli una cartella di OneDrive, così i backup sono al sicuro anche fuori dal PC."))

    c1, c2, c3 = st.columns(3)
    bauto = c1.toggle(t("Backup automatico"), value=storage.backup_auto(), key="set_bak_auto")
    if bauto != storage.backup_auto():
        db.set_setting(storage.BACKUP_AUTO_KEY, "1" if bauto else "0")
    every = c2.number_input(t("Ogni quanti giorni"), min_value=1, max_value=60, value=storage.backup_every_days(),
                            key="set_bak_every")
    if int(every) != storage.backup_every_days():
        db.set_setting(storage.BACKUP_DAYS_KEY, str(int(every)))
    keep = c3.number_input(t("Quanti tenerne"), min_value=1, max_value=100, value=storage.backup_keep(),
                           key="set_bak_keep", help=t("I più vecchi vengono cancellati."))
    if int(keep) != storage.backup_keep():
        db.set_setting(storage.BACKUP_KEEP_KEY, str(int(keep)))

    last = storage.last_backup()
    st.caption(t("Ultimo backup: {d} alle {h}", d=last.strftime(i18n.strf()), h=last.strftime("%H:%M")) if last
               else t("Nessun backup ancora."))
    c1, c2 = st.columns(2)
    if c1.button(t("Fai un backup adesso"), key="set_bak_now", icon=":material/backup:", type="primary"):
        try:
            p = storage.backup_now()
            st.success(t("Backup salvato: {name}", name=p.name))
        except Exception as e:
            st.error(t("Backup non riuscito: {err}", err=e))
    with open(path, "rb") as fh:
        c2.download_button(t("Scarica una copia del database"), fh.read(), file_name="spese_backup.db",
                           icon=":material/download:", key="set_bak_dl")

    backups = storage.list_backups()
    if backups:
        with st.expander(t("Backup disponibili ({n})", n=len(backups)), icon=":material/restore:"):
            labels = {str(p): f"{d:{i18n.strf()} %H:%M} ({_size(n)})" for d, p, n in backups}
            sel = st.selectbox(t("Backup"), list(labels), format_func=labels.get, key="set_bak_sel")
            sure = st.checkbox(t("Sì, voglio sostituire i dati attuali con quelli del backup"), key="set_bak_sure")
            if st.button(t("Ripristina questo backup"), key="set_bak_restore", disabled=not sure,
                         icon=":material/settings_backup_restore:"):
                try:
                    safety = storage.restore_backup(Path(sel))
                    st.cache_data.clear()
                    st.success(t("Backup ripristinato. I dati di prima sono salvati in {name}.", name=safety.name))
                except Exception as e:
                    st.error(t("Ripristino non riuscito: {err}", err=e))


def _show_result(r: dict) -> None:
    if r["status"] == "ok" and r.get("bank") == "Portafoglio titoli":
        st.success(t("{file}: portafoglio titoli aggiornato ({msg}).", file=r["file"], msg=autoimport.message_text(r)))
    elif r["status"] == "ok":
        st.success(t("{file}: {n} movimenti nuovi in «{acc}»", file=r["file"], n=r["inserted"], acc=r["account"])
                   + (t(", {n} già presenti", n=r["skipped"]) if r.get("skipped") else "") + ".")
    elif r["status"] in ("in uso", "sconosciuto"):
        st.warning(f"{r['file']}: {autoimport.message_text(r)}.")
    else:
        st.error(f"{r['file']}: {autoimport.message_text(r)}.")


def startup_notice(results: list[dict]) -> None:
    """Toast all'avvio con il riepilogo dell'import automatico."""
    for r in results:
        if r["status"] == "ok" and r.get("bank") == "Portafoglio titoli":
            st.toast(t("Portafoglio aggiornato da {file}: {msg}", file=r["file"], msg=autoimport.message_text(r)),
                     icon=":material/show_chart:")
        elif r["status"] == "ok":
            st.toast(t("Importato {file}: {n} movimenti nuovi in {acc}", file=r["file"], n=ui.fmt_num(r["inserted"], 0),
                       acc=r["account"]),
                     icon=":material/download_done:")
        elif r["status"] == "sconosciuto":
            st.toast(t("{file}: formato non riconosciuto", file=r["file"]), icon=":material/help:")
        elif r["status"] == "errore":
            st.toast(t("{file}: import non riuscito", file=r["file"]), icon=":material/error:")
