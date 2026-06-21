import os
import json
import time
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback"
TOKEN_FILE = "strava_token.json"

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


class CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Autoritzaci\xc3\xb3 completada! Pots tancar aquesta finestra.</h2></body></html>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error en l'autoritzaci\xc3\xb3")

    def log_message(self, format, *args):
        pass


def save_token(token_data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        return json.load(f)


def refresh_token(token_data):
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": token_data["refresh_token"],
    })
    resp.raise_for_status()
    new_token = resp.json()
    save_token(new_token)
    return new_token


def get_valid_token():
    token_data = load_token()
    if token_data:
        if token_data.get("expires_at", 0) > time.time() + 60:
            return token_data
        print("Token expirat, renovant...")
        return refresh_token(token_data)
    return authorize()


def authorize():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError(
            "Falta STRAVA_CLIENT_ID o STRAVA_CLIENT_SECRET al fitxer .env\n"
            "Registra la teva app a: https://www.strava.com/settings/api"
        )

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,read_all,activity:read_all,profile:read_all",
    }
    auth_url = f"{STRAVA_AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"\nObrint el navegador per autoritzar Strava...")
    print(f"Si no s'obre automàticament, ves a:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    print("Esperant autorització...")
    server.handle_request()

    code = CallbackHandler.auth_code
    if not code:
        raise RuntimeError("No s'ha rebut codi d'autorització")

    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    token_data = resp.json()
    save_token(token_data)
    print("Autorització completada i token desat!\n")
    return token_data


def api_get(endpoint, params=None):
    token = get_valid_token()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = requests.get(f"{STRAVA_API_BASE}{endpoint}", headers=headers, params=params or {})
    resp.raise_for_status()
    return resp.json()


def get_athlete():
    return api_get("/athlete")


def get_activities(per_page=10, page=1):
    return api_get("/athlete/activities", {"per_page": per_page, "page": page})


def get_activity(activity_id):
    return api_get(f"/activities/{activity_id}")


def get_stats(athlete_id):
    return api_get(f"/athletes/{athlete_id}/stats")


def get_routes(athlete_id, per_page=20, page=1):
    return api_get(f"/athletes/{athlete_id}/routes", {"per_page": per_page, "page": page})


def get_route(route_id):
    return api_get(f"/routes/{route_id}")


def export_route_gpx(route_id, filename=None):
    token = get_valid_token()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = requests.get(f"{STRAVA_API_BASE}/routes/{route_id}/export_gpx", headers=headers)
    resp.raise_for_status()
    if not filename:
        filename = f"ruta_{route_id}.gpx"
    with open(filename, "wb") as f:
        f.write(resp.content)
    return filename


def create_route(name, description, athlete_id, route_type, sub_type, waypoints=None, private=True, estimated_moving_time=None):
    token = get_valid_token()
    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Content-Type": "application/json",
    }
    data = {
        "name": name,
        "description": description,
        "athlete_id": athlete_id,
        "type": route_type,
        "sub_type": sub_type,
        "private": private,
    }
    if estimated_moving_time:
        data["estimated_moving_time"] = estimated_moving_time
    resp = requests.post(f"{STRAVA_API_BASE}/routes", headers=headers, json=data)
    resp.raise_for_status()
    return resp.json()


def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def format_pace(meters, seconds, sport_type):
    if meters <= 0 or seconds <= 0:
        return "N/A"
    if sport_type in ("Run", "VirtualRun", "TrailRun"):
        pace_sec_per_km = seconds / (meters / 1000)
        m = int(pace_sec_per_km) // 60
        s = int(pace_sec_per_km) % 60
        return f"{m}:{s:02d} /km"
    km_h = (meters / 1000) / (seconds / 3600)
    return f"{km_h:.1f} km/h"


ROUTE_TYPES = {1: "Ciclisme", 2: "Carrera"}
ROUTE_SUB_TYPES = {1: "Carretera", 2: "MTB", 3: "Ciclocròs", 4: "Trail", 5: "Mixt"}


def print_route(route):
    print(f"\n{'─'*50}")
    print(f"  {route['name']}")
    print(f"  ID:         {route['id_str'] if 'id_str' in route else route['id']}")
    t = ROUTE_TYPES.get(route.get("type"), "Desconegut")
    st = ROUTE_SUB_TYPES.get(route.get("sub_type"), "")
    print(f"  Tipus:      {t}{' / ' + st if st else ''}")
    if route.get("distance"):
        print(f"  Distància:  {route['distance']/1000:.2f} km")
    if route.get("elevation_gain"):
        print(f"  Desnivell:  {route['elevation_gain']:.0f} m")
    if route.get("estimated_moving_time"):
        print(f"  Temps est.: {format_duration(route['estimated_moving_time'])}")
    if route.get("description"):
        print(f"  Descripció: {route['description']}")
    if route.get("private"):
        print(f"  Privada:    Sí")
    if route.get("starred"):
        print(f"  Destacada:  Sí")


def print_activity(act):
    date = datetime.fromisoformat(act["start_date_local"].replace("Z", ""))
    print(f"\n{'─'*50}")
    print(f"  {act['name']}")
    print(f"  Tipus:      {act['sport_type']}")
    print(f"  Data:       {date.strftime('%d/%m/%Y %H:%M')}")
    print(f"  Distància:  {act['distance']/1000:.2f} km")
    print(f"  Durada:     {format_duration(act['moving_time'])}")
    print(f"  Ritme:      {format_pace(act['distance'], act['moving_time'], act['sport_type'])}")
    if act.get("total_elevation_gain"):
        print(f"  Desnivell:  {act['total_elevation_gain']:.0f} m")
    if act.get("average_heartrate"):
        print(f"  FC mitja:   {act['average_heartrate']:.0f} bpm")
    if act.get("max_heartrate"):
        print(f"  FC màxima:  {act['max_heartrate']:.0f} bpm")
    if act.get("kudos_count"):
        print(f"  Kudos:      {act['kudos_count']}")


def main():
    print("=" * 50)
    print("  STRAVA API - ASSISTENT D'ACTIVITATS")
    print("=" * 50)

    athlete = get_athlete()
    print(f"\nHola, {athlete['firstname']} {athlete['lastname']}!")
    print(f"Followers: {athlete.get('follower_count', 0)} | Following: {athlete.get('friend_count', 0)}")

    while True:
        print("\n\nQUÈ VOLS FER?")
        print("  1. Veure últimes activitats")
        print("  2. Veure estadístiques generals")
        print("  3. Veure detalls d'una activitat")
        print("  4. Veure les meves rutes")
        print("  5. Veure detalls d'una ruta")
        print("  6. Exportar ruta com a GPX")
        print("  7. Crear nova ruta")
        print("  8. Sortir")
        opcio = input("\nOpció: ").strip()

        if opcio == "1":
            n = input("Quantes activitats? (per defecte 10): ").strip()
            n = int(n) if n.isdigit() else 10
            print(f"\nCarregant les últimes {n} activitats...")
            activities = get_activities(per_page=n)
            if not activities:
                print("No s'han trobat activitats.")
            for act in activities:
                print_activity(act)
            print(f"\n{'─'*50}")

        elif opcio == "2":
            stats = get_stats(athlete["id"])
            print("\n--- ESTADÍSTIQUES TOTALS ---")
            for key, label in [
                ("all_run_totals", "Carrera total"),
                ("all_ride_totals", "Ciclisme total"),
                ("all_swim_totals", "Natació total"),
            ]:
                s = stats.get(key, {})
                if s.get("count", 0) > 0:
                    print(f"\n{label}:")
                    print(f"  Activitats: {s['count']}")
                    print(f"  Distància:  {s['distance']/1000:.1f} km")
                    print(f"  Temps:      {format_duration(s['moving_time'])}")

        elif opcio == "3":
            aid = input("ID de l'activitat: ").strip()
            if aid.isdigit():
                act = get_activity(int(aid))
                print_activity(act)
                if act.get("description"):
                    print(f"  Descripció: {act['description']}")
                if act.get("splits_metric"):
                    print(f"\n  Kilòmetres:")
                    for i, split in enumerate(act["splits_metric"], 1):
                        pace = format_pace(split["distance"], split["moving_time"], act["sport_type"])
                        print(f"    km {i}: {pace}  | {split['distance']:.0f}m")
            else:
                print("ID no vàlid.")

        elif opcio == "4":
            print("\nCarregant les teves rutes...")
            routes = get_routes(athlete["id"])
            if not routes:
                print("No s'han trobat rutes. Crea'n una des de Strava web o amb l'opció 7.")
            else:
                print(f"\nTotal: {len(routes)} rutes")
                for route in routes:
                    print_route(route)
            print(f"\n{'─'*50}")

        elif opcio == "5":
            rid = input("ID de la ruta: ").strip()
            if rid.isdigit():
                route = get_route(int(rid))
                print_route(route)
            else:
                print("ID no vàlid.")

        elif opcio == "6":
            rid = input("ID de la ruta: ").strip()
            if rid.isdigit():
                fname = input("Nom del fitxer (deixa buit per defecte): ").strip() or None
                path = export_route_gpx(int(rid), fname)
                print(f"\nRuta exportada a: {path}")
            else:
                print("ID no vàlid.")

        elif opcio == "7":
            print("\n--- CREAR NOVA RUTA ---")
            print("Nota: La creació de rutes via API requereix que Strava aprovi\n"
                  "l'accés avançat a la teva app. Per crear rutes amb recorregut\n"
                  "específic, usa strava.com/routes/new o una app GPS.\n")
            nom = input("Nom de la ruta: ").strip()
            if not nom:
                print("Cal un nom.")
                continue
            desc = input("Descripció (opcional): ").strip()
            print("Tipus: 1=Ciclisme  2=Carrera")
            tipus = input("Tipus [1/2]: ").strip()
            tipus = int(tipus) if tipus in ("1", "2") else 2
            print("Subtipus: 1=Carretera  2=MTB  3=Ciclocròs  4=Trail  5=Mixt")
            subtipus = input("Subtipus [1-5]: ").strip()
            subtipus = int(subtipus) if subtipus in ("1", "2", "3", "4", "5") else 1
            privada = input("Privada? [S/n]: ").strip().lower() != "n"
            try:
                route = create_route(nom, desc, athlete["id"], tipus, subtipus, private=privada)
                print(f"\nRuta creada!")
                print_route(route)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    print("\nError 403: La teva app de Strava no té permís per crear rutes.")
                    print("Per tenir aquest accés, cal sol·licitar-ho a:")
                    print("https://www.strava.com/settings/api -> 'Request Extended Access'")
                else:
                    print(f"\nError: {e.response.status_code} - {e.response.text}")

        elif opcio == "8":
            print("\nFins aviat!")
            break
        else:
            print("Opció no vàlida.")


if __name__ == "__main__":
    main()
