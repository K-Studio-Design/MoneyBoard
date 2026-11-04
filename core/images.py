"""Immagini scelte dall'utente (foto di un obiettivo, aspetto di una carta), salvate nel database.

Stanno nel database (tabella `images`), così finiscono nei backup e ogni utente ha le sue. Prima di salvarle si
ridimensionano: una foto del telefono da qualche MB diventa poche centinaia di KB.
"""
from __future__ import annotations

import base64
import io

from core import db
from core.i18n import t

MAX_UPLOAD = 15 * 1024 * 1024      # file più grandi: rifiutati
CARD_SIZE = (856, 540)             # formato carta di credito (85,6 × 54 mm)
PHOTO_MAX = 1400                   # lato lungo massimo delle foto degli obiettivi
FORMATS = ["png", "jpg", "jpeg", "webp"]


class ImageError(ValueError):
    """Immagine non valida: il messaggio si mostra così com'è."""


def _open(data: bytes):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not data:
        raise ImageError(t("Il file è vuoto."))
    if len(data) > MAX_UPLOAD:
        raise ImageError(t("L'immagine è troppo grande (al massimo 15 MB)."))
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageError(t("Non riesco a leggere l'immagine: usa un file PNG, JPG o WEBP.")) from None
    return ImageOps.exif_transpose(im)  # le foto del telefono hanno l'orientamento nei metadati


def _crop_to(im, ratio: float):
    """Ritaglio centrale con il rapporto larghezza/altezza indicato."""
    w, h = im.size
    if w / h > ratio:
        nw = int(round(h * ratio))
        left = (w - nw) // 2
        return im.crop((left, 0, left + nw, h))
    nh = int(round(w / ratio))
    top = (h - nh) // 2
    return im.crop((0, top, w, top + nh))


def _encode(im) -> tuple[str, bytes]:
    out = io.BytesIO()
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        im.convert("RGBA").save(out, "PNG", optimize=True)
        return "image/png", out.getvalue()
    im.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return "image/jpeg", out.getvalue()


def prepare(data: bytes, kind: str) -> tuple[str, bytes]:
    """kind 'card': ritagliata e ridimensionata nel formato carta; 'photo': lato lungo al massimo PHOTO_MAX."""
    from PIL import Image
    im = _open(data)
    if kind == "card":
        im = _crop_to(im, CARD_SIZE[0] / CARD_SIZE[1]).resize(CARD_SIZE, Image.LANCZOS)
    else:
        im.thumbnail((PHOTO_MAX, PHOTO_MAX), Image.LANCZOS)
    return _encode(im)


def save(key: str, data: bytes, kind: str) -> None:
    mime, blob = prepare(data, kind)
    with db.connect() as con:
        con.execute("""INSERT INTO images(key, mime, data, updated) VALUES (?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET mime=excluded.mime, data=excluded.data,
                       updated=excluded.updated""", (key, mime, blob, db.now_str()))


def delete(key: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM images WHERE key=?", (key,))


def exists(key: str) -> bool:
    with db.connect() as con:
        return con.execute("SELECT 1 FROM images WHERE key=?", (key,)).fetchone() is not None


def data_url(key: str) -> str | None:
    """L'immagine come indirizzo «data:» da usare direttamente nella pagina, oppure None."""
    with db.connect() as con:
        r = con.execute("SELECT mime, data FROM images WHERE key=?", (key,)).fetchone()
    if r is None or not r["data"]:
        return None
    return f"data:{r['mime']};base64,{base64.b64encode(r['data']).decode('ascii')}"
