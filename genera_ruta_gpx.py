import math
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

def move_point(lat, lon, distance_m, bearing_deg):
    R = 6371000.0
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    d = distance_m / R
    phi2 = math.asin(math.sin(phi1)*math.cos(d) + math.cos(phi1)*math.sin(d)*math.cos(theta))
    lam2 = lam1 + math.atan2(math.sin(theta)*math.sin(d)*math.cos(phi1),
                               math.cos(d) - math.sin(phi1)*math.sin(phi2))
    return math.degrees(phi2), math.degrees(lam2)

def distance_between(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def interpolate_segment(p1, p2, steps):
    """Retorna punts interpolats entre p1 i p2 (inclou p2, exclou p1)."""
    lat1, lon1, ele1 = p1
    lat2, lon2, ele2 = p2
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        lat = lat1 + t * (lat2 - lat1)
        lon = lon1 + t * (lon2 - lon1)
        ele = ele1 + t * (ele2 - ele1)
        pts.append((lat, lon, round(ele, 1)))
    return pts

def generate_route():
    # Punt de partida: aparcament Sant Marçal, Montseny
    # Ruta: pujada al Turó de l'Home (~1706m) i volta
    segments = [
        # (bearing, dist_m, ele_final)  — definim keypoints de la ruta
        # Pujada (~7.5 km, +700m)
        (25, 1000,  985),   # camí inicial suau
        (15,  900, 1065),   # arrenca la pujada
        (30, 1200, 1185),   # pujada constant
        (20,  900, 1285),   # tram més vertical
        (10,  700, 1375),   # cresta
        (35, 1100, 1465),   # travessa de cresta
        (15,  700, 1545),   # últim repte
        (25,  600, 1610),   # zona de cim
        (5,   400, 1620),   # al cim (~1620m)
        # Descens diferent (~7.5 km, -700m)
        (200,  700, 1540),  # inici baixada W
        (210,  900, 1440),  # baixada ràpida
        (195, 1050, 1330),  # travessa bosc
        (220,  900, 1230),  # soleia
        (205, 1050, 1120),  # vall
        (215,  900, 1030),  # fons de vall
        (190,  700,  980),  # camí de retorn
        (185,  900,  930),  # últims metres
        (175,  500,  920),  # tancament del loop
    ]

    lat, lon, ele = 41.7834, 2.4021, 920.0
    keypoints = [(lat, lon, ele)]

    for bearing, dist, ele_final in segments:
        lat, lon = move_point(lat, lon, dist, bearing)
        keypoints.append((lat, lon, float(ele_final)))

    # Interpolar punts cada ~50m per tenir una traça densa
    track = [keypoints[0]]
    for i in range(len(keypoints) - 1):
        p1 = keypoints[i]
        p2 = keypoints[i + 1]
        seg_dist = distance_between(p1[0], p1[1], p2[0], p2[1])
        steps = max(3, int(seg_dist / 50))
        track.extend(interpolate_segment(p1, p2, steps))

    # Calcular distància i desnivell reals
    total_dist = 0
    total_up = 0
    for i in range(1, len(track)):
        total_dist += distance_between(track[i-1][0], track[i-1][1], track[i][0], track[i][1])
        diff = track[i][2] - track[i-1][2]
        if diff > 0:
            total_up += diff

    print(f"Ruta generada: {total_dist/1000:.2f} km | D+ {total_up:.0f} m | {len(track)} punts")

    # Construir GPX
    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "Strava API Assistant",
        "xmlns": "http://www.topografix.com/GPX/1/1",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd",
    })

    metadata = ET.SubElement(gpx, "metadata")
    ET.SubElement(metadata, "name").text = "Ruta Montseny - Turó de l'Home 15km 700D+"
    ET.SubElement(metadata, "desc").text = "Circular des de Sant Marçal fins al Turó de l'Home. 15km aprox, 700m D+."
    ET.SubElement(metadata, "time").text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = "Montseny - Turó de l'Home"
    ET.SubElement(trk, "type").text = "trail running"
    trkseg = ET.SubElement(trk, "trkseg")

    for lat, lon, ele in track:
        trkpt = ET.SubElement(trkseg, "trkpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})
        ET.SubElement(trkpt, "ele").text = f"{ele:.1f}"

    # Formatar XML amb indentació
    raw = ET.tostring(gpx, encoding="unicode")
    reparsed = minidom.parseString(raw)
    pretty = reparsed.toprettyxml(indent="  ", encoding="UTF-8")

    filename = "ruta_montseny_15km_700d.gpx"
    with open(filename, "wb") as f:
        f.write(pretty)

    print(f"Fitxer guardat: {filename}")
    print("\nPer importar a Strava:")
    print("  1. Ves a https://www.strava.com/routes/new")
    print("  2. Clica 'Import a Route' o 'Upload GPX'")
    print("  3. Selecciona el fitxer:", filename)

if __name__ == "__main__":
    generate_route()
