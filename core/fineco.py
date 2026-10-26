"""Pulizia delle descrizioni Fineco.

Fineco va a capo nella "Descrizione completa" ogni ~40 caratteri inserendo spazi anche a metà
parola ("ROSS I", "Adde bito"), e aggiunge molto rumore (numero carta, IBAN, TRN...).
Qui si estraggono le parti utili: esercente, ordinante/beneficiario, causale e data reale.
"""
from __future__ import annotations

import re


def fz(word: str) -> str:
    """Regex che tollera spazi spuri tra le lettere: fz('Ben') -> 'B\\s?e\\s?n'."""
    return r"\s?".join(re.escape(c) for c in word if c != " ")


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip(" -:;,")


RE_CARD_TAIL = re.compile(r"\s*Carta\s*N\.?\s*[\*\s\d]*.*$", re.I)
RE_CARD_DATE = re.compile(r"Data\s*operazione:?\s*(\d{2}/\d{2}/\d{2,4})", re.I)
RE_POS_DATE = re.compile(r"Pag\.\s*del\s*(\d{2}/\d{2}/\d{2,4})", re.I)
RE_POS_SHOP = re.compile(r"presso:\s*(.*?)\s*(?:Carta\s*N|$)", re.I)
RE_COUNTRY = re.compile(r"\s+(?:IT|IE|LU|NL|DE|FR|ES|GB|US|BE|AT|CH|SE|DK|PT|ITA)$")

# campi dei bonifici (in due formati: esteso "Ordinante:/Beneficiario:" e breve "Ord:/Ben:")
_STOP_WORDS = ["IBAN", "Iban", "Banca", "Data", "Dt-ord", "Ins:", "Canale", "Causale", "Info-Cli", "TRN"]
_STOP_BEN = "|".join(fz(w) for w in _STOP_WORDS)
_STOP_ORD = "|".join(fz(w) for w in _STOP_WORDS + ["Benefici", "Ben:"])
RE_ORD = re.compile(rf"(?:{fz('Ordinante:')}|{fz('Ord:')})\s*(.*?)\s*(?:{_STOP_ORD}|$)", re.I)
RE_BEN = re.compile(rf"(?:{fz('Beneficiario:')}|{fz('Ben:')})\s*(.*?)\s*(?:{_STOP_BEN}|$)", re.I)
RE_CAUS = re.compile(rf"(?:{fz('Causale:')}|{fz('Info-Cli:')})\s*(.*?)\s*(?:{fz('TRN:')}|$)", re.I)
RE_SDD = re.compile(rf"^(.*?)\s*{fz('Addebito')}\s*{fz('SDD')}.*?(?:{fz('Per')}\s+(.*))?$", re.I)


def real_date(full: str) -> str | None:
    """Data effettiva dell'acquisto (per le carte Fineco la 'data operazione' è quella di contabilizzazione)."""
    for rx in (RE_CARD_DATE, RE_POS_DATE):
        m = rx.search(full or "")
        if m:
            return m.group(1)
    return None


def clean(short: str, full: str) -> str:
    short, full = _squash(short), _squash(full)
    low = short.lower()
    if not full:
        return short
    # pagamenti / accrediti / storni con carta
    if "visa debit" in low or "finecocard" in low or low.startswith("accr.su carta"):
        shop = _squash(RE_CARD_TAIL.sub("", full))
        shop = re.sub(r"^Storno\s*-\s*", "", shop, flags=re.I)
        shop = RE_COUNTRY.sub("", shop)
        if low.startswith("pagamento visa") or low == "visa debit":
            return shop or short
        return f"{short} - {shop}" if shop else short
    if low.startswith("pagamento bancomat"):
        m = RE_POS_SHOP.search(full)
        return _squash(m.group(1)) if m else short
    if low.startswith(("prelievo", "pr.finecocard", "prelevamento")):
        return f"{short} (prelievo contanti)"
    # addebiti diretti SDD: "<creditore> Addebito SDD ... Per <dettaglio>"
    m = RE_SDD.search(full)
    if m:
        creditor = _squash(m.group(1))
        detail = _squash(m.group(2) or "")
        detail = re.sub(r"^\d[\d/]*\s*", "", detail)
        return f"Addebito {creditor}" + (f" - {detail}" if detail and len(detail) < 60 else "")
    # bonifici, stipendi
    if re.search(rf"{fz('Ordinante:')}|{fz('Beneficiario:')}|\b{fz('Ord:')}|\b{fz('Ben:')}", full, re.I):
        ordn = RE_ORD.search(full)
        ben = RE_BEN.search(full)
        caus = RE_CAUS.search(full)
        caus_t = _squash(caus.group(1)) if caus else ""
        if ordn and _squash(ordn.group(1)):
            text = f"{short} da {_squash(ordn.group(1))}"
            if ben and _squash(ben.group(1)):
                text += f" a {_squash(ben.group(1))}"
        elif ben:
            text = f"{short} a {_squash(ben.group(1))}"
        else:
            text = short
        return text + (f" - {caus_t}" if caus_t else "")
    # tutto il resto (dividendi, imposte, canoni...): descrizione breve + completa se aggiunge qualcosa
    if full.lower().replace(" ", "") == low.replace(" ", ""):
        return short
    if full.lower().replace(" ", "").startswith(low.replace(" ", "")):
        return full
    return f"{short} - {full}"


def counterparty(full: str, amount: float) -> str | None:
    """Controparte di un bonifico: beneficiario se in uscita, ordinante se in entrata."""
    m = (RE_BEN if amount < 0 else RE_ORD).search(full or "")
    return _squash(m.group(1)) if m else None


def owner_from_header(raw_rows: list[str]) -> str | None:
    for v in raw_rows:
        m = re.search(r"Intestazione\s+Conto\s+Corrente:\s*(.+)", str(v), re.I)
        if m:
            return _squash(m.group(1))
    return None
