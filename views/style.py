"""Sistema visivo dell'app: palette, tipografia, CSS globale, stile dei grafici e componenti HTML.

Stile "dashboard": sfondo lavanda chiaro, card bianche arrotondate con ombra morbida, card colorate
a gradiente per i numeri principali, accento viola, pillole arrotondate. Tema scuro equivalente.
"""
from __future__ import annotations

import html
import re
from datetime import date

import pandas as pd
import streamlit as st

from core import i18n
from core.i18n import t

# ---------------------------------------------------------------- token
PALETTE = {
    "light": {
        "bg": "#F3F2F9", "surface": "#FFFFFF", "field": "#F6F5FB", "line": "#ECEAF4", "ink": "#1F1D2B",
        "muted": "#8A879C", "accent": "#7C5CFC", "accent-soft": "rgba(124,92,252,0.10)", "spesa": "#E8577A",
        "entrata": "#16A394", "track": "#EEECF6", "shadow": "0 8px 28px rgba(76,60,160,0.08)",
    },
    "dark": {
        "bg": "#13121A", "surface": "#1D1B27", "field": "#252333", "line": "#2B2938", "ink": "#ECEAF5",
        "muted": "#9B98AE", "accent": "#9C85FF", "accent-soft": "rgba(156,133,255,0.16)", "spesa": "#FF7A96",
        "entrata": "#3CCFBD", "track": "#2A2837", "shadow": "0 8px 28px rgba(0,0,0,0.35)",
    },
}
# tema "Liquid Glass": superfici traslucide sopra uno sfondo colorato, sfocato dietro al vetro
PALETTE["glass"] = {
    "bg": ("radial-gradient(at 12% 18%, #6E56CF 0px, transparent 46%), "
           "radial-gradient(at 88% 8%, #0EA5E9 0px, transparent 42%), "
           "radial-gradient(at 72% 88%, #DB2777 0px, transparent 46%), "
           "radial-gradient(at 18% 92%, #0D9488 0px, transparent 42%), "
           "linear-gradient(160deg, #0B1026 0%, #151036 55%, #1F0F2E 100%)"),
    "surface": "rgba(255,255,255,0.075)", "field": "rgba(255,255,255,0.10)", "line": "rgba(255,255,255,0.16)",
    "ink": "#F4F6FF", "muted": "rgba(236,239,255,0.70)", "accent": "#C4B5FD", "accent-soft": "rgba(255,255,255,0.14)",
    "spesa": "#FF9DB0", "entrata": "#6EF0D2", "track": "rgba(255,255,255,0.16)",
    "shadow": "0 12px 40px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.28), inset 0 -1px 0 rgba(255,255,255,0.06)",
}
GLASS_THEME_COLORS = {  # colori pieni per i widget nativi di Streamlit (il resto lo fa il CSS)
    "bg": "#0F1230", "surface": "#1A1F45", "field": "#252B57", "line": "#3B4280", "ink": "#F4F6FF",
    "accent": "#B9A6FF",
}
# colori dei grafici (leggibili su entrambi gli sfondi)
SPESA = "#F0627E"
ENTRATA = "#1FB5A4"
NEUTRO = "#A3A0B5"
ACCENT = "#7C5CFC"
GRADIENTS = {
    "spese": ("#F0627E", "#F79A7E"),
    "entrate": ("#14AE9E", "#4FD3C1"),
    "saldo": ("#7C5CFC", "#B18CFF"),
    "media": ("#F59E4C", "#F7C55E"),
    "blu": ("#3B82F6", "#22D3EE"),
    "grafite": ("#475569", "#64748B"),
}
# Font installati su Windows 11 (nessun download): Segoe UI Variable, poi Segoe UI, poi il font di sistema
FONT_BODY = "Segoe UI Variable Text, Segoe UI Variable, Segoe UI, system-ui, -apple-system, sans-serif"
FONT_DISPLAY = "Segoe UI Variable Display, Segoe UI Variable, Segoe UI, system-ui, -apple-system, sans-serif"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _vars(p: dict) -> str:
    return "".join(f"--as-{k}:{v};" for k, v in p.items())


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color if _HEX.match(str(hex_color)) else "#A3A0B5"
    return f"rgba({int(h[1:3], 16)},{int(h[3:5], 16)},{int(h[5:7], 16)},{alpha})"


def safe_color(c) -> str:
    return c if _HEX.match(str(c)) else "#A3A0B5"


def inject_css(mode: str) -> None:
    """mode: 'chiaro' | 'scuro' | 'auto' | 'glass'."""
    light, dark = _vars(PALETTE["light"]), _vars(PALETTE["dark"])
    if mode == "glass":
        root = f":root{{{_vars(PALETTE['glass'])}}}"
    elif mode == "scuro":
        root = f":root{{{dark}}}"
    elif mode == "chiaro":
        root = f":root{{{light}}}"
    else:
        root = f":root{{{light}}} @media (prefers-color-scheme: dark){{:root{{{dark}}}}}"
    css = f"""
<style>
{root}
[data-testid="stAppViewContainer"], .stApp {{ background: var(--as-bg) !important; font-feature-settings: "tnum" 1; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}
/* niente decorazioni di Streamlit */
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stDecoration"], [data-testid="stStatusWidget"], #MainMenu, footer {{ display: none !important; }}
/* pulsante per riaprire la barra laterale quando è chiusa (sta nella toolbar: la toolbar NON va nascosta) */
[data-testid="stExpandSidebarButton"] {{ background: var(--as-surface); border: 1px solid var(--as-line);
  border-radius: 12px; box-shadow: var(--as-shadow); }}
[data-testid="stExpandSidebarButton"]:hover {{ background: var(--as-accent-soft); }}
.block-container {{ padding-top: 3.6rem !important; max-width: 1240px; }}

/* ---- barra laterale ---- */
[data-testid="stSidebar"] {{ background: var(--as-surface) !important; border-right: 1px solid var(--as-line); }}
[data-testid="stSidebarNav"] a[data-testid="stSidebarNavLink"] {{ border-radius: 12px; margin: 1px 0; padding-top: .45rem; padding-bottom: .45rem; }}
[data-testid="stSidebarNav"] a[data-testid="stSidebarNavLink"]:hover {{ background: var(--as-accent-soft); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: var(--as-accent-soft) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"] span, [data-testid="stSidebarNav"] a[aria-current="page"] p {{
  color: var(--as-accent) !important; font-weight: 600 !important; }}
[data-testid="stNavSectionHeader"] {{ color: var(--as-muted) !important; font-size: .78rem !important; }}
[data-testid="stSidebarNavSeparator"] {{ border-color: var(--as-line); }}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ color: var(--as-muted); font-size: .82rem; }}

/* ---- card (contenitori con key "card_...") ---- */
[class*="st-key-card_"] {{ background: var(--as-surface); border-radius: 20px; box-shadow: var(--as-shadow);
  padding: 1.25rem 1.4rem 1.1rem 1.4rem; border: 1px solid var(--as-line); }}
[class*="st-key-card_"] h3 {{ font-size: 1.05rem !important; font-weight: 700 !important; margin: 0 0 .2rem 0; padding-top: 0; }}

/* ---- widget ---- */
[data-testid="stBaseButton-primary"] {{ background: linear-gradient(135deg, #7C5CFC, #A47CFF) !important;
  border: none !important; border-radius: 12px !important; box-shadow: 0 6px 16px rgba(124,92,252,0.28); }}
[data-testid="stBaseButton-secondary"] {{ border-radius: 12px !important; }}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius: 14px; overflow: hidden; }}
[data-testid="stExpander"] details {{ border-radius: 16px !important; background: var(--as-surface);
  border-color: var(--as-line) !important; box-shadow: var(--as-shadow); }}
[data-testid="stTabs"] [role="tablist"] {{ gap: .4rem; border-bottom: none; }}
[data-testid="stTabs"] button[role="tab"] {{ border-radius: 999px; padding: .25rem .9rem; background: transparent; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ background: var(--as-accent-soft); }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {{ color: var(--as-accent); font-weight: 600; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none; }}
[data-testid="stMetricValue"] {{ font-weight: 700; }}
[data-testid="stMetricLabel"] p {{ color: var(--as-muted); font-size: .85rem; }}
div[role="dialog"] {{ border-radius: 22px !important; }}

/* ---- barra superiore ---- */
.as-top {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
  margin: 0 0 1.4rem 0; }}
.as-top h1 {{ font-size: 1.75rem !important; font-weight: 800 !important; margin: 0; padding: 0; line-height: 1.15; }}
.as-top p {{ margin: .25rem 0 0 0; color: var(--as-muted); font-size: .9rem; }}
.as-top .right {{ display: flex; align-items: center; gap: .8rem; }}
.as-date {{ background: var(--as-surface); border: 1px solid var(--as-line); border-radius: 14px; padding: .45rem .9rem;
  text-align: right; line-height: 1.25; box-shadow: var(--as-shadow); }}
.as-date b {{ display: block; font-size: .85rem; }} .as-date span {{ color: var(--as-muted); font-size: .78rem; }}
.as-date-click {{ cursor: pointer; transition: transform .14s ease, box-shadow .14s ease; }}
.as-date-click:hover {{ transform: translateY(-1px); box-shadow: 0 10px 24px rgba(0,0,0,0.16); }}
.as-date-click:focus-visible {{ outline: 2px solid var(--as-accent); outline-offset: 2px; }}
.st-key-as_date_box {{ margin: 0 !important; }}
.as-avatar {{ width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; color: #fff;
  font-weight: 700; font-size: .9rem; background: linear-gradient(135deg, #7C5CFC, #F0627E); box-shadow: var(--as-shadow); }}
.as-avatar.big {{ width: 54px; height: 54px; font-size: 1.1rem; flex: 0 0 54px; }}
.as-profile {{ display: flex; align-items: center; gap: 1.3rem; padding: 1.4rem 1.6rem; border-radius: 22px; color: #fff;
  margin-bottom: 1.2rem; background: linear-gradient(135deg, var(--g1), var(--g2)); box-shadow: var(--as-shadow);
  position: relative; overflow: hidden; }}
.as-profile::after {{ content: ""; position: absolute; right: -50px; top: -60px; width: 220px; height: 220px;
  border-radius: 50%; background: rgba(255,255,255,0.12); }}
.as-avatar.xl {{ width: 76px; height: 76px; font-size: 1.6rem; flex: 0 0 76px; background: rgba(255,255,255,0.22);
  border: 2px solid rgba(255,255,255,0.7); box-shadow: none; }}
.as-profile .n {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }}
.as-profile .m {{ opacity: .9; font-size: .9rem; margin-top: .15rem; }}
.st-key-as_topbar {{ margin: 0 0 1.4rem 0; }}
.st-key-as_topbar .as-top {{ margin: 0; }}
/* avatar = pulsante del menu profilo */
.st-key-as_me button {{ width: 44px; height: 44px; min-height: 44px; border-radius: 50% !important; padding: 0 !important;
  border: 2px solid rgba(255,255,255,0.65) !important; color: #fff !important; font-weight: 700;
  box-shadow: var(--as-shadow); justify-content: center; }}
.st-key-as_me button p {{ color: #fff !important; font-weight: 700; font-size: .9rem; }}
.st-key-as_me button [data-testid="stIconMaterial"] {{ display: none; }}
.st-key-as_me button:hover {{ filter: brightness(1.08); transform: translateY(-1px); }}
.st-key-as_search_box [data-testid="stTextInputRootElement"] {{ border-radius: 14px; background: var(--as-surface);
  box-shadow: var(--as-shadow); }}
.st-key-as_search_box {{ margin: 0 !important; }}
@media (max-width: 640px) {{ .st-key-as_search_box, .st-key-as_search_box [data-testid="stTextInput"] {{ width: 100% !important; }} }}
.st-key-as_logout button {{ justify-content: flex-start !important; padding-left: .5rem !important; min-height: 2.2rem;
  color: var(--as-spesa) !important; }}
.st-key-as_logout button p {{ color: var(--as-spesa) !important; }}
.st-key-as_logout button > div, .st-key-as_logout button > div > div {{ justify-content: flex-start !important;
  width: 100%; }}
.as-me-head {{ display: flex; align-items: center; gap: .8rem; padding: .2rem 0 .6rem 0; margin-bottom: .3rem;
  border-bottom: 1px solid var(--as-line); }}
.as-me-head b {{ display: block; font-size: .98rem; }} .as-me-head span {{ color: var(--as-muted); font-size: .78rem; }}
.as-me-lang {{ color: var(--as-muted); font-size: .85rem; padding-left: .55rem; }}
.st-key-as_me_lang {{ padding: .15rem 0 .25rem 0; }}
/* le pagine del profilo non compaiono nel menu laterale: si aprono dall'avatar */
[data-testid="stSidebarNavItems"] > div:has(a[href$="/profilo"]) {{ display: none; }}

/* ---- card a gradiente ---- */
.as-grads {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1.1rem; margin-bottom: 1.3rem; }}
.as-grad {{ position: relative; overflow: hidden; border-radius: 20px; padding: 1.15rem 1.25rem 1.1rem; color: #fff;
  box-shadow: 0 10px 24px rgba(60,40,120,0.16); min-height: 132px; }}
.as-grad::after {{ content: ""; position: absolute; right: -38px; top: -38px; width: 130px; height: 130px;
  border-radius: 50%; background: rgba(255,255,255,0.14); }}
.as-grad::before {{ content: ""; position: absolute; right: 18px; bottom: -56px; width: 120px; height: 120px;
  border-radius: 50%; background: rgba(255,255,255,0.10); }}
.as-grad .l {{ font-size: .92rem; font-weight: 600; opacity: .95; position: relative; z-index: 1; }}
.as-grad .s {{ font-size: .76rem; opacity: .85; margin-top: .1rem; position: relative; z-index: 1; }}
.as-grad .v {{ font-size: 1.65rem; font-weight: 800; letter-spacing: -0.02em; margin-top: .55rem; white-space: nowrap;
  position: relative; z-index: 1; }}
.as-grad .p {{ display: flex; align-items: center; gap: .6rem; margin-top: .55rem; position: relative; z-index: 1; }}
.as-grad .p .bar {{ flex: 1; height: 5px; border-radius: 3px; background: rgba(255,255,255,0.3); overflow: hidden; }}
.as-grad .p .bar span {{ display: block; height: 100%; border-radius: 3px; background: #fff; }}
.as-grads-click .as-grad {{ cursor: pointer; transition: transform .14s ease, box-shadow .14s ease; }}
.as-grads-click .as-grad:hover {{ transform: translateY(-3px); box-shadow: 0 14px 30px rgba(0,0,0,0.18); }}
.as-grads-click .as-grad:focus-visible {{ outline: 3px solid #fff; outline-offset: 2px; }}
.as-grad .go {{ position: absolute; top: .85rem; right: .9rem; z-index: 2; font-family: "Material Symbols Rounded";
  font-size: 1.15rem; opacity: 0; transition: opacity .14s ease; }}
.as-grads-click .as-grad:hover .go, .as-grads-click .as-grad:focus-visible .go {{ opacity: .9; }}
.as-grad .p b {{ font-size: .8rem; }}
.as-grad .f {{ font-size: .82rem; opacity: .92; margin-top: .3rem; position: relative; z-index: 1; }}
.as-grad .f b {{ font-weight: 700; }}

/* ---- numeri in card bianche ---- */
.as-kpis {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: .2rem 0 1.2rem 0; }}
.as-kpi {{ background: var(--as-surface); border: 1px solid var(--as-line); border-radius: 18px; padding: .95rem 1.1rem;
  box-shadow: var(--as-shadow); }}
.as-kpi .l {{ color: var(--as-muted); font-size: .82rem; font-weight: 500; }}
.as-kpi .v {{ font-size: 1.4rem; font-weight: 800; letter-spacing: -0.02em; margin-top: .2rem; white-space: nowrap; }}
.as-kpi .d {{ font-size: .78rem; margin-top: .15rem; color: var(--as-muted); }}
.as-kpi.click {{ position: relative; cursor: pointer; transition: transform .14s ease, box-shadow .14s ease; }}
.as-kpi.click:hover {{ transform: translateY(-2px); box-shadow: 0 12px 26px rgba(0,0,0,0.16); }}
.as-kpi.click:focus-visible {{ outline: 3px solid var(--as-accent); outline-offset: 2px; }}
.as-kpi .go {{ position: absolute; top: .75rem; right: .85rem; font-family: "Material Symbols Rounded";
  font-size: 1.05rem; opacity: 0; transition: opacity .14s ease; color: var(--as-muted); }}
.as-kpi.click:hover .go, .as-kpi.click:focus-visible .go {{ opacity: .9; }}
[class*="st-key-card_"] .as-kpi, div[role="dialog"] .as-kpi {{ box-shadow: none; background: var(--as-field); border-color: transparent; }}
.pos {{ color: var(--as-entrata) !important; }} .neg {{ color: var(--as-spesa) !important; }}

/* ---- legenda / barre categorie ---- */
.as-legend {{ display: flex; flex-direction: column; gap: .55rem; }}
.as-legend div {{ display: grid; grid-template-columns: 10px minmax(0, 1fr) auto auto; gap: .6rem; align-items: center;
  font-size: .86rem; }}
.as-legend i {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
.as-legend span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.as-legend em {{ font-style: normal; color: var(--as-muted); font-size: .8rem; min-width: 2.4rem; text-align: right; }}
.as-cats {{ display: flex; flex-direction: column; gap: .8rem; }}
.as-cat .top {{ display: flex; justify-content: space-between; gap: 1rem; font-size: .9rem; }}
.as-cat .top .n {{ display: flex; align-items: center; gap: .5rem; min-width: 0; }}
.as-cat .top .n span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.as-cat .dot {{ width: 9px; height: 9px; border-radius: 50%; flex: 0 0 9px; }}
.as-cat .amt {{ white-space: nowrap; font-weight: 600; }} .as-cat .pct {{ color: var(--as-muted); margin-left: .5rem; font-size: .8rem; }}
.as-cat .track {{ height: 7px; border-radius: 4px; background: var(--as-track); margin-top: .35rem; }}
.as-cat .track span {{ display: block; height: 7px; border-radius: 4px; }}
/* legenda e barre cliccabili: aprono il dettaglio della categoria */
.as-pick.as-legend {{ gap: .1rem; }} .as-pick.as-cats {{ gap: .2rem; }}
.as-pick > div {{ cursor: pointer; border-radius: 10px; padding: .4rem .5rem; margin: 0 -.5rem;
  transition: background-color .12s ease; }}
.as-pick.as-cats > div {{ padding: .5rem .5rem .55rem; }}
.as-pick > div:hover {{ background: var(--as-accent-soft); }}
.as-pick > div:focus-visible {{ outline: 2px solid var(--as-accent); outline-offset: -2px; }}
.as-pick > div.more span {{ color: var(--as-accent); font-weight: 600; }}

/* ---- tabelle ---- */
.as-table-wrap {{ overflow: auto; border-radius: 16px; border: 1px solid var(--as-line); background: var(--as-surface);
  margin: .2rem 0 .8rem; }}
.as-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: .86rem; color: var(--as-ink); }}
.as-table th {{ position: sticky; top: 0; z-index: 1; text-align: left; font-weight: 600; font-size: .78rem;
  color: var(--as-muted); padding: .65rem .85rem; background: var(--as-th, var(--as-field));
  border-bottom: 1px solid var(--as-line); white-space: nowrap; }}
.as-table td {{ padding: .58rem .85rem; border-bottom: 1px solid var(--as-line); vertical-align: middle; }}
.as-table tbody tr:last-child td {{ border-bottom: none; }}
.as-table tbody tr {{ transition: background-color .12s ease; }}
.as-table tbody tr:hover {{ background: var(--as-accent-soft); }}
.as-table .num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.as-table td.first {{ font-weight: 600; }}
.as-table tr.tot td {{ font-weight: 700; border-top: 1px solid var(--as-line); }}
.as-table .neg {{ color: var(--as-spesa); }}
.as-table .tbar {{ display: flex; align-items: center; gap: .55rem; min-width: 8rem; }}
.as-table .tbar i {{ flex: 1; height: 6px; border-radius: 3px; background: var(--as-track); overflow: hidden; }}
.as-table .tbar i span {{ display: block; height: 100%; border-radius: 3px; background: var(--as-accent); }}
.as-table .tbar em {{ font-style: normal; min-width: 3.2rem; text-align: right; font-variant-numeric: tabular-nums; }}

/* ---- elenco movimenti ---- */
.as-list {{ display: flex; flex-direction: column; }}
.as-row {{ display: grid; grid-template-columns: 2.6rem minmax(0, 1fr) auto auto; gap: .9rem; align-items: center;
  padding: .7rem .5rem; border-bottom: 1px solid var(--as-line); font-size: .9rem; border-radius: 12px; }}
.as-row:last-child {{ border-bottom: none; }}
.as-row.nopill {{ grid-template-columns: 2.6rem minmax(0, 1fr) auto; }}
.as-row .av {{ width: 2.4rem; height: 2.4rem; border-radius: 12px; display: grid; place-items: center;
  font-weight: 700; font-size: .78rem; }}
.as-row .ds {{ min-width: 0; }}
.as-row .ds .t {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }}
.as-row .ds .m {{ color: var(--as-muted); font-size: .78rem; margin-top: .1rem; }}
.as-row .pill {{ border-radius: 999px; padding: .22rem .65rem; font-size: .74rem; font-weight: 600; white-space: nowrap;
  max-width: 13rem; overflow: hidden; text-overflow: ellipsis; }}
.as-row .am {{ text-align: right; white-space: nowrap; font-weight: 700; min-width: 6.5rem; }}
.as-row .am small {{ display: block; color: var(--as-muted); font-weight: 500; font-size: .74rem; }}
.as-click .as-row {{ cursor: pointer; transition: background-color .12s ease; }}
.as-click .as-row:hover {{ background: var(--as-accent-soft); }}
.as-click .as-row:focus-visible {{ outline: 2px solid var(--as-accent); outline-offset: -2px; }}

/* ---- dettaglio movimento ---- */
.as-focus-top {{ display: flex; justify-content: space-between; align-items: center; gap: 1.5rem; flex-wrap: wrap;
  padding: 1.1rem 1.3rem; border-radius: 18px; margin-bottom: 1.2rem; color: #fff;
  background: linear-gradient(135deg, #7C5CFC, #B18CFF); }}
.as-focus-top.spesa {{ background: linear-gradient(135deg, #F0627E, #F79A7E); }}
.as-focus-top.entrata {{ background: linear-gradient(135deg, #14AE9E, #4FD3C1); }}
.as-focus-top .amt {{ font-size: 2.3rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; }}
.as-focus-top .conv {{ opacity: .9; font-size: .88rem; margin-top: .35rem; }}
.as-focus-top .when {{ text-align: right; font-size: .88rem; line-height: 1.55; opacity: .95; }}
.as-focus-top .when b {{ font-weight: 700; }}
.as-mini {{ display: flex; flex-direction: column; }}
.as-mini div {{ display: flex; justify-content: space-between; gap: 1rem; padding: .45rem .3rem;
  border-bottom: 1px solid var(--as-line); font-size: .88rem; }}
.as-mini div span:first-child {{ color: var(--as-muted); }}
.as-mini div.cur {{ font-weight: 700; }} .as-mini div.cur span:first-child {{ color: var(--as-ink); }}

/* ---- calendario ---- */
.as-cal {{ display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }}
.as-cal .h {{ color: var(--as-muted); font-size: .76rem; font-weight: 600; text-align: center; padding-bottom: .2rem; }}
.as-cal .d {{ --lv: 0; position: relative; min-height: 86px; border-radius: 12px; padding: .4rem .45rem; overflow: hidden;
  background: color-mix(in srgb, var(--as-spesa) calc(var(--lv) * 62%), var(--as-field));
  border: 1px solid transparent; cursor: pointer; transition: transform .12s ease, border-color .12s ease;
  display: flex; flex-direction: column; gap: 2px; font-size: .74rem; line-height: 1.25; }}
.as-cal .d:hover {{ border-color: var(--as-accent); }}
.as-cal .d:focus-visible {{ outline: 2px solid var(--as-accent); outline-offset: 1px; }}
.as-cal .d.empty {{ background: transparent; cursor: default; }}
.as-cal .d.today {{ border: 2px solid var(--as-accent); }}
.as-cal .d.future {{ background: transparent; border: 1px dashed var(--as-line); }}
.as-cal .d.future.today {{ border: 2px solid var(--as-accent); }}
.as-cal .d .n {{ font-weight: 700; font-size: .82rem; color: var(--as-muted); }}
.as-cal .d.we .n {{ color: var(--as-accent); }}
.as-cal .d .a {{ font-weight: 700; font-size: .8rem; white-space: nowrap; color: var(--as-ink); }}
.as-cal .d .i {{ font-weight: 600; white-space: nowrap; color: var(--as-entrata); }}
.as-cal .d .x {{ font-style: italic; color: var(--as-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.as-cal .d .x::before {{ content: ""; display: inline-block; width: 5px; height: 5px; border-radius: 50%;
  background: var(--as-accent); margin-right: 4px; vertical-align: middle; }}
.as-cal .d .x.more::before {{ display: none; }}

/* ---- obiettivi ---- */
.as-goal {{ display: flex; gap: 1.1rem; align-items: center; }}
.as-goal .ring {{ width: 92px; height: 92px; flex: 0 0 92px; }}
.as-goal .ring text {{ font-size: 15px; font-weight: 800; fill: var(--as-ink); font-family: inherit; }}
.as-goal .info {{ min-width: 0; }}
.as-goal .n {{ font-weight: 700; font-size: 1.05rem; }}
.as-goal .v {{ font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; margin-top: .1rem; }}
.as-goal .v span {{ font-size: .85rem; font-weight: 500; color: var(--as-muted); letter-spacing: 0; }}
.as-goal .m {{ color: var(--as-muted); font-size: .8rem; margin-top: .1rem; }}
.as-goal .st {{ font-size: .8rem; font-weight: 600; margin-top: .3rem; color: var(--as-muted); }}
.as-goal-plan {{ color: var(--as-muted); font-size: .86rem; margin: .8rem 0 .2rem 0; }}

/* ---- avvisi ---- */
.as-alert {{ display: grid; grid-template-columns: 2.4rem minmax(0, 1fr); gap: .8rem; align-items: start; }}
.as-alert .ic {{ width: 2.4rem; height: 2.4rem; border-radius: 12px; display: grid; place-items: center;
  font-family: "Material Symbols Rounded"; font-size: 1.3rem; }}
.as-alert .ic.alta {{ background: color-mix(in srgb, var(--as-spesa) 18%, transparent); color: var(--as-spesa); }}
.as-alert .ic.media {{ background: color-mix(in srgb, #F5A524 20%, transparent); color: #E09000; }}
.as-alert .ic.info {{ background: var(--as-accent-soft); color: var(--as-accent); }}
.as-alert .t {{ font-weight: 700; }}
.as-alert .x {{ color: var(--as-muted); font-size: .86rem; margin-top: .15rem; }}

@media (max-width: 1100px) {{ .as-grads {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
@media (max-width: 760px) {{ .as-cal .d {{ min-height: 58px; }} .as-cal .d .x, .as-cal .d .i {{ display: none; }} }}
@media (max-width: 640px) {{
  /* riquadri colorati e numeri: due per riga, più compatti */
  .as-grads {{ grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: .65rem; }}
  .as-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: .6rem; }}
  .as-grad {{ padding: .8rem .85rem .8rem; border-radius: 16px; }}
  .as-grad .l {{ font-size: .82rem; }} .as-grad .s {{ font-size: .68rem; }}
  .as-grad .v {{ font-size: 1.22rem; margin-top: .35rem; }}
  .as-grad .p {{ gap: .4rem; font-size: .68rem; margin-top: .4rem; }}
  .as-kpi {{ padding: .75rem .8rem !important; }} .as-kpi .v {{ font-size: 1.15rem !important; }}
  .as-kpi .l, .as-kpi .d {{ font-size: .72rem !important; }}
  .as-row {{ grid-template-columns: 2.4rem minmax(0, 1fr) auto; }} .as-row .pill {{ display: none; }}
  /* barra in alto: titolo, poi ricerca e avatar sulla stessa riga (la data è nel calendario) */
  .st-key-as_topbar {{ flex-wrap: wrap !important; row-gap: .7rem !important; margin-bottom: 1rem !important; }}
  .st-key-as_topbar > div:first-child {{ flex: 1 1 100% !important; width: 100% !important; }}
  .st-key-as_topbar .st-key-as_search_box {{ flex: 1 1 0 !important; min-width: 0 !important; width: auto !important; }}
  .st-key-as_topbar .st-key-as_search_box [data-testid="stTextInput"] {{ width: 100% !important; }}
  .st-key-as_topbar .st-key-as_date_box, .st-key-as_topbar .as-date {{ display: none !important; }}
  .st-key-as_topbar .st-key-as_me {{ flex: 0 0 auto !important; width: auto !important; }}
  .as-top h1 {{ font-size: 1.5rem !important; }} .as-top p {{ font-size: .82rem; }}
  /* calendario */
  .as-cal {{ gap: 3px; }} .as-cal .h {{ font-size: .66rem; }}
  .as-cal .d {{ min-height: 48px; padding: .22rem .25rem; border-radius: 8px; }}
  .as-cal .d .n {{ font-size: .7rem; }} .as-cal .d .a {{ font-size: .58rem; overflow: hidden; text-overflow: clip; }}
  [data-testid="stHorizontalBlock"]:has(.st-key-cal_prev) {{ flex-wrap: nowrap !important; gap: .4rem !important; }}
  [data-testid="stHorizontalBlock"]:has(.st-key-cal_prev) > [data-testid="stColumn"] {{
    width: auto !important; min-width: 0 !important; flex: 0 0 auto !important; }}
  [data-testid="stHorizontalBlock"]:has(.st-key-cal_prev) > [data-testid="stColumn"]:nth-child(3) {{ flex: 1 1 0 !important; }}
  [data-testid="stHorizontalBlock"]:has(.st-key-cal_prev) h3 {{ font-size: 1.15rem !important; }}
  /* avvisi: testo sopra, «Apri» e «Ignora» affiancati sotto */
  [data-testid="stHorizontalBlock"]:has(.as-alert) {{ flex-wrap: wrap !important; gap: .5rem !important; }}
  [data-testid="stHorizontalBlock"]:has(.as-alert) > [data-testid="stColumn"] {{
    flex: 1 1 0 !important; min-width: 0 !important; width: auto !important; }}
  [data-testid="stHorizontalBlock"]:has(.as-alert) > [data-testid="stColumn"]:first-child {{ flex: 1 1 100% !important; }}
}}
@media (prefers-reduced-motion: reduce) {{ .as-click .as-row, .as-pick > div {{ transition: none; }} }}
</style>"""
    st.html(css)
    if mode == "glass":
        st.html(GLASS_CSS)


# superfici "Liquid Glass": vetro = sfondo traslucido + sfocatura e saturazione di ciò che sta dietro,
# bordo chiaro sottile, riflesso in alto (riga luminosa interna) e alone morbido.
_GLASS = ("background: linear-gradient(160deg, rgba(255,255,255,0.13) 0%, rgba(255,255,255,0.05) 45%, "
          "rgba(255,255,255,0.08) 100%) !important; "
          "-webkit-backdrop-filter: blur(26px) saturate(185%) !important; backdrop-filter: blur(26px) saturate(185%) !important; "
          "border: 1px solid rgba(255,255,255,0.18) !important; box-shadow: var(--as-shadow) !important;")
GLASS_CSS = f"""
<style>
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--as-bg) !important; background-attachment: fixed !important;
  color: var(--as-ink); }}
[data-testid="stMain"], [data-testid="stBottomBlockContainer"] {{ background: transparent !important; }}
[data-testid="stSidebar"] {{ {_GLASS} border-width: 0 1px 0 0 !important; }}
[data-testid="stSidebar"] > div {{ background: transparent !important; }}
[class*="st-key-card_"], .as-kpi, .as-date, [data-testid="stExpander"] details,
[data-testid="stExpandSidebarButton"] {{ {_GLASS} }}
/* tabelle: vetro chiaro, intestazione più piena (resta leggibile quando si scorre) */
.as-table-wrap {{ background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.16);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.16); }}
.as-table {{ --as-th: rgba(38,42,92,0.92); }}
div[role="dialog"] .as-table {{ --as-th: rgba(46,50,104,0.96); }}
/* finestra di dettaglio: vetro più denso, perché sotto c'è altro testo da non far trasparire */
div[role="dialog"] {{ background: linear-gradient(160deg, rgba(40,44,96,0.86), rgba(24,26,62,0.90)) !important;
  -webkit-backdrop-filter: blur(34px) saturate(170%) !important; backdrop-filter: blur(34px) saturate(170%) !important;
  border: 1px solid rgba(255,255,255,0.20) !important;
  box-shadow: 0 30px 80px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.30) !important; }}
[class*="st-key-card_"] .as-kpi, div[role="dialog"] .as-kpi {{ background: rgba(255,255,255,0.07) !important;
  border: 1px solid rgba(255,255,255,0.12) !important; box-shadow: inset 0 1px 0 rgba(255,255,255,0.18) !important;
  -webkit-backdrop-filter: none; backdrop-filter: none; }}
/* riflesso: una luce diagonale sul bordo superiore delle card */
[class*="st-key-card_"], .as-grad {{ position: relative; }}
[class*="st-key-card_"]::before {{ content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: linear-gradient(115deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 28%); opacity: .55; }}
/* card colorate: vetro tinto */
.as-grad {{ background: linear-gradient(135deg, color-mix(in srgb, var(--g1) 58%, transparent),
  color-mix(in srgb, var(--g2) 34%, transparent)) !important; -webkit-backdrop-filter: blur(22px) saturate(180%);
  backdrop-filter: blur(22px) saturate(180%); border: 1px solid rgba(255,255,255,0.26);
  box-shadow: 0 12px 34px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.40) !important; }}
.as-grad::after {{ background: rgba(255,255,255,0.10); }} .as-grad::before {{ background: rgba(255,255,255,0.07); }}
.as-focus-top {{ background: linear-gradient(135deg, rgba(167,139,250,0.55), rgba(196,181,253,0.25)) !important;
  border: 1px solid rgba(255,255,255,0.26); -webkit-backdrop-filter: blur(20px); backdrop-filter: blur(20px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.4); }}
.as-focus-top.spesa {{ background: linear-gradient(135deg, rgba(240,98,126,0.60), rgba(247,154,126,0.28)) !important; }}
.as-focus-top.entrata {{ background: linear-gradient(135deg, rgba(20,174,158,0.60), rgba(79,211,193,0.28)) !important; }}
/* widget: campi di vetro */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"], [data-testid="stDateInputField"],
textarea, [data-testid="stNumberInputContainer"] {{ background: rgba(255,255,255,0.09) !important;
  border-color: rgba(255,255,255,0.20) !important; }}
[data-baseweb="popover"] ul, [data-baseweb="menu"] {{ background: rgba(26,31,69,0.92) !important;
  -webkit-backdrop-filter: blur(24px); backdrop-filter: blur(24px); }}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-pills"], [data-testid="stBaseButton-pillsActive"],
[data-testid="stBaseButton-segmented_control"], [data-testid="stBaseButton-segmented_controlActive"] {{
  background: rgba(255,255,255,0.10) !important; border-color: rgba(255,255,255,0.22) !important;
  -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); }}
[data-testid="stBaseButton-pillsActive"], [data-testid="stBaseButton-segmented_controlActive"] {{
  background: rgba(255,255,255,0.24) !important; }}
/* pillole e controlli segmentati (in questa versione non hanno data-testid ma data-variant) */
button[data-variant="segmented_control"], button[data-variant="pills"] {{ background: rgba(255,255,255,0.08) !important;
  border-color: rgba(255,255,255,0.20) !important; color: var(--as-ink) !important; }}
button[data-variant="segmented_control"][aria-checked="true"], button[data-variant="pills"][aria-checked="true"],
button[data-variant="pills"][aria-pressed="true"] {{ background: rgba(255,255,255,0.26) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.35); }}
[data-testid="stTextInputRootElement"], [data-testid="stFileUploaderDropzone"] {{
  background: rgba(255,255,255,0.09) !important; border-color: rgba(255,255,255,0.20) !important; }}
[data-testid="stBaseButton-primary"] {{ background: linear-gradient(135deg, rgba(167,139,250,0.85), rgba(236,72,153,0.70)) !important;
  border: 1px solid rgba(255,255,255,0.30) !important; box-shadow: inset 0 1px 0 rgba(255,255,255,0.45), 0 8px 22px rgba(0,0,0,0.25); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: rgba(255,255,255,0.16) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.25); }}
[data-testid="stSidebarNav"] a[aria-current="page"] span, [data-testid="stSidebarNav"] a[aria-current="page"] p {{ color: #FFFFFF !important; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ background: rgba(255,255,255,0.16);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.25); }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {{ color: #FFFFFF; }}
.as-click .as-row:hover, .as-pick > div:hover {{ background: rgba(255,255,255,0.10); }}
.as-pick > div.more span {{ color: #FFFFFF; }}
.as-row {{ border-bottom-color: rgba(255,255,255,0.10); }}
[data-baseweb="modal"] > div:first-child {{ background: rgba(6,8,26,0.55) !important;
  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); }}
@media (prefers-reduced-transparency: reduce) {{
  [class*="st-key-card_"], .as-kpi, [data-testid="stSidebar"], div[role="dialog"] {{ background: #1A1F45 !important;
    -webkit-backdrop-filter: none; backdrop-filter: none; }}
}}
</style>"""


# ---------------------------------------------------------------- grafici
_CCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "JPY": "¥"}
_PX_FIELD = re.compile(r"([^<>=]+)=%\{(x|y|label|value|customdata\[\d+\])[^}]*\}")


def _italian_hover(fig) -> None:
    """Riscrive i tooltip generati automaticamente da plotly express (formato inglese «campo=valore»)
    in un formato italiano leggibile; i tooltip già personalizzati non vengono toccati."""
    for tr in fig.data:
        tpl = getattr(tr, "hovertemplate", None)
        if not tpl or "=%{" not in tpl:
            continue
        fields = {m.group(2): m.group(1).strip() for m in _PX_FIELD.finditer(tpl.replace("<br>", "\n<"))}
        horizontal = getattr(tr, "orientation", None) == "h"
        val_axis, cat_axis = ("x", "y") if horizontal else ("y", "x")
        unit_name = fields.get(val_axis, "")
        unit = _CCY_SYMBOL.get(unit_name, "")
        is_date = False
        try:
            first = list(getattr(tr, cat_axis))[0]
            import numpy as np
            is_date = (isinstance(first, np.datetime64) or hasattr(first, "year")
                       or (isinstance(first, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", first))))
        except Exception:
            pass
        cat = f"%{{{cat_axis}|{i18n.strf()}}}" if is_date else f"%{{{cat_axis}}}"
        decimals = ",.2f" if unit else ",.4~f"
        val = f"%{{{val_axis}:{decimals}}}" + (f" {unit}" if unit else "")
        name = tr.name if getattr(tr, "name", None) else ""
        head = f"<b>{html.escape(str(name))}</b><br>" if name else ""
        if tr.type == "pie":
            tr.hovertemplate = "<b>%{label}</b><br>%{value:,.2f}<extra></extra>"
        else:
            tr.hovertemplate = f"{head}{cat}<br>{val}<extra></extra>"


# nomi di mesi e giorni in italiano per gli assi con date (plotly registra la lingua al volo)
_IT_LOCALE = {
    "moduleType": "locale", "name": "it",
    "dictionary": {},
    "format": {
        "days": ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"],
        "shortDays": ["dom", "lun", "mar", "mer", "gio", "ven", "sab"],
        "months": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
                   "settembre", "ottobre", "novembre", "dicembre"],
        "shortMonths": ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"],
        "periods": ["AM", "PM"], "decimal": ",", "thousands": ".", "grouping": [3], "currency": ["", " €"],
        "date": "%d/%m/%Y", "time": "%H:%M:%S", "dateTime": "%a %e %b %Y %X", "year": "%Y", "month": "%b %Y",
        "dayMonth": "%e %b", "dayMonthYear": "%e %b %Y",
    },
}
PLOTLY_CONFIG = {"displayModeBar": False, "locale": "it", "locales": {"it": _IT_LOCALE}}


def plotly_config() -> dict:
    """Configurazione dei grafici nella lingua attuale (in inglese vale quella predefinita di plotly)."""
    return {"displayModeBar": False, "locale": "en"} if i18n.is_en() else PLOTLY_CONFIG


def chart(fig, height: int | None = None, legend: bool = True) -> None:
    """Stile comune a tutti i grafici plotly: niente sfondo, barre arrotondate, griglia leggera."""
    fig.update_layout(
        height=height or fig.layout.height or 340, margin=dict(l=0, r=0, t=28 if fig.layout.title.text else 8, b=0),
        font=dict(family=FONT_BODY, size=12),
        title_font=dict(family=FONT_DISPLAY, size=15),
        separators=".," if i18n.is_en() else ",.",  # italiano: virgola per i decimali, punto per le migliaia
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=legend and fig.layout.showlegend is not False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None),
        bargap=0.38, hoverlabel=dict(font=dict(family=FONT_BODY, size=13), align="left"),
    )
    _italian_hover(fig)
    fig.update_traces(marker_cornerradius=6, selector=dict(type="bar"))
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False, ticks="", title=None, tickangle=0,
                     automargin=True)
    fig.update_yaxes(gridcolor="rgba(150,140,190,0.16)", griddash="dot", zeroline=False, showline=False,
                     ticks="", title=None)
    st.plotly_chart(fig, width="stretch", config=plotly_config())


# ---------------------------------------------------------------- componenti
def e(text) -> str:
    return html.escape(str(text if text is not None else ""))


def card(key: str):
    """Contenitore a card bianca arrotondata: `with style.card("nome"): ...`"""
    return st.container(key=f"card_{key}")


AVATAR_GRADIENTS = {"viola": ("#7C5CFC", "#F0627E"), "blu": ("#3B82F6", "#22D3EE"), "verde": ("#14AE9E", "#84CC16"),
                    "arancio": ("#F59E0B", "#EF4444"), "rosa": ("#EC4899", "#A855F7"), "grafite": ("#475569", "#0F172A")}


def profile_name() -> str:
    from core import db
    name = (db.get_setting("profile_name", "") or "").strip()
    if not name:
        owners = db.owner_names()
        name = owners[0].title() if owners else ""
    return name


def initials_of(name: str) -> str:
    parts = re.findall(r"[A-Za-zÀ-ÿ]+", name or "")[:2]
    return "".join(p[0].upper() for p in parts) or "?"


def avatar_colors() -> tuple[str, str]:
    from core import db
    return AVATAR_GRADIENTS.get(db.get_setting("profile_color", "viola") or "viola", AVATAR_GRADIENTS["viola"])


_DATE_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const old = parentElement.querySelector('.as-date');
  if (old) old.remove();
  const d = document.createElement('div');
  d.className = 'as-date as-date-click';
  const b = document.createElement('b'); b.textContent = data.day; d.appendChild(b);
  const s = document.createElement('span'); s.textContent = data.date; d.appendChild(s);
  d.tabIndex = 0; d.setAttribute('role', 'link'); d.title = data.title;
  d.setAttribute('aria-label', data.aria);
  const go = () => setTriggerValue('open', true);
  d.addEventListener('click', go);
  d.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); go(); } });
  parentElement.appendChild(d);
}
"""
_date_component = None


def _date_chip(day: str, date_txt: str) -> bool:
    global _date_component
    if _date_component is None:
        import streamlit.components.v2 as v2
        _date_component = v2.component("as_date_chip", js=_DATE_JS, isolate_styles=False)
    with st.container(key="as_date_box", width="content"):
        res = _date_component(data={"day": day, "date": date_txt, "title": t("Apri il calendario"),
                                    "aria": t("Oggi, {day} {date}: apri il calendario", day=day, date=date_txt)},
                              key="as_date_chip", on_open_change=lambda: None)
    return bool(getattr(res, "open", None)) if res is not None else False


def header(title: str, subtitle: str | None = None) -> None:
    """Barra superiore: titolo e sottotitolo a sinistra; a destra la data e l'avatar, che apre il menu del profilo
    (Profilo, Importa estratti, Collega banche, Impostazioni)."""
    from datetime import date

    from views import nav

    today = date.today()
    sub = f"<p>{e(subtitle)}</p>" if subtitle else ""
    name = profile_name()
    a, b = avatar_colors()
    from core import db
    sub_me = (t("Account di prova: dati fittizi") if db.is_demo() else
              t("Amministratore") if db.is_admin() else t("Dati salvati solo su questo computer"))
    st.html(f'<style>.st-key-as_me button {{ background: linear-gradient(135deg, {a}, {b}) !important; }}</style>')
    with st.container(key="as_topbar", horizontal=True, vertical_alignment="center", gap="small"):
        st.html(f'<div class="as-top"><div><h1>{e(title)}</h1>{sub}</div></div>', width="stretch")
        from views import cerca
        with st.container(key="as_search_box", width="content"):
            cerca.box()
        if "calendario" in nav.PAGES:
            # la data di oggi è una scorciatoia per il calendario del mese in corso
            if _date_chip(i18n.weekday(today.weekday()), f"{today:{i18n.strf()}}"):
                st.session_state["cal_month"] = today.replace(day=1)
                st.switch_page(nav.PAGES["calendario"])
        else:
            st.html(f'<div class="as-date"><b>{i18n.weekday(today.weekday())}</b><span>{today:{i18n.strf()}}</span></div>',
                    width="content")
        with st.container(key="as_me", width="content"):
            with st.popover(initials_of(name), help=t("Profilo e impostazioni")):
                st.html(f'''<div class="as-me-head"><div class="as-avatar big" style="background:linear-gradient(135deg,{a},{b})">
{e(initials_of(name))}</div><div><b>{e(name or t("Il tuo profilo"))}</b><span>{e(sub_me)}</span></div></div>''')
                for key, label, icon in (("profilo", "Profilo e conti", ":material/person:"),
                                         ("carte", "Carte", ":material/credit_card:"),
                                         ("importa", "Importa estratti", ":material/upload_file:"),
                                         ("banche", "Collega banche", ":material/account_balance:"),
                                         ("impostazioni", "Impostazioni", ":material/tune:"),
                                         ("utenti", "Utenti", ":material/group:")):
                    if key == "utenti" and not db.is_admin():
                        continue  # la gestione degli utenti è solo dell'amministratore
                    if key in nav.PAGES:
                        st.page_link(nav.PAGES[key], label=t(label), icon=icon, width="stretch")
                from views import lingua, login
                with st.container(key="as_me_lang", horizontal=True, vertical_alignment="center"):
                    st.html(f'<span class="as-me-lang">{e(t("Lingua"))}</span>', width="stretch")
                    lingua.selector("as_lang_sel", compact=True)
                st.button(t("Esci"), key="as_logout", icon=":material/logout:", type="tertiary", width="stretch",
                          on_click=login.logout, help=t("Chiude la sessione: per rientrare servono nome utente e password"))


def table(df: pd.DataFrame, fmt: dict | None = None, *, index: bool = False, height: int | None = None,
          total_last: bool = False, neg: tuple = ()) -> None:
    """Tabella nello stile dell'app (al posto di st.dataframe per le tabelle da leggere).
    fmt: {colonna: formato}; formati: "money" o ("money", valuta), "num" (2 decimali) o ("num", decimali),
    "int", ("pct", decimali), "bar" (percentuale con barra), "date", "text". Senza formato: numeri con 2
    decimali (interi senza), date nel formato della lingua.
    index: mostra l'indice come prima colonna; height: altezza massima in px (poi scorre);
    total_last: l'ultima riga è un totale (in grassetto); neg: colonne in cui i negativi sono in rosso."""
    from views import ui

    fmt = fmt or {}
    data = df.reset_index() if index else df
    cols = list(data.columns)

    def cell(col, v) -> tuple[str, str]:
        spec = fmt.get(col)
        kind, arg = (spec if isinstance(spec, tuple) else (spec, None))
        if v is None or (not isinstance(v, str) and pd.api.types.is_scalar(v) and pd.isna(v)):
            return "–", "num" if kind not in (None, "text", "date") else ""
        if kind == "text":
            return e(v), ""
        if kind == "bar":
            w = max(0.0, min(100.0, float(v)))
            return (f'<span class="tbar"><i><span style="width:{w:.1f}%"></span></i>'
                    f'<em>{e(ui.fmt_num(float(v), 1))}%</em></span>'), ""
        if kind == "date" or isinstance(v, (pd.Timestamp, date)):
            try:
                return e(f"{pd.Timestamp(v):{i18n.strf()}}"), ""
            except (ValueError, TypeError):
                return e(v), ""
        if isinstance(v, (bool,)) or not isinstance(v, (int, float)) and not pd.api.types.is_number(v):
            return e(v), ""
        x = float(v)
        cls = "num" + (" neg" if col in neg and x < 0 else "")
        if kind == "money":
            return e(ui.money(x, arg)), cls
        if kind == "int":
            return e(ui.fmt_num(x, 0)), cls
        if kind == "pct":
            return e(ui.fmt_num(x, arg if arg is not None else 1) + "%"), cls
        if kind == "num":
            return e(ui.fmt_num(x, arg if arg is not None else 2)), cls
        is_int = pd.api.types.is_integer(v) or (pd.api.types.is_integer_dtype(data[col].dtype))
        return e(ui.fmt_num(x, 0 if is_int else 2)), cls

    def kind_of(c):
        spec = fmt.get(c)
        return spec[0] if isinstance(spec, tuple) else spec

    numeric = {c for c in cols if kind_of(c) in ("money", "num", "int", "pct")
               or (kind_of(c) is None and pd.api.types.is_numeric_dtype(data[c].dtype)
                   and not pd.api.types.is_bool_dtype(data[c].dtype))}
    head = "".join(f'<th class="{"num" if c in numeric else ""}">{e(c)}</th>' for c in cols)
    body = []
    n = len(data)
    for i, row in enumerate(data.itertuples(index=False, name=None)):
        tds = []
        for j, (c, v) in enumerate(zip(cols, row)):
            txt, cls = cell(c, v)
            if j == 0:
                cls = (cls + " first").strip()
            tds.append(f'<td class="{cls}">{txt}</td>')
        tr_cls = ' class="tot"' if total_last and i == n - 1 else ""
        body.append(f"<tr{tr_cls}>{''.join(tds)}</tr>")
    style_h = f' style="max-height:{int(height)}px"' if height else ""
    st.html(f'<div class="as-table-wrap"{style_h}><table class="as-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def gradient_cards(items: list[dict], key: str | None = None) -> str | None:
    """items: dict(label, value, sub, variant in GRADIENTS, pct=None|0..100, pct_label='', id=…,
    foot=None|(testo, valore): riga sotto il valore, es. ("Speso questo mese", "459,93 €")).
    Con `key` le card sono cliccabili e ritorna l'id della card cliccata (una volta per clic)."""
    if key:
        data = []
        for it in items:
            a, b = GRADIENTS.get(it.get("variant"), GRADIENTS["saldo"])
            w = None if it.get("pct") is None else max(0.0, min(100.0, float(it["pct"])))
            data.append({"id": str(it.get("id", it["label"])), "label": it["label"], "sub": it.get("sub") or "",
                         "value": it["value"], "g1": a, "g2": b, "pct": w,
                         "pct_label": it.get("pct_label", f"{w:.0f}%" if w is not None else ""),
                         "foot": list(it["foot"]) if it.get("foot") else None})
        global _grads_component
        if _grads_component is None:
            import streamlit.components.v2 as v2
            _grads_component = v2.component("as_grad_cards", js=_GRADS_JS, isolate_styles=False)
        res = _grads_component(data={"items": data, "detail": t("Dettaglio: ")}, key=key,
                               on_selected_change=lambda: None)
        return getattr(res, "selected", None) if res is not None else None
    cells = []
    for it in items:
        a, b = GRADIENTS.get(it.get("variant"), GRADIENTS["saldo"])
        prog = ""
        if it.get("pct") is not None:
            w = max(0.0, min(100.0, float(it["pct"])))
            prog = (f'<div class="p"><div class="bar"><span style="width:{w:.1f}%"></span></div>'
                    f'<b>{e(it.get("pct_label", f"{w:.0f}%"))}</b></div>')
        sub = f'<div class="s">{e(it["sub"])}</div>' if it.get("sub") else ""
        foot = (f'<div class="f">{e(it["foot"][0])} <b>{e(it["foot"][1])}</b></div>' if it.get("foot") else "")
        cells.append(f'<div class="as-grad" style="--g1:{a};--g2:{b};background:linear-gradient(135deg,{a},{b})">'
                     f'<div class="l">{e(it["label"])}</div>{sub}<div class="v">{e(it["value"])}</div>{foot}{prog}</div>')
    st.html(f'<div class="as-grads">{"".join(cells)}</div>')
    return None


_grads_component = None
_GRADS_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const old = parentElement.querySelector('.as-grads');
  if (old) old.remove();
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls;
                                    if (text !== undefined) n.textContent = text; return n; };
  const root = el('div', 'as-grads as-grads-click');
  for (const it of data.items) {
    const c = el('div', 'as-grad');
    c.style.setProperty('--g1', it.g1); c.style.setProperty('--g2', it.g2);
    c.style.background = 'linear-gradient(135deg,' + it.g1 + ',' + it.g2 + ')';
    c.appendChild(el('div', 'l', it.label));
    if (it.sub) c.appendChild(el('div', 's', it.sub));
    c.appendChild(el('div', 'v', it.value));
    if (it.foot) { const f = el('div', 'f', it.foot[0] + ' '); f.appendChild(el('b', '', it.foot[1])); c.appendChild(f); }
    if (it.pct !== null && it.pct !== undefined) {
      const p = el('div', 'p'); const bar = el('div', 'bar'); const sp = el('span');
      sp.style.width = it.pct + '%'; bar.appendChild(sp); p.appendChild(bar); p.appendChild(el('b', '', it.pct_label));
      c.appendChild(p);
    }
    const go = el('div', 'go', 'arrow_outward'); go.setAttribute('aria-hidden', 'true'); c.appendChild(go);
    c.tabIndex = 0; c.setAttribute('role', 'button'); c.setAttribute('aria-label', data.detail + it.label);
    const open = () => setTriggerValue('selected', it.id);
    c.addEventListener('click', open);
    c.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    root.appendChild(c);
  }
  parentElement.appendChild(root);
}
"""


_KPIS_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const old = parentElement.querySelector('.as-kpis');
  if (old) old.remove();
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls;
                                    if (text !== undefined) n.textContent = text; return n; };
  const root = el('div', 'as-kpis as-kpis-click');
  if (data.cols) root.style.gridTemplateColumns = 'repeat(' + data.cols + ',minmax(0,1fr))';
  for (const it of data.items) {
    const c = el('div', 'as-kpi' + (it.id ? ' click' : ''));
    c.appendChild(el('div', 'l', it.label));
    c.appendChild(el('div', 'v ' + (it.cls || ''), it.value));
    if (it.note) c.appendChild(el('div', 'd', it.note));
    if (it.id) {
      const go = el('div', 'go', 'arrow_outward'); go.setAttribute('aria-hidden', 'true'); c.appendChild(go);
      c.tabIndex = 0; c.setAttribute('role', 'button'); c.setAttribute('aria-label', data.detail + it.label);
      const open = () => setTriggerValue('selected', it.id);
      c.addEventListener('click', open);
      c.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    }
    root.appendChild(c);
  }
  parentElement.appendChild(root);
}
"""
_kpis_component = None


def kpis(items: list[tuple], cols: int | None = None, key: str | None = None,
         ids: list[str | None] | None = None) -> str | None:
    """items: (etichetta, valore, nota_opzionale, classe_opzionale 'pos'/'neg'/''); cols: colonne (default 3).
    Con `key` e `ids` (un id per riquadro, None = non cliccabile) i riquadri si possono cliccare: ritorna l'id del
    riquadro cliccato (una volta per clic) oppure None."""
    if key and ids:
        global _kpis_component
        if _kpis_component is None:
            import streamlit.components.v2 as v2
            _kpis_component = v2.component("as_kpis_click", js=_KPIS_JS, isolate_styles=False)
        data = []
        for i, it in enumerate(items):
            data.append({"id": ids[i] if i < len(ids) and ids[i] else "", "label": str(it[0]), "value": str(it[1]),
                         "note": str(it[2]) if len(it) > 2 and it[2] else "",
                         "cls": it[3] if len(it) > 3 and it[3] else ""})
        res = _kpis_component(data={"items": data, "cols": int(cols) if cols else 0, "detail": t("Dettaglio: ")},
                              key=key, on_selected_change=lambda: None)
        sel = getattr(res, "selected", None) if res is not None else None
        return sel or None
    cells = []
    for it in items:
        label, value = it[0], it[1]
        note = it[2] if len(it) > 2 else None
        cls = it[3] if len(it) > 3 else ""
        d = f'<div class="d">{e(note)}</div>' if note else ""
        cells.append(f'<div class="as-kpi"><div class="l">{e(label)}</div><div class="v {cls}">{e(value)}</div>{d}</div>')
    style_attr = f' style="grid-template-columns:repeat({int(cols)},minmax(0,1fr))"' if cols else ""
    st.html(f'<div class="as-kpis"{style_attr}>{"".join(cells)}</div>')
    return None


_MORE, _LESS = "__altre__", "__meno__"


def _group(rows: list[tuple[str, float, str]], limit: int, key: str | None,
           others: str | None = None) -> tuple[list, float, bool]:
    """Toglie le voci a zero e, oltre `limit`, raggruppa le ultime in 'Altre N categorie'
    (se la lista è cliccabile, un clic su quella voce mostra tutte le categorie)."""
    rows = [r for r in rows if r[1] > 0]
    total = sum(r[1] for r in rows)
    expanded = bool(key) and st.session_state.get(f"{key}_tutte", False)
    if len(rows) > limit and not expanded:
        rest = sum(r[1] for r in rows[limit - 1:])
        n_more = len(rows) - limit + 1
        label = others.format(n=n_more) if others else t("Altre {n} categorie", n=n_more)
        rows = rows[:limit - 1] + [(label, rest, "#C9C6D8", _MORE)]
    elif len(rows) > limit:
        rows = rows + [(t("Mostra meno"), 0.0, "", _LESS)]
    return rows, total, expanded


def _picked(sel, key: str) -> str | None:
    """Gestisce i clic su 'Altre…' / 'Mostra meno'; per una categoria ne ritorna il nome."""
    if sel in (_MORE, _LESS):
        st.session_state[f"{key}_tutte"] = sel == _MORE
        from streamlit.errors import StreamlitAPIException
        try:  # dentro una finestra di dettaglio si ridisegna solo la finestra, che così resta aperta
            st.rerun(scope="fragment")
        except StreamlitAPIException:
            st.rerun()
    return sel or None


def donut(rows: list[tuple[str, float, str]], center_label: str, center_value: str, fmt, limit: int = 6,
          key: str | None = None) -> str | None:
    """Ciambella con legenda. rows: (nome, importo, colore); oltre `limit` voci raggruppa in 'Altre'.
    Con `key` la legenda è cliccabile e ritorna il nome della categoria scelta (una volta per clic)."""
    import plotly.graph_objects as go

    rows, total, _ = _group(rows, limit, key)
    if not total:
        return None
    pie = [r for r in rows if r[1] > 0]
    fig = go.Figure(go.Pie(
        labels=[r[0] for r in pie], values=[r[1] for r in pie], hole=0.72, sort=False, direction="clockwise",
        marker=dict(colors=[safe_color(r[2]) for r in pie], line=dict(color="rgba(0,0,0,0)", width=0)),
        textinfo="none", hovertemplate="%{label}<br>%{value:,.2f}<extra></extra>"))
    fig.add_annotation(text=f"<span style='font-size:11px'>{e(center_label)}</span><br><b>{e(center_value)}</b>",
                       showarrow=False, x=0.5, y=0.5, font=dict(size=17))
    chart(fig, height=230, legend=False)
    if not key:
        items = "".join(f'<div><i style="background:{safe_color(c)}"></i><span>{e(n)}</span><b>{e(fmt(v))}</b>'
                        f'<em>{v / total * 100:.0f}%</em></div>' for n, v, c, *_ in rows)
        st.html(f'<div class="as-legend">{items}</div>')
        return None
    return _picked(_pick_list(rows, total, fmt, "legend", key), key)


def category_bars(rows: list[tuple[str, float, str]], fmt, limit: int = 8, key: str | None = None,
                  others: str | None = None) -> str | None:
    """rows: (nome, importo, colore). Lista con barre, le restanti raggruppate in 'Altre'.
    Con `key` le voci sono cliccabili e ritorna il nome della categoria scelta (una volta per clic)."""
    rows, total, _ = _group(rows, limit, key, others)
    if not total:
        return None
    if not key:
        top = max(r[1] for r in rows)
        items = "".join(f'''<div class="as-cat"><div class="top"><div class="n"><i class="dot" style="background:{safe_color(c)}"></i>
<span>{e(n)}</span></div><div><span class="amt">{e(fmt(v))}</span><span class="pct">{v / total * 100:.0f}%</span></div></div>
<div class="track"><span style="width:{v / top * 100:.1f}%;background:{safe_color(c)}"></span></div></div>''' for n, v, c, *_ in rows)
        st.html(f'<div class="as-cats">{items}</div>')
        return None
    return _picked(_pick_list(rows, total, fmt, "bars", key), key)


_PICK_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const old = parentElement.querySelector('.as-pick');
  if (old) old.remove();
  const bars = data.mode === 'bars';
  const root = document.createElement('div');
  root.className = 'as-pick ' + (bars ? 'as-cats' : 'as-legend');
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls;
                                    if (text !== undefined) n.textContent = text; return n; };
  for (const r of data.rows) {
    const row = el('div', (bars ? 'as-cat' : '') + (r.special ? ' more' : ''));
    const dot = el('i', bars ? 'dot' : ''); dot.style.background = r.color || 'transparent';
    if (bars) {
      const top = el('div', 'top'); const n = el('div', 'n');
      n.appendChild(dot); n.appendChild(el('span', '', r.name)); top.appendChild(n);
      const right = el('div');
      if (r.amount) { right.appendChild(el('span', 'amt', r.amount)); right.appendChild(el('span', 'pct', r.pct)); }
      top.appendChild(right); row.appendChild(top);
      if (r.width) { const tr = el('div', 'track'); const s = el('span'); s.style.width = r.width + '%';
                     s.style.background = r.color; tr.appendChild(s); row.appendChild(tr); }
    } else {
      row.appendChild(dot); row.appendChild(el('span', '', r.name));
      row.appendChild(el('b', '', r.amount || '')); row.appendChild(el('em', '', r.pct || ''));
    }
    row.tabIndex = 0; row.setAttribute('role', 'button');
    row.setAttribute('aria-label', r.special ? r.name : data.open + r.name);
    const open = () => setTriggerValue('selected', r.id);
    row.addEventListener('click', open);
    row.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    root.appendChild(row);
  }
  parentElement.appendChild(root);
}
"""
_pick_component = None


def _pick_list(rows: list, total: float, fmt, mode: str, key: str):
    global _pick_component
    if _pick_component is None:
        import streamlit.components.v2 as v2
        _pick_component = v2.component("as_pick_list", js=_PICK_JS, isolate_styles=False)
    top = max((r[1] for r in rows), default=0) or 1
    data = [{"id": (r[3] if len(r) > 3 else r[0]), "name": r[0], "special": len(r) > 3,
             "amount": fmt(r[1]) if r[1] else "", "pct": f"{r[1] / total * 100:.0f}%" if r[1] else "",
             "color": safe_color(r[2]) if r[2] else "", "width": round(r[1] / top * 100, 1) if r[1] else 0}
            for r in rows]
    res = _pick_component(data={"rows": data, "mode": mode, "open": t("Apri il dettaglio di ")}, key=key,
                          on_selected_change=lambda: None)
    return getattr(res, "selected", None) if res is not None else None


# ---------------------------------------------------------------- elenco movimenti cliccabile
_TX_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const old = parentElement.querySelector('.as-list');
  if (old) old.remove();
  const root = document.createElement('div');
  root.className = 'as-list' + (data.clickable ? ' as-click' : '');
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls;
                                    if (text !== undefined) n.textContent = text; return n; };
  for (const r of data.rows) {
    const row = el('div', 'as-row');
    const ink = 'color-mix(in srgb, ' + r.color + ' 62%, var(--as-ink))';  // testo leggibile anche su colori chiari
    const av = el('div', 'av', r.ini); av.style.background = r.soft; av.style.color = ink; row.appendChild(av);
    const ds = el('div', 'ds');
    ds.appendChild(el('div', 't', r.desc));
    ds.appendChild(el('div', 'm', r.meta));
    row.appendChild(ds);
    if (r.cat) {
      const pill = el('span', 'pill', r.cat); pill.style.background = r.soft; pill.style.color = ink;
      row.appendChild(pill);
    } else { row.classList.add('nopill'); }
    const am = el('div', 'am ' + r.cls, r.amount);
    if (r.sub) am.appendChild(el('small', '', r.sub));
    row.appendChild(am);
    if (data.clickable) {
      row.tabIndex = 0; row.setAttribute('role', 'button');
      row.setAttribute('aria-label', data.open + r.desc);
      const open = () => setTriggerValue('selected', r.id);
      row.addEventListener('click', open);
      row.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    }
    root.appendChild(row);
  }
  parentElement.appendChild(root);
}
"""
_tx_component = None


def _component():
    global _tx_component
    if _tx_component is None:
        import streamlit.components.v2 as v2
        _tx_component = v2.component("as_tx_list", js=_TX_JS, isolate_styles=False)
    return _tx_component


def _initials(text: str) -> str:
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9]+", str(text or "")) if not w.isdigit()]
    skip = {"pagamento", "bonifico", "istantaneo", "addebito", "sumup", "paypal", "a", "da", "di", "favore", "parte"}
    words = [w for w in words if w.lower() not in skip] or words
    return "".join(w[0].upper() for w in words[:2]) or "•"


def _is_split(r) -> bool:
    """Parte di un movimento diviso, o movimento diviso in parti."""
    for c in ("split_of", "split_total"):
        v = r.get(c)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            return True
    return False


def tx_list(df: pd.DataFrame, fmt_amount, colors: dict[str, str], base: str, key: str,
            clickable: bool = True) -> int | None:
    """Elenco movimenti: iniziali, descrizione, data e conto, categoria, importo (e controvalore se in valuta).
    Cliccando (o premendo Invio) su una riga ritorna l'id del movimento, una sola volta per clic."""
    from core import db

    labels = db.category_labels()
    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        amt = float(r["amount"])
        sub = ""
        if r["currency"] != base and pd.notna(r.get("valore_base")):
            sub = fmt_amount(r["valore_base"], base)
        color = safe_color(colors.get(r["category"], "#A3A0B5"))
        dt = i18n.date_short(d) if pd.notna(d) else ""
        rows.append({
            "id": int(r["id"]),
            "ini": _initials(r["description"]),
            "desc": str(r["description"] or ""),
            "meta": f"{dt}, {r['account']}" + (t(", diviso") if _is_split(r) else ""),
            "cat": str(labels.get(r["category"], r["category"]) or "") if isinstance(r["category"], str) else "",
            "color": color,
            "soft": rgba(color, 0.16),
            "amount": fmt_amount(amt, r["currency"]),
            "sub": sub,
            "cls": "pos" if (amt > 0 and r.get("kind") == "entrata") else "",
        })
    sel = item_list(rows, key=key, clickable=clickable)
    return int(sel) if sel is not None else None


def item_list(rows: list[dict], key: str, clickable: bool = True):
    """Elenco generico nello stile dei movimenti. Ogni riga: id, ini (iniziali), desc, meta, cat (pillola),
    color, soft (sfondo pillola), amount, sub (riga sotto l'importo), cls ('pos' per verde).
    Ritorna l'id della riga cliccata (una volta per clic) oppure None."""
    for r in rows:
        r.setdefault("ini", _initials(r.get("desc", "")))
        r["color"] = safe_color(r.get("color", "#A3A0B5"))
        r.setdefault("soft", rgba(r["color"], 0.16))
        for k in ("meta", "cat", "amount", "sub", "cls"):
            r.setdefault(k, "")
    res = _component()(data={"rows": rows, "clickable": clickable, "open": t("Apri il dettaglio di ")}, key=key,
                       on_selected_change=lambda: None)
    return getattr(res, "selected", None) if res is not None else None
