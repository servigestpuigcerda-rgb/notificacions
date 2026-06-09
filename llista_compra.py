#!/usr/bin/env python3
"""
Obre els productes de la llista de la compra directament al navegador.
Executa: python llista_compra.py
"""

import webbrowser

BASE = "https://www.compraonline.bonpreuesclat.cat"

PRODUCTES = [
    {
        "nom": "Paper higiènic — BONPREU 2 capes 12 rotlles",
        "url": f"{BASE}/products/bonpreu-paper-higi%C3%A8nic-2-capes-12-un/08673",
    },
    {
        "nom": "Paper de cuina — BONPREU",
        "url": f"{BASE}/products/bonpreu-paper-de-cuina/27101",
    },
    {
        "nom": "Coca-Cola — Refresc de cola en llauna",
        "url": f"{BASE}/products/coca-cola-refresc-de-cola-en-llauna/81602",
    },
    {
        "nom": "Font Vella — Aigua mineral 6x1,5 L",
        "url": f"{BASE}/products/font-vella-aigua-mineral-natural-6x1-5-l/45111",
    },
    {
        "nom": "Tomàquet — Frescos (categoria)",
        "url": f"{BASE}/categories/frescos/fruites-i-verdures/verdures-i-hortalisses/tom%C3%A0quets/9db034eb-1914-4b66-94a9-29160b0e651c",
    },
    {
        "nom": "Ous frescos — Classe L/XL",
        "url": f"{BASE}/products/bonpreu-ous-frescos-classe-l-xl/01861",
    },
]

def main():
    print("\n" + "="*58)
    print("  LLISTA DE LA COMPRA - BonpreuEsclat Online")
    print("="*58)
    print(f"\n  {len(PRODUCTES)} productes:\n")
    for i, p in enumerate(PRODUCTES, 1):
        print(f"  {i}. {p['nom']}")

    print("\n" + "-"*58)
    print("  S'obrirà cada producte al navegador.")
    print("  Afegeix-lo al carro i torna aquí per al següent.")
    print("-"*58)
    input("\n  Prem Enter per començar...\n")

    for i, producte in enumerate(PRODUCTES, 1):
        print(f"  [{i}/{len(PRODUCTES)}] {producte['nom']}")
        webbrowser.open(producte["url"])
        input("  → Afegit al carro? Prem Enter per al següent...\n")

    print("="*58)
    print("  Tots els productes processats!")
    print("  Obrint el carro per finalitzar la comanda...")
    print("="*58 + "\n")
    webbrowser.open(f"{BASE}/cart")

if __name__ == "__main__":
    main()
