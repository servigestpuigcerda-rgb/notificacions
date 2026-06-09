#!/usr/bin/env python3
"""
Resposta automàtica de WhatsApp Web.
Monitoritza els missatges entrants i respon automàticament.
"""

import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

SESSION_DIR = Path(__file__).parent / ".whatsapp_session"
WHATSAPP_URL = "https://web.whatsapp.com"

MISSATGE_RESPOSTA = os.getenv(
    "WHATSAPP_AUTO_RESPOSTA",
    "Gràcies pel teu missatge! T'atendré en breu."
)
INTERVAL_COMPROVACIO = int(os.getenv("WHATSAPP_INTERVAL", "10"))
# Temps mínim (segons) entre dues respostes al mateix xat
TEMPS_REFREDAMENT = int(os.getenv("WHATSAPP_REFREDAMENT", "300"))


def guardar_sessio(context):
    SESSION_DIR.mkdir(exist_ok=True)
    with open(SESSION_DIR / "state.json", "w") as f:
        json.dump(context.storage_state(), f)


def carregar_sessio():
    state_file = SESSION_DIR / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return None


def esperar_carregat(page):
    """Espera que WhatsApp Web estigui llest, gestionant el codi QR si cal."""
    print("  Carregant WhatsApp Web...")
    try:
        qr = page.wait_for_selector(
            '[data-testid="qrcode"], canvas[aria-label*="QR"], [data-ref]',
            timeout=5000
        )
        if qr:
            print("\n" + "="*55)
            print("  ESCANEJA EL CODI QR AMB EL MÒBIL")
            print("="*55)
            print("  WhatsApp > Dispositius vinculats > Vincula un dispositiu")
            print("  Esperant l'escaneig... (màxim 2 minuts)")
    except PlaywrightTimeout:
        pass

    try:
        page.wait_for_selector(
            '[data-testid="chat-list"], [aria-label="Chat list"], [aria-label="Llista de xats"]',
            timeout=120000
        )
        print("  WhatsApp Web llest.")
        return True
    except PlaywrightTimeout:
        print("  Error: No s'ha pogut carregar WhatsApp Web.")
        return False


def obtenir_xats_no_llegits(page):
    """Retorna elements de xat amb missatges no llegits."""
    # Primer intenta amb :has() (Chrome modern)
    xats = page.query_selector_all(
        'div[data-testid="cell-frame-container"]:has([data-testid="icon-unread-count"])'
    )
    if xats:
        return xats

    # Fallback: cerca badges i puja fins al contenidor del xat
    xats_trobats = []
    badges = page.query_selector_all('[data-testid="icon-unread-count"]')
    for badge in badges:
        try:
            contenidor = page.evaluate("""
                (el) => {
                    let node = el;
                    for (let i = 0; i < 12; i++) {
                        node = node.parentElement;
                        if (!node) return null;
                        if (node.getAttribute('data-testid') === 'cell-frame-container')
                            return node;
                    }
                    return null;
                }
            """, badge)
            if contenidor:
                xats_trobats.append(contenidor)
        except Exception:
            continue
    return xats_trobats


def nom_del_xat(xat_element):
    """Extreu el nom del xat d'un element contenidor."""
    selectors = [
        '[data-testid="cell-frame-title"] span[title]',
        'span[dir="auto"][title]',
        '[data-testid="cell-frame-title"]',
    ]
    for sel in selectors:
        try:
            el = xat_element.query_selector(sel)
            if el:
                nom = el.get_attribute("title") or el.inner_text()
                if nom and nom.strip():
                    return nom.strip()
        except Exception:
            continue
    return "Desconegut"


def respondre_xat(page, xat_element, missatge, ultimes_respostes):
    """Obre el xat i envia la resposta automàtica si escau."""
    nom = nom_del_xat(xat_element)

    # Comprova el temps de refredament
    ara = time.time()
    if nom in ultimes_respostes:
        transcorregut = ara - ultimes_respostes[nom]
        if transcorregut < TEMPS_REFREDAMENT:
            return False

    print(f"\n  Nou missatge de: {nom}")
    xat_element.click()
    time.sleep(1.5)

    # Espera la caixa de text del xat obert
    selectors_caixa = [
        '[data-testid="conversation-compose-box-input"]',
        'div[contenteditable="true"][data-tab="10"]',
        'footer div[contenteditable="true"]',
        'div[aria-label="Missatge"][contenteditable="true"]',
        'div[aria-label="Message"][contenteditable="true"]',
    ]

    caixa = None
    for sel in selectors_caixa:
        try:
            page.wait_for_selector(sel, timeout=6000)
            caixa = page.query_selector(sel)
            if caixa:
                break
        except PlaywrightTimeout:
            continue

    if not caixa:
        print(f"  No s'ha trobat la caixa de text per a '{nom}'.")
        return False

    try:
        caixa.click()
        caixa.type(missatge, delay=25)
        time.sleep(0.4)
        caixa.press("Enter")
        time.sleep(0.8)

        resum = missatge[:50] + "..." if len(missatge) > 50 else missatge
        print(f"  Resposta enviada a '{nom}': '{resum}'")
        ultimes_respostes[nom] = time.time()
        return True
    except Exception as e:
        print(f"  Error enviant resposta a '{nom}': {e}")
        return False


def main():
    print("\n" + "="*55)
    print("  BOT DE RESPOSTA AUTOMÀTICA - WHATSAPP")
    print("="*55)
    print(f"  Resposta: '{MISSATGE_RESPOSTA}'")
    print(f"  Comprovació cada: {INTERVAL_COMPROVACIO}s")
    print(f"  Refredament per xat: {TEMPS_REFREDAMENT}s")
    print("\n  Prem Ctrl+C per aturar.")
    print("="*55 + "\n")

    estat_sessio = carregar_sessio()
    ultimes_respostes = {}  # {nom_xat: timestamp_ultima_resposta}

    with sync_playwright() as p:
        print("  Obrint el navegador...")
        browser = p.chromium.launch(
            headless=False,
            slow_mo=150,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context_opts = {
            "viewport": {"width": 1300, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if estat_sessio:
            print("  Carregant sessió guardada...")
            context_opts["storage_state"] = estat_sessio

        context = browser.new_context(**context_opts)
        page = context.new_page()

        print("  Navegant a WhatsApp Web...")
        try:
            page.goto(WHATSAPP_URL, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(WHATSAPP_URL, timeout=30000)

        if not esperar_carregat(page):
            browser.close()
            return

        guardar_sessio(context)
        print("  Sessió guardada per a la pròxima vegada.")
        print("\n  Monitoritzant missatges entrants...\n")

        try:
            while True:
                xats = obtenir_xats_no_llegits(page)

                if xats:
                    print(f"  {len(xats)} xat(s) amb missatges nous.")
                    for xat in xats:
                        respondre_xat(page, xat, MISSATGE_RESPOSTA, ultimes_respostes)
                        time.sleep(0.8)
                    guardar_sessio(context)
                else:
                    print(
                        f"  Sense missatges nous. Pròxima comprovació en {INTERVAL_COMPROVACIO}s...",
                        end="\r"
                    )

                time.sleep(INTERVAL_COMPROVACIO)

        except KeyboardInterrupt:
            print("\n\n  Bot aturat per l'usuari.")
        finally:
            guardar_sessio(context)
            print("  Sessió guardada. Tancant el navegador...")
            browser.close()
            print("  Fins aviat!")


if __name__ == "__main__":
    main()
