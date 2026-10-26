"""Amministratore e utenti dell'app.

L'amministratore si crea alla prima apertura dell'app (nome e password scelti da lui) e sta in un file a parte
della cartella base (``amministratore.json``): solo il nome, il sale e l'impronta della password.
Gli altri utenti li crea l'amministratore.

L'elenco sta in un file della cartella base (``utenti.json``), che nessun utente può scegliere come propria cartella.
Per ogni utente: nome per l'accesso (senza distinzione maiuscole/minuscole), impronta della password
(PBKDF2-SHA256, mai la password in chiaro), tipo (normale o di prova con dati fittizi) e cartella del database.

Ogni utente ha un identificativo fisso (``id``), che dà il nome alla sua cartella predefinita
``<cartella base>/utenti/<id>``: rinominare un utente non sposta i suoi dati. Un identificativo non viene mai
riusato finché esiste la sua cartella, così un utente nuovo non eredita i dati di uno cancellato.

Le cartelle (database, estratti, backup) di un utente non possono stare dentro quelle di un altro utente
né dentro le cartelle riservate dell'app: nessuno può leggere o sovrascrivere i dati degli altri.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from core import db
from core.i18n import t

FILE_NAME = "utenti.json"
ADMIN = "admin"
ITERATIONS = 300_000
MIN_PASSWORD = 8
NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9 ._-]{1,29}$")

ADMIN_FILE = "amministratore.json"

# nessun utente predefinito: l'amministratore si crea alla prima apertura, gli altri li crea lui
_DEFAULT: dict = {}

_lock = threading.RLock()
_cache: dict = {"key": None, "users": None}


class UserError(ValueError):
    """Errore da mostrare così com'è all'Admin (nome già usato, password troppo corta…)."""


# ---------------------------------------------------------------- file dell'elenco
def _file() -> Path:
    return db.root_data_dir() / FILE_NAME


def users_root() -> Path:
    return db.root_data_dir() / "utenti"


def _load() -> dict:
    """Elenco degli utenti (id -> dati). Se il file non c'è lo crea vuoto.
    Se il file è illeggibile NON lo sovrascrive (altrimenti si perderebbero gli utenti): solleva un errore."""
    f = _file()
    with _lock:
        try:
            st = f.stat()
        except FileNotFoundError:
            _save(json.loads(json.dumps(_DEFAULT)))
            st = f.stat()
        key = (st.st_mtime_ns, st.st_size)
        if _cache["key"] == key and _cache["users"] is not None:
            return _cache["users"]
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            users = data["users"]
            if not isinstance(users, dict):
                raise ValueError("formato non valido")
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise RuntimeError(f"elenco utenti illeggibile ({f}): {e}") from e
        _cache.update(key=key, users=users)
        return users


def _write_atomic(f: Path, data: dict) -> None:
    tmp = f.with_name(f".{f.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for i in range(20):  # su Windows il file può essere bloccato per un attimo (antivirus, OneDrive)
        try:
            os.replace(tmp, f)
            break
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.1)


def _save(users: dict) -> None:
    _write_atomic(_file(), {"version": 1, "users": users})
    _cache.update(key=None, users=None)


# ---------------------------------------------------------------- amministratore
def _admin_file() -> Path:
    return db.root_data_dir() / ADMIN_FILE


def admin_info() -> dict | None:
    """Nome, sale e impronta della password dell'amministratore; None se non è ancora stato creato.
    Se il file c'è ma è illeggibile solleva un errore (non si deve poter ricreare l'amministratore da capo)."""
    f = _admin_file()
    try:
        raw = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        raise RuntimeError(f"file dell'amministratore illeggibile ({f}): {e}") from e
    try:
        data = json.loads(raw)
        if not all(isinstance(data.get(k), str) and data.get(k) for k in ("name", "salt", "hash")):
            raise ValueError("formato non valido")
        bytes.fromhex(data["salt"])
    except (ValueError, TypeError, AttributeError) as e:
        raise RuntimeError(f"file dell'amministratore illeggibile ({f}): {e}") from e
    return data


def admin_exists() -> bool:
    """True se l'amministratore è già stato creato (o se il suo file c'è ma è rovinato: in quel caso non si
    propone di crearne uno nuovo, che prenderebbe i dati di quello vero)."""
    try:
        return admin_info() is not None
    except RuntimeError:
        return True


def admin_name() -> str:
    try:
        info = admin_info()
    except RuntimeError:
        info = None
    return info["name"] if info else ""


def _check_admin_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not NAME_RE.match(name):
        raise UserError(t("Il nome utente deve avere da 2 a 30 caratteri: lettere, numeri, spazi, punto, trattino "
                          "o trattino basso (e iniziare con una lettera o un numero)."))
    if find_by_name(name):
        raise UserError(t("Esiste già un utente che si chiama «{name}».", name=name))
    return name


def create_admin(name: str, password: str, repeat: str | None = None) -> str:
    """Crea l'amministratore alla prima apertura. Se esiste già non tocca niente e solleva UserError
    (due finestre aperte insieme non possono creare due amministratori)."""
    _validate_password(password, repeat)
    name = _check_admin_name(name)
    salt = secrets.token_hex(16)
    data = {"version": 1, "name": name, "salt": salt, "hash": hash_password(password, salt),
            "created": datetime.now().isoformat(timespec="seconds")}
    f = _admin_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        try:
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise UserError(t("L'amministratore esiste già: accedi con il suo nome e la sua password.")) from None
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2))
    return name


def rename_admin(name: str) -> None:
    with _lock:
        info = admin_info()
        if not info:
            raise UserError(t("Utente non trovato."))
        name = _check_admin_name(name)  # (nessun utente può già chiamarsi come l'amministratore)
        _write_atomic(_admin_file(), dict(info, name=name))


def set_admin_password(password: str, repeat: str | None = None) -> None:
    _validate_password(password, repeat)
    with _lock:
        info = admin_info()
        if not info:
            raise UserError(t("Utente non trovato."))
        salt = secrets.token_hex(16)
        _write_atomic(_admin_file(), dict(info, salt=salt, hash=hash_password(password, salt)))


def all_users() -> dict:
    """Copia dell'elenco: id -> dict(name, demo, data_dir, created, last_login, …)."""
    try:
        return json.loads(json.dumps(_load()))
    except RuntimeError:
        return {}


def get(uid: str | None) -> dict | None:
    if not uid or uid == ADMIN:
        return None
    return all_users().get(uid)


def exists(uid: str | None) -> bool:
    return uid == ADMIN or get(uid) is not None


def is_demo(uid: str | None) -> bool:
    u = get(uid)
    return bool(u and u.get("demo"))


def find_by_name(name: str) -> str | None:
    key = (name or "").strip().casefold()
    for uid, u in all_users().items():
        if u.get("name", "").casefold() == key:
            return uid
    return None


# ---------------------------------------------------------------- password
def hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), ITERATIONS).hex()


def _validate_name(name: str, uid: str | None = None) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not NAME_RE.match(name):
        raise UserError(t("Il nome utente deve avere da 2 a 30 caratteri: lettere, numeri, spazi, punto, trattino "
                          "o trattino basso (e iniziare con una lettera o un numero)."))
    if name.casefold() in (ADMIN, admin_name().casefold()):
        raise UserError(t("Questo nome è già usato dall'amministratore."))
    other = find_by_name(name)
    if other and other != uid:
        raise UserError(t("Esiste già un utente che si chiama «{name}».", name=name))
    return name


def _validate_password(password: str, repeat: str | None = None) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise UserError(t("La password deve avere almeno {n} caratteri.", n=MIN_PASSWORD))
    if password != password.strip():
        raise UserError(t("La password non può iniziare o finire con uno spazio."))
    if repeat is not None and password != repeat:
        raise UserError(t("Le due password non coincidono."))


def _new_id(name: str, users: dict) -> str:
    import unicodedata
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:24] or "utente"
    if base == ADMIN:
        base = "utente"
    uid, n = base, 1
    # mai un id già usato o con una cartella rimasta da un utente cancellato
    while uid in users or uid == ADMIN or (users_root() / uid).exists():
        n += 1
        uid = f"{base}_{n}"
    return uid


# ---------------------------------------------------------------- gestione (solo Admin)
def create(name: str, password: str, repeat: str | None = None, demo: bool = False) -> str:
    _validate_password(password, repeat)
    with _lock:
        users = _load()
        name = _validate_name(name)
        uid = _new_id(name, users)
        salt = secrets.token_hex(16)
        users = dict(users)
        users[uid] = {"name": name, "salt": salt, "hash": hash_password(password, salt), "demo": bool(demo),
                      "data_dir": None, "created": datetime.now().isoformat(timespec="seconds"), "last_login": None}
        _save(users)
    (users_root() / uid).mkdir(parents=True, exist_ok=True)
    return uid


def rename(uid: str, name: str) -> None:
    with _lock:
        users = dict(_load())
        if uid not in users:
            raise UserError(t("Utente non trovato."))
        users[uid] = dict(users[uid], name=_validate_name(name, uid))
        _save(users)


def set_password(uid: str, password: str, repeat: str | None = None) -> None:
    """Nuova password: i «resta connesso» già dati a quell'utente smettono di valere e le sue sessioni aperte
    vengono chiuse."""
    _validate_password(password, repeat)
    with _lock:
        users = dict(_load())
        if uid not in users:
            raise UserError(t("Utente non trovato."))
        salt = secrets.token_hex(16)
        users[uid] = dict(users[uid], salt=salt, hash=hash_password(password, salt))
        _save(users)


def set_demo(uid: str, demo: bool) -> None:
    with _lock:
        users = dict(_load())
        if uid in users:
            users[uid] = dict(users[uid], demo=bool(demo))
            _save(users)


def touch_login(uid: str) -> None:
    if uid == ADMIN:
        return
    try:
        with _lock:
            users = dict(_load())
            if uid in users:
                users[uid] = dict(users[uid], last_login=datetime.now().isoformat(timespec="seconds"))
                _save(users)
    except Exception:  # l'ultimo accesso è solo informativo
        pass


def delete(uid: str, delete_data: bool = False) -> str:
    """Toglie l'accesso all'utente. Con delete_data cancella anche la sua cartella predefinita
    (una cartella scelta da lui altrove non viene toccata: si dice dov'è)."""
    with _lock:
        users = dict(_load())
        if uid not in users:
            raise UserError(t("Utente non trovato."))
        info = users.pop(uid)
        _save(users)
    default = users_root() / uid
    custom = info.get("data_dir")
    notes = []
    if delete_data:
        if default.is_dir():
            shutil.rmtree(default, ignore_errors=True)
            notes.append(t("cartella dei dati cancellata"))
        if custom and Path(custom) != default:
            notes.append(t("il suo database spostato in {path} non è stato toccato", path=custom))
    else:
        notes.append(t("i dati restano in {path}", path=Path(custom) if custom else default))
    return t("Utente «{name}» eliminato: ", name=info.get("name", uid)) + "; ".join(notes) + "."


# ---------------------------------------------------------------- cartelle
def default_dir(uid: str) -> Path:
    return users_root() / re.sub(r"[^a-z0-9_-]", "", uid.lower())


def data_dir(uid: str) -> Path:
    u = get(uid)
    custom = (u or {}).get("data_dir")
    return Path(custom) if custom else default_dir(uid)


def set_data_dir(uid: str, path: Path | None) -> None:
    with _lock:
        users = dict(_load())
        if uid not in users:
            raise UserError(t("Utente non trovato."))
        val = None if path is None or _same(path, default_dir(uid)) else str(path)
        users[uid] = dict(users[uid], data_dir=val)
        _save(users)


def _norm(p: Path | str) -> Path:
    p = Path(str(p).strip().strip('"')).expanduser()
    try:
        p = p.resolve()
    except OSError:
        p = p.absolute()
    return Path(os.path.normcase(str(p)))


def _same(a: Path | str, b: Path | str) -> bool:
    return _norm(a) == _norm(b)


def _inside(p: Path, d: Path) -> bool:
    """p è d oppure una sua sottocartella."""
    return p == d or d in p.parents


def admin_data_dir() -> Path:
    custom = os.environ.get("APP_SPESE_DATA")
    if custom:
        return Path(custom)
    return db.configured_data_dir() or db.DEFAULT_DATA_DIR


def _settings_dirs(data: Path) -> list[Path]:
    """Cartelle degli estratti e dei backup salvate nel database di quella cartella (lettura sola)."""
    f = data / "spese.db"
    if not f.is_file():
        return []
    out = []
    try:
        with closing(sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True, timeout=5)) as con:
            for (v,) in con.execute("SELECT value FROM settings WHERE key IN ('import_dir','backup_dir')"):
                if v and str(v).strip():
                    out.append(Path(str(v).strip()))
    except sqlite3.Error:
        pass
    return out


def owned_dirs(uid: str) -> list[Path]:
    """Cartelle di un utente: database, estratti, backup (quelle predefinite stanno dentro la cartella dati)."""
    d = admin_data_dir() if uid == ADMIN else data_dir(uid)
    return [d] + _settings_dirs(d)


def folder_conflict(uid: str, path: Path | str) -> str | None:
    """Motivo per cui l'utente `uid` non può usare questa cartella (None = va bene).
    Vietate: le cartelle (e sottocartelle) di database, estratti e backup degli altri utenti e le cartelle
    riservate dell'app; ciascuno può usare liberamente la propria cartella predefinita."""
    p = _norm(path)
    root = _norm(db.root_data_dir())
    uroot = _norm(users_root())
    own_default = _norm(admin_data_dir() if uid == ADMIN else default_dir(uid))
    if uid != ADMIN and _inside(p, own_default):
        pass  # la propria cartella predefinita (e le sue sottocartelle) è sempre permessa
    elif _inside(p, uroot):
        return t("è una cartella riservata agli altri utenti dell'app")
    elif uid != ADMIN and _inside(p, root):
        return t("è una cartella riservata dell'app (dati dell'amministratore e degli utenti)")
    others = [ADMIN] + list(all_users())
    for o in others:
        if o == uid:
            continue
        for d in owned_dirs(o):
            nd = _norm(d)
            if uid != ADMIN and o == ADMIN and _inside(own_default, nd) and _inside(p, own_default):
                continue  # la cartella dell'Admin contiene quelle degli utenti: la propria resta permessa
            if _inside(p, nd):
                return t("contiene i dati di un altro utente")
    return None


def db_count(uid: str) -> int | None:
    """Numero di movimenti nel database dell'utente (lettura sola), None se non ancora creato."""
    f = data_dir(uid) / "spese.db"
    if not f.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True, timeout=5)) as con:
            return int(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    except sqlite3.Error:
        return None
