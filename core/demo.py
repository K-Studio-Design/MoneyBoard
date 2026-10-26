"""Dati fittizi per gli account di prova.

Tutto è inventato: persone, datore di lavoro, negozi, conti e importi (generati a caso con un seme fisso, quindi
sempre uguali). Gli schemi ricalcano un uso realistico dell'app, così ogni funzione ha qualcosa da mostrare:
stipendio l'ultimo giorno lavorativo, affitto, bollette, abbonamenti (uno con aumento di prezzo), spesa, ristoranti,
carburante, un viaggio in dollari, giroconti tra i due conti, dividendi di un ETF con ritenute e bollo, un addebito
doppio e una spesa importante per gli avvisi, obiettivi di risparmio e saldi dei conti per la previsione.
Al massimo 500 movimenti in tutto.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

import pandas as pd

from core import db, i18n

MAX_TX = 500
OWNER = "Luca Bianchi"
MAIN, ONLINE = "Conto Corrente", "Conto Online"
SEEDED_KEY = "demo_seeded"
USD_EUR = 0.92

SHOPS = {
    "Spesa alimentare": [("SUPERMERCATO SOLE MILANO", 25, 95), ("COOP DELLA VALLE", 15, 70), ("DISCOUNT PIU'", 10, 45),
                         ("MERCATO RIONALE", 8, 30), ("PANIFICIO LE SPIGHE", 3, 12)],
    "Ristoranti e bar": [("BAR CENTRALE", 1.5, 7), ("PIZZERIA DA GINO", 18, 45), ("SUSHI KUMO", 22, 55),
                         ("TRATTORIA IL PORTICO", 25, 60), ("CAFFE' DEL CORSO", 2, 9), ("BURGER LAB", 12, 28)],
    "Carburante": [("STAZIONE Q-ENERGY", 40, 72), ("DISTRIBUTORE AURORA", 35, 65)],
    "Trasporti pubblici": [("METRO CITTA' BIGLIETTI", 2.2, 10), ("TAXI RAPIDO", 12, 28)],
    "Shopping e acquisti online": [("SHOPONLINE MARKET", 12, 95), ("TECNOSTORE", 20, 140)],
    "Abbigliamento e scarpe": [("MODA URBANA", 25, 90), ("SPORT & STYLE", 30, 110)],
    "Salute e farmacia": [("FARMACIA SAN MARCO", 6, 35)],
    "Svago e tempo libero": [("CINEMA ODEON", 8, 22), ("TICKETPOINT CONCERTI", 25, 70), ("BOWLING STAR", 12, 30)],
    "Cura personale": [("BARBIERE DA TONI", 15, 25)],
    "Casa: arredamento e manutenzione": [("BRICO CASA", 10, 60)],
}
FRIENDS = ["Marco Verdi", "Giulia Neri", "Paolo Gallo", "Sara Fontana"]


def _last_business_day(y: int, m: int) -> date:
    from core import recurring
    return recurring.last_business_day(y, m).date()


def generate(today: date | None = None, seed: int = 20261021) -> list[dict]:
    """Movimenti fittizi degli ultimi 12 mesi (fino a oggi)."""
    rnd = random.Random(seed)
    today = today or date.today()
    start = (today.replace(day=1) - pd.DateOffset(months=11)).date()
    rows: list[dict] = []

    def add(d: date, desc: str, amount: float, cat: str, account: str = MAIN, ccy: str = "EUR", note: str = ""):
        if d > today or d < start:
            return
        amount = round(amount, 2)
        rate = USD_EUR * (1 + rnd.uniform(-0.01, 0.01)) if ccy == "USD" else None
        rows.append({"date": d.isoformat(), "description": desc, "amount": amount, "currency": ccy,
                     "fx_rate": round(rate, 4) if rate else None,
                     "amount_base": round(amount * rate, 2) if rate else amount,
                     "base_currency": "EUR", "category": cat, "category_locked": 0, "account": account,
                     "source": "demo", "notes": note})

    months = pd.period_range(start, today, freq="M")
    for p in months:
        y, m = p.year, p.month
        dim = p.days_in_month

        def day(d):
            return date(y, m, min(d, dim))

        # entrate
        pay = _last_business_day(y, m)
        salary = 2480 + rnd.choice([0, 0, 0, 40, 85]) + (1250 if m == 12 else 0)
        add(pay, f"Stipendio da ROSSI MECCANICA S.R.L. - COMPETENZE {p.strftime('%m/%Y')}", salary, "Stipendio")
        # spese fisse
        add(day(3), "Bonifico a IMMOBILIARE AURORA - Affitto", -650, "Casa (affitto/mutuo)")
        add(day(5), "FIBRANET - Internet casa", -27.90, "Telefono e internet")
        add(day(8), "TELCOMOBILE ricarica automatica", -9.99, "Telefono e internet")
        add(day(10), "FITLAB PALESTRA - quota mensile", -39.00, "Sport e benessere")
        add(day(12), "STREAMFLIX.COM", -(8.99 if p < months[-1] else 9.99),   # aumento di prezzo questo mese
            "Abbonamenti e servizi digitali", ONLINE)
        add(day(15), "MUSICBOX PREMIUM", -10.99, "Abbonamenti e servizi digitali", ONLINE)
        add(day(20), "CLOUDDRIVE 200GB", -2.99, "Abbonamenti e servizi digitali", ONLINE)
        add(day(1), "Canone mensile conto", -2.50, "Commissioni bancarie")
        if m % 2 == 0:
            add(day(18), "LUCE&GAS ENERGIA - bolletta", -rnd.uniform(68, 125), "Bollette e utenze")
        # giroconto verso il conto online
        add(day(2), f"Bonifico a {OWNER} - Ricarica conto online", -300, "Trasferimenti tra conti")
        add(day(2), f"Ricarica da {OWNER}", 300, "Trasferimenti tra conti", ONLINE)
        add(day(rnd.randint(4, 26)), "PRELIEVO BANCOMAT", -rnd.choice([50, 50, 100]), "Contanti e prelievi")
        # spese variabili
        plan = {"Spesa alimentare": 8, "Ristoranti e bar": 6, "Carburante": 2, "Trasporti pubblici": 2,
                "Shopping e acquisti online": 2, "Svago e tempo libero": 1}
        for cat, n in plan.items():
            for _ in range(n):
                name, lo, hi = rnd.choice(SHOPS[cat])
                acc = ONLINE if cat in ("Shopping e acquisti online", "Svago e tempo libero") else MAIN
                add(day(rnd.randint(1, dim)), name, -rnd.uniform(lo, hi), cat, acc)
        for cat, prob in (("Abbigliamento e scarpe", 0.5), ("Salute e farmacia", 0.5), ("Cura personale", 0.6),
                          ("Casa: arredamento e manutenzione", 0.3)):
            if rnd.random() < prob:
                name, lo, hi = rnd.choice(SHOPS[cat])
                add(day(rnd.randint(1, dim)), name, -rnd.uniform(lo, hi), cat)
        # investimenti: dividendi trimestrali dell'ETF, ritenuta e bollo
        if m in (3, 6, 9, 12):
            gross = 40 * rnd.uniform(0.38, 0.46)
            add(day(26), "Dividendo - Div.su 40,000 ETF MSCI WORLD", gross, "Interessi e dividendi")
            add(day(26), "Ritenuta dividendo - Rit.div.su 40,000 ETF MSCI WORLD", -gross * 0.26, "Tasse e imposte")
        if m in (1, 4, 7, 10):
            add(day(8), "Imposta bollo dossier titoli", -rnd.uniform(6, 9), "Tasse e imposte")
        # amici: cene divise e rimborsi
        if rnd.random() < 0.6:
            f = rnd.choice(FRIENDS)
            add(day(rnd.randint(1, dim)), f"Bonifico da {f} - quota cena", rnd.choice([15, 20, 25, 30]), "Rimborsi")
        if rnd.random() < 0.35:
            f = rnd.choice(FRIENDS)
            add(day(rnd.randint(1, dim)), f"Bonifico a {f} - regalo di compleanno", -rnd.choice([20, 30, 50]),
                "Regali e donazioni")

    # una tantum
    y0 = months[-1].year
    add(date(y0, 1, 15) if date(y0, 1, 15) >= start else date(y0 - 1, 12, 15), "TECNOSTORE - Laptop",
        -749.00, "Shopping e acquisti online")
    big = today - timedelta(days=24)
    add(big, "MOBILI CASA NUOVA - divano", -890.00, "Casa: arredamento e manutenzione")
    # viaggio negli USA, pagato in dollari dal conto online (circa 5 mesi fa)
    trip = (today.replace(day=1) - pd.DateOffset(months=2)).date().replace(day=10)
    add(trip - timedelta(days=30), "SKYLINE AIRWAYS - volo New York", -612.40, "Viaggi e vacanze")
    for i, (name, lo, hi, cat) in enumerate([
            ("HOTEL MIDTOWN NYC", 520, 520, "Viaggi e vacanze"), ("JOE'S DINER NYC", 22, 38, "Ristoranti e bar"),
            ("CENTRAL DELI", 12, 24, "Ristoranti e bar"), ("CITY CAB NYC", 18, 35, "Trasporti pubblici"),
            ("MUSEUM PASS NYC", 45, 45, "Svago e tempo libero"), ("BROOKLYN PIZZA CO", 18, 30, "Ristoranti e bar"),
            ("SUBWAY METROCARD", 33, 33, "Trasporti pubblici"), ("TIMES SQ SOUVENIRS", 15, 40, "Shopping e acquisti online")]):
        add(trip + timedelta(days=i // 2), name, -rnd.uniform(lo, hi), cat, ONLINE, "USD")
    add(trip - timedelta(days=2), "Cambio valuta EUR > USD", -500, "Trasferimenti tra conti", ONLINE)
    add(trip - timedelta(days=2), "Cambio valuta: accredito USD", round(500 / USD_EUR, 2), "Trasferimenti tra conti", ONLINE, "USD")
    # addebito doppio recente (per gli avvisi)
    dup = today - timedelta(days=9)
    add(dup, "SHOPONLINE MARKET", -49.90, "Shopping e acquisti online", ONLINE)
    add(dup, "SHOPONLINE MARKET", -49.90, "Shopping e acquisti online", ONLINE)

    rows.sort(key=lambda r: r["date"])
    if len(rows) > MAX_TX:   # sicurezza: mai oltre il limite (si tolgono le spese variabili più vecchie)
        rows = rows[-MAX_TX:]
    seen: dict[str, int] = {}
    for r in rows:
        k = f"demo|{r['account']}|{r['date']}|{r['description']}|{r['amount']:.2f}|{r['currency']}"
        n = seen.get(k, 0)
        seen[k] = n + 1
        r["external_id"] = db.make_external_id(k, n)
    return rows


CARD_CATEGORIES = ("Spesa alimentare", "Ristoranti e bar", "Carburante", "Trasporti pubblici",
                   "Shopping e acquisti online", "Svago e tempo libero", "Abbigliamento e scarpe", "Salute e farmacia",
                   "Cura personale", "Casa: arredamento e manutenzione", "Viaggi e vacanze",
                   "Abbonamenti e servizi digitali", "Contanti e prelievi")
DEMO_CARDS = {MAIN: ("4821", "Visa Debit", "Visa del conto"), ONLINE: ("7310", "Mastercard", "Mastercard online")}


def assign_cards() -> None:
    """Carte fittizie: i pagamenti nei negozi e i prelievi del conto corrente con la Visa, quelli del conto
    online con la Mastercard (per far vedere la sezione Carte anche nell'account di prova)."""
    marks = ",".join("?" * len(CARD_CATEGORIES))
    with db.connect() as con:
        for account, (digits, kind, name) in DEMO_CARDS.items():
            con.execute(f"UPDATE transactions SET card=? WHERE account=? AND amount < 0 AND category IN ({marks})",
                        (digits, account, *CARD_CATEGORIES))
            con.execute("INSERT OR IGNORE INTO cards(account, digits, kind, name) VALUES (?,?,?,?)",
                        (account, digits, kind, name))
    db.set_setting("demo_cards", "1")


def seed(today: date | None = None) -> int:
    """Svuota il database dell'account di prova e lo riempie con i dati fittizi. Ritorna i movimenti inseriti.
    Funziona SOLO per un account ospite (mai sul database del proprietario)."""
    if not db.is_demo():
        raise RuntimeError(i18n.t("i dati di prova si possono creare solo nell'account di prova"))
    from core import forecast, securities

    today = today or date.today()
    db.init_db()
    with db.connect() as con:
        for t in ("transactions", "goal_moves", "goals", "security_trades", "instruments", "exchange_balances",
                  "exchanges", "bank_accounts", "tx_links", "cards"):
            con.execute(f"DELETE FROM {t}")
        con.execute("DELETE FROM settings WHERE key NOT IN ('base_currency','auto_update_prices','eb_app_id',"
                    "'eb_redirect_url','colors_version','rules_version')")
    db.set_setting("owner_names", OWNER.upper())
    db.set_setting("profile_name", OWNER)
    db.set_setting("profile_color", "blu")
    db.set_setting("theme", "scuro")
    db.set_setting("backup_auto", "0")      # niente backup automatici per i dati di prova
    rows = generate(today)
    ins, _ = db.insert_transactions(rows)
    assign_cards()

    tx = db.transactions_df()
    # saldi reali dei conti (per la previsione a fine mese)
    forecast.set_real_balance(MAIN, "EUR", 3480.25, tx)
    forecast.set_real_balance(ONLINE, "EUR", 412.60, tx)
    # obiettivi di risparmio
    g1 = db.save_goal({"name": "Viaggio in Giappone", "target": 3500, "deadline": date(today.year + 1, 6, 30).isoformat(),
                       "start_date": (today - timedelta(days=200)).isoformat(), "mode": "manuale", "initial": 400,
                       "color": "#F0627E"})
    for i in range(6):
        db.add_goal_move(g1, (today - timedelta(days=180 - 30 * i)).isoformat(), 200, "versamento mensile")
    db.save_goal({"name": "Fondo emergenza", "target": 6000, "deadline": None,
                  "start_date": (today - timedelta(days=120)).isoformat(), "mode": "risparmio", "initial": 2500,
                  "color": "#14AE9E"})
    # portafoglio titoli: l'ETF che paga i dividendi
    securities.save_instrument("IE00B4L5Y983", "SWDA.MI", "iShares Core MSCI World", "ETF", "EUR",
                               "Titolo dell'account di prova")
    securities.add_trade("IE00B4L5Y983", date(today.year - 1, 3, 10), "acquisto", 40, 82.50, 0, "EUR", MAIN,
                         "Acquisto di prova")
    db.set_setting(SEEDED_KEY, json.dumps({"when": date.today().isoformat(), "rows": ins}))
    return ins


def ensure_seeded() -> None:
    """Da chiamare dopo l'accesso con un account ospite: crea i dati di prova la prima volta."""
    if db.is_demo() and not db.get_setting(SEEDED_KEY, ""):
        seed()
    elif db.is_demo() and not db.get_setting("demo_cards", ""):
        assign_cards()   # account di prova creato prima della sezione Carte
