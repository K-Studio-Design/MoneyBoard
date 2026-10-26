"""Redditi da investimenti per il calcolo delle tasse USA (funzione in prova, alpha): moduli 1099.

Moduli considerati (i principali che un broker americano invia, di solito riuniti nel «Consolidated 1099»):
- 1099-B   vendite di titoli: per ogni vendita incasso (box 1d), costo fiscale (1e), perdita da wash sale non
           deducibile (1g); a breve termine (fino a un anno) o a lungo termine; ritenuta federale (box 4);
- 1099-DIV dividendi ordinari (1a), di cui qualificati (1b), distribuzioni di plusvalenze (2a), ritenuta federale
           (4), imposte estere pagate (7);
- 1099-INT interessi (1), di cui da titoli del Tesoro USA (3, esenti dalle tasse statali), ritenuta federale (4),
           imposte estere pagate (6).

Come si caricano:
- file TXF (Tax Exchange Format v042), l'esportazione «per TurboTax / software fiscale» offerta da molti broker:
  righe di un carattere iniziale (T tipo, N numero di riferimento, P descrizione, D data, $ importo), record separati
  da «^». Numeri di riferimento usati: 321/711/712 vendite a breve, 323/713/714 a lungo, 673/715/716 durata non
  indicata (si deduce dalle date), 682/718 wash sale; 286 dividendi, 683 qualificati, 488 distribuzioni di
  plusvalenze, 615 ritenuta sui dividendi, 649 imposte estere sui dividendi; 287 interessi, 288 interessi da titoli
  di Stato USA, 616 ritenuta sugli interessi, 641 imposte estere sugli interessi.
  Formato delle vendite (record 4 e 5): P descrizione, D data di acquisto, D data di vendita, $ costo, $ incasso,
  [$ perdita non deducibile per wash sale].
- CSV delle vendite (formato 1099-B / modulo 8949 scaricato dal broker): colonne riconosciute dal nome;
- a mano, copiando i riquadri principali del modulo (anche i totali del riepilogo del 1099-B).
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta

import pandas as pd

from core import db

KINDS = ("1099-B", "1099-DIV", "1099-INT")
SCHEMA = """
CREATE TABLE IF NOT EXISTS tax_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    kind TEXT NOT NULL,              -- 1099-B | 1099-DIV | 1099-INT
    broker TEXT DEFAULT '',
    source TEXT DEFAULT 'manuale',   -- manuale | txf | csv
    file_name TEXT DEFAULT '',
    data TEXT DEFAULT '{}',          -- importi del modulo (JSON)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

INT_FIELDS = ("interest", "us_gov", "fed_withheld", "foreign_tax", "tax_exempt")
DIV_FIELDS = ("ordinary", "qualified", "cg_dist", "fed_withheld", "foreign_tax", "exempt_int_div")
B_SUMMARY_FIELDS = ("st_proceeds", "st_basis", "st_wash", "lt_proceeds", "lt_basis", "lt_wash", "fed_withheld")


class InvestError(Exception):
    pass


# ---------------------------------------------------------------- numeri e date
def num(v) -> float | None:
    """Importo in formato americano: 1,234.56 / $1,234.56 / (1,234.56) negativo / -1234.56."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).strip().replace("$", "").replace("USD", "").replace(" ", "")
    if s in ("", "-", "--", "n/a", "N/A"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if s.endswith("-"):
        neg, s = True, s[:-1]
    if not re.fullmatch(r"[-+]?\d[\d,]*(\.\d+)?|[-+]?\.\d+", s):
        return None
    x = float(s.replace(",", ""))
    return -abs(x) if neg else x


def parse_date(v) -> date | None:
    s = str(v or "").strip()
    if not s or s.lower().startswith("var"):           # «Various»: più acquisti in date diverse
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def long_term(acquired: date | None, sold: date | None) -> bool | None:
    """A lungo termine se tenuto più di un anno (venduto dopo l'anniversario dell'acquisto)."""
    if not acquired or not sold:
        return None
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:                                  # 29 febbraio
        anniversary = acquired + timedelta(days=365)
    return sold > anniversary


def lot_gain(lot: dict) -> float:
    """Plus o minusvalenza di una vendita: incasso - costo + perdita non deducibile per wash sale."""
    return float(lot.get("proceeds") or 0) - float(lot.get("basis") or 0) + float(lot.get("wash") or 0)


def _term(lot: dict) -> str:
    t = lot.get("term")
    if t in ("S", "L"):
        return t
    lt = long_term(parse_date(lot.get("acquired")), parse_date(lot.get("sold")))
    return "L" if lt else "S"      # durata sconosciuta: breve termine (aliquote più alte, stima prudente)


# ---------------------------------------------------------------- TXF
TXF_ST = {"321", "711", "712"}
TXF_LT = {"323", "713", "714"}
TXF_UNKNOWN = {"673", "715", "716", "682", "718"}
TXF_INT = {"287": "interest", "288": "us_gov", "616": "fed_withheld", "641": "foreign_tax", "289": "tax_exempt"}
TXF_DIV = {"286": "ordinary", "683": "qualified", "488": "cg_dist", "615": "fed_withheld", "649": "foreign_tax"}


def parse_txf(text: str) -> dict:
    """Ritorna {"lots": [...], "div": {...}, "int": {...}, "warnings": [...]} da un file TXF v042."""
    lines = [ln.rstrip("\r") for ln in text.splitlines()]
    if not any(ln.strip().upper().startswith("V0") for ln in lines[:5]):
        raise InvestError("TXF_FORMAT")
    records, cur = [], []
    for ln in lines:
        if ln.strip() == "^":
            if cur:
                records.append(cur)
            cur = []
        elif ln:
            cur.append(ln)
    if cur:
        records.append(cur)
    lots, div, intr, warnings = [], {}, {}, []
    for rec in records:
        ref = next((ln[1:].strip() for ln in rec if ln[:1] == "N"), None)
        if ref is None:
            continue                                     # intestazione (V, A, D)
        texts = [ln[1:].strip() for ln in rec if ln[:1] == "P"]
        dates = [ln[1:].strip() for ln in rec if ln[:1] == "D"]
        amounts = [num(ln[1:]) for ln in rec if ln[:1] == "$"]
        if ref in TXF_ST | TXF_LT | TXF_UNKNOWN:
            if len(amounts) < 2 or amounts[0] is None or amounts[1] is None:
                warnings.append("TXF_LOT")
                continue
            lot = {"desc": texts[0] if texts else "", "acquired": dates[0] if len(dates) > 0 else "",
                   "sold": dates[1] if len(dates) > 1 else "", "basis": abs(amounts[0]), "proceeds": abs(amounts[1]),
                   "wash": abs(amounts[2]) if len(amounts) > 2 and amounts[2] else 0.0,
                   "term": "S" if ref in TXF_ST else "L" if ref in TXF_LT else None}
            lot["term"] = _term(lot)
            lots.append(lot)
        elif ref in TXF_DIV or ref in TXF_INT:
            val = next((a for a in amounts if a is not None), None)
            if val is None:
                continue
            target, key = (div, TXF_DIV[ref]) if ref in TXF_DIV else (intr, TXF_INT[ref])
            target[key] = round(target.get(key, 0.0) + abs(val), 2)   # le ritenute nel TXF sono negative
    if not lots and not div and not intr:
        raise InvestError("TXF_EMPTY")
    return {"lots": lots, "div": div, "int": intr, "warnings": warnings}


# ---------------------------------------------------------------- CSV delle vendite (1099-B / 8949)
_COLS = [
    ("wash", ("wash sale", "wash", "disallowed")),
    ("acquired", ("date acquired", "acquired", "open date", "purchase date", "date purchased", "acquisition date")),
    ("sold", ("date sold", "sold", "sale date", "close date", "date of sale", "disposed", "closing date")),
    ("proceeds", ("proceeds", "sales price", "sale price", "gross proceeds", "sale amount")),
    ("basis", ("cost basis", "cost or other basis", "adjusted basis", "basis", "cost")),
    ("gain", ("gain/loss", "gain or loss", "gain (loss)", "realized gain", "gain", "loss")),
    ("term", ("term", "holding period", "short/long", "st/lt", "short-term/long-term")),
    ("desc", ("description", "security", "symbol", "investment name", "name", "ticker")),
]


def _match_columns(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    low = [h.strip().lower() for h in header]
    for key, words in _COLS:
        for w in words:
            idx = next((i for i, h in enumerate(low) if w in h and i not in found.values()), None)
            if idx is not None:
                found[key] = idx
                break
    return found


def parse_csv(data: bytes) -> dict:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    head_i, cols = None, {}
    for i, r in enumerate(rows[:40]):
        c = _match_columns(r)
        if "proceeds" in c and ("basis" in c or "gain" in c):
            head_i, cols = i, c
            break
    if head_i is None:
        raise InvestError("CSV_COLUMNS")
    lots, skipped = [], 0
    for r in rows[head_i + 1:]:
        if not any(x.strip() for x in r):
            continue

        def cell(k):
            i = cols.get(k)
            return r[i].strip() if i is not None and i < len(r) else ""

        first = " ".join(r[:2]).lower()
        if "total" in first:
            continue
        proceeds = num(cell("proceeds"))
        basis = num(cell("basis"))
        gain = num(cell("gain"))
        wash = num(cell("wash")) or 0.0
        if proceeds is None or (basis is None and gain is None):
            skipped += 1
            continue
        if basis is None:
            basis = proceeds - gain + abs(wash)
        t = cell("term").lower()
        term = "L" if ("long" in t or t in ("lt", "l")) else "S" if ("short" in t or t in ("st", "s")) else None
        lot = {"desc": cell("desc"), "acquired": cell("acquired"), "sold": cell("sold"), "proceeds": abs(proceeds),
               "basis": abs(basis), "wash": abs(wash), "term": term}
        lot["term"] = _term(lot)
        lots.append(lot)
    if not lots:
        raise InvestError("CSV_EMPTY")
    return {"lots": lots, "div": {}, "int": {}, "warnings": ["CSV_SKIPPED"] * (1 if skipped else 0),
            "skipped": skipped}


def parse_file(data: bytes, file_name: str) -> dict:
    name = (file_name or "").lower()
    head = data[:200].decode("latin-1", "ignore").lstrip()
    if name.endswith(".txf") or head.upper().startswith("V0"):
        return parse_txf(data.decode("latin-1", "ignore"))
    return parse_csv(data)


def lots_year(lots: list[dict], year: int) -> tuple[list[dict], int]:
    """Vendite dell'anno (per data di vendita) e quante sono di altri anni; senza data restano nell'anno scelto."""
    keep, other = [], 0
    for lot in lots:
        d = parse_date(lot.get("sold"))
        if d is not None and d.year != year:
            other += 1
        else:
            keep.append(lot)
    return keep, other


# ---------------------------------------------------------------- archivio
def _ensure() -> None:
    with db.connect() as con:
        con.executescript(SCHEMA)


def save(year: int, kind: str, data: dict, broker: str = "", source: str = "manuale", file_name: str = "") -> int:
    if kind not in KINDS:
        raise InvestError("KIND")
    _ensure()
    with db.connect() as con:
        cur = con.execute("INSERT INTO tax_docs(year, kind, broker, source, file_name, data) VALUES (?,?,?,?,?,?)",
                          (int(year), kind, broker.strip(), source, file_name, json.dumps(data, ensure_ascii=False)))
        return int(cur.lastrowid)


def delete(doc_id: int) -> None:
    _ensure()
    with db.connect() as con:
        con.execute("DELETE FROM tax_docs WHERE id=?", (int(doc_id),))


def docs(year: int | None = None) -> list[dict]:
    _ensure()
    with db.connect() as con:
        q = "SELECT * FROM tax_docs" + (" WHERE year=?" if year is not None else "") + " ORDER BY year DESC, id"
        rows = con.execute(q, (int(year),) if year is not None else ()).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"] or "{}")
        except ValueError:
            d["data"] = {}
        out.append(d)
    return out


# ---------------------------------------------------------------- totali dell'anno
def _f(d: dict, k: str) -> float:
    v = d.get(k)
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def totals(items: list[dict]) -> dict:
    """Somma dei moduli dell'anno. Tutti gli importi in dollari."""
    t = {k: 0.0 for k in ("interest", "us_gov", "tax_exempt", "ordinary_div", "qualified_div", "cg_dist", "st", "lt",
                          "fed_withheld", "foreign_tax", "proceeds")}
    t["n_lots"] = 0
    for doc in items:
        d, kind = doc["data"], doc["kind"]
        if kind == "1099-INT":
            t["interest"] += _f(d, "interest") + _f(d, "us_gov")     # il box 3 è a parte dal box 1, ma tassabile
            t["us_gov"] += _f(d, "us_gov")
            t["tax_exempt"] += _f(d, "tax_exempt")
            t["fed_withheld"] += _f(d, "fed_withheld")
            t["foreign_tax"] += _f(d, "foreign_tax")
        elif kind == "1099-DIV":
            t["ordinary_div"] += _f(d, "ordinary")
            t["qualified_div"] += min(_f(d, "qualified"), _f(d, "ordinary"))
            t["cg_dist"] += _f(d, "cg_dist")
            t["fed_withheld"] += _f(d, "fed_withheld")
            t["foreign_tax"] += _f(d, "foreign_tax")
        elif kind == "1099-B":
            for lot in d.get("lots", []):
                g = lot_gain(lot)
                t["st" if _term(lot) == "S" else "lt"] += g
                t["proceeds"] += _f(lot, "proceeds")
                t["n_lots"] += 1
            s = d.get("summary") or {}
            t["st"] += _f(s, "st_proceeds") - _f(s, "st_basis") + _f(s, "st_wash")
            t["lt"] += _f(s, "lt_proceeds") - _f(s, "lt_basis") + _f(s, "lt_wash")
            t["proceeds"] += _f(s, "st_proceeds") + _f(s, "lt_proceeds")
            t["fed_withheld"] += _f(d, "fed_withheld") + _f(s, "fed_withheld")
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()}


def has_income(t: dict) -> bool:
    return any(abs(t.get(k, 0.0)) > 0.004 for k in ("interest", "ordinary_div", "cg_dist", "st", "lt"))
