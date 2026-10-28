"""Email: riepilogo mensile e promemoria degli addebiti in arrivo, inviati con il tuo server di posta (SMTP).

Le email partono da questo computer, mentre l'app è aperta (o alla prima apertura utile): il riepilogo del
mese appena finito dal giorno 1 in poi, i promemoria una volta al giorno se ci sono addebiti nuovi in arrivo.
Le impostazioni (compresa la password del server di posta) restano nel database, solo su questo computer.
"""
from __future__ import annotations

import html
import json
import re
import smtplib
import ssl
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

import pandas as pd

from core import db, i18n, recurring
from core.i18n import t

CFG_KEY = "email_config"
MONTHLY_LAST = "email_monthly_last"        # ultimo mese riassunto, "AAAA-MM"
REMINDERS_SENT = "email_reminders_sent"    # promemoria già mandati (id), per non ripeterli
LAST_TRY = "email_last_try"                # {"monthly": iso, "reminders": iso} dopo un errore si riprova più tardi
LAST_ERROR = "email_last_error"
REMINDER_DAYS = "reminder_days"            # giorni di anticipo dei promemoria (anche quelli dentro l'app); 0 = spenti
RETRY = timedelta(hours=3)

PRESETS = {   # server di posta più comuni (servono le «password per le app»)
    "gmail": ("Gmail", "smtp.gmail.com", 465, "ssl"),
    "icloud": ("iCloud", "smtp.mail.me.com", 587, "starttls"),
    "yahoo": ("Yahoo", "smtp.mail.yahoo.com", 465, "ssl"),
    "altro": ("Altro", "", 587, "starttls"),
}
SECURITY = {"ssl": "SSL/TLS", "starttls": "STARTTLS", "none": "Nessuna (sconsigliato)"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NotifyError(RuntimeError):
    """Invio non riuscito: il messaggio si mostra così com'è."""


# ---------------------------------------------------------------- impostazioni
def config() -> dict:
    try:
        c = json.loads(db.get_setting(CFG_KEY, "{}") or "{}")
    except (ValueError, TypeError):
        c = {}
    c = c if isinstance(c, dict) else {}
    out = {"enabled": bool(c.get("enabled")), "host": str(c.get("host") or ""), "port": int(c.get("port") or 587),
           "security": c.get("security") if c.get("security") in SECURITY else "starttls",
           "user": str(c.get("user") or ""), "password": str(c.get("password") or ""),
           "sender": str(c.get("sender") or ""), "to": str(c.get("to") or ""),
           "monthly": c.get("monthly", True) is not False, "reminders": c.get("reminders", True) is not False}
    return out


def save_config(cfg: dict) -> None:
    old = config()
    new = dict(old, **cfg)
    db.set_setting(CFG_KEY, json.dumps(new))
    if new["enabled"] and new["monthly"] and not (old["enabled"] and old["monthly"]):
        # appena attivato: il primo riepilogo arriva a inizio del prossimo mese (non quello di un mese già passato)
        db.set_setting(MONTHLY_LAST, str(pd.Period(date.today(), freq="M") - 1))


def recipients(cfg: dict) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\s]+", cfg.get("to") or "") if x.strip()]


def problems(cfg: dict) -> list[str]:
    """Cosa manca o non va nelle impostazioni (lista vuota = tutto a posto)."""
    out = []
    if not cfg["host"]:
        out.append(t("Indica il server di posta in uscita (SMTP)."))
    if not 1 <= int(cfg["port"]) <= 65535:
        out.append(t("La porta deve essere un numero tra 1 e 65535."))
    to = recipients(cfg)
    if not to:
        out.append(t("Indica a quale indirizzo mandare le email."))
    elif not all(EMAIL_RE.match(x) for x in to):
        out.append(t("Uno degli indirizzi dei destinatari non è valido."))
    sender = cfg["sender"] or cfg["user"]
    if not sender or not EMAIL_RE.match(sender):
        out.append(t("Indica un indirizzo mittente valido (di solito il tuo indirizzo email)."))
    return out


def reminder_days() -> int:
    try:
        v = int(db.get_setting(REMINDER_DAYS, "3") or 3)
    except ValueError:
        v = 3
    return max(0, min(v, 14))


# ---------------------------------------------------------------- invio
def _attempts(cfg: dict) -> list[tuple[int, str]]:
    """Porta e sicurezza da provare: quelle scelte e, se la connessione non riesce, l'altra combinazione standard
    (465 con SSL oppure 587 con STARTTLS), che alcune reti o antivirus lasciano passare."""
    first = (int(cfg["port"]), cfg["security"])
    out = [first]
    for alt in ((465, "ssl"), (587, "starttls")):
        if first in ((465, "ssl"), (587, "starttls")) and alt != first:
            out.append(alt)
    return out


def _deliver(cfg: dict, port: int, security: str, msg: EmailMessage) -> None:
    ctx = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], port, timeout=20, context=ctx)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=20)
    with server:
        server.ehlo()
        if security == "starttls":
            server.starttls(context=ctx)
            server.ehlo()
        if cfg["user"]:
            # le «password per le app» di Google si mostrano a gruppi di 4 lettere separati da spazi
            pwd = cfg["password"].replace(" ", "") if "gmail" in cfg["host"].lower() else cfg["password"]
            server.login(cfg["user"], pwd)
        server.send_message(msg)


def send(cfg: dict, subject: str, html_body: str, text_body: str) -> None:
    errs = problems(cfg)
    if errs:
        raise NotifyError(" ".join(errs))
    msg = EmailMessage()
    msg["Subject"] = subject
    sender = cfg["sender"] or cfg["user"]
    msg["From"] = formataddr(("MoneyBoard", sender))
    msg["To"] = ", ".join(recipients(cfg))
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    last = None
    for port, security in _attempts(cfg):
        try:
            _deliver(cfg, port, security, msg)
            if (port, security) != (int(cfg["port"]), cfg["security"]):
                save_config({"port": port, "security": security})   # questa combinazione funziona: la teniamo
            return
        except smtplib.SMTPAuthenticationError:
            raise NotifyError(t("Il server di posta ha rifiutato utente e password. Con Gmail, iCloud e Yahoo serve "
                                "una «password per le app», non quella normale.")) from None
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPNotSupportedError) as e:
            # problema di connessione: si prova l'altra porta. «STARTTLS non supportato» da Gmail o simili vuol
            # dire che qualcosa in mezzo (rete aziendale, antivirus) intercetta la posta: senza cifratura non si manda
            last = e
        except smtplib.SMTPException as e:               # (prima di OSError: SMTPException ne è un sottotipo)
            raise NotifyError(t("Invio non riuscito: {err}", err=e)) from None
        except OSError as e:                             # rete, timeout, certificato (ssl.SSLError)
            last = e
    raise NotifyError(t("Il computer non riesce a collegarsi al server di posta ({h}): spesso è la rete (aziendale, "
                        "VPN, Wi-Fi pubblico) o l'antivirus a bloccare l'invio di email. Prova da un'altra rete, "
                        "per esempio l'hotspot del telefono. Dettaglio: {err}",
                        h=cfg["host"], err=str(last) or type(last).__name__)) from None


# ---------------------------------------------------------------- contenuti
def _money(x: float, ccy: str | None = None) -> str:
    from core.alerts import _fmt
    return _fmt(float(x), ccy or db.base_currency())


def _page(title: str, intro: str, blocks: list[str]) -> str:
    body = "".join(blocks)
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#f4f2fb;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d1a2e;">
<div style="background:linear-gradient(135deg,#7C5CFC,#F0627E);border-radius:18px;padding:22px 24px;color:#fff;">
<div style="font-size:13px;opacity:.85;">MoneyBoard</div>
<div style="font-size:22px;font-weight:800;margin-top:4px;">{html.escape(title)}</div>
<div style="font-size:14px;opacity:.9;margin-top:6px;">{html.escape(intro)}</div></div>
{body}
<div style="font-size:12px;color:#7b7690;text-align:center;margin-top:18px;">{html.escape(t("Email inviata dalla tua app MoneyBoard. Si cambia o si spegne da Impostazioni → Email e promemoria."))}</div>
</div></body></html>"""


def _block(title: str, rows: list[tuple[str, str]], note: str = "") -> str:
    trs = "".join(f'<tr><td style="padding:7px 0;border-bottom:1px solid #eee;">{html.escape(a)}</td>'
                  f'<td style="padding:7px 0;border-bottom:1px solid #eee;text-align:right;font-weight:600;'
                  f'white-space:nowrap;">{html.escape(b)}</td></tr>' for a, b in rows)
    extra = f'<div style="font-size:12px;color:#7b7690;margin-top:8px;">{html.escape(note)}</div>' if note else ""
    return (f'<div style="background:#fff;border-radius:16px;padding:16px 20px;margin-top:14px;">'
            f'<div style="font-weight:700;font-size:15px;margin-bottom:6px;">{html.escape(title)}</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:14px;">{trs}</table>{extra}</div>')


def _text(title: str, sections: list[tuple[str, list[tuple[str, str]]]]) -> str:
    lines = [title, ""]
    for head, rows in sections:
        lines.append(head)
        lines += [f"  {a}: {b}" for a, b in rows]
        lines.append("")
    return "\n".join(lines)


def monthly_summary(year: int, month: int, today: date | None = None) -> tuple[str, str, str] | None:
    """(oggetto, html, testo) del riepilogo del mese; None se nel mese non ci sono movimenti."""
    from core import budgets, report, shared
    fr = report.frame()
    p = pd.Period(year=year, month=month, freq="M")
    cur = fr[fr["mese"] == p] if not fr.empty else fr
    if cur.empty:
        return None
    prev = fr[fr["mese"] == p - 1]
    spent, income = float(cur["spesa_base"].sum()), float(cur["entrata_base"].sum())
    p_spent, p_income = float(prev["spesa_base"].sum()), float(prev["entrata_base"].sum())
    saved = income - spent
    mname = f"{i18n.month(month)} {year}"
    labels = db.category_labels()

    def delta(a: float, b: float) -> str:
        return t(" ({p:+.0f}% sul mese prima)", p=(a - b) / b * 100) if b else ""

    sections = []
    main = [(t("Spese"), _money(spent) + delta(spent, p_spent)),
            (t("Entrate"), _money(income) + delta(income, p_income)),
            (t("Risparmio"), _money(saved) + (t(" ({p:.0f}% delle entrate)", p=saved / income * 100) if income else ""))]
    sections.append((t("Il mese in breve"), main))
    cats = cur[cur["spesa_base"] != 0].groupby("category")["spesa_base"].sum().sort_values(ascending=False)
    cats = cats[cats > 0].head(6)
    if not cats.empty:
        sections.append((t("Dove hai speso di più"),
                         [(labels.get(c, c), f"{_money(v)} · {v / spent * 100:.0f}%" if spent else _money(v))
                          for c, v in cats.items()]))
    st_b = budgets.status(fr, year, month, today=today or date.today())
    if st_b:
        rows = []
        for r in st_b:
            name = labels.get(r["category"], r["category"]) if r["category"] else t("Spese totali")
            flag = "⚠️ " if r["pct"] >= 100 else ""
            rows.append((f"{flag}{name}", t("{s} su {b} ({p:.0f}%)", s=_money(r["spent"]), b=_money(r["budget"]),
                                            p=r["pct"])))
        sections.append((t("Budget"), rows))
    big = cur[cur["kind"] == "uscita"].sort_values("spesa_base", ascending=False).head(3)
    if not big.empty:
        sections.append((t("Le spese più grandi"),
                         [(f"{r['date']:{i18n.strf()}} · {str(r['description'])[:48]}", _money(r["spesa_base"]))
                          for _, r in big.iterrows()]))
    try:
        series = [s for s in recurring.visible(recurring.detect(today=today)) if s.active and s.kind == "uscita"]
    except Exception:
        series = []
    if series:
        sections.append((t("Abbonamenti e pagamenti ricorrenti"),
                         [(t("Costo al mese"), _money(sum(s.monthly_base for s in series))),
                          (t("Attivi"), str(len(series)))]))
    bal = shared.balances()
    bal = bal[bal["balance"].abs() >= 0.01] if not bal.empty else bal
    if not bal.empty:
        rows = []
        for _, r in bal.iterrows():
            v = float(r["balance"])
            rows.append((r["name"], t("ti deve {v}", v=_money(v, r["currency"])) if v > 0
                         else t("devi tu {v}", v=_money(-v, r["currency"]))))
        sections.append((t("Spese condivise"), rows))
    subject = t("MoneyBoard: il riepilogo di {m}", m=mname)
    intro = (t("Hai risparmiato {v}.", v=_money(saved)) if saved >= 0
             else t("Hai speso {v} più di quanto è entrato.", v=_money(-saved)))
    page = _page(t("Il tuo {m}", m=mname), intro, [_block(h, r) for h, r in sections])
    return subject, page, _text(subject, sections)


def upcoming(today: date | None = None, days: int | None = None) -> list[dict]:
    """Addebiti attesi (abbonamenti, bollette, rate…) da oggi ai prossimi `days` giorni."""
    today = today or date.today()
    days = reminder_days() if days is None else days
    if days <= 0:
        return []
    series = [s for s in recurring.visible(recurring.detect(today=today)) if s.active and s.kind == "uscita"]
    names = recurring.custom_names()
    out = []
    for d, s in recurring.upcoming(series, today, today + timedelta(days=days)):
        out.append({"id": f"{s.sid}|{d.date().isoformat()}", "date": d.date(), "name": recurring.display_name(s, names),
                    "amount": s.typical_base if s.variable else s.amount,
                    "currency": db.base_currency() if s.variable else s.currency, "approx": s.variable,
                    "account": s.account, "sid": s.sid})
    return out


def reminders_email(items: list[dict]) -> tuple[str, str, str]:
    rows = []
    for it in items:
        when = (t("oggi") if it["date"] == date.today() else t("domani") if it["date"] == date.today() + timedelta(1)
                else f"{it['date']:{i18n.strf()}}")
        amt = (t("circa ") if it["approx"] else "") + _money(it["amount"], it["currency"])
        rows.append((f"{when} · {it['name']} ({it['account']})", amt))
    subject = (t("MoneyBoard: 1 addebito in arrivo") if len(items) == 1
               else t("MoneyBoard: {n} addebiti in arrivo", n=len(items)))
    page = _page(t("Addebiti in arrivo"), t("Così non ti trovano impreparato."), [_block(t("Prossimi giorni"), rows)])
    return subject, page, _text(subject, [(t("Prossimi giorni"), rows)])


# ---------------------------------------------------------------- invii automatici
def _tries() -> dict:
    try:
        v = json.loads(db.get_setting(LAST_TRY, "{}") or "{}")
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


def _can_try(kind: str, now: datetime) -> bool:
    try:
        last = datetime.fromisoformat(str(_tries().get(kind)))
    except (TypeError, ValueError):
        return True
    return now - last >= RETRY or last > now


def _mark_try(kind: str, now: datetime, error: str | None) -> None:
    tr = _tries()
    if error:
        tr[kind] = now.isoformat(timespec="seconds")
        db.set_setting(LAST_ERROR, json.dumps({"when": now.isoformat(timespec="seconds"), "error": error}))
    else:
        tr.pop(kind, None)
    db.set_setting(LAST_TRY, json.dumps(tr))


def last_error() -> dict | None:
    try:
        v = json.loads(db.get_setting(LAST_ERROR, "") or "null")
        return v if isinstance(v, dict) else None
    except (ValueError, TypeError):
        return None


def run_due(today: date | None = None, now: datetime | None = None) -> list[tuple[str, bool]]:
    """Manda le email che sono dovute. Ritorna i messaggi da mostrare: [(testo, è_un_errore)]."""
    cfg = config()
    if not cfg["enabled"] or problems(cfg):
        return []
    today = today or date.today()
    now = now or datetime.now()
    out = []
    if cfg["monthly"]:
        prev = pd.Period(today, freq="M") - 1
        if (db.get_setting(MONTHLY_LAST, "") or "") < str(prev) and _can_try("monthly", now):
            try:
                content = monthly_summary(prev.year, prev.month, today=today)
                if content:
                    send(cfg, *content)
                    out.append((t("Email con il riepilogo di {m} inviata.", m=f"{i18n.month(prev.month)} {prev.year}"),
                                False))
                db.set_setting(MONTHLY_LAST, str(prev))
                _mark_try("monthly", now, None)
            except NotifyError as e:
                _mark_try("monthly", now, str(e))
                out.append((str(e), True))
    if cfg["reminders"] and reminder_days() > 0 and _can_try("reminders", now):
        try:
            sent = set(json.loads(db.get_setting(REMINDERS_SENT, "[]") or "[]"))
        except (ValueError, TypeError):
            sent = set()
        items = upcoming(today)
        if any(it["id"] not in sent for it in items):
            try:
                send(cfg, *reminders_email(items))
                keep = (today - timedelta(days=60)).isoformat()   # basta ricordare quelli recenti
                sent = {x for x in sent | {it["id"] for it in items} if str(x).rsplit("|", 1)[-1] >= keep}
                db.set_setting(REMINDERS_SENT, json.dumps(sorted(sent)))
                _mark_try("reminders", now, None)
                out.append((t("Email con gli addebiti in arrivo inviata."), False))
            except NotifyError as e:
                _mark_try("reminders", now, str(e))
                out.append((str(e), True))
    return out
