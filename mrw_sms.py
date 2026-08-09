#!/usr/bin/env python3
"""
Connexió amb l'API oficial de MRW (SAGEC, SOAP) per registrar un enviament
i que MRW enviï un SMS d'avís de repartiment al destinatari.

MRW no és una passarel·la d'SMS genèrica: el que fa aquest mòdul és donar
d'alta un enviament mitjançant el mètode `TransmEnvio` del servei web SAGEC
i activar-ne la NOTIFICACIÓ per SMS. Quan l'enviament es tramita, MRW envia
automàticament l'SMS al número del destinatari (avís d'emissió/repartiment,
segons el tipus de notificació que triïs).

Ús ràpid (CLI):
    python mrw_sms.py \
        --nom "Joan Garcia" \
        --telefon "600123456" \
        --via "Carrer Major" --numero "10" \
        --cp "17520" --poblacio "Puigcerdà"

Les credencials es llegeixen del fitxer .env (vegeu .env.example).
"""

import os
import sys
import argparse
from datetime import date

from dotenv import load_dotenv

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
    from zeep.helpers import serialize_object
    from zeep.exceptions import Fault
except ImportError:
    print("Falta la llibreria 'zeep'. Instal·la les dependències amb:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

load_dotenv()

# --- Endpoints oficials del servei web de MRW (SAGEC) ---------------------
WSDL_PRODUCCIO = "http://sagec.mrw.es/MRWEnvio.asmx?WSDL"
WSDL_PROVES = "https://sagec-test.mrw.es/MRWEnvio.asmx?WSDL"
NAMESPACE = "http://www.mrw.es/"

# --- Canals de notificació de MRW -----------------------------------------
#   "1" = correu electrònic
#   "2" = SMS
CANAL_EMAIL = "1"
CANAL_SMS = "2"

# --- Tipus de notificació (esdeveniment que dispara l'SMS) ----------------
#   "1" = avís d'emissió (quan es dóna d'alta l'enviament)
#   "2" = avís de trànsit
#   "3" = avís de repartiment / entrega (informa el dia de repartiment)
#   "4" = avís d'incidència
# Nota: confirma els codis exactes amb el manual d'integració SAGEC de la
# teva franquícia MRW; poden variar segons el contracte.
TIPUS_EMISSIO = "1"
TIPUS_ENTREGA = "3"

# Codi de servei MRW per defecte (consulta els codis del teu contracte).
#   "0005" = Econòmic 24 h, "0800" = Urgent 19, "0300" = Urgent 12, etc.
CODI_SERVEI_DEFECTE = os.getenv("MRW_CODI_SERVEI", "0005")


class MRWError(Exception):
    """Error retornat pel servei web de MRW o per la configuració local."""


class MRWClient:
    """Client mínim del servei web SAGEC de MRW per crear enviaments."""

    def __init__(self, franquicia, abonat, usuari, contrasenya,
                 departament="", proves=False, timeout=30):
        if not all([franquicia, abonat, usuari, contrasenya]):
            raise MRWError(
                "Falten credencials de MRW. Comprova el fitxer .env "
                "(MRW_FRANQUICIA, MRW_ABONAT, MRW_USUARI, MRW_CONTRASENYA)."
            )

        wsdl = WSDL_PROVES if proves else WSDL_PRODUCCIO
        settings = Settings(strict=False, xml_huge_tree=True)
        self.client = Client(
            wsdl, settings=settings, transport=Transport(timeout=timeout)
        )

        # La capçalera d'autenticació AuthInfo va al SOAP Header.
        auth_type = self.client.get_element("{%s}AuthInfo" % NAMESPACE)
        self.auth_header = auth_type(
            CodigoFranquicia=franquicia,
            CodigoAbonado=abonat,
            CodigoDepartamento=departament or "",
            UserName=usuari,
            Password=contrasenya,
        )

    def crear_enviament(self, *, destinatari, servei):
        """Crida TransmEnvio amb les dades d'entrega i de servei donades.

        `destinatari` i `servei` són diccionaris amb l'estructura que espera
        el WSDL de MRW. Retorna la resposta ja convertida a diccionari.
        """
        request = {
            "DatosEntrega": destinatari,
            "DatosServicio": servei,
        }
        try:
            resposta = self.client.service.TransmEnvio(
                request, _soapheaders=[self.auth_header]
            )
        except Fault as e:
            raise MRWError("El servei de MRW ha retornat un error SOAP: %s" % e)

        return serialize_object(resposta)

    def enviar_amb_avis_sms(self, *, nom, telefon, via, numero, cp, poblacio,
                            nif="", contacte="", observacions="",
                            resta="", codi_tipus_via="",
                            codi_servei=None, num_bultos=1, pes="1",
                            referencia="", data=None,
                            tipus_notificacio=TIPUS_ENTREGA):
        """Crea un enviament i activa l'avís per SMS al destinatari.

        Retorna un diccionari amb el resultat normalitzat:
            {ok, numero_envio, url_etiqueta, missatge, resposta_completa}
        """
        if not telefon:
            raise MRWError("Cal un número de telèfon del destinatari per a l'SMS.")

        data_env = data or date.today().strftime("%d/%m/%Y")
        codi_servei = codi_servei or CODI_SERVEI_DEFECTE

        destinatari = {
            "Nombre": nom,
            "Nif": nif,
            "Telefono": telefon,
            "Contacto": contacte or nom,
            "Observaciones": observacions,
            "Direccion": {
                "CodigoTipoVia": codi_tipus_via,
                "Via": via,
                "Numero": numero,
                "Resto": resta,
                "CodigoPostal": cp,
                "Poblacion": poblacio,
            },
        }

        # Bloc de notificacions: activa el canal SMS cap al telèfon del client.
        # Si el WSDL de la teva franquícia espera una llista de
        # `NotificacionRequest`, canvia aquest bloc per:
        #   "Notificaciones": {"NotificacionRequest": [ { ...camps... } ]}
        notificacions = {
            "CanalNotificacion": CANAL_SMS,
            "TipoNotificacion": tipus_notificacio,
            "MailSMS": telefon,
        }

        servei = {
            "Fecha": data_env,
            "Referencia": referencia,
            "CodigoServicio": codi_servei,
            "NumeroBultos": num_bultos,
            "Peso": pes,
            "Notificaciones": notificacions,
        }

        resposta = self.crear_enviament(destinatari=destinatari, servei=servei)
        return self._normalitza_resposta(resposta)

    @staticmethod
    def _normalitza_resposta(resposta):
        """Interpreta la resposta de TransmEnvio de forma defensiva."""
        resposta = resposta or {}

        # MRW marca l'èxit amb Estado == "1" (o "OK" segons versió).
        estat = str(resposta.get("Estado", "")).strip()
        ok = estat in ("1", "OK", "true", "True")

        missatge = resposta.get("Mensaje") or ""
        errors = resposta.get("Errores")
        if errors and not ok:
            # Errores pot ser un objecte o una llista d'Error amb Descripcion.
            missatge = missatge or _descriu_errors(errors)

        return {
            "ok": ok,
            "numero_envio": resposta.get("NumeroEnvio"),
            "numero_solicitud": resposta.get("NumeroSolicitud"),
            "url_etiqueta": resposta.get("Url") or resposta.get("UrlDocumentoEnvio"),
            "missatge": missatge,
            "resposta_completa": resposta,
        }


def _descriu_errors(errors):
    """Extreu descripcions d'errors de l'estructura Errores de MRW."""
    llista = errors
    if isinstance(errors, dict):
        llista = errors.get("Error", errors)
    if isinstance(llista, dict):
        llista = [llista]
    if not isinstance(llista, (list, tuple)):
        return str(errors)
    parts = []
    for e in llista:
        if isinstance(e, dict):
            parts.append(str(e.get("Descripcion") or e.get("Mensaje") or e))
        else:
            parts.append(str(e))
    return "; ".join(p for p in parts if p)


def _client_des_de_env(proves=False):
    return MRWClient(
        franquicia=os.getenv("MRW_FRANQUICIA", ""),
        abonat=os.getenv("MRW_ABONAT", ""),
        usuari=os.getenv("MRW_USUARI", ""),
        contrasenya=os.getenv("MRW_CONTRASENYA", ""),
        departament=os.getenv("MRW_DEPARTAMENT", ""),
        proves=proves,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Crea un enviament a MRW i activa l'avís per SMS al destinatari."
    )
    parser.add_argument("--nom", required=True, help="Nom del destinatari")
    parser.add_argument("--telefon", required=True, help="Telèfon mòbil (rep l'SMS)")
    parser.add_argument("--via", required=True, help="Nom del carrer / via")
    parser.add_argument("--numero", required=True, help="Número del carrer")
    parser.add_argument("--cp", required=True, help="Codi postal")
    parser.add_argument("--poblacio", required=True, help="Població")
    parser.add_argument("--nif", default="", help="NIF del destinatari (opcional)")
    parser.add_argument("--observacions", default="", help="Observacions per al repartidor")
    parser.add_argument("--referencia", default="", help="Referència interna de l'enviament")
    parser.add_argument("--codi-servei", default=None, help="Codi de servei MRW")
    parser.add_argument("--bultos", type=int, default=1, help="Nombre de bultos")
    parser.add_argument("--pes", default="1", help="Pes en kg")
    parser.add_argument(
        "--tipus-avis", default=TIPUS_ENTREGA,
        help="Tipus de notificació: 1=emissió, 3=repartiment (per defecte)",
    )
    parser.add_argument(
        "--proves", action="store_true",
        help="Fer servir l'entorn de proves de MRW (sagec-test)",
    )
    args = parser.parse_args()

    try:
        client = _client_des_de_env(proves=args.proves)
        resultat = client.enviar_amb_avis_sms(
            nom=args.nom,
            telefon=args.telefon,
            via=args.via,
            numero=args.numero,
            cp=args.cp,
            poblacio=args.poblacio,
            nif=args.nif,
            observacions=args.observacions,
            referencia=args.referencia,
            codi_servei=args.codi_servei,
            num_bultos=args.bultos,
            pes=args.pes,
            tipus_notificacio=args.tipus_avis,
        )
    except MRWError as e:
        print(f"\n  Error: {e}\n")
        sys.exit(1)

    print("\n" + "=" * 55)
    if resultat["ok"]:
        print("  ENVIAMENT CREAT — MRW enviarà l'SMS al destinatari")
        print("=" * 55)
        print(f"  Número d'enviament: {resultat['numero_envio']}")
        if resultat["url_etiqueta"]:
            print(f"  Etiqueta:           {resultat['url_etiqueta']}")
    else:
        print("  NO s'ha pogut crear l'enviament")
        print("=" * 55)
        print(f"  Missatge de MRW: {resultat['missatge'] or 'sense detall'}")
    print("=" * 55 + "\n")

    sys.exit(0 if resultat["ok"] else 1)


if __name__ == "__main__":
    main()
