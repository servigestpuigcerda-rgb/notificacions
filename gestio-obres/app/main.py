"""Gestió d'obres: pressupostos, albarans, costos, facturació i comunicació amb el client."""
import json
import mimetypes
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ai, auth, calc, db, learning, printing
from .auth import admin, usuari_actual

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_UPLOAD = 15 * 1024 * 1024
TIPUS_DOCS = ("tiquet", "factura_proveidor", "albara_proveidor", "foto", "material", "pressupost", "factura", "albara", "altres")



@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="Gestió d'obres", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
def _integrity_error(_, exc):
    return JSONResponse({"detail": "Dades incompletes o duplicades."}, status_code=400)


@app.exception_handler(ai.IAError)
def _ia_error(_, exc: ai.IAError):
    return JSONResponse({"detail": str(exc)}, status_code=422)


# ------------------------------------------------------------------ utilitats

NULLABLES = {"marge_pct", "preu", "iva_pct", "base", "total", "iva_import", "cost_hora", "preu_hora", "ia_confianca"}


def pick(data: dict, camps: dict) -> dict:
    """Agafa només els camps permesos i en converteix el tipus."""
    out = {}
    for k, tipus in camps.items():
        if k not in data:
            continue
        v = data[k]
        if v in ("", None):
            if tipus is bool:
                out[k] = 0
            elif tipus is float and k not in NULLABLES:
                out[k] = 0
            else:
                out[k] = None
            continue
        try:
            if tipus is bool:
                out[k] = 1 if v in (True, 1, "1", "true", "on") else 0
            elif tipus is float:
                out[k] = float(str(v).replace(",", "."))
            elif tipus is int:
                out[k] = int(v)
            else:
                out[k] = str(v).strip()
        except (TypeError, ValueError):
            raise HTTPException(400, f"Valor no vàlid per a «{k}».")
    return out


def cal(obj, msg="No trobat."):
    if not obj:
        raise HTTPException(404, msg)
    return obj


def feina_o_404(fid: int) -> dict:
    return cal(db.row("SELECT * FROM feines WHERE id = ?", (fid,)), "Feina no trobada.")


def missatge(feina_id: int, text: str, tipus="missatge", autor="sistema", intern=False, ref_tipus=None, ref_id=None):
    db.insert("missatges", {"feina_id": feina_id, "autor": autor, "tipus": tipus, "text": text,
                            "intern": 1 if intern else 0, "ref_tipus": ref_tipus, "ref_id": ref_id,
                            "llegit": 0 if autor == "client" else 1, "created_at": db.now()})


def seguent_codi(prefix: str, taula: str, camp: str) -> str:
    any_ = date.today().year
    pref = f"{prefix}{any_}-"
    n = 0
    for (v,) in db.connect().execute(f"SELECT {camp} FROM {taula} WHERE {camp} LIKE ?", (pref + "%",)):
        m = re.match(r"(\d+)", v[len(pref):])
        if m:
            n = max(n, int(m.group(1)))
    return f"{pref}{n + 1:04d}" if prefix else f"{pref}{n + 1:03d}"


def guarda_fitxer(contingut: bytes, nom: str, feina_id: int | None, tipus: str, mime: str | None) -> int:
    carpeta = "general"
    if feina_id:
        f = db.row("SELECT codi FROM feines WHERE id = ?", (feina_id,))
        carpeta = f["codi"] if f else "general"
    ext = Path(nom).suffix.lower() or mimetypes.guess_extension(mime or "") or ".bin"
    rel = Path(carpeta) / f"{db.today()}_{tipus}_{secrets.token_hex(4)}{ext}"
    desti = db.DOCS_DIR / rel
    desti.parent.mkdir(parents=True, exist_ok=True)
    desti.write_bytes(contingut)
    return db.insert("documents", {"feina_id": feina_id, "tipus": tipus, "nom": nom, "fitxer": str(rel),
                                   "mime": mime or mimetypes.guess_type(nom)[0], "mida": len(contingut),
                                   "created_at": db.now()})


# ---------------------------------------------------------------- sessions

@app.get("/api/estat")
def estat(request: Request):
    try:
        u = usuari_actual(request)
    except HTTPException:
        u = None
    return {"configurat": auth.hi_ha_usuaris(), "usuari": u, "ia": ai.disponible(),
            "empresa": db.setting("empresa_nom", "")}


@app.post("/api/setup")
def setup(response: Response, data: dict = Body(...)):
    if auth.hi_ha_usuaris():
        raise HTTPException(400, "L'aplicació ja està configurada.")
    auth.crear_usuari(data.get("nom") or "Administrador", data.get("usuari") or "admin", data.get("password"), "admin",
                      db.setting_float("cost_hora_defecte", 25), db.setting_float("preu_hora_defecte", 38))
    if data.get("empresa_nom"):
        db.set_settings({"empresa_nom": data["empresa_nom"]})
    return login(response, {"usuari": data.get("usuari") or "admin", "password": data.get("password")})


@app.post("/api/login")
def login(response: Response, data: dict = Body(...)):
    token = auth.login(data.get("usuari", ""), data.get("password", ""))
    if not token:
        raise HTTPException(401, "Usuari o contrasenya incorrectes.")
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 90)
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    if request.cookies.get(auth.COOKIE):
        auth.logout(request.cookies[auth.COOKIE])
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


# ---------------------------------------------------------- configuració

CAMPS_CONFIG = set(db.SETTINGS_INICIALS)


@app.get("/api/config")
def get_config(u=Depends(usuari_actual)):
    return {"settings": db.settings(), "partides": db.rows("SELECT * FROM partides ORDER BY ordre, id"),
            "usuaris": db.rows("SELECT id, nom, usuari, rol, cost_hora, preu_hora, actiu FROM usuaris ORDER BY nom"),
            "ia": ai.disponible()}


@app.put("/api/config")
def put_config(data: dict = Body(...), u=Depends(admin)):
    db.set_settings({k: v for k, v in data.items() if k in CAMPS_CONFIG})
    return get_config(u)


@app.post("/api/usuaris")
def post_usuari(data: dict = Body(...), u=Depends(admin)):
    uid = auth.crear_usuari(data.get("nom"), data.get("usuari"), data.get("password"), data.get("rol", "treballador"),
                            float(data.get("cost_hora") or 0), float(data.get("preu_hora") or 0))
    return {"id": uid}


@app.put("/api/usuaris/{uid}")
def put_usuari(uid: int, data: dict = Body(...), u=Depends(admin)):
    d = pick(data, {"nom": str, "rol": str, "cost_hora": float, "preu_hora": float, "actiu": bool})
    if data.get("password"):
        if len(data["password"]) < 8:
            raise HTTPException(400, "La contrasenya ha de tenir com a mínim 8 caràcters.")
        d["password_hash"] = auth.hash_password(data["password"])
    db.update("usuaris", uid, d)
    return {"ok": True}


@app.post("/api/partides")
def post_partida(data: dict = Body(...), u=Depends(admin)):
    d = pick(data, {"nom": str, "tipus": str, "ordre": int})
    if not d.get("nom"):
        raise HTTPException(400, "Cal un nom.")
    return {"id": db.insert("partides", d)}


@app.put("/api/partides/{pid}")
def put_partida(pid: int, data: dict = Body(...), u=Depends(admin)):
    db.update("partides", pid, pick(data, {"nom": str, "tipus": str, "ordre": int}))
    return {"ok": True}


# ------------------------------------------------------------------ clients

CAMPS_CLIENT = {"nom": str, "nif": str, "email": str, "telefon": str, "adreca": str, "notes": str}


@app.get("/api/clients")
def get_clients(q: str = "", u=Depends(usuari_actual)):
    return db.rows("SELECT c.*, (SELECT COUNT(*) FROM feines f WHERE f.client_id = c.id) AS feines FROM clients c "
                   "WHERE c.nom LIKE ? OR c.nif LIKE ? OR c.telefon LIKE ? ORDER BY c.nom", (f"%{q}%",) * 3)


@app.post("/api/clients")
def post_client(data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, CAMPS_CLIENT)
    if not d.get("nom"):
        raise HTTPException(400, "Cal el nom del client.")
    d["created_at"] = db.now()
    return {"id": db.insert("clients", d)}


@app.put("/api/clients/{cid}")
def put_client(cid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    db.update("clients", cid, pick(data, CAMPS_CLIENT))
    return {"ok": True}


@app.delete("/api/clients/{cid}")
def del_client(cid: int, u=Depends(admin)):
    if db.scalar("SELECT COUNT(*) FROM feines WHERE client_id = ?", (cid,)) or \
            db.scalar("SELECT COUNT(*) FROM factures WHERE client_id = ?", (cid,)):
        raise HTTPException(400, "El client té feines o factures; no es pot esborrar.")
    db.delete("clients", cid)
    return {"ok": True}


# ----------------------------------------------------------------- articles

CAMPS_ARTICLE = {"codi": str, "nom": str, "unitat": str, "partida_id": int, "cost": float, "marge_pct": float,
                 "preu": float, "descompte_pct": float, "iva_pct": float, "proveidor": str, "notes": str, "actiu": bool}


def _article_out(a):
    a["preu_venda"] = calc.preu_article(a)
    a["preu_net"] = calc.r2(a["preu_venda"] * (1 - (a["descompte_pct"] or 0) / 100))
    return a


@app.get("/api/articles")
def get_articles(q: str = "", u=Depends(usuari_actual)):
    res = db.rows("SELECT * FROM articles WHERE actiu = 1 AND (nom LIKE ? OR codi LIKE ? OR proveidor LIKE ?) "
                  "ORDER BY nom LIMIT 500", (f"%{q}%",) * 3)
    return [_article_out(a) for a in res]


@app.post("/api/articles")
def post_article(data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, CAMPS_ARTICLE)
    if not d.get("nom"):
        raise HTTPException(400, "Cal el nom de l'article.")
    d.setdefault("cost", 0)
    d.setdefault("descompte_pct", 0)
    d["updated_at"] = db.now()
    return {"id": db.insert("articles", d)}


@app.put("/api/articles/{aid}")
def put_article(aid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, CAMPS_ARTICLE)
    d["updated_at"] = db.now()
    db.update("articles", aid, d)
    return {"ok": True}


@app.delete("/api/articles/{aid}")
def del_article(aid: int, u=Depends(usuari_actual)):
    db.update("articles", aid, {"actiu": 0})
    return {"ok": True}


@app.post("/api/articles/aplicar")
def aplicar_articles(data: dict = Body(...), u=Depends(admin)):
    """Aplica un marge o un descompte a diversos articles alhora (per ids o per partida)."""
    ids = [int(i) for i in data.get("ids") or []]
    if data.get("partida_id"):
        ids += [r["id"] for r in db.rows("SELECT id FROM articles WHERE partida_id = ? AND actiu = 1", (data["partida_id"],))]
    if not ids:
        raise HTTPException(400, "No hi ha cap article seleccionat.")
    canvis = {}
    if data.get("marge_pct") not in (None, ""):
        canvis["marge_pct"] = float(data["marge_pct"])
        canvis["preu"] = None
    if data.get("descompte_pct") not in (None, ""):
        canvis["descompte_pct"] = float(data["descompte_pct"])
    for i in set(ids):
        db.update("articles", i, {**canvis, "updated_at": db.now()})
    return {"actualitzats": len(set(ids))}


# ------------------------------------------------------------------- feines

CAMPS_FEINA = {"nom": str, "client_id": int, "adreca": str, "tipus": str, "estat": str, "mode_facturacio": str,
               "data_inici": str, "data_fi": str, "notes": str}


@app.get("/api/feines")
def get_feines(estat: str = "", q: str = "", u=Depends(usuari_actual)):
    sql = ("SELECT f.*, c.nom AS client_nom FROM feines f LEFT JOIN clients c ON c.id = f.client_id "
           "WHERE (f.nom LIKE ? OR f.codi LIKE ? OR c.nom LIKE ? OR f.adreca LIKE ?)")
    params = [f"%{q}%"] * 4
    if estat == "actives":
        sql += " AND f.estat IN ('pressupost','acceptada','en_curs','acabada')"
    elif estat:
        sql += " AND f.estat = ?"
        params.append(estat)
    feines = db.rows(sql + " ORDER BY f.created_at DESC", params)
    for f in feines:
        r = calc.resum_feina(f["id"])
        f["resum"] = {k: r[k] for k in ("contractat", "cost_previst", "cost_real", "facturat", "pendent_facturar",
                                        "pct_cost", "pct_facturat", "hores_reals", "hores_previstes", "benefici_projectat",
                                        "pendent_acceptar")}
        f["n_alertes"] = len(r["alertes"])
    return feines


@app.post("/api/feines")
def post_feina(data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, CAMPS_FEINA)
    if not d.get("nom"):
        raise HTTPException(400, "Cal un nom per a la feina.")
    if data.get("client_nou"):
        c = pick(data["client_nou"], CAMPS_CLIENT)
        if c.get("nom"):
            c["created_at"] = db.now()
            d["client_id"] = db.insert("clients", c)
    d.update({"codi": seguent_codi("", "feines", "codi"), "token": secrets.token_urlsafe(18),
              "created_at": db.now(), "estat": d.get("estat") or "pressupost",
              "mode_facturacio": d.get("mode_facturacio") or "pressupost"})
    fid = db.insert("feines", d)
    missatge(fid, f"S'ha obert la feina {d['codi']}: {d['nom']}.", "nota", intern=True)
    return {"id": fid, "codi": d["codi"]}


@app.get("/api/feines/{fid}")
def get_feina(fid: int, u=Depends(usuari_actual)):
    f = feina_o_404(fid)
    f["client"] = db.row("SELECT * FROM clients WHERE id = ?", (f["client_id"],)) if f["client_id"] else None
    f["resum"] = calc.resum_feina(fid)
    f["no_llegits"] = db.scalar("SELECT COUNT(*) FROM missatges WHERE feina_id = ? AND llegit = 0", (fid,))
    f["bloquejos"] = calc.bloquejos(fid)
    f["valoracio"] = db.row("SELECT COUNT(*) AS n, AVG(puntuacio) AS mitjana FROM valoracions WHERE feina_id = ?", (fid,))
    return f


@app.put("/api/feines/{fid}")
def put_feina(fid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    feina_o_404(fid)
    db.update("feines", fid, pick(data, CAMPS_FEINA))
    return {"ok": True}


@app.post("/api/feines/{fid}/tancar")
def tancar_feina(fid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    f = feina_o_404(fid)
    r = calc.resum_feina(fid)
    if r["pendent_facturar"] > 0.01 and not data.get("forcar"):
        raise HTTPException(400, f"Encara queden {printing.eur(r['pendent_facturar'])} per facturar. "
                                 "Factura-ho o confirma el tancament igualment.")
    db.update("feines", fid, {"estat": "tancada", "tancada_at": db.now(), "data_fi": f["data_fi"] or db.today()})
    missatge(fid, "Hem donat la feina per acabada i tancada. Gràcies per confiar en nosaltres! "
                  "Si detecteu qualsevol cosa, escriviu-nos per aquí.", "tancament", autor="empresa")
    missatge(fid, f"Tancament: contractat {printing.eur(r['contractat'])}, cost real {printing.eur(r['cost_real'])}, "
                  f"facturat {printing.eur(r['facturat'])}, resultat {printing.eur(r['facturat'] - r['cost_real'])}. "
                  f"Hores {r['hores_reals']} de {r['hores_previstes']} previstes.", "nota", intern=True)
    from .api2 import genera_analisi
    genera_analisi(fid)
    return {"ok": True}


# ------------------------------------------------------------- pressupostos

CAMPS_PRESSUPOST = {"titol": str, "data": str, "validesa_dies": int, "descompte_pct": float, "iva_pct": float,
                    "irpf_pct": float, "notes": str, "condicions": str, "text_origen": str}
CAMPS_LINIA = {"article_id": int, "partida_id": int, "descripcio": str, "quantitat": float, "unitat": str,
               "cost_unitari": float, "marge_pct": float, "preu_unitari": float, "descompte_pct": float,
               "referencia": str, "foto_document_id": int}


def _guarda_linies(pid: int, linies: list):
    with db.tx() as conn:
        conn.execute("DELETE FROM linies_pressupost WHERE pressupost_id = ?", (pid,))
        for i, l in enumerate(linies):
            d = pick(l, CAMPS_LINIA)
            if not d.get("descripcio"):
                continue
            d.setdefault("quantitat", 1)
            for k in ("cost_unitari", "preu_unitari", "descompte_pct", "marge_pct", "quantitat"):
                d[k] = d.get(k) or 0
            if not d["preu_unitari"] and d["cost_unitari"]:
                d["preu_unitari"] = calc.r2(d["cost_unitari"] * (1 + d["marge_pct"] / 100))
            if d["preu_unitari"] and d["cost_unitari"] and not l.get("marge_pct"):
                d["marge_pct"] = calc.r2((d["preu_unitari"] / d["cost_unitari"] - 1) * 100)
            d["unitat"] = d.get("unitat") or "u"
            d["pressupost_id"] = pid
            d["ordre"] = i
            cols = ", ".join(d)
            conn.execute(f"INSERT INTO linies_pressupost ({cols}) VALUES ({', '.join('?' for _ in d)})", tuple(d.values()))


@app.post("/api/feines/{fid}/pressupostos")
def post_pressupost(fid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    f = feina_o_404(fid)
    tipus = "extra" if data.get("tipus") == "extra" else "principal"
    d = pick(data, CAMPS_PRESSUPOST)
    numero = seguent_codi("P", "pressupostos", "numero")
    if tipus == "extra":
        numero += "-E"
    d.update({"feina_id": fid, "numero": numero, "tipus": tipus, "estat": "esborrany",
              "data": d.get("data") or db.today(), "created_at": db.now()})
    d.setdefault("iva_pct", db.setting_float("iva_defecte", 21))
    d.setdefault("irpf_pct", db.setting_float("irpf_defecte", 0))
    d.setdefault("validesa_dies", int(db.setting_float("validesa_pressupost", 30)))
    d.setdefault("descompte_pct", 0)
    d["condicions"] = d.get("condicions") or db.setting("condicions_pressupost", "")
    if data.get("tipus_feina") and not f["tipus"]:
        db.update("feines", fid, {"tipus": data["tipus_feina"]})
    pid = db.insert("pressupostos", d)
    _guarda_linies(pid, data.get("linies") or [])
    return {"id": pid, "numero": numero}


@app.get("/api/pressupostos/{pid}")
def get_pressupost(pid: int, u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    p["totals"] = calc.totals_pressupost(pid)
    p["feina"] = db.row("SELECT f.id, f.codi, f.nom, f.tipus, f.token, c.nom AS client_nom, c.telefon AS client_telefon, "
                        "c.email AS client_email FROM feines f LEFT JOIN clients c ON c.id = f.client_id WHERE f.id = ?",
                        (p["feina_id"],))
    return p


def _editable(p):
    if p["estat"] == "acceptat":
        raise HTTPException(400, "El pressupost ja està acceptat. Per a canvis, crea un pressupost «fora de pressupost».")


@app.put("/api/pressupostos/{pid}")
def put_pressupost(pid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    _editable(p)
    d = pick(data, CAMPS_PRESSUPOST)
    if p["estat"] in ("enviat", "rebutjat") and ("linies" in data or d):
        d["estat"] = "esborrany"
    db.update("pressupostos", pid, d)
    if "linies" in data:
        _guarda_linies(pid, data["linies"])
    return get_pressupost(pid, u)


@app.delete("/api/pressupostos/{pid}")
def del_pressupost(pid: int, u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    if p["estat"] != "esborrany":
        raise HTTPException(400, "Només es poden esborrar esborranys.")
    db.delete("pressupostos", pid)
    return {"ok": True}


@app.post("/api/pressupostos/{pid}/duplicar")
def duplicar_pressupost(pid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    linies = db.rows("SELECT * FROM linies_pressupost WHERE pressupost_id = ? ORDER BY ordre", (pid,))
    desti = int(data.get("feina_id") or p["feina_id"])
    nou = {k: p[k] for k in CAMPS_PRESSUPOST}
    nou.update({"titol": (p["titol"] or "") + (" (còpia)" if desti == p["feina_id"] else ""), "data": db.today(),
                "linies": linies, "tipus": p["tipus"]})
    return post_pressupost(desti, nou, u)


@app.post("/api/pressupostos/{pid}/enviar")
def enviar_pressupost(pid: int, u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    _editable(p)
    t = calc.totals_pressupost(pid)
    if not t["linies"]:
        raise HTTPException(400, "El pressupost no té línies.")
    db.update("pressupostos", pid, {"estat": "enviat", "enviat_at": db.now()})
    if p["tipus"] == "extra":
        text = (f"AVÍS DE TREBALL FORA DE PRESSUPOST ({p['numero']}): {p['titol'] or ''}. "
                f"Import {printing.eur(t['total'])} (IVA inclòs). Cal la vostra conformitat abans de fer-lo.")
        tipus = "fora_pressupost"
    else:
        text = f"Us hem enviat el pressupost {p['numero']} {p['titol'] or ''} per {printing.eur(t['total'])} (IVA inclòs)."
        tipus = "pressupost"
    missatge(p["feina_id"], text, tipus, autor="empresa", ref_tipus="pressupost", ref_id=pid)
    f = db.row("SELECT token FROM feines WHERE id = ?", (p["feina_id"],))
    return {"ok": True, "token": f["token"], "text": text}


def _accepta(p: dict, per: str, autor: str):
    t = calc.totals_pressupost(p["id"])
    db.update("pressupostos", p["id"], {"estat": "acceptat", "acceptat_at": db.now(), "acceptat_per": per})
    f = db.row("SELECT * FROM feines WHERE id = ?", (p["feina_id"],))
    if f["estat"] == "pressupost":
        db.update("feines", f["id"], {"estat": "acceptada"})
    missatge(p["feina_id"], f"Pressupost {p['numero']} ACCEPTAT per {per} ({printing.eur(t['total'])}).",
             "acceptacio", autor=autor, ref_tipus="pressupost", ref_id=p["id"])
    # Còpia fixa del pressupost acceptat a la carpeta de documents
    html = printing.pressupost(p["id"]).encode()
    guarda_fitxer(html, f"Pressupost {p['numero']} acceptat.html", p["feina_id"], "pressupost", "text/html")


@app.post("/api/pressupostos/{pid}/acceptar")
def acceptar_pressupost(pid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    _editable(p)
    _accepta(p, data.get("per") or "el client (registrat per l'empresa)", "empresa")
    return {"ok": True}


@app.post("/api/pressupostos/{pid}/rebutjar")
def rebutjar_pressupost(pid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    _editable(p)
    db.update("pressupostos", pid, {"estat": "rebutjat", "rebutjat_motiu": data.get("motiu")})
    missatge(p["feina_id"], f"Pressupost {p['numero']} rebutjat. {data.get('motiu') or ''}", "rebuig", ref_tipus="pressupost", ref_id=pid)
    return {"ok": True}


@app.get("/api/pressupostos/{pid}/revisio")
def revisio_pressupost(pid: int, u=Depends(usuari_actual)):
    cal(db.row("SELECT id FROM pressupostos WHERE id = ?", (pid,)))
    return learning.revisar_pressupost(pid)


@app.post("/api/pressupostos/{pid}/revisio-ia")
def revisio_ia(pid: int, u=Depends(usuari_actual)):
    cal(db.row("SELECT id FROM pressupostos WHERE id = ?", (pid,)))
    return ai.revisar_pressupost_ia(pid)


@app.post("/api/ia/pressupost")
def ia_pressupost(data: dict = Body(...), u=Depends(usuari_actual)):
    tipus = data.get("tipus")
    if not tipus and data.get("feina_id"):
        tipus = db.scalar("SELECT tipus FROM feines WHERE id = ?", (data["feina_id"],))
    return ai.proposar_pressupost(data.get("text", ""), tipus)


@app.get("/api/semblants")
def semblants(text: str, tipus: str = "", u=Depends(usuari_actual)):
    return learning.pressupostos_semblants(text, tipus or None, limit=6)


# ------------------------------------------------------------------ despeses

CAMPS_DESPESA = {"feina_id": int, "partida_id": int, "proveidor": str, "proveidor_nif": str, "tipus_doc": str,
                 "num_document": str, "data": str, "concepte": str, "base": float, "iva_pct": float, "iva_import": float,
                 "total": float, "marge_pct": float, "facturable": bool, "document_id": int, "estat": str,
                 "ia_confianca": float, "notes": str}


def _completa_imports(d: dict):
    base, iva_pct, total = d.get("base"), d.get("iva_pct"), d.get("total")
    if iva_pct is None:
        iva_pct = d["iva_pct"] = db.setting_float("iva_defecte", 21)
    if base and not total:
        d["iva_import"] = calc.r2(base * iva_pct / 100)
        d["total"] = calc.r2(base + d["iva_import"])
    elif total and not base:
        d["base"] = calc.r2(total / (1 + iva_pct / 100))
        d["iva_import"] = calc.r2(total - d["base"])
    elif base and total and d.get("iva_import") is None:
        d["iva_import"] = calc.r2(total - base)


@app.get("/api/despeses")
def get_despeses(feina_id: int | None = None, estat: str = "", u=Depends(usuari_actual)):
    sql = ("SELECT d.*, p.nom AS partida_nom, f.codi AS feina_codi, f.nom AS feina_nom FROM despeses d "
           "LEFT JOIN partides p ON p.id = d.partida_id LEFT JOIN feines f ON f.id = d.feina_id WHERE 1=1")
    params = []
    if feina_id:
        sql += " AND d.feina_id = ?"
        params.append(feina_id)
    if estat == "pendents":
        sql += " AND (d.estat = 'pendent_revisio' OR d.feina_id IS NULL OR d.partida_id IS NULL)"
    return db.rows(sql + " ORDER BY d.data DESC, d.id DESC LIMIT 500", params)


@app.post("/api/despeses")
def post_despesa(data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, CAMPS_DESPESA)
    d.setdefault("data", db.today())
    d["data"] = d["data"] or db.today()
    if not d.get("partida_id"):
        d["partida_id"] = learning.partida_proveidor(d.get("proveidor"))
    if d.get("feina_id") and "facturable" not in d:
        mode = db.scalar("SELECT mode_facturacio FROM feines WHERE id = ?", (d["feina_id"],))
        d["facturable"] = 1 if mode == "administracio" else 0
    if d.get("facturable") and d.get("marge_pct") is None:
        d["marge_pct"] = db.setting_float("marge_defecte", 20)
    d["marge_pct"] = d.get("marge_pct") or 0
    _completa_imports(d)
    for k in ("base", "iva_import", "total"):
        d[k] = d.get(k) or 0
    d["estat"] = d.get("estat") or ("ok" if d.get("feina_id") and d.get("partida_id") else "pendent_revisio")
    d["created_at"] = db.now()
    did = db.insert("despeses", d)
    learning.aprendre_proveidor(d.get("proveidor"), d.get("partida_id"))
    if d.get("document_id") and d.get("feina_id"):
        db.update("documents", d["document_id"], {"feina_id": d["feina_id"]})
    return {"id": did}


@app.put("/api/despeses/{did}")
def put_despesa(did: int, data: dict = Body(...), u=Depends(usuari_actual)):
    actual = cal(db.row("SELECT * FROM despeses WHERE id = ?", (did,)))
    d = pick(data, CAMPS_DESPESA)
    if any(k in d for k in ("base", "total", "iva_pct")):
        tmp = {**actual, **d}
        if "total" in d and "base" not in d:
            tmp["base"] = None
        if "base" in d and "total" not in d:
            tmp["total"] = None
        tmp["iva_import"] = None
        _completa_imports(tmp)
        d.update({k: tmp[k] for k in ("base", "iva_import", "total")})
    merged = {**actual, **d}
    if "estat" not in d and merged.get("feina_id") and merged.get("partida_id"):
        d["estat"] = "ok"
    db.update("despeses", did, d)
    if d.get("partida_id"):
        learning.aprendre_proveidor(merged.get("proveidor"), d["partida_id"])
    if merged.get("document_id") and merged.get("feina_id"):
        db.update("documents", merged["document_id"], {"feina_id": merged["feina_id"]})
    return {"ok": True}


@app.delete("/api/despeses/{did}")
def del_despesa(did: int, u=Depends(usuari_actual)):
    if db.scalar("SELECT COUNT(*) FROM linies_factura lf JOIN factures f ON f.id = lf.factura_id "
                 "WHERE lf.origen_tipus='despesa' AND lf.origen_id = ? AND f.estat IN ('emesa','cobrada')", (did,)):
        raise HTTPException(400, "Aquesta despesa ja s'ha facturat al client.")
    db.delete("despeses", did)
    return {"ok": True}


# ---------------------------------------------------------------- documents

@app.post("/api/ia/document")
async def ia_document(fitxer: UploadFile = File(...), feina_id: int | None = Form(None), u=Depends(usuari_actual)):
    """Desa la foto/PDF i, si la IA està activa, n'extreu les dades. No crea la despesa:
    l'usuari revisa les dades i les confirma."""
    contingut = await fitxer.read()
    if len(contingut) > MAX_UPLOAD:
        raise HTTPException(400, "El fitxer és massa gran (màxim 15 MB).")
    mime = fitxer.content_type or mimetypes.guess_type(fitxer.filename or "")[0] or ""
    if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"):
        raise HTTPException(400, "Format no admès. Fes servir una foto (JPG/PNG) o un PDF.")
    doc_id = guarda_fitxer(contingut, fitxer.filename or "document", feina_id, "tiquet", mime)
    dades, error = None, None
    if ai.disponible():
        try:
            dades = ai.llegir_document(contingut, mime)
            tipus = {"factura": "factura_proveidor", "albara": "albara_proveidor"}.get(dades["tipus_doc"], "tiquet")
            db.update("documents", doc_id, {"dades_json": json.dumps(dades, ensure_ascii=False),
                                            "text_extret": " ".join(filter(None, [dades.get("proveidor"), dades.get("concepte")] +
                                                                           [l["descripcio"] for l in dades.get("linies", [])])),
                                            "tipus": tipus,
                                            "nom": f"{dades.get('proveidor') or 'Proveïdor'} {dades.get('num_document') or ''}".strip()})
        except ai.IAError as e:
            error = str(e)
    else:
        error = "IA no configurada: omple les dades a mà."
    if dades and feina_id and not dades.get("feina_id"):
        dades["feina_id"] = feina_id
    return {"document_id": doc_id, "dades": dades, "error": error}


@app.get("/api/documents")
def get_documents(feina_id: int | None = None, tipus: str = "", q: str = "", u=Depends(usuari_actual)):
    sql = ("SELECT d.id, d.feina_id, d.tipus, d.nom, d.mime, d.mida, d.created_at, d.text_extret, "
           "f.codi AS feina_codi, f.nom AS feina_nom FROM documents d LEFT JOIN feines f ON f.id = d.feina_id WHERE 1=1")
    params = []
    if feina_id:
        sql += " AND d.feina_id = ?"
        params.append(feina_id)
    if tipus:
        sql += " AND d.tipus = ?"
        params.append(tipus)
    if q:
        sql += " AND (d.nom LIKE ? OR d.text_extret LIKE ? OR f.nom LIKE ? OR f.codi LIKE ?)"
        params += [f"%{q}%"] * 4
    docs = db.rows(sql + " ORDER BY d.created_at DESC LIMIT 500", params)
    # Documents generats per l'app (sempre actualitzats)
    gen = []
    if tipus in ("", "pressupost"):
        s = ("SELECT p.id, p.numero, p.titol, p.estat, p.data, p.feina_id, f.codi AS feina_codi, f.nom AS feina_nom "
             "FROM pressupostos p JOIN feines f ON f.id = p.feina_id WHERE 1=1")
        ps = []
        if feina_id:
            s += " AND p.feina_id = ?"
            ps.append(feina_id)
        if q:
            s += " AND (p.numero LIKE ? OR p.titol LIKE ? OR f.nom LIKE ?)"
            ps += [f"%{q}%"] * 3
        gen += [{"generat": "pressupost", **r} for r in db.rows(s, ps)]
    if tipus in ("", "factura"):
        s = ("SELECT fa.id, fa.codi AS numero, fa.concepte AS titol, fa.estat, fa.data, fa.feina_id, f.codi AS feina_codi, "
             "f.nom AS feina_nom FROM factures fa LEFT JOIN feines f ON f.id = fa.feina_id WHERE 1=1")
        ps = []
        if feina_id:
            s += " AND fa.feina_id = ?"
            ps.append(feina_id)
        if q:
            s += " AND (fa.codi LIKE ? OR fa.concepte LIKE ? OR f.nom LIKE ?)"
            ps += [f"%{q}%"] * 3
        gen += [{"generat": "factura", **r} for r in db.rows(s, ps)]
    if tipus in ("", "albara"):
        s = ("SELECT a.id, a.numero, a.descripcio AS titol, a.estat, a.data, a.feina_id, f.codi AS feina_codi, "
             "f.nom AS feina_nom FROM albarans a JOIN feines f ON f.id = a.feina_id WHERE 1=1")
        ps = []
        if feina_id:
            s += " AND a.feina_id = ?"
            ps.append(feina_id)
        if q:
            s += " AND (a.numero LIKE ? OR a.descripcio LIKE ? OR f.nom LIKE ?)"
            ps += [f"%{q}%"] * 3
        gen += [{"generat": "albara", **r} for r in db.rows(s, ps)]
    gen.sort(key=lambda x: x["data"] or "", reverse=True)
    return {"fitxers": docs, "generats": gen}


@app.post("/api/documents")
async def post_document(fitxer: UploadFile = File(...), feina_id: int | None = Form(None), tipus: str = Form("altres"),
                        u=Depends(usuari_actual)):
    contingut = await fitxer.read()
    if len(contingut) > MAX_UPLOAD:
        raise HTTPException(400, "El fitxer és massa gran (màxim 15 MB).")
    if tipus not in TIPUS_DOCS:
        tipus = "altres"
    return {"id": guarda_fitxer(contingut, fitxer.filename or "document", feina_id, tipus, fitxer.content_type)}


@app.put("/api/documents/{did}")
def put_document(did: int, data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, {"feina_id": int, "tipus": str, "nom": str})
    db.update("documents", did, d)
    return {"ok": True}


@app.get("/api/documents/{did}/fitxer")
def get_fitxer(did: int, u=Depends(usuari_actual)):
    d = cal(db.row("SELECT * FROM documents WHERE id = ?", (did,)))
    path = (db.DOCS_DIR / d["fitxer"]).resolve()
    if not str(path).startswith(str(db.DOCS_DIR.resolve())) or not path.exists():
        raise HTTPException(404, "Fitxer no trobat.")
    return FileResponse(path, media_type=d["mime"] or None, filename=Path(d["nom"]).name if d["mime"] != "text/html" else None,
                        content_disposition_type="inline")


@app.delete("/api/documents/{did}")
def del_document(did: int, u=Depends(admin)):
    d = cal(db.row("SELECT * FROM documents WHERE id = ?", (did,)))
    if d["tipus"] == "factura":
        raise HTTPException(400, "Les còpies de factures emeses no es poden esborrar.")
    (db.DOCS_DIR / d["fitxer"]).unlink(missing_ok=True)
    db.delete("documents", did)
    return {"ok": True}


# -------------------------------------------------------------------- hores

CAMPS_HORES = {"feina_id": int, "usuari_id": int, "treballador": str, "data": str, "hores": float, "cost_hora": float,
               "preu_hora": float, "descripcio": str, "facturable": bool, "albara_id": int}


@app.get("/api/hores")
def get_hores(feina_id: int | None = None, desde: str = "", u=Depends(usuari_actual)):
    sql = ("SELECT h.*, f.codi AS feina_codi, f.nom AS feina_nom FROM hores h JOIN feines f ON f.id = h.feina_id WHERE 1=1")
    params = []
    if feina_id:
        sql += " AND h.feina_id = ?"
        params.append(feina_id)
    if desde:
        sql += " AND h.data >= ?"
        params.append(desde)
    if u["rol"] != "admin":
        sql += " AND h.usuari_id = ?"
        params.append(u["id"])
    return db.rows(sql + " ORDER BY h.data DESC, h.id DESC LIMIT 500", params)


@app.post("/api/hores")
def post_hores(data: dict = Body(...), u=Depends(usuari_actual)):
    d = pick(data, CAMPS_HORES)
    if not d.get("feina_id") or not d.get("hores"):
        raise HTTPException(400, "Cal la feina i les hores.")
    feina = feina_o_404(d["feina_id"])
    treb = db.row("SELECT * FROM usuaris WHERE id = ?", (d.get("usuari_id") or u["id"],)) or u
    d["usuari_id"] = treb["id"]
    d["treballador"] = d.get("treballador") or treb["nom"]
    if d.get("cost_hora") is None:
        d["cost_hora"] = treb["cost_hora"] or db.setting_float("cost_hora_defecte", 25)
    if d.get("preu_hora") is None:
        d["preu_hora"] = treb["preu_hora"] or db.setting_float("preu_hora_defecte", 38)
    if "facturable" not in d:
        d["facturable"] = 1 if feina["mode_facturacio"] == "administracio" else 0
    d["data"] = d.get("data") or db.today()
    d["created_at"] = db.now()
    if feina["estat"] in ("pressupost", "acceptada"):
        db.update("feines", feina["id"], {"estat": "en_curs", "data_inici": feina["data_inici"] or d["data"]})
    return {"id": db.insert("hores", d)}


@app.put("/api/hores/{hid}")
def put_hores(hid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    cal(db.row("SELECT id FROM hores WHERE id = ?", (hid,)))
    db.update("hores", hid, pick(data, CAMPS_HORES))
    return {"ok": True}


@app.delete("/api/hores/{hid}")
def del_hores(hid: int, u=Depends(usuari_actual)):
    if db.scalar("SELECT COUNT(*) FROM linies_factura lf JOIN factures f ON f.id = lf.factura_id "
                 "WHERE lf.origen_tipus='hores' AND lf.origen_id = ? AND f.estat IN ('emesa','cobrada')", (hid,)):
        raise HTTPException(400, "Aquestes hores ja s'han facturat.")
    db.delete("hores", hid)
    return {"ok": True}


# ----------------------------------------------------------------- albarans

@app.get("/api/feines/{fid}/albarans")
def get_albarans(fid: int, u=Depends(usuari_actual)):
    res = db.rows("SELECT * FROM albarans WHERE feina_id = ? ORDER BY data DESC, id DESC", (fid,))
    for a in res:
        a["linies"] = db.rows("SELECT * FROM linies_albara WHERE albara_id = ?", (a["id"],))
        a["hores"] = db.rows("SELECT * FROM hores WHERE albara_id = ?", (a["id"],))
        a.pop("signatura", None)
    return res


@app.post("/api/feines/{fid}/albarans")
def post_albara(fid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    feina_o_404(fid)
    aid = db.insert("albarans", {"feina_id": fid, "numero": seguent_codi("A", "albarans", "numero"),
                                 "data": data.get("data") or db.today(), "descripcio": data.get("descripcio"),
                                 "created_at": db.now()})
    _guarda_albara(aid, fid, data)
    return {"id": aid}


def _guarda_albara(aid: int, fid: int, data: dict):
    with db.tx() as conn:
        if "linies" in data:
            conn.execute("DELETE FROM linies_albara WHERE albara_id = ?", (aid,))
            for l in data["linies"]:
                d = pick(l, {"article_id": int, "descripcio": str, "quantitat": float, "unitat": str})
                if d.get("descripcio"):
                    conn.execute("INSERT INTO linies_albara(albara_id, article_id, descripcio, quantitat, unitat) VALUES (?,?,?,?,?)",
                                 (aid, d.get("article_id"), d["descripcio"], d.get("quantitat") or 1, d.get("unitat") or "u"))
        if "hores_ids" in data:
            conn.execute("UPDATE hores SET albara_id = NULL WHERE albara_id = ?", (aid,))
            for hid in data["hores_ids"]:
                conn.execute("UPDATE hores SET albara_id = ? WHERE id = ? AND feina_id = ?", (aid, int(hid), fid))


@app.put("/api/albarans/{aid}")
def put_albara(aid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    a = cal(db.row("SELECT * FROM albarans WHERE id = ?", (aid,)))
    if a["estat"] == "signat":
        raise HTTPException(400, "L'albarà ja està signat.")
    db.update("albarans", aid, pick(data, {"data": str, "descripcio": str}))
    _guarda_albara(aid, a["feina_id"], data)
    return {"ok": True}


def _signa_albara(a: dict, nom: str, signatura: str | None, autor: str):
    if a["estat"] == "signat":
        raise HTTPException(400, "L'albarà ja està signat.")
    if not nom:
        raise HTTPException(400, "Cal el nom de qui signa.")
    if signatura and (not signatura.startswith("data:image/png;base64,") or len(signatura) > 500_000):
        raise HTTPException(400, "Signatura no vàlida.")
    db.update("albarans", a["id"], {"estat": "signat", "signat_per": nom, "signatura": signatura, "signat_at": db.now()})
    missatge(a["feina_id"], f"Albarà {a['numero']} signat per {nom}.", "nota", autor=autor, ref_tipus="albara", ref_id=a["id"])


@app.post("/api/albarans/{aid}/signar")
def signar_albara(aid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    a = cal(db.row("SELECT * FROM albarans WHERE id = ?", (aid,)))
    _signa_albara(a, data.get("nom"), data.get("signatura"), "empresa")
    return {"ok": True}


@app.delete("/api/albarans/{aid}")
def del_albara(aid: int, u=Depends(usuari_actual)):
    a = cal(db.row("SELECT * FROM albarans WHERE id = ?", (aid,)))
    if a["estat"] == "signat":
        raise HTTPException(400, "Un albarà signat no es pot esborrar.")
    db.delete("albarans", aid)
    return {"ok": True}


# ----------------------------------------------------------------- factures

@app.get("/api/feines/{fid}/pendent")
def get_pendent(fid: int, u=Depends(usuari_actual)):
    feina_o_404(fid)
    return calc.pendent_facturar(fid)


@app.get("/api/factures")
def get_factures(estat: str = "", feina_id: int | None = None, u=Depends(usuari_actual)):
    sql = ("SELECT fa.*, f.codi AS feina_codi, f.nom AS feina_nom, c.nom AS client_nom FROM factures fa "
           "LEFT JOIN feines f ON f.id = fa.feina_id LEFT JOIN clients c ON c.id = fa.client_id WHERE 1=1")
    params = []
    if estat == "pendents_cobrar":
        sql += " AND fa.estat = 'emesa'"
    elif estat:
        sql += " AND fa.estat = ?"
        params.append(estat)
    if feina_id:
        sql += " AND fa.feina_id = ?"
        params.append(feina_id)
    res = db.rows(sql + " ORDER BY fa.data DESC, fa.id DESC LIMIT 500", params)
    avui = db.today()
    for f in res:
        f["vencuda"] = f["estat"] == "emesa" and bool(f["venciment"]) and f["venciment"] < avui
    return res


@app.post("/api/feines/{fid}/factures")
def post_factura(fid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    """Crea un esborrany de factura amb una part del pendent.

    data.items: [{origen_tipus, origen_id, import}] (import opcional: per defecte tot el pendent)
    data.pct: si s'indica, factura aquest % del total de cada línia de pressupost acceptat
    data.linies_manuals: [{descripcio, quantitat, preu_unitari}]"""
    feina = feina_o_404(fid)
    pend = calc.pendent_facturar(fid)
    disponibles = {(x["origen_tipus"], x["origen_id"]): x for x in pend["linies_pressupost"] + pend["despeses"] + pend["hores"]}
    linies = []
    pct = data.get("pct")
    if pct not in (None, ""):
        pct = float(pct)
        if not 0 < pct <= 100:
            raise HTTPException(400, "El percentatge ha d'estar entre 0 i 100.")
        for x in pend["linies_pressupost"]:
            imp = min(calc.r2(x["total"] * pct / 100), x["pendent"])
            if imp > 0:
                linies.append((x, imp, f"{x['descripcio']} ({pct:g}% del pressupost {x['pressupost']})"))
    for it in data.get("items") or []:
        x = disponibles.get((it.get("origen_tipus"), int(it.get("origen_id") or 0)))
        if not x:
            continue
        imp = float(it["import"]) if it.get("import") not in (None, "") else x["pendent"]
        imp = min(calc.r2(imp), x["pendent"])
        if imp <= 0:
            continue
        desc = x["descripcio"]
        if x["origen_tipus"] == "linia_pressupost" and imp < x["total"] - 0.009:
            desc += f" ({imp / x['total'] * 100:.0f}% · pressupost {x['pressupost']})"
        linies.append((x, imp, desc))
    for m in data.get("linies_manuals") or []:
        if m.get("descripcio"):
            linies.append((None, None, m))
    if not linies:
        raise HTTPException(400, "No hi ha res seleccionat per facturar.")

    p_ref = db.row("SELECT iva_pct, irpf_pct FROM pressupostos WHERE feina_id = ? AND estat = 'acceptat' ORDER BY id LIMIT 1", (fid,))
    iva = float(data["iva_pct"]) if data.get("iva_pct") not in (None, "") else (p_ref["iva_pct"] if p_ref else db.setting_float("iva_defecte", 21))
    irpf = float(data["irpf_pct"]) if data.get("irpf_pct") not in (None, "") else (p_ref["irpf_pct"] if p_ref else db.setting_float("irpf_defecte", 0))
    data_f = data.get("data") or db.today()
    venc = (date.fromisoformat(data_f) + timedelta(days=int(db.setting_float("venciment_dies", 30)))).isoformat()
    fac_id = db.insert("factures", {"feina_id": fid, "client_id": feina["client_id"], "serie": db.setting("serie_factura", "F"),
                                    "data": data_f, "venciment": venc, "concepte": data.get("concepte") or f"Treballs a {feina['nom']}",
                                    "iva_pct": iva, "irpf_pct": irpf, "estat": "esborrany", "created_at": db.now()})
    with db.tx() as conn:
        for x, imp, desc in linies:
            if x is None:
                m = desc
                conn.execute("INSERT INTO linies_factura(factura_id, descripcio, quantitat, preu_unitari, descompte_pct, origen_tipus) "
                             "VALUES (?,?,?,?,?, 'manual')", (fac_id, m["descripcio"], float(m.get("quantitat") or 1),
                                                              float(m.get("preu_unitari") or 0), float(m.get("descompte_pct") or 0)))
            else:
                conn.execute("INSERT INTO linies_factura(factura_id, descripcio, quantitat, preu_unitari, origen_tipus, origen_id) "
                             "VALUES (?,?,1,?,?,?)", (fac_id, desc, imp, x["origen_tipus"], x["origen_id"]))
    calc.recalcula_factura(fac_id)
    return {"id": fac_id}


@app.get("/api/factures/{fid}")
def get_factura(fid: int, u=Depends(usuari_actual)):
    f = cal(db.row("SELECT fa.*, fe.codi AS feina_codi, fe.nom AS feina_nom, fe.token, c.nom AS client_nom, "
                   "c.nif AS client_nif, c.email AS client_email, c.telefon AS client_telefon FROM factures fa "
                   "LEFT JOIN feines fe ON fe.id = fa.feina_id LEFT JOIN clients c ON c.id = fa.client_id WHERE fa.id = ?", (fid,)))
    f["linies"] = db.rows("SELECT * FROM linies_factura WHERE factura_id = ? ORDER BY id", (fid,))
    return f


@app.put("/api/factures/{fid}")
def put_factura(fid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    f = cal(db.row("SELECT * FROM factures WHERE id = ?", (fid,)))
    if f["estat"] != "esborrany":
        raise HTTPException(400, "Una factura emesa no es pot modificar. Cal fer-ne una de rectificativa.")
    db.update("factures", fid, pick(data, {"data": str, "venciment": str, "concepte": str, "iva_pct": float,
                                           "irpf_pct": float, "notes": str, "client_id": int}))
    if "linies" in data:
        with db.tx() as conn:
            existents = {l["id"]: l for l in db.rows("SELECT * FROM linies_factura WHERE factura_id = ?", (fid,))}
            conservar = set()
            for l in data["linies"]:
                d = pick(l, {"descripcio": str, "quantitat": float, "preu_unitari": float, "descompte_pct": float})
                if not d.get("descripcio"):
                    continue
                lid = l.get("id")
                if lid in existents:
                    conservar.add(lid)
                    conn.execute("UPDATE linies_factura SET descripcio=?, quantitat=?, preu_unitari=?, descompte_pct=? WHERE id=?",
                                 (d["descripcio"], d.get("quantitat") or 1, d.get("preu_unitari") or 0, d.get("descompte_pct") or 0, lid))
                else:
                    conn.execute("INSERT INTO linies_factura(factura_id, descripcio, quantitat, preu_unitari, descompte_pct, origen_tipus) "
                                 "VALUES (?,?,?,?,?,'manual')", (fid, d["descripcio"], d.get("quantitat") or 1,
                                                                 d.get("preu_unitari") or 0, d.get("descompte_pct") or 0))
            for lid in set(existents) - conservar:
                conn.execute("DELETE FROM linies_factura WHERE id = ?", (lid,))
    calc.recalcula_factura(fid)
    return get_factura(fid, u)


@app.delete("/api/factures/{fid}")
def del_factura(fid: int, u=Depends(usuari_actual)):
    f = cal(db.row("SELECT * FROM factures WHERE id = ?", (fid,)))
    if f["estat"] != "esborrany":
        raise HTTPException(400, "Només es poden esborrar esborranys.")
    db.delete("factures", fid)
    return {"ok": True}


def _assigna_numero(fid: int):
    f = db.row("SELECT * FROM factures WHERE id = ?", (fid,))
    any_ = f["data"][:4]
    serie = f"{f['serie']}{any_}"
    darrer = db.scalar("SELECT MAX(numero) FROM factures WHERE serie = ?", (serie,)) or 0
    # Les dates han de ser correlatives a la numeració
    ultima_data = db.scalar("SELECT MAX(data) FROM factures WHERE serie = ? AND numero IS NOT NULL", (serie,))
    if ultima_data and f["data"] < ultima_data:
        raise HTTPException(400, f"La data no pot ser anterior a la de l'última factura emesa ({printing.data_cat(ultima_data)}).")
    n = darrer + 1
    db.update("factures", fid, {"serie": serie, "numero": n, "codi": f"{serie}-{n:04d}", "estat": "emesa"})


@app.post("/api/factures/{fid}/emetre")
def emetre_factura(fid: int, u=Depends(usuari_actual)):
    f = cal(db.row("SELECT * FROM factures WHERE id = ?", (fid,)))
    if f["estat"] != "esborrany":
        raise HTTPException(400, "La factura ja està emesa.")
    if not f["client_id"]:
        raise HTTPException(400, "La factura necessita un client amb les seves dades fiscals.")
    c = db.row("SELECT * FROM clients WHERE id = ?", (f["client_id"],))
    if not c.get("nif") or not c.get("adreca"):
        raise HTTPException(400, "Falten el NIF o l'adreça del client per poder emetre la factura.")
    s = db.settings()
    if not s.get("empresa_nom") or not s.get("empresa_nif"):
        raise HTTPException(400, "Falten les dades de l'empresa (nom i NIF) a Configuració.")
    if f["total"] == 0:
        raise HTTPException(400, "La factura no té import.")
    _assigna_numero(fid)
    f = db.row("SELECT * FROM factures WHERE id = ?", (fid,))
    guarda_fitxer(printing.factura(fid).encode(), f"Factura {f['codi']}.html", f["feina_id"], "factura", "text/html")
    if f["feina_id"]:
        missatge(f["feina_id"], f"Factura {f['codi']} emesa per {printing.eur(f['total'])}. Venciment {printing.data_cat(f['venciment'])}.",
                 "factura", autor="empresa", ref_tipus="factura", ref_id=fid)
    return get_factura(fid, u)


@app.post("/api/factures/{fid}/cobrar")
def cobrar_factura(fid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    f = cal(db.row("SELECT * FROM factures WHERE id = ?", (fid,)))
    if f["estat"] not in ("emesa", "cobrada"):
        raise HTTPException(400, "Només es poden cobrar factures emeses.")
    cobrada = data.get("cobrada", True)
    db.update("factures", fid, {"estat": "cobrada" if cobrada else "emesa",
                                "cobrada_at": (data.get("data") or db.today()) if cobrada else None})
    return {"ok": True}


@app.post("/api/factures/{fid}/rectificar")
def rectificar_factura(fid: int, data: dict = Body(default={}), u=Depends(usuari_actual)):
    """Anul·la una factura emesa creant-ne la rectificativa (import negatiu)."""
    f = cal(db.row("SELECT * FROM factures WHERE id = ?", (fid,)))
    if f["estat"] not in ("emesa", "cobrada") or f["rectifica_id"]:
        raise HTTPException(400, "Només es poden rectificar factures emeses.")
    serie_base = db.setting("serie_factura", "F") + "R"
    rid = db.insert("factures", {"feina_id": f["feina_id"], "client_id": f["client_id"], "serie": serie_base,
                                 "data": db.today(), "concepte": f"Rectificació de la factura {f['codi']}. {data.get('motiu') or ''}".strip(),
                                 "iva_pct": f["iva_pct"], "irpf_pct": f["irpf_pct"], "estat": "esborrany",
                                 "rectifica_id": fid, "created_at": db.now()})
    with db.tx() as conn:
        for l in db.rows("SELECT * FROM linies_factura WHERE factura_id = ?", (fid,)):
            conn.execute("INSERT INTO linies_factura(factura_id, descripcio, quantitat, preu_unitari, descompte_pct, origen_tipus) "
                         "VALUES (?,?,?,?,?,'rectificacio')", (rid, l["descripcio"], -l["quantitat"], l["preu_unitari"], l["descompte_pct"]))
    calc.recalcula_factura(rid)
    _assigna_numero(rid)
    db.update("factures", fid, {"estat": "anullada"})
    r = db.row("SELECT * FROM factures WHERE id = ?", (rid,))
    guarda_fitxer(printing.factura(rid).encode(), f"Factura {r['codi']}.html", r["feina_id"], "factura", "text/html")
    if f["feina_id"]:
        missatge(f["feina_id"], f"Factura {f['codi']} anul·lada amb la rectificativa {r['codi']}.", "factura",
                 autor="empresa", ref_tipus="factura", ref_id=rid)
    return {"id": rid}


# ---------------------------------------------------------------- missatges

@app.get("/api/feines/{fid}/missatges")
def get_missatges(fid: int, u=Depends(usuari_actual)):
    feina_o_404(fid)
    res = db.rows("SELECT * FROM missatges WHERE feina_id = ? ORDER BY created_at, id", (fid,))
    with db.tx() as conn:
        conn.execute("UPDATE missatges SET llegit = 1 WHERE feina_id = ? AND llegit = 0", (fid,))
    return res


@app.post("/api/feines/{fid}/missatges")
def post_missatge(fid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    feina_o_404(fid)
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Missatge buit.")
    intern = bool(data.get("intern"))
    missatge(fid, text, "nota" if intern else "missatge", autor="empresa", intern=intern)
    return {"ok": True}


# ------------------------------------------------------------ resum / inici

@app.get("/api/inici")
def inici(u=Depends(usuari_actual)):
    feines = db.rows("SELECT f.id, f.codi, f.nom, f.estat, f.tipus, c.nom AS client_nom FROM feines f "
                     "LEFT JOIN clients c ON c.id = f.client_id WHERE f.estat IN ('pressupost','acceptada','en_curs','acabada') "
                     "ORDER BY f.created_at DESC")
    alertes = []
    tot = {"contractat": 0, "cost_real": 0, "facturat": 0, "pendent_facturar": 0, "pendent_acceptar": 0}
    for f in feines:
        r = calc.resum_feina(f["id"])
        f["resum"] = {k: r[k] for k in ("contractat", "cost_previst", "cost_real", "facturat", "pendent_facturar", "pct_cost",
                                        "pct_facturat", "hores_reals", "hores_previstes", "benefici_projectat", "pendent_acceptar")}
        f["alertes"] = r["alertes"]
        for k in tot:
            tot[k] += r[k]
        for a in r["alertes"]:
            alertes.append({"feina_id": f["id"], "feina": f["codi"] + " " + f["nom"], "text": a})
    no_llegits = db.rows("SELECT m.feina_id, f.codi, f.nom, COUNT(*) AS n FROM missatges m JOIN feines f ON f.id = m.feina_id "
                         "WHERE m.llegit = 0 GROUP BY m.feina_id")
    avui = db.today()
    pendents_cobrar = db.row("SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS total, "
                             "COALESCE(SUM(CASE WHEN venciment < ? THEN total ELSE 0 END),0) AS vencut "
                             "FROM factures WHERE estat = 'emesa'", (avui,))
    pendents_revisar = db.scalar("SELECT COUNT(*) FROM despeses WHERE estat = 'pendent_revisio' OR feina_id IS NULL OR partida_id IS NULL")
    pressupostos_enviats = db.rows("SELECT p.id, p.numero, p.titol, p.enviat_at, p.tipus, f.id AS feina_id, f.nom AS feina_nom "
                                   "FROM pressupostos p JOIN feines f ON f.id = p.feina_id WHERE p.estat = 'enviat' ORDER BY p.enviat_at")
    bloquejades = []
    for f in feines:
        b = calc.bloquejos(f["id"])
        if b:
            bloquejades.append({"feina_id": f["id"], "feina": f"{f['codi']} {f['nom']}", "bloquejos": b})
    pagaments = db.rows("SELECT fa.id, fa.codi, fa.total, fa.pagament_notificat_at, fe.nom AS feina_nom FROM factures fa "
                        "LEFT JOIN feines fe ON fe.id = fa.feina_id WHERE fa.estat = 'emesa' AND fa.pagament_notificat_at IS NOT NULL")
    return {"feines": feines, "alertes": alertes, "bloquejades": bloquejades, "pagaments_notificats": pagaments, "totals": {k: calc.r2(v) for k, v in tot.items()},
            "no_llegits": no_llegits, "pendents_cobrar": pendents_cobrar, "despeses_pendents": pendents_revisar,
            "pressupostos_enviats": pressupostos_enviats, "hores_avui": db.scalar(
                "SELECT COALESCE(SUM(hores),0) FROM hores WHERE data = ? AND usuari_id = ?", (avui, u["id"]))}


@app.get("/api/impostos")
def impostos(any: int | None = None, trimestre: int | None = None, u=Depends(admin)):
    return calc.resum_impostos(any or date.today().year, trimestre)


@app.get("/api/aprenentatge")
def aprenentatge(u=Depends(usuari_actual)):
    return learning.resum_aprenentatge()


@app.get("/api/partides")
def get_partides(u=Depends(usuari_actual)):
    return db.rows("SELECT * FROM partides ORDER BY ordre, id")


@app.get("/api/usuaris")
def get_usuaris(u=Depends(usuari_actual)):
    return db.rows("SELECT id, nom, rol, cost_hora, preu_hora FROM usuaris WHERE actiu = 1 ORDER BY nom")


# ---------------------------------------------------------------- impressió

IMPRESSIO = {"pressupost": printing.pressupost, "factura": printing.factura, "albara": printing.albara}


@app.get("/imprimir/{tipus}/{id_}", response_class=HTMLResponse)
def imprimir(tipus: str, id_: int, request: Request):
    usuari_actual(request)
    taula = {"pressupost": "pressupostos", "factura": "factures", "albara": "albarans"}.get(tipus)
    if not taula:
        raise HTTPException(404)
    cal(db.row(f"SELECT id FROM {taula} WHERE id = ?", (id_,)))
    return IMPRESSIO[tipus](id_)


# ------------------------------------------------------------ portal client

def _feina_token(token: str) -> dict:
    return cal(db.row("SELECT * FROM feines WHERE token = ?", (token,)), "Enllaç no vàlid.")


@app.get("/api/portal/{token}")
def portal(token: str):
    f = _feina_token(token)
    pres = db.rows("SELECT id, numero, tipus, titol, estat, data, enviat_at, acceptat_at, acceptat_per, validesa_dies "
                   "FROM pressupostos WHERE feina_id = ? AND estat IN ('enviat','acceptat','rebutjat') ORDER BY id", (f["id"],))
    for p in pres:
        t = calc.totals_pressupost(p["id"])
        p["total"] = t["total"]
        p["base"] = t["base"]
    fact = db.rows("SELECT id, codi, data, venciment, total, estat, pagament_notificat_at FROM factures WHERE feina_id = ? AND estat IN "
                   "('emesa','cobrada','anullada') ORDER BY data", (f["id"],))
    alb = db.rows("SELECT id, numero, data, descripcio, estat, signat_per FROM albarans WHERE feina_id = ? ORDER BY data", (f["id"],))
    msgs = db.rows("SELECT autor, tipus, text, document_id, created_at FROM missatges WHERE feina_id = ? AND intern = 0 "
                   "ORDER BY created_at, id", (f["id"],))
    r = calc.resum_feina(f["id"])
    s = db.settings()
    planning = db.rows("SELECT titol, data_inici, data_fi, estat, pct FROM planning WHERE feina_id = ? "
                       "ORDER BY ordre, COALESCE(data_inici, '9999'), id", (f["id"],))
    return {"feina": {"codi": f["codi"], "nom": f["nom"], "estat": f["estat"], "adreca": f["adreca"],
                      "data_inici": f["data_inici"], "data_fi": f["data_fi"]},
            "empresa": {"nom": s.get("empresa_nom"), "telefon": s.get("empresa_telefon"), "email": s.get("empresa_email")},
            "pagament": {"iban": s.get("empresa_iban"), "bizum": s.get("empresa_bizum"), "titular": s.get("empresa_nom")},
            "pressupostos": pres, "factures": fact, "albarans": alb, "missatges": msgs,
            "bloquejos": calc.bloquejos(f["id"]), "pendent": calc.pendent_client(f["id"]),
            "planning": planning,
            "progres": round(sum(t["pct"] for t in planning) / len(planning)) if planning else None,
            "evolucio": [x for x in msgs if x["tipus"] == "evolucio"],
            "valoracions": db.rows("SELECT puntuacio, comentari, created_at FROM valoracions WHERE feina_id = ? ORDER BY created_at DESC", (f["id"],)),
            "renders": db.rows("SELECT id, titol FROM renders WHERE feina_id = ? AND visible_client = 1 ORDER BY id DESC", (f["id"],)),
            "resum": {"contractat": r["contractat"], "facturat": r["facturat_total"], "cobrat": r["cobrat"],
                      "pendent_cobrar": r["pendent_cobrar"]}}


def _pressupost_portal(token: str, pid: int) -> dict:
    f = _feina_token(token)
    p = cal(db.row("SELECT * FROM pressupostos WHERE id = ? AND feina_id = ?", (pid, f["id"])))
    if p["estat"] != "enviat":
        raise HTTPException(400, "Aquest pressupost ja no està pendent de resposta.")
    return p


@app.post("/api/portal/{token}/pressupostos/{pid}/acceptar")
def portal_acceptar(token: str, pid: int, data: dict = Body(...)):
    p = _pressupost_portal(token, pid)
    nom = (data.get("nom") or "").strip()
    if not nom or not data.get("accepto"):
        raise HTTPException(400, "Escriu el teu nom i marca la casella d'acceptació.")
    _accepta(p, nom, "client")
    return {"ok": True}


@app.post("/api/portal/{token}/pressupostos/{pid}/rebutjar")
def portal_rebutjar(token: str, pid: int, data: dict = Body(default={})):
    p = _pressupost_portal(token, pid)
    db.update("pressupostos", pid, {"estat": "rebutjat", "rebutjat_motiu": data.get("motiu")})
    missatge(p["feina_id"], f"El client ha rebutjat el pressupost {p['numero']}. {data.get('motiu') or ''}".strip(),
             "rebuig", autor="client", ref_tipus="pressupost", ref_id=pid)
    return {"ok": True}


@app.post("/api/portal/{token}/missatges")
def portal_missatge(token: str, data: dict = Body(...)):
    f = _feina_token(token)
    text = (data.get("text") or "").strip()[:4000]
    if not text:
        raise HTTPException(400, "Missatge buit.")
    missatge(f["id"], text, "missatge", autor="client")
    return {"ok": True}


@app.post("/api/portal/{token}/albarans/{aid}/signar")
def portal_signar(token: str, aid: int, data: dict = Body(...)):
    f = _feina_token(token)
    a = cal(db.row("SELECT * FROM albarans WHERE id = ? AND feina_id = ?", (aid, f["id"])))
    _signa_albara(a, (data.get("nom") or "").strip(), data.get("signatura"), "client")
    return {"ok": True}


@app.get("/p/{token}/imprimir/{tipus}/{id_}", response_class=HTMLResponse)
def portal_imprimir(token: str, tipus: str, id_: int):
    f = _feina_token(token)
    if tipus == "pressupost":
        cal(db.row("SELECT id FROM pressupostos WHERE id = ? AND feina_id = ? AND estat <> 'esborrany'", (id_, f["id"])))
    elif tipus == "factura":
        cal(db.row("SELECT id FROM factures WHERE id = ? AND feina_id = ? AND estat <> 'esborrany'", (id_, f["id"])))
    elif tipus == "albara":
        cal(db.row("SELECT id FROM albarans WHERE id = ? AND feina_id = ?", (id_, f["id"])))
    else:
        raise HTTPException(404)
    return IMPRESSIO[tipus](id_)


@app.get("/p/{token}", response_class=HTMLResponse)
def portal_pagina(token: str):
    _feina_token(token)
    return FileResponse(STATIC / "portal.html")


# ------------------------------------------------------------------- estàtics

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


from . import api2  # noqa: E402  (rutes addicionals; s'importa al final per evitar cicles)

app.include_router(api2.router)
