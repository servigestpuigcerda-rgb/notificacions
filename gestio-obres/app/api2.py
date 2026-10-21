"""Assistent per ordres en llenguatge natural, planning i evolució, maqueta 3D, anàlisi de tancament,
paquet per al gestor, estimació d'impostos i extres del portal del client."""
import csv
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from . import ai, calc, db, learning, printing
from . import main as m
from .auth import admin, usuari_actual

router = APIRouter()
IMATGES = ("image/jpeg", "image/png", "image/webp", "image/gif")


async def _llegeix_imatge(f: UploadFile) -> tuple[bytes, str]:
    contingut = await f.read()
    if len(contingut) > m.MAX_UPLOAD:
        raise HTTPException(400, "La imatge és massa gran (màxim 15 MB).")
    mime = f.content_type or ""
    if mime not in IMATGES:
        raise HTTPException(400, "Només s'admeten imatges (JPG, PNG, WEBP).")
    return contingut, mime


# =============================================================== assistent

def _paraules(text):
    return learning.paraules(text or "")


def resol_feina(codi: str | None, text: str | None, actual: int | None) -> tuple[int | None, list]:
    """Troba la feina localment (els noms dels clients no surten mai cap a la IA)."""
    if codi:
        f = db.row("SELECT id FROM feines WHERE codi = ?", (codi,))
        if f:
            return f["id"], []
    if text:
        objectiu = _paraules(text)
        candidats = []
        for f in db.rows("SELECT f.id, f.codi, f.nom, f.adreca, f.estat, c.nom AS client FROM feines f "
                         "LEFT JOIN clients c ON c.id = f.client_id WHERE f.estat <> 'cancellada'"):
            bossa = _paraules(" ".join(filter(None, [f["codi"], f["nom"], f["adreca"], f["client"]])))
            punts = len(objectiu & bossa) + (0.5 if f["estat"] != "tancada" else 0)
            if objectiu & bossa:
                candidats.append((punts, f))
        candidats.sort(key=lambda x: -x[0])
        if candidats and (len(candidats) == 1 or candidats[0][0] > candidats[1][0]):
            return candidats[0][1]["id"], []
        if candidats:
            return None, [{"id": c["id"], "etiqueta": f"{c['codi']} · {c['nom']}"} for _, c in candidats[:6]]
    return (actual, []) if actual else (None, [])


def resol_treballador(text: str | None) -> int | None:
    if not text:
        return None
    objectiu = _paraules(text)
    for u in db.rows("SELECT id, nom FROM usuaris WHERE actiu = 1"):
        if objectiu & _paraules(u["nom"]):
            return u["id"]
    return None


def resol_partida(nom: str | None, unitat: str | None) -> int | None:
    if nom:
        p = db.row("SELECT id FROM partides WHERE lower(nom) = lower(?)", (nom,))
        if p:
            return p["id"]
    tipus = "ma_obra" if calc.es_hora({"unitat": unitat}) else "material"
    return db.scalar("SELECT id FROM partides WHERE tipus = ? ORDER BY ordre LIMIT 1", (tipus,))


@router.post("/api/assistent/interpretar")
def assistent_interpretar(data: dict = Body(...), u=Depends(usuari_actual)):
    actual = int(data["feina_id"]) if data.get("feina_id") else None
    res = ai.interpretar_ordre(data.get("text", ""), actual)
    for a in res["accions"]:
        if a["tipus"] == "crear_feina":
            a["feina_id"], a["opcions_feina"] = None, []
        else:
            a["feina_id"], a["opcions_feina"] = resol_feina(a.get("feina_codi"), a.get("feina_text"), actual)
        if a["feina_id"]:
            f = db.row("SELECT codi, nom FROM feines WHERE id = ?", (a["feina_id"],))
            a["feina_etiqueta"] = f"{f['codi']} · {f['nom']}"
        a["usuari_id"] = resol_treballador(a.get("treballador_text"))
    return res


def _linies_actuals(pid: int) -> list:
    return db.rows("SELECT * FROM linies_pressupost WHERE pressupost_id = ? ORDER BY ordre, id", (pid,))


def _pressupost_desti(fid: int, numero: str | None, crear: bool, u, titol: str) -> dict | None:
    if numero:
        p = db.row("SELECT * FROM pressupostos WHERE feina_id = ? AND numero = ?", (fid, numero))
        if p and p["estat"] != "acceptat":
            return p
    p = db.row("SELECT * FROM pressupostos WHERE feina_id = ? AND estat IN ('esborrany','enviat','rebutjat') "
               "ORDER BY (estat = 'esborrany') DESC, id DESC LIMIT 1", (fid,))
    if p or not crear:
        return p
    hi_ha_acceptat = db.scalar("SELECT COUNT(*) FROM pressupostos WHERE feina_id = ? AND estat = 'acceptat'", (fid,))
    r = m.post_pressupost(fid, {"tipus": "extra" if hi_ha_acceptat else "principal",
                                "titol": f"Canvis: {titol}" if hi_ha_acceptat else titol}, u)
    return db.row("SELECT * FROM pressupostos WHERE id = ?", (r["id"],))


def _preus_linia(a: dict, partida_id: int) -> dict:
    l = {"descripcio": a.get("descripcio") or a.get("text") or "Línia", "quantitat": a.get("quantitat") or a.get("hores") or 1,
         "unitat": a.get("unitat") or ("h" if a.get("hores") else "u"), "partida_id": partida_id,
         "referencia": a.get("referencia"), "descompte_pct": a.get("descompte_pct") or 0}
    cost, preu = a.get("cost_unitari"), a.get("preu_unitari")
    tipus = db.scalar("SELECT tipus FROM partides WHERE id = ?", (partida_id,))
    if cost is None and preu is None:
        art = db.row("SELECT * FROM articles WHERE actiu = 1 AND lower(nom) = lower(?)", (l["descripcio"],))
        if art:
            l["article_id"], cost, preu = art["id"], art["cost"], calc.preu_article(art)
            l["unitat"] = a.get("unitat") or art["unitat"]
        elif tipus == "ma_obra":
            cost, preu = db.setting_float("cost_hora_defecte", 25), db.setting_float("preu_hora_defecte", 38)
    marge = db.setting_float("marge_defecte", 20)
    if cost is not None and preu is None:
        preu = calc.r2(cost * (1 + marge / 100))
    l["cost_unitari"], l["preu_unitari"] = cost or 0, preu or 0
    l["marge_pct"] = calc.r2((preu / cost - 1) * 100) if cost and preu else 0
    return l


def _executa(a: dict, u) -> dict:
    t = a["tipus"]
    fid = int(a["feina_id"]) if a.get("feina_id") else None
    if t != "crear_feina" and not fid:
        raise HTTPException(400, "Cal triar la feina.")
    if t == "afegir_hores":
        if not a.get("hores"):
            raise HTTPException(400, "Falten les hores.")
        d = {"feina_id": fid, "hores": a["hores"], "data": a.get("data"), "descripcio": a.get("descripcio") or a.get("text")}
        if a.get("usuari_id"):
            d["usuari_id"] = a["usuari_id"]
        if a.get("facturable") is not None:
            d["facturable"] = a["facturable"]
        m.post_hores(d, u)
        return {"text": f"{a['hores']:g} h apuntades", "enllac": f"#/feina/{fid}/hores"}
    if t == "afegir_linia_pressupost":
        p = _pressupost_desti(fid, a.get("pressupost_numero"), True, u, a.get("descripcio") or "")
        linies = _linies_actuals(p["id"]) + [_preus_linia(a, resol_partida(a.get("partida"), a.get("unitat") or ("h" if a.get("hores") else None)))]
        m.put_pressupost(p["id"], {"linies": linies}, u)
        return {"text": f"Línia afegida al pressupost {p['numero']}" + (" (fora de pressupost)" if p["tipus"] == "extra" else ""),
                "enllac": f"#/pressupost/{p['id']}"}
    if t in ("modificar_linia_pressupost", "eliminar_linia_pressupost"):
        p = _pressupost_desti(fid, a.get("pressupost_numero"), False, u, "")
        if not p:
            raise HTTPException(400, "No hi ha cap pressupost modificable (els acceptats no es poden canviar).")
        linies = _linies_actuals(p["id"])
        i = (a.get("linia_index") or 0) - 1
        if not 0 <= i < len(linies):
            if a.get("descripcio"):
                obj = _paraules(a["descripcio"])
                i = max(range(len(linies)), key=lambda k: len(obj & _paraules(linies[k]["descripcio"])), default=-1)
            if not 0 <= i < len(linies):
                raise HTTPException(400, "No trobo la línia a modificar.")
        if t == "eliminar_linia_pressupost":
            linies.pop(i)
        else:
            l = linies[i]
            for k in ("quantitat", "unitat", "cost_unitari", "preu_unitari", "descompte_pct", "referencia"):
                if a.get(k) is not None:
                    l[k] = a[k]
            if a.get("descripcio") and a.get("linia_index"):
                l["descripcio"] = a["descripcio"]
            if a.get("cost_unitari") is not None and a.get("preu_unitari") is None:
                l["preu_unitari"] = calc.r2(l["cost_unitari"] * (1 + (l["marge_pct"] or 0) / 100))
            l["marge_pct"] = calc.r2((l["preu_unitari"] / l["cost_unitari"] - 1) * 100) if l["cost_unitari"] else l["marge_pct"]
        m.put_pressupost(p["id"], {"linies": linies}, u)
        return {"text": f"Pressupost {p['numero']} actualitzat", "enllac": f"#/pressupost/{p['id']}"}
    if t == "afegir_linia_factura":
        linia = {"descripcio": a.get("descripcio") or a.get("text") or "Concepte", "quantitat": a.get("quantitat") or 1,
                 "preu_unitari": a.get("preu_unitari") or 0, "descompte_pct": a.get("descompte_pct") or 0}
        fac = db.row("SELECT id FROM factures WHERE feina_id = ? AND estat = 'esborrany' ORDER BY id DESC LIMIT 1", (fid,))
        if fac:
            with db.tx() as conn:
                conn.execute("INSERT INTO linies_factura(factura_id, descripcio, quantitat, preu_unitari, descompte_pct, origen_tipus) "
                             "VALUES (?,?,?,?,?,'manual')", (fac["id"], linia["descripcio"], linia["quantitat"],
                                                             linia["preu_unitari"], linia["descompte_pct"]))
            calc.recalcula_factura(fac["id"])
            fac_id = fac["id"]
        else:
            fac_id = m.post_factura(fid, {"linies_manuals": [linia]}, u)["id"]
        return {"text": "Línia afegida a l'esborrany de factura", "enllac": f"#/factura/{fac_id}"}
    if t == "afegir_despesa":
        m.post_despesa({"feina_id": fid, "proveidor": a.get("proveidor"), "concepte": a.get("descripcio") or a.get("text"),
                        "total": a.get("import_total"), "data": a.get("data"),
                        "partida_id": resol_partida(a.get("partida"), None) if a.get("partida") else None,
                        **({"facturable": a["facturable"]} if a.get("facturable") is not None else {})})
        return {"text": "Despesa afegida", "enllac": f"#/feina/{fid}/despeses"}
    if t == "afegir_missatge":
        m.post_missatge(fid, {"text": a.get("text") or a.get("descripcio"), "intern": bool(a.get("intern"))}, u)
        return {"text": "Nota interna desada" if a.get("intern") else "Missatge enviat al client", "enllac": f"#/feina/{fid}/missatges"}
    if t == "afegir_planning":
        post_planning(fid, {"titol": a.get("text") or a.get("descripcio"), "data_inici": a.get("data"), "data_fi": a.get("data_fi")}, u)
        return {"text": "Tasca afegida al planning", "enllac": f"#/feina/{fid}/planning"}
    if t == "canviar_estat_feina":
        if a.get("estat") not in ("pressupost", "acceptada", "en_curs", "acabada", "tancada", "cancellada"):
            raise HTTPException(400, "Estat no vàlid.")
        if a["estat"] == "tancada":
            m.tancar_feina(fid, {"forcar": True}, u)
        else:
            m.put_feina(fid, {"estat": a["estat"]}, u)
        return {"text": f"Feina en estat «{a['estat']}»", "enllac": f"#/feina/{fid}"}
    if t == "crear_feina":
        d = {"nom": a.get("descripcio") or a.get("text") or "Feina nova"}
        if a.get("feina_text"):
            obj = _paraules(a["feina_text"])
            c = next((c for c in db.rows("SELECT id, nom FROM clients") if obj and obj <= _paraules(c["nom"])), None)
            d["client_id"] = c["id"] if c else None
            if not c:
                d["client_nou"] = {"nom": a["feina_text"]}
        r = m.post_feina(d, u)
        return {"text": f"Feina {r['codi']} creada", "enllac": f"#/feina/{r['id']}"}
    raise HTTPException(400, "Acció desconeguda.")


@router.post("/api/assistent/executar")
def assistent_executar(data: dict = Body(...), u=Depends(usuari_actual)):
    resultats = []
    for a in data.get("accions") or []:
        try:
            resultats.append({"ok": True, **_executa(a, u)})
        except HTTPException as e:
            resultats.append({"ok": False, "text": f"{a.get('resum', a['tipus'])}: {e.detail}"})
    return {"resultats": resultats}


# =============================================================== planning

CAMPS_PLANNING = {"titol": str, "data_inici": str, "data_fi": str, "estat": str, "pct": int, "ordre": int}


@router.get("/api/feines/{fid}/planning")
def get_planning(fid: int, u=Depends(usuari_actual)):
    return db.rows("SELECT * FROM planning WHERE feina_id = ? ORDER BY ordre, COALESCE(data_inici, '9999'), id", (fid,))


@router.post("/api/feines/{fid}/planning")
def post_planning(fid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    m.feina_o_404(fid)
    d = m.pick(data, CAMPS_PLANNING)
    if not d.get("titol"):
        raise HTTPException(400, "Cal el nom de la tasca.")
    d.update({"feina_id": fid, "created_at": db.now(), "estat": d.get("estat") or "pendent", "pct": d.get("pct") or 0,
              "ordre": d.get("ordre") if d.get("ordre") is not None else (db.scalar("SELECT COALESCE(MAX(ordre),0)+1 FROM planning WHERE feina_id = ?", (fid,)))})
    return {"id": db.insert("planning", d)}


@router.put("/api/planning/{pid}")
def put_planning(pid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    t = m.cal(db.row("SELECT * FROM planning WHERE id = ?", (pid,)))
    d = m.pick(data, CAMPS_PLANNING)
    if d.get("estat") == "fet":
        d["pct"] = 100
    elif d.get("pct") == 100:
        d["estat"] = "fet"
    db.update("planning", pid, d)
    if d.get("estat") == "fet" and t["estat"] != "fet":
        m.missatge(t["feina_id"], f"Fase acabada: {t['titol']}.", "evolucio", autor="empresa")
    return {"ok": True}


@router.delete("/api/planning/{pid}")
def del_planning(pid: int, u=Depends(usuari_actual)):
    db.delete("planning", pid)
    return {"ok": True}


@router.post("/api/feines/{fid}/evolucio")
async def post_evolucio(fid: int, text: str = Form(""), fotos: list[UploadFile] = File(default=[]), u=Depends(usuari_actual)):
    """Publica l'evolució de la feina (text i fotos) al portal del client."""
    m.feina_o_404(fid)
    if not text.strip() and not fotos:
        raise HTTPException(400, "Escriu alguna cosa o afegeix una foto.")
    docs = []
    for f in fotos:
        contingut, mime = await _llegeix_imatge(f)
        did = m.guarda_fitxer(contingut, f.filename or "foto.jpg", fid, "foto", mime)
        db.update("documents", did, {"visible_client": 1})
        docs.append(did)
    if not docs:
        m.missatge(fid, text.strip(), "evolucio", autor="empresa")
    for i, did in enumerate(docs):
        db.insert("missatges", {"feina_id": fid, "autor": "empresa", "tipus": "evolucio",
                                "text": text.strip() if i == 0 and text.strip() else "📷", "intern": 0, "document_id": did,
                                "llegit": 1, "created_at": db.now()})
    return {"ok": True}


# =============================================================== valoracions

@router.get("/api/feines/{fid}/valoracions")
def get_valoracions(fid: int, u=Depends(usuari_actual)):
    return db.rows("SELECT * FROM valoracions WHERE feina_id = ? ORDER BY created_at DESC", (fid,))


# ========================================================= foto de material

@router.post("/api/pressupostos/{pid}/foto")
async def foto_material(pid: int, fitxer: UploadFile = File(...), u=Depends(usuari_actual)):
    p = m.cal(db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,)))
    contingut, mime = await _llegeix_imatge(fitxer)
    did = m.guarda_fitxer(contingut, fitxer.filename or "material.jpg", p["feina_id"], "material", mime)
    db.update("documents", did, {"visible_client": 1})
    return {"document_id": did}


# ============================================================== maqueta 3D

def model_per_defecte(amplada=2.5, llargada=2.0, alcada=2.5) -> dict:
    return {
        "estanca": {"nom": "Estança", "amplada": amplada, "llargada": llargada, "alcada": alcada},
        "obertures": [{"paret": "sud", "tipus": "porta", "posicio": 0.6, "amplada": 0.8, "alcada": 2.05, "alcada_terra": 0}],
        "elements": [],
        "materials": [
            {"id": "terra", "nom": "Porcellànic gris 60x60", "tipus": "ceramica", "color": "#b9b4ad", "patro": "rajola",
             "mida_peca_cm": 60, "mida_peca_alt_cm": 60, "color_junta": "#9a958f", "brillant": False},
            {"id": "paret", "nom": "Pintura blanca", "tipus": "pintura", "color": "#f2f0eb", "patro": "llis", "brillant": False},
            {"id": "blanc", "nom": "Ceràmica blanca", "tipus": "ceramica", "color": "#ffffff", "patro": "llis", "brillant": True},
        ],
        "acabats": {"terra": "terra", "parets": "paret", "sostre": "paret", "zona_humida": None, "zona_humida_parets": [],
                    "zona_humida_alcada": None},
        "suposits": [],
    }


def _valida_model(model: dict) -> dict:
    try:
        return ai.ModelRender.model_validate(model).model_dump()
    except Exception as e:  # noqa: BLE001 - errors de validació de l'usuari
        raise HTTPException(400, f"Model 3D no vàlid: {str(e)[:300]}")


def _marca_fotos_visibles(model: dict, feina_id: int, visible: bool):
    if not visible:
        return
    for mat in model.get("materials", []):
        if mat.get("foto_document_id"):
            with db.tx() as conn:
                conn.execute("UPDATE documents SET visible_client = 1 WHERE id = ?", (mat["foto_document_id"],))


@router.get("/api/feines/{fid}/renders")
def get_renders(fid: int, u=Depends(usuari_actual)):
    return db.rows("SELECT id, titol, descripcio, visible_client, created_at, updated_at FROM renders WHERE feina_id = ? ORDER BY id DESC", (fid,))


@router.post("/api/feines/{fid}/renders")
async def post_render(fid: int, titol: str = Form("Proposta"), mesures: str = Form(""), descripcio: str = Form(""),
                      fotos: list[UploadFile] = File(default=[]), u=Depends(usuari_actual)):
    m.feina_o_404(fid)
    imatges, docs = [], []
    for f in fotos[:6]:
        contingut, mime = await _llegeix_imatge(f)
        imatges.append((contingut, mime))
        docs.append(m.guarda_fitxer(contingut, f.filename or "estat-inicial.jpg", fid, "foto", mime))
    avis = None
    if ai.disponible():
        model = ai.generar_render(imatges, mesures, descripcio)
    else:
        nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", mesures)][:3]
        nums = [n / 100 if n > 20 else n for n in nums]
        model = model_per_defecte(*nums) if nums else model_per_defecte()
        avis = "IA no configurada: s'ha creat una estança bàsica amb les mides; afegeix els elements a mà."
    now = db.now()
    rid = db.insert("renders", {"feina_id": fid, "titol": titol or "Proposta", "descripcio": f"{mesures}\n{descripcio}".strip(),
                                "model_json": json.dumps(model, ensure_ascii=False), "fotos_json": json.dumps(docs),
                                "created_at": now, "updated_at": now})
    return {"id": rid, "avis": avis}


@router.get("/api/renders/{rid}")
def get_render(rid: int, u=Depends(usuari_actual)):
    r = m.cal(db.row("SELECT * FROM renders WHERE id = ?", (rid,)))
    r["model"] = json.loads(r.pop("model_json"))
    r["fotos"] = json.loads(r.pop("fotos_json") or "[]")
    return r


@router.put("/api/renders/{rid}")
def put_render(rid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    r = m.cal(db.row("SELECT * FROM renders WHERE id = ?", (rid,)))
    d = m.pick(data, {"titol": str, "visible_client": bool})
    if "model" in data:
        model = _valida_model(data["model"])
        d["model_json"] = json.dumps(model, ensure_ascii=False)
    else:
        model = json.loads(r["model_json"])
    d["updated_at"] = db.now()
    db.update("renders", rid, d)
    visible = d.get("visible_client", r["visible_client"])
    _marca_fotos_visibles(model, r["feina_id"], bool(visible))
    if d.get("visible_client") and not r["visible_client"]:
        m.missatge(r["feina_id"], f"Hem compartit la maqueta 3D «{d.get('titol') or r['titol']}» de com quedarà.", "evolucio", autor="empresa")
    return get_render(rid, u)


@router.post("/api/renders/{rid}/ia")
def render_ia(rid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    r = m.cal(db.row("SELECT * FROM renders WHERE id = ?", (rid,)))
    if not (data.get("instruccio") or "").strip():
        raise HTTPException(400, "Explica quin canvi vols.")
    model = ai.modificar_render(json.loads(r["model_json"]), data["instruccio"])
    return put_render(rid, {"model": model}, u)


@router.delete("/api/renders/{rid}")
def del_render(rid: int, u=Depends(usuari_actual)):
    db.delete("renders", rid)
    return {"ok": True}


# ================================================================ anàlisi

def genera_analisi(fid: int) -> dict:
    dades = calc.analisi_feina(fid)
    text = {"resum": None, "be": dades["be"], "malament": dades["malament"], "propostes": dades["propostes"], "font": "dades"}
    if ai.disponible():
        try:
            text = {**ai.analisi_tancament(dades), "font": "ia"}
        except ai.IAError:
            pass
    db.insert("analisis", {"feina_id": fid, "dades_json": json.dumps(dades, ensure_ascii=False),
                           "text_json": json.dumps(text, ensure_ascii=False), "created_at": db.now()})
    return {"dades": dades, "text": text}


@router.get("/api/feines/{fid}/analisi")
def get_analisi(fid: int, u=Depends(usuari_actual)):
    m.feina_o_404(fid)
    a = db.row("SELECT * FROM analisis WHERE feina_id = ? ORDER BY id DESC LIMIT 1", (fid,))
    if a:
        return {"dades": json.loads(a["dades_json"]), "text": json.loads(a["text_json"]), "created_at": a["created_at"]}
    return {"dades": calc.analisi_feina(fid), "text": None, "created_at": None}


@router.post("/api/feines/{fid}/analisi")
def post_analisi(fid: int, u=Depends(usuari_actual)):
    m.feina_o_404(fid)
    return genera_analisi(fid)


# ================================================================ factures

@router.post("/api/factures/{fid}/bloqueja")
def bloqueja_factura(fid: int, data: dict = Body(...), u=Depends(usuari_actual)):
    m.cal(db.row("SELECT id FROM factures WHERE id = ?", (fid,)))
    db.update("factures", fid, {"bloqueja": 1 if data.get("bloqueja") else 0})
    return {"ok": True}


# ================================================================ impostos

@router.get("/api/impostos/estimacio")
def estimacio(any: int | None = None, trimestre: int | None = None, u=Depends(admin)):
    avui = date.today()
    return calc.estimacio_trimestre(any or avui.year, trimestre or (avui.month - 1) // 3 + 1)


def _periode(any_: int, trimestre: int | None):
    r = calc.resum_impostos(any_, trimestre)
    return r["periode"]["inici"], r["periode"]["fi"]


def _nom_fitxer(text: str) -> str:
    return re.sub(r"[^\w.-]+", "_", text or "")[:60].strip("_") or "document"


@router.get("/api/gestor/paquet")
def paquet_gestor(any: int | None = None, trimestre: int | None = None, u=Depends(admin)):
    """ZIP amb factures emeses i rebudes, tiquets, llibres de registre i estimació d'impostos."""
    avui = date.today()
    any_ = any or avui.year
    ini, fi = _periode(any_, trimestre)
    etiqueta = f"{any_}-{trimestre}T" if trimestre else str(any_)
    s = db.settings()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        emeses = db.rows("SELECT f.*, c.nom AS client_nom, c.nif AS client_nif FROM factures f LEFT JOIN clients c ON c.id = f.client_id "
                         "WHERE f.numero IS NOT NULL AND f.data >= ? AND f.data < ? ORDER BY f.serie, f.numero", (ini, fi))
        out = io.StringIO()
        w = csv.writer(out, delimiter=";")
        w.writerow(["Data", "Número", "Client", "NIF", "Base", "IVA %", "Quota IVA", "IRPF %", "Retenció", "Total", "Estat", "Rectifica"])
        for f in emeses:
            orig = db.scalar("SELECT codi FROM factures WHERE id = ?", (f["rectifica_id"],)) if f["rectifica_id"] else ""
            w.writerow([f["data"], f["codi"], f["client_nom"], f["client_nif"], _n(f["base"]), _n(f["iva_pct"]), _n(f["iva_import"]),
                        _n(f["irpf_pct"]), _n(f["irpf_import"]), _n(f["total"]), f["estat"], orig])
            z.writestr(f"factures_emeses/{_nom_fitxer(f['codi'])}.html", printing.factura(f["id"]))
        z.writestr("llibre_factures_emeses.csv", "﻿" + out.getvalue())

        rebudes = db.rows("SELECT d.*, p.nom AS partida, fe.codi AS feina FROM despeses d LEFT JOIN partides p ON p.id = d.partida_id "
                          "LEFT JOIN feines fe ON fe.id = d.feina_id WHERE d.data >= ? AND d.data < ? ORDER BY d.data", (ini, fi))
        out = io.StringIO()
        w = csv.writer(out, delimiter=";")
        w.writerow(["Data", "Tipus", "Proveïdor", "NIF", "Número", "Concepte", "Base", "IVA %", "Quota IVA", "Total", "Partida", "Feina", "Fitxer"])
        for d in rebudes:
            fitxer = ""
            if d["document_id"]:
                doc = db.row("SELECT * FROM documents WHERE id = ?", (d["document_id"],))
                path = db.DOCS_DIR / doc["fitxer"] if doc else None
                if path and path.exists():
                    fitxer = f"despeses/{d['data']}_{_nom_fitxer(d['proveidor'])}_{d['id']}{Path(doc['fitxer']).suffix}"
                    z.write(path, fitxer)
            w.writerow([d["data"], d["tipus_doc"], d["proveidor"], d["proveidor_nif"], d["num_document"], d["concepte"], _n(d["base"]),
                        _n(d["iva_pct"]), _n(d["iva_import"]), _n(d["total"]), d["partida"], d["feina"], fitxer])
        z.writestr("llibre_factures_rebudes.csv", "﻿" + out.getvalue())

        imp = calc.resum_impostos(any_, trimestre)
        linies = [f"Resum d'impostos {etiqueta} — {s.get('empresa_nom', '')} {s.get('empresa_nif', '')}", "",
                  f"IVA repercutit: {_n(imp['iva_repercutit'])} €", f"IVA suportat: {_n(imp['iva_suportat'])} €",
                  f"Resultat IVA (303): {_n(imp['resultat_iva'])} €", f"Retencions IRPF suportades: {_n(imp['retencions_irpf'])} €",
                  f"Ingressos (base): {_n(imp['ingressos'])} €", f"Despeses (base): {_n(imp['despeses'])} €"]
        if trimestre:
            est = calc.estimacio_trimestre(any_, trimestre)
            if "irpf_130" in est["real"]:
                linies.append(f"Estimació pagament fraccionat IRPF (130): {_n(est['real']['irpf_130'])} €")
        if imp["avis_tiquets"]:
            linies += ["", "Avís: " + imp["avis_tiquets"]]
        linies += ["", f"{len(emeses)} factures emeses i {len(rebudes)} despeses. Les factures emeses van en HTML (es poden obrir i desar en PDF).",
                   "Document generat automàticament: cal revisar-lo abans de presentar cap declaració."]
        z.writestr("LLEGEIX-ME.txt", "\n".join(linies))
    nom = f"gestor_{etiqueta}.zip"
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nom}"'})


def _n(v) -> str:
    return f"{(v or 0):.2f}".replace(".", ",")


# ========================================================= portal (client)

def _doc_visible(doc: dict, feina_id: int) -> bool:
    if doc["feina_id"] != feina_id:
        return False
    if doc["visible_client"]:
        return True
    return bool(db.scalar("SELECT 1 FROM linies_pressupost lp JOIN pressupostos p ON p.id = lp.pressupost_id "
                          "WHERE lp.foto_document_id = ? AND p.estat <> 'esborrany'", (doc["id"],)))


@router.get("/p/{token}/fitxer/{did}")
def portal_fitxer(token: str, did: int):
    f = m._feina_token(token)
    d = m.cal(db.row("SELECT * FROM documents WHERE id = ?", (did,)))
    if not _doc_visible(d, f["id"]):
        raise HTTPException(404, "No trobat.")
    path = (db.DOCS_DIR / d["fitxer"]).resolve()
    if not str(path).startswith(str(db.DOCS_DIR.resolve())) or not path.exists():
        raise HTTPException(404, "No trobat.")
    return FileResponse(path, media_type=d["mime"] or None)


@router.get("/api/portal/{token}/renders/{rid}")
def portal_render(token: str, rid: int):
    f = m._feina_token(token)
    r = m.cal(db.row("SELECT * FROM renders WHERE id = ? AND feina_id = ? AND visible_client = 1", (rid, f["id"])))
    return {"id": r["id"], "titol": r["titol"], "model": json.loads(r["model_json"])}


@router.post("/api/portal/{token}/factures/{fid}/pagat")
def portal_pagat(token: str, fid: int, data: dict = Body(default={})):
    f = m._feina_token(token)
    fa = m.cal(db.row("SELECT * FROM factures WHERE id = ? AND feina_id = ? AND estat = 'emesa'", (fid, f["id"])))
    metode = "Bizum" if data.get("metode") == "bizum" else "transferència"
    db.update("factures", fid, {"pagament_notificat_at": db.now()})
    m.missatge(f["id"], f"El client indica que ha pagat la factura {fa['codi']} ({printing.eur(fa['total'])}) per {metode}. "
                        "Cal comprovar l'ingrés i marcar-la com a cobrada.", "pagament", autor="client", ref_tipus="factura", ref_id=fid)
    return {"ok": True}


@router.post("/api/portal/{token}/valoracions")
def portal_valoracio(token: str, data: dict = Body(...)):
    f = m._feina_token(token)
    try:
        punts = int(data.get("puntuacio"))
    except (TypeError, ValueError):
        punts = 0
    if not 1 <= punts <= 5:
        raise HTTPException(400, "Tria una puntuació de 1 a 5 estrelles.")
    comentari = (data.get("comentari") or "").strip()[:2000]
    db.insert("valoracions", {"feina_id": f["id"], "puntuacio": punts, "comentari": comentari, "created_at": db.now()})
    m.missatge(f["id"], f"Valoració del client: {'★' * punts}{'☆' * (5 - punts)} {comentari}".strip(), "valoracio", autor="client")
    return {"ok": True}


@router.post("/api/portal/{token}/peticions")
def portal_peticio(token: str, data: dict = Body(...)):
    f = m._feina_token(token)
    text = (data.get("text") or "").strip()[:4000]
    if not text:
        raise HTTPException(400, "Explica què necessites.")
    tipus = {"canvi": "Petició de canvi", "dubte": "Dubte", "incidencia": "Incidència"}.get(data.get("tipus"), "Petició")
    m.missatge(f["id"], f"{tipus}: {text}", "peticio", autor="client")
    return {"ok": True}
