"""Collegamento automatico ai conti (Fineco, Revolut e altre banche europee) tramite
Enable Banking, un aggregatore PSD2/Open Banking autorizzato.

Per uso personale si registra gratuitamente un'applicazione in modalità "restricted"
su https://enablebanking.com (Control Panel) e si collegano i PROPRI conti.
Servono: Application ID + file della chiave privata (.pem) scaricato alla creazione.
"""
from __future__ import annotations

import json
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


def _old_uids(row) -> list[str]:
    try:
        v = json.loads(row["old_uids"] or "[]")
    except (ValueError, TypeError, KeyError, IndexError):
        v = []
    return [str(x) for x in v if x] if isinstance(v, list) else []


def _same_text(a, b) -> bool:
    a, b = str(a or "").strip().lower(), str(b or "").strip().lower()
    return bool(a) and a == b


def match_existing(rows: list, accounts: list[dict], aspsp_name: str) -> dict[str, str]:
    """Con un nuovo consenso la banca dà id nuovi agli stessi conti (gli id di Enable Banking valgono per un solo
    collegamento). Abbina ogni conto ricevuto a quello già collegato: prima con identification_hash (stabile tra un
    consenso e l'altro), altrimenti con banca + valuta + IBAN (o, senza IBAN, + nome del prodotto, es. la carta
    mascherata). Se più conti ricevuti somigliano allo stesso conto già collegato (es. conto principale e un pocket
    con lo stesso IBAN) vince quello con lo stesso tipo e nome. Ritorna {uid nuovo: uid già collegato}."""
    rows = [dict(r) for r in rows if (r["aspsp_name"] or "") == aspsp_name]
    new_uids = {a.get("uid") for a in accounts}
    free = [r for r in rows if r["uid"] not in new_uids]
    out: dict[str, str] = {}
    used: set[str] = set()
    # 1) identification_hash
    for a in accounts:
        h = a.get("identification_hash")
        if not h or a.get("uid") in new_uids & {r["uid"] for r in rows}:
            continue
        r = next((r for r in free if r.get("ident_hash") == h and r["uid"] not in used), None)
        if r:
            out[a["uid"]] = r["uid"]
            used.add(r["uid"])
    # 2) IBAN / prodotto + valuta, per i conti collegati prima che l'hash venisse salvato
    scored = []
    for a in accounts:
        uid = a.get("uid")
        if not uid or uid in out or uid in {r["uid"] for r in rows}:
            continue
        iban = (a.get("account_id") or {}).get("iban") or ""
        ccy = str(a.get("currency") or "").upper()
        for r in free:
            if r["uid"] in used or str(r.get("currency") or "").upper() != ccy:
                continue
            if r.get("ident_hash") and a.get("identification_hash"):
                continue  # entrambi hanno l'id stabile ed è diverso: sono conti diversi
            if iban:
                if (r.get("iban") or "") != iban:
                    continue
            elif r.get("iban") or not _same_text(r.get("product"), a.get("product")):
                continue
            score = (_same_text(r.get("cash_account_type"), a.get("cash_account_type"))
                     or not (r.get("cash_account_type") or a.get("cash_account_type")),
                     _same_text(r.get("account_name"), a.get("name")),
                     _same_text(r.get("product"), a.get("product")) or not (r.get("product") or a.get("product")))
            scored.append((score, -accounts.index(a), uid, r["uid"]))
    for _score, _pos, uid, old in sorted(scored, reverse=True):
        if uid in out or old in used:
            continue
        out[uid] = old
        used.add(old)
    return out


def create_session(code: str, aspsp_name: str, country: str) -> list[dict]:
    """Salva i conti autorizzati. I conti già collegati (consenso rinnovato) mantengono nome nell'app, storico e
    impostazioni: cambia solo l'id del collegamento. Ogni voce ritornata: uid, name, iban, renewed (bool)."""
    data = _req("POST", "/sessions", json={"code": code})
    session_id = data.get("session_id")
    valid_until = (data.get("access") or {}).get("valid_until", "")
    label = default_label(aspsp_name)
    accounts = [a for a in data.get("accounts", []) if a.get("uid")]
    saved = []
    with db.connect() as con:
        existing = con.execute("SELECT * FROM bank_accounts").fetchall()
        matches = match_existing(existing, accounts, aspsp_name)
        for acc in accounts:
            uid = acc["uid"]
            iban = (acc.get("account_id") or {}).get("iban", "")
            name = acc.get("name") or acc.get("product") or iban or uid[:8]
            ident = acc.get("identification_hash") or None
            old = matches.get(uid)
            if old:
                prev = con.execute("SELECT * FROM bank_accounts WHERE uid=?", (old,)).fetchone()
                olds = list(dict.fromkeys(_old_uids(prev) + [old]))
                con.execute(
                    """UPDATE bank_accounts SET uid=?, session_id=?, valid_until=?, aspsp_country=?,
                           ident_hash=COALESCE(?, ident_hash), old_uids=?,
                           iban=COALESCE(NULLIF(?, ''), iban),
                           cash_account_type=COALESCE(NULLIF(?, ''), cash_account_type),
                           product=COALESCE(NULLIF(?, ''), product)
                       WHERE uid=?""",
                    (uid, session_id, valid_until, country, ident, json.dumps(olds), iban,
                     acc.get("cash_account_type") or "", acc.get("product") or "", old))
                con.execute("UPDATE transactions SET bank_uid=? WHERE bank_uid=?", (uid, old))
                saved.append({"uid": uid, "name": name, "iban": iban, "renewed": True})
                continue
            con.execute(
                """INSERT INTO bank_accounts(uid, session_id, aspsp_name, aspsp_country, account_name, iban, currency,
                                             valid_until, label, cash_account_type, product, ident_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(uid) DO UPDATE SET session_id=excluded.session_id, valid_until=excluded.valid_until,
                       cash_account_type=excluded.cash_account_type, product=excluded.product,
                       ident_hash=COALESCE(excluded.ident_hash, ident_hash)""",
                (uid, session_id, aspsp_name, country, name, iban, acc.get("currency", ""), valid_until, label,
                 acc.get("cash_account_type") or "", acc.get("product") or "", ident),
            )
            saved.append({"uid": uid, "name": name, "iban": iban,
                          "renewed": any(r["uid"] == uid for r in existing)})
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
    # altri collegamenti della stessa banca e valuta che restano nel conto di prima (es. il conto principale quando
    # si sposta un suo pocket in un conto a parte): i loro movimenti e le carte non si toccano
    others = con.execute(
        """SELECT COUNT(*) FROM bank_accounts WHERE uid<>? AND aspsp_name=? AND upper(COALESCE(currency, ''))=?
             AND COALESCE(NULLIF(label, ''), aspsp_name)=?""",
        (uid, acc["aspsp_name"], (acc["currency"] or "").upper(), old)).fetchone()[0]
    if others:
        cur = con.execute("UPDATE transactions SET account=? WHERE account=? AND source=? AND bank_uid=?",
                          (label, old, src, uid))
        return cur.rowcount
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
            row["_legacy_ids"] = [db.make_external_id("eb", lab, key, n) for lab in legacy_labels if lab]
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


def legacy_keys(acc: dict, all_rows: list) -> tuple[str, ...]:
    """Nomi e id con cui i movimenti di questo conto possono essere già stati salvati: il nome del conto nell'app,
    quello della banca e gli id dei collegamenti precedenti (anche quelli finiti, per errore di abbinamento, su un
    altro conto della stessa banca e valuta: un movimento ha un riferimento unico, quindi non si confonde)."""
    keys = [acc.get("label") or acc.get("aspsp_name") or "Banca", acc.get("aspsp_name") or ""]
    ccy = str(acc.get("currency") or "").upper()
    for r in all_rows:
        r = dict(r)
        if (r.get("aspsp_name") or "") == (acc.get("aspsp_name") or "") and \
                str(r.get("currency") or "").upper() == ccy:
            keys += _old_uids(r)
    return tuple(k for k in dict.fromkeys(keys) if k and k != acc.get("uid"))


def link_internal_transfers(aspsp_name: str, days: int = 120) -> int:
    """Giroconti tra due conti della stessa banca collegati all'app (es. dal conto Revolut a un pocket): stesso
    importo con segno opposto, stessa valuta, a 0-1 giorni di distanza, su due conti diversi (carte escluse).
    Entrambe le parti diventano «Trasferimenti tra conti», così non contano né come spesa né come entrata.
    Le categorie scelte a mano non si toccano. Ritorna quanti movimenti sono stati cambiati."""
    from core.categorize import TRANSFER_CAT

    since = (date.today() - timedelta(days=days)).isoformat()
    with db.connect() as con:
        accs = [dict(r) for r in con.execute("SELECT * FROM bank_accounts WHERE aspsp_name=?", (aspsp_name,))]
        uids = {a["uid"] for a in accs if not is_card(a)}
        if len(uids) < 2:
            return 0
        q = ",".join("?" * len(uids))
        rows = [dict(r) for r in con.execute(
            f"""SELECT id, date, amount, currency, bank_uid, category, category_locked FROM transactions
                WHERE source=? AND bank_uid IN ({q}) AND split_of IS NULL AND split_total IS NULL AND date >= ?
                ORDER BY date, id""", (f"openbanking:{aspsp_name}", *uids, since))]
        used: set[int] = set()
        changed = 0
        for o in rows:
            if o["amount"] >= 0 or o["id"] in used:
                continue
            d = date.fromisoformat(str(o["date"])[:10])
            mate = None
            for i in rows:
                if i["id"] in used or i["amount"] <= 0 or i["bank_uid"] == o["bank_uid"] or \
                        i["currency"] != o["currency"] or abs(i["amount"] + o["amount"]) >= 0.005:
                    continue
                if abs((date.fromisoformat(str(i["date"])[:10]) - d).days) <= 1:
                    mate = i
                    break
            if mate is None:
                continue
            used.update((o["id"], mate["id"]))
            for r in (o, mate):
                if not r["category_locked"] and r["category"] != TRANSFER_CAT:
                    con.execute("UPDATE transactions SET category=? WHERE id=?", (TRANSFER_CAT, r["id"]))
                    changed += 1
    return changed


def sync_account(uid: str, date_from: date | None = None, include_pending: bool = False) -> tuple[int, int]:
    from core.importers import finalize

    with db.connect() as con:
        acc = dict(con.execute("SELECT * FROM bank_accounts WHERE uid=?", (uid,)).fetchone())
        all_rows = con.execute("SELECT * FROM bank_accounts").fetchall()
    if date_from is None:
        if acc.get("last_sync"):
            date_from = datetime.fromisoformat(acc["last_sync"][:10]).date() - timedelta(days=5)
        else:
            date_from = date.today() - timedelta(days=90)
    txs = fetch_transactions(uid, date_from)
    label = acc.get("label") or acc.get("aspsp_name") or "Banca"
    legacy = legacy_keys(acc, all_rows)
    rows = to_rows(txs, label, include_pending, uid=uid, legacy_labels=legacy)
    _use_legacy_ids(rows)
    rows = finalize(rows, label, f"openbanking:{acc.get('aspsp_name')}")
    res = db.insert_transactions(rows)
    try:
        link_internal_transfers(acc.get("aspsp_name") or "")
    except Exception:
        pass  # solo una comodità sulle categorie: non deve mai bloccare la sincronizzazione
    try:
        from core import pockets
        pockets.sync()   # pocket Revolut che la banca non mostra: seguiti dai giroconti
    except Exception:
        pass
    info = fetch_details_and_balance(uid)
    save_account_info(uid, info)
    with db.connect() as con:
        con.execute("UPDATE bank_accounts SET last_sync=? WHERE uid=?", (db.now_str(), uid))
    return res
