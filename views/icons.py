"""Icone disegnate dentro le fette dei grafici a ciambella (categorie di spesa, valute, tipi di investimento).

Le icone sono di Lucide (https://lucide.dev), versione 0.460.0, copiate come elenco di elementi SVG (24×24, solo
contorno). Licenza ISC:

    Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other
    copyright (c) for Lucide are held by Lucide Contributors 2022.

    Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby
    granted, provided that the above copyright notice and this permission notice appear in all copies.

    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING
    ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL,
    DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
    WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE
    OR PERFORMANCE OF THIS SOFTWARE.

Le categorie le sceglie l'utente: l'icona si ricava dal nome (italiano o inglese) e, se il nome non dice nulla,
dall'emoji della categoria; altrimenti un'etichetta generica.
"""
from __future__ import annotations

import re
import unicodedata

# nome dell'icona -> elementi SVG [tag, attributi]
ICONS: dict[str, list] = {
    'shopping-cart': [["circle",{"cx":"8","cy":"21","r":"1"}],["circle",{"cx":"19","cy":"21","r":"1"}],["path",{"d":"M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"}]],
    'utensils-crossed': [["path",{"d":"m16 2-2.3 2.3a3 3 0 0 0 0 4.2l1.8 1.8a3 3 0 0 0 4.2 0L22 8"}],["path",{"d":"M15 15 3.3 3.3a4.2 4.2 0 0 0 0 6l7.3 7.3c.7.7 2 .7 2.8 0L15 15Zm0 0 7 7"}],["path",{"d":"m2.1 21.8 6.4-6.3"}],["path",{"d":"m19 5-7 7"}]],
    'coffee': [["path",{"d":"M10 2v2"}],["path",{"d":"M14 2v2"}],["path",{"d":"M16 8a1 1 0 0 1 1 1v8a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1h14a4 4 0 1 1 0 8h-1"}],["path",{"d":"M6 2v2"}]],
    'house': [["path",{"d":"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"}],["path",{"d":"M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"}]],
    'lightbulb': [["path",{"d":"M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"}],["path",{"d":"M9 18h6"}],["path",{"d":"M10 22h4"}]],
    'droplet': [["path",{"d":"M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"}]],
    'flame': [["path",{"d":"M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"}]],
    'smartphone': [["rect",{"width":"14","height":"20","x":"5","y":"2","rx":"2","ry":"2"}],["path",{"d":"M12 18h.01"}]],
    'train-front': [["path",{"d":"M8 3.1V7a4 4 0 0 0 8 0V3.1"}],["path",{"d":"m9 15-1-1"}],["path",{"d":"m15 15 1-1"}],["path",{"d":"M9 19c-2.8 0-5-2.2-5-5v-4a8 8 0 0 1 16 0v4c0 2.8-2.2 5-5 5Z"}],["path",{"d":"m8 19-2 3"}],["path",{"d":"m16 19 2 3"}]],
    'fuel': [["line",{"x1":"3","x2":"15","y1":"22","y2":"22"}],["line",{"x1":"4","x2":"14","y1":"9","y2":"9"}],["path",{"d":"M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18"}],["path",{"d":"M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 2 2a2 2 0 0 0 2-2V9.83a2 2 0 0 0-.59-1.42L18 5"}]],
    'car': [["path",{"d":"M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"}],["circle",{"cx":"7","cy":"17","r":"2"}],["path",{"d":"M9 17h6"}],["circle",{"cx":"17","cy":"17","r":"2"}]],
    'heart-pulse': [["path",{"d":"M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"}],["path",{"d":"M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"}]],
    'pill': [["path",{"d":"m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"}],["path",{"d":"m8.5 8.5 7 7"}]],
    'shirt': [["path",{"d":"M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"}]],
    'shopping-bag': [["path",{"d":"M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"}],["path",{"d":"M3 6h18"}],["path",{"d":"M16 10a4 4 0 0 1-8 0"}]],
    'tv': [["rect",{"width":"20","height":"15","x":"2","y":"7","rx":"2","ry":"2"}],["polyline",{"points":"17 2 12 7 7 2"}]],
    'ticket': [["path",{"d":"M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"}],["path",{"d":"M13 5v2"}],["path",{"d":"M13 17v2"}],["path",{"d":"M13 11v2"}]],
    'gamepad-2': [["line",{"x1":"6","x2":"10","y1":"11","y2":"11"}],["line",{"x1":"8","x2":"8","y1":"9","y2":"13"}],["line",{"x1":"15","x2":"15.01","y1":"12","y2":"12"}],["line",{"x1":"18","x2":"18.01","y1":"10","y2":"10"}],["path",{"d":"M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"}]],
    'film': [["rect",{"width":"18","height":"18","x":"3","y":"3","rx":"2"}],["path",{"d":"M7 3v18"}],["path",{"d":"M3 7.5h4"}],["path",{"d":"M3 12h18"}],["path",{"d":"M3 16.5h4"}],["path",{"d":"M17 3v18"}],["path",{"d":"M17 7.5h4"}],["path",{"d":"M17 16.5h4"}]],
    'music': [["path",{"d":"M9 18V5l12-2v13"}],["circle",{"cx":"6","cy":"18","r":"3"}],["circle",{"cx":"18","cy":"16","r":"3"}]],
    'plane': [["path",{"d":"M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"}]],
    'dumbbell': [["path",{"d":"M14.4 14.4 9.6 9.6"}],["path",{"d":"M18.657 21.485a2 2 0 1 1-2.829-2.828l-1.767 1.768a2 2 0 1 1-2.829-2.829l6.364-6.364a2 2 0 1 1 2.829 2.829l-1.768 1.767a2 2 0 1 1 2.828 2.829z"}],["path",{"d":"m21.5 21.5-1.4-1.4"}],["path",{"d":"M3.9 3.9 2.5 2.5"}],["path",{"d":"M6.404 12.768a2 2 0 1 1-2.829-2.829l1.768-1.767a2 2 0 1 1-2.828-2.829l2.828-2.828a2 2 0 1 1 2.829 2.828l1.767-1.768a2 2 0 1 1 2.829 2.829z"}]],
    'scissors': [["circle",{"cx":"6","cy":"6","r":"3"}],["path",{"d":"M8.12 8.12 12 12"}],["path",{"d":"M20 4 8.12 15.88"}],["circle",{"cx":"6","cy":"18","r":"3"}],["path",{"d":"M14.8 14.8 20 20"}]],
    'graduation-cap': [["path",{"d":"M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"}],["path",{"d":"M22 10v6"}],["path",{"d":"M6 12.5V16a6 3 0 0 0 12 0v-3.5"}]],
    'book-open': [["path",{"d":"M12 7v14"}],["path",{"d":"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"}]],
    'gift': [["rect",{"x":"3","y":"8","width":"18","height":"4","rx":"1"}],["path",{"d":"M12 8v13"}],["path",{"d":"M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"}],["path",{"d":"M7.5 8a2.5 2.5 0 0 1 0-5A4.8 8 0 0 1 12 8a4.8 8 0 0 1 4.5-5 2.5 2.5 0 0 1 0 5"}]],
    'paw-print': [["circle",{"cx":"11","cy":"4","r":"2"}],["circle",{"cx":"18","cy":"8","r":"2"}],["circle",{"cx":"20","cy":"16","r":"2"}],["path",{"d":"M9 10a5 5 0 0 1 5 5v3.5a3.5 3.5 0 0 1-6.84 1.045Q6.52 17.48 4.46 16.84A3.5 3.5 0 0 1 5.5 10Z"}]],
    'baby': [["path",{"d":"M9 12h.01"}],["path",{"d":"M15 12h.01"}],["path",{"d":"M10 16c.5.3 1.2.5 2 .5s1.5-.2 2-.5"}],["path",{"d":"M19 6.3a9 9 0 0 1 1.8 3.9 2 2 0 0 1 0 3.6 9 9 0 0 1-17.6 0 2 2 0 0 1 0-3.6A9 9 0 0 1 12 3c2 0 3.5 1.1 3.5 2.5s-.9 2.5-2 2.5c-.8 0-1.5-.4-1.5-1"}]],
    'hammer': [["path",{"d":"m15 12-8.373 8.373a1 1 0 1 1-3-3L12 9"}],["path",{"d":"m18 15 4-4"}],["path",{"d":"m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172V7l-2.26-2.26a6 6 0 0 0-4.202-1.756L9 2.96l.92.82A6.18 6.18 0 0 1 12 8.4V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5"}]],
    'shield-check': [["path",{"d":"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}],["path",{"d":"m9 12 2 2 4-4"}]],
    'landmark': [["line",{"x1":"3","x2":"21","y1":"22","y2":"22"}],["line",{"x1":"6","x2":"6","y1":"18","y2":"11"}],["line",{"x1":"10","x2":"10","y1":"18","y2":"11"}],["line",{"x1":"14","x2":"14","y1":"18","y2":"11"}],["line",{"x1":"18","x2":"18","y1":"18","y2":"11"}],["polygon",{"points":"12 2 20 7 4 7"}]],
    'receipt': [["path",{"d":"M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"}],["path",{"d":"M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"}],["path",{"d":"M12 17.5v-11"}]],
    'banknote': [["rect",{"width":"20","height":"12","x":"2","y":"6","rx":"2"}],["circle",{"cx":"12","cy":"12","r":"2"}],["path",{"d":"M6 12h.01M18 12h.01"}]],
    'piggy-bank': [["path",{"d":"M19 5c-1.5 0-2.8 1.4-3 2-3.5-1.5-11-.3-11 5 0 1.8 0 3 2 4.5V20h4v-2h3v2h4v-4c1-.5 1.7-1 2-2h2v-4h-2c0-1-.5-1.5-1-2V5z"}],["path",{"d":"M2 9v1c0 1.1.9 2 2 2h1"}],["path",{"d":"M16 11h.01"}]],
    'credit-card': [["rect",{"width":"20","height":"14","x":"2","y":"5","rx":"2"}],["line",{"x1":"2","x2":"22","y1":"10","y2":"10"}]],
    'shapes': [["path",{"d":"M8.3 10a.7.7 0 0 1-.626-1.079L11.4 3a.7.7 0 0 1 1.198-.043L16.3 8.9a.7.7 0 0 1-.572 1.1Z"}],["rect",{"x":"3","y":"14","width":"7","height":"7","rx":"1"}],["circle",{"cx":"17.5","cy":"17.5","r":"3.5"}]],
    'users': [["path",{"d":"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"}],["circle",{"cx":"9","cy":"7","r":"4"}],["path",{"d":"M22 21v-2a4 4 0 0 0-3-3.87"}],["path",{"d":"M16 3.13a4 4 0 0 1 0 7.75"}]],
    'briefcase': [["path",{"d":"M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"}],["rect",{"width":"20","height":"14","x":"2","y":"6","rx":"2"}]],
    'undo-2': [["path",{"d":"M9 14 4 9l5-5"}],["path",{"d":"M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"}]],
    'trending-up': [["polyline",{"points":"22 7 13.5 15.5 8.5 10.5 2 17"}],["polyline",{"points":"16 7 22 7 22 13"}]],
    'wallet': [["path",{"d":"M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"}],["path",{"d":"M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"}]],
    'arrow-left-right': [["path",{"d":"M8 3 4 7l4 4"}],["path",{"d":"M4 7h16"}],["path",{"d":"m16 21 4-4-4-4"}],["path",{"d":"M20 17H4"}]],
    'chart-line': [["path",{"d":"M3 3v16a2 2 0 0 0 2 2h16"}],["path",{"d":"m19 9-5 5-4-4-3 3"}]],
    'ellipsis': [["circle",{"cx":"12","cy":"12","r":"1"}],["circle",{"cx":"19","cy":"12","r":"1"}],["circle",{"cx":"5","cy":"12","r":"1"}]],
    'tag': [["path",{"d":"M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"}],["circle",{"cx":"7.5","cy":"7.5","r":".5","fill":"currentColor"}]],
    'euro': [["path",{"d":"M4 10h12"}],["path",{"d":"M4 14h9"}],["path",{"d":"M19 6a7.7 7.7 0 0 0-5.2-2A7.9 7.9 0 0 0 6 12c0 4.4 3.5 8 7.8 8 2 0 3.8-.8 5.2-2"}]],
    'dollar-sign': [["line",{"x1":"12","x2":"12","y1":"2","y2":"22"}],["path",{"d":"M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"}]],
    'pound-sterling': [["path",{"d":"M18 7c0-5.333-8-5.333-8 0"}],["path",{"d":"M10 7v14"}],["path",{"d":"M6 21h12"}],["path",{"d":"M6 13h10"}]],
    'japanese-yen': [["path",{"d":"M12 9.5V21m0-11.5L6 3m6 6.5L18 3"}],["path",{"d":"M6 15h12"}],["path",{"d":"M6 11h12"}]],
    'swiss-franc': [["path",{"d":"M10 21V3h8"}],["path",{"d":"M6 16h9"}],["path",{"d":"M10 9.5h7"}]],
    'bitcoin': [["path",{"d":"M11.767 19.089c4.924.868 6.14-6.025 1.216-6.894m-1.216 6.894L5.86 18.047m5.908 1.042-.347 1.97m1.563-8.864c4.924.869 6.14-6.025 1.215-6.893m-1.215 6.893-3.94-.694m5.155-6.2L8.29 4.26m5.908 1.042.348-1.97M7.48 20.364l3.126-17.727"}]],
    'indian-rupee': [["path",{"d":"M6 3h12"}],["path",{"d":"M6 8h12"}],["path",{"d":"m6 13 8.5 8"}],["path",{"d":"M6 13h3"}],["path",{"d":"M9 13c6.667 0 6.667-10 0-10"}]],
    'russian-ruble': [["path",{"d":"M6 11h8a4 4 0 0 0 0-8H9v18"}],["path",{"d":"M6 15h8"}]],
    'coins': [["circle",{"cx":"8","cy":"8","r":"6"}],["path",{"d":"M18.09 10.37A6 6 0 1 1 10.34 18"}],["path",{"d":"M7 6h1v4"}],["path",{"d":"m16.71 13.88.7.71-2.82 2.82"}]],
    'building-2': [["path",{"d":"M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"}],["path",{"d":"M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"}],["path",{"d":"M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"}],["path",{"d":"M10 6h4"}],["path",{"d":"M10 10h4"}],["path",{"d":"M10 14h4"}],["path",{"d":"M10 18h4"}]],
    'layers': [["path",{"d":"m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"}],["path",{"d":"m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"}],["path",{"d":"m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"}]],
    'scroll-text': [["path",{"d":"M15 12h-5"}],["path",{"d":"M15 8h-5"}],["path",{"d":"M19 17V5a2 2 0 0 0-2-2H4"}],["path",{"d":"M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"}]],
    'chart-pie': [["path",{"d":"M21 12c.552 0 1.005-.449.95-.998a10 10 0 0 0-8.953-8.951c-.55-.055-.998.398-.998.95v8a1 1 0 0 0 1 1z"}],["path",{"d":"M21.21 15.89A10 10 0 1 1 8 2.83"}]],
    'gem': [["path",{"d":"M6 3h12l4 6-10 13L2 9Z"}],["path",{"d":"M11 3 8 9l4 13 4-13-3-6"}],["path",{"d":"M2 9h20"}]],
    'beer': [["path",{"d":"M17 11h1a3 3 0 0 1 0 6h-1"}],["path",{"d":"M9 12v6"}],["path",{"d":"M13 12v6"}],["path",{"d":"M14 7.5c-1 0-1.44.5-3 .5s-2-.5-3-.5-1.72.5-2.5.5a2.5 2.5 0 0 1 0-5c.78 0 1.57.5 2.5.5S9.44 2 11 2s2 1.5 3 1.5 1.72-.5 2.5-.5a2.5 2.5 0 0 1 0 5c-.78 0-1.5-.5-2.5-.5Z"}],["path",{"d":"M5 8v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V8"}]],
    'wine': [["path",{"d":"M8 22h8"}],["path",{"d":"M7 10h10"}],["path",{"d":"M12 15v7"}],["path",{"d":"M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z"}]],
}

# (espressione sul nome normalizzato, icona): la prima che corrisponde vince, quindi le più specifiche prima
_NAME_RULES = [
    (r"condivis|shared|split", "users"),
    (r"trasferiment|giroconto|transfer", "arrow-left-right"),
    (r"investiment|invest|broker|\bazion|\bstocks?\b|\betf\b", "chart-line"),
    (r"stipend|salar|\bpaga\b|payroll|\bwage", "briefcase"),
    (r"rimbors|refund|reimburs|cashback", "undo-2"),
    (r"interess|dividend|cedol|interest", "trending-up"),
    (r"risparm|saving|salvadanaio", "piggy-bank"),
    (r"entrat|income|ricav|earning|bonus", "wallet"),
    (r"alimentar|supermerc|grocer|\bspesa\b|market|\bfood shop", "shopping-cart"),
    (r"caffe|coffee|colazion|breakfast", "coffee"),
    (r"birr|\bbeer|\bpub\b", "beer"),
    (r"\bvin[oi]\b|wine|enotec", "wine"),
    (r"ristorant|\bbar\b|\bbars\b|restaurant|pizz|trattori|osteri|pranz|\bcena\b|dining|takeaway|"
     r"delivery|\bcibo\b|\bfood\b|\beat", "utensils-crossed"),
    (r"arredament|manutenzion|furniture|maintenance|fai da te|\bdiy\b|ferrament|repair|riparazion", "hammer"),
    (r"affitt|mutuo|\brent\b|mortgage|housing|\bcasa\b|\bhome\b|\bhouse\b|condominio", "house"),
    (r"\bacqua\b|\bwater\b", "droplet"),
    (r"\bgas\b|riscaldament|heating", "flame"),
    (r"bollett|utenz|utilit|\bbills?\b|\bluce\b|elettric|electric|energi|energy", "lightbulb"),
    (r"telefon|internet|\bphone|mobile|cellular|\bsim\b|fibra|wifi", "smartphone"),
    (r"carburant|benzin|\bfuel|diesel|gasolio|rifornim", "fuel"),
    (r"trasport|transport|transit|\btren|\btrain|\bbus\b|metro|\btaxi|\btram\b|commut", "train-front"),
    (r"\bauto\b|\bmoto\b|\bcars?\b|motorbike|veicol|vehicle|parchegg|parking|pedagg|\btoll", "car"),
    (r"farmac|pharmac|medicin|\bdrug", "pill"),
    (r"salut|health|medic|dottor|doctor|dentist|ospedal|hospital|visite", "heart-pulse"),
    (r"abbigliament|vestit|scarp|cloth|shoe|fashion|apparel", "shirt"),
    (r"shopping|acquist|\bonline\b|amazon|purchase|negoz|\bstore", "shopping-bag"),
    (r"\bsport|palestr|\bgym|fitness|benesser|wellness|piscin", "dumbbell"),
    (r"abbonament|subscription|digital|streaming|netflix|spotify|software|\bapp\b|\bapps\b", "tv"),
    (r"videogioc|gaming|\bgames?\b|console", "gamepad-2"),
    (r"cinema|\bfilm|movie", "film"),
    (r"music|concert", "music"),
    (r"svago|tempo libero|divertiment|leisure|entertain|hobby|spettacol|teatr|theat|event", "ticket"),
    (r"viagg|vacanz|travel|holiday|vacation|\bvol[oi]\b|flight|hotel|alberg", "plane"),
    (r"cura personal|personal care|parrucch|barbier|\bhair|beauty|estetic|cosmetic", "scissors"),
    (r"istruzion|scuol|universit|educat|school|\bcors[oi]\b|course|tuition", "graduation-cap"),
    (r"\blibr[oi]\b|\bbooks?\b|lettur|reading", "book-open"),
    (r"regal|donazion|\bgift|donation|charit|beneficen", "gift"),
    (r"animal|\bpets?\b|\bcane\b|\bgatt|veterinar|\bdogs?\b|\bcats?\b", "paw-print"),
    (r"figli|famigl|bambin|\bchild|\bkids?\b|family|\bbab", "baby"),
    (r"assicuraz|insurance|polizz", "shield-check"),
    (r"\btass|impost|\btax|\bf24\b|tribut", "landmark"),
    (r"commission|\bfees?\b|bancari|\bbank", "receipt"),
    (r"contant|preliev|\bcash\b|\batm\b|withdraw|bancomat", "banknote"),
    (r"carta di credito|credit card|prestit|\bloan|finanziam|\brat[ae]\b|debit", "credit-card"),
    (r"\baltr[eio]\b|\bother|\bvari[eo]?\b|\bmisc", "shapes"),
]
_NAME_RULES = [(re.compile(p), icon) for p, icon in _NAME_RULES]

# emoji della categoria -> icona (per le categorie che hanno un nome che non dice nulla)
_EMOJI = {
    "🛒": "shopping-cart", "🍽": "utensils-crossed", "🍕": "utensils-crossed", "🍔": "utensils-crossed",
    "🍝": "utensils-crossed", "🍣": "utensils-crossed", "☕": "coffee", "🍺": "beer", "🍻": "beer", "🍷": "wine",
    "🏠": "house", "🏡": "house", "💡": "lightbulb", "⚡": "lightbulb", "💧": "droplet", "🔥": "flame",
    "📱": "smartphone", "☎": "smartphone", "🌐": "smartphone", "🚆": "train-front", "🚇": "train-front",
    "🚌": "train-front", "🚋": "train-front", "⛽": "fuel", "🚗": "car", "🚙": "car", "🏍": "car", "💊": "pill",
    "🏥": "heart-pulse", "🩺": "heart-pulse", "👕": "shirt", "👗": "shirt", "👟": "shirt", "🛍": "shopping-bag",
    "📦": "shopping-bag", "📺": "tv", "💻": "tv", "🎭": "ticket", "🎟": "ticket", "🎮": "gamepad-2", "🎬": "film",
    "🎵": "music", "🎧": "music", "✈": "plane", "🏖": "plane", "🧳": "plane", "🏋": "dumbbell", "⚽": "dumbbell",
    "🏃": "dumbbell", "💇": "scissors", "💅": "scissors", "📚": "book-open", "📖": "book-open",
    "🎓": "graduation-cap", "🎁": "gift", "🐾": "paw-print", "🐶": "paw-print", "🐱": "paw-print", "👶": "baby",
    "🧸": "baby", "🔧": "hammer", "🔨": "hammer", "🛋": "hammer", "🛡": "shield-check", "🏛": "landmark",
    "🏦": "receipt", "💵": "banknote", "💶": "banknote", "💳": "credit-card", "💼": "briefcase", "🔁": "undo-2",
    "📈": "trending-up", "💰": "wallet", "🐷": "piggy-bank", "↔": "arrow-left-right", "📊": "chart-line",
    "🤝": "users", "❓": "shapes",
}

_CURRENCY = {"EUR": "euro", "USD": "dollar-sign", "CAD": "dollar-sign", "AUD": "dollar-sign", "NZD": "dollar-sign",
             "HKD": "dollar-sign", "SGD": "dollar-sign", "MXN": "dollar-sign", "GBP": "pound-sterling",
             "JPY": "japanese-yen", "CNY": "japanese-yen", "CHF": "swiss-franc", "INR": "indian-rupee",
             "RUB": "russian-ruble", "BTC": "bitcoin"}

_ASSET = {"ETF": "layers", "Azione": "building-2", "Obbligazione": "scroll-text", "Fondo": "chart-pie",
          "ETC/ETN": "gem", "Crypto": "bitcoin", "Altro": "shapes"}

GROUP = "ellipsis"      # la fetta che raggruppa le voci più piccole («Altre 4 categorie»)
FALLBACK = "tag"


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def category_icon(name: str, emoji: str | None = None) -> str:
    """Icona di una categoria di spesa o entrata, dal nome (italiano o inglese) o dall'emoji."""
    n = _norm(name)
    for rx, icon in _NAME_RULES:
        if icon != "shapes" and rx.search(n):
            return icon
    for ch in str(emoji or ""):
        if ch in _EMOJI:
            return _EMOJI[ch]
    if _NAME_RULES[-1][0].search(n):
        return "shapes"
    return FALLBACK


def currency_icon(code: str) -> str:
    return _CURRENCY.get(str(code or "").upper(), "coins")


def asset_icon(kind: str) -> str:
    return _ASSET.get(str(kind or ""), "shapes")
