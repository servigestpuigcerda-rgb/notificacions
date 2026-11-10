"""Herramientas de correo de Outlook (Microsoft Graph) para el conector MCP de Servigest.

Contiene:
  - buscar_correos  (ampliada: solo_no_leidos + campo `leido` en cada correo)
  - mover_correo    (nueva: vista previa + confirmar=true, acepta uno o varios ids)

Todo va contra /me con el token DELEGADO del usuario que ha iniciado sesión, así que cada persona
(p. ej. Carles) trabaja con su propio buzón. Nunca se usa /users/{id} ni permisos de aplicación.

Integración: el servidor solo tiene que dar un objeto `graph` con dos métodos
    graph.get(ruta_o_url, params=None) -> dict
    graph.post(ruta, json=None) -> dict
que lancen `GraphError` (o una excepción con atributos .status y .code) si Graph responde con error,
y una clave `graph.usuario` (id/UPN del usuario) para guardar la paginación por persona.
Ver `registrar()` al final.
"""
from __future__ import annotations

import re
from typing import Any, Callable

# Nombres estándar (well-known) de carpetas que Graph acepta directamente como id.
CARPETAS_ESTANDAR = {
    "inbox", "archive", "drafts", "sentitems", "deleteditems", "junkemail",
    "outbox", "clutter", "conversationhistory", "scheduled", "searchfolders",
}
# Alias en castellano/catalán que la gente suele decir por voz.
ALIAS_CARPETAS = {
    "bandeja de entrada": "inbox", "entrada": "inbox", "safata d'entrada": "inbox",
    "archivo": "archive", "arxiu": "archive", "archivados": "archive",
    "borradores": "drafts", "esborranys": "drafts",
    "enviados": "sentitems", "elementos enviados": "sentitems", "enviats": "sentitems",
    "papelera": "deleteditems", "elementos eliminados": "deleteditems", "paperera": "deleteditems",
    "spam": "junkemail", "correo no deseado": "junkemail", "brossa": "junkemail",
}

CAMPOS_LISTADO = "id,receivedDateTime,subject,from,hasAttachments,isRead,parentFolderId"
MAX_IDS_POR_LLAMADA = 50

MSG_PERMISO = (
    "Microsoft 365 ha denegado la operación (falta el permiso delegado Mail.ReadWrite en la app de "
    "Azure, o el usuario aún no ha vuelto a iniciar sesión tras concederlo). Con solo Mail.Read se "
    "puede leer pero no mover. Avisa al administrador del despacho."
)


class GraphError(Exception):
    def __init__(self, status: int, code: str = "", mensaje: str = ""):
        super().__init__(f"{status} {code} {mensaje}".strip())
        self.status, self.code, self.mensaje = status, code, mensaje


def _es_error_permiso(e: Exception) -> bool:
    return getattr(e, "status", None) == 403 or getattr(e, "code", "") in (
        "ErrorAccessDenied", "Authorization_RequestDenied", "AccessDenied")


def _es_no_encontrado(e: Exception) -> bool:
    return getattr(e, "status", None) == 404 or getattr(e, "code", "") in (
        "ErrorItemNotFound", "ErrorInvalidIdMalformed", "ResourceNotFound")


# ------------------------------------------------------------------------------------------
# buscar_correos
# ------------------------------------------------------------------------------------------

# Paginación por usuario: {usuario: {"url": nextLink, "solo_no_leidos": bool, "maximo": int}}
_SIGUIENTE: dict[str, dict[str, Any]] = {}


def _fecha(valor: str, fin: bool = False) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor or ""):
        raise ValueError(f"Fecha «{valor}» no válida: usa AAAA-MM-DD.")
    return f"{valor}T23:59:59Z" if fin else f"{valor}T00:00:00Z"


def _kql(v: str) -> str:
    return v.replace('"', "")


def _resumen_correo(m: dict) -> dict:
    remit = (m.get("from") or {}).get("emailAddress") or {}
    return {
        "id": m.get("id"),
        "fecha": m.get("receivedDateTime"),
        "asunto": m.get("subject") or "(sin asunto)",
        "remitente": f"{remit.get('name', '')} <{remit.get('address', '')}>".strip(),
        "leido": bool(m.get("isRead")),
        "adjuntos": [
            {"id": a.get("id"), "nombre": a.get("name"), "inline": a.get("isInline", False)}
            for a in m.get("attachments") or []
        ],
    }


def _peticion_busqueda(carpeta, texto, remitente, destinatario, desde, hasta,
                       solo_con_adjuntos, solo_no_leidos, maximo):
    """Devuelve (ruta, params, filtrar_no_leidos_en_local).

    Graph no deja combinar $search con $filter en mensajes. Si hay texto/remitente/destinatario
    se usa $search (KQL) y el filtro de no leídos se aplica en local; si no, todo va en $filter.
    """
    base = f"/me/mailFolders/{carpeta}/messages" if carpeta else "/me/messages"
    params: dict[str, Any] = {"$select": CAMPOS_LISTADO, "$expand": "attachments($select=id,name,isInline)"}

    if texto or remitente or destinatario:
        partes = []
        if texto:
            partes.append(_kql(texto))
        if remitente:
            partes.append(f'from:"{_kql(remitente)}"')
        if destinatario:
            partes.append(f'to:"{_kql(destinatario)}"')
        if desde:
            partes.append(f"received>={desde}")
        if hasta:
            partes.append(f"received<={hasta}")
        if solo_con_adjuntos:
            partes.append("hasattachments:true")
        params["$search"] = '"' + " AND ".join(partes).replace('"', "'") + '"'
        # Pedimos más si hay que filtrar no leídos en local, para llenar la página.
        params["$top"] = min(maximo * 4, 100) if solo_no_leidos else maximo
        return base, params, solo_no_leidos

    # Con $orderby, Graph exige que receivedDateTime aparezca primero en el $filter.
    filtros = [f"receivedDateTime ge {_fecha(desde) if desde else '1900-01-01T00:00:00Z'}"]
    if hasta:
        filtros.append(f"receivedDateTime le {_fecha(hasta, fin=True)}")
    if solo_con_adjuntos:
        filtros.append("hasAttachments eq true")
    if solo_no_leidos:
        filtros.append("isRead eq false")
    params["$filter"] = " and ".join(filtros)
    params["$orderby"] = "receivedDateTime desc"
    params["$top"] = maximo
    return base, params, False


def buscar_correos(graph, texto: str = "", remitente: str = "", destinatario: str = "",
                   desde: str = "", hasta: str = "", solo_con_adjuntos: bool = False,
                   solo_no_leidos: bool = False, carpeta: str = "", maximo: int = 10,
                   continuar: str = "") -> dict:
    maximo = max(1, min(int(maximo or 10), 50))
    usuario = getattr(graph, "usuario", "") or "_"
    carpeta = ALIAS_CARPETAS.get(carpeta.strip().lower(), carpeta.strip()) if carpeta else ""

    try:
        if continuar:
            estado = _SIGUIENTE.get(usuario)
            if not estado:
                return {"error": "No hay más resultados pendientes. Repite la búsqueda."}
            datos = graph.get(estado["url"])
            filtrar_local, maximo = estado["solo_no_leidos"], estado["maximo"]
        else:
            if desde:
                _fecha(desde)
            if hasta:
                _fecha(hasta)
            ruta, params, filtrar_local = _peticion_busqueda(
                carpeta, texto, remitente, destinatario, desde, hasta,
                solo_con_adjuntos, solo_no_leidos, maximo)
            datos = graph.get(ruta, params=params)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        if _es_error_permiso(e):
            return {"error": "Microsoft 365 ha denegado la lectura del correo (permiso Mail.Read)."}
        if carpeta and _es_no_encontrado(e):
            return {"error": f"La carpeta «{carpeta}» no existe. Usa listar_carpetas_correo para ver los ids."}
        raise

    mensajes = datos.get("value", [])
    if filtrar_local:
        mensajes = [m for m in mensajes if not m.get("isRead")]
    correos = [_resumen_correo(m) for m in mensajes[:maximo]]

    siguiente = datos.get("@odata.nextLink")
    if siguiente:
        _SIGUIENTE[usuario] = {"url": siguiente, "solo_no_leidos": filtrar_local, "maximo": maximo}
    else:
        _SIGUIENTE.pop(usuario, None)

    res: dict[str, Any] = {"total": len(correos), "correos": correos}
    if solo_no_leidos and not continuar:
        res["filtro"] = "solo no leídos"
    if siguiente:
        res["continuar"] = "siguiente"
    return res


# ------------------------------------------------------------------------------------------
# mover_correo
# ------------------------------------------------------------------------------------------

def _parece_id(valor: str) -> bool:
    return len(valor) > 40 and re.fullmatch(r"[A-Za-z0-9+/=_\-]+", valor) is not None


def _todas_las_carpetas(graph, max_profundidad: int = 4) -> list[dict]:
    """Recorre el árbol de carpetas del usuario y devuelve [{id, nombre, ruta}]."""
    res: list[dict] = []
    pendientes = [("/me/mailFolders", "", 0)]
    sel = {"$select": "id,displayName,childFolderCount", "$top": 100}
    while pendientes:
        ruta, prefijo, nivel = pendientes.pop(0)
        url, params = ruta, dict(sel)
        while url:
            datos = graph.get(url, params=params)
            for f in datos.get("value", []):
                camino = f"{prefijo}/{f['displayName']}" if prefijo else f["displayName"]
                res.append({"id": f["id"], "nombre": f["displayName"], "ruta": camino})
                if f.get("childFolderCount") and nivel + 1 < max_profundidad:
                    pendientes.append((f"/me/mailFolders/{f['id']}/childFolders", camino, nivel + 1))
            url, params = datos.get("@odata.nextLink"), None
    return res


def resolver_carpeta(graph, carpeta: str) -> dict:
    """Devuelve {"id", "nombre"} o {"error"}."""
    valor = (carpeta or "").strip()
    if not valor:
        return {"error": "Falta carpeta_destino."}
    estandar = ALIAS_CARPETAS.get(valor.lower(), valor.lower())
    if estandar in CARPETAS_ESTANDAR or _parece_id(valor):
        destino = estandar if estandar in CARPETAS_ESTANDAR else valor
        try:
            f = graph.get(f"/me/mailFolders/{destino}", params={"$select": "id,displayName"})
            return {"id": f["id"], "nombre": f.get("displayName", destino)}
        except Exception as e:  # noqa: BLE001
            if _es_no_encontrado(e):
                return {"error": f"La carpeta «{valor}» no existe en el buzón. "
                                 "Usa listar_carpetas_correo para ver las carpetas y sus ids."}
            raise

    # Nombre libre: buscar por displayName (sin distinguir mayúsculas) o por ruta «Padre/Hija».
    buscado = valor.lower().strip("/")
    todas = _todas_las_carpetas(graph)
    campo = "ruta" if "/" in buscado else "nombre"
    coinciden = [f for f in todas if f[campo].lower() == buscado]
    if len(coinciden) == 1:
        return {"id": coinciden[0]["id"], "nombre": coinciden[0]["ruta"]}
    if not coinciden:
        return {"error": f"No encuentro ninguna carpeta llamada «{valor}». "
                         "Usa listar_carpetas_correo para ver las carpetas y pasa su id."}
    return {"error": f"Hay {len(coinciden)} carpetas llamadas «{valor}»: "
                     + "; ".join(f["ruta"] for f in coinciden)
                     + ". Indica la ruta completa (p. ej. «Clientes/2026») o el id de listar_carpetas_correo."}


def _normalizar_ids(correo_id) -> list[str]:
    if isinstance(correo_id, str):
        ids = [i.strip() for i in correo_id.split(",")] if "," in correo_id else [correo_id.strip()]
    else:
        ids = [str(i).strip() for i in correo_id or []]
    vistos, res = set(), []
    for i in ids:
        if i and i not in vistos:
            vistos.add(i)
            res.append(i)
    return res


def mover_correo(graph, correo_id, carpeta_destino: str, confirmar: bool = False) -> dict:
    ids = _normalizar_ids(correo_id)
    if not ids:
        return {"error": "Falta correo_id (usa el id que devuelve buscar_correos)."}
    if len(ids) > MAX_IDS_POR_LLAMADA:
        return {"error": f"Máximo {MAX_IDS_POR_LLAMADA} correos por llamada; divide la operación."}

    try:
        destino = resolver_carpeta(graph, carpeta_destino)
    except Exception as e:  # noqa: BLE001
        if _es_error_permiso(e):
            return {"error": MSG_PERMISO}
        raise
    if "error" in destino:
        return destino

    nombres_carpeta: dict[str, str] = {destino["id"]: destino["nombre"]}

    def nombre_carpeta(fid: str) -> str:
        if fid not in nombres_carpeta:
            try:
                nombres_carpeta[fid] = graph.get(f"/me/mailFolders/{fid}",
                                                 params={"$select": "displayName"}).get("displayName", "?")
            except Exception:  # noqa: BLE001
                nombres_carpeta[fid] = "?"
        return nombres_carpeta[fid]

    correos, no_encontrados = [], []
    for mid in ids:
        try:
            m = graph.get(f"/me/messages/{mid}",
                          params={"$select": "id,subject,from,receivedDateTime,parentFolderId"})
        except Exception as e:  # noqa: BLE001
            if _es_no_encontrado(e):
                no_encontrados.append(mid)
                continue
            if _es_error_permiso(e):
                return {"error": MSG_PERMISO}
            raise
        remit = (m.get("from") or {}).get("emailAddress") or {}
        correos.append({
            "id": mid,
            "asunto": m.get("subject") or "(sin asunto)",
            "remitente": f"{remit.get('name', '')} <{remit.get('address', '')}>".strip(),
            "fecha": m.get("receivedDateTime"),
            "carpeta_actual": nombre_carpeta(m.get("parentFolderId", "")),
            "_ya_en_destino": m.get("parentFolderId") == destino["id"],
        })

    if not correos:
        return {"error": "No encuentro ninguno de los correos indicados en tu buzón "
                         "(puede que ya se hayan movido: al moverlos cambian de id). Vuelve a usar buscar_correos."}

    if not confirmar:
        return {
            "vista_previa": True,
            "accion": f"Mover {len(correos)} correo(s) a «{destino['nombre']}»",
            "carpeta_destino": destino["nombre"],
            "correos": [{k: v for k, v in c.items() if not k.startswith("_")} for c in correos],
            "no_encontrados": no_encontrados,
            "instruccion": "Enseña esta vista previa al usuario y, solo si está de acuerdo, "
                           "vuelve a llamar con confirmar=true.",
        }

    movidos, errores = [], []
    for c in correos:
        if c["_ya_en_destino"]:
            movidos.append({"id_anterior": c["id"], "id_nuevo": c["id"], "asunto": c["asunto"],
                            "nota": "ya estaba en la carpeta de destino"})
            continue
        try:
            r = graph.post(f"/me/messages/{c['id']}/move", json={"destinationId": destino["id"]})
            movidos.append({"id_anterior": c["id"], "id_nuevo": r.get("id"), "asunto": c["asunto"]})
        except Exception as e:  # noqa: BLE001
            if _es_error_permiso(e):
                return {"error": MSG_PERMISO, "movidos": movidos}
            errores.append({"id": c["id"], "asunto": c["asunto"], "error": str(e)})

    res: dict[str, Any] = {
        "movidos": movidos,
        "carpeta_destino": destino["nombre"],
        "nota": "Graph cambia el id del correo al moverlo: usa id_nuevo a partir de ahora.",
    }
    if errores:
        res["errores"] = errores
    if no_encontrados:
        res["no_encontrados"] = no_encontrados
    return res


# ------------------------------------------------------------------------------------------
# Registro en el servidor MCP
# ------------------------------------------------------------------------------------------

DESC_BUSCAR = """Busca correos en el buzón del usuario de Outlook. Úsala cuando pida «busca el correo de...», «el último
        correo de...», «qué me ha enviado...» o «resúmeme los correos que no he leído». Filtros opcionales:
        texto libre (asunto/cuerpo), remitente (nombre o email), destinatario, fechas desde/hasta (AAAA-MM-DD),
        solo_con_adjuntos, solo_no_leidos (true = solo los no leídos) y carpeta (inbox, sentitems, drafts,
        archive o id de listar_carpetas_correo; vacío = todo el buzón). Los filtros se pueden combinar.
        Devuelve por correo: id, fecha, asunto, remitente, leido (true/false) y lista de adjuntos (incluidos
        los inline). Pagina con `continuar` (valor «siguiente»)."""

DESC_MOVER = """Mueve uno o varios correos de Outlook del usuario a otra carpeta. correo_id: id de buscar_correos
        (o una lista de ids para mover varios de una vez). carpeta_destino: id de listar_carpetas_correo,
        nombre estándar (inbox, archive, deleteditems, junkemail...) o nombre/ruta de una carpeta propia
        («Clientes/2026»). Sin confirmar=true solo devuelve la vista previa (asunto, remitente, fecha, carpeta
        actual y destino) que hay que enseñar al usuario. Al mover, Graph cambia el id: usa id_nuevo después."""


def registrar(mcp, obtener_graph: Callable[[], Any]) -> None:
    """Registra las dos herramientas. `obtener_graph()` devuelve el cliente Graph del usuario actual
    (el mismo que usan leer_correo, crear_carpeta_correo, etc.)."""

    @mcp.tool(name="buscar_correos", description=DESC_BUSCAR)
    def _buscar_correos(texto: str = "", remitente: str = "", destinatario: str = "",
                        desde: str = "", hasta: str = "", solo_con_adjuntos: bool = False,
                        solo_no_leidos: bool = False, carpeta: str = "", maximo: int = 10,
                        continuar: str = "") -> dict:
        return buscar_correos(obtener_graph(), texto, remitente, destinatario, desde, hasta,
                              solo_con_adjuntos, solo_no_leidos, carpeta, maximo, continuar)

    @mcp.tool(name="mover_correo", description=DESC_MOVER)
    def _mover_correo(correo_id: str | list[str], carpeta_destino: str, confirmar: bool = False) -> dict:
        return mover_correo(obtener_graph(), correo_id, carpeta_destino, confirmar)
