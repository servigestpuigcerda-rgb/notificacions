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
        "scope": "read,activity:read_all,profile:read_all",
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
        print("  4. Sortir")
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
            print("\nFins aviat!")
            break
        else:
            print("Opció no vàlida.")


if __name__ == "__main__":
    main()
