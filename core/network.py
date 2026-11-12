"""Accesso all'app da altri dispositivi della rete (telefono, tablet, altri PC).

Di base l'app si apre solo dal computer su cui gira: avvia_app.bat / avvia_app.sh la avviano con
``--server.address localhost``. Se l'amministratore attiva l'accesso dalla rete, nella cartella base dei dati
compare il file ``accesso_rete.on``: al prossimo avvio gli script la aprono a tutta la rete di casa
(``--server.address 0.0.0.0``). La scelta vale dal riavvio successivo, perché l'indirizzo su cui l'app ascolta
si decide all'avvio.
"""
from __future__ import annotations

import socket

from core import db

FLAG_FILE = "accesso_rete.on"


def _flag():
    return db.root_data_dir() / FLAG_FILE


def lan_enabled() -> bool:
    """True se l'amministratore ha scelto di aprire l'app agli altri dispositivi della rete."""
    try:
        return _flag().is_file()
    except OSError:
        return False


def set_lan(enabled: bool) -> None:
    f = _flag()
    if enabled:
        f.write_text("Accesso a MoneyBoard dagli altri dispositivi della rete: attivo dal prossimo avvio.\n"
                     "Cancella questo file (o spegni l'opzione nell'app) per tornare al solo accesso da questo PC.\n",
                     encoding="utf-8")
    else:
        f.unlink(missing_ok=True)


def listening_on_network() -> bool:
    """True se l'app in questo momento accetta collegamenti anche dagli altri dispositivi."""
    try:
        import streamlit as st
        addr = (st.get_option("server.address") or "").strip().lower()
    except Exception:
        return False
    return addr not in ("localhost", "127.0.0.1", "::1")


def port() -> int:
    try:
        import streamlit as st
        return int(st.get_option("server.port") or 8501)
    except Exception:
        return 8501


def local_ip() -> str | None:
    """Indirizzo di questo computer nella rete di casa (per aprire l'app dal telefono). Non manda dati: serve solo
    a chiedere al sistema quale scheda di rete userebbe."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.2)
        s.connect(("192.0.2.1", 9))   # indirizzo di documentazione: nessun pacchetto parte davvero
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()
