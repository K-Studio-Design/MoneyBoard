"""Cifratura delle password salvate dall'app (password della posta, chiavi API degli exchange).

Nel database (e quindi nei backup, che spesso finiscono su OneDrive) queste password stanno cifrate: la chiave è
un file a parte nella cartella base dei dati (``.chiave_segreti``), che non va nei backup. Chi trova un backup
non legge le password.

Se il database viene aperto su un altro computer (o la chiave viene cancellata) le password cifrate non si possono
più leggere: l'app le considera mancanti e le chiede di nuovo. I valori salvati dalle versioni precedenti (in
chiaro) si leggono ancora e vengono cifrati al primo salvataggio.
"""
from __future__ import annotations

import os
import threading

from core import db

PREFIX = "enc1:"
KEY_FILE = ".chiave_segreti"
_lock = threading.Lock()


def _key_path():
    return db.root_data_dir() / KEY_FILE


def _fernet(create: bool):
    from cryptography.fernet import Fernet
    f = _key_path()
    with _lock:
        try:
            key = f.read_bytes().strip()
        except FileNotFoundError:
            key = b""
        if not key:
            if not create:
                return None
            key = Fernet.generate_key()
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(key)
    try:
        return Fernet(key)
    except ValueError:
        return None


def is_sealed(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def seal(text: str | None) -> str:
    """Testo cifrato da salvare (stringa vuota resta vuota)."""
    text = text or ""
    if not text or is_sealed(text):
        return text
    f = _fernet(create=True)
    if f is None:   # chiave rovinata: meglio non salvare che salvare in chiaro
        raise RuntimeError("chiave per cifrare le password non utilizzabile")
    return PREFIX + f.encrypt(text.encode("utf-8")).decode("ascii")


def unseal(value: str | None) -> str:
    """Testo in chiaro. Un valore vecchio non cifrato si restituisce così com'è; uno cifrato che non si riesce a
    leggere (altro computer, chiave persa) diventa stringa vuota."""
    value = value or ""
    if not is_sealed(value):
        return value
    from cryptography.fernet import InvalidToken
    f = _fernet(create=False)
    if f is None:
        return ""
    try:
        return f.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        return ""
