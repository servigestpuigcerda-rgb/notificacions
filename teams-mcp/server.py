"""
Servidor MCP per enviar (i llegir) missatges de Microsoft Teams via Microsoft Graph.

Exposa aquestes eines a Claude:
  - list_chats()                       -> llista els xats (1:1 i grup) amb els seus membres i id
  - send_chat_message(chat_id, text)   -> envia un missatge a un xat pel seu id
  - send_message_to_person(name, text) -> busca el xat 1:1 amb una persona pel seu nom i li envia el missatge

Autenticació: OAuth delegat (device code flow) amb MSAL. El token es guarda en
cache a disc (token_cache.bin) perquè només calgui iniciar sessió un cop.

Permisos de Microsoft Graph necessaris (delegats):
  - Chat.ReadWrite   (enviar i llegir missatges de xat)
  - User.Read        (identitat de l'usuari)
"""

import os
import sys
import json
import atexit
import pathlib

import msal
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuració
# ---------------------------------------------------------------------------
load_dotenv()

CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
TENANT_ID = os.environ.get("MS_TENANT_ID", "common")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Chat.ReadWrite", "User.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"

# El cache es guarda al costat d'aquest fitxer
CACHE_PATH = pathlib.Path(__file__).with_name("token_cache.bin")

mcp = FastMCP("teams-sender")


# ---------------------------------------------------------------------------
# Autenticació (MSAL device code flow amb cache persistent)
# ---------------------------------------------------------------------------
def _build_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text())
    atexit.register(
        lambda: CACHE_PATH.write_text(cache.serialize()) if cache.has_state_changed else None
    )
    return cache


def _get_token() -> str:
    if not CLIENT_ID:
        raise RuntimeError(
            "Falta MS_CLIENT_ID. Configura l'app d'Entra ID i posa'l al fitxer .env "
            "(mira el README)."
        )

    cache = _build_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    # 1) Intenta silenciosament amb un compte ja loguejat
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

    # 2) Device code flow: l'usuari inicia sessió un cop
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"No s'ha pogut iniciar el device flow: {json.dumps(flow)}")
    # El missatge d'instruccions surt per stderr (visible als logs de l'MCP)
    print(flow["message"], file=sys.stderr, flush=True)

    result = app.acquire_token_by_device_flow(flow)  # bloqueja fins que l'usuari valida
    if "access_token" not in result:
        raise RuntimeError(
            f"Error autenticant: {result.get('error_description', result)}"
        )
    return result["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Eines MCP
# ---------------------------------------------------------------------------
@mcp.tool()
def list_chats(limit: int = 25) -> str:
    """Llista els xats de Teams (1:1 i grup) amb el seu id, tema i membres.

    Útil per trobar el chat_id d'una persona abans d'enviar-li un missatge.
    """
    url = f"{GRAPH}/me/chats?$expand=members&$top={min(limit, 50)}"
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    out = []
    for chat in data.get("value", []):
        members = ", ".join(
            m.get("displayName", "?") for m in chat.get("members", [])
        )
        out.append(
            {
                "id": chat.get("id"),
                "type": chat.get("chatType"),
                "topic": chat.get("topic"),
                "members": members,
            }
        )
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp.tool()
def send_chat_message(chat_id: str, text: str) -> str:
    """Envia un missatge de text a un xat de Teams identificat pel seu chat_id."""
    url = f"{GRAPH}/chats/{chat_id}/messages"
    body = {"body": {"contentType": "text", "content": text}}
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, headers=_headers(), json=body)
        resp.raise_for_status()
        msg = resp.json()
    return f"OK, missatge enviat (id: {msg.get('id')})."


@mcp.tool()
def send_message_to_person(name: str, text: str) -> str:
    """Busca el xat 1:1 amb una persona pel seu nom (coincidència parcial) i li envia el missatge.

    Si troba diversos xats que coincideixen, retorna la llista perquè triïs el chat_id
    i facis servir send_chat_message.
    """
    url = f"{GRAPH}/me/chats?$expand=members&$top=50"
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_headers())
        resp.raise_for_status()
        chats = resp.json().get("value", [])

    name_low = name.lower()
    matches = []
    for chat in chats:
        if chat.get("chatType") != "oneOnOne":
            continue
        for m in chat.get("members", []):
            if name_low in (m.get("displayName", "").lower()):
                matches.append((chat["id"], m.get("displayName")))
                break

    if not matches:
        return (
            f"No he trobat cap xat 1:1 amb '{name}'. Fes servir list_chats() per veure "
            f"els disponibles."
        )
    if len(matches) > 1:
        return "He trobat diversos xats:\n" + "\n".join(
            f"- {n} -> chat_id: {cid}" for cid, n in matches
        )

    chat_id, disp = matches[0]
    return send_chat_message(chat_id, text) + f" (destinatari: {disp})"


if __name__ == "__main__":
    mcp.run()
