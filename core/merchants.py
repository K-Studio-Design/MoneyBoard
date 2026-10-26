"""Riconoscimento dell'esercente (o della persona) dalla descrizione di un movimento."""
import re

# prefissi che non identificano l'esercente (intermediari di pagamento, tipo di operazione)
_GENERIC = ["pagamento a favore di", "pagamento da parte di", "pagamento da", "bonifico istantaneo",
            "bonifico sepa italia", "bonifico sepa estero", "bonifico", "addebito", "transfer to", "transfer from",
            "to", "from", "a", "da", "sumup", "paypal", "sq", "zettle", "nexi", "accr.su carta finecocard debit",
            "storno operaz.finecocard debit", "rettifica valuta"]
# parole che indicano il tipo di locale, non il locale: servono due parole ("osteria senza")
_SHOP_WORDS = {"osteria", "ristorante", "rist", "pizzeria", "trattoria", "bar", "farmacia", "hotel", "caffe",
               "caffè", "cafe", "pasticceria", "gelateria", "supermercato", "panificio", "macelleria", "parcheggio",
               "pub", "agriturismo", "albergo", "tabaccheria", "libreria", "ottica", "the", "la", "il", "lo", "le",
               "gruppo", "bagno", "antica", "piscina", "cantina", "azienda", "ditta", "studio", "centro", "spazio"}
_STOP = {"da", "di", "del", "della", "dei", "e", "al", "alla", "in", "srl", "spa", "s", "p", "a", "de", "du", "and"}
_TRANSFER_PREFIX = ("pagamento a favore di", "pagamento da parte di", "pagamento da", "bonifico", "transfer",
                    "to ", "from ")


def merchant_key(description: str) -> str:
    """Chiave che raggruppa le descrizioni dello stesso esercente o della stessa persona.
    Es.: 'SEGAFREDO MILANO' e 'Segafredo' -> 'segafredo'; 'Netflix.com Los Gatos' -> 'netflix'."""
    t = str(description or "").lower()
    t = re.sub(r"\*\s*[a-z0-9]*\d[a-z0-9]*", " ", t)          # codici tipo *BB2QD9Q65
    t = re.sub(r"[^a-zà-ü0-9 ]", " ", t)
    t = re.sub(r"\b\d+\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    person = t.startswith(_TRANSFER_PREFIX)
    changed = True
    while changed:
        changed = False
        for g in _GENERIC:
            if t.startswith(g + " "):
                t = t[len(g) + 1:].strip()
                changed = True
    t = re.sub(r"^(?:a|da|di)\s+", "", t)
    toks = [w for w in t.split() if w]
    if not toks:
        return re.sub(r"\s+", " ", str(description or "").lower()).strip()
    if person:
        return " ".join(toks[:2])
    if len(toks[0]) < 5 or toks[0] in _SHOP_WORDS:
        # parole consecutive fino alla prima "distintiva" (max 3): "ristorante da loredana", "osteria senza"
        out = []
        for w in toks[:3]:
            out.append(w)
            if len(out) >= 2 and w not in _SHOP_WORDS and w not in _STOP:
                break
        return " ".join(out)
    return toks[0]


def rule_keyword(description: str, key: str) -> str:
    """Testo da usare come regola: il tratto della descrizione originale che corrisponde alla chiave
    (es. chiave 'rist pizzeria madera' -> 'rist. pizzeria madera'), così la regola la riconosce davvero."""
    low = str(description or "").lower()
    toks = key.split()
    m = re.search(r"(?<!\w)" + r"[^\w]+".join(re.escape(t) for t in toks) + r"(?!\w)", low)
    return m.group(0) if m else key


# chiavi poco leggibili prodotte da descrizioni bancarie comuni
_PRETTY = {"europe": "PayPal", "riten": "Ritenute fiscali", "rit": "Ritenute fiscali", "imposta": "Imposte",
           "canone": "Canone del conto", "paga in rate": "PayPal, pagamento a rate"}


def pretty_name(description: str, key: str) -> str:
    """Nome leggibile per un esercente: la parte della descrizione originale che corrisponde alla chiave,
    con le maiuscole originali (es. 'SpotifyIT'); se è tutta maiuscola diventa 'Iniziali Maiuscole'."""
    if key in _PRETTY:
        return _PRETTY[key]
    text = str(description or "")
    toks = key.split()
    m = re.search(r"(?<!\w)" + r"[^\w]+".join(re.escape(t) for t in toks) + r"(?!\w)", text, flags=re.I) if toks else None
    name = m.group(0) if m else key
    if name.isupper() or name.islower():
        name = name.title()
    return name
