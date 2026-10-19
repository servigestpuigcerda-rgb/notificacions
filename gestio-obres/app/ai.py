"""Funcions d'intel·ligència artificial (Claude API).

- Lectura de tiquets, albarans i factures de proveïdor a partir d'una foto o PDF.
- Elaboració d'un pressupost a partir d'una explicació dictada.
- Revisió d'un pressupost amb l'historial.

Protecció de dades: a la IA NO s'envien mai dades del client (nom, NIF, adreça,
contacte). Només s'envien la imatge del document del proveïdor, el text que
dictes, el catàleg d'articles i xifres agregades de l'historial.
Cal la variable d'entorn ANTHROPIC_API_KEY.
"""
import base64
import json
import os
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from . import calc, db, learning

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class IAError(Exception):
    pass


def disponible() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and db.setting("ia_activa", "1") == "1"


def _client():
    if not disponible():
        raise IAError("La IA no està configurada (falta ANTHROPIC_API_KEY o està desactivada a Configuració).")
    import anthropic
    return anthropic.Anthropic()


def _parse(output_format, content, system: str, effort: str = "medium", max_tokens: int = 16000):
    import anthropic
    client = _client()
    try:
        resp = client.beta.messages.parse(
            model=db.setting("ia_model", "claude-opus-5-5"),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=output_format,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise IAError("La clau de l'API d'Anthropic no és vàlida.")
    except anthropic.RateLimitError:
        raise IAError("Massa peticions a la IA. Torna-ho a provar d'aquí a un minut.")
    except anthropic.APIStatusError as e:
        raise IAError(f"Error del servei d'IA ({e.status_code}).")
    except anthropic.APIConnectionError:
        raise IAError("No s'ha pogut connectar amb el servei d'IA. Comprova la connexió.")
    if resp.stop_reason == "refusal":
        raise IAError("La IA no ha pogut processar aquesta petició.")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise IAError("La resposta de la IA ha quedat incompleta. Torna-ho a provar.")
    return resp.parsed_output


# ------------------------------------------------------------------ tiquets

class LiniaDocument(BaseModel):
    descripcio: str
    quantitat: Optional[float] = None
    preu_unitari: Optional[float] = None
    import_linia: Optional[float] = None


class DadesDocument(BaseModel):
    tipus_doc: Literal["tiquet", "factura", "albara"]
    proveidor: Optional[str] = None
    proveidor_nif: Optional[str] = None
    num_document: Optional[str] = None
    data: Optional[str] = Field(default=None, description="Format AAAA-MM-DD")
    concepte: str = Field(description="Resum curt del que s'ha comprat, en català")
    linies: List[LiniaDocument] = []
    base: Optional[float] = None
    iva_pct: Optional[float] = None
    iva_import: Optional[float] = None
    total: Optional[float] = None
    partida_suggerida: Optional[str] = Field(default=None, description="Nom exacte d'una de les partides donades")
    feina_suggerida_codi: Optional[str] = Field(default=None, description="Codi d'una feina oberta si el document hi fa referència")
    confianca: float = Field(description="0 a 1: seguretat global en la lectura")
    avisos: List[str] = Field(default=[], description="Problemes detectats: il·legible, suma que no quadra, falta NIF...")


SYSTEM_TIQUET = """Ets l'assistent administratiu d'una empresa de reformes i serveis a Catalunya.
Llegeixes fotos de tiquets, albarans i factures de proveïdors i n'extreus les dades amb precisió.
Regles:
- Imports en euros amb punt decimal. Si només hi ha el total amb IVA inclòs, calcula la base i l'IVA.
- Comprova que base + IVA = total; si no quadra, explica-ho a "avisos".
- Si hi ha diversos tipus d'IVA, posa l'iva_pct majoritari i avisa-ho.
- Un albarà sense preus: deixa els imports buits i llista el material a "linies".
- No inventis dades: si un camp no es llegeix, deixa'l buit i baixa la confiança.
- La partida suggerida ha de ser exactament un dels noms de partida que et donen."""


def llegir_document(contingut: bytes, mime: str) -> dict:
    partides = [p["nom"] for p in db.rows("SELECT nom FROM partides ORDER BY ordre")]
    feines = [{"codi": f["codi"], "nom": f["nom"], "tipus": f["tipus"]} for f in learning.feina_probable_per_despesa()]
    proveidors = db.rows("SELECT a.proveidor, p.nom AS partida FROM aprenentatge_proveidors a "
                         "JOIN partides p ON p.id = a.partida_id ORDER BY usos DESC LIMIT 40")
    b64 = base64.standard_b64encode(contingut).decode()
    if mime == "application/pdf":
        bloc = {"type": "document", "source": {"type": "base64", "media_type": mime, "data": b64}}
    else:
        bloc = {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}
    context = (f"Partides disponibles: {json.dumps(partides, ensure_ascii=False)}\n"
               f"Feines obertes: {json.dumps(feines, ensure_ascii=False)}\n"
               f"Partida habitual per proveïdor (après de l'historial): {json.dumps(proveidors, ensure_ascii=False)}\n"
               "Extreu les dades d'aquest document.")
    dades = _parse(DadesDocument, [bloc, {"type": "text", "text": context}], SYSTEM_TIQUET, effort="medium")
    res = dades.model_dump()
    # Completar amb el que hem après
    part = db.row("SELECT id, nom FROM partides WHERE nom = ?", (res.get("partida_suggerida"),))
    apresa = learning.partida_proveidor(res.get("proveidor"))
    if apresa:
        res["partida_id"] = apresa
    elif part:
        res["partida_id"] = part["id"]
    if res.get("feina_suggerida_codi"):
        f = db.row("SELECT id FROM feines WHERE codi = ?", (res["feina_suggerida_codi"],))
        res["feina_id"] = f["id"] if f else None
    if res.get("total") and res.get("base") is None and res.get("iva_pct") is not None:
        res["base"] = calc.r2(res["total"] / (1 + res["iva_pct"] / 100))
        res["iva_import"] = calc.r2(res["total"] - res["base"])
    return res


# ------------------------------------------------------------- pressupostos

class LiniaProposta(BaseModel):
    descripcio: str = Field(description="Descripció clara per al client, en català")
    partida: str = Field(description="Nom exacte d'una de les partides donades")
    quantitat: float
    unitat: str = Field(description="h, u, m, m2, m3, kg, l, ml, pa (partida alçada)...")
    article_id: Optional[int] = Field(default=None, description="id de l'article del catàleg si n'hi ha un que encaixa")
    cost_unitari: float = Field(description="Cost per a l'empresa, sense IVA")
    preu_unitari: float = Field(description="Preu de venda al client, sense IVA")
    justificacio: Optional[str] = Field(default=None, description="D'on surt la quantitat o el preu (breu)")


class PropostaPressupost(BaseModel):
    titol: str
    tipus_feina: Optional[str] = Field(default=None, description="Categoria curta: bany, cuina, electricitat, pintura...")
    linies: List[LiniaProposta]
    hipotesis: List[str] = Field(default=[], description="Suposicions fetes per falta d'informació")
    preguntes: List[str] = Field(default=[], description="Què cal confirmar amb el client o mesurar")
    avisos: List[str] = Field(default=[], description="Riscos: hores justes, material que sol faltar, permisos...")
    notes_client: Optional[str] = Field(default=None, description="Text breu per al client: què inclou i què no")


SYSTEM_PRESSUPOST = """Ets un cap d'obra amb molta experiència que prepara pressupostos per a una empresa
de reformes i serveis a Catalunya. A partir de l'explicació (sovint dictada, informal) proposes les línies del pressupost.
Regles:
- Separa mà d'obra (en hores, unitat "h", partida de mà d'obra) del material i de les subcontractes.
- Fes servir els articles del catàleg quan encaixin (indica article_id i respecta el seu cost i preu).
- Per a la mà d'obra fes servir les tarifes donades. Per al material sense article, estima preus de mercat raonables a Catalunya.
- Aplica el marge per defecte al material si no tens preu de venda.
- Fes servir l'historial: si les feines semblants van necessitar més hores o material del previst, corregeix-ho ara i explica-ho a "avisos".
- No oblidis el que se sol oblidar: protecció i neteja, runa i contenidor, desplaçaments, petit material, proves.
- No inventis mides: si falten, fes una hipòtesi raonable i afegeix la pregunta per confirmar-la.
- Descripcions entenedores per al client, en català."""


def _context_pressupost(text: str, tipus: str | None) -> str:
    partides = db.rows("SELECT nom, tipus FROM partides ORDER BY ordre")
    articles = db.rows("SELECT id, codi, nom, unitat, cost, marge_pct, preu, descompte_pct FROM articles "
                       "WHERE actiu = 1 ORDER BY nom LIMIT 400")
    for a in articles:
        a["preu_venda"] = calc.preu_article(a)
    hist = learning.desviacions(tipus) if tipus else learning.desviacions()
    hist.pop("mostres", None)
    semblants = learning.pressupostos_semblants(text, tipus, limit=4)
    tarifes = {
        "cost_hora": db.setting_float("cost_hora_defecte", 25),
        "preu_hora": db.setting_float("preu_hora_defecte", 38),
        "marge_defecte_pct": db.setting_float("marge_defecte", 20),
    }
    return (f"Tarifes: {json.dumps(tarifes)}\n"
            f"Partides: {json.dumps(partides, ensure_ascii=False)}\n"
            f"Catàleg d'articles: {json.dumps(articles, ensure_ascii=False)}\n"
            f"Desviació històrica (ràtio real/pressupostat; >1 vol dir que ens quedem curts): {json.dumps(hist, ensure_ascii=False)}\n"
            f"Pressupostos semblants de l'historial (amb hores i cost reals si la feina és acabada): "
            f"{json.dumps(semblants, ensure_ascii=False)}\n")


def proposar_pressupost(text: str, tipus: str | None = None) -> dict:
    if not text or len(text.strip()) < 10:
        raise IAError("Explica una mica més la feina per poder fer el pressupost.")
    content = _context_pressupost(text, tipus) + f"\nExplicació de la feina:\n\"\"\"\n{text.strip()}\n\"\"\""
    proposta = _parse(PropostaPressupost, content, SYSTEM_PRESSUPOST, effort="high", max_tokens=32000)
    res = proposta.model_dump()
    noms = {p["nom"]: p["id"] for p in db.rows("SELECT id, nom FROM partides")}
    ids_articles = {a["id"] for a in db.rows("SELECT id FROM articles")}
    for l in res["linies"]:
        l["partida_id"] = noms.get(l["partida"])
        if l.get("article_id") not in ids_articles:
            l["article_id"] = None
    return res


class RevisioIA(BaseModel):
    resum: str = Field(description="Valoració general en dues frases")
    avisos: List[str] = Field(description="Errors o omissions concretes")
    suggeriments: List[str] = Field(description="Canvis proposats (afegir, treure, ajustar)")


def revisar_pressupost_ia(pressupost_id: int) -> dict:
    p = db.row("SELECT p.titol, p.descompte_pct, p.text_origen, f.tipus FROM pressupostos p "
               "JOIN feines f ON f.id = p.feina_id WHERE p.id = ?", (pressupost_id,))
    t = calc.totals_pressupost(pressupost_id)
    revisio = learning.revisar_pressupost(pressupost_id)
    linies = [{k: l[k] for k in ("descripcio", "quantitat", "unitat", "cost_unitari", "preu_unitari", "descompte_pct")}
              for l in t["linies"]]
    content = (f"Pressupost: {json.dumps({'titol': p['titol'], 'tipus': p['tipus'], 'explicacio': p['text_origen'], 'descompte_global': p['descompte_pct']}, ensure_ascii=False)}\n"
               f"Línies: {json.dumps(linies, ensure_ascii=False)}\n"
               f"Totals: {json.dumps(revisio['totals'])}\n"
               f"Historial: {json.dumps(revisio['historial'], ensure_ascii=False)}\n"
               f"Semblants: {json.dumps(revisio['semblants'], ensure_ascii=False)}\n"
               "Revisa'l: què falta, què sembla curt d'hores o de material, errors de preu o quantitat.")
    return _parse(RevisioIA, content, SYSTEM_PRESSUPOST, effort="high").model_dump()
