"""Formati standard degli estratti conto, offerti da moltissime banche oltre al CSV/Excel:

- OFX / QFX («Microsoft Money» / «Quicken»): banche USA, UK, Francia, Canada…
- QIF («Quicken»): formato testuale più vecchio, ancora offerto da molte banche europee.
- CAMT.053 / CAMT.052 / CAMT.054 (ISO 20022, XML): standard SEPA, offerto da banche tedesche, olandesi,
  svizzere, austriache… Anche come ZIP con più file XML dentro.
- MT940 (SWIFT): formato testuale molto diffuso in Germania, Olanda, Svizzera, Polonia.

Ogni lettore ritorna le righe nel formato usato dagli import dell'app:
{date: 'AAAA-MM-GG', description, amount (negativo = uscita), currency, _bank_category, _counterparty, _extra}.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from core import i18n

RE_PAYMENT = re.compile(r"payment|thank you|autopay|pagamento ricevuto|zahlung erhalten", re.I)


def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ---------------------------------------------------------------- riconoscimento
def detect(data: bytes, filename: str) -> str | None:
    """'ofx', 'qif', 'camt', 'mt940' oppure None (file a tabella: CSV/Excel)."""
    name = filename.lower()
    if name.endswith(".zip") or data[:4] == b"PK\x03\x04":
        if name.endswith((".xlsx", ".xlsm")):
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if any(n.lower().endswith(".xml") for n in z.namelist()):
                    return "camt"
        except zipfile.BadZipFile:
            return None
        return None
    head = _text(data[:6000])
    up = head.upper()
    if name.endswith((".ofx", ".qfx")) or "<OFX>" in up or "OFXHEADER" in up:
        return "ofx"
    if name.endswith(".qif") or re.match(r"\s*!(TYPE|ACCOUNT|OPTION)", up):
        return "qif"
    if "<DOCUMENT" in up and re.search(r"camt\.05[234]", head, re.I):
        return "camt"
    if re.search(r"^:20:", head, re.M) and (re.search(r"^:61:", head, re.M) or re.search(r"^:60[FM]:", head, re.M)):
        return "mt940"
    return None


def parse(data: bytes, filename: str, dayfirst: bool = True) -> tuple[str, list[dict]]:
    """(formato, righe) per un file in formato standard; ValueError se il formato non è riconosciuto."""
    kind = detect(data, filename)
    if kind == "ofx":
        from core import chase
        rows, _ccy, acc_kind = chase.parse_ofx(data)
        for r in rows:  # i movimenti delle carte: il pagamento della carta dal conto è un giroconto
            if acc_kind == "card" and r["amount"] > 0 and RE_PAYMENT.search(r["description"]):
                r["_bank_category"] = "giroconto"
        return "OFX/QFX", rows
    if kind == "qif":
        return "QIF", parse_qif(data, dayfirst)
    if kind == "camt":
        return "CAMT (ISO 20022)", parse_camt(data)
    if kind == "mt940":
        return "MT940", parse_mt940(data)
    raise ValueError(i18n.t("formato non riconosciuto"))


# ---------------------------------------------------------------- QIF
def _qif_date(s: str, dayfirst: bool) -> str | None:
    """Date QIF: 01/15/2024, 15/01/2024, 1/15'24, 15.01.2024, 2024-01-15."""
    s = s.strip().replace("'", "/").replace(" ", "")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", s)
        if not m:
            return None
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if "." in s:
            d, mo = a, b
        elif a > 12:
            d, mo = a, b
        elif b > 12:
            mo, d = a, b
        else:
            d, mo = (a, b) if dayfirst else (b, a)
        if y < 100:
            y += 2000 if y < 70 else 1900
    try:
        from datetime import date
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_qif(data: bytes, dayfirst: bool = True) -> list[dict]:
    text = _text(data)
    rows: list[dict] = []
    raw_dates: list[str] = []
    cur: dict = {}
    skip_section = False
    blocks: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("!"):
            low = line.lower()
            # sezioni con movimenti: Bank, Cash, CCard, Oth A/L; le altre (Invst, Cat, Class, Memorized) no
            skip_section = low.startswith("!type:") and not any(
                k in low for k in ("bank", "cash", "ccard", "oth a", "oth l"))
            continue
        code, val = line[0], line[1:].strip()
        if code == "^":
            if cur and not skip_section:
                blocks.append(cur)
            cur = {}
            continue
        if code == "D":
            cur["D"] = val
        elif code in ("T", "U") and "T" not in cur:
            cur["T"] = val
        elif code in ("P", "M", "N", "L"):
            cur[code] = val
    if cur and not skip_section:
        blocks.append(cur)
    # ordine giorno/mese: se qualche data lo rivela, vale per tutto il file
    for b in blocks:
        raw_dates.append(b.get("D", ""))
    order = _infer_dayfirst(raw_dates, dayfirst)
    for b in blocks:
        d = _qif_date(b.get("D", ""), order)
        a = _num(b.get("T"))
        if not d or a is None or a == 0:
            continue
        payee, memo = _clean(b.get("P", "")), _clean(b.get("M", ""))
        desc = payee + (f" · {memo}" if memo and memo.lower() not in payee.lower() else "")
        cat = b.get("L", "")
        rows.append({"date": d, "description": desc or memo or "-", "amount": a, "currency": "",
                     "_bank_category": "giroconto" if cat.startswith("[") else cat.lower(),
                     "_counterparty": payee or None, "_extra": b.get("N", "")})
    return rows


def _infer_dayfirst(values: list[str], default: bool) -> bool:
    for v in values:
        m = re.match(r"\s*(\d{1,2})[/'\-](\d{1,2})[/'\-]", str(v))
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                return True
            if b > 12:
                return False
    return default


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(" ", "").replace("\xa0", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        # 1,234 / 12,345,678 = migliaia (stile USA); altrimenti la virgola è il separatore decimale
        s = s.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- CAMT (ISO 20022)
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el, path: str):
    """Come el.find ma ignorando i namespace: path con nomi locali separati da '/'."""
    cur = [el]
    for part in path.split("/"):
        nxt = []
        for c in cur:
            nxt.extend(ch for ch in c if _local(ch.tag) == part)
        if not nxt:
            return None
        cur = nxt
    return cur[0]


def _findall(el, path: str) -> list:
    cur = [el]
    for part in path.split("/"):
        nxt = []
        for c in cur:
            nxt.extend(ch for ch in c if _local(ch.tag) == part)
        cur = nxt
    return cur


def _txt(el, path: str) -> str:
    e = _find(el, path)
    return (e.text or "").strip() if e is not None and e.text else ""


def _camt_files(data: bytes) -> list[bytes]:
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return [z.read(n) for n in sorted(z.namelist()) if n.lower().endswith(".xml")]
    return [data]


def parse_camt(data: bytes) -> list[dict]:
    rows: list[dict] = []
    for xml in _camt_files(data):
        root = ET.fromstring(xml)
        for stmt in [e for e in root.iter() if _local(e.tag) in ("Stmt", "Rpt", "Ntfctn")]:
            acc_ccy = _txt(stmt, "Acct/Ccy")
            for n in _findall(stmt, "Ntry"):
                status = _txt(n, "Sts/Cd") or _txt(n, "Sts")
                if status and status.upper() not in ("BOOK",):
                    continue  # in attesa (PDNG) o informativo (INFO): non ancora contabilizzato
                amt_el = _find(n, "Amt")
                if amt_el is None or not (amt_el.text or "").strip():
                    continue
                try:
                    a = float(amt_el.text.strip())
                except ValueError:
                    continue
                if _txt(n, "CdtDbtInd").upper() == "DBIT":
                    a = -a
                if _txt(n, "RvslInd").lower() == "true":
                    a = -a  # storno: segno opposto all'indicatore
                ccy = amt_el.get("Ccy") or acc_ccy or ""
                d = (_txt(n, "BookgDt/Dt") or _txt(n, "BookgDt/DtTm") or _txt(n, "ValDt/Dt")
                     or _txt(n, "ValDt/DtTm"))[:10]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or a == 0:
                    continue
                txs = _findall(n, "NtryDtls/TxDtls")
                tx = txs[0] if len(txs) == 1 else None
                party = ""
                info = []
                if tx is not None:
                    side = "Cdtr" if a < 0 else "Dbtr"
                    party = (_txt(tx, f"RltdPties/{side}/Nm") or _txt(tx, f"RltdPties/{side}/Pty/Nm")
                             or _txt(tx, f"RltdPties/Ultmt{side}/Nm"))
                    info += [e.text.strip() for e in _findall(tx, "RmtInf/Ustrd") if e.text and e.text.strip()]
                    info += [_txt(tx, "AddtlTxInf")]
                info += [_txt(n, "AddtlNtryInf")]
                info = [i for i in dict.fromkeys(_clean(i) for i in info) if i]
                desc = " · ".join(([party] if party else []) + info) or "-"
                if len(txs) > 1:
                    desc += " " + i18n.t("({n} operazioni)", n=len(txs))
                code = _txt(n, "BkTxCd/Domn/Fmly/SubFmlyCd").upper()
                hint = ""
                if code in ("CWDL", "ATM"):
                    hint = "prelievo contanti"
                elif code in ("CHRG", "FEES", "COMM"):
                    hint = "commissioni"
                elif code in ("INTR",):
                    hint = "interessi"
                ref = _txt(n, "AcctSvcrRef") or _txt(n, "NtryRef") or (_txt(tx, "Refs/EndToEndId") if tx is not None else "")
                rows.append({"date": d, "description": desc, "amount": round(a, 2), "currency": ccy.upper(),
                             "_bank_category": hint, "_counterparty": party or None, "_extra": ref})
    return rows


# ---------------------------------------------------------------- MT940
RE_61 = re.compile(r"^(\d{6})(\d{4})?(R?[CD])([A-Z])?([\d,\.]+)(.*)$")


def _mt940_86(text: str) -> tuple[str, str]:
    """(descrizione, controparte) dal campo :86:. Gestisce il formato strutturato tedesco (?20..?29, ?32/?33)."""
    t = text.replace("\n", "")
    if re.search(r"\?\d\d", t):
        parts = dict()
        for m in re.finditer(r"\?(\d\d)([^?]*)", t):
            parts.setdefault(m.group(1), "")
            parts[m.group(1)] += m.group(2)
        purpose = "".join(parts.get(f"{i}", "") for i in range(20, 30)) + "".join(
            parts.get(f"{i}", "") for i in range(60, 64))
        name = (parts.get("32", "") + parts.get("33", "")).strip()
        booking = parts.get("00", "").strip()
        desc = " · ".join(x for x in (name, _clean(purpose), booking if not purpose else "") if x)
        return desc, name
    # formato olandese/libero: /NAME/…/REMI/…
    m = re.search(r"/NAME/([^/]*)", t)
    name = m.group(1).strip() if m else ""
    m2 = re.search(r"/REMI/(.*?)(?:/[A-Z]{3,4}/|$)", t)
    remi = m2.group(1).strip() if m2 else ""
    desc = " · ".join(x for x in (name, remi) if x) or _clean(t)
    return desc, name


def parse_mt940(data: bytes) -> list[dict]:
    text = _text(data).replace("\r\n", "\n").replace("\r", "\n")
    rows: list[dict] = []
    ccy = ""
    # unisce le righe di continuazione ai rispettivi campi «:XX:»
    fields: list[tuple[str, str]] = []
    for line in text.split("\n"):
        m = re.match(r"^:(\d{2}[A-Z]?):(.*)$", line)
        if m:
            fields.append((m.group(1), m.group(2)))
        elif fields and line.strip() and not line.startswith("-}") and line.strip() != "-":
            tag, val = fields[-1]
            fields[-1] = (tag, val + "\n" + line)
    pending = None
    for tag, val in fields + [("END", "")]:
        if tag in ("61", "62F", "62M", "60F", "60M", "END", "20") and pending is not None:
            rows.append(pending)
            pending = None
        if tag in ("60F", "60M"):
            m = re.match(r"^[CD]\d{6}([A-Z]{3})", val.strip())
            if m:
                ccy = m.group(1)
        elif tag == "61":
            first = val.split("\n")[0].strip()
            m = RE_61.match(first)
            if not m:
                continue
            ymd, _entry, dc, _fund, amt, _rest = m.groups()
            try:
                a = float(amt.replace(",", "."))
            except ValueError:
                continue
            if dc in ("D", "RC"):
                a = -a
            y, mo, d = int(ymd[:2]), ymd[2:4], ymd[4:6]
            y += 2000 if y < 70 else 1900
            pending = {"date": f"{y}-{mo}-{d}", "description": "-", "amount": round(a, 2), "currency": ccy,
                       "_bank_category": "", "_counterparty": None, "_extra": first[-30:]}
        elif tag == "86" and pending is not None:
            desc, name = _mt940_86(val)
            pending["description"] = desc or "-"
            pending["_counterparty"] = name or None
    return [r for r in rows if r["amount"] != 0 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"])]
