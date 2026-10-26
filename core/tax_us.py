"""Stima delle tasse USA sugli stipendi (funzione in prova, alpha).

Cosa calcola, per un anno fiscale e per chi risiede negli Stati Uniti:
- imposta federale sul reddito: stipendi dell'anno - deduzione standard, poi scaglioni secondo lo stato civile;
- contributi FICA (Social Security fino alla base massima + Medicare, con lo 0,9% aggiuntivo oltre la soglia);
- imposta dello stato (o degli stati, se ci si è trasferiti): per ogni stato si calcola l'imposta come se tutto il
  reddito dell'anno fosse suo e poi se ne prende la quota degli stipendi ricevuti mentre si risiedeva lì (il metodo
  di proporzione usato da molti stati per chi risiede solo una parte dell'anno);
- un'eventuale imposta locale (città/contea) indicata dall'utente in percentuale.
Sul totale si aggiunge il margine di sicurezza scelto e si tolgono le tasse già pagate o trattenute.
Restano fuori (vedi le note nella pagina): detrazioni analitiche, crediti d'imposta, altri redditi, recapture e
riduzioni particolari di alcuni stati, accordi contro la doppia imposizione.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from core import db, fx
from core import tax_us_data as D

ENABLED_KEY = "alpha_tax_us"      # "1" = funzione attivata dal profilo
CFG_KEY = "tax_us_cfg"
SALARY_CATEGORY = "Stipendio"


# ---------------------------------------------------------------- attivazione e impostazioni
def enabled() -> bool:
    return db.get_setting(ENABLED_KEY, "0") == "1"


def set_enabled(on: bool) -> None:
    db.set_setting(ENABLED_KEY, "1" if on else "0")


DEFAULT_CFG = {"status": "single", "periods": [], "categories": [SALARY_CATEGORY], "start": {}, "margin": 10.0,
               "fica": True, "paid": {}, "project": False, "proj_amount": {}, "rows": {}, "goal": {},
               "use_payslips": True, "use_invest": True}


def load_cfg() -> dict:
    try:
        cfg = json.loads(db.get_setting(CFG_KEY) or "{}")
    except ValueError:
        cfg = {}
    out = json.loads(json.dumps(DEFAULT_CFG))
    if isinstance(cfg, dict):
        out.update({k: v for k, v in cfg.items() if k in DEFAULT_CFG})
    if out["status"] not in D.FILING:
        out["status"] = "single"
    out["periods"] = [p for p in out["periods"] if isinstance(p, dict) and p.get("state") in D.all_states()
                      and _iso(p.get("from"))]
    return out


def save_cfg(cfg: dict) -> None:
    db.set_setting(CFG_KEY, json.dumps(cfg, ensure_ascii=False))


def _iso(v) -> str | None:
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- residenza
def sorted_periods(periods: list[dict]) -> list[dict]:
    return sorted(periods, key=lambda p: p["from"])


def state_on(day, periods: list[dict]) -> str | None:
    """Stato di residenza in quel giorno: l'ultimo periodo iniziato entro quel giorno (prima del primo periodo vale
    il primo)."""
    ps = sorted_periods(periods)
    if not ps:
        return None
    d = pd.Timestamp(day).date().isoformat()
    cur = ps[0]
    for p in ps:
        if p["from"] <= d:
            cur = p
    return cur["state"]


def local_rate(state: str, periods: list[dict]) -> float:
    """Imposta locale (%) indicata per quello stato (l'ultimo periodo in quello stato)."""
    rate = 0.0
    for p in sorted_periods(periods):
        if p["state"] == state:
            rate = float(p.get("local") or 0)
    return max(0.0, rate)


# ---------------------------------------------------------------- calcoli
def bracket_tax(x: float, brackets: list[tuple[float, float]]) -> tuple[float, list[dict]]:
    """Imposta progressiva: per ogni scaglione l'aliquota vale sulla parte di x oltre la soglia (fino alla soglia
    successiva). Ritorna (imposta, dettaglio per scaglione)."""
    x = max(0.0, float(x))
    total, rows = 0.0, []
    for i, (lo, rate) in enumerate(brackets):
        hi = brackets[i + 1][0] if i + 1 < len(brackets) else None
        if x <= lo:
            break
        part = (min(x, hi) if hi is not None else x) - lo
        tax = part * rate / 100
        total += tax
        rows.append({"from": lo, "to": hi, "rate": rate, "taxed": part, "tax": tax})
    return total, rows


def marginal_rate(x: float, brackets) -> float:
    rate = 0.0
    for lo, r in brackets:
        if x > lo:
            rate = r
    return rate


def federal(wages: float, status: str) -> dict:
    sd = D.FEDERAL_SD[status]
    taxable = max(0.0, wages - sd)
    tax, rows = bracket_tax(taxable, D.FEDERAL[status])
    return {"sd": sd, "taxable": taxable, "tax": tax, "rows": rows,
            "marginal": marginal_rate(taxable, D.FEDERAL[status]) if taxable > 0 else 0.0}


def federal_with_investments(wages: float, inv: dict, status: str) -> dict:
    """Imposta federale con stipendi e redditi da investimenti (moduli 1099), come nel «Qualified Dividends and
    Capital Gain Tax Worksheet»: il reddito ordinario segue gli scaglioni normali, i dividendi qualificati e le
    plusvalenze nette a lungo termine le aliquote 0/15/20% impilate sopra il reddito ordinario. Una perdita netta
    di capitale si deduce fino a 3.000 $ l'anno (1.500 $ separati), il resto si riporta. In più la Net Investment
    Income Tax (3,8%) oltre la soglia e il credito per le imposte estere dei 1099 (semplificato)."""
    sd = D.FEDERAL_SD[status]
    interest = float(inv.get("interest", 0.0))
    ord_div = float(inv.get("ordinary_div", 0.0))
    qual = min(float(inv.get("qualified_div", 0.0)), ord_div)
    st = float(inv.get("st", 0.0))
    lt = float(inv.get("lt", 0.0)) + float(inv.get("cg_dist", 0.0))
    net_cg = st + lt
    limit = D.CAPITAL_LOSS_LIMIT[status]
    cap_in_income = net_cg if net_cg >= 0 else max(net_cg, -limit)
    carryover = net_cg - cap_in_income if net_cg < 0 else 0.0
    agi = wages + interest + ord_div + cap_in_income
    taxable = max(0.0, agi - sd)
    net_capital_gain = max(0.0, min(lt, net_cg)) if net_cg > 0 else 0.0
    pref = min(qual + net_capital_gain, taxable)
    ordinary_taxable = taxable - pref
    ord_tax, rows = bracket_tax(ordinary_taxable, D.FEDERAL[status])
    t0, t15 = D.LTCG[status]
    top = ordinary_taxable + pref
    zero = max(0.0, min(top, t0) - ordinary_taxable)
    fifteen = max(0.0, min(top, t15) - max(ordinary_taxable, t0))
    twenty = max(0.0, pref - zero - fifteen)
    pref_tax = fifteen * 0.15 + twenty * 0.20
    income_tax = ord_tax + pref_tax
    nii = interest + ord_div + max(0.0, net_cg)
    niit = max(0.0, min(nii, agi - D.NIIT_THRESHOLD[status])) * D.NIIT_RATE / 100
    ftc = min(float(inv.get("foreign_tax", 0.0)), income_tax)
    return {"sd": sd, "taxable": taxable, "tax": income_tax + niit - ftc, "rows": rows,
            "marginal": marginal_rate(ordinary_taxable, D.FEDERAL[status]) if ordinary_taxable > 0 else 0.0,
            "agi": agi, "ordinary_taxable": ordinary_taxable, "ordinary_tax": ord_tax, "pref": pref,
            "pref_parts": (zero, fifteen, twenty), "pref_tax": pref_tax, "niit": niit, "ftc": ftc,
            "cap_in_income": cap_in_income, "carryover": carryover, "inv_income": interest + ord_div + cap_in_income}


def residence_days(year: int, periods: list[dict]) -> dict[str, float]:
    """Quota dell'anno passata in ogni stato (per dividere i redditi da investimenti tra gli stati)."""
    start = date(year, 1, 1)
    days = (date(year, 12, 31) - start).days + 1
    out: dict[str, float] = {}
    for i in range(days):
        s = state_on(start + pd.Timedelta(days=i), periods)
        if s:
            out[s] = out.get(s, 0) + 1
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()} if tot else {}


def fica(wages: float, status: str) -> dict:
    ss = min(wages, D.SS_WAGE_BASE) * D.SS_RATE / 100
    med = wages * D.MEDICARE_RATE / 100
    add = max(0.0, wages - D.ADD_MEDICARE_THRESHOLD[status]) * D.ADD_MEDICARE_RATE / 100
    return {"ss": ss, "medicare": med + add, "add": add, "total": ss + med + add}


def state_full_year(code: str, wages: float, status: str, fed_tax: float) -> dict:
    """Imposta dello stato come se tutto il reddito `wages` fosse dell'anno intero di residenza lì."""
    if code in D.NO_TAX or code not in D.STATES:
        return {"taxable": 0.0, "tax": 0.0, "deductions": 0.0, "credits": 0.0, "notax": True}
    s = D.STATES[code]
    joint = status == "mfj"
    k = 1 if joint else 0
    income = float(wages)
    sd = float(s.get("sd", (0, 0))[k])
    ex = float(s.get("ex", (0, 0))[k])
    credit = float(s.get("credit", (0, 0))[k])
    if code == "AL":       # Alabama: si deducono le tasse federali; deduzione standard decrescente col reddito
        income = max(0.0, income - fed_tax)
        (lo, hi), mins = D.AL_SD_PHASE
        floor_ = mins[k]
        if wages > lo:
            sd = max(floor_, sd - (sd - floor_) * min(1.0, (wages - lo) / (hi - lo)))
    elif code == "CT":     # Connecticut: esenzione che si azzera di 1.000 $ ogni 1.000 $ oltre la soglia
        over = max(0.0, wages - D.CT_EX_PHASEOUT[k])
        ex = max(0.0, ex - 1_000 * -(-over // 1_000))
    elif code == "IL" and wages > D.IL_EX_LIMIT[k]:
        ex = 0.0
    elif code == "OH":     # Ohio: esenzione per persona secondo il reddito
        per = 0.0
        for limit, amount in D.OH_EX_TIERS:
            if wages <= limit:
                per = amount
                break
        ex = per * (2 if joint else 1)
    elif code == "WI":     # Wisconsin: deduzione standard che scende col reddito
        start, pct = D.WI_SD_PHASE[k]
        sd = max(0.0, sd - max(0.0, wages - start) * pct / 100)
    elif code == "OR" and wages > D.OR_CREDIT_LIMIT[k]:
        credit = 0.0
    elif code == "UT":     # Utah: credito del 6% della deduzione standard federale, ridotto oltre la soglia
        credit = D.FEDERAL_SD[status] * D.UT_CREDIT_RATE / 100
        credit = max(0.0, credit - max(0.0, wages - D.UT_PHASEOUT[k]) * D.UT_PHASEOUT_RATE / 100)
    taxable = max(0.0, income - sd - ex)
    tax, _rows = bracket_tax(taxable, s["j" if joint else "s"])
    tax = max(0.0, tax - credit)
    return {"taxable": taxable, "tax": tax, "deductions": sd + ex + (wages - income), "credits": credit,
            "notax": False}


def compute(rows: list[dict], status: str, periods: list[dict], with_fica: bool = True, inv: dict | None = None,
            year: int | None = None) -> dict:
    """rows: stipendi considerati, ognuno {usd, state}; inv: totali dei moduli 1099 dell'anno (core.tax_invest),
    facoltativi. Ritorna il dettaglio del calcolo (tutto in dollari).
    Stati: si tassa la somma di stipendi e redditi da investimenti (la maggior parte degli stati tratta plusvalenze e
    dividendi come reddito ordinario; gli interessi dei titoli del Tesoro USA ne sono esenti); gli stipendi vanno
    allo stato in cui sono stati ricevuti, i redditi da investimenti in proporzione ai giorni di residenza."""
    wages = float(sum(r["usd"] for r in rows))
    if inv:
        fed = federal_with_investments(wages, inv, status)
        inv_state = max(0.0, fed["inv_income"] - float(inv.get("us_gov", 0.0))) if fed["inv_income"] > 0 \
            else fed["inv_income"]
    else:
        fed = federal(wages, status)
        fed.update(agi=wages, niit=0.0, ftc=0.0, pref=0.0, pref_tax=0.0, inv_income=0.0, carryover=0.0)
        inv_state = 0.0
    fi = fica(wages, status) if with_fica else {"ss": 0.0, "medicare": 0.0, "add": 0.0, "total": 0.0}
    by_wages: dict[str, float] = {}
    for r in rows:
        by_wages[r["state"]] = by_wages.get(r["state"], 0.0) + float(r["usd"])
    by_inv: dict[str, float] = {}
    if inv_state > 0 and periods:      # redditi da investimenti: in proporzione ai giorni di residenza
        by_inv = {k: inv_state * v for k, v in residence_days(int(year or date.today().year), periods).items()}
    elif inv_state < 0 and wages > 0:  # perdita deducibile: riduce il reddito degli stati in cui si lavorava
        by_inv = {k: inv_state * w / wages for k, w in by_wages.items()}
    income = max(0.0, wages + inv_state)
    states = []
    for code in sorted(set(by_wages) | set(by_inv), key=lambda c: -(by_wages.get(c, 0) + by_inv.get(c, 0))):
        w, iv = by_wages.get(code, 0.0), by_inv.get(code, 0.0)
        full = state_full_year(code, income, status, fed["tax"])
        share = max(0.0, (w + iv) / income) if income else 0.0
        local = local_rate(code, periods)
        states.append({"code": code, "name": D.all_states().get(code, code), "wages": w, "inv": iv, "share": share,
                       "full": full["tax"], "tax": full["tax"] * share, "local_rate": local,
                       "local": w * local / 100, "notax": full["notax"]})
    state_tax = sum(s["tax"] for s in states)
    local_tax = sum(s["local"] for s in states)
    total = fed["tax"] + fi["total"] + state_tax + local_tax
    base_income = wages + max(0.0, fed["inv_income"])
    return {"wages": wages, "inv_income": fed["inv_income"], "federal": fed, "fica": fi, "states": states,
            "state_tax": state_tax, "local_tax": local_tax, "total": total,
            "effective": total / base_income * 100 if base_income else 0.0}


def with_margin(total: float, margin_pct: float, paid: float) -> tuple[float, float]:
    """(totale con il margine di sicurezza, quanto resta da mettere da parte togliendo il già pagato)."""
    gross = total * (1 + max(0.0, margin_pct) / 100)
    return gross, max(0.0, gross - max(0.0, paid))


# ---------------------------------------------------------------- stipendi
def salary_categories(tx: pd.DataFrame) -> list[str]:
    """Categorie di entrata presenti nei movimenti (per scegliere quali contano come stipendio)."""
    inc = tx[(tx["kind"] == "entrata") & (tx["amount"] > 0)]
    cats = sorted({str(c) for c in inc["category"].dropna()})
    if SALARY_CATEGORY not in cats:
        cats.insert(0, SALARY_CATEGORY)
    return cats


def _to_usd(amount: float, ccy: str, day, amount_base, base: str) -> float | None:
    ccy = (ccy or "").upper()
    if ccy == "USD":
        return float(amount)
    try:
        return float(amount) * fx.get_rate(ccy, "USD", day)
    except Exception:
        pass
    try:  # ripiego: controvalore nella valuta base già salvato nel movimento
        if amount_base is not None and not pd.isna(amount_base):
            return float(amount_base) * fx.get_rate(base, "USD", day)
    except Exception:
        pass
    return None


def salary_rows(tx: pd.DataFrame, year: int, cfg: dict) -> pd.DataFrame:
    """Stipendi dell'anno (categorie scelte, importi positivi) con importo in dollari, stato e se vanno inclusi:
    i valori predefiniti vengono dalla residenza e dal primo stipendio scelto, poi valgono le modifiche dell'utente.
    Se l'accredito ha una busta paga abbinata (e l'opzione è attiva) l'importo proposto è il lordo tassabile USA della
    busta invece dell'accredito in banca."""
    cols = ["id", "date", "desc", "amount", "ccy", "usd", "auto_usd", "state", "inc", "conv_ok", "src"]
    if tx.empty:
        return pd.DataFrame(columns=cols)
    cats = set(cfg.get("categories") or [SALARY_CATEGORY])
    m = (tx["date"].dt.year == year) & (tx["amount"] > 0) & tx["category"].isin(cats)
    s = tx[m].sort_values(["date", "id"])
    if s.empty:
        return pd.DataFrame(columns=cols)
    base = db.base_currency()
    for ccy in sorted(set(s["currency"].str.upper()) - {"USD"}):
        fx.prefetch_range(ccy, "USD", s["date"].min().date(), s["date"].max().date())
    start = (cfg.get("start") or {}).get(str(year))
    start_key = None
    if start is not None:
        hit = s[s["id"] == int(start)]
        if not hit.empty:
            start_key = (hit.iloc[0]["date"], int(start))
    over = cfg.get("rows") or {}
    slips = {}
    if cfg.get("use_payslips", True):
        from core import payslip
        try:
            slips = payslip.linked()
        except Exception:   # l'archivio delle buste non deve mai bloccare il calcolo
            slips = {}
    out = []
    for r in s.itertuples():
        slip = slips.get(int(r.id))
        if slip:
            auto = _to_usd(slip["taxable"], slip["currency"], r.date.date(), None, base)
        else:
            auto = _to_usd(r.amount, r.currency, r.date.date(), getattr(r, "amount_base", None), base)
        o = over.get(str(r.id), {})
        inc = (r.date, int(r.id)) >= start_key if start_key else True
        if "inc" in o:
            inc = bool(o["inc"])
        state = o.get("state") if o.get("state") in D.all_states() else state_on(r.date, cfg.get("periods") or [])
        usd = o.get("usd")
        usd = float(usd) if isinstance(usd, (int, float)) and usd >= 0 else auto
        out.append({"id": int(r.id), "date": r.date, "desc": str(r.description), "amount": float(r.amount),
                    "ccy": str(r.currency).upper(), "usd": usd, "auto_usd": auto, "state": state, "inc": inc,
                    "conv_ok": auto is not None, "src": "payslip" if slip else "bank"})
    return pd.DataFrame(out, columns=cols)


def projection_default(rows: pd.DataFrame) -> float | None:
    """Stipendio mensile proposto per i mesi che mancano: la mediana degli ultimi tre stipendi considerati."""
    inc = rows[rows["inc"] & rows["usd"].notna()]
    if inc.empty:
        return None
    return float(inc.sort_values("date")["usd"].tail(3).median())


def projected_rows(rows: pd.DataFrame, year: int, periods: list[dict], today: date | None = None,
                   amount: float | None = None) -> list[dict]:
    """Stipendi previsti fino a dicembre (anno in corso): uno al mese dopo l'ultimo considerato, dell'importo dato
    (di solito la mediana degli ultimi tre), nello stato di residenza di quel mese."""
    today = today or date.today()
    inc = rows[rows["inc"] & rows["usd"].notna()]
    if year != today.year or inc.empty:
        return []
    last = inc["date"].max()
    if amount is None:
        amount = projection_default(rows)
    amount = max(0.0, float(amount or 0.0))
    state = state_on(today, periods) or inc.iloc[-1]["state"]
    out = []
    for month in range(max(last.month, today.month - 1) + 1, 13):
        day = date(year, month, 1)
        out.append({"date": pd.Timestamp(day), "usd": amount, "state": state_on(day, periods) or state})
    return out
