"""Accesso all'app con nome utente e password.

- L'amministratore (il proprietario) si crea alla prima apertura dell'app scegliendo nome e password; i suoi dati
  stanno nella cartella normale. Crea, rinomina ed elimina gli altri utenti e ne cambia la password
  (menu dell'avatar → Utenti), e lì cambia anche il proprio nome e la propria password.
- Gli altri utenti stanno nell'elenco di core/users.py: ognuno ha i suoi dati in una cartella separata e non vede
  né tocca mai quelli degli altri. Un utente «di prova» parte con dati fittizi.
Nei file non ci sono password in chiaro: solo la loro impronta PBKDF2-SHA256 (300.000 iterazioni,
sale casuale per utente). Il confronto è a tempo costante. Dopo 5 tentativi sbagliati in un minuto l'accesso si
blocca per 60 s.

«Resta connesso»: cookie firmato (HMAC con un segreto casuale salvato in un file della cartella base) valido
30 giorni: contiene utente, scadenza e firma, mai la password. Se la password di un utente cambia, i suoi cookie
smettono di valere (e le sue sessioni aperte si chiudono).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from core import db, users

# record fittizio (sale e impronta casuali, nessuna password li soddisfa): serve solo a far durare la verifica
# lo stesso tempo anche quando il nome utente non esiste
_DUMMY = ("", secrets.token_hex(16), secrets.token_hex(32))

MAX_FAILURES = 5          # tentativi sbagliati...
WINDOW = 60               # ...in questi secondi
LOCK_SECONDS = 60         # bloccano l'accesso per questo tempo
COOKIE_NAME = "appspese_sessione"
REMEMBER_DAYS = 30
_SECRET_FILE = ".auth_secret"

_lock = threading.Lock()
# tentativi sbagliati e blocchi tenuti per nome utente: chi sbaglia apposta blocca solo quel nome,
# non l'accesso di tutti gli altri
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def _hash(password: str, salt_hex: str) -> str:
    return users.hash_password(password, salt_hex)


def _record(user: str | None) -> tuple[str, str, str] | None:
    """(nome mostrato, sale, impronta) dell'utente, None se non esiste."""
    if user == users.ADMIN:
        try:
            info = users.admin_info()
        except RuntimeError:
            return None
        return (info["name"], info["salt"], info["hash"]) if info else None
    u = users.get(user)
    return (u["name"], u["salt"], u["hash"]) if u else None


def check(username: str, password: str) -> str | None:
    """Id dell'utente se nome utente (senza distinzione maiuscole/minuscole) e password (esatta) sono corretti,
    altrimenti None. La password viene sempre verificata (stesso tempo per utenti esistenti e non)."""
    name = (username or "").strip()
    admin = users.admin_name()
    uid = users.ADMIN if (admin and name.casefold() == admin.casefold()) else users.find_by_name(name)
    rec = _record(uid)
    _name, salt, expected = rec or _DUMMY
    ok_pwd = hmac.compare_digest(_hash(password or "", salt), expected)
    return uid if (rec is not None and ok_pwd) else None


def exists(user: str | None) -> bool:
    return _record(user) is not None


def version(user: str | None) -> str:
    """Impronta corta della password attuale: se cambia, le sessioni aperte di quell'utente si chiudono."""
    rec = _record(user)
    return hashlib.sha256(rec[2].encode()).hexdigest()[:16] if rec else ""


def display_name(user: str | None) -> str:
    rec = _record(user)
    return rec[0] if rec else ""


def needs_setup() -> bool:
    """True alla prima apertura: l'amministratore non è ancora stato creato."""
    return not users.admin_exists()


def is_demo(user: str | None) -> bool:
    return users.is_demo(user)


# ---------------------------------------------------------------- protezione dai tentativi ripetuti
def _key(username: str | None) -> str:
    return " ".join((username or "").split()).casefold()[:64]


def _prune(now: float) -> None:
    """Toglie i conteggi scaduti (la memoria non cresce con nomi utente inventati)."""
    for k in [k for k, v in _failures.items() if not v or now - v[-1] >= WINDOW]:
        _failures.pop(k, None)
    for k in [k for k, v in _locked_until.items() if v <= now]:
        _locked_until.pop(k, None)


def locked_for(username: str | None) -> int:
    """Secondi che mancano allo sblocco di questo nome utente (0 = si può provare)."""
    with _lock:
        return max(0, int(round(_locked_until.get(_key(username), 0.0) - time.time())))


def register_failure(username: str | None) -> int:
    """Registra un tentativo sbagliato per quel nome utente. Ritorna quanti tentativi restano prima del blocco."""
    now = time.time()
    k = _key(username)
    with _lock:
        _prune(now)
        tries = [x for x in _failures.get(k, []) if now - x < WINDOW] + [now]
        if len(tries) >= MAX_FAILURES:
            _locked_until[k] = now + LOCK_SECONDS
            _failures.pop(k, None)
            return 0
        _failures[k] = tries
        return MAX_FAILURES - len(tries)


def register_success(username: str | None) -> None:
    with _lock:
        _failures.pop(_key(username), None)


# ---------------------------------------------------------------- «resta connesso»
def _secret() -> bytes:
    f = db.root_data_dir() / _SECRET_FILE
    try:
        s = f.read_text(encoding="utf-8").strip()
    except OSError:
        s = ""
    if len(s) < 64:
        s = secrets.token_hex(32)
        f.write_text(s, encoding="utf-8")
    return bytes.fromhex(s)


def _sign(user: str, exp: int) -> str:
    rec = _record(user)
    msg = f"{user}|{exp}|{rec[2] if rec else ''}".encode()
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def make_token(user: str, days: int = REMEMBER_DAYS) -> str:
    exp = int(time.time()) + days * 86400
    return f"{user}.{exp}.{_sign(user, exp)}"


def token_user(token: str | None) -> str | None:
    """Utente del cookie se valido e non scaduto, altrimenti None."""
    if not token or token.count(".") != 2:
        return None
    user, exp_s, sig = token.split(".")
    if not exists(user) or not exp_s.isdigit() or int(exp_s) < time.time():
        return None
    return user if hmac.compare_digest(sig, _sign(user, int(exp_s))) else None


def forget_all_devices() -> None:
    """Cambia il segreto: tutti i «resta connesso» già dati smettono di valere."""
    (db.root_data_dir() / _SECRET_FILE).write_text(secrets.token_hex(32), encoding="utf-8")
