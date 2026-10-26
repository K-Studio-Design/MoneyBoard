"""Buste paga per il calcolo delle tasse USA (funzione in prova, alpha).

Dalla busta paga si ricava il «lordo tassabile USA» del mese, che può essere diverso dall'accredito in banca:
- conta lo stipendio in denaro prima delle trattenute (retribuzione, straordinari, indennità, bonus…);
- contano i benefit tassabili non in denaro (auto, casa, fringe benefit…), anche se in busta sono figurativi;
- non contano gli importi figurativi che servono solo al calcolo italiano (retribuzione convenzionale, quote
  «SOGG.» del distacco…), i rimborsi di imposte e spese, i contributi dell'azienda a fondi sanitari;
- le imposte e i contributi italiani trattenuti vengono mostrati a parte.
Ogni voce ha una proposta che l'utente può cambiare; la scelta viene ricordata per lo stesso codice.

Lettura automatica: buste Zucchetti in PDF (testo, non scansione). Per le altre buste si inseriscono a mano
netto, lordo tassabile e imposte del mese.
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from core import db

MEMORY_KEY = "payslip_classes"   # {codice voce: classe} scelte dall'utente

# classi delle voci: (etichetta, conta nel lordo tassabile USA)
CLASSES = {
    "pay": ("Compenso in denaro (tassabile)", True),
    "benefit": ("Benefit non in denaro (tassabile)", True),
    "benefit_free": ("Benefit non tassabile", False),
    "figurative": ("Figurativo, solo per il calcolo italiano", False),
    "refund": ("Rimborso di imposte o spese", False),
    "tax_it": ("Imposta italiana trattenuta", False),
    "social_it": ("Contributo previdenziale italiano", False),
    "deduction": ("Altra trattenuta", False),
    "info": ("Solo informativa", False),
}
TAXABLE = {k for k, (_l, on) in CLASSES.items() if on}

SCHEMA = """
CREATE TABLE IF NOT EXISTS payslips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,            -- AAAA-MM
    employer TEXT DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'EUR',
    net REAL,                        -- netto del mese
    gross REAL,                      -- totale competenze
    deductions REAL,                 -- totale trattenute
    taxable REAL,                    -- lordo tassabile USA (nella valuta della busta)
    tax_it REAL DEFAULT 0,           -- imposte italiane trattenute (al netto dei rimborsi)
    social_it REAL DEFAULT 0,        -- contributi previdenziali italiani
    tax_us REAL DEFAULT 0,           -- tasse USA già trattenute (buste americane, inserite a mano)
    items TEXT DEFAULT '[]',         -- voci (JSON)
    source TEXT DEFAULT 'manuale',   -- zucchetti | manuale
    file_name TEXT DEFAULT '',
    tx_id INTEGER,                   -- accredito in banca abbinato
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class PayslipError(Exception):
    pass


@dataclass
class Item:
    code: str
    desc: str
    base: str = ""
    ref: str = ""
    ded: float | None = None       # trattenute
    comp: float | None = None      # competenze
    fig: bool = False              # importo tra parentesi (figurativo)
    cls: str = "info"
    auto_cls: str = "info"

    def amount(self) -> float:
        return float(self.comp if self.comp is not None else (self.ded or 0.0))


@dataclass
class Payslip:
    period: str
    employer: str
    currency: str
    net: float | None
    gross: float | None
    deductions: float | None
    items: list[Item] = field(default_factory=list)
    source: str = "zucchetti"
    file_name: str = ""
    warnings: list[str] = field(default_factory=list)

    def taxable(self) -> float:
        return round(sum(i.amount() for i in self.items if i.cls in TAXABLE and i.comp is not None), 2)

    def tax_it(self) -> float:
        tax = sum(i.ded or 0.0 for i in self.items if i.cls == "tax_it" and not i.fig)
        refunded = sum(i.comp or 0.0 for i in self.items if i.cls == "refund" and _is_tax_refund(i) and not i.fig)
        return round(max(0.0, tax - refunded), 2)

    def social_it(self) -> float:
        return round(sum(i.ded or 0.0 for i in self.items if i.cls == "social_it" and not i.fig), 2)


# ---------------------------------------------------------------- numeri e testo
def _num(s: str) -> float | None:
    s = s.strip().replace("€", "").replace(" ", "")
    if not re.fullmatch(r"-?[\d.]*\d(,\d+)?", s):
        return None
    return float(s.replace(".", "").replace(",", "."))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _is_tax_refund(it: Item) -> bool:
    d = _norm(it.desc)
    return any(w in d for w in ("imposta", "irpef", "rec.", "rest."))


# ---------------------------------------------------------------- proposta di classificazione
_BENEFIT_TAX = ("fringe", "benefit", "auto ", "auto az", "alloggio", "abitazione", "casa ", "affitto", "housing",
                "welfare", "buoni", "voucher", "carburante", "stock", "azioni", "school", "scuola")
_BENEFIT_FREE = ("metasalute", "fondo sanit", "fasi", "assistenza sanit", "previdenza compl", "fondo pens", "cometa")
_SOCIAL = ("contributo ivs", "ivs", "inps", "contrib. inps", "fap", "cigs", "contributo fis", "contr.")
_TAX = ("ritenute irpef", "ritenuta irpef", "addizionale", "addiz.", "acconto add", "rata ult.detr", "irpef a debito",
        "imposta sostitutiva", "conguaglio irpef", "ritenuta")
_INFO = ("imponibile", "irpef lorda", "detrazioni", "retribuzione utile", "quota t.f.r", "imp. inail", "ferie godute",
         "smart working", "permessi", "rol ", "ex festiv")
_REFUND = ("rimborso", "rest./rec", "restituzione", "rec. imposta", "rimb.")


def propose(it: Item) -> str:
    d = _norm(it.desc)
    if any(w in d for w in _BENEFIT_FREE):
        return "benefit_free"
    if it.comp is not None and any(w in d for w in _BENEFIT_TAX):
        return "benefit"            # anche se figurativo: per gli USA il benefit in natura è reddito
    if it.fig:
        return "figurative"
    if it.comp is not None:
        if any(w in d for w in _REFUND):
            return "refund"
        return "pay"
    if it.ded is not None:
        if any(w in d for w in _TAX):
            return "tax_it"
        if any(w in d for w in _SOCIAL):
            return "social_it"
        return "deduction"
    return "info"


def memory() -> dict[str, str]:
    try:
        m = json.loads(db.get_setting(MEMORY_KEY) or "{}")
        return {str(k): v for k, v in m.items() if v in CLASSES}
    except ValueError:
        return {}


def remember(items: list[Item]) -> None:
    """Ricorda le classi scelte a mano (diverse dalla proposta) per lo stesso codice nelle buste successive."""
    m = memory()
    for it in items:
        if it.cls != it.auto_cls:
            m[it.code] = it.cls
        elif it.code in m:
            m.pop(it.code)
    db.set_setting(MEMORY_KEY, json.dumps(m))


def classify(items: list[Item]) -> None:
    mem = memory()
    for it in items:
        it.auto_cls = propose(it)
        it.cls = mem.get(it.code, it.auto_cls)


# ---------------------------------------------------------------- lettura Zucchetti
MONTHS_IT = {m: i for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                          "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1)}
_CODE = re.compile(r"^([A-Z0-9]{6})\s*(.*)$")


def _lines(page) -> list[list[dict]]:
    """Caratteri raggruppati in righe (tolleranza verticale di 3 punti: alcune voci hanno codice e descrizione
    su righe sfasate di 1-2 punti)."""
    chars = [c for c in page.chars if c["text"].strip() and c["x0"] >= 30]
    chars.sort(key=lambda c: (c["top"], c["x0"]))
    rows, cur, last = [], [], None
    for c in chars:
        if last is not None and c["top"] - last > 3:
            rows.append(cur)
            cur = []
        cur.append(c)
        last = c["top"] if last is None or c["top"] - last > 3 else last
    if cur:
        rows.append(cur)
    return rows


def _text(chars: list[dict]) -> str:
    out, prev = "", None
    for c in sorted(chars, key=lambda c: c["x0"]):
        if prev is not None and c["x0"] - prev > 1.5:
            out += " "
        out += c["text"]
        prev = c["x1"]
    return out.strip()


def _columns(header: list[dict]) -> dict[str, float] | None:
    """Posizioni delle colonne dall'intestazione «VOCI VARIABILI … IMPORTO BASE RIFERIMENTO TRATTENUTE COMPETENZE»."""
    words, cur, prev = [], [], None
    for c in sorted(header, key=lambda c: c["x0"]):
        if prev is not None and c["x0"] - prev > 4:
            words.append(cur)
            cur = []
        cur.append(c)
        prev = c["x1"]
    if cur:
        words.append(cur)
    pos = {}
    for w in words:
        txt = "".join(c["text"] for c in w).upper()
        if "IMPORTO" in txt:
            pos["base"] = w[0]["x0"]
        elif "RIFERIMENTO" in txt:
            pos["ref"] = w[0]["x0"]
        elif "TRATTENUTE" in txt:
            pos["ded"] = w[0]["x0"]
        elif "COMPETENZE" in txt:
            pos["comp"] = w[0]["x0"]
    return pos if len(pos) == 4 else None


def _split(row: list[dict], pos: dict[str, float]) -> dict[str, str]:
    """Divide una riga nelle colonne: descrizione | importo base | riferimento | trattenute | competenze.
    Confini a metà tra l'inizio dei titoli (gli importi sono allineati a destra sotto il titolo)."""
    b_desc = pos["base"] - 25
    b_ref = pos["ref"] - 32
    b_ded = pos["ded"] - 20
    b_comp = pos["comp"] - 20
    cols = {"desc": [], "base": [], "ref": [], "ded": [], "comp": []}
    for c in row:
        x = c["x0"]
        k = ("desc" if x < b_desc else "base" if x < b_ref else "ref" if x < b_ded else "ded" if x < b_comp
             else "comp")
        cols[k].append(c)
    return {k: _text(v) for k, v in cols.items()}


def _money_cell(s: str) -> tuple[float | None, bool]:
    s = s.strip()
    fig = s.startswith("(") or s.endswith(")")
    v = _num(s.strip("() "))
    return v, fig


_LABELS = {"gross": re.compile(r"TOTALE\s?S?COMPETENZE"), "ded": re.compile(r"TOTALE\s?S?TRATTENUTE"),
           "net": re.compile(r"NETTO\s?S?DEL\s?S?MESE")}
_MONEY = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)")


def _totals(rows: list[list[dict]], found: dict[str, float]) -> None:
    """Totali della busta (competenze, trattenute, netto): l'importo è sulla stessa riga dell'etichetta, a
    destra, oppure nella riga subito sotto."""
    for i, r in enumerate(rows):
        t = _text(r).upper()
        for name, rx in _LABELS.items():
            m = rx.search(t)
            if not m:
                continue
            after = _MONEY.findall(t[m.end():])
            if not after and i + 1 < len(rows):
                after = _MONEY.findall(_text(rows[i + 1]))
            if after:
                found[name] = _num(after[-1] if name != "net" else after[0])


def _meta(reader_meta: dict) -> dict[str, str]:
    kw = str(reader_meta.get("Keywords") or reader_meta.get("/Keywords") or "")
    out = {}
    for part in kw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().upper()] = v.strip()
    return out


def parse_pdf(data: bytes, file_name: str = "") -> Payslip:
    try:
        import pdfplumber
    except ImportError as e:   # pacchetto mancante: si installa al prossimo avvio con avvia_app.bat
        raise PayslipError("PDF_LIB") from e
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:
        raise PayslipError("PDF_READ") from e
    with pdf:
        meta = _meta(pdf.metadata or {})
        full = "\n".join((p.extract_text() or "") for p in pdf.pages)
        if not full.strip():
            raise PayslipError("PDF_SCAN")
        items: list[Item] = []
        found: dict[str, float] = {}
        for page in pdf.pages:
            rows = _lines(page)
            _totals(rows, found)
            pos, start = None, None
            for i, r in enumerate(rows):
                t = _text(r).upper()
                if "TRATTENUTE" in t and "COMPETENZE" in t and "RIFERIMENTO" in t:
                    pos, start = _columns(r), i + 1
                    break
            if not pos:
                continue
            for r in rows[start:]:
                cells = _split(r, pos)
                if cells["desc"].upper().startswith("CONGUAGLIO") or "CONGUAGLIO" in _text(r).upper():
                    break
                desc = cells["desc"].lstrip("* ").strip()
                m = _CODE.match(desc)
                if not m:
                    continue
                code, text = m.group(1), m.group(2).strip()
                if not re.search(r"\d", code) or not text:
                    continue
                ded, fig_d = _money_cell(cells["ded"])
                comp, fig_c = _money_cell(cells["comp"])
                items.append(Item(code=code, desc=text, base=cells["base"], ref=cells["ref"], ded=ded, comp=comp,
                                  fig=(fig_d and ded is not None) or (fig_c and comp is not None)))
    if not items:
        raise PayslipError("PDF_FORMAT")
    # periodo, totali, azienda
    period = None
    if meta.get("ANNO") and meta.get("MESE"):
        period = f"{int(meta['ANNO']):04d}-{int(meta['MESE']):02d}"
    else:
        m = re.search(r"(" + "|".join(MONTHS_IT) + r")\s+(\d{4})", full, re.I)
        if m:
            period = f"{int(m.group(2)):04d}-{MONTHS_IT[m.group(1).lower()]:02d}"
    if not period:
        raise PayslipError("PDF_PERIOD")

    def total(key: str, name: str) -> float | None:
        if meta.get(key):
            try:
                return float(meta[key])
            except ValueError:
                pass
        return found.get(name)

    gross = total("TOTCOMPET", "gross")
    net = total("IMPNETTO", "net")
    deductions = found.get("ded")
    p = Payslip(period=period, employer=meta.get("DENAZI", ""), currency="EUR", net=net, gross=gross,
                deductions=deductions, items=items, source="zucchetti", file_name=file_name)
    classify(p.items)
    # controlli: le voci lette devono tornare con i totali della busta
    comp_sum = round(sum(i.comp for i in items if i.comp is not None and not i.fig), 2)
    ded_sum = round(sum(i.ded for i in items if i.ded is not None and not i.fig), 2)
    if gross is not None and abs(comp_sum - gross) > 0.05:
        p.warnings.append(f"COMP:{comp_sum:.2f}:{gross:.2f}")
    if deductions is not None and abs(ded_sum - deductions) > 0.05:
        p.warnings.append(f"DED:{ded_sum:.2f}:{deductions:.2f}")
    return p


# ---------------------------------------------------------------- archivio
def _ensure() -> None:
    with db.connect() as con:
        con.executescript(SCHEMA)


def save(p: Payslip, tx_id: int | None, payslip_id: int | None = None, tax_us: float = 0.0,
         taxable: float | None = None) -> int:
    _ensure()
    items = json.dumps([i.__dict__ for i in p.items], ensure_ascii=False)
    vals = dict(period=p.period, employer=p.employer, currency=p.currency, net=p.net, gross=p.gross,
                deductions=p.deductions, taxable=p.taxable() if taxable is None else float(taxable),
                tax_it=p.tax_it(), social_it=p.social_it(), tax_us=float(tax_us or 0), items=items, source=p.source,
                file_name=p.file_name, tx_id=tx_id)
    with db.connect() as con:
        if payslip_id is None:
            cur = con.execute(f"INSERT INTO payslips({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                              tuple(vals.values()))
            return int(cur.lastrowid)
        con.execute(f"UPDATE payslips SET {', '.join(k + '=?' for k in vals)} WHERE id=?",
                    (*vals.values(), payslip_id))
        return payslip_id


def delete(payslip_id: int) -> None:
    _ensure()
    with db.connect() as con:
        con.execute("DELETE FROM payslips WHERE id=?", (payslip_id,))


def all_df() -> pd.DataFrame:
    _ensure()
    with db.connect() as con:
        return pd.read_sql_query("SELECT * FROM payslips ORDER BY period DESC, id DESC", con)


def load(payslip_id: int) -> tuple[Payslip, dict]:
    df = all_df()
    r = df[df["id"] == payslip_id]
    if r.empty:
        raise PayslipError("NOT_FOUND")
    row = r.iloc[0].to_dict()
    items = [Item(**{k: v for k, v in d.items() if k in Item.__dataclass_fields__})
             for d in json.loads(row["items"] or "[]")]
    p = Payslip(period=row["period"], employer=row["employer"] or "", currency=row["currency"], net=row["net"],
                gross=row["gross"], deductions=row["deductions"], items=items, source=row["source"],
                file_name=row["file_name"] or "")
    return p, row


def manual(period: str, currency: str, net: float, taxable: float, tax_it: float, tax_us: float,
           employer: str = "") -> Payslip:
    """Busta inserita a mano (formato non letto in automatico, oppure busta americana)."""
    items = [Item(code="MANUALE", desc="Lordo tassabile", comp=float(taxable), cls="pay", auto_cls="pay")]
    if tax_it:
        items.append(Item(code="MAN_IT", desc="Imposte italiane", ded=float(tax_it), cls="tax_it", auto_cls="tax_it"))
    return Payslip(period=period, employer=employer, currency=currency, net=net, gross=taxable, deductions=None,
                   items=items, source="manuale")


def match_tx(tx: pd.DataFrame, period: str, net: float | None, currency: str,
             exclude: set[int] | None = None) -> int | None:
    """Accredito in banca dello stesso importo netto, entro il mese della busta o il mese dopo."""
    if net is None or tx.empty:
        return None
    y, m = (int(x) for x in period.split("-"))
    start = pd.Timestamp(date(y, m, 1)) - pd.Timedelta(days=5)
    end = (pd.Timestamp(date(y, m, 1)) + pd.offsets.MonthEnd(2))
    c = tx[(tx["amount"] > 0) & (tx["currency"].str.upper() == currency.upper())
           & ((tx["amount"] - float(net)).abs() < 0.015) & (tx["date"] >= start) & (tx["date"] <= end)]
    if exclude:
        c = c[~c["id"].isin(list(exclude))]
    if c.empty:
        return None
    return int(c.sort_values("date").iloc[0]["id"])


def linked() -> dict[int, dict]:
    """{id del movimento: busta} per le buste abbinate a un accredito."""
    df = all_df()
    out = {}
    for r in df.itertuples():
        if r.tx_id is not None and not pd.isna(r.tx_id):
            out[int(r.tx_id)] = {"id": int(r.id), "period": r.period, "taxable": float(r.taxable or 0),
                                 "currency": r.currency, "tax_it": float(r.tax_it or 0),
                                 "social_it": float(r.social_it or 0), "tax_us": float(r.tax_us or 0)}
    return out
