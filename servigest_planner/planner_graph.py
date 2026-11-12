"""Herramientas de Microsoft Planner (Microsoft Graph) para el conector MCP de Servigest.

Herramientas:
  planner_planes           planes del usuario con sus columnas (buckets)
  planner_tareas           tareas de un plan (de cualquier persona), con responsables y columna por nombre
  planner_crear_tarea      crear tarea con responsables, fecha, prioridad, descripción y checklist
  planner_modificar_tarea  cambiar título, responsables, fechas, avance, prioridad, columna, descripción, checklist
  planner_comentarios      leer los comentarios de una tarea
  planner_comentar         escribir un comentario en una tarea

Todo se hace con el token DELEGADO de quien ha iniciado sesión: cada persona ve solo los planes
de los grupos de Microsoft 365 a los que pertenece.

El servidor debe dar un objeto `graph` con:
    get(ruta_o_url, params=None, headers=None) -> dict
    post(ruta, json=None, headers=None) -> dict        (dict vacío si Graph responde 204)
    patch(ruta, json=None, headers=None) -> dict       (dict vacío si Graph responde 204)
que lancen una excepción con .status y .code si Graph devuelve error (o GraphError de este módulo).
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date
from typing import Any, Callable

PRIORIDADES = {"urgente": 1, "importante": 3, "media": 5, "normal": 5, "baja": 9}
PRIORIDAD_NOMBRE = {0: "urgente", 1: "urgente", 2: "importante", 3: "importante", 4: "importante",
                    5: "media", 6: "media", 7: "media", 8: "baja", 9: "baja", 10: "baja"}
AVANCE = {"no iniciada": 0, "pendiente": 0, "en curso": 50, "en progreso": 50, "completada": 100, "hecha": 100}

MSG_PERMISO = ("Microsoft 365 ha denegado la operación. La app de Servigest necesita los permisos delegados "
               "Tasks.ReadWrite y Group.Read.All (y Group.ReadWrite.All para comentarios), con consentimiento "
               "del administrador; luego cada usuario debe volver a iniciar sesión.")


class GraphError(Exception):
    def __init__(self, status: int, code: str = "", mensaje: str = ""):
        super().__init__(f"{status} {code} {mensaje}".strip())
        self.status, self.code, self.mensaje = status, code, mensaje


class ErrorUsuario(Exception):
    """Error con un mensaje pensado para el usuario (se devuelve como {"error": ...})."""


def _es_permiso(e) -> bool:
    return getattr(e, "status", None) == 403 or getattr(e, "code", "") in ("Forbidden", "AccessDenied",
                                                                            "Authorization_RequestDenied")


def _es_no_encontrado(e) -> bool:
    return getattr(e, "status", None) == 404


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def _parece_id(v: str) -> bool:
    return len(v) >= 20 and re.fullmatch(r"[A-Za-z0-9_\-]+", v) is not None


def _todos(graph, ruta, params=None) -> list[dict]:
    res, url = [], ruta
    while url:
        d = graph.get(url, params=params)
        res.extend(d.get("value", []))
        url, params = d.get("@odata.nextLink"), None
    return res


def _fecha_graph(v: str) -> str | None:
    if v in ("", None):
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ErrorUsuario(f"Fecha «{v}» no válida: usa AAAA-MM-DD.")
    return f"{v}T10:00:00Z"   # mediodía en Madrid: evita que salga el día anterior por zona horaria


def _fecha_corta(v: str | None) -> str:
    return (v or "")[:10]


def _con_errores(fn):
    def envoltorio(*a, **k):
        try:
            return fn(*a, **k)
        except ErrorUsuario as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            if _es_permiso(e):
                return {"error": MSG_PERMISO}
            if _es_no_encontrado(e):
                return {"error": "No encontrado en Planner (puede que el id sea incorrecto o que no tengas "
                                 "acceso). Usa planner_planes / planner_tareas para obtener los ids."}
            raise
    envoltorio.__name__ = fn.__name__
    envoltorio.__doc__ = fn.__doc__
    return envoltorio


# ------------------------------------------------------------------------------------------
# Resolución de planes, columnas y personas
# ------------------------------------------------------------------------------------------

def _planes(graph) -> list[dict]:
    """Planes de los grupos del usuario (+ los compartidos con él), sin duplicados."""
    vistos: dict[str, dict] = {}
    for p in _todos(graph, "/me/planner/plans", {"$select": "id,title,owner,container"}):
        vistos[p["id"]] = p
    grupos = _todos(graph, "/me/memberOf/microsoft.graph.group",
                    {"$select": "id,displayName,groupTypes", "$top": 100})
    for g in grupos:
        if "Unified" not in (g.get("groupTypes") or []):
            continue
        try:
            for p in _todos(graph, f"/groups/{g['id']}/planner/plans", {"$select": "id,title,owner,container"}):
                p["_grupo"] = g.get("displayName", "")
                vistos.setdefault(p["id"], p)
        except Exception as e:  # noqa: BLE001
            if not (_es_permiso(e) or _es_no_encontrado(e)):
                raise
    return list(vistos.values())


def _grupo_del_plan(plan: dict) -> str:
    return (plan.get("container") or {}).get("containerId") or plan.get("owner", "")


def resolver_plan(graph, plan: str) -> dict:
    v = (plan or "").strip()
    if not v:
        raise ErrorUsuario("Falta el plan (nombre o id de planner_planes).")
    if _parece_id(v):
        try:
            return graph.get(f"/planner/plans/{v}", params={"$select": "id,title,owner,container"})
        except Exception as e:  # noqa: BLE001
            if not _es_no_encontrado(e):
                raise
    todos = _planes(graph)
    exactos = [p for p in todos if _norm(p["title"]) == _norm(v)]
    candidatos = exactos or [p for p in todos if _norm(v) in _norm(p["title"])]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise ErrorUsuario(f"No encuentro ningún plan «{v}». Usa planner_planes para ver los planes.")
    raise ErrorUsuario(f"«{v}» coincide con varios planes: " + "; ".join(p["title"] for p in candidatos)
                       + ". Indica el nombre exacto o el id.")


def _columnas(graph, plan_id: str) -> list[dict]:
    cols = _todos(graph, f"/planner/plans/{plan_id}/buckets", {"$select": "id,name,orderHint"})
    return sorted(cols, key=lambda c: c.get("orderHint", ""))


def resolver_columna(graph, plan_id: str, columna: str) -> dict:
    cols = _columnas(graph, plan_id)
    if not cols:
        raise ErrorUsuario("El plan no tiene columnas; créala antes en Planner.")
    if not columna:
        return cols[0]
    v = _norm(columna)
    c = [x for x in cols if x["id"] == columna or _norm(x["name"]) == v] or \
        [x for x in cols if v in _norm(x["name"])]
    if len(c) == 1:
        return c[0]
    nombres = ", ".join(x["name"] for x in cols)
    if not c:
        raise ErrorUsuario(f"No hay ninguna columna «{columna}» en el plan. Columnas: {nombres}.")
    raise ErrorUsuario(f"«{columna}» coincide con varias columnas ({', '.join(x['name'] for x in c)}). "
                       "Indica el nombre exacto.")


def _miembros(graph, grupo_id: str) -> list[dict]:
    return _todos(graph, f"/groups/{grupo_id}/members/microsoft.graph.user",
                  {"$select": "id,displayName,mail,userPrincipalName", "$top": 100})


def resolver_personas(graph, grupo_id: str, nombres: list[str]) -> list[dict]:
    """Nombre, parte del nombre o email -> miembro del grupo del plan. Solo miembros del grupo."""
    miembros = _miembros(graph, grupo_id)
    res = []
    for n in nombres:
        v = _norm(n)
        if not v:
            continue
        c = [m for m in miembros if v in (_norm(m.get("mail")), _norm(m.get("userPrincipalName")), m["id"].lower())]
        c = c or [m for m in miembros if _norm(m.get("displayName")) == v]
        c = c or [m for m in miembros if all(p in _norm(m.get("displayName")) for p in v.split())]
        if len(c) == 1:
            res.append(c[0])
        elif not c:
            raise ErrorUsuario(f"«{n}» no es miembro del grupo de este plan. En Planner solo se puede asignar "
                               "a miembros del grupo; añádelo antes en Teams/Outlook.")
        else:
            raise ErrorUsuario(f"«{n}» coincide con varias personas: "
                               + "; ".join(f"{m['displayName']} <{m.get('mail') or m.get('userPrincipalName')}>"
                                           for m in c) + ". Indica el email.")
    return res


def _nombres_usuarios(graph, grupo_id: str) -> dict[str, str]:
    try:
        return {m["id"]: m.get("displayName", "") for m in _miembros(graph, grupo_id)}
    except Exception:  # noqa: BLE001
        return {}


def _resumen_tarea(t: dict, nombres: dict, columnas: dict) -> dict:
    return {
        "id": t["id"],
        "titulo": t.get("title"),
        "columna": columnas.get(t.get("bucketId"), ""),
        "responsables": [nombres.get(uid, uid) for uid in (t.get("assignments") or {})],
        "avance": t.get("percentComplete", 0),
        "prioridad": PRIORIDAD_NOMBRE.get(t.get("priority", 5), "media"),
        "inicio": _fecha_corta(t.get("startDateTime")),
        "vence": _fecha_corta(t.get("dueDateTime")),
        "tiene_comentarios": bool(t.get("conversationThreadId")),
    }


# ------------------------------------------------------------------------------------------
# Herramientas
# ------------------------------------------------------------------------------------------

@_con_errores
def planner_planes(graph, con_columnas: bool = True) -> dict:
    planes = []
    for p in sorted(_planes(graph), key=lambda x: _norm(x["title"])):
        item = {"id": p["id"], "plan": p["title"]}
        if p.get("_grupo"):
            item["grupo"] = p["_grupo"]
        if con_columnas:
            item["columnas"] = [{"id": c["id"], "nombre": c["name"]} for c in _columnas(graph, p["id"])]
        planes.append(item)
    return {"total": len(planes), "planes": planes}


@_con_errores
def planner_tareas(graph, plan: str, responsable: str = "", columna: str = "", texto: str = "",
                   incluir_completadas: bool = False, vencidas: bool = False, maximo: int = 50) -> dict:
    p = resolver_plan(graph, plan)
    grupo = _grupo_del_plan(p)
    nombres = _nombres_usuarios(graph, grupo)
    cols = {c["id"]: c["name"] for c in _columnas(graph, p["id"])}
    tareas = _todos(graph, f"/planner/plans/{p['id']}/tasks")

    if responsable:
        uid = resolver_personas(graph, grupo, [responsable])[0]["id"]
        tareas = [t for t in tareas if uid in (t.get("assignments") or {})]
    if columna:
        cid = resolver_columna(graph, p["id"], columna)["id"]
        tareas = [t for t in tareas if t.get("bucketId") == cid]
    if texto:
        tareas = [t for t in tareas if _norm(texto) in _norm(t.get("title"))]
    if not incluir_completadas:
        tareas = [t for t in tareas if t.get("percentComplete", 0) < 100]
    if vencidas:
        hoy = date.today().isoformat()
        tareas = [t for t in tareas if t.get("dueDateTime") and t["dueDateTime"][:10] < hoy
                  and t.get("percentComplete", 0) < 100]

    tareas.sort(key=lambda t: (t.get("dueDateTime") or "9999", t.get("title") or ""))
    maximo = max(1, min(int(maximo or 50), 200))
    return {"plan": p["title"], "total": len(tareas),
            "tareas": [_resumen_tarea(t, nombres, cols) for t in tareas[:maximo]]}


def _checklist(items: list[str]) -> dict:
    return {str(uuid.uuid4()): {"@odata.type": "microsoft.graph.plannerChecklistItem",
                                "title": i[:100], "isChecked": False} for i in items if i.strip()}


def _prioridad(v: str) -> int:
    if v in ("", None):
        return 5
    n = PRIORIDADES.get(_norm(v))
    if n is None:
        raise ErrorUsuario("Prioridad no válida: usa urgente, importante, media o baja.")
    return n


def _avance(v) -> int:
    if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
        n = int(v)
    else:
        n = AVANCE.get(_norm(str(v)), -1)
    if n not in (0, 50, 100):
        raise ErrorUsuario("Avance no válido: usa 0 (no iniciada), 50 (en curso) o 100 (completada).")
    return n


ASIG = {"@odata.type": "#microsoft.graph.plannerAssignment", "orderHint": " !"}


@_con_errores
def planner_crear_tarea(graph, plan: str, titulo: str, columna: str = "", responsables: list[str] | None = None,
                        vence: str = "", inicio: str = "", prioridad: str = "", descripcion: str = "",
                        checklist: list[str] | None = None, confirmar: bool = False) -> dict:
    if not (titulo or "").strip():
        raise ErrorUsuario("Falta el título de la tarea.")
    p = resolver_plan(graph, plan)
    col = resolver_columna(graph, p["id"], columna)
    personas = resolver_personas(graph, _grupo_del_plan(p), responsables or [])
    cuerpo: dict[str, Any] = {"planId": p["id"], "bucketId": col["id"], "title": titulo.strip()[:255],
                              "priority": _prioridad(prioridad)}
    if vence:
        cuerpo["dueDateTime"] = _fecha_graph(vence)
    if inicio:
        cuerpo["startDateTime"] = _fecha_graph(inicio)
    if personas:
        cuerpo["assignments"] = {m["id"]: dict(ASIG) for m in personas}

    vista = {"plan": p["title"], "columna": col["name"], "titulo": cuerpo["title"],
             "responsables": [m["displayName"] for m in personas] or ["(sin asignar)"],
             "vence": vence or "(sin fecha)", "prioridad": PRIORIDAD_NOMBRE[cuerpo["priority"]],
             "descripcion": descripcion, "checklist": checklist or []}
    if not confirmar:
        return {"vista_previa": True, "accion": "Crear tarea en Planner", **vista,
                "instruccion": "Enseña esta vista previa al usuario y, solo si está de acuerdo, "
                               "vuelve a llamar con confirmar=true."}

    tarea = graph.post("/planner/tasks", json=cuerpo)
    aviso = None
    if descripcion or checklist:
        try:
            det = graph.get(f"/planner/tasks/{tarea['id']}/details")
            cambios: dict[str, Any] = {}
            if descripcion:
                cambios["description"] = descripcion
                cambios["previewType"] = "description"
            if checklist:
                cambios["checklist"] = _checklist(checklist)
            graph.patch(f"/planner/tasks/{tarea['id']}/details", json=cambios,
                        headers={"If-Match": det["@odata.etag"]})
        except Exception as e:  # noqa: BLE001
            aviso = f"La tarea se ha creado, pero no se ha podido guardar la descripción/checklist: {e}"
    res = {"creada": True, "id": tarea["id"], **vista}
    if aviso:
        res["aviso"] = aviso
    return res


@_con_errores
def planner_modificar_tarea(graph, tarea_id: str, titulo: str = "", columna: str = "",
                            anadir_responsables: list[str] | None = None,
                            quitar_responsables: list[str] | None = None,
                            vence: str = "", inicio: str = "", quitar_fecha: bool = False,
                            avance: str = "", prioridad: str = "", descripcion: str = "",
                            anadir_checklist: list[str] | None = None,
                            marcar_checklist: list[str] | None = None,
                            confirmar: bool = False) -> dict:
    t = graph.get(f"/planner/tasks/{tarea_id}")
    p = graph.get(f"/planner/plans/{t['planId']}", params={"$select": "id,title,owner,container"})
    grupo = _grupo_del_plan(p)
    nombres = _nombres_usuarios(graph, grupo)

    cambios: dict[str, Any] = {}
    texto: list[str] = []
    if titulo:
        cambios["title"] = titulo.strip()[:255]
        texto.append(f"título → «{cambios['title']}»")
    if columna:
        col = resolver_columna(graph, t["planId"], columna)
        cambios["bucketId"] = col["id"]
        texto.append(f"columna → {col['name']}")
    asign: dict[str, Any] = {}
    for m in resolver_personas(graph, grupo, anadir_responsables or []):
        asign[m["id"]] = dict(ASIG)
        texto.append(f"añadir responsable {m['displayName']}")
    for m in resolver_personas(graph, grupo, quitar_responsables or []):
        if m["id"] in (t.get("assignments") or {}):
            asign[m["id"]] = None
            texto.append(f"quitar responsable {m['displayName']}")
    if asign:
        cambios["assignments"] = asign
    if quitar_fecha:
        cambios["dueDateTime"] = None
        texto.append("quitar fecha de vencimiento")
    elif vence:
        cambios["dueDateTime"] = _fecha_graph(vence)
        texto.append(f"vence → {vence}")
    if inicio:
        cambios["startDateTime"] = _fecha_graph(inicio)
        texto.append(f"inicio → {inicio}")
    if avance not in ("", None):
        cambios["percentComplete"] = _avance(avance)
        texto.append(f"avance → {cambios['percentComplete']}%")
    if prioridad:
        cambios["priority"] = _prioridad(prioridad)
        texto.append(f"prioridad → {PRIORIDAD_NOMBRE[cambios['priority']]}")

    det_cambios: dict[str, Any] = {}
    det = None
    if descripcion or anadir_checklist or marcar_checklist:
        det = graph.get(f"/planner/tasks/{tarea_id}/details")
        if descripcion:
            det_cambios["description"] = descripcion
            texto.append("descripción nueva")
        chk: dict[str, Any] = {}
        if anadir_checklist:
            chk.update(_checklist(anadir_checklist))
            texto.append(f"añadir {len(anadir_checklist)} punto(s) al checklist")
        for item in marcar_checklist or []:
            hits = [k for k, v in (det.get("checklist") or {}).items() if _norm(item) in _norm(v.get("title"))]
            if len(hits) != 1:
                raise ErrorUsuario(f"No encuentro (o hay varios) puntos del checklist con «{item}».")
            chk[hits[0]] = {"@odata.type": "microsoft.graph.plannerChecklistItem", "isChecked": True}
            texto.append(f"marcar «{det['checklist'][hits[0]]['title']}»")
        if chk:
            det_cambios["checklist"] = chk

    if not cambios and not det_cambios:
        raise ErrorUsuario("No has indicado ningún cambio.")

    actual = _resumen_tarea(t, nombres, {c["id"]: c["name"] for c in _columnas(graph, t["planId"])})
    if not confirmar:
        return {"vista_previa": True, "plan": p["title"], "tarea": actual, "cambios": texto,
                "instruccion": "Enseña esta vista previa al usuario y, solo si está de acuerdo, "
                               "vuelve a llamar con confirmar=true."}

    if cambios:
        graph.patch(f"/planner/tasks/{tarea_id}", json=cambios, headers={"If-Match": t["@odata.etag"]})
    if det_cambios:
        graph.patch(f"/planner/tasks/{tarea_id}/details", json=det_cambios,
                    headers={"If-Match": det["@odata.etag"]})
    return {"modificada": True, "id": tarea_id, "titulo": cambios.get("title", t.get("title")), "cambios": texto}


# --- Comentarios: Planner los guarda como conversación del grupo de Microsoft 365 del plan ---

def _limpiar_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h or "")
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = re.sub(r"&nbsp;", " ", h).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\n{3,}", "\n\n", h).strip()


@_con_errores
def planner_comentarios(graph, tarea_id: str, maximo: int = 30) -> dict:
    t = graph.get(f"/planner/tasks/{tarea_id}")
    hilo = t.get("conversationThreadId")
    if not hilo:
        return {"tarea": t.get("title"), "total": 0, "comentarios": []}
    p = graph.get(f"/planner/plans/{t['planId']}", params={"$select": "id,title,owner,container"})
    posts = _todos(graph, f"/groups/{_grupo_del_plan(p)}/threads/{hilo}/posts",
                   {"$select": "id,createdDateTime,from,body"})
    posts.sort(key=lambda x: x.get("createdDateTime", ""))
    coms = [{"fecha": x.get("createdDateTime"),
             "autor": ((x.get("from") or {}).get("emailAddress") or {}).get("name", ""),
             "texto": _limpiar_html((x.get("body") or {}).get("content", ""))[:2000]} for x in posts]
    return {"tarea": t.get("title"), "total": len(coms), "comentarios": coms[-max(1, int(maximo)):]}


@_con_errores
def planner_comentar(graph, tarea_id: str, comentario: str, confirmar: bool = False) -> dict:
    if not (comentario or "").strip():
        raise ErrorUsuario("El comentario está vacío.")
    t = graph.get(f"/planner/tasks/{tarea_id}")
    p = graph.get(f"/planner/plans/{t['planId']}", params={"$select": "id,title,owner,container"})
    grupo = _grupo_del_plan(p)
    if not confirmar:
        return {"vista_previa": True, "plan": p["title"], "tarea": t.get("title"), "comentario": comentario,
                "aviso": "Lo verán todos los miembros del plan.",
                "instruccion": "Enseña esta vista previa al usuario y, solo si está de acuerdo, "
                               "vuelve a llamar con confirmar=true."}
    cuerpo = {"body": {"contentType": "text", "content": comentario}}
    hilo = t.get("conversationThreadId")
    if hilo:
        graph.post(f"/groups/{grupo}/threads/{hilo}/reply", json={"post": cuerpo})
    else:
        nuevo = graph.post(f"/groups/{grupo}/threads",
                           json={"topic": f"Comentarios sobre la tarea \"{t.get('title')}\"", "posts": [cuerpo]})
        graph.patch(f"/planner/tasks/{tarea_id}", json={"conversationThreadId": nuevo["id"]},
                    headers={"If-Match": t["@odata.etag"]})
    return {"comentado": True, "tarea": t.get("title")}


# ------------------------------------------------------------------------------------------
# Registro en el servidor MCP
# ------------------------------------------------------------------------------------------

def registrar(mcp, obtener_graph: Callable[[], Any]) -> None:
    @mcp.tool(name="planner_planes", description="""Lista los planes de Microsoft Planner del usuario (los de
        sus grupos de Microsoft 365) con sus columnas (buckets) e ids. Úsala cuando pregunte «qué planes tengo»
        o antes de crear una tarea si no sabes el plan. NO modifica nada.""")
    def _planes_tool(con_columnas: bool = True) -> dict:
        return planner_planes(obtener_graph(), con_columnas)

    @mcp.tool(name="planner_tareas", description="""Lista las tareas de un plan de Planner (de cualquier
        persona, no solo las mías): título, columna, responsables, avance, prioridad, fechas y si tiene
        comentarios. plan: nombre (o parte) o id de planner_planes. Filtros opcionales: responsable (nombre o
        email), columna, texto del título, incluir_completadas, vencidas=true (solo las que han pasado de fecha).
        Para «qué tareas tiene Carles en el plan X» o «qué hay vencido en Planner». NO modifica nada.""")
    def _tareas_tool(plan: str, responsable: str = "", columna: str = "", texto: str = "",
                     incluir_completadas: bool = False, vencidas: bool = False, maximo: int = 50) -> dict:
        return planner_tareas(obtener_graph(), plan, responsable, columna, texto,
                              incluir_completadas, vencidas, maximo)

    @mcp.tool(name="planner_crear_tarea", description="""Crea una tarea en un plan de Microsoft Planner y la
        asigna. plan: nombre o id (planner_planes). columna: nombre (vacío = primera columna). responsables:
        lista de nombres o emails de miembros del grupo del plan (cada uno recibe el aviso de Planner). vence /
        inicio: AAAA-MM-DD. prioridad: urgente, importante, media o baja. descripcion y checklist (lista de
        puntos) opcionales. Para tareas de la app propia «Tareas» de Servigest usa app_tareas_crear.
        Sin confirmar=true solo devuelve la vista previa que hay que enseñar al usuario.""")
    def _crear_tool(plan: str, titulo: str, columna: str = "", responsables: list[str] | None = None,
                    vence: str = "", inicio: str = "", prioridad: str = "", descripcion: str = "",
                    checklist: list[str] | None = None, confirmar: bool = False) -> dict:
        return planner_crear_tarea(obtener_graph(), plan, titulo, columna, responsables, vence, inicio,
                                   prioridad, descripcion, checklist, confirmar)

    @mcp.tool(name="planner_modificar_tarea", description="""Modifica una tarea de Planner (id de
        planner_tareas o tareas_listar): titulo, columna (moverla), anadir_responsables / quitar_responsables
        (nombres o emails), vence / inicio (AAAA-MM-DD) o quitar_fecha, avance (0, 50 o 100), prioridad,
        descripcion (la sustituye), anadir_checklist (puntos nuevos) y marcar_checklist (texto de puntos a
        marcar como hechos). Sin confirmar=true solo devuelve la vista previa que hay que enseñar al usuario.""")
    def _modificar_tool(tarea_id: str, titulo: str = "", columna: str = "",
                        anadir_responsables: list[str] | None = None, quitar_responsables: list[str] | None = None,
                        vence: str = "", inicio: str = "", quitar_fecha: bool = False, avance: str = "",
                        prioridad: str = "", descripcion: str = "", anadir_checklist: list[str] | None = None,
                        marcar_checklist: list[str] | None = None, confirmar: bool = False) -> dict:
        return planner_modificar_tarea(obtener_graph(), tarea_id, titulo, columna, anadir_responsables,
                                       quitar_responsables, vence, inicio, quitar_fecha, avance, prioridad,
                                       descripcion, anadir_checklist, marcar_checklist, confirmar)

    @mcp.tool(name="planner_comentarios", description="""Lee los comentarios (el chat) de una tarea de
        Planner, del más antiguo al más reciente, con autor y fecha. tarea_id de planner_tareas. NO modifica
        nada.""")
    def _comentarios_tool(tarea_id: str, maximo: int = 30) -> dict:
        return planner_comentarios(obtener_graph(), tarea_id, maximo)

    @mcp.tool(name="planner_comentar", description="""Escribe un comentario en una tarea de Planner (lo ven
        todos los miembros del plan). Sin confirmar=true solo devuelve la vista previa que hay que enseñar al
        usuario.""")
    def _comentar_tool(tarea_id: str, comentario: str, confirmar: bool = False) -> dict:
        return planner_comentar(obtener_graph(), tarea_id, comentario, confirmar)
