"""Versione dell'app e autore (mostrati in fondo alla barra laterale)."""

APP_VERSION = "1.0.0"
AUTHOR = "K Studio Design"


def credit_markdown() -> str:
    """Righe «versione» e «made by» per la barra laterale."""
    return f"MoneyBoard v{APP_VERSION}  \nMade by **{AUTHOR}** in Italy"
