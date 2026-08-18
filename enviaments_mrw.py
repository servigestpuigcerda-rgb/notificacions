#!/usr/bin/env python3
"""
Accés a l'àrea de clients de MRW per consultar els enviaments.

Obre el navegador, inicia sessió (automàticament amb .env o manualment),
guarda la sessió per no haver de tornar a entrar cada vegada, i llista
els enviaments. També permet consultar el seguiment d'un enviament concret.

Ús:
    python enviaments_mrw.py                      # llista els enviaments
    python enviaments_mrw.py 12345678             # seguiment d'un enviament
    python enviaments_mrw.py --csv enviaments.csv # exporta el llistat a CSV
    python enviaments_mrw.py --login              # força tornar a iniciar sessió
"""

import csv
import os
import sys
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

# L'adreça de l'àrea de clients es pot canviar des del .env si MRW la mou.
BASE_URL = os.getenv("MRW_URL", "https://www.mrw.es/acceso-clientes/")
SEGUIMENT_URL = os.getenv("MRW_SEGUIMENT_URL", "https://www.mrw.es/seguimiento-envios/")
FITXER_SESSIO = ".mrw_sessio.json"


def iniciar_navegador(p, headless):
    """Obre el navegador reaprofitant la sessió guardada si existeix."""
    browser = p.chromium.launch(headless=headless, slow_mo=200)
    opcions = {
        "viewport": {"width": 1400, "height": 950},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "locale": "es-ES",
    }
    if os.path.exists(FITXER_SESSIO):
        opcions["storage_state"] = FITXER_SESSIO
        print("  Reaprofitant la sessió guardada.")
    context = browser.new_context(**opcions)
    return browser, context


def login(page, usuari, clau):
    """Intenta iniciar sessió a l'àrea de clients de MRW."""
    print("\n  Iniciant sessió a MRW...")
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)
        acceptar_cookies(page)
    except Exception as e:
        print(f"  No s'ha pogut obrir {BASE_URL}: {e}")
        return False

    if not (usuari and clau):
        print("  No hi ha credencials al .env (MRW_USUARI / MRW_CONTRASENYA).")
        return False

    selectors_usuari = [
        "input[name*='user' i]",
        "input[name*='usuario' i]",
        "input[name*='email' i]",
        "input[type='email']",
        "input[id*='user' i]",
        "input[id*='login' i]",
    ]
    selectors_clau = [
        "input[type='password']",
        "input[name*='pass' i]",
        "input[id*='pass' i]",
    ]
    selectors_boto = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Acceder')",
        "button:has-text('Entrar')",
        "button:has-text('Iniciar')",
        "a:has-text('Acceder')",
    ]

    try:
        if not omplir(page, selectors_usuari, usuari):
            print("  No s'ha trobat el camp d'usuari.")
            return False
        if not omplir(page, selectors_clau, clau):
            print("  No s'ha trobat el camp de contrasenya.")
            return False

        for sel in selectors_boto:
            boto = page.query_selector(sel)
            if boto:
                boto.click()
                break
        else:
            page.keyboard.press("Enter")

        page.wait_for_load_state("networkidle", timeout=20000)
        time.sleep(2)

        if page.query_selector("input[type='password']"):
            print("  Sembla que la sessió no s'ha iniciat (potser hi ha un captcha).")
            return False

        print("  Sessió iniciada correctament.")
        return True

    except PlaywrightTimeout:
        print("  Temps d'espera superat en iniciar sessió.")
        return False
    except Exception as e:
        print(f"  No s'ha pogut iniciar sessió automàticament: {e}")
        return False


def omplir(page, selectors, valor):
    """Omple el primer camp visible que coincideixi amb algun selector."""
    for sel in selectors:
        camp = page.query_selector(sel)
        if camp and camp.is_visible():
            camp.fill(valor)
            return True
    return False


def acceptar_cookies(page):
    """Tanca el bàner de cookies si apareix."""
    textos = ["Aceptar", "Aceptar todas", "Acepto", "Entendido", "De acuerdo", "Accept"]
    for text in textos:
        try:
            boto = page.query_selector(f"button:has-text('{text}')")
            if boto and boto.is_visible():
                boto.click()
                time.sleep(0.5)
                return
        except Exception:
            continue


def login_manual(page):
    """Espera que l'usuari iniciï sessió ell mateix al navegador."""
    print("\n  " + "-" * 50)
    print("  Inicia sessió tu mateix a la finestra del navegador.")
    print("  Quan ja siguis a dins, torna aquí i prem Enter.")
    print("  " + "-" * 50)
    input("  Prem Enter quan hagis iniciat sessió: ")
    return True


def extreure_taula(page):
    """Busca la taula amb més files de la pàgina i n'extreu el contingut."""
    taules = page.query_selector_all("table")
    millor, max_files = None, 0
    for taula in taules:
        files = taula.query_selector_all("tr")
        if len(files) > max_files:
            millor, max_files = taula, len(files)

    if not millor or max_files < 2:
        return [], []

    capcalera = []
    cel_les_cap = millor.query_selector_all("thead th, thead td, tr:first-child th")
    for c in cel_les_cap:
        capcalera.append(c.inner_text().strip())

    files = []
    for fila in millor.query_selector_all("tbody tr") or millor.query_selector_all("tr"):
        cel_les = fila.query_selector_all("td")
        if not cel_les:
            continue
        files.append([c.inner_text().strip().replace("\n", " ") for c in cel_les])

    return capcalera, files


def llistar_enviaments(page):
    """Navega a l'apartat d'enviaments i n'extreu el llistat."""
    print("\n  Buscant el llistat d'enviaments...")

    enllacos = ["Envíos", "Mis envíos", "Expediciones", "Listado de envíos", "Seguimiento"]
    for text in enllacos:
        try:
            enllac = page.query_selector(f"a:has-text('{text}')")
            if enllac and enllac.is_visible():
                enllac.click()
                page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(2)
                print(f"  Obert l'apartat '{text}'.")
                break
        except Exception:
            continue

    capcalera, files = extreure_taula(page)

    if not files:
        print("  No s'ha trobat cap taula d'enviaments automàticament.")
        print("  Navega tu fins al llistat al navegador i torna a provar.")
        resposta = input("  Ja hi ets? Prem Enter per tornar a llegir la pàgina (o 'n' per sortir): ")
        if resposta.strip().lower() != "n":
            capcalera, files = extreure_taula(page)

    return capcalera, files


def seguiment(page, numero):
    """Consulta el seguiment d'un número d'enviament concret."""
    print(f"\n  Consultant el seguiment de l'enviament {numero}...")
    try:
        page.goto(SEGUIMENT_URL, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)
        acceptar_cookies(page)

        selectors = [
            "input[name*='envio' i]",
            "input[name*='numero' i]",
            "input[name*='shipment' i]",
            "input[type='text']",
            "input[type='search']",
        ]
        if not omplir(page, selectors, str(numero)):
            print("  No s'ha trobat el camp del número d'enviament.")
            return [], []

        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=20000)
        time.sleep(2)

        return extreure_taula(page)

    except Exception as e:
        print(f"  Error consultant el seguiment: {e}")
        return [], []


def mostrar(capcalera, files, titol):
    """Mostra el resultat per pantalla."""
    print("\n" + "=" * 70)
    print(f"  {titol}")
    print("=" * 70)

    if not files:
        print("  No hi ha dades per mostrar.")
        print("=" * 70 + "\n")
        return

    if capcalera:
        print("  " + " | ".join(capcalera))
        print("  " + "-" * 66)

    for fila in files:
        print("  " + " | ".join(c[:28] for c in fila))

    print(f"\n  Total: {len(files)} registre(s).")
    print("=" * 70 + "\n")


def exportar_csv(capcalera, files, fitxer):
    """Desa el resultat en un fitxer CSV."""
    if not files:
        print("  No hi ha dades per exportar.")
        return
    with open(fitxer, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        if capcalera:
            writer.writerow(capcalera)
        writer.writerows(files)
    print(f"  Dades desades a '{fitxer}'.")


def main():
    args = sys.argv[1:]
    headless = "--headless" in args
    forcar_login = "--login" in args
    fitxer_csv = None

    if "--csv" in args:
        i = args.index("--csv")
        if i + 1 < len(args):
            fitxer_csv = args[i + 1]
            args.pop(i + 1)
        else:
            fitxer_csv = "enviaments_mrw.csv"
        args.pop(i)

    numeros = [a for a in args if not a.startswith("--")]

    if forcar_login and os.path.exists(FITXER_SESSIO):
        os.remove(FITXER_SESSIO)
        print("  Sessió guardada esborrada.")

    usuari = os.getenv("MRW_USUARI", "")
    clau = os.getenv("MRW_CONTRASENYA", "")

    with sync_playwright() as p:
        print("\n  Obrint el navegador...")
        browser, context = iniciar_navegador(p, headless)
        page = context.new_page()

        te_sessio = os.path.exists(FITXER_SESSIO)
        if not te_sessio:
            if not login(page, usuari, clau):
                if headless:
                    print("  Sense sessió i en mode headless: no es pot continuar.")
                    browser.close()
                    return
                login_manual(page)
            context.storage_state(path=FITXER_SESSIO)
            print(f"  Sessió guardada a '{FITXER_SESSIO}'.")
        else:
            try:
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
                time.sleep(2)
                acceptar_cookies(page)
            except Exception:
                pass

        if numeros:
            for numero in numeros:
                capcalera, files = seguiment(page, numero)
                mostrar(capcalera, files, f"SEGUIMENT DE L'ENVIAMENT {numero}")
                if fitxer_csv:
                    exportar_csv(capcalera, files, fitxer_csv)
        else:
            capcalera, files = llistar_enviaments(page)
            mostrar(capcalera, files, "ENVIAMENTS MRW")
            if fitxer_csv:
                exportar_csv(capcalera, files, fitxer_csv)

        if not headless:
            input("  Prem Enter per tancar el navegador quan hagis acabat...")
        browser.close()


if __name__ == "__main__":
    main()
