#!/usr/bin/env python3
"""Genera index.html (pàgina completa, per a GitHub Pages) a partir d'app.html.

app.html és la font de veritat: és un fragment sense <html>/<head>/<body>
perquè és el format que espera el publicador d'Artifacts de Claude. Aquest
script l'embolcalla en un document HTML complet per poder servir-lo com a
web estàtica normal.

    python3 fitxatge/build.py
"""
from pathlib import Path

AQUI = Path(__file__).parent
FRAGMENT = AQUI / "app.html"
SORTIDA = AQUI / "index.html"

EMBOLCALL = """<!doctype html>
<html lang="ca">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="Registre horari: fitxatge d'entrada, pausa i sortida des del mòbil o des de qualsevol ordinador.">
<meta name="theme-color" content="#F1F4F0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0E1412" media="(prefers-color-scheme: dark)">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Fitxatge">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%231C6A55'/%3E%3Cpath d='M16 8v8.4l5.2 3' fill='none' stroke='white' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
  :root{color-scheme:light dark}
  html,body{margin:0}
  img{max-width:100%}
  [hidden]{display:none!important}
</style>
</head>
<body>
{FRAGMENT}
</body>
</html>
"""


def main() -> None:
    fragment = FRAGMENT.read_text(encoding="utf-8").rstrip()
    # El fragment comença amb <title>/<link>/<style> i segueix amb el cos;
    # l'HTML permet aquests elements dins de <body> i el navegador els aplica
    # igualment, així que el fragment s'insereix sencer tal com està.
    SORTIDA.write_text(EMBOLCALL.replace("{FRAGMENT}", fragment), encoding="utf-8")
    print(f"escrit {SORTIDA} ({SORTIDA.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
