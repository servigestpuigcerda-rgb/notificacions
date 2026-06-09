#!/usr/bin/env python3
"""
Obre les cerques de la llista de la compra directament al navegador.
Executa: python llista_compra.py
"""

import webbrowser
import urllib.parse
import time

PRODUCTES = [
    "paper higiènic",
    "paper de cuina",
    "coca-cola",
    "font vella aigua",
    "tomàquet",
    "ous",
]

BASE_CERCA = "https://www.compraonline.bonpreuesclat.cat/search?q="

def main():
    print("\n" + "="*55)
    print("  LLISTA DE LA COMPRA - BonpreuEsclat Online")
    print("="*55)
    print(f"\n  {len(PRODUCTES)} productes a cercar:\n")
    for i, p in enumerate(PRODUCTES, 1):
        print(f"  {i}. {p.capitalize()}")

    print("\n" + "-"*55)
    print("  S'obrirà el navegador amb cada cerca.")
    print("  Afegeix el producte al carro i torna aquí.")
    print("-"*55)
    input("\n  Prem Enter per començar...\n")

    for i, producte in enumerate(PRODUCTES, 1):
        url = BASE_CERCA + urllib.parse.quote(producte)
        print(f"  [{i}/{len(PRODUCTES)}] Cercant: {producte.capitalize()}")
        print(f"         URL: {url}")
        webbrowser.open(url)
        input("  → Afegeix al carro i prem Enter per al següent...\n")

    print("="*55)
    print("  Tots els productes processats!")
    print("  Ves al carro per confirmar i finalitzar la comanda:")
    print("  https://www.compraonline.bonpreuesclat.cat/cart")
    print("="*55 + "\n")
    webbrowser.open("https://www.compraonline.bonpreuesclat.cat/cart")

if __name__ == "__main__":
    main()
