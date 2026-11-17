"""Pruebas de las cuentas de correo (despacho + buzones externos) con Graph simulado y sin red.

Ejecutar:  python -m pytest servigest_correo -q

Lo que se comprueba, sobre todo: el buzón de otra organización (aquí «carlos») SOLO se usa
cuando se pide por su nombre. Sin `cuenta`, o con un alias que no existe, no se toca nunca.
"""
import json
import os
import stat

import pytest
from cryptography.fernet import Fernet

from servigest_correo import correo_graph as cg
from servigest_correo import cuentas
from servigest_correo.test_correo_graph import ID_ARCHIVO, FakeGraph

EMAIL_CARLOS = "carlos@despachocarlos.example"


class FakeGraphExterno(FakeGraph):
    """El buzón de Carlos: mismos caminos /me, pero otro usuario y otros correos."""

    usuario = EMAIL_CARLOS

    def __init__(self):
        super().__init__(mensajes={
            "c1": {"id": "c1", "subject": "Contrato Carlos", "isRead": False,
                   "parentFolderId": "A" * 60, "receivedDateTime": "2026-11-10T09:00:00Z",
                   "from": {"emailAddress": {"name": "Cliente", "address": "cliente@x.example"}}},
        })


@pytest.fixture(autouse=True)
def entorno_aislado(tmp_path, monkeypatch):
    """Carpeta de datos y clave de cifrado propias de cada prueba."""
    monkeypatch.setenv("SERVIGEST_DATOS_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("SERVIGEST_TOKEN_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SERVIGEST_CLIENT_ID", "11111111-2222-3333-4444-555555555555")
    monkeypatch.delenv("SERVIGEST_CUENTAS_EXTERNAS", raising=False)
    cuentas._FLUJOS.clear()
    cg._SIGUIENTE.clear()
    yield
    cuentas._FLUJOS.clear()
    cg._SIGUIENTE.clear()


@pytest.fixture
def carlos_registrado():
    cuentas.registrar_cuenta_externa("carlos", EMAIL_CARLOS, "Buzón del despacho de Carlos")
    return "carlos"


@pytest.fixture
def carlos_con_sesion(carlos_registrado, monkeypatch):
    """Carlos registrado y con token (simulado): el cliente Graph es un FakeGraph."""
    cuentas.guardar_token("carlos", json.dumps({"cache": "simulada"}))
    externo = FakeGraphExterno()
    monkeypatch.setattr(cuentas, "cliente_externo", lambda alias: externo)
    return externo


class ClienteExternoProhibido:
    """Si alguien intenta construir el cliente externo sin pedirlo, la prueba falla."""

    def __init__(self):
        self.intentos = []

    def __call__(self, alias):
        self.intentos.append(alias)
        raise AssertionError(f"Se ha intentado usar el buzón externo «{alias}» sin pedirlo")


# ---------------- almacén cifrado ----------------

def test_token_se_guarda_cifrado_y_solo_para_el_dueno():
    cuentas.guardar_token("carlos", "refresh-token-secreto")
    ruta = cuentas._ruta_token("carlos")
    bytes_en_disco = ruta.read_bytes()

    assert b"refresh-token-secreto" not in bytes_en_disco          # cifrado, no en claro
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600              # solo el usuario del servidor
    assert cuentas.leer_token("carlos") == "refresh-token-secreto"  # y se puede recuperar


def test_token_del_despacho_y_del_externo_van_en_ficheros_distintos():
    cuentas.guardar_token("carlos", "token-de-carlos")
    ficheros = [p.name for p in cuentas.directorio_datos().glob("token_*.enc")]
    assert ficheros == ["token_carlos.enc"]  # el del despacho no pasa por aquí: es la sesión del conector


def test_si_cambia_la_clave_el_token_no_sirve(monkeypatch):
    cuentas.guardar_token("carlos", "token-de-carlos")
    monkeypatch.setenv("SERVIGEST_TOKEN_KEY", Fernet.generate_key().decode())
    with pytest.raises(cuentas.SesionRequerida, match="volver a iniciar sesión"):
        cuentas.leer_token("carlos")


def test_directorio_de_datos_es_privado():
    assert stat.S_IMODE(cuentas.directorio_datos().stat().st_mode) == 0o700


# ---------------- registro de cuentas ----------------

def test_registrar_y_listar(carlos_registrado):
    listado = cuentas.listar_cuentas()
    assert listado["por_defecto"] == "despacho"
    externas = [c for c in listado["cuentas"] if c["tipo"] == "externa"]
    assert externas[0]["alias"] == "carlos" and externas[0]["email"] == EMAIL_CARLOS
    assert externas[0]["sesion"] == "sin_sesion"


@pytest.mark.parametrize("alias", ["despacho", "gestoria", "mío"])
def test_no_se_puede_registrar_con_un_nombre_reservado(alias):
    with pytest.raises(cuentas.CuentaNoValida, match="reservado"):
        cuentas.registrar_cuenta_externa(alias, EMAIL_CARLOS)


@pytest.mark.parametrize("alias,email", [("c", EMAIL_CARLOS), ("Carlos Pérez", EMAIL_CARLOS),
                                         ("carlos", "no-es-un-email")])
def test_registro_rechaza_datos_malos(alias, email):
    with pytest.raises(cuentas.CuentaNoValida):
        cuentas.registrar_cuenta_externa(alias, email)


def test_cuentas_del_entorno(monkeypatch):
    monkeypatch.setenv("SERVIGEST_CUENTAS_EXTERNAS", f"carlos={EMAIL_CARLOS};malo=sin-arroba")
    externas = cuentas.cuentas_externas()
    assert list(externas) == ["carlos"] and externas["carlos"]["email"] == EMAIL_CARLOS


def test_olvidar_cuenta_borra_el_token(carlos_registrado):
    cuentas.guardar_token("carlos", "token-de-carlos")
    res = cuentas.olvidar_cuenta_externa("carlos")
    assert res["borrada_del_registro"] and res["token_borrado"]
    assert not cuentas._ruta_token("carlos").exists()
    assert "carlos" not in cuentas.cuentas_externas()


# ---------------- resolución de la cuenta ----------------

@pytest.mark.parametrize("cuenta", ["", "despacho", "DESPACHO", " mi buzón ", "gestoria"])
def test_por_defecto_es_el_despacho(cuenta, carlos_con_sesion, monkeypatch):
    prohibido = ClienteExternoProhibido()
    monkeypatch.setattr(cuentas, "cliente_externo", prohibido)
    despacho = FakeGraph()

    graph, info = cuentas.resolver_cuenta(cuenta, lambda: despacho, "buscar_correos")

    assert graph is despacho and info["tipo"] == "despacho" and info["alias"] == "despacho"
    assert prohibido.intentos == []


def test_alias_desconocido_es_error_y_no_usa_ningun_buzon_externo(carlos_registrado, monkeypatch):
    prohibido = ClienteExternoProhibido()
    monkeypatch.setattr(cuentas, "cliente_externo", prohibido)

    with pytest.raises(cuentas.CuentaNoValida) as e:
        cuentas.resolver_cuenta("carlo", lambda: FakeGraph(), "buscar_correos")

    assert "carlo" in str(e.value) and "carlos" in str(e.value)  # dice las disponibles
    assert prohibido.intentos == []


def test_cuenta_externa_se_usa_cuando_se_pide_por_alias(carlos_con_sesion):
    graph, info = cuentas.resolver_cuenta("carlos", lambda: FakeGraph(), "buscar_correos")
    assert graph is carlos_con_sesion
    assert info == {"alias": "carlos", "tipo": "externa", "email": EMAIL_CARLOS}


def test_cuenta_externa_tambien_por_email_exacto(carlos_con_sesion):
    graph, info = cuentas.resolver_cuenta(EMAIL_CARLOS.upper(), lambda: FakeGraph(), "buscar_correos")
    assert graph is carlos_con_sesion and info["alias"] == "carlos"


def test_cuenta_externa_sin_sesion_pide_iniciar_sesion(carlos_registrado):
    with pytest.raises(cuentas.SesionRequerida, match="iniciar_sesion"):
        cuentas.resolver_cuenta("carlos", lambda: FakeGraph(), "buscar_correos")


# ---------------- registro de accesos (RGPD) ----------------

def _accesos():
    ruta = cuentas.directorio_datos() / "accesos_externos.jsonl"
    return [json.loads(l) for l in ruta.read_text().splitlines()] if ruta.exists() else []


def test_cada_acceso_al_buzon_externo_queda_anotado(carlos_con_sesion):
    cuentas.resolver_cuenta("carlos", lambda: FakeGraph(), "mover_correo")
    (anotacion,) = _accesos()
    assert anotacion["buzon"] == EMAIL_CARLOS and anotacion["alias"] == "carlos"
    assert anotacion["herramienta"] == "mover_correo"
    assert anotacion["usuario_despacho"] == FakeGraph.usuario
    assert anotacion["cuando"].startswith("20")


def test_el_buzon_del_despacho_no_se_anota(carlos_con_sesion):
    cuentas.resolver_cuenta("", lambda: FakeGraph(), "buscar_correos")
    assert _accesos() == []


def test_el_registro_de_accesos_es_privado(carlos_con_sesion):
    cuentas.resolver_cuenta("carlos", lambda: FakeGraph(), "buscar_correos")
    ruta = cuentas.directorio_datos() / "accesos_externos.jsonl"
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600


# ---------------- las herramientas de correo con el parámetro cuenta ----------------

class FakeMCP:
    """Recoge las funciones que registra correo_graph, como haría FastMCP."""

    def __init__(self):
        self.tools = {}
        self.descripciones = {}

    def tool(self, name=None, description=None):
        def decorador(fn):
            self.tools[name or fn.__name__] = fn
            self.descripciones[name or fn.__name__] = description or ""
            return fn
        return decorador


@pytest.fixture
def servidor(monkeypatch):
    """Servidor MCP simulado con las dos herramientas de correo registradas."""
    mcp = FakeMCP()
    despacho = FakeGraph()
    cg.registrar(mcp, lambda: despacho)
    cuentas.registrar(mcp)
    return mcp, despacho


def test_sin_cuenta_busca_en_el_buzon_del_despacho(servidor, carlos_con_sesion):
    mcp, despacho = servidor
    r = mcp.tools["buscar_correos"]()
    assert r["buzon"] == "despacho"
    assert [c["id"] for c in r["correos"]] == ["m1", "m2"]      # los del despacho
    assert carlos_con_sesion.llamadas == []                     # el de Carlos, intacto
    assert _accesos() == []


def test_con_cuenta_carlos_busca_en_su_buzon(servidor, carlos_con_sesion):
    mcp, despacho = servidor
    r = mcp.tools["buscar_correos"](cuenta="carlos")
    assert [c["id"] for c in r["correos"]] == ["c1"]
    assert r["buzon"] == f"carlos <{EMAIL_CARLOS}>" and "EXTERNO" in r["aviso_buzon"]
    assert carlos_con_sesion.llamadas and despacho.llamadas == []
    assert _accesos()[0]["herramienta"] == "buscar_correos"


def test_cuenta_desconocida_devuelve_error_y_no_busca_en_ningun_sitio(servidor, carlos_registrado,
                                                                      monkeypatch):
    mcp, despacho = servidor
    monkeypatch.setattr(cuentas, "cliente_externo", ClienteExternoProhibido())

    r = mcp.tools["buscar_correos"](cuenta="carles")

    assert "No existe ninguna cuenta" in r["error"] and r["cuenta_pedida"] == "carles"
    assert "correos" not in r and despacho.llamadas == []


def test_cuenta_registrada_sin_sesion_devuelve_error_claro(servidor, carlos_registrado):
    mcp, despacho = servidor
    r = mcp.tools["buscar_correos"](cuenta="carlos")
    assert "iniciar_sesion" in r["error"] and despacho.llamadas == []


def test_mover_correo_sin_cuenta_mueve_en_el_despacho(servidor, carlos_con_sesion):
    mcp, despacho = servidor
    r = mcp.tools["mover_correo"](correo_id="m1", carpeta_destino="archive", confirmar=True)
    assert r["buzon"] == "despacho"
    assert ("POST", "/me/messages/m1/move", {"destinationId": ID_ARCHIVO}) in despacho.llamadas
    assert carlos_con_sesion.llamadas == []


def test_mover_correo_en_el_buzon_de_carlos_avisa_en_la_vista_previa(servidor, carlos_con_sesion):
    mcp, despacho = servidor
    r = mcp.tools["mover_correo"](correo_id="c1", carpeta_destino="archive", cuenta="carlos")
    assert r["vista_previa"] and r["buzon"] == f"carlos <{EMAIL_CARLOS}>"
    assert "EXTERNO" in r["aviso_buzon"]
    assert not [x for x in carlos_con_sesion.llamadas if x[0] == "POST"]  # la previa no mueve
    assert despacho.llamadas == []


def test_la_paginacion_no_se_mezcla_entre_buzones(servidor, carlos_con_sesion, monkeypatch):
    """Tras buscar en el buzón de Carlos, un «continuar» sin cuenta no sigue por sus resultados."""
    mcp, despacho = servidor
    monkeypatch.setattr(FakeGraphExterno, "get", lambda self, ruta, params=None: {
        "value": list(self.mensajes.values()), "@odata.nextLink": "https://graph/pagina-de-carlos"})

    mcp.tools["buscar_correos"](cuenta="carlos")
    r = mcp.tools["buscar_correos"](continuar="siguiente")

    assert r["buzon"] == "despacho"
    assert "error" in r and "Repite la búsqueda" in r["error"]
    assert not [x for x in despacho.llamadas if str(x[1]).startswith("https://graph/pagina-de-carlos")]


def test_la_descripcion_de_las_tools_explica_el_parametro(servidor):
    mcp, _ = servidor
    for nombre in ("buscar_correos", "mover_correo"):
        descripcion = mcp.descripciones[nombre]
        assert "cuenta:" in descripcion and "despacho" in descripcion
        assert "expresamente" in descripcion


# ---------------- herramientas de gestión de cuentas ----------------

def test_tool_registrar_pide_confirmacion(servidor):
    mcp, _ = servidor
    previa = mcp.tools["cuenta_externa_registrar"](alias="carlos", email=EMAIL_CARLOS)
    assert previa["vista_previa"] and "carlos" not in cuentas.cuentas_externas()

    hecho = mcp.tools["cuenta_externa_registrar"](alias="carlos", email=EMAIL_CARLOS, confirmar=True)
    assert hecho["email"] == EMAIL_CARLOS and "carlos" in cuentas.cuentas_externas()


def test_tool_login_pide_confirmacion_y_no_inicia_sesion_sola(servidor, carlos_registrado, monkeypatch):
    mcp, _ = servidor
    monkeypatch.setattr(cuentas, "iniciar_sesion",
                        lambda alias: (_ for _ in ()).throw(AssertionError("no debería llamarse")))
    previa = mcp.tools["cuenta_externa_iniciar_sesion"](cuenta="carlos")
    assert previa["vista_previa"] and EMAIL_CARLOS in previa["accion"]


def test_tool_login_devuelve_codigo_para_esa_persona(servidor, carlos_registrado, monkeypatch):
    mcp, _ = servidor
    monkeypatch.setattr(cuentas, "iniciar_sesion", lambda alias: {
        "estado": "pendiente", "alias": alias, "codigo": "ABCD-1234",
        "url": "https://microsoft.com/devicelogin"})

    r = mcp.tools["cuenta_externa_iniciar_sesion"](cuenta="carlos", confirmar=True)

    assert r["codigo"] == "ABCD-1234" and "esa persona" in r["instruccion"]


def test_tool_estado_y_cierre_de_sesion(servidor, carlos_registrado):
    mcp, _ = servidor
    assert mcp.tools["cuenta_externa_estado"](cuenta="carlos")["estado"] == "sin_sesion"

    cuentas.guardar_token("carlos", "token-de-carlos")
    assert mcp.tools["cuenta_externa_estado"](cuenta="carlos")["estado"] == "activa"

    previa = mcp.tools["cuenta_externa_cerrar_sesion"](cuenta="carlos")
    assert previa["vista_previa"] and cuentas._ruta_token("carlos").exists()

    cerrado = mcp.tools["cuenta_externa_cerrar_sesion"](cuenta="carlos", confirmar=True)
    assert cerrado["token_borrado"] and not cuentas._ruta_token("carlos").exists()


def test_tool_estado_con_alias_inventado(servidor):
    mcp, _ = servidor
    assert "No existe ninguna cuenta" in mcp.tools["cuenta_externa_estado"](cuenta="pepe")["error"]


# ---------------- login contra MSAL (simulado) ----------------

class AppMSALFalsa:
    def __init__(self, resultado, usuario=EMAIL_CARLOS):
        self.resultado, self.usuario = resultado, usuario

    def initiate_device_flow(self, scopes=None):
        self.scopes = scopes
        return {"user_code": "ABCD-1234", "verification_uri": "https://microsoft.com/devicelogin",
                "expires_in": 900, "message": "Ve a ... y pon el código ABCD-1234"}

    def acquire_token_by_device_flow(self, flujo):
        return self.resultado


class CacheFalsa:
    has_state_changed = True

    def serialize(self):
        return json.dumps({"cache": "de-carlos"})

    def deserialize(self, texto):
        pass


def _preparar_msal(monkeypatch, resultado):
    app = AppMSALFalsa(resultado)
    monkeypatch.setattr(cuentas, "_app_msal", lambda alias: (app, CacheFalsa()))
    return app


def test_login_correcto_guarda_el_token_cifrado(carlos_registrado, monkeypatch):
    app = _preparar_msal(monkeypatch, {
        "access_token": "token-de-acceso", "refresh_token": "token-de-refresco",
        "scope": "Mail.ReadWrite Mail.Send offline_access",
        "id_token_claims": {"preferred_username": EMAIL_CARLOS}})

    inicio = cuentas.iniciar_sesion("carlos")
    assert inicio["codigo"] == "ABCD-1234" and inicio["estado"] == "pendiente"

    import threading
    for hilo in threading.enumerate():       # el login se completa en un hilo
        if hilo.name == "login-carlos":
            hilo.join(5)

    assert cuentas.estado_sesion("carlos")["estado"] == "activa"
    assert b"de-carlos" not in cuentas._ruta_token("carlos").read_bytes()   # cifrado
    assert json.loads(cuentas.leer_token("carlos")) == {"cache": "de-carlos"}
    assert app.scopes == ["Mail.ReadWrite", "Mail.Send"]  # offline_access lo añade MSAL


def test_login_con_otra_cuenta_no_guarda_el_token(carlos_registrado, monkeypatch):
    _preparar_msal(monkeypatch, {"access_token": "t", "id_token_claims":
                                 {"preferred_username": "otro@otraempresa.example"}})
    cuentas.iniciar_sesion("carlos")

    import threading
    for hilo in threading.enumerate():
        if hilo.name == "login-carlos":
            hilo.join(5)

    estado = cuentas.estado_sesion("carlos")
    assert estado["estado"] == "error" and "No se guarda el token" in estado["mensaje"]
    assert not cuentas._ruta_token("carlos").exists()


def test_login_sin_consentimiento_explica_que_hacer(carlos_registrado, monkeypatch):
    _preparar_msal(monkeypatch, {"error": "invalid_grant",
                                 "error_description": "AADSTS65001: no consent"})
    cuentas.iniciar_sesion("carlos")

    import threading
    for hilo in threading.enumerate():
        if hilo.name == "login-carlos":
            hilo.join(5)

    mensaje = cuentas.estado_sesion("carlos")["mensaje"]
    assert "consentimiento" in mensaje and "administrador" in mensaje
    assert not cuentas._ruta_token("carlos").exists()


def test_sin_client_id_no_se_puede_iniciar_sesion(carlos_registrado, monkeypatch):
    monkeypatch.delenv("SERVIGEST_CLIENT_ID", raising=False)
    monkeypatch.delenv("MS_CLIENT_ID", raising=False)
    with pytest.raises(cuentas.SesionRequerida, match="SERVIGEST_CLIENT_ID"):
        cuentas.iniciar_sesion("carlos")


# ---------------- cliente Graph del buzón externo ----------------

class RespuestaFalsa:
    def __init__(self, status=200, datos=None, texto="", cabeceras=None):
        self.status_code, self._datos = status, datos if datos is not None else {}
        self.text, self.headers = texto, cabeceras or {}
        self.content = (texto or json.dumps(self._datos)).encode()

    def json(self):
        return self._datos


class ClienteHTTPFalso:
    """Sustituye a httpx.Client: guarda la llamada y devuelve respuestas preparadas."""

    llamadas: list = []
    respuestas: list = []

    def __init__(self, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False

    def request(self, metodo, url, params=None, json=None, headers=None):
        ClienteHTTPFalso.llamadas.append({"metodo": metodo, "url": url, "params": params,
                                          "json": json, "headers": headers})
        return ClienteHTTPFalso.respuestas.pop(0)


@pytest.fixture
def http_falso(monkeypatch):
    import httpx

    ClienteHTTPFalso.llamadas, ClienteHTTPFalso.respuestas = [], []
    monkeypatch.setattr(httpx, "Client", ClienteHTTPFalso)
    return ClienteHTTPFalso


def test_cliente_externo_llama_a_me_con_su_token(http_falso):
    from servigest_correo.graph_cliente import ClienteGraph

    http_falso.respuestas.append(RespuestaFalsa(200, {"value": [{"id": "c1"}]}))
    cliente = ClienteGraph(lambda: "token-de-carlos", usuario=EMAIL_CARLOS, alias="carlos")

    datos = cliente.get("/me/messages", params={"$top": 5})

    llamada = http_falso.llamadas[0]
    assert datos == {"value": [{"id": "c1"}]}
    assert llamada["url"] == "https://graph.microsoft.com/v1.0/me/messages"
    assert llamada["headers"]["Authorization"] == "Bearer token-de-carlos"
    assert cliente.usuario == EMAIL_CARLOS


def test_cliente_externo_acepta_el_nextlink_absoluto(http_falso):
    from servigest_correo.graph_cliente import ClienteGraph

    http_falso.respuestas.append(RespuestaFalsa(200, {"value": []}))
    ClienteGraph(lambda: "t").get("https://graph.microsoft.com/v1.0/me/messages?$skip=10")
    assert http_falso.llamadas[0]["url"].endswith("$skip=10")


def test_cliente_externo_convierte_el_error_de_graph(http_falso):
    from servigest_correo.graph_cliente import ClienteGraph, GraphError

    http_falso.respuestas.append(RespuestaFalsa(
        403, {"error": {"code": "ErrorAccessDenied", "message": "Access denied"}}))

    with pytest.raises(GraphError) as e:
        ClienteGraph(lambda: "t").post("/me/messages/x/move", json={"destinationId": "y"})

    assert e.value.status == 403 and e.value.code == "ErrorAccessDenied"
    assert cg._es_error_permiso(e.value)  # correo_graph lo reconoce y da el mensaje de permisos


def test_token_corrupto_pide_cerrar_y_reiniciar_sesion(carlos_registrado):
    cuentas.guardar_token("carlos", "esto-no-es-una-cache-msal")
    with pytest.raises(cuentas.SesionRequerida, match="cerrar_sesion"):
        cuentas._app_msal("carlos")


def test_falta_client_id_antes_de_tocar_el_token(carlos_registrado, monkeypatch):
    cuentas.guardar_token("carlos", "esto-no-es-una-cache-msal")
    monkeypatch.delenv("SERVIGEST_CLIENT_ID", raising=False)
    with pytest.raises(cuentas.SesionRequerida, match="SERVIGEST_CLIENT_ID"):
        cuentas._app_msal("carlos")
