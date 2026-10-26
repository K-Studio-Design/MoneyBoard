"""Parametri fiscali USA per il calcolo delle tasse sugli stipendi (funzione in prova, alpha).

Anno dei parametri: 2026.
Fonti:
- federale: IRS Rev. Proc. 2025-32 (scaglioni e deduzione standard 2026);
- Social Security: base massima 2026 annunciata dalla SSA (184.500 $); Medicare 1,45% + 0,9% oltre le soglie di legge;
- stati: Tax Foundation, «State Individual Income Tax Rates and Brackets, 2026» (dati al 1° gennaio 2026),
  aggiornati con le leggi approvate nel 2026 e retroattive al 1° gennaio 2026:
  Georgia (HB 463: 4,99%, deduzione 15.000/30.000), Carolina del Sud (H.4216: 1,99% fino a 30.000, 5,21% oltre,
  deduzione 15.000/30.000), Virginia Occidentale (SB 392), Utah (SB 60: 4,45%), Arkansas (HB1001: 3,7%),
  Hawaii (deduzione standard 2026: 8.000/16.000).
Scaglioni: lista di (soglia, aliquota %) — l'aliquota vale per la parte di imponibile oltre la soglia.
"""
from __future__ import annotations

YEAR = 2026

# ---------------------------------------------------------------- federale
FILING = ("single", "mfj", "mfs", "hoh")
FEDERAL_SD = {"single": 16_100, "mfj": 32_200, "mfs": 16_100, "hoh": 24_150}
FEDERAL = {
    "single": [(0, 10), (12_400, 12), (50_400, 22), (105_700, 24), (201_775, 32), (256_225, 35), (640_600, 37)],
    "mfj": [(0, 10), (24_800, 12), (100_800, 22), (211_400, 24), (403_550, 32), (512_450, 35), (768_700, 37)],
    "mfs": [(0, 10), (12_400, 12), (50_400, 22), (105_700, 24), (201_775, 32), (256_225, 35), (384_350, 37)],
    "hoh": [(0, 10), (17_700, 12), (67_450, 22), (105_700, 24), (201_750, 32), (256_200, 35), (640_600, 37)],
}

# ---------------------------------------------------------------- FICA (contributi sociali sul lavoro dipendente)
SS_RATE = 6.2
SS_WAGE_BASE = 184_500
MEDICARE_RATE = 1.45
ADD_MEDICARE_RATE = 0.9
ADD_MEDICARE_THRESHOLD = {"single": 200_000, "mfj": 250_000, "mfs": 125_000, "hoh": 200_000}

# ---------------------------------------------------------------- stati
# s / j: scaglioni per single e per coppie (dichiarazione congiunta)
# sd: deduzione standard (single, coppia); ex: esenzione personale (single, coppia);
# credit: esenzione che è un credito d'imposta (single, coppia)
NO_TAX = {
    "AK": "Alaska", "FL": "Florida", "NV": "Nevada", "NH": "New Hampshire", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "WA": "Washington", "WY": "Wyoming",
}


def _same(b):
    return {"s": b, "j": b}


STATES: dict[str, dict] = {
    "AL": {"name": "Alabama", "s": [(0, 2), (500, 4), (3_000, 5)], "j": [(0, 2), (1_000, 4), (6_000, 5)],
           "sd": (3_000, 8_500), "ex": (1_500, 3_000)},
    "AZ": {"name": "Arizona", **_same([(0, 2.5)]), "sd": (8_350, 16_700)},
    "AR": {"name": "Arkansas", **_same([(0, 2.0), (4_600, 3.7)]), "sd": (2_470, 4_940), "credit": (29, 58)},
    "CA": {"name": "California",
           "s": [(0, 1), (11_079, 2), (26_264, 4), (41_452, 6), (57_542, 8), (72_724, 9.3), (371_479, 10.3),
                 (445_771, 11.3), (742_953, 12.3), (1_000_000, 13.3)],
           "j": [(0, 1), (22_158, 2), (52_528, 4), (82_904, 6), (115_084, 8), (145_448, 9.3), (742_958, 10.3),
                 (891_542, 11.3), (1_000_000, 12.3), (1_485_906, 13.3)],
           "sd": (5_540, 11_080), "credit": (153, 306)},
    "CO": {"name": "Colorado", **_same([(0, 4.4)]), "sd": (16_100, 32_200)},
    "CT": {"name": "Connecticut",
           "s": [(0, 2), (10_000, 4.5), (50_000, 5.5), (100_000, 6), (200_000, 6.5), (250_000, 6.9), (500_000, 6.99)],
           "j": [(0, 2), (20_000, 4.5), (100_000, 5.5), (200_000, 6), (400_000, 6.5), (500_000, 6.9),
                 (1_000_000, 6.99)],
           "ex": (15_000, 24_000)},
    "DE": {"name": "Delaware", **_same([(2_000, 2.2), (5_000, 3.9), (10_000, 4.8), (20_000, 5.2), (25_000, 5.55),
                                        (60_000, 6.6)]),
           "sd": (3_250, 6_500), "credit": (110, 220)},
    "GA": {"name": "Georgia", **_same([(0, 4.99)]), "sd": (15_000, 30_000)},
    "HI": {"name": "Hawaii",
           "s": [(0, 1.4), (9_600, 3.2), (14_400, 5.5), (19_200, 6.4), (24_000, 6.8), (36_000, 7.2), (48_000, 7.6),
                 (125_000, 7.9), (175_000, 8.25), (225_000, 9), (275_000, 10), (325_000, 11)],
           "j": [(0, 1.4), (19_200, 3.2), (28_800, 5.5), (38_400, 6.4), (48_000, 6.8), (72_000, 7.2), (96_000, 7.6),
                 (250_000, 7.9), (350_000, 8.25), (450_000, 9), (550_000, 10), (650_000, 11)],
           "sd": (8_000, 16_000), "ex": (1_144, 2_288)},
    "ID": {"name": "Idaho", "s": [(4_811, 5.3)], "j": [(9_622, 5.3)], "sd": (16_100, 32_200)},
    "IL": {"name": "Illinois", **_same([(0, 4.95)]), "ex": (2_925, 5_850)},
    "IN": {"name": "Indiana", **_same([(0, 2.95)]), "ex": (1_000, 2_000)},
    "IA": {"name": "Iowa", **_same([(0, 3.8)]), "sd": (16_100, 32_200), "credit": (40, 80)},
    "KS": {"name": "Kansas", "s": [(0, 5.2), (23_000, 5.58)], "j": [(0, 5.2), (46_000, 5.58)],
           "sd": (3_605, 8_240), "ex": (9_160, 18_320)},
    "KY": {"name": "Kentucky", **_same([(0, 3.5)]), "sd": (3_360, 3_360)},
    "LA": {"name": "Louisiana", **_same([(0, 3.0)]), "sd": (12_875, 25_750)},
    "ME": {"name": "Maine", "s": [(0, 5.8), (27_399, 6.75), (64_849, 7.15)],
           "j": [(0, 5.8), (54_849, 6.75), (129_749, 7.15)], "sd": (8_350, 16_700), "ex": (5_300, 10_600)},
    "MD": {"name": "Maryland",
           "s": [(0, 2), (1_000, 3), (2_000, 4), (3_000, 4.75), (100_000, 5), (125_000, 5.25), (150_000, 5.5),
                 (250_000, 5.75), (500_000, 6.25), (1_000_000, 6.5)],
           "j": [(0, 2), (1_000, 3), (2_000, 4), (3_000, 4.75), (150_000, 5), (175_000, 5.25), (225_000, 5.5),
                 (300_000, 5.75), (600_000, 6.25), (1_200_000, 6.5)],
           "sd": (3_350, 6_700), "ex": (3_200, 6_400)},
    "MA": {"name": "Massachusetts", **_same([(0, 5), (1_083_150, 9)]), "ex": (4_400, 8_800)},
    "MI": {"name": "Michigan", **_same([(0, 4.25)]), "ex": (5_900, 11_800)},
    "MN": {"name": "Minnesota", "s": [(0, 5.35), (33_310, 6.8), (109_430, 7.85), (203_150, 9.85)],
           "j": [(0, 5.35), (48_700, 6.8), (193_480, 7.85), (337_930, 9.85)], "sd": (15_300, 30_600)},
    "MS": {"name": "Mississippi", **_same([(10_000, 4.0)]), "sd": (2_300, 4_600), "ex": (6_000, 12_000)},
    "MO": {"name": "Missouri", **_same([(1_348, 2), (2_696, 2.5), (4_044, 3), (5_392, 3.5), (6_740, 4),
                                        (8_088, 4.5), (9_436, 4.7)]),
           "sd": (16_100, 32_200)},
    "MT": {"name": "Montana", "s": [(0, 4.7), (47_500, 5.65)], "j": [(0, 4.7), (95_000, 5.65)],
           "sd": (16_100, 32_200)},
    "NE": {"name": "Nebraska", "s": [(0, 2.46), (4_130, 3.51), (24_760, 4.55)],
           "j": [(0, 2.46), (8_250, 3.51), (49_530, 4.55)], "sd": (8_850, 17_700), "credit": (176, 352)},
    "NJ": {"name": "New Jersey",
           "s": [(0, 1.4), (20_000, 1.75), (35_000, 3.5), (40_000, 5.53), (75_000, 6.37), (500_000, 8.97),
                 (1_000_000, 10.75)],
           "j": [(0, 1.4), (20_000, 1.75), (50_000, 2.45), (70_000, 3.5), (80_000, 5.53), (150_000, 6.37),
                 (500_000, 8.97), (1_000_000, 10.75)],
           "ex": (1_000, 2_000)},
    "NM": {"name": "New Mexico", "s": [(0, 1.5), (5_500, 3.2), (16_500, 4.3), (33_500, 4.7), (66_500, 4.9),
                                       (210_000, 5.9)],
           "j": [(0, 1.5), (8_000, 3.2), (25_000, 4.3), (50_000, 4.7), (100_000, 4.9), (315_000, 5.9)],
           "sd": (16_100, 32_200)},
    "NY": {"name": "New York",
           "s": [(0, 3.9), (8_500, 4.4), (11_700, 5.15), (13_900, 5.4), (80_650, 5.9), (215_400, 6.85),
                 (1_077_550, 9.65), (5_000_000, 10.3), (25_000_000, 10.9)],
           "j": [(0, 3.9), (17_150, 4.4), (23_600, 5.15), (27_900, 5.4), (161_550, 5.9), (323_200, 6.85),
                 (2_155_350, 9.65), (5_000_000, 10.3), (25_000_000, 10.9)],
           "sd": (8_000, 16_050)},
    "NC": {"name": "North Carolina", **_same([(0, 3.99)]), "sd": (12_750, 25_500)},
    "ND": {"name": "North Dakota", "s": [(48_475, 1.95), (244_825, 2.5)], "j": [(80_975, 1.95), (298_075, 2.5)],
           "sd": (16_100, 32_200)},
    "OH": {"name": "Ohio", **_same([(26_050, 2.75)]), "ex": (2_400, 4_800)},
    "OK": {"name": "Oklahoma", "s": [(3_750, 2.5), (4_900, 3.5), (7_200, 4.5)],
           "j": [(7_500, 2.5), (9_800, 3.5), (14_400, 4.5)], "sd": (6_350, 12_700), "ex": (1_000, 2_000)},
    "OR": {"name": "Oregon", "s": [(0, 4.75), (4_550, 6.75), (11_400, 8.75), (125_000, 9.9)],
           "j": [(0, 4.75), (9_100, 6.75), (22_800, 8.75), (250_000, 9.9)], "sd": (2_910, 5_820),
           "credit": (256, 512)},
    "PA": {"name": "Pennsylvania", **_same([(0, 3.07)])},
    "RI": {"name": "Rhode Island", **_same([(0, 3.75), (82_050, 4.75), (186_450, 5.99)]), "sd": (11_200, 22_400),
           "ex": (5_250, 10_500)},
    "SC": {"name": "South Carolina", **_same([(0, 1.99), (30_000, 5.21)]), "sd": (15_000, 30_000)},
    "UT": {"name": "Utah", **_same([(0, 4.45)])},
    "VT": {"name": "Vermont", "s": [(0, 3.35), (49_400, 6.6), (119_700, 7.6), (249_700, 8.75)],
           "j": [(0, 3.35), (82_500, 6.6), (199_450, 7.6), (304_000, 8.75)], "sd": (7_650, 15_300),
           "ex": (5_300, 10_600)},
    "VA": {"name": "Virginia", **_same([(0, 2), (3_000, 3), (5_000, 5), (17_000, 5.75)]), "sd": (8_750, 17_500),
           "ex": (930, 1_860)},
    "WV": {"name": "West Virginia", **_same([(0, 2.11), (10_000, 2.81), (25_000, 3.16), (40_000, 4.22),
                                             (60_000, 4.58)]),
           "ex": (2_000, 4_000)},
    "WI": {"name": "Wisconsin", "s": [(0, 3.5), (15_110, 4.4), (51_950, 5.3), (332_720, 7.65)],
           "j": [(0, 3.5), (20_150, 4.4), (69_260, 5.3), (443_630, 7.65)], "sd": (13_960, 25_840),
           "ex": (700, 1_400)},
    "DC": {"name": "District of Columbia", **_same([(0, 4), (10_000, 6), (40_000, 6.5), (60_000, 8.5),
                                                    (250_000, 9.25), (500_000, 9.75), (1_000_000, 10.75)]),
           "sd": (16_100, 32_200)},
}

# regole particolari (applicate in core/tax_us.py)
UT_CREDIT_RATE = 6.0                        # Utah: credito = 6% della deduzione standard federale…
UT_PHASEOUT = (18_213, 36_426)              # …ridotto dell'1,3% del reddito oltre queste soglie (valori 2025)
UT_PHASEOUT_RATE = 1.3
CT_EX_PHASEOUT = (30_000, 48_000)           # Connecticut: esenzione ridotta di 1.000 $ ogni 1.000 $ oltre la soglia
IL_EX_LIMIT = (250_000, 500_000)            # Illinois: niente esenzione oltre questo reddito
OR_CREDIT_LIMIT = (100_000, 200_000)        # Oregon: niente credito personale oltre questo reddito
OH_EX_TIERS = [(40_000, 2_400), (80_000, 2_150), (750_000, 1_900)]   # Ohio: esenzione per persona secondo il reddito
AL_SD_PHASE = ((23_000, 33_000), (2_500, 5_000))   # Alabama: deduzione standard ridotta fino al minimo
# Wisconsin: deduzione standard decrescente (12% single, 19,778% coppie) oltre una soglia (stima indicizzata dal 2017)
WI_SD_PHASE = ((20_120, 12.0), (29_040, 19.778))


def all_states() -> dict[str, str]:
    """Codice → nome di tutti gli stati (e Washington D.C.), in ordine alfabetico di nome."""
    names = {k: v["name"] for k, v in STATES.items()} | NO_TAX
    return dict(sorted(names.items(), key=lambda kv: kv[1]))

# ---------------------------------------------------------------- redditi da investimenti (IRS Rev. Proc. 2025-32)
# dividendi qualificati e plusvalenze a lungo termine: 0% fino alla prima soglia di reddito imponibile, 15% fino
# alla seconda, 20% oltre
LTCG = {"single": (49_450, 545_500), "mfj": (98_900, 613_700), "mfs": (49_450, 306_850), "hoh": (66_200, 579_600)}
# Net Investment Income Tax: 3,8% sul minore tra redditi da investimenti e reddito oltre la soglia (soglie fisse)
NIIT_RATE = 3.8
NIIT_THRESHOLD = {"single": 200_000, "mfj": 250_000, "mfs": 125_000, "hoh": 200_000}
# perdita netta di capitale deducibile dal reddito ordinario in un anno (il resto si riporta agli anni dopo)
CAPITAL_LOSS_LIMIT = {"single": 3_000, "mfj": 3_000, "mfs": 1_500, "hoh": 3_000}
