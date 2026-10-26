"""Cartelle dell'app (database, estratti da importare, backup), spostamento del database e backup automatici.

Le impostazioni delle cartelle di import e backup stanno nel database; la posizione del database stesso sta
in un piccolo file nella cartella predefinita (~/AppSpese_dati/posizione_dati.json) per l'Admin e nell'elenco
degli utenti (core/users.py) per gli altri, perché serve prima di poter aprire il database.
Nessun utente può scegliere una cartella che appartiene a un altro utente (vedi users.folder_conflict).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from core import db
from core.i18n import t

IMPORT_DIR_KEY = "import_dir"
IMPORT_AUTO_KEY = "import_auto"
BACKUP_DIR_KEY = "backup_dir"
BACKUP_AUTO_KEY = "backup_auto"
BACKUP_DAYS_KEY = "backup_every_days"
BACKUP_KEEP_KEY = "backup_keep"
BACKUP_LAST_KEY = "backup_last"
BACKUP_PATTERN = re.compile(r"^spese_backup_(\d{4}-\d{2}-\d{2}_\d{6})\.db$")
CLOUD_HINTS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud")


# ---------------------------------------------------------------- cartelle
def is_cloud_folder(path: Path | str) -> bool:
    low = str(path).lower()
    return any(h in low for h in CLOUD_HINTS)


def onedrive_candidates() -> list[Path]:
    """Cartelle OneDrive dell'utente (utili come destinazione dei backup)."""
    out = []
    for env in ("OneDriveConsumer", "OneDrive", "OneDriveCommercial"):
        v = os.environ.get(env)
        if v and Path(v).is_dir():
            out.append(Path(v))
    try:
        for p in Path.home().iterdir():
            if p.is_dir() and p.name.lower().startswith("onedrive"):
                out.append(p)
    except OSError:
        pass
    return list(dict.fromkeys(out))


def import_dir() -> Path:
    v = (db.get_setting(IMPORT_DIR_KEY, "") or "").strip()
    return Path(v).expanduser() if v else db.get_data_dir() / "Estratti da importare"


def backup_dir() -> Path:
    v = (db.get_setting(BACKUP_DIR_KEY, "") or "").strip()
    return Path(v).expanduser() if v else db.get_data_dir() / "Backup"


def import_auto() -> bool:
    return (db.get_setting(IMPORT_AUTO_KEY, "1") or "1") == "1"


def backup_auto() -> bool:
    return (db.get_setting(BACKUP_AUTO_KEY, "1") or "1") == "1"


def backup_every_days() -> int:
    try:
        return max(1, int(db.get_setting(BACKUP_DAYS_KEY, "7") or 7))
    except ValueError:
        return 7


def backup_keep() -> int:
    try:
        return max(1, int(db.get_setting(BACKUP_KEEP_KEY, "8") or 8))
    except ValueError:
        return 8


def check_folder(path: str | Path, create: bool = True) -> tuple[bool, str]:
    """Verifica che la cartella esista (o la crea) e sia scrivibile. Ritorna (ok, messaggio)."""
    p = Path(str(path).strip().strip('"')).expanduser()
    if not str(path).strip():
        return False, t("Percorso vuoto.")
    if not p.is_absolute():
        return False, t("Scrivi il percorso completo (es. C:\\Users\\nome\\Documenti\\Estratti).")
    try:
        if not p.exists():
            if not create:
                return False, t("La cartella non esiste.")
            p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir():
            return False, t("Il percorso indica un file, non una cartella.")
        probe = p / ".appspese_prova"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return False, t("Cartella non utilizzabile: {err}", err=e)
    return True, str(p)


def pick_folder(initial: str | Path | None = None) -> str | None:
    """Apre la finestra di Windows «Scegli cartella» (gira in un processo separato, così non blocca l'app).
    Ritorna None se non è disponibile o se l'utente annulla."""
    code = (
        "import sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        "p = filedialog.askdirectory(initialdir=sys.argv[1] if len(sys.argv) > 1 else None, "
        "title='Scegli la cartella')\n"
        "print(p or '')\n"
    )
    try:
        res = subprocess.run([sys.executable, "-c", code, str(initial or "")], capture_output=True, text=True,
                             timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (res.stdout or "").strip()
    return str(Path(out)) if out else None


def folder_conflict(path: str | Path) -> str | None:
    """Motivo per cui l'utente collegato non può usare la cartella (è di un altro utente), None se va bene."""
    from core import users
    return users.folder_conflict(db.current_user() or users.ADMIN, path)


def _checked_folder(path: str | Path) -> str:
    """Cartella pronta all'uso e non appartenente ad altri utenti (altrimenti RuntimeError con il motivo)."""
    raw = str(path).strip().strip('"')
    p = Path(raw).expanduser()
    if raw and p.is_absolute():  # controllo prima di creare la cartella
        why = folder_conflict(p)
        if why:
            raise RuntimeError(t("non puoi usare questa cartella: {why}", why=why))
    ok, msg = check_folder(path)
    if not ok:
        raise RuntimeError(msg)
    return msg


def set_import_dir(path: str | Path) -> str:
    folder = _checked_folder(path)
    db.set_setting(IMPORT_DIR_KEY, folder)
    return folder


def set_backup_dir(path: str | Path) -> str:
    folder = _checked_folder(path)
    db.set_setting(BACKUP_DIR_KEY, folder)
    return folder


# ---------------------------------------------------------------- database
def _open(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path), timeout=30)


def _integrity_ok(path: Path) -> bool:
    # closing(): su Windows un file con una connessione aperta non si può rinominare né cancellare
    # (il «with sqlite3.connect()» di Python NON chiude la connessione, conferma solo le modifiche)
    with closing(_open(path)) as d:
        return d.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def _replace(src: Path, dst: Path, attempts: int = 20) -> None:
    """os.replace con qualche nuovo tentativo: OneDrive e l'antivirus a volte tengono il file appena creato
    bloccato per qualche istante (WinError 32 «file utilizzato da un altro processo»)."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.25 * (i + 1) if i < 8 else 2.0)


def _cleanup_tmp(folder: Path) -> None:
    """Toglie i file .tmp rimasti da copie interrotte (più vecchi di 10 minuti)."""
    try:
        for p in folder.glob("spese*.tmp"):
            if time.time() - p.stat().st_mtime > 600:
                try:
                    p.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def _copy_sqlite(src: Path, dst: Path) -> None:
    """Copia coerente del database (API di backup di SQLite: sicura anche con l'app aperta)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_tmp(dst.parent)
    tmp = dst.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    with closing(_open(src)) as s, closing(_open(tmp)) as d:
        s.backup(d)
    if not _integrity_ok(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(t("verifica del database copiato non riuscita"))
    _replace(tmp, dst)


def move_database(new_dir: str | Path, use_existing: bool = False) -> str:
    """Sposta (copia) il database nella nuova cartella e la rende quella in uso.
    Se lì c'è già un database: con use_existing=True si usa quello, altrimenti viene salvato come backup e
    sostituito con quello attuale. Il database nella vecchia cartella resta dov'è (non viene cancellato)."""
    admin = db.is_admin()
    if admin and os.environ.get("APP_SPESE_DATA"):
        raise RuntimeError(t("la cartella dati è fissata dalla variabile d'ambiente APP_SPESE_DATA"))
    target = Path(_checked_folder(new_dir))
    current = db.db_path()
    dst = target / "spese.db"
    if target.resolve() == current.parent.resolve():
        return t("È già la cartella in uso.")
    # le cartelle degli estratti e dei backup restano dove sono: si fissano prima di spostare il database
    # (altrimenti, se erano quelle predefinite, «seguirebbero» il database nella nuova cartella)
    for key, fn in ((IMPORT_DIR_KEY, import_dir), (BACKUP_DIR_KEY, backup_dir)):
        if not (db.get_setting(key, "") or "").strip():
            db.set_setting(key, str(fn()))
    if dst.exists() and use_existing:
        if not _integrity_ok(dst):
            raise RuntimeError(t("il database presente nella nuova cartella è danneggiato"))
        note = t("Uso il database che c'era già nella nuova cartella.")
    else:
        if dst.exists():
            keep = target / f"spese_prima_dello_spostamento_{datetime.now():%Y-%m-%d_%H%M%S}.db"
            shutil.copy2(dst, keep)
        _copy_sqlite(current, dst)
        note = t("Database copiato nella nuova cartella.")
    if not admin:
        # utente creato dall'Admin: la posizione si salva nell'elenco degli utenti
        from core import users
        users.set_data_dir(db.current_user(), target)
        return note + t(" La copia precedente resta in {path} (puoi cancellarla tu quando vuoi).", path=current.parent)
    db.DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if target.resolve() == db.DEFAULT_DATA_DIR.resolve():
        db.POINTER_FILE.unlink(missing_ok=True)
    else:
        db.POINTER_FILE.write_text(json.dumps({"data_dir": str(target)}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    return note + t(" La copia precedente resta in {path} (puoi cancellarla tu quando vuoi).", path=current.parent)


# ---------------------------------------------------------------- backup
def list_backups() -> list[tuple[datetime, Path, int]]:
    d = backup_dir()
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        m = BACKUP_PATTERN.match(p.name)
        if m and p.is_file():
            out.append((datetime.strptime(m.group(1), "%Y-%m-%d_%H%M%S"), p, p.stat().st_size))
    return sorted(out, reverse=True)


def backup_now() -> Path:
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"spese_backup_{datetime.now():%Y-%m-%d_%H%M%S}.db"
    _copy_sqlite(db.db_path(), dst)
    db.set_setting(BACKUP_LAST_KEY, datetime.now().isoformat(timespec="seconds"))
    # tiene solo gli ultimi N (solo i file creati dall'app: nomi spese_backup_AAAA-MM-GG_hhmmss.db)
    for _, p, _ in list_backups()[backup_keep():]:
        try:
            p.unlink()
        except OSError:
            pass
    return dst


def last_backup() -> datetime | None:
    v = db.get_setting(BACKUP_LAST_KEY, "") or ""
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def backup_due() -> bool:
    last = last_backup()
    if last is None:
        files = list_backups()
        last = files[0][0] if files else None
    return last is None or datetime.now() - last >= timedelta(days=backup_every_days())


def maybe_auto_backup() -> Path | None:
    """Da chiamare all'avvio: fa un backup se è attivo e se è passato l'intervallo scelto."""
    if not backup_auto() or not backup_due():
        return None
    if not db.db_path().exists():
        return None
    return backup_now()


def restore_backup(path: Path) -> Path:
    """Ripristina un backup. Prima salva una copia del database attuale (spese_prima_del_ripristino_…)."""
    path = Path(path)
    if not _integrity_ok(path):
        raise RuntimeError(t("il backup scelto è danneggiato"))
    current = db.db_path()
    safety = backup_dir() / f"spese_prima_del_ripristino_{datetime.now():%Y-%m-%d_%H%M%S}.db"
    _copy_sqlite(current, safety)
    _copy_sqlite(path, current)
    return safety
