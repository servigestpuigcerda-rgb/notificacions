"""Pruebas con un Graph simulado (sin red ni datos reales).  Ejecutar:  python -m pytest servigest_correo -q"""
import base64
import json

import pytest

from servigest_correo import correo_graph as cg
from servigest_correo.permisos import permisos_correo

ID_INBOX = "A" * 60
ID_ARCHIVO = "B" * 60
ID_CLIENTES = "C" * 60
ID_2026_A = "D" * 60
ID_2026_B = "E" * 60


class FakeGraph:
    usuario = "usuario-prueba"

    def __init__(self, mensajes=None, denegar_post=False):
        self.llamadas = []
        self.mensajes = mensajes or {
            "m1": {"id": "m1", "subject": "Factura", "isRead": False, "parentFolderId": ID_INBOX,
                   "receivedDateTime": "2026-11-09T10:00:00Z",
                   "from": {"emailAddress": {"name": "Remitente Uno", "address": "uno@ejemplo.com"}},
                   "attachments": [{"id": "a1", "name": "f.pdf", "isInline": False}]},
            "m2": {"id": "m2", "subject": "Hola", "isRead": True, "parentFolderId": ID_INBOX,
                   "receivedDateTime": "2026-11-08T10:00:00Z",
                   "from": {"emailAddress": {"name": "Remitente Dos", "address": "dos@ejemplo.com"}}},
        }
        self.carpetas = {
            ID_INBOX: {"id": ID_INBOX, "displayName": "Bandeja de entrada", "childFolderCount": 0},
            ID_ARCHIVO: {"id": ID_ARCHIVO, "displayName": "Archivo", "childFolderCount": 0},
            ID_CLIENTES: {"id": ID_CLIENTES, "displayName": "Clientes", "childFolderCount": 1},
        }
        self.hijas = {ID_CLIENTES: [{"id": ID_2026_A, "displayName": "2026", "childFolderCount": 0}],
                      ID_ARCHIVO: []}
        self.denegar_post = denegar_post

    def get(self, ruta, params=None):
        self.llamadas.append(("GET", ruta, params))
        if ruta in ("/me/messages", f"/me/mailFolders/inbox/messages") or ruta.startswith("https://"):
            vals = list(self.mensajes.values())
            if params and "isRead eq false" in params.get("$filter", ""):
                vals = [m for m in vals if not m["isRead"]]
            return {"value": vals}
        if ruta == "/me/mailFolders":
            # Segunda carpeta raíz llamada "2026" para provocar ambigüedad
            return {"value": list(self.carpetas.values())
                    + [{"id": ID_2026_B, "displayName": "2026", "childFolderCount": 0}]}
        if ruta.endswith("/childFolders"):
            return {"value": self.hijas.get(ruta.split("/")[3], [])}
        if ruta.startswith("/me/mailFolders/"):
            fid = ruta.split("/")[3]
            fid = {"inbox": ID_INBOX, "archive": ID_ARCHIVO}.get(fid, fid)
            if fid in self.carpetas:
                return self.carpetas[fid]
            raise cg.GraphError(404, "ErrorItemNotFound")
        if ruta.startswith("/me/messages/"):
            mid = ruta.split("/")[3]
            if mid in self.mensajes:
                return self.mensajes[mid]
            raise cg.GraphError(404, "ErrorItemNotFound")
        raise AssertionError(ruta)

    def post(self, ruta, json=None):
        self.llamadas.append(("POST", ruta, json))
        if self.denegar_post:
            raise cg.GraphError(403, "ErrorAccessDenied")
        return {"id": "nuevo-" + ruta.split("/")[3]}


# ---------------- buscar_correos ----------------

def test_buscar_devuelve_leido():
    r = cg.buscar_correos(FakeGraph())
    assert [c["leido"] for c in r["correos"]] == [False, True]


def test_buscar_solo_no_leidos_usa_filter():
    g = FakeGraph()
    r = cg.buscar_correos(g, solo_no_leidos=True, carpeta="inbox", desde="2026-11-01")
    params = g.llamadas[0][2]
    assert g.llamadas[0][1] == "/me/mailFolders/inbox/messages"
    assert params["$filter"].startswith("receivedDateTime ge 2026-11-01T00:00:00Z")
    assert "isRead eq false" in params["$filter"]
    assert r["total"] == 1 and r["correos"][0]["id"] == "m1"


def test_buscar_no_leidos_con_texto_filtra_en_local():
    g = FakeGraph()
    r = cg.buscar_correos(g, texto="factura", remitente="uno@ejemplo.com", solo_no_leidos=True)
    params = g.llamadas[0][2]
    assert "$search" in params and "$filter" not in params
    assert "from:'uno@ejemplo.com'" in params["$search"]
    assert [c["id"] for c in r["correos"]] == ["m1"]


def test_buscar_fecha_invalida():
    assert "error" in cg.buscar_correos(FakeGraph(), desde="09/11/2026")


# ---------------- mover_correo ----------------

def test_mover_vista_previa_no_mueve():
    g = FakeGraph()
    r = cg.mover_correo(g, "m1", "archive")
    assert r["vista_previa"] and r["carpeta_destino"] == "Archivo"
    c = r["correos"][0]
    assert c["carpeta_actual"] == "Bandeja de entrada" and c["asunto"] == "Factura"
    assert not [x for x in g.llamadas if x[0] == "POST"]


def test_mover_confirmado_devuelve_id_nuevo():
    g = FakeGraph()
    r = cg.mover_correo(g, "m1", "archivo", confirmar=True)  # alias en castellano
    assert r["movidos"][0] == {"id_anterior": "m1", "id_nuevo": "nuevo-m1", "asunto": "Factura"}
    assert ("POST", "/me/messages/m1/move", {"destinationId": ID_ARCHIVO}) in g.llamadas


def test_mover_varios_una_vista_previa():
    r = cg.mover_correo(FakeGraph(), ["m1", "m2", "m1"], ID_ARCHIVO)
    assert len(r["correos"]) == 2


def test_mover_por_ruta_de_carpeta_propia():
    g = FakeGraph()
    r = cg.mover_correo(g, "m1", "Clientes/2026", confirmar=True)
    assert ("POST", "/me/messages/m1/move", {"destinationId": ID_2026_A}) in g.llamadas
    assert r["carpeta_destino"] == "Clientes/2026"


def test_mover_nombre_ambiguo():
    r = cg.mover_correo(FakeGraph(), "m1", "2026")
    assert "error" in r and "Clientes/2026" in r["error"] and "listar_carpetas_correo" in r["error"]


def test_mover_carpeta_inexistente():
    assert "listar_carpetas_correo" in cg.mover_correo(FakeGraph(), "m1", "NoExiste")["error"]
    assert "listar_carpetas_correo" in cg.mover_correo(FakeGraph(), "m1", "Z" * 60)["error"]


def test_mover_sin_permiso_mail_readwrite():
    r = cg.mover_correo(FakeGraph(denegar_post=True), "m1", "archive", confirmar=True)
    assert "Mail.ReadWrite" in r["error"]


def test_mover_correo_inexistente():
    assert "error" in cg.mover_correo(FakeGraph(), "nada", "archive")


# ---------------- permisos ----------------

def _token(scp):
    carga = base64.urlsafe_b64encode(json.dumps({"scp": scp}).encode()).decode().rstrip("=")
    return f"x.{carga}.y"


@pytest.mark.parametrize("scp,esperado", [("Mail.ReadWrite User.Read", "OK"),
                                          ("Mail.Read User.Read", "FALTA")])
def test_permisos(scp, esperado):
    assert permisos_correo(_token(scp)).startswith(esperado)
