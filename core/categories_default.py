"""Categorie e regole di categorizzazione predefinite (modificabili dall'app)."""

# (nome, tipo, icona, colore)
# colori precedenti (v1), usati per aggiornare solo le categorie mai ricolorate dall'utente
OLD_COLORS_V1 = {'Spesa alimentare': '#2E7D32', 'Ristoranti e bar': '#EF6C00', 'Casa (affitto/mutuo)': '#5D4037', 'Bollette e utenze': '#F9A825', 'Telefono e internet': '#0277BD', 'Trasporti pubblici': '#00838F', 'Carburante': '#C62828', 'Auto e moto': '#AD1457', 'Salute e farmacia': '#D81B60', 'Abbigliamento e scarpe': '#8E24AA', 'Shopping e acquisti online': '#6A1B9A', 'Abbonamenti e servizi digitali': '#3949AB', 'Svago e tempo libero': '#1E88E5', 'Viaggi e vacanze': '#039BE5', 'Sport e benessere': '#43A047', 'Cura personale': '#EC407A', 'Istruzione e libri': '#7CB342', 'Regali e donazioni': '#FF7043', 'Animali domestici': '#8D6E63', 'Figli e famiglia': '#FFB300', 'Casa: arredamento e manutenzione': '#6D4C41', 'Assicurazioni': '#546E7A', 'Tasse e imposte': '#455A64', 'Commissioni bancarie': '#78909C', 'Contanti e prelievi': '#9E9D24', 'Altre spese': '#9E9E9E', 'Stipendio': '#1B5E20', 'Rimborsi': '#26A69A', 'Interessi e dividendi': '#00695C', 'Altre entrate': '#66BB6A', 'Trasferimenti tra conti': '#BDBDBD', 'Investimenti': '#90A4AE'}
OLD_COLORS_V2 = {'Spesa alimentare': '#3E8E7E', 'Ristoranti e bar': '#D0675F', 'Casa (affitto/mutuo)': '#B07D3A', 'Bollette e utenze': '#4C6EB1', 'Telefono e internet': '#8A63B0', 'Trasporti pubblici': '#2E95A3', 'Carburante': '#B85A7A', 'Auto e moto': '#6E8F3E', 'Salute e farmacia': '#5A7A8C', 'Abbigliamento e scarpe': '#C49A3A', 'Shopping e acquisti online': '#9C6B4E', 'Abbonamenti e servizi digitali': '#4F8FC0', 'Svago e tempo libero': '#A05C8F', 'Viaggi e vacanze': '#5E9C6A', 'Sport e benessere': '#C27C4A', 'Cura personale': '#6D6FA8', 'Istruzione e libri': '#3F7F96', 'Regali e donazioni': '#B2685B', 'Animali domestici': '#7C8B4A', 'Figli e famiglia': '#8F7A9E', 'Casa: arredamento e manutenzione': '#5D8C8A', 'Assicurazioni': '#A88A5A', 'Tasse e imposte': '#7A6E66', 'Commissioni bancarie': '#8E8A86', 'Contanti e prelievi': '#8A939C', 'Altre spese': '#A3ABB5', 'Stipendio': '#1E9E74', 'Rimborsi': '#3BB3A0', 'Interessi e dividendi': '#2C8C6B', 'Altre entrate': '#7CC4A8', 'Trasferimenti tra conti': '#B8BEC6', 'Investimenti': '#8B95A1'}
COLORS_VERSION = 3

# tipo: 'uscita' | 'entrata' | 'neutro' (neutro = escluso dalle statistiche, es. giroconti)
DEFAULT_CATEGORIES = [
    ("Spesa alimentare", "uscita", "🛒", "#22B8A7"),
    ("Ristoranti e bar", "uscita", "🍽️", "#F0627E"),
    ("Casa (affitto/mutuo)", "uscita", "🏠", "#F59E4C"),
    ("Bollette e utenze", "uscita", "💡", "#4C8DF6"),
    ("Telefono e internet", "uscita", "📱", "#7C5CFC"),
    ("Trasporti pubblici", "uscita", "🚆", "#2EC4D6"),
    ("Carburante", "uscita", "⛽", "#E86AC5"),
    ("Auto e moto", "uscita", "🚗", "#6BCB77"),
    ("Salute e farmacia", "uscita", "💊", "#5B7CFA"),
    ("Abbigliamento e scarpe", "uscita", "👕", "#F7C55E"),
    ("Shopping e acquisti online", "uscita", "🛍️", "#FF8F6B"),
    ("Abbonamenti e servizi digitali", "uscita", "📺", "#46A6FF"),
    ("Svago e tempo libero", "uscita", "🎭", "#A86BEA"),
    ("Viaggi e vacanze", "uscita", "✈️", "#3BBF8F"),
    ("Sport e benessere", "uscita", "🏋️", "#FFB547"),
    ("Cura personale", "uscita", "💇", "#8E7CF8"),
    ("Istruzione e libri", "uscita", "📚", "#54C6EB"),
    ("Regali e donazioni", "uscita", "🎁", "#F27059"),
    ("Animali domestici", "uscita", "🐾", "#9AD35D"),
    ("Figli e famiglia", "uscita", "👶", "#C77DFF"),
    ("Casa: arredamento e manutenzione", "uscita", "🔧", "#2FA89A"),
    ("Assicurazioni", "uscita", "🛡️", "#E8A04C"),
    ("Tasse e imposte", "uscita", "🏛️", "#7D8CC4"),
    ("Commissioni bancarie", "uscita", "🏦", "#B07AA1"),
    ("Contanti e prelievi", "uscita", "💵", "#8FA3B8"),
    ("Altre spese", "uscita", "❓", "#B9B4CF"),
    ("Stipendio", "entrata", "💼", "#14AE9E"),
    ("Rimborsi", "entrata", "🔁", "#4FD3C1"),
    ("Interessi e dividendi", "entrata", "📈", "#7C5CFC"),
    ("Altre entrate", "entrata", "💰", "#8FD9C9"),
    ("Trasferimenti tra conti", "neutro", "↔️", "#C9C6D8"),
    ("Investimenti", "neutro", "📊", "#A3A0B5"),
]

# nome inglese delle categorie predefinite (mostrato quando l'app è in inglese; modificabile in Impostazioni)
CATEGORIES_EN = {
    "Spesa alimentare": "Groceries",
    "Ristoranti e bar": "Restaurants and bars",
    "Casa (affitto/mutuo)": "Housing (rent/mortgage)",
    "Bollette e utenze": "Bills and utilities",
    "Telefono e internet": "Phone and internet",
    "Trasporti pubblici": "Public transport",
    "Carburante": "Fuel",
    "Auto e moto": "Car and motorbike",
    "Salute e farmacia": "Health and pharmacy",
    "Abbigliamento e scarpe": "Clothing and shoes",
    "Shopping e acquisti online": "Shopping and online purchases",
    "Abbonamenti e servizi digitali": "Subscriptions and digital services",
    "Svago e tempo libero": "Entertainment and leisure",
    "Viaggi e vacanze": "Travel and holidays",
    "Sport e benessere": "Sports and wellness",
    "Cura personale": "Personal care",
    "Istruzione e libri": "Education and books",
    "Regali e donazioni": "Gifts and donations",
    "Animali domestici": "Pets",
    "Figli e famiglia": "Children and family",
    "Casa: arredamento e manutenzione": "Home: furniture and maintenance",
    "Assicurazioni": "Insurance",
    "Tasse e imposte": "Taxes",
    "Commissioni bancarie": "Bank fees",
    "Contanti e prelievi": "Cash and withdrawals",
    "Altre spese": "Other expenses",
    "Stipendio": "Salary",
    "Rimborsi": "Refunds",
    "Interessi e dividendi": "Interest and dividends",
    "Altre entrate": "Other income",
    "Trasferimenti tra conti": "Transfers between accounts",
    "Investimenti": "Investments",
}
CATEGORIES_EN_VERSION = 1

# (parola chiave, categoria). La corrispondenza è "parola intera", senza maiuscole.
# Se più regole corrispondono vince la priorità più alta, poi la parola chiave più lunga
# (es. "amazon prime" batte "amazon").
_R = {
    "Spesa alimentare": [
        "esselunga", "coop", "conad", "lidl", "carrefour", "eurospin", "penny market", "aldi",
        "despar", "interspar", "eurospar", "bennet", "famila", "tigros", "unes", "naturasi",
        "pam panorama", "pam local", "iper la grande i", "ipercoop", "tosano", "todis", "md discount",
        "supermercato", "alimentari", "panificio", "macelleria", "ortofrutta", "il gigante",
        "basko", "crai", "sigma", "decò", "dpiu", "prix quality", "in's mercato", "carrefour express",
    ],
    "Ristoranti e bar": [
        "ristorante", "pizzeria", "trattoria", "osteria", "bar", "caffe", "caffè", "cafe",
        "mcdonald", "mcdonalds", "burger king", "kfc", "starbucks", "autogrill", "just eat",
        "deliveroo", "glovo", "uber eats", "sushi", "paninoteca", "gelateria", "pasticceria",
        "roadhouse", "old wild west", "poke", "rosticceria", "bistrot", "pub", "spizzico",
    ],
    "Casa (affitto/mutuo)": ["affitto", "canone locazione", "rata mutuo", "mutuo", "condominio", "spese condominiali"],
    "Bollette e utenze": [
        "enel", "enel energia", "a2a", "iren", "hera", "edison", "acea", "sorgenia", "plenitude",
        "eni plenitude", "servizio elettrico nazionale", "illumia", "octopus energy", "bolletta",
        "acquedotto", "tari", "e.on", "engie", "estra", "dolomiti energia", "metropolitana milanese",
    ],
    "Telefono e internet": [
        "tim", "telecom italia", "vodafone", "windtre", "wind tre", "iliad", "fastweb", "ho mobile",
        "kena mobile", "very mobile", "postemobile", "tiscali", "sky wifi", "eolo", "coopvoce",
    ],
    "Trasporti pubblici": [
        "trenitalia", "italo", "ntv", "trenord", "gtt", "atac", "atm milano", "flixbus", "itabus",
        "uber", "free now", "freenow", "taxi", "metro", "tper", "busitalia", "cotral", "moovit",
    ],
    "Carburante": [
        "q8", "tamoil", "esso", "shell", "enilive", "eni station", "agip", "totalerg", "total energies",
        "carburante", "carburanti", "benzina", "distributore", "stazione di servizio", "italiana petroli",
    ],
    "Auto e moto": [
        "autostrade", "autostrade per l'italia", "telepass", "unipolmove", "parcheggio", "easypark",
        "bollo auto", "meccanico", "gommista", "officina", "revisione", "carrozzeria", "autolavaggio",
        "mytaxi parking", "aci", "ricarica auto", "ionity", "enel x way",
    ],
    "Salute e farmacia": [
        "farmacia", "parafarmacia", "ospedale", "dentista", "odontoiatra", "medico", "poliambulatorio",
        "centro medico", "ottica", "ottico", "ticket sanitario", "analisi cliniche", "laboratorio analisi",
        "fisioterapia", "veterinaria",
    ],
    "Abbigliamento e scarpe": [
        "zara", "h&m", "primark", "ovs", "uniqlo", "bershka", "pull&bear", "calzedonia", "intimissimi",
        "foot locker", "tezenis", "piazza italia", "benetton", "pittarello", "scarpe", "zalando",
        "stradivarius", "mango", "massimo dutti", "nike", "adidas", "terranova",
    ],
    "Shopping e acquisti online": [
        "amazon", "amzn", "ebay", "aliexpress", "temu", "shein", "mediaworld", "unieuro", "euronics",
        "trony", "apple store", "paypal", "vinted", "subito", "flying tiger",
    ],
    "Abbonamenti e servizi digitali": [
        "netflix", "spotify", "disney plus", "disneyplus", "prime video", "amazon prime", "dazn", "sky",
        "now tv", "apple.com", "icloud", "google one", "youtube premium", "chatgpt", "openai",
        "anthropic", "claude.ai", "microsoft", "adobe", "audible", "paramount", "timvision",
        "infinity", "dropbox", "github",
    ],
    "Svago e tempo libero": [
        "cinema", "the space", "uci cinemas", "ticketone", "vivaticket", "teatro", "museo", "concerto",
        "steam", "playstation", "nintendo", "xbox", "bowling", "luna park", "gardaland", "discoteca",
    ],
    "Viaggi e vacanze": [
        "booking.com", "airbnb", "ryanair", "easyjet", "wizz air", "ita airways", "alitalia", "expedia",
        "hotel", "volotea", "vueling", "lufthansa", "trivago", "hostel", "b&b", "agenzia viaggi",
        "edreams", "lastminute", "skyscanner", "hertz", "europcar", "avis", "sixt", "aeroporto",
    ],
    "Sport e benessere": [
        "palestra", "virgin active", "mcfit", "decathlon", "piscina", "fitness", "gym", "yoga",
        "centro sportivo", "skipass", "terme",
    ],
    "Cura personale": [
        "parrucchiere", "barbiere", "estetista", "sephora", "douglas", "kiko", "acqua & sapone",
        "acqua e sapone", "tigota", "pinalli", "profumeria", "beauty",
    ],
    "Istruzione e libri": [
        "feltrinelli", "mondadori", "libreria", "giunti", "universita", "università", "corso online",
        "udemy", "coursera", "scuola", "tasse universitarie", "cartoleria",
    ],
    "Regali e donazioni": ["donazione", "regalo", "unicef", "emergency", "medici senza frontiere", "gofundme", "fiorista", "fioraio"],
    "Animali domestici": ["veterinario", "arcaplanet", "isola dei tesori", "zooplus", "maxi zoo", "pet shop", "toelettatura"],
    "Figli e famiglia": ["asilo", "baby sitter", "babysitter", "giocattoli", "toys center", "prenatal", "chicco", "mensa scolastica"],
    "Casa: arredamento e manutenzione": [
        "ikea", "leroy merlin", "bricoman", "brico", "obi", "mondo convenienza", "maisons du monde",
        "idraulico", "elettricista", "ferramenta", "jysk", "kasanova", "zara home", "brico io",
    ],
    "Assicurazioni": [
        "assicurazione", "assicurazioni", "unipol", "unipolsai", "generali", "allianz", "axa", "zurich insurance",
        "zurich connect",
        "prima assicurazioni", "genertel", "linear", "verti", "direct line", "conte.it", "reale mutua",
        "cattolica", "polizza",
    ],
    "Tasse e imposte": [
        "f24", "agenzia entrate", "agenzia delle entrate", "imposta di bollo", "pagopa", "tributi",
        "imu", "comune di", "multa", "sanzione", "canone rai",
    ],
    "Commissioni bancarie": [
        "commissione", "commissioni", "spese tenuta conto", "canone conto", "costo bonifico",
        "canone carta", "spese invio", "fee",
    ],
    "Contanti e prelievi": ["prelievo", "prelevamento", "atm", "bancomat", "cash withdrawal"],
    "Stipendio": ["stipendio", "emolumenti", "retribuzione", "busta paga", "salary"],
    "Rimborsi": ["rimborso", "refund", "storno", "reso", "cashback"],
    "Interessi e dividendi": ["cedola", "dividendo", "dividendi", "interessi creditori", "interest", "interessi"],
    "Trasferimenti tra conti": [
        "giroconto", "ricarica revolut", "revolut", "top-up", "top up", "trasferimento tra conti",
        "bonifico a me stesso", "ricarica carta", "satispay ricarica", "to eur", "to usd", "exchanged to",
        "pocket", "vault", "salvadanaio",
    ],
    "Investimenti": [
        "compravendita titoli", "acquisto titoli", "vendita titoli", "eseguito ordine", "trade republic",
        "directa", "scalable capital", "degiro", "moneyfarm", "fondo pensione", "piano di accumulo", "eseguito acquisto",
        "eseguito vendita", "coinbase", "binance", "kraken", "bitpanda", "young platform",
    ],
}

# Regole aggiunte nella versione 2 (estratti Fineco reali)
_R2 = {
    "Commissioni bancarie": ["canone", "canone mensile", "canone annuo", "quota associativa",
                             "spese sostituzione carta", "spese riemissione", "commiss", "comm.prel",
                             "sconto canone"],
    "Tasse e imposte": ["imposta bollo", "imposta sostitutiva", "ritenuta", "riten", "cbill", "bollettino"],
    "Interessi e dividendi": ["div.su", "dividendo italia", "dividendo"],
    "Investimenti": ["interactive brokers", "ibkr", "trading 212", "etoro"],
    "Trasporti pubblici": ["lime", "bolt", "mobike", "share now"],
    "Ristoranti e bar": ["grill", "kebab", "piadineria", "burger", "ramen", "enoteca", "birreria",
                         "signorvino", "segafredo", "bauli", "panetteria", "rostipollo", "brewdog",
                         "ristorazione", "ristorazi", "mychef", "aramark", "chef express", "camst"],
    "Svago e tempo libero": ["ondaland", "acquapark", "parco acquatico", "deviantart", "supercell",
                             "bowling", "playstation network"],
    "Abbonamenti e servizi digitali": ["google play", "prime video"],
    "Auto e moto": ["autoscuola", "norauto", "drivalia", "noleggio auto", "autosilo"],
}
# Revolut (estratto consolidato) e spese all'estero
_R2["Trasferimenti tra conti"] = ["conto deposito", "conversione in", "exchanged to", "ricarica di"]
_R2["Investimenti"] += ["revolut digital assets", "revolut securities"]
_R2["Auto e moto"] += ["satap", "autostrada", "autostrade", "autoroutes", "tollway", "ipass", "concessioni del tirreno",
                       "spothero", "parkchicago", "parkingmeter", "parkmobile", "car wash", "pedaggio"]
_R2["Carburante"] = ["bp", "love's travel stop", "pilot travel", "chevron", "marathon", "speedway", "circle k",
                     "ip italiana petroli", "eni"]
_R2["Spesa alimentare"] = ["walmart", "target", "jewel-osco", "whole foods", "meijer", "7-eleven", "trader joe's",
                           "costco", "fresh market", "fresh mrkt", "binny's", "dispensa emilia", "kroger",
                           "dollar tree", "mrkt", "bakery"]
_R2["Ristoranti e bar"] += ["mcdonald's", "dunkin", "portillo's", "taco", "pancake", "steak", "thai", "beer",
                            "cider", "pizza", "doppio malto", "caffetteria", "gelateri", "speakeasy", "nightclub",
                            "cafe", "diner", "wood fire", "ramen"]
_R2["Svago e tempo libero"] += ["topgolf", "amc theatres", "theatres", "zoo", "bzoo", "shooters", "eventdiox",
                                "midaticket", "webtic", "vivaticket", "ticketmaster"]
_R2["Abbonamenti e servizi digitali"] += ["claude", "patreon", "canone piano premium", "revolut premium"]
_R2["Telefono e internet"] = ["comcast", "mint mobile", "t-mobile", "at&t", "verizon"]
_R2["Viaggi e vacanze"] = ["airlines", "american airlines", "united airlines", "delta air", "airbnb", "hotel"]
_R2["Shopping e acquisti online"] = ["best buy", "menards", "home depot", "funko", "pawn shop"]

# Satispay: la ricarica del borsellino è di fatto spesa (gli acquisti non sono visibili nell'estratto)
_R2["Altre spese"] = ["satispay"]
_R2["Trasporti pubblici"] += ["wetaxi", "gruppo torinese trasporti", "it taxi", "appentaxi"]
# Chase (USA): giroconti, stipendio, commissioni e servizi americani comuni
_R2["Trasferimenti tra conti"] += ["online transfer to", "online transfer from", "chase credit crd",
                                   "payment to chase card", "payment thank you", "automatic payment - thank",
                                   "transfer to sav", "transfer from sav", "transfer to chk", "transfer from chk"]
_R2.setdefault("Stipendio", [])
_R2["Stipendio"] += ["payroll", "dir dep", "direct dep"]
_R2.setdefault("Contanti e prelievi", [])
_R2["Contanti e prelievi"] += ["atm withdrawal", "non-chase atm withdraw"]
_R2.setdefault("Commissioni bancarie", [])
_R2["Commissioni bancarie"] += ["monthly service fee", "non-chase atm fee", "foreign exch rt adj fee", "overdraft fee",
                               "insufficient funds fee", "wire transfer fee"]
_R2.setdefault("Interessi e dividendi", [])
_R2["Interessi e dividendi"] += ["interest payment"]
_R2.setdefault("Bollette e utenze", [])
_R2["Bollette e utenze"] += ["comed", "nicor gas", "peoples gas", "duke energy", "con edison", "pg&e", "xcel energy",
                            "dominion energy", "national grid"]
_R2.setdefault("Assicurazioni", [])
_R2["Assicurazioni"] += ["geico", "state farm", "progressive ins", "allstate", "lemonade ins"]
_R2["Trasporti pubblici"] += ["ventra", "metra", "lyft", "mta*nyct"]
# Versione 5: parole chiave in inglese, corrispondenti a quelle generiche in italiano (i nomi di negozi e marchi
# valgono già in entrambe le lingue). Solo parole poco ambigue: la corrispondenza è a parola intera.
_R3 = {
    "Spesa alimentare": ["supermarket", "grocery", "groceries", "grocery store", "butcher shop", "greengrocer"],
    "Ristoranti e bar": ["restaurant", "coffee shop", "ice cream", "pastry shop", "sandwich shop", "bistro",
                         "food delivery"],
    "Casa (affitto/mutuo)": ["rent payment", "mortgage", "mortgage payment", "hoa dues", "condo fees"],
    "Bollette e utenze": ["electric bill", "electricity", "utility bill", "water bill", "gas bill", "trash service"],
    "Telefono e internet": ["phone bill", "mobile plan", "internet service", "broadband"],
    "Trasporti pubblici": ["train ticket", "bus ticket", "subway", "public transit", "metro card"],
    "Carburante": ["gas station", "fuel", "gasoline", "petrol"],
    "Auto e moto": ["parking", "car repair", "auto repair", "tire shop", "oil change", "car inspection", "dmv",
                    "toll"],
    "Salute e farmacia": ["pharmacy", "hospital", "dentist", "doctor", "medical center", "clinic", "optician",
                          "urgent care", "physical therapy", "lab test"],
    "Abbigliamento e scarpe": ["clothing", "shoe store", "apparel"],
    "Shopping e acquisti online": ["online store", "electronics store", "department store"],
    "Abbonamenti e servizi digitali": ["subscription"],
    "Svago e tempo libero": ["movie theater", "movie theatre", "theater", "museum", "concert", "amusement park"],
    "Viaggi e vacanze": ["airline", "travel agency", "airport", "car rental", "hostel"],
    "Sport e benessere": ["swimming pool", "sports center", "ski pass", "fitness center"],
    "Cura personale": ["hairdresser", "hair salon", "barber shop", "beauty salon", "nail salon", "perfume"],
    "Istruzione e libri": ["bookstore", "book store", "university", "tuition", "online course", "stationery"],
    "Regali e donazioni": ["donation", "gift shop", "florist", "flower shop"],
    "Animali domestici": ["veterinarian", "vet clinic", "pet store", "pet shop", "pet grooming"],
    "Figli e famiglia": ["daycare", "kindergarten", "babysitting", "toy store", "school lunch"],
    "Casa: arredamento e manutenzione": ["plumber", "electrician", "hardware store", "furniture", "home improvement"],
    "Assicurazioni": ["insurance", "insurance premium", "insurance policy"],
    "Tasse e imposte": ["irs", "usataxpymt", "tax payment", "property tax", "stamp duty", "traffic ticket"],
    "Commissioni bancarie": ["bank fee", "service fee", "account fee", "card fee", "transfer fee", "commission"],
    "Contanti e prelievi": ["cash withdrawal"],
    "Stipendio": ["wages", "paycheck", "payroll deposit"],
    "Rimborsi": ["reimbursement"],
    "Interessi e dividendi": ["dividend", "dividends", "interest earned", "interest credit"],
    "Trasferimenti tra conti": ["transfer between accounts", "own account transfer", "internal transfer"],
    "Investimenti": ["securities purchase", "securities sale", "buy order", "sell order", "pension fund",
                     "brokerage"],
}
for _cat, _kws in _R3.items():
    _R2.setdefault(_cat, [])
    _R2[_cat] += _kws
for _cat, _kws in _R2.items():
    _R.setdefault(_cat, [])
    _R[_cat] += [k for k in dict.fromkeys(_kws) if k not in _R[_cat]]

# priorità diverse da 0 (più alta = vince). PayPal/SumUp sono intermediari: vince il nome dell'esercente.
RULE_PRIORITY = {
    ("paypal", "Shopping e acquisti online"): -1,
    ("commiss", "Commissioni bancarie"): 5,
    ("comm.prel", "Commissioni bancarie"): 5,
    ("satispay", "Altre spese"): 3,
    ("canone piano premium", "Abbonamenti e servizi digitali"): 2,
}
RULES_VERSION = 5
# regole predefinite tolte perché davano falsi positivi (es. "Zurich" città)
REMOVED_RULES = [("zurich", "Assicurazioni")]

DEFAULT_RULES = [(kw, cat) for cat, kws in _R.items() for kw in kws]

# Traduzione delle categorie "Moneymap" di Fineco (o di altre banche) verso le nostre,
# per sottostringa del nome categoria della banca.
BANK_CATEGORY_HINTS = [
    ("aliment", "Spesa alimentare"), ("supermerc", "Spesa alimentare"),
    ("ristor", "Ristoranti e bar"), ("bar", "Ristoranti e bar"),
    ("carbur", "Carburante"), ("benzin", "Carburante"),
    ("viagg", "Viaggi e vacanze"), ("vacanz", "Viaggi e vacanze"),
    ("abbigl", "Abbigliamento e scarpe"),
    ("salute", "Salute e farmacia"), ("farmac", "Salute e farmacia"), ("medic", "Salute e farmacia"),
    ("utenz", "Bollette e utenze"), ("bollet", "Bollette e utenze"),
    ("telefon", "Telefono e internet"), ("internet", "Telefono e internet"),
    ("stipend", "Stipendio"), ("tasse", "Tasse e imposte"), ("impost", "Tasse e imposte"),
    ("assicur", "Assicurazioni"), ("trasport", "Auto e moto"),
    ("auto", "Auto e moto"), ("affitt", "Casa (affitto/mutuo)"), ("mutuo", "Casa (affitto/mutuo)"),
    ("arred", "Casa: arredamento e manutenzione"), ("casa", "Casa: arredamento e manutenzione"),
    ("svago", "Svago e tempo libero"), ("tempo libero", "Svago e tempo libero"),
    ("sport", "Sport e benessere"), ("istruz", "Istruzione e libri"), ("animal", "Animali domestici"),
    ("regal", "Regali e donazioni"), ("donaz", "Regali e donazioni"), ("figli", "Figli e famiglia"),
    ("giroconto", "Trasferimenti tra conti"), ("trasfer", "Trasferimenti tra conti"),
    ("invest", "Investimenti"), ("titoli", "Investimenti"),
    ("contant", "Contanti e prelievi"), ("preliev", "Contanti e prelievi"),
    ("commission", "Commissioni bancarie"), ("abbonam", "Abbonamenti e servizi digitali"),
    ("shopping", "Shopping e acquisti online"), ("acquist", "Shopping e acquisti online"),
    ("cura", "Cura personale"), ("bellezz", "Cura personale"),
    ("commerce", "Shopping e acquisti online"), ("giochi", "Svago e tempo libero"),
    ("cultura", "Svago e tempo libero"), ("spettacol", "Svago e tempo libero"),
    ("hotel", "Viaggi e vacanze"), ("altre entrate", "Altre entrate"), ("altre spese", "Altre spese"),
    ("rimbors", "Rimborsi"), ("interess", "Interessi e dividendi"), ("dividend", "Interessi e dividendi"),
]
