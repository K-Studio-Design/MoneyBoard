"""Lettore dell'«Estratto conto consolidato» di Revolut (xlsx, report a sezioni).

Struttura del file:
  - "Conti correnti … Estratti conto delle operazioni": una sezione per valuta
    ("Conto personale (EUR)", "(USD)", "(CHF)") con colonne
    Data | Descrizione | Categoria | Denaro in entrata/uscita | Saldo | Imposte | Altre imposte | Costi
    (per le valute diverse dall'euro ogni importo ha due colonne: valuta del conto + controvalore in EUR);
  - "Conti deposito … Transaction Statements": interessi del conto deposito;
  - sezioni riepilogative e crypto (ignorate: gli acquisti crypto compaiono già come
    uscite dal conto in euro).

Insidie gestite:
  - simbolo € corrotto ("â_x0082_¬") e importi in formato italiano "1.047,57";
  - date in parte testuali ("1 gen 2025") e in parte già convertite da Excel. Dove il testo
    originale era "gg/mm/aa", Excel ha invertito giorno e mese (04/08/26 -> 8 aprile): in quelle
    sezioni le date convertite vengono corrette.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

MESI = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9,
        "ott": 10, "nov": 11, "dic": 12,
        "jan": 1, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "dec": 12}
CCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
RE_TEXT_DATE = re.compile(r"^\s*(\d{1,2})\s+([a-zA-Zà-ü]{3})[a-zà-ü]*\.?\s+(\d{4})\s*$")
RE_NUM_DATE = re.compile(r"^\s*(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\s*$")
RE_ACCOUNT = re.compile(r"^Conto personale \(([A-Z]{3})\)\s*$")


def is_consolidated(raw: pd.DataFrame) -> bool:
    first = " ".join(str(v) for v in raw.iloc[:5, 0].tolist())
    col0 = raw.iloc[:, 0].astype(str)
    return "Riepiloghi" in first or col0.str.contains("Estratti conto delle op", regex=False).any()


def fix_text(s) -> str:
    """Ripara la codifica rotta (UTF-8 letto come Latin-1) e il segnaposto _x0082_ di Excel."""
    s = str(s)
    s = s.replace("_x0082_", "\x82")
    if "â" in s or "Ã" in s:
        try:
            s = s.encode("cp1252", errors="strict").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                s = s.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return s.replace("â\x82¬", "€").replace("\x82", "").strip()


def parse_money(v) -> tuple[float | None, str | None]:
    """'−1.047,57â_x0082_¬' -> (-1047.57, 'EUR'); '-32,94$' -> (-32.94, 'USD'); '121,60 CHF' -> (121.6, 'CHF')."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None, None
    if isinstance(v, (int, float)):
        return float(v), None
    s = fix_text(v)
    ccy = None
    m = re.search(r"\b([A-Z]{3})\b", s)
    if m:
        ccy = m.group(1)
    for sym, code in CCY_SYMBOLS.items():
        if sym in s:
            ccy = ccy or code
    num = re.sub(r"[^\d,.\-+−]", "", s).replace("−", "-").replace("+", "")
    if not num or num in "-.,":
        return None, ccy
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    try:
        return float(num), ccy
    except ValueError:
        return None, ccy


def _section_style(values: list) -> str:
    """Capisce se nella sezione le date testuali sono 'gg mese aaaa' o 'gg/mm/aa'."""
    for v in values:
        if isinstance(v, str):
            if RE_TEXT_DATE.match(v):
                return "text"
            if RE_NUM_DATE.match(v):
                return "numeric"
    return "text"


def parse_date(v, style: str) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (datetime, pd.Timestamp, date)):
        d = v.date() if isinstance(v, (datetime, pd.Timestamp)) else v
        if style == "numeric" and d.day <= 12:
            # Excel ha letto "gg/mm/aa" come "mm/gg/aa": inverte giorno e mese
            try:
                d = date(d.year, d.day, d.month)
            except ValueError:
                return None
        return d.isoformat()
    s = fix_text(v)
    m = RE_TEXT_DATE.match(s)
    if m:
        month = MESI.get(m.group(2).lower()[:3])
        if month:
            return date(int(m.group(3)), month, int(m.group(1))).isoformat()
    m = RE_NUM_DATE.match(s)
    if m:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def parse(file_bytes: bytes, filename: str) -> pd.DataFrame:
    import io

    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl") if filename.lower().endswith(
        (".xlsx", ".xlsm")) else pd.read_csv(io.BytesIO(file_bytes), header=None)
    rows = raw.values.tolist()
    out = []
    zone = None          # "correnti" | "deposito" | altro
    account_ccy = None
    i = 0
    while i < len(rows):
        r = rows[i]
        c0 = fix_text(r[0]) if not (isinstance(r[0], float) and pd.isna(r[0])) else ""
        if "Estratti conto delle op" in c0 and c0.startswith("Conti correnti"):
            zone = "correnti"
        elif c0.startswith("Conti deposito") and ("Transaction" in c0 or "Estratti" in c0):
            zone = "deposito"
        elif c0.startswith(("Crypto", "Investment", "Commodities", "Prestiti")) and "Riepiloghi" not in c0:
            zone = "altro"
        elif "Riepiloghi" in c0:
            zone = "riepilogo"
        m = RE_ACCOUNT.match(c0)
        if m:
            account_ccy = m.group(1)
        if zone in ("correnti", "deposito") and c0 == "Data" and i + 1 < len(rows):
            header = [fix_text(h) if isinstance(h, str) else "" for h in r]
            # righe della tabella fino a "Totale" / separatore / riga vuota
            j = i + 1
            block = []
            while j < len(rows):
                rr = rows[j]
                first = rr[0]
                if isinstance(first, float) and pd.isna(first):
                    break
                f = fix_text(first)
                if f.startswith(("Totale", "---")):
                    break
                block.append(rr)
                j += 1
            style = _section_style([b[0] for b in block])
            if zone == "correnti":
                out += _parse_current(block, header, account_ccy or "EUR", style)
            else:
                out += _parse_deposit(block, header, style)
            i = j
            continue
        i += 1
    df = pd.DataFrame(out, columns=["date", "description", "bank_category", "amount", "currency",
                                    "amount_eur", "fees", "section"])
    return df.dropna(subset=["date", "amount"]).reset_index(drop=True)


def _parse_current(block, header, ccy, style):
    # posizioni delle colonne: per valute estere ogni grandezza ha 2 colonne (valuta, EUR)
    idx_money = [k for k, h in enumerate(header) if h.startswith("Denaro")]
    idx_fee = [k for k, h in enumerate(header) if h.startswith("Costi")]
    res = []
    for b in block:
        d = parse_date(b[0], style)
        desc = fix_text(b[1]) if isinstance(b[1], str) else str(b[1])
        cat = fix_text(b[2]) if isinstance(b[2], str) else ""
        amount, c1 = parse_money(b[idx_money[0]]) if idx_money else (None, None)
        amount_eur = None
        if len(idx_money) > 1:
            amount_eur, _ = parse_money(b[idx_money[1]])
        elif (c1 or ccy) == "EUR":
            amount_eur = amount
        fee = parse_money(b[idx_fee[0]])[0] if idx_fee else None
        res.append([d, desc, cat, amount, c1 or ccy, amount_eur, fee or 0.0, f"Conto {ccy}"])
    return res


def _parse_deposit(block, header, style):
    """Conto deposito: si registrano solo gli interessi netti accreditati."""
    try:
        k_net = next(k for k, h in enumerate(header) if h.lower().startswith("net interest") or "netti" in h.lower())
    except StopIteration:
        k_net = len(header) - 1
    res = []
    for b in block:
        d = parse_date(b[0], style)
        net, c = parse_money(b[k_net])
        if not net:
            continue
        res.append([d, "Interessi conto deposito Revolut", "Interessi", net, c or "EUR",
                    net if (c or "EUR") == "EUR" else None, 0.0, "Conto deposito"])
    return res
