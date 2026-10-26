"""Rendite e costi degli investimenti ricavati dai movimenti del conto (estratti Fineco e simili).

Dall'estratto del conto si vedono:
- dividendi lordi:   «Dividendo Italia - Div.su 286,000 ETF ISHARES S&P 500»          (+)
- ritenute:          «Riten.DIVIDENDI ETF armoniz. - Rit.div.su 286,000 ETF ISHARES…»  (−)
                     «Ritenuta dividendo estero - Rit.div.su 10,000 NVIDIA»            (−)
- imposta di bollo sul dossier titoli, imposta sostitutiva sul capital gain.
Dal testo «Div.su <quantità> <titolo>» si ricava anche quante quote avevi alla data del dividendo.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

RE_DIV = re.compile(r"div\.?\s*su\s+([\d.,]+)\s+(.+?)\s*$", re.I)
RE_BOLLO = re.compile(r"imposta (?:di )?bollo (?:dossier|titoli|deposito)", re.I)
RE_CGT = re.compile(r"imposta sostitutiva.*(?:capit|gain|plusval)", re.I)


def _qty(s: str) -> float | None:
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _base_val(df: pd.DataFrame) -> pd.Series:
    if "valore_base" in df:
        return df["valore_base"]
    return df["amount_base"].where(df["amount_base"].notna(), df["amount"])


def extract(df: pd.DataFrame) -> pd.DataFrame:
    """Movimenti legati agli investimenti, con tipo ('dividendo', 'ritenuta', 'bollo', 'capital gain'),
    titolo e quantità. df: movimenti (db.transactions_df o ui.prepared_transactions)."""
    if df.empty:
        return pd.DataFrame(columns=["date", "tipo", "titolo", "quantita", "importo", "id", "account"])
    rows = []
    val = _base_val(df)
    for (_, r), v in zip(df.iterrows(), val):
        desc = str(r["description"] or "")
        if pd.isna(v):
            continue
        m = RE_DIV.search(desc)
        if m:
            tipo = "ritenuta" if (v < 0 or re.search(r"\brit", desc, re.I)) else "dividendo"
            rows.append({"date": r["date"], "tipo": tipo, "titolo": m.group(2).strip().upper(),
                         "quantita": _qty(m.group(1)), "importo": float(v), "id": int(r["id"]), "account": r["account"]})
        elif RE_BOLLO.search(desc):
            rows.append({"date": r["date"], "tipo": "bollo", "titolo": "", "quantita": None, "importo": float(v),
                         "id": int(r["id"]), "account": r["account"]})
        elif RE_CGT.search(desc):
            rows.append({"date": r["date"], "tipo": "capital gain", "titolo": "", "quantita": None,
                         "importo": float(v), "id": int(r["id"]), "account": r["account"]})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"])
    return out


def per_security(inc: pd.DataFrame) -> pd.DataFrame:
    """Per titolo: dividendi lordi, ritenute, netto, numero di stacchi, ultime quote note e data."""
    d = inc[inc["tipo"].isin(["dividendo", "ritenuta"])]
    if d.empty:
        return pd.DataFrame(columns=["Titolo", "Lordo", "Ritenute", "Netto", "Stacchi", "Quote", "Al", "Ultimo anno"])
    year_ago = pd.Timestamp.today() - pd.DateOffset(years=1)
    rows = []
    for t, g in d.groupby("titolo"):
        div = g[g["tipo"] == "dividendo"]
        last = div.sort_values("date").iloc[-1] if not div.empty else g.sort_values("date").iloc[-1]
        rows.append({
            "Titolo": t.title().replace("Etf", "ETF").replace("S&P", "S&P"),
            "chiave": t,
            "Lordo": float(div["importo"].sum()),
            "Ritenute": float(g.loc[g["tipo"] == "ritenuta", "importo"].sum()),
            "Netto": float(g["importo"].sum()),
            "Stacchi": int(len(div)),
            "Quote": last["quantita"],
            "Al": last["date"],
            "Ultimo anno": float(g.loc[g["date"] >= year_ago, "importo"].sum()),
        })
    return pd.DataFrame(rows).sort_values("Netto", ascending=False)


def per_year(inc: pd.DataFrame) -> pd.DataFrame:
    if inc.empty:
        return pd.DataFrame()
    x = inc.copy()
    x["Anno"] = x["date"].dt.year
    t = x.pivot_table(index="Anno", columns="tipo", values="importo", aggfunc="sum", fill_value=0.0)
    for c in ["dividendo", "ritenuta", "bollo", "capital gain"]:
        if c not in t:
            t[c] = 0.0
    t["netto"] = t[["dividendo", "ritenuta", "bollo", "capital gain"]].sum(axis=1)
    return t.reset_index()


def match_instrument(title: str, instruments: pd.DataFrame) -> str | None:
    """ISIN del titolo registrato che somiglia di più al nome letto nel dividendo (o None)."""
    if instruments.empty:
        return None

    def norm(s):
        s = re.sub(r"[^a-z0-9&]+", " ", str(s).lower())
        return " ".join(w for w in s.split() if w not in {"etf", "ucits", "acc", "dist", "usd", "eur", "spa", "inc",
                                                          "corp", "nv", "plc", "the", "core", "shares"})
    t = norm(title)
    best, score = None, 0.0
    for r in instruments.itertuples():
        for cand in (r.name, r.ticker):
            sc = SequenceMatcher(None, t, norm(cand)).ratio()
            if t and norm(cand) and (t in norm(cand) or norm(cand) in t):
                sc = max(sc, 0.9)
            if sc > score:
                best, score = r.isin, sc
    return best if score >= 0.6 else None
