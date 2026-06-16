#!/usr/bin/env python3
"""Integració amb Microsoft Planner via Microsoft Graph API."""

import os
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

import requests
from dotenv import load_dotenv, set_key

load_dotenv()

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
REDIRECT_URI = "http://localhost:8766/callback"
SCOPES = "Tasks.ReadWrite offline_access"
ENV_FILE = ".env"

PRIORITATS = {
    0: "Urgent",
    1: "Important",
    5: "Mitjana",
    9: "Baixa",
}


class CallbackHandler(BaseHTTPRequestHandler):
    """Captura el codi d'autorització de Microsoft."""

    auth_code = None
    error = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body style='font-family:sans-serif;text-align:center;padding:50px'>"
                "<h2>✅ Autenticació completada!</h2>"
                "<p>Ja pots tancar aquesta finestra i tornar al terminal.</p>"
                "</body></html>".encode("utf-8")
            )
        else:
            CallbackHandler.error = params.get("error_description", ["Error desconegut"])[0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write("Error d'autorització".encode("utf-8"))

    def log_message(self, *args):
        pass


def obtenir_client_id():
    client_id = os.getenv("MS_PLANNER_CLIENT_ID", "").strip()
    if not client_id:
        print("\n" + "=" * 62)
        print("  CONFIGURACIÓ DE L'APLICACIÓ AZURE AD")
        print("=" * 62)
        print("\nNecessites registrar una aplicació a Azure AD:")
        print("  1. Vés a https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps")
        print("  2. Clica 'New registration'")
        print("  3. Nom: 'Planner Integration' (o el que vulguis)")
        print("  4. Supported account types: 'Accounts in any organizational")
        print("     directory and personal Microsoft accounts'")
        print("  5. Redirect URI: Web → http://localhost:8766/callback")
        print("  6. Clica 'Register' i copia l'Application (client) ID")
        print()
        print("  IMPORTANT: A 'API permissions' afegeix:")
        print("    → Tasks.ReadWrite (Delegated)")
        print("    → Clica 'Grant admin consent' si el boto esta disponible")
        print()
        client_id = input("Application (Client) ID: ").strip()
        set_key(ENV_FILE, "MS_PLANNER_CLIENT_ID", client_id)
        print("✓ Client ID desat a .env\n")
    return client_id


def autenticar(client_id):
    """Inicia el flux OAuth 2.0 i retorna el token d'accés."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "response_mode": "query",
    }
    auth_url = f"{MS_AUTH_URL}?{urlencode(params)}"

    print("\nObrint el navegador per autoritzar l'accés a Microsoft Planner...")
    print(f"Si no s'obre, vés manualment a:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    CallbackHandler.auth_code = None
    CallbackHandler.error = None
    server = HTTPServer(("localhost", 8766), CallbackHandler)
    server.timeout = 120
    print("Esperant autorització (màxim 2 minuts)...")
    server.handle_request()

    if CallbackHandler.error:
        raise RuntimeError(f"Error d'autorització: {CallbackHandler.error}")
    if not CallbackHandler.auth_code:
        raise RuntimeError("No s'ha rebut el codi d'autorització. Torna-ho a provar.")

    print("✓ Codi rebut. Obtenint tokens...")
    resp = requests.post(
        MS_TOKEN_URL,
        data={
            "client_id": client_id,
            "code": CallbackHandler.auth_code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": SCOPES,
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    set_key(ENV_FILE, "MS_PLANNER_ACCESS_TOKEN", tokens["access_token"])
    set_key(ENV_FILE, "MS_PLANNER_REFRESH_TOKEN", tokens.get("refresh_token", ""))
    expires_at = int(time.time()) + tokens.get("expires_in", 3600)
    set_key(ENV_FILE, "MS_PLANNER_TOKEN_EXPIRES", str(expires_at))

    print("✓ Tokens desats a .env\n")
    return tokens["access_token"]


def renovar_token_si_cal(client_id):
    """Renova el token d'accés si ha caducat."""
    expires_at = int(os.getenv("MS_PLANNER_TOKEN_EXPIRES", "0"))
    if time.time() < expires_at - 60:
        return os.getenv("MS_PLANNER_ACCESS_TOKEN")

    refresh_token = os.getenv("MS_PLANNER_REFRESH_TOKEN", "")
    if not refresh_token:
        return None

    print("Renovant el token d'accés...")
    resp = requests.post(
        MS_TOKEN_URL,
        data={
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": SCOPES,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        return None

    tokens = resp.json()
    set_key(ENV_FILE, "MS_PLANNER_ACCESS_TOKEN", tokens["access_token"])
    if "refresh_token" in tokens:
        set_key(ENV_FILE, "MS_PLANNER_REFRESH_TOKEN", tokens["refresh_token"])
    expires_at = int(time.time()) + tokens.get("expires_in", 3600)
    set_key(ENV_FILE, "MS_PLANNER_TOKEN_EXPIRES", str(expires_at))
    load_dotenv(override=True)
    return tokens["access_token"]


def obtenir_token(client_id):
    """Retorna un token vàlid, autenticant si cal."""
    token = renovar_token_si_cal(client_id)
    if token:
        return token
    return autenticar(client_id)


def obtenir_perfil(token):
    resp = requests.get(
        f"{GRAPH_BASE}/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def obtenir_tasques_meves(token):
    """Obté les tasques de Planner assignades a l'usuari actual."""
    resp = requests.get(
        f"{GRAPH_BASE}/me/planner/tasks",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def obtenir_pla(token, plan_id):
    resp = requests.get(
        f"{GRAPH_BASE}/planner/plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    return {"title": f"Pla {plan_id[:8]}...", "id": plan_id}


def obtenir_tasques_pla(token, plan_id):
    resp = requests.get(
        f"{GRAPH_BASE}/planner/plans/{plan_id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def obtenir_cubells_pla(token, plan_id):
    resp = requests.get(
        f"{GRAPH_BASE}/planner/plans/{plan_id}/buckets",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def crear_tasca(token, plan_id, bucket_id, titol, prioritat=None, data_limit=None):
    dades = {
        "planId": plan_id,
        "bucketId": bucket_id,
        "title": titol,
    }
    if prioritat is not None:
        dades["priority"] = prioritat
    if data_limit:
        dades["dueDateTime"] = f"{data_limit}T00:00:00Z"

    resp = requests.post(
        f"{GRAPH_BASE}/planner/tasks",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=dades,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def completar_tasca(token, task_id, etag):
    resp = requests.patch(
        f"{GRAPH_BASE}/planner/tasks/{task_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "If-Match": etag,
        },
        json={"percentComplete": 100},
        timeout=15,
    )
    resp.raise_for_status()


def mostrar_tasques(tasques, nom_pla=None):
    if not tasques:
        print("\nNo s'han trobat tasques.")
        return

    titol = f"TASQUES DE '{nom_pla.upper()}'" if nom_pla else "LES MEVES TASQUES"
    print(f"\n{'=' * 60}")
    print(f"  {len(tasques)} {titol}")
    print(f"{'=' * 60}")

    for i, t in enumerate(tasques, 1):
        pct = t.get("percentComplete", 0)
        marcador = "✓" if pct == 100 else ("~" if pct > 0 else " ")
        nom = t.get("title", "Sense títol")
        prioritat = PRIORITATS.get(t.get("priority"), "—")
        data = (t.get("dueDateTime") or "")[:10] or "—"
        estat = "Completada" if pct == 100 else ("En progrés" if pct > 0 else "Pendent")

        print(f"\n  [{i}] [{marcador}] {nom}")
        print(f"       Estat: {estat}  |  Prioritat: {prioritat}  |  Límit: {data}")

    print(f"\n{'=' * 60}\n")


def seleccionar_pla(token, cache_plans):
    """Descobreix plans a partir de les tasques de l'usuari i en tria un."""
    print("\nObtenant plans disponibles...")
    tasques = obtenir_tasques_meves(token)
    plans_ids = list(dict.fromkeys(t["planId"] for t in tasques if "planId" in t))

    if not plans_ids:
        print("No s'ha trobat cap pla. Cal tenir almenys una tasca assignada a Planner.")
        return None, None

    plans = []
    for pid in plans_ids:
        if pid not in cache_plans:
            cache_plans[pid] = obtenir_pla(token, pid)
        plans.append(cache_plans[pid])

    print(f"\nPlans disponibles ({len(plans)}):")
    for i, pla in enumerate(plans, 1):
        print(f"  {i}. {pla.get('title', 'Sense nom')}")

    sel = input("\nQuin pla? (número): ").strip()
    try:
        idx = int(sel) - 1
        return plans[idx], tasques
    except (ValueError, IndexError):
        print("Selecció no vàlida.")
        return None, None


def menu_principal(token):
    cache_plans = {}

    while True:
        print("\n--- MENÚ MICROSOFT PLANNER ---")
        print("1. Veure les meves tasques")
        print("2. Veure tasques d'un pla concret")
        print("3. Crear tasca nova")
        print("4. Marcar tasca com a completada")
        print("0. Sortir")
        print()

        opcio = input("Tria una opció: ").strip()

        if opcio == "1":
            tasques = obtenir_tasques_meves(token)
            mostrar_tasques(tasques)

        elif opcio == "2":
            pla, _ = seleccionar_pla(token, cache_plans)
            if pla:
                tasques_pla = obtenir_tasques_pla(token, pla["id"])
                mostrar_tasques(tasques_pla, nom_pla=pla.get("title", ""))

        elif opcio == "3":
            pla, _ = seleccionar_pla(token, cache_plans)
            if not pla:
                continue

            cubells = obtenir_cubells_pla(token, pla["id"])
            if not cubells:
                print("Aquest pla no té cubells (buckets).")
                continue

            print("\nTriar cubell:")
            for i, c in enumerate(cubells, 1):
                print(f"  {i}. {c.get('name', 'Sense nom')}")

            sel = input("Quin cubell? (número): ").strip()
            try:
                cubell = cubells[int(sel) - 1]
            except (ValueError, IndexError):
                print("Selecció no vàlida.")
                continue

            titol = input("\nTítol de la tasca: ").strip()
            if not titol:
                print("Cal un títol.")
                continue

            print("\nPrioritat: 1=Urgent  2=Important  3=Mitjana  4=Baixa  (Enter per ometre)")
            p_map = {"1": 0, "2": 1, "3": 5, "4": 9}
            prioritat = p_map.get(input("Prioritat: ").strip())

            data = input("Data límit (AAAA-MM-DD, Enter per ometre): ").strip() or None

            nova = crear_tasca(token, pla["id"], cubell["id"], titol, prioritat, data)
            print(f"\n✓ Tasca '{nova.get('title')}' creada correctament!")

        elif opcio == "4":
            tasques = obtenir_tasques_meves(token)
            pendents = [t for t in tasques if t.get("percentComplete", 0) < 100]
            if not pendents:
                print("\nNo tens tasques pendents.")
                continue

            mostrar_tasques(pendents)
            sel = input("Quina tasca completar? (número, 0 per cancel·lar): ").strip()
            try:
                idx = int(sel) - 1
                if not (0 <= idx < len(pendents)):
                    print("Cancel·lat.")
                    continue
                tasca = pendents[idx]
                completar_tasca(token, tasca["id"], tasca.get("@odata.etag", ""))
                print(f"\n✓ Tasca '{tasca.get('title')}' marcada com a completada!")
            except (ValueError, IndexError):
                print("Selecció no vàlida.")

        elif opcio == "0":
            print("Fins aviat!")
            break

        else:
            print("Opció no vàlida.")


def main():
    print("=" * 62)
    print("  INTEGRACIÓ AMB MICROSOFT PLANNER")
    print("=" * 62)

    client_id = obtenir_client_id()

    try:
        token = obtenir_token(client_id)
    except Exception as e:
        print(f"\nError d'autenticació: {e}")
        return

    perfil = obtenir_perfil(token)
    nom = perfil.get("displayName") or perfil.get("userPrincipalName", "Usuari")
    print(f"\nConnectat com: {nom} ✓")

    menu_principal(token)


if __name__ == "__main__":
    main()
