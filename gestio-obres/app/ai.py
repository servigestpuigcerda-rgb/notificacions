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
    propostes = [p for a in db.rows("SELECT a.text_json FROM analisis a JOIN feines f ON f.id = a.feina_id "
                                    "WHERE (? IS NULL OR lower(f.tipus) = lower(?)) ORDER BY a.id DESC LIMIT 5", (tipus, tipus))
                 for p in json.loads(a["text_json"]).get("propostes", [])]
    return (f"Tarifes: {json.dumps(tarifes)}\n"
            f"Lliçons de les anàlisis de feines acabades: {json.dumps(propostes, ensure_ascii=False)}\n"
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


# ---------------------------------------------------------------- assistent

TIPUS_ACCIO = Literal["afegir_hores", "afegir_linia_pressupost", "modificar_linia_pressupost", "eliminar_linia_pressupost",
                      "afegir_linia_factura", "afegir_despesa", "afegir_missatge", "afegir_planning",
                      "canviar_estat_feina", "crear_feina"]


class AccioAssistent(BaseModel):
    tipus: TIPUS_ACCIO
    resum: str = Field(description="Què es farà, en una frase en català, per confirmar-ho amb l'usuari")
    feina_codi: Optional[str] = Field(default=None, description="Codi de la feina si la pots identificar a la llista")
    feina_text: Optional[str] = Field(default=None, description="Com ha anomenat l'usuari la feina o el client (literal)")
    pressupost_numero: Optional[str] = None
    linia_index: Optional[int] = Field(default=None, description="Número de línia (1 = primera) per modificar o eliminar")
    descripcio: Optional[str] = None
    referencia: Optional[str] = Field(default=None, description="Referència o model del material")
    partida: Optional[str] = Field(default=None, description="Nom exacte d'una partida")
    quantitat: Optional[float] = None
    unitat: Optional[str] = None
    cost_unitari: Optional[float] = None
    preu_unitari: Optional[float] = None
    descompte_pct: Optional[float] = None
    hores: Optional[float] = None
    data: Optional[str] = Field(default=None, description="AAAA-MM-DD")
    treballador_text: Optional[str] = Field(default=None, description="Nom del treballador tal com l'ha dit l'usuari")
    facturable: Optional[bool] = None
    proveidor: Optional[str] = None
    import_total: Optional[float] = Field(default=None, description="Import amb IVA d'una despesa")
    text: Optional[str] = Field(default=None, description="Text del missatge, nota o tasca")
    intern: Optional[bool] = Field(default=None, description="true = nota interna que el client no veu")
    estat: Optional[str] = Field(default=None, description="pressupost, acceptada, en_curs, acabada, tancada")
    data_fi: Optional[str] = None


class RespostaAssistent(BaseModel):
    accions: List[AccioAssistent]
    dubtes: List[str] = Field(default=[], description="Què no està clar i cal preguntar")


SYSTEM_ASSISTENT = """Ets l'assistent d'una aplicació de gestió d'obres. L'usuari et diu (sovint dictat i informal) què vol fer
i tu ho converteixes en accions concretes. No executes res: l'usuari les revisarà i confirmarà.
Regles:
- Una ordre pot generar diverses accions.
- Identifica la feina pel codi de la llista quan sigui clar. Si l'usuari parla d'un client o d'una adreça que no surt a la llista,
  posa el text literal a "feina_text" (el sistema el buscarà) i deixa feina_codi buit.
- "Afegeix X al pressupost": afegir_linia_pressupost. Si el pressupost ja està acceptat, igualment proposa-la (el sistema crearà un fora de pressupost).
- Per modificar o eliminar línies fes servir linia_index de la llista de línies que et dono.
- Mà d'obra: unitat "h" i partida de mà d'obra. Si no et diuen preu, deixa'l buit (s'aplicaran les tarifes).
- Avui és {avui}. Converteix "ahir", "dilluns"... a dates.
- No inventis imports ni quantitats que no s'han dit; si falten, deixa-ho buit o pregunta-ho a "dubtes"."""


def _context_assistent(feina_id: int | None) -> str:
    feines = db.rows("SELECT id, codi, nom, tipus, estat FROM feines WHERE estat IN ('pressupost','acceptada','en_curs','acabada') "
                     "ORDER BY (id = ?) DESC, created_at DESC LIMIT 40", (feina_id or 0,))
    ctx = []
    for f in feines:
        d = {"codi": f["codi"], "nom": f["nom"], "tipus": f["tipus"], "estat": f["estat"]}
        if f["id"] == feina_id or len(ctx) < 12:
            ps = db.rows("SELECT id, numero, tipus, estat FROM pressupostos WHERE feina_id = ? ORDER BY id DESC LIMIT 3", (f["id"],))
            d["pressupostos"] = [{"numero": p["numero"], "tipus": p["tipus"], "estat": p["estat"],
                                  "linies": [f"{i}. {l['descripcio']} · {l['quantitat']:g} {l['unitat']} · {l['preu_unitari']:g} €"
                                             for i, l in enumerate(db.rows("SELECT * FROM linies_pressupost WHERE pressupost_id = ? "
                                                                           "ORDER BY ordre, id", (p["id"],)), 1)]} for p in ps]
            fe = db.rows("SELECT id, codi FROM factures WHERE feina_id = ? AND estat = 'esborrany'", (f["id"],))
            if fe:
                d["factures_esborrany"] = len(fe)
        ctx.append(d)
    partides = [p["nom"] for p in db.rows("SELECT nom FROM partides ORDER BY ordre")]
    actual = next((f["codi"] for f in feines if f["id"] == feina_id), None)
    return (f"Feina oberta a la pantalla ara mateix: {actual or 'cap'}\n"
            f"Partides: {json.dumps(partides, ensure_ascii=False)}\n"
            f"Feines obertes: {json.dumps(ctx, ensure_ascii=False)}\n")


def interpretar_ordre(text: str, feina_id: int | None = None) -> dict:
    if not text or len(text.strip()) < 3:
        raise IAError("No t'he entès. Digues què vols fer.")
    system = SYSTEM_ASSISTENT.replace("{avui}", db.today())
    content = _context_assistent(feina_id) + f"\nOrdre de l'usuari:\n\"\"\"\n{text.strip()}\n\"\"\""
    return _parse(RespostaAssistent, content, system, effort="medium").model_dump()


# -------------------------------------------------------------- maqueta 3D

PARET = Literal["nord", "sud", "est", "oest"]
TIPUS_ELEMENT = Literal["plat_dutxa", "banyera", "lavabo", "moble_lavabo", "wc", "bidet", "mampara", "mirall",
                        "armari_baix", "armari_alt", "taulell", "pica", "placa", "forn", "nevera", "rentadora",
                        "radiador", "prestatge", "taula", "cadira", "sofa", "llit", "illa", "columna", "altre"]


class MaterialRender(BaseModel):
    id: str = Field(description="Identificador curt, p. ex. m1")
    nom: str
    tipus: Literal["ceramica", "pintura", "fusta", "pedra", "metall", "vidre", "laminat", "altres"]
    color: str = Field(description="Color hexadecimal #rrggbb")
    patro: Literal["llis", "rajola", "llistons"] = "llis"
    mida_peca_cm: Optional[float] = Field(default=None, description="Amplada de la peça (rajola, llistó)")
    mida_peca_alt_cm: Optional[float] = None
    color_junta: Optional[str] = None
    brillant: bool = False
    article_id: Optional[int] = None
    foto_document_id: Optional[int] = None


class Obertura(BaseModel):
    paret: PARET
    tipus: Literal["porta", "finestra"]
    posicio: float = Field(description="Distància en metres des de l'inici de la paret fins al centre de l'obertura")
    amplada: float
    alcada: float
    alcada_terra: float = 0


class ElementRender(BaseModel):
    id: str
    tipus: TIPUS_ELEMENT
    nom: str
    paret: Optional[PARET] = Field(default=None, description="Paret on està recolzat; buit si està al mig")
    posicio: Optional[float] = Field(default=None, description="Metres des de l'inici de la paret fins al centre de l'element")
    x: Optional[float] = Field(default=None, description="Només si no té paret: centre en metres des de la paret oest")
    y: Optional[float] = Field(default=None, description="Només si no té paret: centre en metres des de la paret sud")
    amplada: float
    fondaria: float
    alcada: float
    alcada_terra: float = 0
    material_id: Optional[str] = None


class Acabats(BaseModel):
    terra: Optional[str] = Field(default=None, description="id de material")
    parets: Optional[str] = None
    sostre: Optional[str] = None
    zona_humida: Optional[str] = Field(default=None, description="Material d'una zona diferenciada (p. ex. dutxa)")
    zona_humida_parets: List[PARET] = []
    zona_humida_alcada: Optional[float] = None


class Estanca(BaseModel):
    nom: str
    amplada: float = Field(description="Metres, eix est-oest (paret sud i nord)")
    llargada: float = Field(description="Metres, eix nord-sud (paret oest i est)")
    alcada: float


class ModelRender(BaseModel):
    estanca: Estanca
    obertures: List[Obertura] = []
    elements: List[ElementRender] = []
    materials: List[MaterialRender]
    acabats: Acabats
    suposits: List[str] = Field(default=[], description="Mides o posicions suposades que cal confirmar")


SYSTEM_RENDER = """Ets un interiorista tècnic. A partir de fotos de l'estat actual, les mides i la descripció del resultat desitjat,
defineixes una maqueta 3D senzilla de l'estança TAL COM QUEDARÀ un cop acabada la feina.
Sistema de coordenades:
- La paret sud és la de y=0 i la nord la de y=llargada; l'oest és x=0 i l'est x=amplada.
- Situa la porta principal a la paret sud si no se sap.
- "posicio" a les parets sud i nord es mesura des de l'oest; a les parets est i oest, des del sud.
- Els elements recolzats a una paret porten "paret" i "posicio"; la fondària és perpendicular a la paret.
Regles:
- Respecta les mides donades. Les que no tinguis, estima-les de les fotos i posa-ho a "suposits".
- Fes servir mides reals estàndard (lavabo 60x45, plat dutxa 140x80 o la mida dita, vàter 37x65...).
- Defineix materials realistes amb colors hexadecimals; per a rajoles indica patró "rajola" i la mida de la peça.
- Si hi ha articles del catàleg amb foto que encaixen, posa article_id i foto_document_id."""


def _materials_cataleg() -> list:
    return db.rows("SELECT a.id AS article_id, a.nom, a.unitat, d.id AS foto_document_id FROM articles a "
                   "LEFT JOIN documents d ON d.id = (SELECT lp.foto_document_id FROM linies_pressupost lp "
                   "WHERE lp.article_id = a.id AND lp.foto_document_id IS NOT NULL ORDER BY lp.id DESC LIMIT 1) "
                   "WHERE a.actiu = 1 ORDER BY a.nom LIMIT 150")


def generar_render(fotos: list, mesures: str, descripcio: str) -> dict:
    """fotos: [(bytes, mime)]"""
    blocs = []
    for contingut, mime in fotos[:6]:
        blocs.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                                                  "data": base64.standard_b64encode(contingut).decode()}})
    text = (f"Mides i observacions: {mesures or '(no n’hi ha; estima-les)'}\n"
            f"Resultat desitjat: {descripcio or '(el que es dedueixi del pressupost)'}\n"
            f"Catàleg de materials: {json.dumps(_materials_cataleg(), ensure_ascii=False)}")
    blocs.append({"type": "text", "text": text})
    return _parse(ModelRender, blocs, SYSTEM_RENDER, effort="high", max_tokens=32000).model_dump()


def modificar_render(model: dict, instruccio: str) -> dict:
    content = (f"Model actual: {json.dumps(model, ensure_ascii=False)}\n"
               f"Catàleg de materials: {json.dumps(_materials_cataleg(), ensure_ascii=False)}\n"
               f"Canvi demanat: {instruccio}\nTorna el model complet amb el canvi aplicat.")
    return _parse(ModelRender, content, SYSTEM_RENDER, effort="medium", max_tokens=32000).model_dump()


# ------------------------------------------------------------ anàlisi final

class AnalisiIA(BaseModel):
    resum: str = Field(description="Valoració global de la feina en 2-3 frases")
    be: List[str] = Field(description="Què ha anat bé")
    malament: List[str] = Field(description="Què ha fallat o es pot millorar")
    propostes: List[str] = Field(description="Canvis concrets per al proper pressupost d'aquest tipus de feina")


def analisi_tancament(dades: dict) -> dict:
    content = ("Dades objectives de la feina acabada (sense dades personals):\n"
               f"{json.dumps({k: v for k, v in dades.items() if k != 'comentaris_client'}, ensure_ascii=False)}\n"
               f"Comentaris del client: {json.dumps(dades.get('comentaris_client', []), ensure_ascii=False)}\n"
               "Fes l'anàlisi de tancament: què ha anat bé, què ha fallat i propostes concretes (amb xifres) per al proper pressupost.")
    return _parse(AnalisiIA, content, "Ets un cap d'obra i gestor que analitza la rendibilitat de les feines acabades.",
                  effort="high").model_dump()
