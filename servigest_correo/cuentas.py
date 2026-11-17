"""Cuentas de correo del conector Servigest: la del despacho y buzones de OTRA organización.

Dos tipos de cuenta:

* **despacho** (por defecto, alias `despacho`): el buzón del usuario que ha iniciado sesión en
  el conector. No se toca nada: se sigue usando el cliente Graph que ya da el servidor
  (`obtener_graph()`), con su token delegado y contra `/me`.

* **externa** (alias propio, p. ej. `carlos`): buzón de un tenant distinto. Tiene su **propio
  token delegado**, que esa persona obtiene iniciando sesión ella misma (device code flow de
  MSAL contra una app multiorganización). El token **no** se mezcla con el del despacho: se
  guarda aparte, **cifrado** (Fernet/AES) y con permisos 0600.

Reglas de uso (las aplica `resolver_cuenta`):
  - sin `cuenta`, o con `cuenta="despacho"`, se usa SIEMPRE el buzón del despacho;
  - un buzón externo solo se usa si se nombra su alias (o su email) de forma exacta;
  - un alias desconocido es un error: NUNCA se cae hacia atrás a un buzón externo;
  - cada acceso a un buzón externo se anota en un registro (`accesos_externos.jsonl`) para el
    registro de actividades de tratamiento (RGPD).

Variables de entorno:
  SERVIGEST_CLIENT_ID / MS_CLIENT_ID   id de la app multiorganización de Entra ID (obligatoria)
  SERVIGEST_AUTORIDAD_EXTERNA          por defecto https://login.microsoftonline.com/organizations
  SERVIGEST_DATOS_DIR                  carpeta de datos (por defecto ~/.servigest/cuentas)
  SERVIGEST_TOKEN_KEY                  clave Fernet (base64 urlsafe de 32 bytes). Si no está,
                                       se crea y se usa el fichero `clave_tokens.key` (0600).
  SERVIGEST_CUENTAS_EXTERNAS           cuentas predefinidas: "carlos=carlos@empresa.com;otro=x@y.es"

CLI para el administrador del servidor (PC del Xavi):
    python -m servigest_correo.cuentas listar
    python -m servigest_correo.cuentas registrar carlos carlos@empresa.com "Buzón de Carlos"
    python -m servigest_correo.cuentas login carlos
    python -m servigest_correo.cuentas logout carlos
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .graph_cliente import ClienteGraph, GraphError  # noqa: F401  (GraphError se re-exporta)

ALIAS_DESPACHO = "despacho"
# Formas de pedir el buzón propio. Aquí sí se admiten sinónimos: el resultado es el de por defecto.
SINONIMOS_DESPACHO = {
    "", "despacho", "despatx", "gestoria", "gestoría", "servigest", "propio", "propia", "mio",
    "mío", "meu", "el mio", "el mío", "yo", "mi buzon", "mi buzón", "nuestro", "oficina",
}
# Permisos delegados que se piden al iniciar sesión en el buzón externo.
# MSAL añade solo offline_access, openid y profile (de ahí el refresh token).
SCOPES_EXTERNOS = ["Mail.ReadWrite", "Mail.Send"]
AUTORIDAD_POR_DEFECTO = "https://login.microsoftonline.com/organizations"

RE_ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CuentaNoValida(Exception):
    """El alias de cuenta pedido no existe o no es válido."""


class SesionRequerida(Exception):
    """La cuenta externa existe pero no tiene una sesión válida (nadie ha iniciado sesión aún)."""


# ----------------------------------------------------------------------------------------------
# Carpeta de datos, clave y almacén cifrado
# ----------------------------------------------------------------------------------------------

def directorio_datos() -> pathlib.Path:
    ruta = pathlib.Path(os.environ.get("SERVIGEST_DATOS_DIR")
                        or pathlib.Path.home() / ".servigest" / "cuentas")
    ruta.mkdir(parents=True, exist_ok=True)
    os.chmod(ruta, 0o700)
    return ruta


def _escribir_privado(ruta: pathlib.Path, datos: bytes) -> None:
    """Escribe el fichero con permisos 0600 desde el primer byte (nunca legible por otros)."""
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, datos)
    finally:
        os.close(fd)
    os.replace(tmp, ruta)
    os.chmod(ruta, 0o600)


def _clave() -> bytes:
    """Clave de cifrado de los tokens. Preferible en SERVIGEST_TOKEN_KEY; si no, fichero 0600."""
    del_entorno = (os.environ.get("SERVIGEST_TOKEN_KEY") or "").strip()
    if del_entorno:
        return del_entorno.encode()
    fichero = directorio_datos() / "clave_tokens.key"
    if fichero.exists():
        return fichero.read_bytes().strip()
    from cryptography.fernet import Fernet

    clave = Fernet.generate_key()
    _escribir_privado(fichero, clave)
    return clave


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(_clave())


def _ruta_token(alias: str) -> pathlib.Path:
    return directorio_datos() / f"token_{alias}.enc"


def guardar_token(alias: str, contenido: str) -> None:
    """Guarda cifrada la cache MSAL (incluye el refresh token) de una cuenta externa."""
    _escribir_privado(_ruta_token(alias), _fernet().encrypt(contenido.encode()))


def leer_token(alias: str) -> str:
    ruta = _ruta_token(alias)
    if not ruta.exists():
        return ""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(ruta.read_bytes()).decode()
    except InvalidToken as e:  # clave cambiada o fichero manipulado
        raise SesionRequerida(
            f"El token guardado de «{alias}» no se puede descifrar (¿ha cambiado "
            "SERVIGEST_TOKEN_KEY?). Hay que volver a iniciar sesión en ese buzón.") from e


def borrar_token(alias: str) -> bool:
    ruta = _ruta_token(alias)
    if ruta.exists():
        ruta.unlink()
        return True
    return False


# ----------------------------------------------------------------------------------------------
# Registro de cuentas externas
# ----------------------------------------------------------------------------------------------

def _ruta_registro() -> pathlib.Path:
    return directorio_datos() / "cuentas_externas.json"


def _del_entorno() -> dict[str, dict]:
    res: dict[str, dict] = {}
    for trozo in (os.environ.get("SERVIGEST_CUENTAS_EXTERNAS") or "").split(";"):
        if "=" in trozo:
            alias, email = trozo.split("=", 1)
            alias, email = alias.strip().lower(), email.strip()
            if RE_ALIAS.match(alias) and RE_EMAIL.match(email):
                res[alias] = {"email": email, "descripcion": "definida en SERVIGEST_CUENTAS_EXTERNAS"}
    return res


def cuentas_externas() -> dict[str, dict]:
    """{alias: {email, descripcion, sesion: activa|pendiente|sin_sesion}}"""
    res = _del_entorno()
    ruta = _ruta_registro()
    if ruta.exists():
        try:
            res.update(json.loads(ruta.read_text() or "{}"))
        except json.JSONDecodeError:
            pass
    for alias, info in res.items():
        info["alias"] = alias
        info["sesion"] = _estado_sesion(alias)
    return res


def registrar_cuenta_externa(alias: str, email: str, descripcion: str = "") -> dict:
    alias = (alias or "").strip().lower()
    email = (email or "").strip()
    if alias in SINONIMOS_DESPACHO or alias == ALIAS_DESPACHO:
        raise CuentaNoValida(f"«{alias}» está reservado para el buzón del despacho.")
    if not RE_ALIAS.match(alias):
        raise CuentaNoValida("El alias solo puede llevar letras minúsculas, números, «-» y «_» "
                             "(2 a 32 caracteres). Por ejemplo: carlos.")
    if not RE_EMAIL.match(email):
        raise CuentaNoValida(f"«{email}» no parece una dirección de correo.")

    registro = {}
    if _ruta_registro().exists():
        try:
            registro = json.loads(_ruta_registro().read_text() or "{}")
        except json.JSONDecodeError:
            registro = {}
    registro[alias] = {"email": email, "descripcion": descripcion,
                       "registrada": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _escribir_privado(_ruta_registro(), json.dumps(registro, indent=2, ensure_ascii=False).encode())
    return {"alias": alias, **registro[alias], "sesion": _estado_sesion(alias)}


def olvidar_cuenta_externa(alias: str) -> dict:
    """Cierra la sesión y borra la cuenta del registro (el token cifrado se elimina)."""
    alias = (alias or "").strip().lower()
    registro = {}
    if _ruta_registro().exists():
        try:
            registro = json.loads(_ruta_registro().read_text() or "{}")
        except json.JSONDecodeError:
            registro = {}
    estaba = registro.pop(alias, None) is not None
    _escribir_privado(_ruta_registro(), json.dumps(registro, indent=2, ensure_ascii=False).encode())
    token_borrado = borrar_token(alias)
    _FLUJOS.pop(alias, None)
    return {"alias": alias, "borrada_del_registro": estaba, "token_borrado": token_borrado,
             "nota": "Si estaba definida en SERVIGEST_CUENTAS_EXTERNAS, hay que quitarla también de ahí."}


def cuenta_externa(alias: str) -> dict:
    alias = (alias or "").strip().lower()
    cuentas = cuentas_externas()
    if alias not in cuentas:
        raise CuentaNoValida(_mensaje_alias_desconocido(alias, cuentas))
    return cuentas[alias]


def _mensaje_alias_desconocido(alias: str, cuentas: dict[str, dict]) -> str:
    disponibles = ", ".join(sorted(cuentas)) or "(ninguna)"
    return (f"No existe ninguna cuenta de correo llamada «{alias}». Cuentas disponibles: "
            f"«{ALIAS_DESPACHO}» (el buzón del despacho, el de por defecto) y buzones externos: "
            f"{disponibles}. No se usa ningún otro buzón por si acaso: revisa el nombre o "
            "regístralo con cuenta_externa_registrar.")


# ----------------------------------------------------------------------------------------------
# Inicio de sesión de una cuenta externa (device code flow, app multiorganización)
# ----------------------------------------------------------------------------------------------

# {alias: {"estado": pendiente|activa|error, "codigo", "url", "caduca", "mensaje", "email"}}
_FLUJOS: dict[str, dict[str, Any]] = {}


def _client_id() -> str:
    cid = (os.environ.get("SERVIGEST_CLIENT_ID") or os.environ.get("MS_CLIENT_ID") or "").strip()
    if not cid:
        raise SesionRequerida(
            "Falta SERVIGEST_CLIENT_ID: es el id de la app multiorganización de Entra ID. "
            "Mira MULTIORGANIZACION.md para crearla o para marcar la actual como multiorganización.")
    return cid


def _autoridad() -> str:
    return (os.environ.get("SERVIGEST_AUTORIDAD_EXTERNA") or AUTORIDAD_POR_DEFECTO).strip()


def _app_msal(alias: str):
    """PublicClientApplication con la cache descifrada de esa cuenta (se vuelve a cifrar al salir)."""
    import msal

    client_id = _client_id()  # antes de tocar el token: así el aviso de configuración va primero
    cache = msal.SerializableTokenCache()
    guardado = leer_token(alias)
    if guardado:
        try:
            cache.deserialize(guardado)
        except Exception as e:  # noqa: BLE001 - fichero corrupto o de otra versión
            raise SesionRequerida(
                f"El token guardado de «{alias}» no se puede leer ({e}). Cierra la sesión de esa "
                "cuenta (cuenta_externa_cerrar_sesion) y vuelve a iniciarla.") from e
    app = msal.PublicClientApplication(client_id, authority=_autoridad(), token_cache=cache)
    return app, cache


def _persistir(alias: str, cache) -> None:
    if cache.has_state_changed:
        guardar_token(alias, cache.serialize())


def _estado_sesion(alias: str) -> str:
    flujo = _FLUJOS.get(alias)
    if flujo and flujo.get("estado") == "pendiente":
        return "pendiente"
    if flujo and flujo.get("estado") == "error":
        return "error"
    return "activa" if _ruta_token(alias).exists() else "sin_sesion"


def iniciar_sesion(alias: str) -> dict:
    """Arranca el device code flow. Devuelve el código y la URL para que los use ESA persona.

    No bloquea: la espera va en un hilo y el estado se consulta con `estado_sesion(alias)`.
    """
    info = cuenta_externa(alias)
    alias = info["alias"]
    app, cache = _app_msal(alias)

    flujo = app.initiate_device_flow(scopes=SCOPES_EXTERNOS)
    if "user_code" not in flujo:
        raise SesionRequerida(
            "Microsoft no ha dado código de inicio de sesión: "
            f"{flujo.get('error_description') or flujo.get('error') or flujo}. "
            "Comprueba que la app de Entra ID admite «cuentas en cualquier organización» y que "
            "tiene activado el flujo de cliente público / dispositivo.")

    estado = {"estado": "pendiente", "alias": alias, "email_esperado": info["email"],
              "codigo": flujo["user_code"], "url": flujo.get("verification_uri", ""),
              "caduca_en_segundos": flujo.get("expires_in", 900), "mensaje": flujo.get("message", "")}
    _FLUJOS[alias] = estado
    threading.Thread(target=_esperar_login, args=(alias, app, cache, flujo, info),
                     daemon=True, name=f"login-{alias}").start()
    return dict(estado)


def _esperar_login(alias: str, app, cache, flujo: dict, info: dict) -> None:
    try:
        res = app.acquire_token_by_device_flow(flujo)  # bloquea hasta que la persona valide o caduque
    except Exception as e:  # noqa: BLE001
        _FLUJOS[alias] = {"estado": "error", "alias": alias, "mensaje": str(e)}
        return

    if "access_token" not in res:
        _FLUJOS[alias] = {"estado": "error", "alias": alias,
                          "mensaje": _mensaje_error_login(res)}
        return

    # Que el buzón sea el que se esperaba: si no, se descarta el token.
    firmado = ((res.get("id_token_claims") or {}).get("preferred_username")
               or (res.get("id_token_claims") or {}).get("upn") or "")
    if firmado and info["email"] and firmado.lower() != info["email"].lower():
        # No se persiste nada: la cache se queda en memoria y se descarta con el hilo.
        _FLUJOS[alias] = {"estado": "error", "alias": alias,
                          "mensaje": (f"Ha iniciado sesión «{firmado}», pero la cuenta «{alias}» está "
                                      f"registrada como «{info['email']}». No se guarda el token. "
                                      "Corrige el email del registro o inicia sesión con la cuenta correcta.")}
        return

    _persistir(alias, cache)
    _FLUJOS[alias] = {"estado": "activa", "alias": alias, "email": firmado or info["email"],
                      "scopes": res.get("scope", ""),
                      "desde": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _mensaje_error_login(res: dict) -> str:
    error = res.get("error", "")
    descripcion = res.get("error_description", "") or str(res)
    if error in ("consent_required", "invalid_grant") or "AADSTS65001" in descripcion:
        return ("Falta consentimiento en la organización del buzón: un administrador de ESE tenant "
                "tiene que aceptar los permisos de la app (Mail.ReadWrite, Mail.Send, offline_access). "
                "Mira MULTIORGANIZACION.md, apartado «consentimiento en el tenant externo». "
                f"Detalle: {descripcion}")
    if "AADSTS50020" in descripcion or error == "unauthorized_client":
        return ("La app no admite cuentas de otras organizaciones: en Entra ID hay que ponerla como "
                "«Cuentas en cualquier directorio organizativo (multitenant)». "
                f"Detalle: {descripcion}")
    if error == "expired_token" or "expired" in descripcion.lower():
        return "El código ha caducado sin usarse. Vuelve a iniciar sesión."
    return descripcion


def estado_sesion(alias: str) -> dict:
    info = cuenta_externa(alias)
    alias = info["alias"]
    estado = _estado_sesion(alias)
    res = {"alias": alias, "email": info["email"], "estado": estado}
    flujo = _FLUJOS.get(alias) or {}
    for clave in ("codigo", "url", "mensaje", "caduca_en_segundos", "desde"):
        if flujo.get(clave):
            res[clave] = flujo[clave]
    if estado == "sin_sesion":
        res["siguiente_paso"] = (f"Nadie ha iniciado sesión en «{alias}». Usa "
                                 "cuenta_externa_iniciar_sesion y pásale el código a esa persona.")
    return res


def cerrar_sesion(alias: str) -> dict:
    """Borra el token cifrado de la cuenta externa (la cuenta sigue registrada)."""
    info = cuenta_externa(alias)
    alias = info["alias"]
    borrado = borrar_token(alias)
    _FLUJOS.pop(alias, None)
    return {"alias": alias, "email": info["email"], "token_borrado": borrado,
            "estado": _estado_sesion(alias)}


# ----------------------------------------------------------------------------------------------
# Cliente Graph de una cuenta externa
# ----------------------------------------------------------------------------------------------

def _token_externo(alias: str) -> str:
    app, cache = _app_msal(alias)
    cuentas_msal = app.get_accounts()
    if not cuentas_msal:
        raise SesionRequerida(
            f"Nadie ha iniciado sesión en el buzón «{alias}». Usa cuenta_externa_iniciar_sesion, "
            "pásale el código a esa persona y vuelve a intentarlo.")
    res = app.acquire_token_silent(SCOPES_EXTERNOS, account=cuentas_msal[0])
    _persistir(alias, cache)
    if not res or "access_token" not in res:
        raise SesionRequerida(
            f"La sesión del buzón «{alias}» ha caducado o se ha revocado (el refresh token ya no "
            "sirve). Hay que volver a iniciar sesión con cuenta_externa_iniciar_sesion.")
    return res["access_token"]


def cliente_externo(alias: str) -> ClienteGraph:
    info = cuenta_externa(alias)
    alias = info["alias"]
    if not _ruta_token(alias).exists():
        raise SesionRequerida(
            f"Nadie ha iniciado sesión en el buzón «{alias}» ({info['email']}). Usa "
            "cuenta_externa_iniciar_sesion y pásale el código a esa persona.")
    return ClienteGraph(lambda: _token_externo(alias), usuario=info["email"], alias=alias)


# ----------------------------------------------------------------------------------------------
# Resolución de la cuenta pedida + registro de accesos
# ----------------------------------------------------------------------------------------------

def es_despacho(cuenta: str) -> bool:
    return (cuenta or "").strip().lower() in SINONIMOS_DESPACHO


def resolver_cuenta(cuenta: str, obtener_graph: Callable[[], Any],
                    herramienta: str = "") -> tuple[Any, dict]:
    """Devuelve (cliente_graph, info) para la cuenta pedida.

    `cuenta` vacía o «despacho» → buzón del despacho (lo normal). Para un buzón externo hay que
    nombrar su alias o su email exactamente; cualquier otra cosa levanta CuentaNoValida y NO se
    cae hacia atrás a ningún buzón externo.
    """
    pedida = (cuenta or "").strip().lower()
    if es_despacho(pedida):
        graph = obtener_graph()
        return graph, {"alias": ALIAS_DESPACHO, "tipo": "despacho",
                       "email": getattr(graph, "usuario", "") or ""}

    externas = cuentas_externas()
    if pedida not in externas:
        # También se admite el email exacto de una cuenta registrada.
        por_email = [a for a, i in externas.items() if (i.get("email") or "").lower() == pedida]
        if len(por_email) != 1:
            raise CuentaNoValida(_mensaje_alias_desconocido(cuenta, externas))
        pedida = por_email[0]

    cliente = cliente_externo(pedida)
    info = {"alias": pedida, "tipo": "externa", "email": externas[pedida]["email"]}
    anotar_acceso(info, herramienta, usuario_despacho=_quien_pide(obtener_graph))
    return cliente, info


def _quien_pide(obtener_graph: Callable[[], Any]) -> str:
    """Quién del despacho está pidiendo el buzón externo (para el registro de accesos)."""
    try:
        return getattr(obtener_graph(), "usuario", "") or ""
    except Exception:  # noqa: BLE001 - el registro no debe romper la operación
        return ""



def anotar_acceso(info: dict, herramienta: str, usuario_despacho: str = "") -> None:
    """Deja constancia de cada acceso a un buzón externo (registro de tratamiento, RGPD)."""
    if info.get("tipo") != "externa":
        return  # el buzón del despacho ya queda registrado en Microsoft 365
    linea = {"cuando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "buzon": info.get("email"), "alias": info.get("alias"),
             "herramienta": herramienta or "?", "usuario_despacho": usuario_despacho or ""}
    ruta = directorio_datos() / "accesos_externos.jsonl"
    try:
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(linea, ensure_ascii=False) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass  # no se bloquea la operación por no poder escribir el registro


def listar_cuentas() -> dict:
    """Resumen para la herramienta `cuentas_correo_listar`."""
    externas = cuentas_externas()
    return {
        "por_defecto": ALIAS_DESPACHO,
        "cuentas": [
            {"alias": ALIAS_DESPACHO, "tipo": "despacho", "por_defecto": True,
             "descripcion": "Buzón del usuario que ha iniciado sesión en Servigest."},
            *[{"alias": a, "tipo": "externa", "email": i.get("email"),
               "descripcion": i.get("descripcion", ""), "sesion": i.get("sesion")}
              for a, i in sorted(externas.items())],
        ],
        "nota": "Las herramientas de correo usan el buzón del despacho si no se indica «cuenta».",
    }


# ----------------------------------------------------------------------------------------------
# Herramientas MCP de gestión de cuentas
# ----------------------------------------------------------------------------------------------

DESC_LISTAR = """Lista las cuentas de correo que el conector puede usar: la del despacho (la de por
        defecto) y los buzones externos de otras organizaciones, con el estado de su sesión.
        Úsala cuando el usuario pregunte «qué buzones tengo» o antes de usar el parámetro cuenta."""

DESC_REGISTRAR = """Registra un buzón de OTRA organización para poder usarlo luego con el parámetro
        cuenta de las herramientas de correo. alias: nombre corto (p. ej. carlos). email: dirección
        de ese buzón. Registrarlo no da acceso: después esa persona tiene que iniciar sesión con
        cuenta_externa_iniciar_sesion. Sin confirmar=true solo muestra la vista previa."""

DESC_LOGIN = """Inicia sesión en un buzón externo ya registrado. Devuelve un código y una URL que hay
        que pasar a ESA persona (no los uses tú): ella entra, pone el código e inicia sesión con su
        cuenta de Microsoft 365. El token queda guardado cifrado y aparte del del despacho.
        Consulta después cuenta_externa_estado. Sin confirmar=true solo muestra la vista previa."""

DESC_ESTADO = """Dice si un buzón externo tiene sesión activa, pendiente de que la persona ponga el
        código, o sin sesión. Útil tras cuenta_externa_iniciar_sesion o si una herramienta de correo
        responde que hace falta iniciar sesión."""

DESC_LOGOUT = """Cierra la sesión de un buzón externo: borra su token cifrado (la cuenta sigue
        registrada y se puede volver a iniciar sesión). Sin confirmar=true solo muestra la vista previa."""


def registrar(mcp, obtener_graph: Callable[[], Any] | None = None) -> None:
    """Registra en el servidor MCP las herramientas de gestión de cuentas."""

    @mcp.tool(name="cuentas_correo_listar", description=DESC_LISTAR)
    def _listar() -> dict:
        return listar_cuentas()

    @mcp.tool(name="cuenta_externa_registrar", description=DESC_REGISTRAR)
    def _registrar(alias: str, email: str, descripcion: str = "", confirmar: bool = False) -> dict:
        if not confirmar:
            return {"vista_previa": True,
                    "accion": f"Registrar el buzón externo «{alias}» ({email})",
                    "aviso": "Solo registra el buzón; el acceso llega cuando esa persona inicia "
                             "sesión y su organización da el consentimiento.",
                    "instruccion": "Enseña esta vista previa al usuario y, si está de acuerdo, "
                                   "vuelve a llamar con confirmar=true."}
        try:
            return registrar_cuenta_externa(alias, email, descripcion)
        except CuentaNoValida as e:
            return {"error": str(e)}

    @mcp.tool(name="cuenta_externa_iniciar_sesion", description=DESC_LOGIN)
    def _login(cuenta: str, confirmar: bool = False) -> dict:
        try:
            info = cuenta_externa(cuenta)
        except CuentaNoValida as e:
            return {"error": str(e)}
        if not confirmar:
            return {"vista_previa": True,
                    "accion": f"Iniciar sesión en el buzón externo «{info['alias']}» ({info['email']})",
                    "aviso": "El código hay que dárselo a esa persona: inicia sesión ella, con su "
                             "contraseña y su MFA. Nosotros solo guardamos el token, cifrado.",
                    "instruccion": "Enseña esta vista previa al usuario y, si está de acuerdo, "
                                   "vuelve a llamar con confirmar=true."}
        try:
            res = iniciar_sesion(cuenta)
        except (CuentaNoValida, SesionRequerida) as e:
            return {"error": str(e)}
        res["instruccion"] = ("Pásale el código y la URL a esa persona. Cuando la haya usado, "
                              "comprueba con cuenta_externa_estado.")
        return res

    @mcp.tool(name="cuenta_externa_estado", description=DESC_ESTADO)
    def _estado(cuenta: str) -> dict:
        try:
            return estado_sesion(cuenta)
        except CuentaNoValida as e:
            return {"error": str(e)}

    @mcp.tool(name="cuenta_externa_cerrar_sesion", description=DESC_LOGOUT)
    def _logout(cuenta: str, confirmar: bool = False) -> dict:
        try:
            info = cuenta_externa(cuenta)
        except CuentaNoValida as e:
            return {"error": str(e)}
        if not confirmar:
            return {"vista_previa": True,
                    "accion": f"Cerrar la sesión del buzón «{info['alias']}» ({info['email']})",
                    "instruccion": "Enseña esta vista previa al usuario y, si está de acuerdo, "
                                   "vuelve a llamar con confirmar=true."}
        return cerrar_sesion(cuenta)


# ----------------------------------------------------------------------------------------------
# CLI (para el administrador, en el PC donde corre el servidor)
# ----------------------------------------------------------------------------------------------

def _cli(argv: list[str]) -> int:
    orden = (argv[0] if argv else "listar").lower()
    try:
        if orden == "listar":
            print(json.dumps(listar_cuentas(), indent=2, ensure_ascii=False))
        elif orden == "registrar":
            print(json.dumps(registrar_cuenta_externa(argv[1], argv[2],
                                                      argv[3] if len(argv) > 3 else ""),
                             indent=2, ensure_ascii=False))
        elif orden == "login":
            alias = argv[1]
            datos = iniciar_sesion(alias)
            print(datos.get("mensaje") or f"Ve a {datos['url']} y pon el código {datos['codigo']}")
            print("Esperando a que esa persona inicie sesión...")
            limite = time.time() + int(datos.get("caduca_en_segundos") or 900)
            while time.time() < limite and _estado_sesion(alias) == "pendiente":
                time.sleep(3)
            print(json.dumps(estado_sesion(alias), indent=2, ensure_ascii=False))
        elif orden == "logout":
            print(json.dumps(cerrar_sesion(argv[1]), indent=2, ensure_ascii=False))
        elif orden == "olvidar":
            print(json.dumps(olvidar_cuenta_externa(argv[1]), indent=2, ensure_ascii=False))
        else:
            print(__doc__)
            return 2
    except (CuentaNoValida, SesionRequerida) as e:
        print(f"Error: {e}")
        return 1
    except IndexError:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_cli(sys.argv[1:]))
