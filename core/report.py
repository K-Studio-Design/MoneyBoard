"""Movimenti pronti per i calcoli (in valuta base, tutti i conti): usati da budget, riepiloghi ed email,
anche fuori dalle pagine (senza i filtri della barra laterale)."""
from __future__ import annotations

import pandas as pd

from core import db


def frame(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Colonne aggiunte: valore_base (importo in valuta base), spesa_base (spesa positiva; i rimborsi su
    categorie di spesa la riducono), entrata_base, mese (periodo mensile). Le categorie neutre valgono 0."""
    df = db.transactions_df() if df is None else df.copy()
    if df.empty:
        for c in ("valore_base", "spesa_base", "entrata_base"):
            df[c] = pd.Series(dtype=float)
        df["mese"] = pd.Series(dtype="period[M]")
        return df
    base = db.base_currency()
    val = df["amount_base"].copy()
    same = df["currency"].str.upper() == base
    df["valore_base"] = val.where(val.notna() | ~same, df["amount"])
    df["spesa_base"] = (-df["valore_base"]).where(df["kind"] == "uscita", 0.0).fillna(0.0)
    df["entrata_base"] = df["valore_base"].where(df["kind"] == "entrata", 0.0).fillna(0.0)
    df["mese"] = df["date"].dt.to_period("M")
    return df
