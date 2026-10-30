"""Versione dell'app e autore (mostrati in fondo alla barra laterale)."""

APP_VERSION = "1.2.1"
AUTHOR = "K Studio Design"
GITHUB_REPO = "K-Studio-Design/MoneyBoard"            # dove si controllano le nuove versioni
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def credit_markdown() -> str:
    """Righe «versione» e «made by» per la barra laterale."""
    return f"MoneyBoard v{APP_VERSION}  \nMade by **{AUTHOR}** in Italy"
