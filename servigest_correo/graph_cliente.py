"""Cliente HTTP mínimo de Microsoft Graph para el conector Servigest.

El servidor de Servigest ya tiene el suyo para el usuario del despacho (sesión delegada del
usuario que ha iniciado sesión en el conector). Este cliente es el que usan los **buzones
externos** (otra organización), que no pasan por esa sesión sino por su propio token guardado
cifrado (ver `cuentas.py`).

Expone la misma interfaz que espera `correo_graph`:
    get(ruta_o_url, params=None) -> dict
    post(ruta, json=None) -> dict
    .usuario   (id/UPN, para separar la paginación de cada buzón)
y lanza `GraphError` con `.status` y `.code`.
"""
from __future__ import annotations

import time
from typing import Any, Callable

GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
REINTENTOS_429 = 2


class GraphError(Exception):
    """Error devuelto por Microsoft Graph. `.status` es el código HTTP y `.code` el de Graph."""

    def __init__(self, status: int, code: str = "", mensaje: str = ""):
        super().__init__(f"{status} {code} {mensaje}".strip())
        self.status, self.code, self.mensaje = status, code, mensaje


class ClienteGraph:
    """Cliente Graph que pide el access token a `obtener_token()` en cada llamada.

    `obtener_token` debe devolver un token delegado válido (lo renueva con el refresh token
    si hace falta); así el cliente no guarda credenciales en memoria más de lo necesario.
    """

    def __init__(self, obtener_token: Callable[[], str], usuario: str = "", alias: str = ""):
        self._obtener_token = obtener_token
        self.usuario = usuario or alias or "externo"
        self.alias = alias

    # -- interno ---------------------------------------------------------------------------
    def _url(self, ruta_o_url: str) -> str:
        return ruta_o_url if ruta_o_url.startswith("https://") else f"{GRAPH}{ruta_o_url}"

    def _llamar(self, metodo: str, ruta_o_url: str, params=None, json=None) -> dict:
        import httpx  # import diferido: el servidor ya lo tiene, pero así importar el módulo no lo exige

        url = self._url(ruta_o_url)
        for intento in range(REINTENTOS_429 + 1):
            cabeceras = {"Authorization": f"Bearer {self._obtener_token()}",
                         "Content-Type": "application/json"}
            with httpx.Client(timeout=TIMEOUT) as cliente:
                r = cliente.request(metodo, url, params=params, json=json, headers=cabeceras)

            if r.status_code == 429 and intento < REINTENTOS_429:
                time.sleep(min(int(r.headers.get("Retry-After", "2") or 2), 10))
                continue
            if r.status_code >= 400:
                raise _error_de_respuesta(r)
            if r.status_code == 204 or not (r.content or b"").strip():
                return {}
            return r.json()
        raise GraphError(429, "TooManyRequests", "Microsoft Graph está limitando las peticiones.")

    # -- interfaz que usa correo_graph -----------------------------------------------------
    def get(self, ruta_o_url: str, params: dict[str, Any] | None = None) -> dict:
        return self._llamar("GET", ruta_o_url, params=params)

    def post(self, ruta: str, json: dict[str, Any] | None = None) -> dict:
        return self._llamar("POST", ruta, json=json)


def _error_de_respuesta(r) -> GraphError:
    code = mensaje = ""
    try:
        error = (r.json() or {}).get("error") or {}
        code, mensaje = error.get("code", ""), error.get("message", "")
    except Exception:  # noqa: BLE001 - cuerpo no JSON
        mensaje = (r.text or "")[:200]
    return GraphError(r.status_code, code, mensaje)
