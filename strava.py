#!/usr/bin/env python3
"""Integració amb Strava: autenticació OAuth 2.0 i consulta d'activitats."""

import os
import json
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import requests
from dotenv import load_dotenv, set_key

load_dotenv()

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
REDIRECT_URI = "http://localhost:8765/callback"
ENV_FILE = ".env"

TIPUS_ACTIVITAT = {
    "Run": "Cursa",
    "Ride": "Ciclisme",
    "Swim": "Natació",
    "Walk": "Caminada",
    "Hike": "Senderisme",
    "VirtualRide": "Ciclisme virtual",
    "VirtualRun": "Cursa virtual",
    "WeightTraining": "Musculació",
    "Yoga": "Ioga",
    "Workout": "Entrenament",
}


class CallbackHandler(BaseHTTPRequestHandler):
    """Captura el codi d'autorització de Strava."""

    auth_code = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;text-align:center;padding:50px'>"
                b"<h2>\xe2\x9c\x85 Autenticaci\xc3\xb3 completada!</h2>"
                b"<p>Ja pots tancar aquesta finestra i tornar al terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error: no s'ha rebut el codi d'autoritzaci\xc3\xb3")

    def log_message(self, *args):
        pass


def obtenir_client_id_secret():
    client_id = os.getenv("STRAVA_CLIENT_ID", "").strip()
    client_secret = os.getenv("STRAVA_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print("\n" + "=" * 55)
        print("  CONFIGURACIÓ DE L'APLICACIÓ STRAVA")
        print("=" * 55)
        print("\nNecessites crear una aplicació a Strava:")
        print("  1. Vés a https://www.strava.com/settings/api")
        print("  2. Omple el formulari (nom, web, zona de callback: localhost)")
        print("  3. A 'Authorization Callback Domain' posa: localhost")
        print("  4. Copia el 'Client ID' i el 'Client Secret'\n")

        client_id = input("Client ID de Strava: ").strip()
        client_secret = input("Client Secret de Strava: ").strip()

        set_key(ENV_FILE, "STRAVA_CLIENT_ID", client_id)
        set_key(ENV_FILE, "STRAVA_CLIENT_SECRET", client_secret)
        print("✓ Credencials desades a .env\n")

    return client_id, client_secret


def autenticar(client_id, client_secret):
    """Inicia el flux OAuth 2.0 i retorna els tokens."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "activity:read_all",
    }
    auth_url = f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    print("\nObrint el navegador per autoritzar l'accés a Strava...")
    print(f"Si no s'obre, vés manualment a:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8765), CallbackHandler)
    server.timeout = 120
    print("Esperant autorització (màxim 2 minuts)...")
    server.handle_request()

    if not CallbackHandler.auth_code:
        raise RuntimeError("No s'ha rebut el codi d'autorització. Torna-ho a provar.")

    print("✓ Codi d'autorització rebut. Obtenint tokens...")

    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": CallbackHandler.auth_code,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    set_key(ENV_FILE, "STRAVA_ACCESS_TOKEN", tokens["access_token"])
    set_key(ENV_FILE, "STRAVA_REFRESH_TOKEN", tokens["refresh_token"])
    set_key(ENV_FILE, "STRAVA_TOKEN_EXPIRES", str(tokens["expires_at"]))

    print("✓ Tokens desats a .env\n")
    return tokens


def renovar_token_si_cal(client_id, client_secret):
    """Renova el token d'accés si ha caducat."""
    expires_at = int(os.getenv("STRAVA_TOKEN_EXPIRES", "0"))
    if time.time() < expires_at - 60:
        return os.getenv("STRAVA_ACCESS_TOKEN")

    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN", "")
    if not refresh_token:
        return None

    print("Renovant el token d'accés...")
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    set_key(ENV_FILE, "STRAVA_ACCESS_TOKEN", tokens["access_token"])
    set_key(ENV_FILE, "STRAVA_REFRESH_TOKEN", tokens["refresh_token"])
    set_key(ENV_FILE, "STRAVA_TOKEN_EXPIRES", str(tokens["expires_at"]))

    load_dotenv(override=True)
    return tokens["access_token"]


def obtenir_token(client_id, client_secret):
    """Retorna un token vàlid, autenticant si cal."""
    token = renovar_token_si_cal(client_id, client_secret)
    if token:
        return token
    tokens = autenticar(client_id, client_secret)
    return tokens["access_token"]


def obtenir_perfil(token):
    resp = requests.get(
        f"{STRAVA_API_BASE}/athlete",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def obtenir_activitats(token, pagina=1, per_pagina=10, tipus=None):
    params = {"page": pagina, "per_page": per_pagina}
    resp = requests.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    activitats = resp.json()
    if tipus:
        activitats = [a for a in activitats if a.get("type") == tipus]
    return activitats


def formatar_distancia(metres):
    if metres >= 1000:
        return f"{metres / 1000:.2f} km"
    return f"{metres:.0f} m"


def formatar_temps(segons):
    h = int(segons // 3600)
    m = int((segons % 3600) // 60)
    s = int(segons % 60)
    if h > 0:
        return f"{h}h {m:02d}min {s:02d}s"
    return f"{m}min {s:02d}s"


def formatar_ritme(metres, segons):
    if metres <= 0:
        return "—"
    min_per_km = (segons / 60) / (metres / 1000)
    m = int(min_per_km)
    s = int((min_per_km - m) * 60)
    return f"{m}:{s:02d} min/km"


def mostrar_activitats(activitats):
    if not activitats:
        print("\nNo s'han trobat activitats.")
        return

    print(f"\n{'=' * 60}")
    print(f"  {len(activitats)} ACTIVITAT(S) TROBADA(S)")
    print(f"{'=' * 60}")

    for i, act in enumerate(activitats, 1):
        tipus = TIPUS_ACTIVITAT.get(act.get("type", ""), act.get("type", "Desconegut"))
        data = act.get("start_date_local", "")[:10]
        nom = act.get("name", "Sense nom")
        distancia = formatar_distancia(act.get("distance", 0))
        temps = formatar_temps(act.get("moving_time", 0))
        desnivell = act.get("total_elevation_gain", 0)
        fc_mitja = act.get("average_heartrate")
        ritme = formatar_ritme(act.get("distance", 0), act.get("moving_time", 0))

        print(f"\n  [{i}] {nom}")
        print(f"       Tipus:     {tipus}  |  Data: {data}")
        print(f"       Distància: {distancia}  |  Temps: {temps}")
        if act.get("type") in ("Run", "Walk", "Hike"):
            print(f"       Ritme:     {ritme}  |  Desnivell: {desnivell:.0f} m")
        else:
            print(f"       Desnivell: {desnivell:.0f} m")
        if fc_mitja:
            print(f"       FC mitjana: {fc_mitja:.0f} bpm")

    print(f"\n{'=' * 60}\n")


def menu_principal(token):
    while True:
        print("\n--- MENÚ STRAVA ---")
        print("1. Veure les últimes 10 activitats")
        print("2. Veure les últimes 20 activitats")
        print("3. Filtrar per tipus d'activitat")
        print("4. Veure el meu perfil")
        print("0. Sortir")
        print()

        opcio = input("Tria una opció: ").strip()

        if opcio == "1":
            acts = obtenir_activitats(token, per_pagina=10)
            mostrar_activitats(acts)

        elif opcio == "2":
            acts = obtenir_activitats(token, per_pagina=20)
            mostrar_activitats(acts)

        elif opcio == "3":
            print("\nTipus disponibles:")
            tipus_llista = list(TIPUS_ACTIVITAT.items())
            for i, (codi, nom) in enumerate(tipus_llista, 1):
                print(f"  {i}. {nom} ({codi})")
            sel = input("\nQuin tipus? (número): ").strip()
            try:
                idx = int(sel) - 1
                codi_tipus = tipus_llista[idx][0]
                acts = obtenir_activitats(token, per_pagina=20, tipus=codi_tipus)
                mostrar_activitats(acts)
            except (ValueError, IndexError):
                print("Selecció no vàlida.")

        elif opcio == "4":
            perfil = obtenir_perfil(token)
            print(f"\n  Atleta: {perfil.get('firstname', '')} {perfil.get('lastname', '')}")
            print(f"  Ciutat: {perfil.get('city', '—')}")
            print(f"  País:   {perfil.get('country', '—')}")
            print(f"  Seguidors: {perfil.get('follower_count', 0)}")
            print(f"  Seguint:   {perfil.get('friend_count', 0)}")

        elif opcio == "0":
            print("Fins aviat!")
            break
        else:
            print("Opció no vàlida.")


def main():
    print("=" * 55)
    print("  INTEGRACIÓ AMB STRAVA")
    print("=" * 55)

    client_id, client_secret = obtenir_client_id_secret()

    try:
        token = obtenir_token(client_id, client_secret)
    except Exception as e:
        print(f"\nError d'autenticació: {e}")
        return

    perfil = obtenir_perfil(token)
    print(f"\nConnectat com: {perfil.get('firstname', '')} {perfil.get('lastname', '')} ✓")

    menu_principal(token)


if __name__ == "__main__":
    main()
