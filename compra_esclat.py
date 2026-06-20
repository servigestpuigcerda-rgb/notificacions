#!/usr/bin/env python3
"""
Cercador de productes i assistència de compra per BonpreuEsclat Online.
Obre el navegador, cerca cada producte i mostra els resultats per confirmar.
"""

import os
import sys
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from planner import crear_tasca_planner

load_dotenv()

BASE_URL = "https://www.compraonline.bonpreuesclat.cat"
SEARCH_URL = f"{BASE_URL}/search?q="

def llegir_productes():
    """Llegeix la llista de productes de l'usuari interactivament."""
    print("\n" + "="*55)
    print("  LLISTA DE LA COMPRA - BonpreuEsclat Online")
    print("="*55)
    print("Escriu els productes que vols comprar.")
    print("Quan hagis acabat, escriu 'fi' o prem Enter en línia buida.\n")

    productes = []
    while True:
        entrada = input(f"  Producte {len(productes)+1}: ").strip()
        if not entrada or entrada.lower() == "fi":
            break
        productes.append(entrada)

    return productes


def login(page, email, password):
    """Intenta fer login a la plataforma."""
    print("\n  Iniciant sessió...")
    try:
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=15000)
        page.fill('input[type="email"], input[name="email"]', email)
        page.fill('input[type="password"], input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=10000)
        print("  Sessió iniciada correctament.")
        return True
    except Exception as e:
        print(f"  No s'ha pogut fer login automàtic: {e}")
        print("  Pots iniciar sessió manualment al navegador.")
        return False


def cercar_producte(page, producte):
    """Cerca un producte i retorna els resultats."""
    url = SEARCH_URL + producte.replace(" ", "+")
    print(f"\n  Cercant: '{producte}'...")
    try:
        page.goto(url, wait_until="networkidle", timeout=20000)
        time.sleep(1)

        resultats = []
        # Intenta trobar targetes de producte amb patrons comuns
        selectors = [
            "[data-testid='product-card']",
            ".product-card",
            "[class*='ProductCard']",
            "[class*='product-item']",
            "article[class*='product']",
        ]

        items = []
        for sel in selectors:
            items = page.query_selector_all(sel)
            if items:
                break

        for i, item in enumerate(items[:5]):
            try:
                nom_el = item.query_selector(
                    "[class*='name'], [class*='title'], [class*='Name'], h3, h2, p"
                )
                preu_el = item.query_selector(
                    "[class*='price'], [class*='Price'], [class*='preu']"
                )
                nom = nom_el.inner_text().strip() if nom_el else "Sense nom"
                preu = preu_el.inner_text().strip() if preu_el else "Preu no disponible"
                resultats.append({"index": i + 1, "nom": nom, "preu": preu, "element": item})
            except Exception:
                continue

        return resultats

    except PlaywrightTimeout:
        print(f"  Temps d'espera superat per '{producte}'.")
        return []
    except Exception as e:
        print(f"  Error cercant '{producte}': {e}")
        return []


def mostrar_resultats(producte, resultats):
    """Mostra els resultats i demana confirmació."""
    if not resultats:
        print(f"  No s'han trobat resultats per '{producte}'.")
        print(f"  Pots cercar-lo manualment al navegador.")
        return None

    print(f"\n  Resultats per '{producte}':")
    print("  " + "-"*40)
    for r in resultats:
        print(f"  [{r['index']}] {r['nom'][:50]:<50} {r['preu']}")
    print("  [0] Saltar aquest producte")
    print("  " + "-"*40)

    while True:
        try:
            opcio = input(f"  Quin vols afegir al carro? (1-{len(resultats)}, 0=saltar): ").strip()
            opcio = int(opcio)
            if 0 <= opcio <= len(resultats):
                return opcio
        except ValueError:
            pass
        print(f"  Opció no vàlida. Escriu un número entre 0 i {len(resultats)}.")


def afegir_al_carro(page, item):
    """Intenta afegir un producte al carro."""
    try:
        boto_selectors = [
            "button[aria-label*='Afegir']",
            "button[aria-label*='afegir']",
            "button[aria-label*='Add']",
            "[class*='add-to-cart']",
            "[class*='AddToCart']",
            "[data-testid*='add']",
            "button[class*='add']",
        ]
        for sel in boto_selectors:
            boto = item.query_selector(sel)
            if boto:
                boto.click()
                time.sleep(0.8)
                return True

        # Si no trobem el botó dins la targeta, fem clic a la targeta per anar al detall
        item.click()
        page.wait_for_load_state("networkidle", timeout=8000)
        for sel in boto_selectors:
            boto = page.query_selector(sel)
            if boto:
                boto.click()
                time.sleep(0.8)
                print("  Afegit al carro des de la pàgina de detall.")
                page.go_back()
                return True

        print("  No s'ha trobat el botó 'Afegir al carro'. Afegeix-lo manualment.")
        page.go_back()
        return False
    except Exception as e:
        print(f"  Error afegint al carro: {e}")
        return False


def resum_final(carro):
    """Mostra el resum dels productes afegits."""
    print("\n" + "="*55)
    print("  RESUM DE LA COMANDA")
    print("="*55)
    if not carro:
        print("  No s'ha afegit cap producte al carro.")
    else:
        for i, p in enumerate(carro, 1):
            print(f"  {i}. {p}")
        print(f"\n  Total: {len(carro)} producte(s) afegit(s) al carro.")
    print("\n  Revisa el carro al navegador per confirmar i finalitzar la comanda.")
    print("="*55 + "\n")


def main():
    # Llegir productes
    if len(sys.argv) > 1:
        productes = sys.argv[1:]
    else:
        productes = llegir_productes()

    if not productes:
        print("No has introduït cap producte. Fins aviat!")
        return

    print(f"\n  {len(productes)} producte(s) a cercar: {', '.join(productes)}")

    # Credencials (opcionals)
    email = os.getenv("ESCLAT_EMAIL", "")
    password = os.getenv("ESCLAT_PASSWORD", "")

    carro = []
    saltats = []

    with sync_playwright() as p:
        print("\n  Obrint el navegador...")
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ca-ES",
        )
        page = context.new_page()

        # Anar a la pàgina principal
        print("  Navegant a BonpreuEsclat Online...")
        try:
            page.goto(BASE_URL, wait_until="networkidle", timeout=20000)
        except Exception:
            page.goto(BASE_URL, timeout=20000)

        # Login si hi ha credencials
        if email and password:
            login(page, email, password)
        else:
            print("\n  No s'han trobat credencials al fitxer .env")
            print("  Pots iniciar sessió manualment al navegador si ho necessites.")
            print("  (Tens 20 segons per fer-ho ara si vols)")
            time.sleep(20)

        # Cercar cada producte
        for producte in productes:
            resultats = cercar_producte(page, producte)
            opcio = mostrar_resultats(producte, resultats)

            if opcio and opcio > 0:
                item_seleccionat = resultats[opcio - 1]
                print(f"  Afegint '{item_seleccionat['nom'][:40]}' al carro...")
                ok = afegir_al_carro(page, item_seleccionat["element"])
                if ok:
                    carro.append(item_seleccionat["nom"])
                    print("  Afegit correctament!")
                else:
                    print("  No s'ha pogut afegir automàticament.")
            elif opcio == 0:
                saltats.append(producte)
                print(f"  '{producte}' saltat.")

        # Obrir el carro al final
        print("\n  Obrint el carro de la compra...")
        try:
            page.goto(f"{BASE_URL}/cart", wait_until="networkidle", timeout=10000)
        except Exception:
            pass

        resum_final(carro)

        # Crear tasca a Microsoft Planner (si està configurat)
        crear_tasca_planner(carro, saltats if saltats else None)

        input("  Prem Enter per tancar el navegador quan hagis acabat...")
        browser.close()


if __name__ == "__main__":
    main()
