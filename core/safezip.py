"""Controllo dei file compressi caricati (Excel .xlsx, archivi .zip) prima di aprirli.

Un file .xlsx è un archivio zip. Un archivio costruito apposta può pesare pochi KB e diventare decine di GB una
volta aperto, bloccando l'app (e il computer) per mancanza di memoria. Qui si legge solo l'indice dell'archivio
(dimensioni dichiarate dei file contenuti, che zipfile non lascia superare in lettura) e lo si rifiuta se è
esagerato per un estratto conto.
"""
from __future__ import annotations

import io
import zipfile

MAX_UNZIPPED = 150 * 1024 * 1024    # un estratto conto vero, aperto, sta in pochi MB
MAX_MEMBERS = 5000


class ArchiveTooBig(ValueError):
    """Archivio troppo grande una volta aperto: il messaggio si mostra così com'è."""


def check(data: bytes) -> None:
    """Solleva ArchiveTooBig se `data` è un archivio zip (anche .xlsx) che aperto supera i limiti.
    Per i file che non sono archivi non fa niente."""
    if not data or data[:4] != b"PK\x03\x04":
        return
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
    except zipfile.BadZipFile:
        return  # non è un archivio valido: ci penserà chi lo legge a segnalarlo
    total = sum(max(0, i.file_size) for i in infos)
    if len(infos) > MAX_MEMBERS or total > MAX_UNZIPPED:
        from core.i18n import t
        raise ArchiveTooBig(t("Il file è troppo grande una volta aperto ({mb} MB): non sembra un estratto conto e "
                              "non viene letto.", mb=f"{total / 1_048_576:,.0f}"))
