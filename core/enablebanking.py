"""Collegamento automatico ai conti (Fineco, Revolut e altre banche europee) tramite
Enable Banking, un aggregatore PSD2/Open Banking autorizzato.

Per uso personale si registra gratuitamente un'applicazione in modalità "restricted"
su https://enablebanking.com (Control Panel) e si collegano i PROPRI conti.
Servono: Application ID + file della chiave privata (.pem) scaricato alla creazione.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests

from core import db, i18n

API = "https://api.enablebanking.com"
TIMEOUT = 40


class EBError(Exception):
    pass


class RateLimited(EBError):
    """La banca ha rifiutato perché il conto è già stato letto troppe volte oggi (PSD2: di norma 4 accessi al
    giorno per conto quando la lettura non è chiesta dall'utente in quel momento)."""


def key_path() -> Path:
    return db.get_data_dir() / "enablebanking_private.pem"


def save_private_key(content: bytes) -> None:
    if b"PRIVATE KEY" not in content:
        raise EBError(i18n.t("Il file non sembra una chiave privata PEM."))
    key_path().write_bytes(content)


def is_configured() -> bool:
    return bool(db.get_setting("eb_app_id")) and key_path().exists()


def _token() -> str:
    import jwt  # PyJWT

    app_id = db.get_setting("eb_app_id")
    if not app_id or not key_path().exists():
        raise EBError(i18n.t("Configura prima Application ID e chiave privata."))
    now = int(time.time())
    payload = {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, key_path().read_bytes(), algorithm="RS256", headers={"kid": app_id, "typ": "JWT"})


def _req(method: str, path: str, **kw) -> dict:
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    r = requests.request(method, API + path, headers=headers, timeout=TIMEOUT, **kw)
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:400]
        if r.status_code == 429 or "RATE_LIMIT" in str(detail).upper():
            raise RateLimited(f"HTTP {r.status_code}: {detail}")
        raise EBError(f"HTTP {r.status_code}: {detail}")
    return r.json() if r.text else {}


def list_aspsps(country: str) -> list[dict]:
    data = _req("GET", "/aspsps", params={"country": country, "psu_type": "personal"})
    return sorted(data.get("aspsps", []), key=lambda a: a.get("name", "").lower())


def start_auth(aspsp_name: str, country: str, days: int = 90, max_seconds: int | None = None) -> str:
    """Ritorna l'URL della banca su cui autenticarsi."""
    seconds = days * 86400
    if max_seconds:
        seconds = min(seconds, int(max_seconds))
    valid_until = (datetime.now(timezone.utc) + timedelta(seconds=seconds - 60)).isoformat()
    body = {
        "access": {"valid_until": valid_until},
        "aspsp": {"name": aspsp_name, "country": country},
        "state": str(uuid.uuid4()),
        "redirect_url": db.get_setting("eb_redirect_url"),
        "psu_type": "personal",
        "language": "it",
    }
    return _req("POST", "/auth", json=body)["url"]


def extract_code(pasted: str) -> str:
    pasted = (pasted or "").strip()
    if not pasted:
        raise EBError(i18n.t("Incolla l'indirizzo (URL) di ritorno o il codice."))
    if "://" in pasted or pasted.startswith(("?", "/")):
        qs = parse_qs(urlparse(pasted).query)
        if "error" in qs:
            raise EBError(i18n.t("La banca ha restituito un errore: {err} {desc}", err=qs.get("error"),
                                 desc=qs.get("error_description", "")))
        if "code" not in qs:
            raise EBError(i18n.t("Nell'URL non c'è il parametro 'code'."))
        return qs["code"][0]
    return pasted


def default_label(aspsp_name: str) -> str:
    """Nome del conto nell'app per una banca appena collegata: se esiste già un conto con quel nome (es. «Fineco»
    per «FinecoBank», creato importando gli estratti) si usa quello, così i movimenti finiscono nello stesso conto."""
    low = (aspsp_name or "").lower().replace(" ", "")
    for acc in db.accounts_list():
        a = acc.lower().replace(" ", "")
        if a and (a in low or low in a):
            return acc
    return aspsp_name


def create_session(code: str, aspsp_name: str, country: str) -> list[dict]:
    data = _req("POST", "/sessions", json={"code": code})
    session_id = data.get("session_id")
    valid_until = (data.get("access") or {}).get("valid_until", "")
    label = default_label(aspsp_name)
    saved = []
    with db.connect() as con:
        for acc in data.get("accounts", []):
            uid = acc.get("uid")
            if not uid:
                continue
            iban = (acc.get("account_id") or {}).get("iban", "")
            name = acc.get("name") or acc.get("product") or iban or uid[:8]
            con.execute(
                """INSERT INTO bank_accounts(uid, session_id, aspsp_name, aspsp_country, account_name, iban, currency,
                                             valid_until, label, cash_account_type, product)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(uid) DO UPDATE SET session_id=excluded.session_id, valid_until=excluded.valid_until,
                       cash_account_type=excluded.cash_account_type, product=excluded.product""",
                (uid, session_id, aspsp_name, country, name, iban, acc.get("currency", ""), valid_until, label,
                 acc.get("cash_account_type") or "", acc.get("product") or ""),
            )
            saved.append({"uid": uid, "name": name, "iban": iban})
    return saved


def accounts_df() -> pd.DataFrame:
    with db.connect() as con:
        return pd.read_sql_query("SELECT * FROM bank_accounts ORDER BY aspsp_name, account_name", con)


def set_label(uid: str, label: str) -> int:
    """Cambia il conto dell'app in cui vanno i movimenti di questo collegamento e sposta lì anche quelli già
    scaricati. Ritorna quanti movimenti sono stati spostati."""
    with db.connect() as con:
        return relabel(con, uid, label)


def relabel(con, uid: str, label: str) -> int:
    """Come set_label, su una connessione già aperta (serve anche all'anteprima, che poi annulla tutto)."""
    label = (label or "").strip()
    if not label:
        return 0
    acc = con.execute("SELECT * FROM bank_accounts WHERE uid=?", (uid,)).fetchone()
    if acc is None:
        return 0
    old = acc["label"] or acc["aspsp_name"]
    con.execute("UPDATE bank_accounts SET label=? WHERE uid=?", (label, uid))
    if old == label:
        return 0
    src = f"openbanking:{acc['aspsp_name']}"
    # movimenti di questo collegamento: quelli segnati con il suo uid e, per i più vecchi (scaricati prima che
    # l'uid venisse salvato), quelli con lo stesso conto, fonte e valuta
    cur = con.execute(
        """UPDATE transactions SET account=? WHERE account=? AND source=?
             AND (bank_uid=? OR (bank_uid IS NULL AND currency=?))""",
        (label, old, src, uid, (acc["currency"] or "").upper()))
    con.execute("""UPDATE cards SET account=? WHERE account=? AND NOT EXISTS
                     (SELECT 1 FROM cards c2 WHERE c2.account=? AND c2.digits=cards.digits)""", (label, old, label))
    con.execute("DELETE FROM cards WHERE account=? AND digits IN (SELECT digits FROM cards WHERE account=?)",
                (old, label))
    return cur.rowcount


def remove_account(uid: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM bank_accounts WHERE uid=?", (uid,))


def fetch_transactions(uid: str, date_from: date, date_to: date | None = None) -> list[dict]:
    params = {"date_from": date_from.isoformat()}
    if date_to:
        params["date_to"] = date_to.isoformat()
    out, guard = [], 0
    while True:
        data = _req("GET", f"/accounts/{uid}/transactions", params=params)
        out.extend(data.get("transactions", []))
        ck = data.get("continuation_key")
        guard += 1
        if not ck or guard > 200:
            break
        params["continuation_key"] = ck
    return out


_RE_OPDATE = re.compile(r"(?:data operazione:?|pag\. del)\s*(\d{1,2})/(\d{1,2})/(\d{2,4})", re.I)


def op_date(text: str, booked: date) -> date | None:
    """Data reale dell'operazione scritta nella descrizione («Data operazione 05/03/26»), se plausibile."""
    m = _RE_OPDATE.search(text or "")
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    y = y + 2000 if y < 100 else y
    try:
        op = date(y, mth, d)
    except ValueError:
        return None
    return op if timedelta(0) <= booked - op <= timedelta(days=15) else None


def to_rows(txs: list[dict], account_label: str, include_pending: bool = False, uid: str = "",
            legacy_labels: tuple[str, ...] = ()) -> list[dict]:
    """Movimenti della banca → righe dell'app. Importi a zero (preautorizzazioni, verifiche della carta) esclusi;
    la data è quella dell'operazione quando la banca la indica; la carta usata finisce nella colonna `card`."""
    from core import cards

    rows = []
    seen: dict[str, int] = {}
    for t in txs:
        status = (t.get("status") or "BOOK").upper()
        if status != "BOOK" and not include_pending:
            continue
        amt = t.get("transaction_amount") or {}
        try:
            value = abs(float(amt.get("amount")))
        except (TypeError, ValueError):
            continue
        if value < 0.005:
            continue
        debit = (t.get("credit_debit_indicator") or "").upper() == "DBIT"
        amount = -value if debit else value
        d = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
        if not d:
            continue
        party = (t.get("creditor") if debit else t.get("debtor")) or {}
        remit = " ".join(x for x in (t.get("remittance_information") or []) if x)
        raw_desc = " - ".join(x for x in [party.get("name", ""), remit, t.get("note") or ""] if x).strip()
        try:
            booked = date.fromisoformat(str(d)[:10])
        except ValueError:
            continue
        real = None
        if t.get("transaction_date"):
            try:
                real = date.fromisoformat(str(t["transaction_date"])[:10])
            except ValueError:
                real = None
        real = real or op_date(raw_desc, booked) or booked
        digits, kind = cards.detect(raw_desc)
        desc = (cards.strip_card(raw_desc) if digits else raw_desc) or "Movimento"
        ref = t.get("entry_reference") or t.get("transaction_id")
        row = {
            "date": real.isoformat(),
            "description": desc,
            "amount": amount,
            "currency": (amt.get("currency") or "EUR").upper(),
            "_bank_category": "",
            "_counterparty": party.get("name") or None,
            "bank_uid": uid or None,
            "card": digits,
            "_card_kind": kind,
        }
        if ref:
            row["external_id"] = db.make_external_id("eb", uid or account_label, ref)
            row["_legacy_ids"] = [db.make_external_id("eb", lab, ref) for lab in legacy_labels if lab]
        else:
            key = f"{booked}|{amount:.2f}|{row['currency']}|{raw_desc}"
            n = seen.get(key, 0)
            seen[key] = n + 1
            row["external_id"] = db.make_external_id("eb", uid or account_label, key, n)
        rows.append(row)
    return rows


def _use_legacy_ids(rows: list[dict]) -> None:
    """Movimenti già scaricati con la versione precedente (id costruito con il nome del conto): si riusa quell'id,
    così non vengono reinseriti."""
    with db.connect() as con:
        for r in rows:
            for old in r.pop("_legacy_ids", []) or []:
                if con.execute("SELECT 1 FROM transactions WHERE external_id=? UNION ALL "
                               "SELECT 1 FROM tx_links WHERE external_id=?", (old, old)).fetchone():
                    r["external_id"] = old
                    break


BALANCE_ORDER = ["ITAV", "ITBD", "CLAV", "CLBD", "XPCD", "OPAV", "OPBD", "PRCD", "INFO", "VALU", "FWAV", "OTHR"]


def fetch_details_and_balance(uid: str) -> dict:
    """Tipo di conto (es. CARD = carta, CACC = conto corrente), prodotto e saldo attuale dalla banca."""
    out: dict = {}
    try:
        det = _req("GET", f"/accounts/{uid}/details")
        out["cash_account_type"] = det.get("cash_account_type") or ""
        out["product"] = det.get("product") or ""
    except Exception:
        pass
    try:
        bal = _req("GET", f"/accounts/{uid}/balances").get("balances", [])
    except Exception:
        bal = []
    if bal:
        def rank(b):
            bt = (b.get("balance_type") or "").upper()
            return BALANCE_ORDER.index(bt) if bt in BALANCE_ORDER else len(BALANCE_ORDER)
        best = sorted(bal, key=rank)[0]
        amt = best.get("balance_amount") or {}
        try:
            out["balance"] = float(amt.get("amount"))
            out["balance_currency"] = (amt.get("currency") or "").upper()
            out["balance_type"] = (best.get("balance_type") or "").upper()
            out["balance_date"] = (best.get("reference_date") or best.get("last_change_date_time") or
                                   db.now_str())[:19]
        except (TypeError, ValueError):
            pass
        import json
        out["balances_json"] = json.dumps(bal, ensure_ascii=False)[:20000]
    return out


def save_account_info(uid: str, info: dict) -> None:
    keys = [k for k in ("cash_account_type", "product", "balance", "balance_currency", "balance_type", "balance_date",
                        "balances_json") if k in info]
    if not keys:
        return
    with db.connect() as con:
        con.execute(f"UPDATE bank_accounts SET {', '.join(k + '=?' for k in keys)} WHERE uid=?",
                    [info[k] for k in keys] + [uid])


def sync_error(acc, e: Exception) -> tuple[str, bool]:
    """Messaggio da mostrare quando la sincronizzazione di un conto non riesce, e se è solo un avviso (limite
    giornaliero della banca: si risolve da solo) invece di un errore."""
    name = f"{acc.get('label') or acc.get('aspsp_name') or ''} · {acc.get('account_name') or ''}".strip(" ·")
    if isinstance(e, RateLimited):
        d = next((str(v)[:10] for v in (acc.get("balance_date"), acc.get("last_sync"))
                  if isinstance(v, str) and v.strip()), "")
        try:
            when = i18n.date_short(date.fromisoformat(d)) if d else ""
        except ValueError:
            when = ""
        msg = i18n.t("{name}: la banca ha raggiunto il limite giornaliero di accessi (di solito 4 al giorno per "
                     "conto). Riprova domani.", name=name)
        msg += " " + (i18n.t("Intanto vale il saldo del {d}.", d=when) if when
                      else i18n.t("Intanto restano i dati dell'ultima sincronizzazione."))
        return msg, True
    return f"{name}: {e}", False


def is_card(acc) -> bool:
    """Il conto collegato è una carta (di credito o prepagata), non un conto corrente."""
    typ = str(acc.get("cash_account_type") or "").upper()
    if typ == "CARD":
        return True
    if typ:
        return False
    text = f"{acc.get('product') or ''} {acc.get('account_name') or ''}".lower()
    return any(w in text for w in ("card", "carta", "credit", "credito", "prepagat"))


def sync_account(uid: str, date_from: date | None = None, include_pending: bool = False) -> tuple[int, int]:
    from core.importers import finalize

    with db.connect() as con:
        acc = dict(con.execute("SELECT * FROM bank_accounts WHERE uid=?", (uid,)).fetchone())
    if date_from is None:
        if acc.get("last_sync"):
            date_from = datetime.fromisoformat(acc["last_sync"][:10]).date() - timedelta(days=5)
        else:
            date_from = date.today() - timedelta(days=90)
    txs = fetch_transactions(uid, date_from)
    label = acc.get("label") or acc.get("aspsp_name") or "Banca"
    legacy = tuple(dict.fromkeys([label, acc.get("aspsp_name") or ""]))
    rows = to_rows(txs, label, include_pending, uid=uid, legacy_labels=legacy)
    _use_legacy_ids(rows)
    rows = finalize(rows, label, f"openbanking:{acc.get('aspsp_name')}")
    res = db.insert_transactions(rows)
    info = fetch_details_and_balance(uid)
    save_account_info(uid, info)
    with db.connect() as con:
        con.execute("UPDATE bank_accounts SET last_sync=? WHERE uid=?", (db.now_str(), uid))
    return res
