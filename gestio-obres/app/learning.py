"""Aprenentatge a partir de l'historial.

No és una caixa negra: tot surt de les feines ja fetes.
- Desviació d'hores i de material entre el pressupostat i el real, per tipus de feina.
- Partida habitual de cada proveïdor (per imputar despeses automàticament).
- Pressupostos semblants (per paraules clau) que serveixen d'exemple a la IA.
- Revisió d'un pressupost nou: errors evidents i avís si anem curts d'hores o de material.
"""
import re
import unicodedata

from . import calc, db

MIN_FEINES_FIABLE = 2
STOPWORDS = set("""a al als amb de del dels el els en es i la les o per pel pels que un una uns unes
d l s n m t es se lo fer fem posar canviar nou nova nous noves cal""".split())


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def paraules(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", _norm(text)) if w not in STOPWORDS}


# ---------------------------------------------------------------- desviacions

def _feines_tancades(tipus: str | None = None):
    sql = ("SELECT * FROM feines WHERE estat IN ('acabada','tancada') "
           "AND EXISTS (SELECT 1 FROM pressupostos p WHERE p.feina_id = feines.id AND p.estat = 'acceptat')")
    params = ()
    if tipus:
        sql += " AND lower(tipus) = lower(?)"
        params = (tipus,)
    return db.rows(sql, params)


def desviacions(tipus: str | None = None) -> dict:
    """Ràtio real/pressupostat d'hores i de cost de material de les feines acabades."""
    mostres = []
    for f in _feines_tancades(tipus):
        r = calc.resum_feina(f["id"])
        mat_prev = sum(p["previst"] for p in r["partides"] if not _es_ma_obra(p["partida_id"]))
        mat_real = sum(p["real"] for p in r["partides"] if not _es_ma_obra(p["partida_id"]))
        mostres.append({
            "feina_id": f["id"], "codi": f["codi"], "tipus": f["tipus"],
            "hores_previstes": r["hores_previstes"], "hores_reals": r["hores_reals"],
            "ratio_hores": (r["hores_reals"] / r["hores_previstes"]) if r["hores_previstes"] else None,
            "ratio_material": (mat_real / mat_prev) if mat_prev else None,
            "marge_previst_pct": r["marge_previst_pct"],
            "marge_real_pct": calc.r2((r["contractat"] - r["cost_real"]) / r["contractat"] * 100) if r["contractat"] else None,
        })

    def mitjana(clau):
        vals = [m[clau] for m in mostres if m[clau] is not None]
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

    rh, nh = mitjana("ratio_hores")
    rm, nm = mitjana("ratio_material")
    mr, _ = mitjana("marge_real_pct")
    return {
        "tipus": tipus, "feines": len(mostres),
        "ratio_hores": calc.r2(rh) if rh else None, "n_hores": nh,
        "ratio_material": calc.r2(rm) if rm else None, "n_material": nm,
        "marge_real_mitja": calc.r2(mr) if mr is not None else None,
        "mostres": mostres,
    }


def _es_ma_obra(partida_id) -> bool:
    if not partida_id:
        return False
    return db.scalar("SELECT tipus FROM partides WHERE id = ?", (partida_id,)) == "ma_obra"


def resum_aprenentatge() -> dict:
    tipus = [r["tipus"] for r in db.rows("SELECT DISTINCT tipus FROM feines WHERE tipus IS NOT NULL AND tipus <> ''")]
    per_tipus = []
    for t in tipus:
        d = desviacions(t)
        if d["feines"]:
            d.pop("mostres")
            per_tipus.append(d)
    general = desviacions()
    general.pop("mostres")
    proveidors = db.rows("SELECT a.proveidor, a.usos, p.nom AS partida FROM aprenentatge_proveidors a "
                         "LEFT JOIN partides p ON p.id = a.partida_id ORDER BY a.usos DESC LIMIT 50")
    return {"general": general, "per_tipus": per_tipus, "proveidors": proveidors}


# ---------------------------------------------------------------- proveïdors

def aprendre_proveidor(proveidor: str | None, partida_id: int | None):
    if not proveidor or not partida_id:
        return
    clau = _norm(proveidor).strip()
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO aprenentatge_proveidors(proveidor, partida_id, usos, updated_at) VALUES (?,?,1,?) "
            "ON CONFLICT(proveidor) DO UPDATE SET partida_id = excluded.partida_id, usos = usos + 1, "
            "updated_at = excluded.updated_at", (clau, partida_id, db.now()))


def partida_proveidor(proveidor: str | None):
    if not proveidor:
        return None
    return db.scalar("SELECT partida_id FROM aprenentatge_proveidors WHERE proveidor = ?", (_norm(proveidor).strip(),))


def feina_probable_per_despesa() -> list:
    """Feines obertes ordenades per activitat recent (on és més probable imputar)."""
    return db.rows(
        "SELECT f.id, f.codi, f.nom, f.tipus, f.adreca, "
        "MAX(COALESCE(h.data,''), COALESCE(d.data,''), f.created_at) AS activitat "
        "FROM feines f LEFT JOIN hores h ON h.feina_id = f.id LEFT JOIN despeses d ON d.feina_id = f.id "
        "WHERE f.estat IN ('pressupost','acceptada','en_curs') GROUP BY f.id ORDER BY activitat DESC LIMIT 15")


# ---------------------------------------------------------------- semblants

def pressupostos_semblants(text: str, tipus: str | None = None, limit: int = 4, excloure_id: int | None = None) -> list:
    """Pressupostos acceptats amb més paraules en comú (exemples per a la IA i referència)."""
    objectiu = paraules(text) | paraules(tipus or "")
    if not objectiu:
        return []
    candidats = []
    for p in db.rows("SELECT p.*, f.tipus AS feina_tipus, f.nom AS feina_nom, f.estat AS feina_estat FROM pressupostos p "
                     "JOIN feines f ON f.id = p.feina_id WHERE p.estat IN ('acceptat','enviat') AND p.id IS NOT ?",
                     (excloure_id,)):
        linies = db.rows("SELECT descripcio FROM linies_pressupost WHERE pressupost_id = ?", (p["id"],))
        bossa = paraules(" ".join([p["titol"] or "", p["feina_nom"] or "", p["text_origen"] or ""] +
                                  [l["descripcio"] for l in linies]))
        comunes = objectiu & bossa
        punts = len(comunes) / (len(objectiu) ** 0.5 * max(len(bossa), 1) ** 0.5)
        if tipus and p["feina_tipus"] and _norm(tipus) == _norm(p["feina_tipus"]):
            punts += 0.15
        if p["estat"] == "acceptat":
            punts += 0.05
        if comunes:
            candidats.append((punts, p))
    candidats.sort(key=lambda x: -x[0])
    res = []
    for punts, p in candidats[:limit]:
        t = calc.totals_pressupost(p["id"])
        real = calc.resum_feina(p["feina_id"]) if p["feina_estat"] in ("acabada", "tancada") else None
        res.append({
            "id": p["id"], "numero": p["numero"], "titol": p["titol"] or p["feina_nom"], "tipus": p["feina_tipus"],
            "similitud": round(punts, 3), "base": t["base"], "hores": t["hores"], "cost": t["cost"],
            "hores_reals": real["hores_reals"] if real else None,
            "cost_real": real["cost_real"] if real else None,
            "linies": [{k: l[k] for k in ("descripcio", "quantitat", "unitat", "cost_unitari", "preu_unitari")}
                       for l in t["linies"]],
        })
    return res


# ---------------------------------------------------------------- revisió

def revisar_pressupost(pressupost_id: int) -> dict:
    """Detecta errors i compara amb l'historial: anem curts d'hores o de material?"""
    p = db.row("SELECT p.*, f.tipus AS feina_tipus, f.nom AS feina_nom FROM pressupostos p "
               "JOIN feines f ON f.id = p.feina_id WHERE p.id = ?", (pressupost_id,))
    t = calc.totals_pressupost(pressupost_id)
    pm = calc.partides_map()
    marge_min = db.setting_float("marge_defecte", 20) / 2
    avisos = []  # {nivell: error|avis|info, text}

    def add(nivell, text):
        avisos.append({"nivell": nivell, "text": text})

    if not t["linies"]:
        add("error", "El pressupost no té cap línia.")
    for i, l in enumerate(t["linies"], 1):
        nom = f"Línia {i} «{l['descripcio'][:40]}»"
        if l["quantitat"] <= 0:
            add("error", f"{nom}: quantitat zero o negativa.")
        if l["preu_unitari"] <= 0:
            add("error", f"{nom}: sense preu.")
        elif l["cost_unitari"] and l["preu_unitari"] * (1 - l["descompte_pct"] / 100) < l["cost_unitari"]:
            add("error", f"{nom}: es ven per sota de cost.")
        elif l["cost_unitari"] and l["preu_unitari"]:
            m = (l["preu_unitari"] * (1 - l["descompte_pct"] / 100) - l["cost_unitari"]) / l["preu_unitari"] * 100
            if m < marge_min:
                add("avis", f"{nom}: marge molt baix ({m:.0f}%).")
        if not l["cost_unitari"]:
            add("avis", f"{nom}: sense cost; no es podrà controlar el benefici.")
        if l["descompte_pct"] > 25:
            add("avis", f"{nom}: descompte alt ({l['descompte_pct']:.0f}%).")
        if not l["partida_id"]:
            add("info", f"{nom}: sense partida assignada.")
    tipus_linies = {(pm.get(l["partida_id"]) or {}).get("tipus") for l in t["linies"]}
    if t["linies"] and "ma_obra" not in tipus_linies:
        add("avis", "No hi ha cap línia de mà d'obra. És correcte?")
    if p["descompte_pct"] > 15:
        add("avis", f"Descompte global alt ({p['descompte_pct']:.0f}%).")
    if t["base"] and t["marge_pct"] < marge_min:
        add("avis", f"Marge global baix: {t['marge_pct']:.1f}%.")

    # Duplicats
    vistos = {}
    for l in t["linies"]:
        k = _norm(l["descripcio"]).strip()
        if k in vistos:
            add("avis", f"Línia repetida: «{l['descripcio'][:40]}».")
        vistos[k] = True

    # Historial
    hist = desviacions(p["feina_tipus"]) if p["feina_tipus"] else {"feines": 0}
    origen = f"feines de tipus «{p['feina_tipus']}»"
    if hist.get("feines", 0) < MIN_FEINES_FIABLE:
        hist = desviacions()
        origen = "totes les feines acabades"
    historial = {k: v for k, v in hist.items() if k != "mostres"}
    historial["origen"] = origen
    if hist.get("feines", 0) >= MIN_FEINES_FIABLE:
        rh = hist.get("ratio_hores")
        if rh and t["hores"] and rh > 1.05:
            falten = t["hores"] * rh - t["hores"]
            add("avis", f"Anem curts d'hores: a les {origen} les hores reals han estat un {(rh - 1) * 100:.0f}% "
                        f"més de les pressupostades. Caldrien ~{t['hores'] * rh:.1f} h (+{falten:.1f} h).")
        elif rh and t["hores"] and rh < 0.9:
            add("info", f"Historial: normalment fem un {(1 - rh) * 100:.0f}% menys d'hores de les pressupostades.")
        rm = hist.get("ratio_material")
        mat = sum(pp["cost"] for pp in t["per_partida"] if pp["tipus"] != "ma_obra")
        if rm and mat and rm > 1.05:
            add("avis", f"Anem curts de material: a les {origen} el material real ha costat un {(rm - 1) * 100:.0f}% "
                        f"més del previst. Cost previst {mat:.0f} € → probable {mat * rm:.0f} €.")
        if hist.get("marge_real_mitja") is not None and t["base"]:
            add("info", f"Marge real mitjà de l'historial: {hist['marge_real_mitja']:.1f}% (aquest pressupost: {t['marge_pct']:.1f}%).")
    else:
        add("info", "Encara no hi ha prou feines acabades per comparar amb l'historial.")

    # Comparació amb semblants
    text = " ".join([p["titol"] or "", p["feina_nom"] or ""] + [l["descripcio"] for l in t["linies"]])
    semblants = pressupostos_semblants(text, p["feina_tipus"], limit=3, excloure_id=pressupost_id)
    for s in semblants:
        if s["hores_reals"] and t["hores"] and s["similitud"] > 0.25 and s["hores_reals"] > t["hores"] * 1.3:
            add("avis", f"La feina semblant {s['numero']} ({s['titol']}) va necessitar {s['hores_reals']:.0f} h reals "
                        f"i aquí n'hi ha {t['hores']:.0f}.")

    return {"avisos": avisos, "historial": historial, "semblants": semblants,
            "totals": {k: t[k] for k in ("base", "cost", "benefici", "marge_pct", "hores", "total")}}
