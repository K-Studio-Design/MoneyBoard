"""Riconoscimento dei pagamenti ricorrenti (abbonamenti, canoni, bollette, rate) e delle entrate ricorrenti.

Idea: si raggruppano i movimenti per esercente (merchant_key); dentro ogni esercente si cercano
serie di importi simili che si ripetono a intervalli regolari (settimana, mese, bimestre, trimestre,
semestre, anno). Una serie è "attiva" se il prossimo addebito atteso non è in ritardo di molto.
Tutto è calcolato al volo dai movimenti: nessuna tabella in più, solo le scelte dell'utente
(serie nascoste o confermate) salvate nelle impostazioni.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from core import db
from core.merchants import merchant_key, pretty_name

# (nome, giorni tipici, tolleranza in giorni, mesi per il calcolo della data successiva)
CADENCES = [
    ("settimanale", 7, 1.5, None),
    ("bisettimanale", 14, 2, None),
    ("mensile", 30.44, 5, 1),
    ("bimestrale", 60.9, 7, 2),
    ("trimestrale", 91.3, 10, 3),
    ("semestrale", 182.6, 15, 6),
    ("annuale", 365.25, 20, 12),
]
MIN_OCCURRENCES = {"settimanale": 4, "bisettimanale": 4, "mensile": 3, "bimestrale": 3, "trimestrale": 3, "semestrale": 2, "annuale": 2}
HIDDEN_KEY = "recurring_hidden"
DELETED_KEY = "recurring_deleted"   # eliminati: spariscono da tutte le liste (tornano solo se cambiano i dati)
CONFIRMED_KEY = "recurring_confirmed"


@dataclass
class Series:
    sid: str                 # identificativo stabile (esercente + importo tipico + cadenza)
    name: str                # esercente, come chiave leggibile
    description: str         # descrizione dell'ultimo movimento
    kind: str                # 'uscita' o 'entrata'
    cadence: str
    period_days: float
    months: int | None
    category: str
    account: str
    currency: str
    amount: float            # ultimo importo, valuta originale (positivo)
    amount_base: float       # ultimo importo in valuta base (positivo)
    typical_base: float      # importo tipico (mediana) in valuta base
    variable: bool           # importo che cambia (es. bollette)
    first: pd.Timestamp
    last: pd.Timestamp
    next_date: pd.Timestamp
    count: int
    active: bool
    monthly_base: float      # costo medio al mese in valuta base
    ids: list[int] = field(default_factory=list)
    anchor_day: int = 1      # giorno del mese tipico (per le cadenze mensili o più lunghe)
    day_rule: str = "giorno"          # regola usata per le date: giorno | ultimo_lav | primo_lav
    day_rule_detected: str = "giorno"  # regola rilevata dai movimenti
    price_change: tuple[float, float] | None = None   # (prima, adesso) in valuta originale, se cambiata
    price_change_date: pd.Timestamp | None = None
    schedule: dict | None = None      # stipendio con le date scelte nel Profilo (giorni del mese, ogni 1-2 settimane)

    @property
    def yearly_base(self) -> float:
        return self.monthly_base * 12


# ---------------------------------------------------------------- giorni lavorativi (calendario italiano)
DAY_RULES = {
    "auto": "Automatico (come rilevato dai movimenti)",
    "giorno": "Stesso giorno del mese",
    "ultimo_lav": "Ultimo giorno lavorativo del mese",
    "primo_lav": "Primo giorno lavorativo del mese",
}
RULES_KEY = "recurring_day_rules"
SALARY_KEY = "salary_day_rule"      # quando arriva lo stipendio (categoria «Stipendio»)
SALARY_SCHED_KEY = "salary_schedule"  # dettagli delle date scelte a mano (giorni, giorno di riferimento, festivi)
SALARY_CATEGORY = "Stipendio"
# come arriva lo stipendio (scelta nel Profilo)
SALARY_MODES = {
    "ultimo_lav": "L'ultimo giorno lavorativo del mese",
    "primo_lav": "Il primo giorno lavorativo del mese",
    "giorni": "In uno o più giorni del mese a scelta",
    "bisettimanale": "Ogni 2 settimane",
    "settimanale": "Ogni settimana",
    "auto": "Riconoscilo dai movimenti",
}
SCHEDULE_MODES = ("giorni", "bisettimanale", "settimanale")   # date calcolate dal calendario scelto nel Profilo
SHIFTS = {"prima": "Il giorno lavorativo prima", "dopo": "Il giorno lavorativo dopo", "no": "Lascia la data com'è"}
CALENDARS = {"IT": "Italia", "US": "Stati Uniti", "none": "Nessuna (solo sabato e domenica)"}


def salary_rule() -> str:
    v = db.get_setting(SALARY_KEY, "ultimo_lav") or "ultimo_lav"
    return v if v in SALARY_MODES else "ultimo_lav"


def clean_schedule(raw, mode: str) -> dict | None:
    """Calendario dello stipendio valido per la modalità (None se mancano i dati, es. nessun giorno scelto)."""
    if mode not in SCHEDULE_MODES or not isinstance(raw, dict):
        return None
    shift = raw.get("shift") if raw.get("shift") in SHIFTS else "prima"
    cal = raw.get("cal") if raw.get("cal") in CALENDARS else "IT"
    out = {"mode": mode, "shift": shift, "cal": cal}
    if mode == "giorni":
        days = set()
        for x in raw.get("days") or []:
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if 1 <= v <= 31:
                days.add(v)
        if not days:
            return None
        out["days"] = sorted(days)
    else:
        ref = raw.get("ref")
        if not ref:
            return None
        try:
            out["ref"] = pd.Timestamp(str(ref)).normalize().date().isoformat()
        except (TypeError, ValueError):
            return None
    return out


def salary_schedule() -> dict | None:
    """Calendario dello stipendio scelto nel Profilo (None se la modalità non usa date scelte a mano)."""
    try:
        raw = json.loads(db.get_setting(SALARY_SCHED_KEY, "{}") or "{}")
    except (ValueError, TypeError):
        raw = {}
    return clean_schedule(raw, salary_rule())


def salary_rules() -> dict[str, str]:
    """Le scelte del Profilo sullo stipendio, nel formato delle regole di detect()."""
    out = {"__stipendio__": salary_rule()}
    sched = salary_schedule()
    if sched:
        out["__stipendio_sched__"] = json.dumps(sched, sort_keys=True)
    return out


def _sched_from_rules(rules: dict) -> dict | None:
    raw = rules.get("__stipendio_sched__")
    if not raw:
        return None
    try:
        return clean_schedule(json.loads(raw), rules.get("__stipendio__", ""))
    except (ValueError, TypeError):
        return None


def _shift(d: pd.Timestamp, shift: str, cal: str) -> pd.Timestamp:
    """Sposta una data che cade di sabato, domenica o festivo (secondo il calendario) al giorno lavorativo
    prima o dopo; con 'no' la lascia com'è."""
    if shift == "no":
        return d
    step = pd.Timedelta(days=-1 if shift == "prima" else 1)
    guard = 0
    while not is_business_day(d, cal) and guard < 15:
        d += step
        guard += 1
    return d


def schedule_next(sched: dict, after) -> pd.Timestamp:
    """Primo accredito del calendario `sched` strettamente dopo la data `after`."""
    after = pd.Timestamp(after).normalize()
    shift, cal = sched.get("shift", "prima"), sched.get("cal", "IT")
    if sched["mode"] == "giorni":
        best = None
        p = after.to_period("M") - 1
        for _ in range(16):
            for day in sched["days"]:
                d = _shift(pd.Timestamp(year=p.year, month=p.month, day=min(day, p.days_in_month)), shift, cal)
                if d > after and (best is None or d < best):
                    best = d
            # una data spostata in avanti può finire al massimo pochi giorni nel mese dopo: se la migliore
            # trovata è prima della fine del mese successivo, i mesi seguenti non possono dare di meglio
            if best is not None and best <= (p + 1).end_time.normalize():
                break
            p += 1
        return best
    period = 7 if sched["mode"] == "settimanale" else 14
    ref = pd.Timestamp(sched["ref"])
    k = (after - ref).days // period - 1
    while True:
        d = _shift(ref + pd.Timedelta(days=k * period), shift, cal)
        if d > after:
            return d
        k += 1


def schedule_dates(sched: dict, start, end) -> list[pd.Timestamp]:
    """Accrediti del calendario tra start ed end (compresi)."""
    out, d = [], pd.Timestamp(start).normalize() - pd.Timedelta(days=1)
    end = pd.Timestamp(end).normalize()
    while len(out) < 400:
        d = schedule_next(sched, d)
        if d > end:
            break
        out.append(d)
    return out


def schedule_period_days(sched: dict) -> float:
    if sched["mode"] == "settimanale":
        return 7.0
    if sched["mode"] == "bisettimanale":
        return 14.0
    return 30.44 / len(sched["days"])


def schedule_cadence(sched: dict) -> str:
    if sched["mode"] in ("settimanale", "bisettimanale"):
        return sched["mode"]
    n = len(sched["days"])
    return "mensile" if n == 1 else "due volte al mese" if n == 2 else "più volte al mese"


def _easter(year: int) -> date:
    """Domenica di Pasqua (algoritmo di Gauss/Meeus, calendario gregoriano)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def holidays_it(year: int) -> set[date]:
    """Festività nazionali italiane (le banche sono chiuse): Capodanno, Epifania, Pasquetta, 25 aprile,
    1 maggio, 2 giugno, Ferragosto, Ognissanti, Immacolata, Natale, Santo Stefano."""
    fixed = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)]
    out = {date(year, m, d) for m, d in fixed}
    out.add(_easter(year) + timedelta(days=1))
    return out


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-esimo giorno della settimana del mese (n = -1: l'ultimo). weekday: 0 = lunedì."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = (pd.Period(year=year, month=month, freq="M")).end_time.date()
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def holidays_us(year: int) -> set[date]:
    """Festività federali USA in cui le banche (Federal Reserve) sono chiuse. Se cadono di domenica si
    festeggiano il lunedì; se cadono di sabato le banche restano aperte il venerdì (regola della Federal Reserve)."""
    out = set()
    for m, d in [(1, 1), (6, 19), (7, 4), (11, 11), (12, 25)]:
        x = date(year, m, d)
        out.add(x + timedelta(days=1) if x.weekday() == 6 else x)
    out |= {_nth_weekday(year, 1, 0, 3),    # Martin Luther King Jr. Day
            _nth_weekday(year, 2, 0, 3),    # Washington's Birthday
            _nth_weekday(year, 5, 0, -1),   # Memorial Day
            _nth_weekday(year, 9, 0, 1),    # Labor Day
            _nth_weekday(year, 10, 0, 2),   # Columbus Day
            _nth_weekday(year, 11, 3, 4)}   # Thanksgiving
    return out


def is_business_day(d, cal: str = "IT") -> bool:
    """Giorno lavorativo per le banche: dal lunedì al venerdì, escluse le festività del calendario
    ('IT' Italia, 'US' Stati Uniti, 'none' nessuna festività)."""
    d = pd.Timestamp(d).date()
    if d.weekday() >= 5:
        return False
    if cal == "US":
        return d not in holidays_us(d.year)
    if cal == "none":
        return True
    return d not in holidays_it(d.year)


def last_business_day(year: int, month: int) -> pd.Timestamp:
    d = (pd.Period(year=year, month=month, freq="M")).end_time.normalize()
    while not is_business_day(d):
        d -= pd.Timedelta(days=1)
    return d


def first_business_day(year: int, month: int) -> pd.Timestamp:
    d = pd.Timestamp(year=year, month=month, day=1)
    while not is_business_day(d):
        d += pd.Timedelta(days=1)
    return d


def occurrence(period: pd.Period, rule: str, day: int) -> pd.Timestamp:
    """Data dell'addebito nel mese `period` secondo la regola."""
    if rule == "ultimo_lav":
        return last_business_day(period.year, period.month)
    if rule == "primo_lav":
        return first_business_day(period.year, period.month)
    return pd.Timestamp(year=period.year, month=period.month, day=min(day, period.days_in_month))


def detect_day_rule(dates: pd.Series) -> str:
    """'ultimo_lav' / 'primo_lav' se almeno l'80% delle date cade su quel giorno, altrimenti 'giorno'."""
    ds = pd.to_datetime(pd.Series(dates)).dt.normalize()
    if len(ds) < 3:
        return "giorno"
    last = np.mean([d == last_business_day(d.year, d.month) for d in ds])
    first = np.mean([d == first_business_day(d.year, d.month) for d in ds])
    if last >= 0.8:
        return "ultimo_lav"
    if first >= 0.8:
        return "primo_lav"
    return "giorno"


def day_rules() -> dict[str, str]:
    """Regole scelte a mano per singole serie (sid -> regola)."""
    try:
        v = json.loads(db.get_setting(RULES_KEY, "{}") or "{}")
        return {str(k): str(x) for k, x in v.items() if x in DAY_RULES} if isinstance(v, dict) else {}
    except (ValueError, TypeError, AttributeError):
        return {}


def set_day_rule(sid: str, rule: str) -> None:
    cur = day_rules()
    if rule == "auto" or rule not in DAY_RULES:
        cur.pop(sid, None)
    else:
        cur[sid] = rule
    db.set_setting(RULES_KEY, json.dumps(cur))


def _add_months(d: pd.Timestamp, months: int, day: int) -> pd.Timestamp:
    """Stesso giorno del mese, `months` mesi dopo (al massimo l'ultimo giorno del mese)."""
    p = (d.to_period("M") + months)
    last = p.days_in_month
    return pd.Timestamp(year=p.year, month=p.month, day=min(day, last))


def _cadence_of(gaps: np.ndarray):
    """Cadenza a cui corrisponde la maggior parte degli intervalli, oppure None."""
    if len(gaps) == 0:
        return None
    med = float(np.median(gaps))
    for name, days, tol, months in CADENCES:
        if abs(med - days) <= tol:
            ok = np.abs(gaps - days) <= tol * (1.6 if name != "settimanale" else 1)
            # quasi tutti gli intervalli regolari; uno saltato (doppio intervallo) è tollerato
            doubled = np.abs(gaps - 2 * days) <= tol * 2
            if (ok | doubled).mean() >= 0.8 and ok.mean() >= 0.6:
                return name, days, months
    return None


def _clusters(amounts: np.ndarray) -> list[np.ndarray]:
    """Gruppi di indici con importi simili (entro il 12% o 1 unità), dal più numeroso."""
    order = np.argsort(amounts)
    groups, cur = [], [order[0]]
    for i in order[1:]:
        ref = np.median(amounts[cur])
        if abs(amounts[i] - ref) <= max(0.12 * abs(ref), 1.0):
            cur.append(i)
        else:
            groups.append(np.array(cur))
            cur = [i]
    groups.append(np.array(cur))
    return sorted(groups, key=len, reverse=True)


# categorie di spese "a piacere": qui una ripetizione ogni 3-12 mesi è quasi sempre una coincidenza
_DISCRETIONARY = {"Ristoranti e bar", "Spesa alimentare", "Carburante", "Shopping e acquisti online",
                  "Abbigliamento e scarpe", "Contanti e prelievi", "Viaggi e vacanze", "Cura personale",
                  "Regali e donazioni", "Altre spese"}


def _plausible(cadence: str, series_rows: pd.DataFrame, merchant_rows: pd.DataFrame, variable: bool = False) -> bool:
    """Scarta le coincidenze. Nelle categorie di spese occasionali (ristoranti, spesa, carburante…)
    si accettano solo importi fissi con cadenza mensile o bimestrale (es. una rata). Le cadenze lunghe
    (3-12 mesi), con pochi casi, valgono solo se la serie è la gran parte dei movimenti dell'esercente."""
    if str(series_rows["category"].iloc[-1]) in _DISCRETIONARY:
        if variable or cadence not in ("mensile", "bimestrale"):
            return False
    if cadence in ("settimanale", "mensile", "bimestrale"):
        return True
    return len(series_rows) >= 0.6 * merchant_rows["date"].nunique()


def _make_series(g: pd.DataFrame, name: str, kind: str, cad, today: pd.Timestamp, variable: bool,
                 ids=None, rules: dict | None = None, sid: str | None = None) -> Series:
    cname, days, months = cad
    g = g.sort_values("date")
    last = g.iloc[-1]
    day = int(np.median(g["date"].dt.day))
    # identificativo stabile: per gli importi variabili (stipendio, bollette) non dipende dall'importo
    amount_key = "var" if variable else round(float(np.median(g["abs_amount"])), 0)
    sid = sid or hashlib.sha1(f"{kind}|{name}|{cname}|{amount_key}|{last['currency']}".encode()).hexdigest()[:12]
    detected = detect_day_rule(g["date"]) if months else "giorno"
    rules = rules or {}
    rule = "giorno"
    # stipendio con le date scelte nel Profilo (giorni del mese, ogni 1 o 2 settimane): valgono quelle,
    # qualunque sia la cadenza trovata nei movimenti, salvo una regola scelta a mano per questa serie
    sched = None
    if kind == "entrata" and str(last["category"]) == SALARY_CATEGORY and sid not in rules \
            and cname in _SALARY_CADENCES:
        sched = _sched_from_rules(rules)
    if sched:
        cname, days, months = schedule_cadence(sched), schedule_period_days(sched), None
        rule = detected = "profilo"
        # un accredito arrivato con qualche giorno di anticipo non fa saltare il successivo
        nxt = schedule_next(sched, last["date"] + pd.Timedelta(days=min(3.0, days / 3)))
    elif months:
        rule = rules.get(sid) or detected
        # stipendio: vale la regola indicata nel profilo (di default l'ultimo giorno lavorativo del mese)
        if sid not in rules and months == 1 and kind == "entrata" and str(last["category"]) == SALARY_CATEGORY:
            sal = rules.get("__stipendio__", "ultimo_lav")
            rule = sal if sal in ("ultimo_lav", "primo_lav") else detected
    if sched:
        pass                    # data già calcolata dal calendario
    elif months and rule in ("ultimo_lav", "primo_lav"):
        # il mese dell'ultimo accredito "regolare" + la cadenza; se cade prima dell'ultimo, si va avanti
        p = last["date"].to_period("M") + months
        nxt = occurrence(p, rule, day)
        while nxt <= last["date"]:
            p += months
            nxt = occurrence(p, rule, day)
    elif months:
        # stesso giorno tipico del mese (mediana): un addebito arrivato con qualche giorno di anticipo
        # o di ritardo (es. il 31 slittato al 1°) non sposta la previsione
        approx = last["date"] + pd.Timedelta(days=round(days))
        cands = [_add_months(approx, k, day) for k in (-1, 0, 1)]
        nxt = min(cands, key=lambda c: abs((c - approx).days))
    else:
        nxt = last["date"] + pd.Timedelta(days=round(days))
    # se la data attesa è passata ma la serie è ancora attiva, si porta avanti al prossimo ciclo futuro
    grace = max(days * 0.5, 6)
    active = (today - nxt).days <= grace
    while active and nxt < today:
        nxt = _step(nxt, months, days, rule, day, sched)
    vals = g["abs_base"].to_numpy()
    typical = float(np.median(vals[-6:]))
    s = Series(
        sid=sid, name=name, description=str(last["description"]),
        kind=kind, cadence=cname, period_days=days, months=months, category=str(last["category"] or ""),
        account=str(last["account"]), currency=str(last["currency"]), amount=float(last["abs_amount"]),
        amount_base=float(last["abs_base"]), typical_base=typical, variable=variable,
        first=g["date"].iloc[0], last=last["date"], next_date=nxt, count=len(g), active=active,
        monthly_base=typical * 30.44 / days, ids=[int(i) for i in (g["id"] if ids is None else ids)],
        anchor_day=day, day_rule=rule, day_rule_detected=detected, schedule=sched,
    )
    # cambio di prezzo: ultimo importo diverso dal precedente (solo per importi fissi)
    if not variable and len(g) >= 2:
        prev_amt, cur_amt = float(g["abs_amount"].iloc[-2]), float(g["abs_amount"].iloc[-1])
        if abs(cur_amt - prev_amt) >= max(0.01 * prev_amt, 0.05):
            s.price_change, s.price_change_date = (prev_amt, cur_amt), last["date"]
    return s


def _step(d: pd.Timestamp, months: int | None, days: float, rule: str, day: int,
          sched: dict | None = None) -> pd.Timestamp:
    """Data successiva a `d` secondo cadenza e regola (o secondo il calendario dello stipendio)."""
    if sched:
        return schedule_next(sched, d)
    if not months:
        return d + pd.Timedelta(days=round(days))
    if rule in ("ultimo_lav", "primo_lav"):
        return occurrence(d.to_period("M") + months, rule, day)
    return _add_months(d, months, day)


def detect(df: pd.DataFrame | None = None, today: date | None = None, rules: dict | None = None) -> list[Series]:
    """Serie ricorrenti trovate nei movimenti (uscite ed entrate; i movimenti neutri sono esclusi).
    df: transazioni come da db.transactions_df() (serve 'kind'); default tutte.
    rules: regole per il giorno dell'addebito scelte a mano (sid -> regola); default quelle salvate."""
    if rules is None:
        rules = day_rules()
        rules.update(salary_rules())
    if df is None:
        df = db.transactions_df()
    if df.empty:
        return []
    today = pd.Timestamp(today or date.today())
    base = db.base_currency()
    d = df[df["kind"].isin(["uscita", "entrata"])].copy()
    val = d["amount_base"].where(d["amount_base"].notna() | (d["currency"] != base), d["amount"])
    sign = np.where(d["kind"] == "uscita", -1, 1)
    # solo addebiti veri (per le uscite) e accrediti veri (per le entrate): niente storni o rimborsi
    d = d[(np.sign(d["amount"]) == sign) & val.notna()]
    d["abs_amount"] = d["amount"].abs()
    d["abs_base"] = val.loc[d.index].abs()
    d["mkey"] = d["description"].map(merchant_key)
    out: list[Series] = []
    for (kind, mkey, ccy), g in d.groupby(["kind", "mkey", "currency"], sort=False):
        if len(g) < 2:
            continue
        g = g.sort_values("date")
        # 1) tutto l'esercente è regolare (abbonamento, oppure stipendio/bolletta con importo che varia)
        days_u = np.unique(g["date"].to_numpy())
        cad = _cadence_of(np.diff(days_u).astype("timedelta64[D]").astype(float)) if len(days_u) >= 3 else None
        if cad:
            # un movimento per giorno (somma degli importi dello stesso giorno), senza groupby.agg (lento)
            last_of_day = g.drop_duplicates("date", keep="last").set_index("date")
            sums = g.groupby("date")[["abs_amount", "abs_base"]].sum()
            per_day = last_of_day.drop(columns=["abs_amount", "abs_base"]).join(sums).reset_index()
            vals = per_day["abs_amount"]
            med = max(float(vals.median()), 0.01)
            # dispersione robusta: un importo eccezionale (tredicesima, premio, conguaglio) non conta
            steady = float((vals - med).abs().median()) / med <= 0.35
            variable = (vals.max() - vals.min()) / med > 0.12
            if steady and len(per_day) >= max(MIN_OCCURRENCES[cad[0]], 3) \
                    and _plausible(cad[0], per_day, g, variable):
                out.append(_make_series(per_day, mkey, kind, cad, today, variable=variable, ids=g["id"], rules=rules))
                continue
        # 2) serie a importo (quasi) fisso dentro un esercente con altri acquisti (es. PayPal, Amazon, Google)
        for idx in _clusters(g["abs_amount"].to_numpy()):
            if len(idx) < 2:
                continue
            sub = g.iloc[np.sort(idx)].drop_duplicates("date")
            cad = _cadence_of(np.diff(sub["date"].to_numpy()).astype("timedelta64[D]").astype(float))
            if cad and len(sub) >= MIN_OCCURRENCES[cad[0]] and _plausible(cad[0], sub, g):
                out.append(_make_series(sub, mkey, kind, cad, today, variable=False, rules=rules))
    # stipendio con le date scelte nel Profilo ma non ancora riconosciuto come ricorrente (pochi accrediti,
    # o date che dai movimenti non si capiscono): si prevede comunque, dall'ultimo accredito
    sched = _sched_from_rules(rules)
    if sched and not any(s.active and s.kind == "entrata" and s.category == SALARY_CATEGORY for s in out):
        extra = _salary_from_schedule(d, today, rules)
        if extra is not None:
            out.append(extra)
    # canoni rimborsati: se una serie di entrate/storni dello stesso importo li azzera, non sono un costo
    out = [s for s in out if not _fully_refunded(s, df)]
    out.sort(key=lambda s: (not s.active, -s.monthly_base))
    return out


_SALARY_CADENCES = ("settimanale", "bisettimanale", "mensile")


def _salary_from_schedule(d: pd.DataFrame, today: pd.Timestamp, rules: dict) -> Series | None:
    """Serie dello stipendio costruita dal calendario del Profilo e dagli accrediti degli ultimi 4 mesi
    (categoria «Stipendio»): si usa il datore di lavoro che ha pagato per ultimo."""
    sal = d[(d["kind"] == "entrata") & (d["category"] == SALARY_CATEGORY) & (d["date"] <= today)
            & (d["date"] >= today - pd.Timedelta(days=120))]
    if sal.empty:
        return None
    last = sal.sort_values("date").iloc[-1]
    mkey, ccy = last["mkey"], last["currency"]
    g = sal[(sal["mkey"] == mkey) & (sal["currency"] == ccy)].sort_values("date")
    last_of_day = g.drop_duplicates("date", keep="last").set_index("date")
    sums = g.groupby("date")[["abs_amount", "abs_base"]].sum()
    per_day = last_of_day.drop(columns=["abs_amount", "abs_base"]).join(sums).reset_index()
    vals = per_day["abs_amount"]
    med = max(float(vals.median()), 0.01)
    variable = bool(len(vals) > 1 and (vals.max() - vals.min()) / med > 0.12)
    sid = hashlib.sha1(f"entrata|{mkey}|stipendio-profilo|{ccy}".encode()).hexdigest()[:12]
    # la cadenza passata qui serve solo a far valere il calendario del Profilo (che la sostituisce)
    return _make_series(per_day, mkey, "entrata", ("mensile", 30.44, None), today, variable=variable,
                        ids=g["id"], rules=rules, sid=sid)


def _fully_refunded(s: Series, df: pd.DataFrame) -> bool:
    if s.kind != "uscita":
        return False
    rows = df[df["id"].isin(s.ids)]
    # rimborsi: movimenti positivi della stessa categoria, stesso importo, entro 3 giorni
    pos = df[(df["amount"] > 0) & (df["category"] == s.category) & (df["account"] == s.account)]
    if pos.empty:
        return False
    hits = 0
    for _, r in rows.iterrows():
        m = pos[(pos["amount"].round(2) == round(-r["amount"], 2))
                & ((pos["date"] - r["date"]).dt.days.abs() <= 3)]
        hits += not m.empty
    return hits >= 0.8 * len(rows)


# ---------------------------------------------------------------- scelte dell'utente
def _load(key: str) -> list[str]:
    try:
        v = json.loads(db.get_setting(key, "[]") or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def hidden() -> set[str]:
    return set(_load(HIDDEN_KEY))


def confirmed() -> set[str]:
    return set(_load(CONFIRMED_KEY))


def set_hidden(sid: str, value: bool) -> None:
    cur = hidden()
    cur.add(sid) if value else cur.discard(sid)
    db.set_setting(HIDDEN_KEY, json.dumps(sorted(cur)))


def set_confirmed(sid: str, value: bool) -> None:
    cur = confirmed()
    cur.add(sid) if value else cur.discard(sid)
    db.set_setting(CONFIRMED_KEY, json.dumps(sorted(cur)))


def deleted() -> set[str]:
    return set(_load(DELETED_KEY))


def delete(sids) -> None:
    """Elimina una o più serie: non compaiono più né tra gli attivi né tra i nascosti."""
    sids = {sids} if isinstance(sids, str) else set(sids)
    db.set_setting(DELETED_KEY, json.dumps(sorted(deleted() | sids)[-3000:]))
    h = hidden() - sids
    db.set_setting(HIDDEN_KEY, json.dumps(sorted(h)))


def not_deleted(series: list[Series]) -> list[Series]:
    d = deleted()
    return [s for s in series if s.sid not in d]


def visible(series: list[Series]) -> list[Series]:
    gone = hidden() | deleted()
    return [s for s in series if s.sid not in gone]


def upcoming(series: list[Series], start: date, end: date) -> list[tuple[pd.Timestamp, Series]]:
    """Addebiti/accrediti attesi tra start e end (compresi), dalle serie attive."""
    out = []
    s0, e0 = pd.Timestamp(start), pd.Timestamp(end)
    for s in series:
        if not s.active:
            continue
        d = s.next_date
        guard = 0
        while d <= e0 and guard < 60:
            if d >= s0:
                out.append((d, s))
            d = _step(d, s.months, s.period_days, s.day_rule, s.anchor_day, s.schedule)
            guard += 1
    out.sort(key=lambda x: x[0])
    return out


NAMES_KEY = "recurring_names"


def custom_names() -> dict[str, str]:
    try:
        v = json.loads(db.get_setting(NAMES_KEY, "{}") or "{}")
        return {str(k): str(x) for k, x in v.items()} if isinstance(v, dict) else {}
    except (ValueError, TypeError, AttributeError):
        return {}


def set_name(sid: str, name: str) -> None:
    cur = custom_names()
    if name.strip():
        cur[sid] = name.strip()
    else:
        cur.pop(sid, None)
    db.set_setting(NAMES_KEY, json.dumps(cur, ensure_ascii=False))


def display_name(s: Series, names: dict[str, str] | None = None) -> str:
    names = custom_names() if names is None else names
    return names.get(s.sid) or pretty_name(s.description, s.name)


CADENCE_ADJ = {"settimanale": "a settimana", "bisettimanale": "ogni 2 settimane", "due volte al mese": "ogni volta",
               "più volte al mese": "ogni volta", "mensile": "al mese", "bimestrale": "ogni 2 mesi",
               "trimestrale": "ogni 3 mesi", "semestrale": "ogni 6 mesi", "annuale": "all'anno"}


def pretty_name_of(s: Series) -> str:
    return pretty_name(s.description, s.name)
