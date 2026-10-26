"""Import automatico degli estratti messi nella cartella «Estratti da importare».

All'avvio (e poi al massimo ogni 30 secondi mentre l'app è aperta) si guardano i file nella cartella:
- si riconosce la banca dal contenuto (Fineco, Revolut consolidato o CSV, Chase CSV/QFX/OFX);
- si importano i movimenti saltando quelli già presenti (stesso meccanismo anti-doppioni dell'import a mano);
- il file viene spostato in «Importati/AAAA-MM», oppure in «Non riconosciuti» se non è un formato noto.
Un file aperto in Excel (bloccato) resta dov'è e viene riprovato la volta dopo.
"""
from __future__ import annotations

import io
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from core import chase, db, importers, storage

SUPPORTED = (".xlsx", ".xlsm", ".xls", ".csv", ".qfx", ".ofx")
DONE_DIR, UNKNOWN_DIR = "Importati", "Non riconosciuti"
LOG_KEY = "autoimport_log"
ACCOUNTS = {"fineco": "Fineco", "revolut": "Revolut", "chase_checking": "Chase", "chase_card": "Chase carta"}
_last_scan = 0.0


def pending_files(folder: Path | None = None) -> list[Path]:
    folder = folder or storage.import_dir()
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.name.startswith(("~$", ".")) or p.suffix.lower() not in SUPPORTED:
            continue
        out.append(p)
    return out


def detect(file_bytes: bytes, filename: str) -> str | None:
    """'fineco', 'revolut', 'chase_checking', 'chase_card', 'portafoglio' (posizioni titoli) oppure None."""
    kind = chase.detect(file_bytes, filename)
    if kind == "checking":
        return "chase_checking"
    if kind == "card":
        return "chase_card"
    if kind == "ofx":
        _rows, _ccy, acc_kind = chase.parse_ofx(file_bytes)
        return "chase_card" if acc_kind == "card" else "chase_checking"
    low = filename.lower()
    if low.endswith((".xlsx", ".xlsm")):
        from core import revolut_consolidated as rc
        try:
            raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl", nrows=60)
            if rc.is_consolidated(raw):
                return "revolut"
        except Exception:
            pass
    try:
        if len(importers.parse_fineco(file_bytes, filename)) > 0:
            return "fineco"
    except Exception:
        pass
    if low.endswith(".csv"):
        try:
            if len(importers.parse_revolut(file_bytes, filename)) > 0:
                return "revolut"
        except Exception:
            pass
    try:
        from core import positions
        if len(positions.parse(file_bytes, filename)) > 0:
            return "portafoglio"
    except Exception:
        pass
    return None


def rows_for(bank: str, file_bytes: bytes, filename: str) -> list[dict]:
    if bank == "fineco":
        df = importers.parse_fineco(file_bytes, filename)
        owner = df.attrs.get("owner")
        if owner:
            db.add_owner_name(owner)
        return importers.fineco_rows(df)
    if bank == "revolut":
        kind, df = importers.parse_revolut_any(file_bytes, filename)
        return (importers.revolut_consolidated_rows(df, ACCOUNTS["revolut"]) if kind == "consolidato"
                else importers.revolut_rows(df, ACCOUNTS["revolut"]))
    _kind, rows = chase.parse(file_bytes, filename)
    return rows


def _move(p: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / p.name
    n = 2
    while dst.exists():
        dst = dest_dir / f"{p.stem} ({n}){p.suffix}"
        n += 1
    shutil.move(str(p), str(dst))
    return dst


def _say(res: dict, key: str, append: bool = False, **args) -> None:
    """Messaggio dell'esito: si salva il testo italiano (chiave) con i valori, così nel registro si mostra sempre
    nella lingua in uso (vedi message_text)."""
    args = {k: str(v) for k, v in args.items()}
    parts = (res.get("msg") or []) if append else []
    res["msg"] = parts + [[key, args]]
    res["message"] = "".join(k.format(**a) for k, a in res["msg"])


def message_text(r: dict) -> str:
    """Messaggio di un risultato di import nella lingua attuale."""
    from core.i18n import t
    parts = r.get("msg")
    if isinstance(parts, list) and parts:
        try:
            return "".join(t(k, **a) if a else t(k) for k, a in parts)
        except (KeyError, ValueError, TypeError):
            pass
    return str(r.get("message") or "")


def process_file(p: Path, folder: Path) -> dict:
    res = {"file": p.name, "when": datetime.now().isoformat(timespec="seconds"), "bank": "", "account": "",
           "inserted": 0, "skipped": 0, "status": "ok", "message": ""}
    try:
        data = p.read_bytes()
    except PermissionError:
        res.update(status="in uso")
        _say(res, "file aperto in un altro programma: riprovo più tardi")
        return res
    except OSError as e:
        res.update(status="errore")
        _say(res, "{err}", err=e)
        return res
    bank = detect(data, p.name)
    if not bank:
        res.update(status="sconosciuto")
        _say(res, "formato non riconosciuto, spostato in «{folder}»", folder=UNKNOWN_DIR)
        try:
            _move(p, folder / UNKNOWN_DIR)
        except OSError as e:
            _say(res, " (spostamento non riuscito: {err})", append=True, err=e)
        return res
    if bank == "portafoglio":
        from core import positions
        res.update(bank="Portafoglio titoli", account="Investimenti")
        try:
            counts = positions.apply(positions.parse(data, p.name))
            res.update(inserted=counts["nuovo"] + counts["allinea"], skipped=counts["ok"])
            _say(res, "{n} titoli nuovi, {m} quantità allineate", n=counts["nuovo"], m=counts["allinea"])
            if counts["senza prezzo"]:
                _say(res, ", {n} senza prezzo medio", append=True, n=counts["senza prezzo"])
        except Exception as e:
            res.update(status="errore")
            _say(res, "lettura non riuscita: {err}", err=e)
            return res
        try:
            _move(p, folder / DONE_DIR / datetime.now().strftime("%Y-%m"))
        except OSError:
            pass
        return res
    account = ACCOUNTS[bank]
    res.update(bank=bank.split("_")[0].capitalize(), account=account)
    try:
        rows = rows_for(bank, data, p.name)
        if rows:
            source = {"fineco": "fineco", "revolut": "revolut"}.get(bank, "chase")
            final = importers.finalize(rows, account, source)
            ins, skip = db.insert_transactions(final)
            res.update(inserted=ins, skipped=skip)
        else:
            _say(res, "nessun movimento nel file")
    except Exception as e:  # file rovinato o formato cambiato: lo si lascia lì e si segnala
        res.update(status="errore")
        _say(res, "lettura non riuscita: {err}", err=e)
        return res
    try:
        dst = _move(p, folder / DONE_DIR / datetime.now().strftime("%Y-%m"))
        if not res["message"]:
            _say(res, "spostato in «{folder}»", folder=f"{DONE_DIR}/{dst.parent.name}")
    except OSError as e:
        _say(res, "importato, ma non sono riuscito a spostarlo ({err}): i doppioni vengono comunque saltati", err=e)
    return res


def run(force: bool = False, min_interval: float = 30.0) -> list[dict]:
    """Importa i file presenti. Senza force non fa nulla se l'ultimo controllo è di meno di min_interval secondi
    fa o se l'import automatico è disattivato. Ritorna i risultati di questo giro (vuoto se niente da fare)."""
    global _last_scan
    if not force:
        if not storage.import_auto() or time.monotonic() - _last_scan < min_interval:
            return []
    _last_scan = time.monotonic()
    folder = storage.import_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    results = [process_file(p, folder) for p in pending_files(folder)]
    if results:
        log = load_log()
        db.set_setting(LOG_KEY, json.dumps((results + log)[:50], ensure_ascii=False))
    return results


def load_log() -> list[dict]:
    try:
        v = json.loads(db.get_setting(LOG_KEY, "[]") or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []
