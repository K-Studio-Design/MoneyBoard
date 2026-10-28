"""Database SQLite locale: transazioni, categorie, regole, titoli, exchange, banche."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from core.categories_default import (CATEGORIES_EN, CATEGORIES_EN_VERSION, COLORS_VERSION, DEFAULT_CATEGORIES,
                                     DEFAULT_RULES, OLD_COLORS_V1, OLD_COLORS_V2,
                                     REMOVED_RULES, RULE_PRIORITY, RULES_VERSION)


DEFAULT_DATA_DIR = Path.home() / "AppSpese_dati"
# file "segnaposto" nella cartella predefinita: dice dove si trova il database se è stato spostato
POINTER_FILE = DEFAULT_DATA_DIR / "posizione_dati.json"


def configured_data_dir() -> Path | None:
    """Cartella scelta in Impostazioni (None se si usa quella predefinita)."""
    try:
        data = json.loads(POINTER_FILE.read_text(encoding="utf-8"))
        p = Path(data.get("data_dir", "")).expanduser()
        return p if str(p).strip() and data.get("data_dir") else None
    except (OSError, ValueError, AttributeError):
        return None


USER_KEY = "_mb_user"          # utente collegato (in st.session_state); None/"admin" = proprietario
_forced_user: str | None = None


def set_user_override(user: str | None) -> None:
    """Per script e test fuori da Streamlit: usa la cartella dati di questo utente."""
    global _forced_user
    _forced_user = user


def current_user() -> str | None:
    """Utente della sessione Streamlit in corso (None fuori da Streamlit o prima dell'accesso)."""
    if _forced_user is not None:
        return _forced_user
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx(suppress_warning=True) is None:
            return None
        import streamlit as st
        return st.session_state.get(USER_KEY)
    except Exception:
        return None


def root_data_dir() -> Path:
    """Cartella base fissa (non segue lo spostamento del database del proprietario)."""
    custom = os.environ.get("APP_SPESE_DATA")
    path = Path(custom) if custom else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_admin() -> bool:
    """Sessione dell'amministratore (o nessun utente: script, test, prima dell'accesso)."""
    u = current_user()
    return not u or u == "admin"


def is_demo() -> bool:
    """Account di prova con dati fittizi (scelto dall'Admin quando crea l'utente)."""
    if is_admin():
        return False
    from core import users
    return users.is_demo(current_user())


def get_data_dir() -> Path:
    """Cartella dati. Di default fuori da OneDrive (dati bancari personali e SQLite non vanno d'accordo con la
    sincronizzazione cloud). Si cambia da Impostazioni → Cartelle e backup (oppure, per l'Admin, con la variabile
    d'ambiente APP_SPESE_DATA, che ha la precedenza).
    Ogni utente creato dall'Admin ha la sua cartella (predefinita: <cartella base>/utenti/<id>, oppure quella
    che ha scelto lui): non vede e non tocca mai i dati degli altri."""
    if not is_admin():
        from core import users
        path = users.data_dir(current_user())
        path.mkdir(parents=True, exist_ok=True)
        return path
    custom = os.environ.get("APP_SPESE_DATA")
    if custom:
        path = Path(custom)
    else:
        path = configured_data_dir() or DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return get_data_dir() / "spese.db"


@contextmanager
def connect():
    con = sqlite3.connect(db_path(), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('uscita','entrata','neutro')),
    icon TEXT DEFAULT '',
    color TEXT DEFAULT '#888888',
    sort_order INTEGER DEFAULT 100
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    category TEXT NOT NULL REFERENCES categories(name) ON UPDATE CASCADE ON DELETE CASCADE,
    priority INTEGER DEFAULT 0,
    UNIQUE(keyword, category)
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    fx_rate REAL,
    amount_base REAL,
    base_currency TEXT,
    category TEXT,
    category_locked INTEGER DEFAULT 0,
    account TEXT DEFAULT 'Contanti',
    source TEXT DEFAULT 'manuale',
    notes TEXT DEFAULT '',
    external_id TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS ix_tx_cat ON transactions(category);

CREATE TABLE IF NOT EXISTS fx_cache (
    date TEXT NOT NULL,
    base TEXT NOT NULL,
    quote TEXT NOT NULL,
    rate REAL NOT NULL,
    PRIMARY KEY (date, base, quote)
);

CREATE TABLE IF NOT EXISTS instruments (
    isin TEXT PRIMARY KEY,
    ticker TEXT,
    name TEXT,
    asset_type TEXT DEFAULT 'ETF',
    quote_currency TEXT,
    last_price REAL,
    last_update TEXT,
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS security_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL REFERENCES instruments(isin) ON UPDATE CASCADE ON DELETE CASCADE,
    date TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('acquisto','vendita')),
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fees REAL DEFAULT 0,
    currency TEXT NOT NULL,
    account TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange_id TEXT NOT NULL,
    label TEXT,
    api_key TEXT,
    secret TEXT,
    password TEXT,
    last_sync TEXT
);
CREATE TABLE IF NOT EXISTS exchange_balances (
    exchange_row INTEGER REFERENCES exchanges(id) ON DELETE CASCADE,
    asset TEXT,
    amount REAL,
    value_base REAL,
    updated TEXT,
    PRIMARY KEY (exchange_row, asset)
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    uid TEXT PRIMARY KEY,
    session_id TEXT,
    aspsp_name TEXT,
    aspsp_country TEXT,
    account_name TEXT,
    iban TEXT,
    currency TEXT,
    valid_until TEXT,
    last_sync TEXT,
    label TEXT
);

-- stesso movimento arrivato da un'altra fonte (es. estratto e collegamento banca): l'id esterno della copia
-- scartata punta al movimento tenuto (tx_id NULL = da ignorare), così non viene reinserito
CREATE TABLE IF NOT EXISTS tx_links (
    external_id TEXT PRIMARY KEY,
    tx_id INTEGER,
    family TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cards (
    account TEXT NOT NULL,
    digits TEXT NOT NULL,
    kind TEXT DEFAULT '',
    name TEXT DEFAULT '',
    hidden INTEGER DEFAULT 0,
    PRIMARY KEY (account, digits)
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target REAL NOT NULL,
    deadline TEXT,                 -- data entro cui raggiungerlo (facoltativa)
    start_date TEXT NOT NULL,      -- da quando si conta
    mode TEXT NOT NULL DEFAULT 'manuale',   -- manuale | conto | risparmio
    account TEXT,                  -- per mode='conto'
    account_ccy TEXT,
    balance_offset REAL DEFAULT 0, -- per mode='conto': saldo reale - somma dei movimenti importati
    initial REAL DEFAULT 0,        -- già messo da parte all'inizio (manuale / risparmio)
    color TEXT DEFAULT '#7C5CFC',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- budget mensile per categoria (in valuta base)
CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY REFERENCES categories(name) ON UPDATE CASCADE ON DELETE CASCADE,
    amount REAL NOT NULL
);

-- spese condivise: persone e quanto ti devono (importo positivo) o devi tu (negativo)
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    archived INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS shared (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    description TEXT DEFAULT '',
    amount REAL NOT NULL,          -- > 0: questa persona ti deve; < 0: tu devi a lei
    currency TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'manuale',   -- quota | rimborso | manuale | saldo
    tx_id INTEGER,                 -- movimento collegato (quota divisa o rimborso), se c'è
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goal_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT DEFAULT ''
);
"""

SHARED_CATEGORY = "Spese condivise"   # neutra: la parte di una spesa che ti verrà restituita

DEFAULT_SETTINGS = {
    "base_currency": "EUR",
    "auto_update_prices": "1",
    "eb_app_id": "",
    "eb_redirect_url": "https://localhost/callback",
    "owner_names": "",
}


_EXTRA_COLUMNS = {
    # split_of: movimento diviso da cui proviene questa parte; split_total: importo originale del movimento diviso
    "transactions": {"card": "TEXT", "bank_uid": "TEXT", "split_of": "INTEGER", "split_total": "REAL"},
    "categories": {"name_en": "TEXT"},       # nome mostrato quando l'app è in inglese (vuoto = come il nome)
    "bank_accounts": {"cash_account_type": "TEXT", "product": "TEXT", "balance": "REAL", "balance_currency": "TEXT",
                      "balance_type": "TEXT", "balance_date": "TEXT", "balances_json": "TEXT"},
}


def _migrate_columns(con) -> None:
    """Colonne aggiunte dopo la prima versione (i database esistenti le ricevono qui)."""
    for table, cols in _EXTRA_COLUMNS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, kind in cols.items():
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        _migrate_columns(con)
        con.execute("CREATE INDEX IF NOT EXISTS ix_tx_match ON transactions(account, currency, date)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_tx_split ON transactions(split_of)")
        for k, v in DEFAULT_SETTINGS.items():
            con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        n = con.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if n == 0:
            for i, (name, kind, icon, color) in enumerate(DEFAULT_CATEGORIES):
                con.execute(
                    "INSERT INTO categories(name, kind, icon, color, sort_order, name_en) VALUES (?,?,?,?,?,?)",
                    (name, kind, icon, color, i, CATEGORIES_EN.get(name)),
                )
        # nomi inglesi delle categorie predefinite (anche per i database già esistenti; una volta sola, così un
        # nome inglese cambiato o tolto dall'utente resta com'è)
        row = con.execute("SELECT value FROM settings WHERE key='categories_en_version'").fetchone()
        if not row or not str(row["value"]).isdigit() or int(row["value"]) < CATEGORIES_EN_VERSION:
            for name, en in CATEGORIES_EN.items():
                # non se c'è già una categoria che si chiama (o si mostra) così: due nomi uguali sarebbero ambigui
                con.execute("""UPDATE categories SET name_en=? WHERE name=? AND (name_en IS NULL OR name_en='')
                               AND NOT EXISTS (SELECT 1 FROM categories c2 WHERE c2.name<>? AND
                                   (lower(c2.name)=lower(?) OR lower(COALESCE(c2.name_en, ''))=lower(?)))""",
                            (en, name, name, en, en))
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('categories_en_version', ?)",
                        (str(CATEGORIES_EN_VERSION),))
            _bump_categories()
        # nuova palette colori: aggiorna solo le categorie con il colore predefinito precedente
        row = con.execute("SELECT value FROM settings WHERE key='colors_version'").fetchone()
        if not row or int(row["value"]) < COLORS_VERSION:
            for name, _kind, _icon, color in DEFAULT_CATEGORIES:
                for old in (OLD_COLORS_V1.get(name, ""), OLD_COLORS_V2.get(name, "")):
                    con.execute("UPDATE categories SET color=? WHERE name=? AND upper(color)=upper(?)",
                                (color, name, old))
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('colors_version', ?)", (str(COLORS_VERSION),))
        # aggiunge le regole predefinite nuove (anche a database già esistenti)
        row = con.execute("SELECT value FROM settings WHERE key='rules_version'").fetchone()
        current = int(row["value"]) if row and str(row["value"]).isdigit() else (0 if n == 0 else 1)
        if current < RULES_VERSION:
            cats = {r[0] for r in con.execute("SELECT name FROM categories").fetchall()}
            for kw, cat in DEFAULT_RULES:
                if cat in cats:
                    con.execute("INSERT OR IGNORE INTO rules(keyword, category, priority) VALUES (?,?,?)",
                                (kw, cat, RULE_PRIORITY.get((kw, cat), 0)))
            for kw, cat in REMOVED_RULES:
                con.execute("DELETE FROM rules WHERE keyword=? AND category=?", (kw, cat))
            for (kw, cat), prio in RULE_PRIORITY.items():
                con.execute("UPDATE rules SET priority=? WHERE keyword=? AND category=?", (prio, kw, cat))
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('rules_version', ?)", (str(RULES_VERSION),))
        if not con.execute("SELECT 1 FROM settings WHERE key='shared_category'").fetchone():
            clash = con.execute("SELECT 1 FROM categories WHERE lower(name)=lower(?) OR lower(COALESCE(name_en,''))="
                                "lower(?)", (SHARED_CATEGORY, "Shared expenses")).fetchone()
            if not clash:
                top = con.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories").fetchone()[0]
                con.execute("INSERT INTO categories(name, kind, icon, color, sort_order, name_en) VALUES (?,?,?,?,?,?)",
                            (SHARED_CATEGORY, "neutro", "🤝", "#9C8CF0", top, "Shared expenses"))
            con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('shared_category', '1')")
            _bump_categories()
    # carte: riconosce le carte nei movimenti già presenti (una volta sola)
    if get_setting("cards_backfill", "") != "1":
        from core import cards
        cards.backfill()
        set_setting("cards_backfill", "1")


# ---------------------------------------------------------------- settings
def get_setting(key: str, default: str | None = None) -> str | None:
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def base_currency() -> str:
    return get_setting("base_currency", "EUR") or "EUR"


def owner_names() -> list[str]:
    """Nomi degli intestatari: i bonifici verso/da questi nomi sono giroconti tra i propri conti."""
    raw = get_setting("owner_names", "") or ""
    return [n.strip() for n in raw.replace(";", "\n").splitlines() if n.strip()]


def add_owner_name(name: str) -> bool:
    from core.categorize import is_owner

    names = owner_names()
    if not name or is_owner(name, names):
        return False
    set_setting("owner_names", "\n".join(names + [name.strip()]))
    return True


# ---------------------------------------------------------------- categories & rules
def categories_df() -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM categories ORDER BY sort_order, name", con)


_categories_rev = 0   # cambia a ogni modifica delle categorie (per la cache dei nomi da mostrare)


def _bump_categories() -> None:
    global _categories_rev
    _categories_rev += 1


@lru_cache(maxsize=128)
def _category_labels(path: str, lang: str, rev: int, mtime: float) -> tuple[tuple[str, str], ...]:
    with connect() as con:
        rows = con.execute("SELECT name, name_en FROM categories").fetchall()
    return tuple((r["name"], (str(r["name_en"]).strip() or r["name"]) if lang == "en" and r["name_en"] else r["name"])
                 for r in rows)


def category_labels(lang: str | None = None) -> dict[str, str]:
    """Nome da mostrare per ogni categoria nella lingua dell'app: in inglese il nome inglese (se c'è), altrimenti
    il nome della categoria. Il nome della categoria resta la chiave salvata nei movimenti e nelle regole."""
    if lang is None:
        from core import i18n
        lang = i18n.lang()
    path = db_path()
    try:
        mtime = path.stat().st_mtime   # anche un ripristino da backup o un'altra scheda cambiano il file
    except OSError:
        mtime = 0.0
    return dict(_category_labels(str(path), lang, _categories_rev, mtime))


def category_label(name, lang: str | None = None):
    """Nome da mostrare di una categoria (None resta None)."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return name
    return category_labels(lang).get(str(name), str(name))


def category_names(kind: str | None = None) -> list[str]:
    df = categories_df()
    if kind:
        df = df[df["kind"] == kind]
    return df["name"].tolist()


def upsert_category(name: str, kind: str, icon: str, color: str, name_en: str | None = None) -> None:
    """Crea o aggiorna una categoria; name_en=None lascia com'è il nome inglese, "" lo toglie."""
    with connect() as con:
        con.execute(
            """INSERT INTO categories(name, kind, icon, color) VALUES (?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, icon=excluded.icon, color=excluded.color""",
            (name, kind, icon, color),
        )
        if name_en is not None:
            con.execute("UPDATE categories SET name_en=? WHERE name=?", (name_en.strip() or None, name))
    _bump_categories()


def rename_category(old: str, new: str) -> None:
    with connect() as con:
        con.execute("UPDATE categories SET name=? WHERE name=?", (new, old))
        con.execute("UPDATE transactions SET category=? WHERE category=?", (new, old))
    _bump_categories()


def delete_category(name: str, move_to: str) -> None:
    with connect() as con:
        con.execute("UPDATE transactions SET category=? WHERE category=?", (move_to, name))
        con.execute("DELETE FROM categories WHERE name=?", (name,))
    _bump_categories()


def rules_df() -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM rules ORDER BY category, keyword", con)


def add_rule(keyword: str, category: str, priority: int = 0) -> None:
    """Aggiunge una regola; se la stessa parola chiave puntava a un'altra categoria, la sostituisce."""
    with connect() as con:
        con.execute("DELETE FROM rules WHERE keyword=? AND category<>?", (keyword.strip().lower(), category))
        con.execute(
            "INSERT INTO rules(keyword, category, priority) VALUES (?,?,?) "
            "ON CONFLICT(keyword, category) DO UPDATE SET priority=max(priority, excluded.priority)",
            (keyword.strip().lower(), category, priority),
        )


def delete_rules(ids: list[int]) -> None:
    with connect() as con:
        con.executemany("DELETE FROM rules WHERE id=?", [(int(i),) for i in ids])


# ---------------------------------------------------------------- transactions
def make_external_id(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


MATCH_DAYS = 4  # stesso movimento da due fonti: la data può differire di qualche giorno (operazione / contabile)


def source_family(source: str | None) -> str:
    """'api' (collegamento banca), 'manual' (inserito a mano) o 'file' (estratti importati e dati di prova)."""
    s = str(source or "")
    if s.startswith("openbanking"):
        return "api"
    if s == "manuale":
        return "manual"
    return "file"


def _similarity(a: str, b: str) -> float:
    wa = {w for w in re.findall(r"[a-z0-9]{3,}", str(a).lower())}
    wb = {w for w in re.findall(r"[a-z0-9]{3,}", str(b).lower())}
    return len(wa & wb) / max(len(wa | wb), 1)


def find_twin(con, row: dict, family: str) -> int | None:
    """Movimento già presente che è lo stesso di `row` ma arrivato dall'altra fonte (estratto ↔ collegamento banca):
    stesso conto, valuta e importo, data entro MATCH_DAYS giorni, non già abbinato a un altro movimento di questa
    fonte. Se ce n'è più di uno vince la data più vicina, poi la descrizione più simile."""
    if family == "api":
        other = "source NOT LIKE 'openbanking%' AND source <> 'manuale'"
    elif family == "file":
        other = "source LIKE 'openbanking%'"
    else:
        return None
    try:
        d = datetime.fromisoformat(str(row["date"])[:10])
    except ValueError:
        return None
    lo = (d - pd.Timedelta(days=MATCH_DAYS)).strftime("%Y-%m-%d")
    hi = (d + pd.Timedelta(days=MATCH_DAYS)).strftime("%Y-%m-%d")
    cands = con.execute(
        f"""SELECT id, date, description FROM transactions
            WHERE account=? AND currency=? AND abs(COALESCE(split_total, amount) - ?) < 0.005
              AND date BETWEEN ? AND ? AND {other} AND split_of IS NULL
              AND id NOT IN (SELECT tx_id FROM tx_links WHERE family=? AND tx_id IS NOT NULL)""",
        (row.get("account"), str(row.get("currency") or "").upper(), float(row["amount"]), lo, hi, family),
    ).fetchall()
    if not cands:
        return None
    # data più vicina, ma una descrizione molto simile vale fino a due giorni di differenza
    best = min(cands, key=lambda c: (abs((datetime.fromisoformat(str(c["date"])[:10]) - d).days)
                                     - 2 * _similarity(c["description"], row.get("description", "")), c["id"]))
    return int(best["id"])


def _enrich(con, tx_id: int, row: dict, family: str) -> None:
    """Completa il movimento tenuto con i dati dell'altra copia (carta, conto collegato; dall'estratto anche
    descrizione, data e categoria, che sono più precise di quelle del collegamento banca)."""
    cur = con.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if cur is None:
        return
    sets: dict = {}
    if row.get("card") and not cur["card"]:
        sets["card"] = row["card"]
    if row.get("bank_uid") and not cur["bank_uid"]:
        sets["bank_uid"] = row["bank_uid"]
    if family == "file" and source_family(cur["source"]) == "api":
        sets.update(description=row["description"], date=row["date"])
        if not cur["category_locked"] and row.get("category"):
            sets["category"] = row["category"]
    if sets:
        con.execute(f"UPDATE transactions SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
                    [*sets.values(), tx_id])


def insert_transactions(rows: list[dict], match_sources: bool = True) -> tuple[int, int]:
    """Inserisce righe e ritorna (inserite, saltate). Si saltano:
    - i duplicati esatti (stesso external_id), anche se erano stati scartati in passato (tx_links);
    - con match_sources, lo stesso movimento già arrivato dall'altra fonte (estratto ↔ collegamento banca), che
      viene completato con i dati mancanti (es. la carta) e ricordato in tx_links.
    La carta usata, se scritta nella descrizione, viene riconosciuta e salvata."""
    from core import cards

    inserted = skipped = 0
    cols = ["date", "description", "amount", "currency", "fx_rate", "amount_base", "base_currency",
            "category", "category_locked", "account", "source", "notes", "external_id", "card", "bank_uid"]
    with connect() as con:
        for r in rows:
            kind = r.pop("_card_kind", "")
            if not r.get("card"):
                digits, k2 = cards.detect(r.get("description", ""))
                if digits:
                    r["card"], kind = digits, kind or k2
            ext = r.get("external_id")
            if ext:
                hit = con.execute("SELECT id FROM transactions WHERE external_id=?", (ext,)).fetchone()
                link = None if hit else con.execute("SELECT tx_id FROM tx_links WHERE external_id=?", (ext,)).fetchone()
                if hit or link:
                    tx_id = hit["id"] if hit else link["tx_id"]
                    if tx_id is not None and r.get("card"):
                        con.execute("UPDATE transactions SET card=? WHERE id=? AND card IS NULL", (r["card"], tx_id))
                    if r.get("card"):
                        cards.remember(con, r.get("account"), r["card"], kind)
                    skipped += 1
                    continue
            fam = source_family(r.get("source"))
            if match_sources and ext and fam in ("api", "file"):
                twin = find_twin(con, r, fam)
                if twin is not None:
                    con.execute("INSERT OR IGNORE INTO tx_links(external_id, tx_id, family) VALUES (?,?,?)",
                                (ext, twin, fam))
                    _enrich(con, twin, r, fam)
                    if r.get("card"):
                        cards.remember(con, r.get("account"), r["card"], kind)
                    skipped += 1
                    continue
            vals = [r.get(c) for c in cols]
            cur = con.execute(
                f"INSERT OR IGNORE INTO transactions({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                vals,
            )
            if cur.rowcount:
                inserted += 1
                if r.get("card"):
                    cards.remember(con, r.get("account"), r["card"], kind)
            else:
                skipped += 1
    return inserted, skipped


def transactions_df() -> pd.DataFrame:
    with connect() as con:
        df = pd.read_sql_query(
            """SELECT t.*, COALESCE(c.kind, CASE WHEN t.amount < 0 THEN 'uscita' ELSE 'entrata' END) AS kind,
                      COALESCE(c.icon, '') AS icon, COALESCE(c.color, '#888888') AS color
               FROM transactions t LEFT JOIN categories c ON c.name = t.category
               ORDER BY t.date DESC, t.id DESC""",
            con,
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def update_transaction(tx_id: int, **fields) -> None:
    if not fields:
        return
    keys = list(fields)
    with connect() as con:
        con.execute(
            f"UPDATE transactions SET {', '.join(k + '=?' for k in keys)} WHERE id=?",
            [fields[k] for k in keys] + [int(tx_id)],
        )
        row = con.execute("SELECT id, split_of FROM transactions WHERE id=?", (int(tx_id),)).fetchone()
        if row is None:
            return
        root = int(row["split_of"] or row["id"])
        # un movimento diviso: data, conto, descrizione e valuta valgono per tutte le sue parti
        if row["split_of"] is None:
            same = {k: fields[k] for k in ("date", "account", "description", "currency") if k in fields}
            if same:
                con.execute(f"UPDATE transactions SET {', '.join(k + '=?' for k in same)} WHERE split_of=?",
                            [*same.values(), root])
        if "amount" in fields:
            _fix_split_total(con, root)


def _fix_split_total(con, root: int) -> None:
    """Importo originale del movimento diviso = somma delle parti (NULL se non ha più parti)."""
    n, tot = con.execute("SELECT COUNT(*), TOTAL(amount) FROM transactions WHERE split_of=?", (root,)).fetchone()
    if n:
        con.execute("UPDATE transactions SET split_total=round(amount + ?, 2) WHERE id=?", (tot, root))
    else:
        con.execute("UPDATE transactions SET split_total=NULL WHERE id=?", (root,))


def delete_transactions(ids: list[int]) -> None:
    """Cancella i movimenti. Cancellando un movimento diviso si cancellano anche le sue parti; cancellando solo una
    parte, il suo importo torna al movimento da cui era stata divisa (il totale resta quello della banca)."""
    ids = {int(i) for i in ids}
    if not ids:
        return
    with connect() as con:
        q = ",".join("?" * len(ids))
        ids |= {int(r[0]) for r in con.execute(f"SELECT id FROM transactions WHERE split_of IN ({q})", tuple(ids))}
        q = ",".join("?" * len(ids))
        parts = con.execute(f"SELECT id, split_of, amount, amount_base FROM transactions WHERE id IN ({q}) "
                            "AND split_of IS NOT NULL", tuple(ids)).fetchall()
        roots = set()
        for p in parts:
            root = int(p["split_of"])
            if root in ids:
                continue
            roots.add(root)
            con.execute("UPDATE transactions SET amount=round(amount + ?, 2), "
                        "amount_base=CASE WHEN amount_base IS NULL OR ? IS NULL THEN amount_base "
                        "ELSE round(amount_base + ?, 2) END WHERE id=?",
                        (p["amount"], p["amount_base"], p["amount_base"], root))
        con.executemany("DELETE FROM transactions WHERE id=?", [(i,) for i in ids])
        # le copie abbinate da altre fonti non restano «bloccate»: se reimportate, tornano come prima
        con.executemany("DELETE FROM tx_links WHERE tx_id=?", [(i,) for i in ids])
        # quote e rimborsi delle spese condivise legati a questi movimenti
        con.executemany("DELETE FROM shared WHERE tx_id=?", [(i,) for i in ids])
        for root in roots:
            _fix_split_total(con, root)


# ---------------------------------------------------------------- movimenti divisi
class SplitError(ValueError):
    """Divisione non possibile (importo troppo alto, movimento non trovato…): il messaggio si mostra così com'è."""


def split_off(tx_id: int, amount: float, category: str, note: str = "", con=None) -> int:
    """Stacca dal movimento `tx_id` una parte di `amount` (positivo, nella valuta del movimento) con la sua
    categoria. La parte è un movimento a sé (stessa data, conto, descrizione e carta) collegato al movimento
    diviso: totali, saldi e abbinamenti con la banca restano quelli dell'importo originale. Ritorna l'id."""
    from core.i18n import t
    if con is None:
        with connect() as c:
            return split_off(tx_id, amount, category, note, con=c)
    r = con.execute("SELECT * FROM transactions WHERE id=?", (int(tx_id),)).fetchone()
    if r is None:
        raise SplitError(t("Movimento non trovato."))
    amount = round(abs(float(amount)), 2)
    cur = float(r["amount"])
    if amount < 0.01:
        raise SplitError(t("L'importo di ogni parte deve essere maggiore di zero."))
    if amount >= round(abs(cur), 2):
        raise SplitError(t("La parte deve essere minore dell'importo rimasto ({v}).", v=f"{abs(cur):.2f}"))
    sign = -1.0 if cur < 0 else 1.0
    part = round(sign * amount, 2)
    base_part = None
    if r["amount_base"] is not None and cur:
        base_part = round(float(r["amount_base"]) * part / cur, 2)
    root = int(r["split_of"] or r["id"])
    if r["split_of"] is None and r["split_total"] is None:
        con.execute("UPDATE transactions SET split_total=amount WHERE id=?", (root,))
    con.execute("UPDATE transactions SET amount=round(amount - ?, 2), amount_base=CASE WHEN amount_base IS NULL "
                "OR ? IS NULL THEN amount_base ELSE round(amount_base - ?, 2) END, category_locked=1 WHERE id=?",
                (part, base_part, base_part, int(tx_id)))
    ext = make_external_id("split", root, tx_id, part, datetime.now().isoformat(), os.urandom(4).hex())
    cur_ins = con.execute(
        """INSERT INTO transactions(date, description, amount, currency, fx_rate, amount_base, base_currency,
               category, category_locked, account, source, notes, external_id, card, bank_uid, split_of)
           VALUES (?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?)""",
        (r["date"], r["description"], part, r["currency"], r["fx_rate"], base_part, r["base_currency"], category,
         r["account"], r["source"], note or "", ext, r["card"], r["bank_uid"], root))
    _fix_split_total(con, root)
    return int(cur_ins.lastrowid)


def split_transaction(tx_id: int, parts: list[tuple[str, float, str]]) -> list[int]:
    """Divide il movimento in più parti: parts = [(categoria, importo positivo, nota), …]. La prima parte resta
    sul movimento (cambia la sua categoria e nota), le altre diventano movimenti collegati. La somma delle parti
    deve essere uguale all'importo del movimento."""
    from core.i18n import t
    with connect() as con:
        r = con.execute("SELECT * FROM transactions WHERE id=?", (int(tx_id),)).fetchone()
        if r is None:
            raise SplitError(t("Movimento non trovato."))
        parts = [(c, round(abs(float(a)), 2), n or "") for c, a, n in parts if c and a and abs(float(a)) >= 0.005]
        if len(parts) < 2:
            raise SplitError(t("Servono almeno due parti con un importo."))
        total = round(abs(float(r["amount"])), 2)
        if abs(sum(a for _c, a, _n in parts) - total) > 0.005:
            raise SplitError(t("La somma delle parti ({s}) deve essere uguale all'importo del movimento ({v}).",
                               s=f"{sum(a for _c, a, _n in parts):.2f}", v=f"{total:.2f}"))
        new_ids = [split_off(tx_id, a, c, n, con=con) for c, a, n in parts[1:]]
        first_cat, _a, first_note = parts[0]
        con.execute("UPDATE transactions SET category=?, category_locked=1, notes=? WHERE id=?",
                    (first_cat, first_note or (r["notes"] or ""), int(tx_id)))
        return new_ids


def split_family(tx_id: int) -> list[int]:
    """Id del movimento diviso e delle sue parti (il movimento diviso per primo); [] se non è diviso."""
    with connect() as con:
        r = con.execute("SELECT id, split_of FROM transactions WHERE id=?", (int(tx_id),)).fetchone()
        if r is None:
            return []
        root = int(r["split_of"] or r["id"])
        kids = [int(x[0]) for x in con.execute("SELECT id FROM transactions WHERE split_of=? ORDER BY id", (root,))]
    return [root] + kids if kids else []


def unsplit(tx_id: int) -> None:
    """Annulla la divisione: le parti tornano nel movimento originale (e le quote condivise legate spariscono)."""
    fam = split_family(tx_id)
    if fam:
        delete_transactions(fam[1:])


def accounts_list() -> list[str]:
    with connect() as con:
        rows = con.execute("SELECT DISTINCT account FROM transactions WHERE account IS NOT NULL ORDER BY account").fetchall()
    names = [r[0] for r in rows if r[0]]
    for default in ["Contanti", "Fineco", "Revolut"]:
        if default not in names:
            names.append(default)
    return names


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def data_signature() -> str:
    """Impronta veloce dei movimenti: cambia a ogni inserimento, modifica o cancellazione (per le cache)."""
    with connect() as con:
        r = con.execute("SELECT COUNT(*), MAX(id), TOTAL(amount), TOTAL(id * length(COALESCE(category, ''))), "
                        "TOTAL(id * length(COALESCE(description, ''))), TOTAL(COALESCE(amount_base, 0)) "
                        "FROM transactions").fetchone()
        c = con.execute("SELECT group_concat(name || ':' || kind || ':' || COALESCE(name_en, ''), '|') "
                        "FROM categories").fetchone()
    return "|".join(str(x) for x in (str(db_path()),) + tuple(r) + tuple(c))


# ---------------------------------------------------------------- obiettivi di risparmio
def goals_df(include_archived: bool = False) -> pd.DataFrame:
    with connect() as con:
        q = "SELECT * FROM goals" + ("" if include_archived else " WHERE archived=0") + " ORDER BY archived, id"
        df = pd.read_sql_query(q, con)
    # i valori mancanti (es. obiettivo senza scadenza) devono essere None, non NaN (che risulterebbe «vero»)
    return df.astype(object).where(df.notna(), None)


def save_goal(fields: dict, goal_id: int | None = None) -> int:
    cols = ["name", "target", "deadline", "start_date", "mode", "account", "account_ccy", "balance_offset",
            "initial", "color", "archived"]
    data = {k: fields[k] for k in cols if k in fields}
    with connect() as con:
        if goal_id is None:
            cur = con.execute(f"INSERT INTO goals({', '.join(data)}) VALUES ({', '.join('?' * len(data))})",
                              tuple(data.values()))
            return int(cur.lastrowid)
        con.execute(f"UPDATE goals SET {', '.join(f'{k}=?' for k in data)} WHERE id=?", (*data.values(), goal_id))
        return goal_id


def delete_goal(goal_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM goal_moves WHERE goal_id=?", (goal_id,))
        con.execute("DELETE FROM goals WHERE id=?", (goal_id,))


def goal_moves_df(goal_id: int) -> pd.DataFrame:
    with connect() as con:
        df = pd.read_sql_query("SELECT * FROM goal_moves WHERE goal_id=? ORDER BY date, id", con, params=(goal_id,))
    df["date"] = pd.to_datetime(df["date"])
    return df


def add_goal_move(goal_id: int, day: str, amount: float, note: str = "") -> None:
    with connect() as con:
        con.execute("INSERT INTO goal_moves(goal_id, date, amount, note) VALUES (?,?,?,?)", (goal_id, day, amount, note))


def delete_goal_move(move_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM goal_moves WHERE id=?", (move_id,))
