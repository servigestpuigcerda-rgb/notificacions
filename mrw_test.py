#!/usr/bin/env python3
"""
Diagnòstic de la connexió amb el servei web de MRW (SAGEC).

NO crea cap enviament ni envia cap SMS. Serveix per comprovar, abans de
fer res real, que tot està a punt:

  1. Que des de la teva màquina s'arriba al servidor de MRW.
  2. Que el WSDL es descarrega i s'interpreta correctament.
  3. Que les credencials del fitxer .env es carreguen.
  4. Quins mètodes (operacions) ofereix el servei del teu compte.
  5. L'ESTRUCTURA EXACTA que espera el mètode TransmEnvio (útil per
     confirmar com s'ha d'informar el bloc de notificacions/SMS).

Ús:
    python mrw_test.py            # entorn de producció
    python mrw_test.py --proves   # entorn de proves (sagec-test)
"""

import os
import sys
import argparse

from dotenv import load_dotenv

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
except ImportError:
    print("Falta la llibreria 'zeep'. Instal·la les dependències amb:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

# Reutilitzem la configuració i el client del mòdul principal.
from mrw_sms import (
    WSDL_PRODUCCIO,
    WSDL_PROVES,
    NAMESPACE,
    MRWClient,
    MRWError,
    _client_des_de_env,
)

load_dotenv()


def _linia(car="-", n=60):
    print("  " + car * n)


def comprovar_wsdl(proves):
    """Descarrega i interpreta el WSDL. Retorna el client zeep."""
    wsdl = WSDL_PROVES if proves else WSDL_PRODUCCIO
    print(f"\n  [1] Connectant al WSDL de MRW:")
    print(f"      {wsdl}")
    try:
        settings = Settings(strict=False, xml_huge_tree=True)
        client = Client(wsdl, settings=settings, transport=Transport(timeout=30))
    except Exception as e:
        print(f"\n  ✗ No s'ha pogut connectar/interpretar el WSDL.")
        print(f"    Motiu: {e}")
        print("\n    Causes habituals:")
        print("      - Sense connexió a Internet o MRW temporalment caigut.")
        print("      - Un tallafoc/proxy bloqueja sagec.mrw.es.")
        raise MRWError("WSDL no disponible")
    print("  ✓ WSDL descarregat i interpretat correctament.")
    return client


def llistar_operacions(client):
    """Mostra les operacions (mètodes) que ofereix el servei."""
    print("\n  [2] Operacions disponibles al servei:")
    _linia()
    noms = []
    try:
        for service in client.wsdl.services.values():
            for port in service.ports.values():
                operacions = port.binding._operations
                noms.extend(operacions.keys())
    except Exception as e:
        print(f"      (no s'han pogut llistar: {e})")
        return
    for nom in sorted(set(noms)):
        marca = "  ← el que fem servir" if nom == "TransmEnvio" else ""
        print(f"      · {nom}{marca}")


def mostrar_estructura_transmenvio(client):
    """Bolca l'estructura que espera TransmEnvio (camps i notificacions)."""
    print("\n  [3] Estructura que espera TransmEnvio (segons el teu WSDL):")
    _linia()
    try:
        elem = client.get_element("{%s}TransmEnvio" % NAMESPACE)
        print("      " + elem.signature(schema=client.wsdl.types).replace("\n", "\n      "))
    except Exception:
        # Alternativa: bolcat complet del WSDL (més verbós però sempre funciona).
        try:
            print("      (signatura no disponible; bolcat complet del WSDL a sota)\n")
            client.wsdl.dump()
        except Exception as e:
            print(f"      No s'ha pogut obtenir l'estructura: {e}")
    print("\n      NOTA: fixa't en el bloc 'Notificaciones'. Si al teu WSDL")
    print("      apareix com una llista de 'NotificacionRequest', cal ajustar")
    print("      mrw_sms.py (hi ha un comentari indicant on).")


def comprovar_credencials(proves):
    """Comprova que les credencials del .env es carreguen i el header es crea."""
    print("\n  [4] Credencials del fitxer .env:")
    _linia()
    camps = {
        "MRW_FRANQUICIA": os.getenv("MRW_FRANQUICIA", ""),
        "MRW_ABONAT": os.getenv("MRW_ABONAT", ""),
        "MRW_USUARI": os.getenv("MRW_USUARI", ""),
        "MRW_CONTRASENYA": os.getenv("MRW_CONTRASENYA", ""),
    }
    tot_ok = True
    for nom, valor in camps.items():
        if valor:
            # No mostrem mai el valor sencer (sobretot la contrasenya).
            mostra = valor[:2] + "···" if nom == "MRW_CONTRASENYA" else valor
            print(f"      ✓ {nom} = {mostra}")
        else:
            print(f"      ✗ {nom} — BUIT")
            tot_ok = False

    if not tot_ok:
        print("\n      Falten credencials. Edita el fitxer .env.")
        return False

    # Comprova que el client i la capçalera AuthInfo es construeixen bé.
    try:
        _client_des_de_env(proves=proves)
        print("\n  ✓ Capçalera d'autenticació (AuthInfo) construïda correctament.")
    except MRWError as e:
        print(f"\n  ✗ {e}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Diagnòstic de la connexió amb MRW (no crea enviaments)."
    )
    parser.add_argument(
        "--proves", action="store_true",
        help="Fer servir l'entorn de proves de MRW (sagec-test)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 62)
    print("  DIAGNÒSTIC DE CONNEXIÓ AMB MRW (SAGEC) — no crea enviaments")
    print("=" * 62)

    try:
        client = comprovar_wsdl(args.proves)
    except MRWError:
        print("\n  Resultat: NO es pot continuar sense connexió al WSDL.\n")
        sys.exit(1)

    llistar_operacions(client)
    mostrar_estructura_transmenvio(client)
    creds_ok = comprovar_credencials(args.proves)

    print("\n" + "=" * 62)
    if creds_ok:
        print("  ✓ Tot a punt: connexió correcta i credencials carregades.")
        print("    Ja pots fer una prova real amb:")
        print("      python mrw_sms.py --proves --nom ... --telefon ...")
    else:
        print("  ⚠ Connexió correcta, però revisa les credencials del .env.")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()
