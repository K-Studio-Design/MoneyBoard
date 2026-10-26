"""Import degli export di Chase (JPMorgan Chase Bank, USA).

Formati supportati (scaricabili da chase.com → conto → «Download account activity»):
- CSV conto corrente / risparmio:
    Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
  Details = DEBIT / CREDIT / CHECK / DSLIP; Amount negativo per le uscite; date MM/DD/YYYY.
  Spesso ogni riga finisce con una virgola in più (una colonna vuota in fondo): va letta senza indice.
- CSV carta di credito:
    Transaction Date,Post Date,Description,Category,Type,Amount,Memo
  Type = Sale / Payment / Return / Adjustment / Fee; normalmente gli acquisti sono negativi e i pagamenti
  della carta positivi. Alcuni export (e alcuni strumenti) usano il segno opposto: si riconosce dai «Sale».
  Alcuni export aggiungono una colonna «Card» (ultime cifre della carta) all'inizio.
- QFX / OFX («Quicken» / «Microsoft Money»): blocchi <STMTTRN> con DTPOSTED, TRNAMT, FITID, NAME, MEMO.
Gli estratti PDF non sono supportati: dal sito Chase si scarica lo stesso periodo in CSV.
"""
from __future__ import annotations

import csv
import io
import re

import pandas as pd

from core import i18n

CHECKING_COLS = {"details", "posting date", "description", "amount", "type", "balance"}
CARD_COLS = {"transaction date", "post date", "description", "category", "type", "amount"}

# categorie Chase (carte di credito) -> parola chiave che il categorizzatore conosce (BANK_CATEGORY_HINTS)
CARD_CATEGORY_HINTS = {
    "food & drink": "ristoranti", "groceries": "alimentari", "gas": "carburante", "shopping": "shopping",
    "travel": "viaggi", "entertainment": "svago", "bills & utilities": "bollette", "health & wellness": "salute",
    "personal": "cura personale", "home": "casa", "automotive": "auto", "education": "istruzione",
    "fees & adjustments": "commissioni", "gifts & donations": "regali", "professional services": "",
}
# «Type» del conto corrente -> suggerimento
CHECKING_TYPE_HINTS = {
    "atm": "prelievo contanti", "fee_transaction": "commissioni", "acct_xfer": "giroconto",
    "loan_pmt": "", "check_deposit": "", "atm_deposit": "giroconto",
}
RE_ZELLE = re.compile(r"^zelle (?:payment|pmt) (?:to|from) (.+)$", re.I)
RE_PAYROLL = re.compile(r"(?<!\w)(payroll|dir dep|direct dep|direct deposit|salary)(?!\w)", re.I)


def _text(file_bytes: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1", errors="replace")


def _norm_cols(cols) -> list[str]:
    return [re.sub(r"\s+", " ", str(c)).strip().lower() for c in cols]


def detect(file_bytes: bytes, filename: str) -> str | None:
    """'checking', 'card', 'ofx' oppure None se non sembra un export Chase."""
    head = _text(file_bytes[:4000])
    if filename.lower().endswith((".qfx", ".ofx")) or "<OFX>" in head.upper() or "OFXHEADER" in head.upper():
        return "ofx"
    first = head.splitlines()[0] if head else ""
    cols = set(_norm_cols(first.split(",")))
    if CHECKING_COLS <= cols:
        return "checking"
    if CARD_COLS <= cols:
        return "card"
    return None


def _date_us(v) -> str | None:
    d = pd.to_datetime(str(v).strip(), format="%m/%d/%Y", errors="coerce")
    if pd.isna(d):
        d = pd.to_datetime(str(v).strip(), errors="coerce", dayfirst=False)
    return None if pd.isna(d) else d.date().isoformat()


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def _counterparty(desc: str) -> str | None:
    """Nome della persona nei pagamenti Zelle (per riconoscere i giroconti verso se stessi)."""
    m = RE_ZELLE.match(desc.strip())
    if not m:
        return None
    words = []
    for w in m.group(1).split():
        if any(ch.isdigit() for ch in w) or (len(words) >= 2 and re.fullmatch(r"(jpm|bac|wfct|cti)\w*", w, re.I)):
            break
        words.append(w)
    return " ".join(words) or None


def _read_csv(file_bytes: bytes) -> pd.DataFrame:
    """Legge il CSV riga per riga: Chase spesso aggiunge una virgola finale (colonna vuota in più) che
    farebbe slittare le colonne con una lettura standard."""
    reader = csv.reader(io.StringIO(_text(file_bytes)))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return pd.DataFrame()
    head = _norm_cols(rows[0])
    while head and head[-1] == "":
        head.pop()
    data = [(r + [""] * len(head))[:len(head)] for r in rows[1:]]
    return pd.DataFrame(data, columns=head)


def parse_checking(file_bytes: bytes) -> list[dict]:
    df = _read_csv(file_bytes)
    rows = []
    for _, r in df.iterrows():
        d = _date_us(r.get("posting date"))
        a = _num(r.get("amount"))
        if not d or a is None or a == 0:
            continue
        desc = re.sub(r"\s+", " ", str(r.get("description", ""))).strip()
        typ = str(r.get("type", "")).strip()
        hint = CHECKING_TYPE_HINTS.get(typ.lower(), "")
        if a > 0 and RE_PAYROLL.search(desc):
            hint = "stipendio"
        check = str(r.get("check or slip #", "")).strip()
        rows.append({
            "date": d,
            "description": desc + (f" (assegno {check})" if check and "check" in typ.lower() and check not in desc else ""),
            "amount": float(a), "currency": "USD", "_bank_category": hint, "_counterparty": _counterparty(desc),
            "_extra": f"{typ}|{check}",
        })
    return rows


def parse_card(file_bytes: bytes) -> list[dict]:
    df = _read_csv(file_bytes)
    types = df.get("type", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    amounts = df["amount"].map(_num)
    # segno: gli acquisti («Sale») devono risultare negativi (uscite)
    sales = amounts[types == "sale"].dropna()
    flip = len(sales) > 0 and (sales > 0).mean() > 0.5
    rows = []
    for (_, r), a, typ in zip(df.iterrows(), amounts, types):
        d = _date_us(r.get("transaction date")) or _date_us(r.get("post date"))
        if not d or a is None or a == 0:
            continue
        a = -a if flip else a
        desc = re.sub(r"\s+", " ", str(r.get("description", ""))).strip()
        hint = CARD_CATEGORY_HINTS.get(str(r.get("category", "")).strip().lower(), "")
        if typ == "payment":
            hint = "giroconto"      # pagamento della carta dal conto corrente: non è un'entrata
        elif typ == "fee":
            hint = "commissioni"
        memo = str(r.get("memo", "")).strip()
        rows.append({
            "date": d, "description": desc, "amount": float(a), "currency": "USD", "_bank_category": hint,
            "_reversal": typ == "return" and a > 0,
            "_extra": f"{typ}|{str(r.get('card', '')).strip()}",
            "notes": memo,
        })
    return rows


def _ofx_tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else ""


def parse_ofx(file_bytes: bytes) -> tuple[list[dict], str, str]:
    """Ritorna (righe, valuta, tipo conto 'card' o 'checking')."""
    text = _text(file_bytes)
    ccy = (_ofx_tag(text, "CURDEF") or "USD").upper()
    kind = "card" if re.search(r"<CCSTMTRS>|<CREDITCARDMSGSRSV1>", text, re.I) else "checking"
    rows = []
    for block in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", text, re.I | re.S):
        dt = _ofx_tag(block, "DTPOSTED")[:8]
        a = _num(_ofx_tag(block, "TRNAMT"))
        if not re.fullmatch(r"\d{8}", dt) or a is None or a == 0:
            continue
        name = _ofx_tag(block, "NAME")
        memo = _ofx_tag(block, "MEMO")
        desc = re.sub(r"\s+", " ", (name + (" " + memo if memo and memo.lower() not in name.lower() else ""))).strip()
        desc = desc.replace("&amp;", "&")
        typ = _ofx_tag(block, "TRNTYPE").upper()
        hint = {"ATM": "prelievo contanti", "FEE": "commissioni", "SRVCHG": "commissioni", "INT": "interessi",
                "XFER": "giroconto", "DIV": "interessi"}.get(typ, "")
        if a > 0 and (typ == "DIRECTDEP" or RE_PAYROLL.search(desc)):
            hint = "stipendio"
        if kind == "card" and typ in ("PAYMENT", "CREDIT") and re.search(r"payment|thank you", desc, re.I):
            hint = "giroconto"
        fitid = _ofx_tag(block, "FITID")
        rows.append({
            "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}", "description": desc, "amount": float(a), "currency": ccy,
            "_bank_category": hint, "_counterparty": _counterparty(desc), "_extra": f"{typ}|{fitid}",
        })
    return rows, ccy, kind


def parse(file_bytes: bytes, filename: str) -> tuple[str, list[dict]]:
    """('checking' | 'card', righe) per qualsiasi export Chase supportato."""
    kind = detect(file_bytes, filename)
    if kind == "checking":
        return kind, parse_checking(file_bytes)
    if kind == "card":
        return kind, parse_card(file_bytes)
    if kind == "ofx":
        rows, _ccy, acc_kind = parse_ofx(file_bytes)
        return acc_kind, rows
    raise ValueError(i18n.t("non sembra un export Chase (CSV del conto, CSV della carta o file QFX/OFX)"))
