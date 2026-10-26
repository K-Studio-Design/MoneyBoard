"""Import degli estratti conto esportati da Fineco, Revolut o da un CSV/Excel generico."""
from __future__ import annotations

import io
import re

import pandas as pd

from core import db, i18n
from core.categorize import Categorizer


def _clean(col) -> str:
    return re.sub(r"[\s_]+", " ", str(col)).strip().lower()


def read_any(file_bytes: bytes, filename: str, header=0) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        return pd.read_excel(io.BytesIO(file_bytes), header=header, engine="openpyxl")
    if name.endswith(".xls"):
        try:
            return pd.read_excel(io.BytesIO(file_bytes), header=header, engine="xlrd")
        except Exception:
            # alcune banche esportano un HTML con estensione .xls
            return pd.read_html(io.BytesIO(file_bytes), header=header)[0]
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.splitlines()[0] if text else ""
    sep = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
    return pd.read_csv(io.StringIO(text), sep=sep, header=header)


def parse_number(v) -> float | None:
    """Accetta 1.234,56 / 1,234.56 / -12,5 / '€ 3,00' / numeri già numerici."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("€", "").replace("EUR", "").replace("\xa0", "").replace(" ", "")
    if s in ("", "-", "nan", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def parse_date(v, dayfirst=True):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat()
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        d = pd.to_datetime(s[:19], errors="coerce")
    else:
        d = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)
    return None if pd.isna(d) else d.date().isoformat()


def _finalize(rows: list[dict], account: str, source: str, base: str) -> list[dict]:
    """Categorizza, converte in valuta base e crea un id univoco anti-duplicati."""
    from core import fx

    cat = Categorizer()
    seen: dict[str, int] = {}
    for r in rows:
        key = f"{source}|{account}|{r['date']}|{r['description']}|{r['amount']:.2f}|{r['currency']}|{r.get('_extra', '')}"
        n = seen.get(key, 0)
        seen[key] = n + 1
        r["external_id"] = r.get("external_id") or db.make_external_id(key, n)
        forced = r.pop("_force_category", None)
        guessed = cat.categorize(r["description"], r["amount"], r.pop("_bank_category", None),
                                 r.pop("_counterparty", None), r.pop("_reversal", False))
        r["category"] = forced if forced in cat.kind else guessed
        r.pop("_extra", None)
        r["category_locked"] = 0
        r["account"] = account
        r["source"] = source
        r.setdefault("notes", "")
    return fx.to_base_rows(rows, base)


# ---------------------------------------------------------------- Fineco
def _find_header_row(raw: pd.DataFrame) -> int | None:
    for i in range(min(len(raw), 40)):
        vals = [_clean(v) for v in raw.iloc[i].tolist()]
        joined = " | ".join(vals)
        if "data" in joined and ("entrate" in joined or "uscite" in joined or "importo" in joined):
            return i
    return None


def parse_fineco(file_bytes: bytes, filename: str, include_pending: bool = False) -> pd.DataFrame:
    """Export 'Movimenti' del conto Fineco (xlsx/xls/csv). Colonne tipiche:
    Data_Operazione | Data_Valuta | Entrate | Uscite | Descrizione | Descrizione_Completa | Stato | Moneymap
    L'intestatario letto dall'intestazione del file è in df.attrs['owner']."""
    from core import fineco

    raw = read_any(file_bytes, filename, header=None)
    h = _find_header_row(raw)
    if h is None:
        raise ValueError(i18n.t("Non trovo l'intestazione del file Fineco (colonne Data / Entrate / Uscite)."))
    owner = fineco.owner_from_header(raw.iloc[:h, 0].tolist())
    df = raw.iloc[h + 1:].copy()
    df.columns = [_clean(c) for c in raw.iloc[h].tolist()]
    df = df.dropna(how="all")

    def col(*names):
        for n in names:
            for c in df.columns:
                if c == n:
                    return c
        for n in names:
            for c in df.columns:
                if n in c:
                    return c
        return None

    c_date = col("data operazione", "data contabile", "data")
    if not c_date:
        raise ValueError(i18n.t("Colonna data non trovata nel file Fineco."))
    c_val = col("data valuta")
    c_in, c_out, c_amt = col("entrate"), col("uscite"), col("importo")
    c_full = col("descrizione completa")
    c_short = col("descrizione")
    c_cat = col("moneymap", "categoria")
    c_state = col("stato")
    c_ccy = col("divisa")

    def text(c):
        return df[c].fillna("").astype(str) if c else pd.Series("", index=df.index)

    out = pd.DataFrame(index=df.index)
    if c_in or c_out:
        ins = df[c_in].map(parse_number).fillna(0).abs() if c_in else 0
        outs = df[c_out].map(parse_number).fillna(0).abs() if c_out else 0
        out["amount"] = ins - outs
    else:
        out["amount"] = df[c_amt].map(parse_number)
    short, full = text(c_short), text(c_full)
    if c_short == c_full:
        short = full
    out["description"] = [fineco.clean(a, b) for a, b in zip(short, full)]
    # carta usata (ultime cifre) e tipo: «Pagamento Visa Debit» + «... Carta N. ***** 123 ...»
    from core import cards
    found = [cards.detect(f"{a} {b}") for a, b in zip(short, full)]
    out["card"] = [d for d, _k in found]
    out["card_kind"] = [k for _d, k in found]
    # data: quella reale dell'acquisto se presente nel testo, altrimenti data operazione, poi data valuta
    d_real = full.map(lambda t: parse_date(fineco.real_date(t)) if fineco.real_date(t) else None)
    d_op = df[c_date].map(parse_date)
    d_val = df[c_val].map(parse_date) if c_val else pd.Series(None, index=df.index)
    out["date"] = d_real.where(d_real.notna(), d_op.where(d_op.notna(), d_val))
    out["currency"] = text(c_ccy).str.upper().str[:3].replace("", "EUR") if c_ccy else "EUR"
    out["bank_category"] = text(c_cat).replace("nan", "")
    out["state"] = text(c_state)
    is_transfer = short.str.lower().str.contains("bonific|stipendio|giroconto|sepa italia|sepa estero", regex=True)
    out["counterparty"] = [fineco.counterparty(f, a) if t else None
                           for f, a, t in zip(full, out["amount"].fillna(0), is_transfer)]
    if not include_pending and c_state:
        pend = out["state"].str.lower().str.contains("autorizz|non contab|in corso|sospes", regex=True)
        out = out[~pend]
    out = out.dropna(subset=["date", "amount"])
    out = out[out["amount"] != 0].reset_index(drop=True)
    out.attrs["owner"] = owner
    return out


# ---------------------------------------------------------------- Revolut
REVOLUT_ALIASES = {
    "type": ["type", "tipo"],
    "product": ["product", "prodotto"],
    "started": ["started date", "data di inizio", "data inizio"],
    "completed": ["completed date", "data di completamento", "data completamento"],
    "description": ["description", "descrizione"],
    "amount": ["amount", "importo"],
    "fee": ["fee", "costo", "commissione", "commissioni"],
    "currency": ["currency", "valuta"],
    "state": ["state", "stato"],
}
# controparte nelle descrizioni Revolut (inglese e italiano)
RE_REV_PARTY = re.compile(
    r"^(?:pagamento a favore di|pagamento da parte di|pagamento da|transfer to|transfer from|payment from|"
    r"to|from|bonifico a|bonifico da|a|da)\s+(.+)$", re.I)
REVOLUT_NEUTRAL_TYPES = ["topup", "top-up", "ricarica", "exchange", "cambio", "transfer between", "trasferimento tra"]
REVOLUT_BAD_STATES = ["revert", "declin", "fail", "annull", "rifiut", "stornat", "respint"]


def parse_revolut(file_bytes: bytes, filename: str, include_pending: bool = False) -> pd.DataFrame:
    df = read_any(file_bytes, filename)
    cols = {_clean(c): c for c in df.columns}

    def col(key):
        for alias in REVOLUT_ALIASES[key]:
            if alias in cols:
                return cols[alias]
        return None

    c = {k: col(k) for k in REVOLUT_ALIASES}
    missing = [k for k in ("amount", "currency", "description") if not c[k]]
    if missing or not (c["started"] or c["completed"]):
        raise ValueError(i18n.t("Non sembra un estratto Revolut: colonne mancanti {cols}.", cols=missing or ["data"]))
    out = pd.DataFrame()
    date_col = c["completed"] or c["started"]
    out["date"] = df[date_col].where(df[date_col].notna(), df[c["started"]] if c["started"] else None).map(
        lambda v: parse_date(v, dayfirst=False if re.match(r"^\d{4}-", str(v)) else True))
    amount = df[c["amount"]].map(parse_number).fillna(0)
    fee = df[c["fee"]].map(parse_number).fillna(0) if c["fee"] else 0
    out["amount"] = amount - fee
    out["description"] = df[c["description"]].fillna("").astype(str).str.strip()
    out["currency"] = df[c["currency"]].fillna("EUR").astype(str).str.upper().str.strip()
    out["type"] = df[c["type"]].fillna("").astype(str) if c["type"] else ""
    out["product"] = df[c["product"]].fillna("").astype(str) if c["product"] else ""
    out["state"] = df[c["state"]].fillna("").astype(str) if c["state"] else ""
    st = out["state"].str.lower()
    bad = st.apply(lambda s: any(b in s for b in REVOLUT_BAD_STATES))
    pending = st.str.contains("pend|in sospeso|in attesa", regex=True)
    out = out[~bad & (include_pending | ~pending)]
    out = out.dropna(subset=["date"])
    out = out[out["amount"] != 0]
    return out.reset_index(drop=True)


def revolut_rows(df: pd.DataFrame, account: str = "Revolut") -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        t = str(r.get("type", "")).lower()
        product = str(r.get("product", ""))
        bank_cat = ""
        if any(k in t for k in REVOLUT_NEUTRAL_TYPES) or product.lower() in ("savings", "risparmi", "deposit"):
            bank_cat = "giroconto"
        elif "atm" in t or "preliev" in t:
            bank_cat = "prelievo contanti"
        elif t == "fee" or "commission" in t:
            bank_cat = "commissioni"
        elif "refund" in t or "rimbors" in t:
            bank_cat = "rimborsi"
        desc = r["description"]
        m = RE_REV_PARTY.match(desc.strip())
        rows.append({
            "date": r["date"], "description": desc, "amount": float(r["amount"]),
            "currency": r["currency"], "_bank_category": bank_cat,
            "_counterparty": m.group(1) if m else None,
            "_extra": f"{r.get('type', '')}|{product}",
        })
    return rows


# ---------------------------------------------------------------- generico
def parse_revolut_any(file_bytes: bytes, filename: str, include_pending: bool = False) -> tuple[str, pd.DataFrame]:
    """Riconosce il tipo di export Revolut: ('consolidato', df) oppure ('csv', df)."""
    from core import revolut_consolidated as rc

    if filename.lower().endswith((".xlsx", ".xlsm")):
        raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl", nrows=60)
        if rc.is_consolidated(raw):
            return "consolidato", rc.parse(file_bytes, filename)
    return "csv", parse_revolut(file_bytes, filename, include_pending)


# categoria Revolut -> suggerimento per il categorizzatore
REV_CONSOLIDATED_HINTS = {"ricarica": "giroconto", "cambio valuta": "giroconto", "interessi": "interessi"}


def revolut_consolidated_rows(df: pd.DataFrame, account: str = "Revolut") -> list[dict]:
    """Righe dall'estratto consolidato. Gli interessi giornalieri del conto deposito vengono
    raggruppati per mese. Per i conti in valuta estera si usa il controvalore EUR indicato da Revolut."""
    rows = []
    dep = df[df["section"] == "Conto deposito"]
    cur = df[df["section"] != "Conto deposito"]
    for _, r in cur.iterrows():
        desc = str(r["description"]).strip()
        m = RE_REV_PARTY.match(desc)
        fee = float(r.get("fees") or 0)
        rows.append({
            "date": r["date"], "description": desc, "amount": float(r["amount"]), "currency": r["currency"],
            "_bank_category": REV_CONSOLIDATED_HINTS.get(str(r["bank_category"]).strip().lower(), ""),
            "_counterparty": m.group(1) if m else None,
            "_amount_eur": None if pd.isna(r["amount_eur"]) else float(r["amount_eur"]),
            "_extra": r["section"],
            "notes": f"di cui costi Revolut: {fee:.2f} {r['currency']}" if fee else "",
        })
    if not dep.empty:
        dep = dep.copy()
        dep["mese"] = dep["date"].str[:7]
        for mese, g in dep.groupby("mese"):
            y, mo = mese.split("-")
            rows.append({
                "date": g["date"].max(), "description": f"Interessi netti conto deposito Revolut {mo}/{y}",
                "amount": round(float(g["amount"].sum()), 2), "currency": g["currency"].iloc[0],
                "_bank_category": "interessi", "_counterparty": None, "_force_category": "Interessi e dividendi",
                "_amount_eur": round(float(g["amount_eur"].sum()), 2) if g["amount_eur"].notna().all() else None,
                "_extra": "Conto deposito", "notes": f"{len(g)} accrediti giornalieri",
            })
    return rows


def generic_rows(df: pd.DataFrame, c_date, c_desc, c_amount=None, c_in=None, c_out=None,
                 c_ccy=None, fixed_ccy="EUR", dayfirst=True, invert_sign=False) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        d = parse_date(r[c_date], dayfirst=dayfirst)
        if not d:
            continue
        if c_amount:
            a = parse_number(r[c_amount])
        else:
            i = parse_number(r[c_in]) if c_in else None
            o = parse_number(r[c_out]) if c_out else None
            a = abs(i or 0) - abs(o or 0)
        if a is None or a == 0:
            continue
        if invert_sign:
            a = -a
        ccy = str(r[c_ccy]).upper().strip()[:3] if c_ccy and pd.notna(r[c_ccy]) else fixed_ccy
        rows.append({"date": d, "description": str(r[c_desc]) if pd.notna(r[c_desc]) else "", "amount": float(a),
                     "currency": ccy})
    return rows


def fineco_rows(df: pd.DataFrame) -> list[dict]:
    return [{"date": r["date"], "description": r["description"], "amount": float(r["amount"]),
             "currency": r["currency"] or "EUR", "_bank_category": r.get("bank_category", ""),
             "_counterparty": r.get("counterparty"),
             "card": (r.get("card") or None) if isinstance(r.get("card"), str) else None,
             "_card_kind": r.get("card_kind") or ""}
            for _, r in df.iterrows()]


def finalize(rows: list[dict], account: str, source: str) -> list[dict]:
    return _finalize(rows, account, source, db.base_currency())
