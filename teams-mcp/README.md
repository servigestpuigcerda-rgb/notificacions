# Teams Sender — Servidor MCP per enviar missatges a Teams

Servidor MCP que dóna a Claude la capacitat d'**enviar** (i llegir) missatges de
Microsoft Teams via Microsoft Graph. El connector oficial de Microsoft 365 és de
**només lectura**; aquest servidor afegeix l'escriptura (`Chat.ReadWrite`).

## Eines que exposa
- `list_chats()` — llista els teus xats amb id i membres.
- `send_chat_message(chat_id, text)` — envia a un xat pel seu id.
- `send_message_to_person(name, text)` — busca el xat 1:1 amb una persona i li envia.

---

## Posada en marxa (una sola vegada)

### 1) Registrar una app a Entra ID (Azure AD)
1. Ves a **https://entra.microsoft.com** → **Identity → Applications → App registrations → New registration**.
2. Nom: p. ex. `Claude Teams Sender`. A *Supported account types* deixa
   "Accounts in this organizational directory only". **Register**.
3. Copia el **Application (client) ID** i el **Directory (tenant) ID**.
4. A **Authentication → Advanced settings**, activa **Allow public client flows = Yes**. **Save**.
5. A **API permissions → Add a permission → Microsoft Graph → Delegated permissions**,
   afegeix **`Chat.ReadWrite`** i **`User.Read`**.
   - Si surt "admin consent required", que un **administrador** premi
     **Grant admin consent**.

> No cal client secret: fem servir *device code flow* (l'usuari inicia sessió).

### 2) Instal·lar dependències
```bash
cd teams-mcp
pip install -r requirements.txt
```

### 3) Configurar credencials
```bash
cp .env.example .env
# edita .env i posa MS_CLIENT_ID i MS_TENANT_ID
```

### 4) Iniciar sessió un cop (device code)
La primera vegada que s'usi una eina, el servidor imprimirà (als logs) un
missatge tipus:
> *To sign in, use a web browser to open https://microsoft.com/devicelogin and
> enter the code XXXXXXXXX to authenticate.*

Obre l'enllaç, posa el codi i inicia sessió amb el compte de Teams. El token queda
guardat a `token_cache.bin` (ja ignorat pel git) i no caldrà repetir-ho.

### 5) Registrar-lo a Claude Code
Ja hi ha un `.mcp.json` a l'arrel del repo amb el servidor `teams-sender`.
Perquè Claude el carregui:
- Exporta les variables abans d'obrir Claude Code, **o** posa els valors
  directament al `.mcp.json` (en comptes de `${MS_CLIENT_ID}`).
- **Obre una sessió nova** de Claude Code al repo i accepta el servidor MCP quan
  ho demani.

---

## Notes de seguretat
- `.env` i `token_cache.bin` **no** es pugen al git (`.gitignore`).
- El servidor només fa el que li demanis explícitament (enviar un missatge concret).
- Els permisos són **delegats**: actua en nom teu, respectant els teus accessos.
