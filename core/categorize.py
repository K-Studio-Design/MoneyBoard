"""Categorizzazione automatica delle transazioni tramite regole a parole chiave."""
from __future__ import annotations

import re
import unicodedata

from core import db
from core.categories_default import BANK_CATEGORY_HINTS

FALLBACK_OUT = "Altre spese"
FALLBACK_IN = "Altre entrate"
TRANSFER_CAT = "Trasferimenti tra conti"
# parole chiave da almeno questi caratteri vengono cercate anche "senza spazi", per gestire
# descrizioni spezzate dalla banca ("TELEP ASS") o attaccate ("SpotifyIT")
NOSPACE_MIN_LEN = 6
RE_REVERSAL = re.compile(r"(?<!\w)(storno|sconto|annullo|reversal)(?!\w)")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"\s+", " ", text).strip()


def _tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-zà-ü]+", _norm(name)) if len(t) >= 2]


def is_owner(name: str | None, owners: list[str]) -> bool:
    """True se `name` corrisponde a uno degli intestatari (ordine dei nomi e spazi spuri ignorati:
    'ROSS I MARIO' == 'Mario Rossi')."""
    if not name:
        return False
    squashed = re.sub(r"[^a-zà-ü]", "", _norm(name))
    for owner in owners:
        toks = _tokens(owner)
        if toks and all(t in squashed for t in toks) and len(squashed) <= len("".join(toks)) + 6:
            return True
    return False


class Categorizer:
    """Carica categorie e regole una volta sola e le applica a molte righe."""

    def __init__(self):
        cats = db.categories_df()
        self.kind = dict(zip(cats["name"], cats["kind"]))
        self.owners = db.owner_names()
        rules = db.rules_df()
        compiled = []
        for _, r in rules.iterrows():
            kw = _norm(r["keyword"])
            if not kw or r["category"] not in self.kind:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)")
            # variante tollerante: deve iniziare a inizio parola, ammette spazi spuri tra le lettere
            # e lettere attaccate dopo ("SpotifyIT", "TELEP ASS"), ma non dentro un'altra parola ("redpocket")
            chars = [c for c in kw if not c.isspace()]
            loose = (re.compile(r"(?<!\w)" + r"\s?".join(re.escape(c) for c in chars))
                     if len(chars) >= NOSPACE_MIN_LEN else None)
            compiled.append((int(r["priority"] or 0), len(kw), pattern, loose, r["category"]))
        # priorità più alta prima, poi parola chiave più lunga (più specifica)
        compiled.sort(key=lambda x: (-x[0], -x[1]))
        self.rules = compiled

    def _kind_ok(self, category: str, amount: float) -> bool:
        k = self.kind.get(category)
        if k == "uscita":
            return amount < 0
        if k == "entrata":
            return amount > 0
        return True  # neutro: valido in entrambi i sensi

    def _match(self, text: str, amount: float) -> str | None:
        for _, _, pattern, loose, cat in self.rules:
            if (pattern.search(text) or (loose and loose.search(text))) and self._kind_ok(cat, amount):
                return cat
        return None

    def categorize(self, description: str, amount: float, bank_category: str | None = None,
                   counterparty: str | None = None, reversal: bool = False) -> str:
        # 1) bonifico verso/da un proprio conto -> giroconto (non conta nelle statistiche)
        if counterparty and self.owners and is_owner(counterparty, self.owners) and TRANSFER_CAT in self.kind:
            return TRANSFER_CAT
        text = _norm(description)
        # 2) storni/sconti: stessa categoria della spesa che annullano (riducono la spesa)
        # (reversal=True: la banca indica che è un reso/rimborso di un acquisto, es. «Return» di Chase)
        if amount > 0 and (reversal or RE_REVERSAL.search(text)):
            cat = self._match(text, -amount)
            if cat and self.kind.get(cat) in ("uscita", "neutro"):
                return cat
        # 3) regole a parole chiave
        cat = self._match(text, amount)
        if cat:
            return cat
        # 4) categoria proposta dalla banca (es. Moneymap di Fineco)
        if bank_category:
            bc = _norm(bank_category)
            for hint, cat in BANK_CATEGORY_HINTS:
                if hint in bc and cat in self.kind and self._kind_ok(cat, amount):
                    return cat
        fallback = FALLBACK_OUT if amount < 0 else FALLBACK_IN
        return fallback if fallback in self.kind else (next(iter(self.kind), fallback))


def recategorize_all(only_unlocked: bool = True) -> int:
    """Riapplica le regole alle transazioni esistenti. Ritorna quante sono cambiate.
    Nota: la categoria della banca e la controparte non sono salvate, quindi qui contano solo le regole."""
    c = Categorizer()
    df = db.transactions_df()
    if only_unlocked:
        df = df[df["category_locked"].fillna(0).astype(int) == 0]
    changed = 0
    for _, r in df.iterrows():
        if r["category"] == TRANSFER_CAT and r["source"] != "manuale":
            continue  # i giroconti riconosciuti all'import restano tali
        new = c.categorize(r["description"], float(r["amount"]))
        if new in (FALLBACK_OUT, FALLBACK_IN) and r["category"] not in (FALLBACK_OUT, FALLBACK_IN):
            continue  # non perdere la categoria data dalla banca all'import
        if new != r["category"]:
            db.update_transaction(int(r["id"]), category=new)
            changed += 1
    return changed
