# Buzones de otra organización en el conector Servigest

Para leer y enviar correo de un buzón de Microsoft 365 que **no está en el tenant del despacho**
(por ejemplo el de Carlos), sin tocar cómo funciona hoy el buzón propio.

---

## 1. Cómo autentica hoy el conector (revisión)

| Pieza | Cómo funciona hoy |
|---|---|
| Tipo de permiso | **Delegado** (en nombre del usuario), nunca permisos de aplicación |
| Identidad | La del usuario que ha iniciado sesión en el conector Servigest |
| Rutas de Graph | Siempre `/me/...` (`/me/messages`, `/me/mailFolders/...`). Nunca `/users/{id}` |
| Token | Lo gestiona el servidor MCP (PC del Xavi) para la sesión en curso; los módulos de este repo reciben un cliente ya autenticado mediante `obtener_graph()` |
| Tenant | **Uno solo**: la app de Entra ID está registrada para la organización del despacho |
| Patrón equivalente en este repo | `teams-mcp/server.py`: MSAL `PublicClientApplication` + **device code flow** + cache de token en disco (`token_cache.bin`, sin cifrar) |
| Permisos de correo actuales | `Mail.Read` / `Mail.ReadWrite` delegados (ver `permisos.py` para comprobar un token) |

Consecuencia: hoy **no se puede** llegar al buzón de Carlos. Su buzón vive en otro tenant, y el
token del despacho no vale allí; tampoco serviría pedir permisos de aplicación (darían acceso a
*todos* los buzones de un tenant, que es justo lo que no queremos).

La solución implementada: la misma app, marcada como **multiorganización**, y un **segundo token
delegado** que obtiene Carlos iniciando sesión él mismo. Ese token se guarda **aparte y cifrado**.

---

## 2. Qué cambiar en el registro de la app (Entra ID)

Portal: <https://portal.azure.com> → **Microsoft Entra ID → App registrations → [app de Servigest]**.

### 2.1 Tipos de cuenta admitidos

**Authentication → Supported account types** → marcar:

> **Accounts in any organizational directory (Any Microsoft Entra ID tenant – Multitenant)**

En el **Manifest** es `"signInAudience": "AzureADMultipleOrgs"`.

- No hace falta «…and personal Microsoft accounts»: el buzón de Carlos es de empresa.
- Cambiar esto **no afecta** a los usuarios actuales del despacho: siguen entrando igual.

### 2.2 Flujo de cliente público (lo que usa el device code)

**Authentication → Advanced settings → Allow public client flows → Yes**
(en el Manifest, `"allowPublicClient": true`).

### 2.3 URI de redirección

El device code flow **no necesita URI de redirección**, y es el flujo elegido porque el servidor
corre en un PC sin HTTPS público. Aun así conviene registrar una, por dos motivos (consentimiento
de administrador y poder pasar luego a un flujo interactivo):

**Authentication → Add a platform → Mobile and desktop applications**, y marcar:

- `https://login.microsoftonline.com/common/oauth2/nativeclient`
- `http://localhost` (si algún día se usa `acquire_token_interactive` en el propio PC)

Si en el futuro se monta un flujo de código de autorización con navegador (servidor publicado con
HTTPS), entonces sí: plataforma **Web** con `https://<tu-servidor>/oauth/callback`.

### 2.4 Permisos delegados

**API permissions → Add a permission → Microsoft Graph → Delegated permissions**:

| Permiso | Para qué |
|---|---|
| `Mail.ReadWrite` | Leer, buscar y mover correo del buzón |
| `Mail.Send` | Enviar y responder desde ese buzón |
| `offline_access` | Refresh token: no hay que volver a iniciar sesión cada hora |
| `openid`, `profile` | Identidad (saber qué buzón ha iniciado sesión). MSAL los añade solo |

Después, **Grant admin consent** en el tenant del despacho.

> **No añadir los equivalentes de tipo Application** (`Mail.ReadWrite` / `Mail.Send` de aplicación):
> darían acceso a todos los buzones del tenant y requieren consentimiento global. Con delegado,
> el alcance es exactamente el buzón de quien ha iniciado sesión.

### 2.5 Consentimiento en el tenant externo (el de Carlos)

El «Grant admin consent» del despacho **no cubre** la organización de Carlos. Dos caminos:

1. **Carlos consiente él mismo** al iniciar sesión, si su organización permite el consentimiento
   de usuario. Es el camino normal: le sale la pantalla con los permisos y acepta.
2. **Su administrador lo aprueba antes**, abriendo esta URL (sustituyendo los dos valores) e
   iniciando sesión como admin de ese tenant:

   ```
   https://login.microsoftonline.com/<TENANT-DE-CARLOS>/v2.0/adminconsent
     ?client_id=<CLIENT-ID-DE-LA-APP>
     &scope=https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send offline_access
     &redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient
   ```

   `<TENANT-DE-CARLOS>` puede ser su dominio (`empresadecarlos.com`) o el id del directorio.

Al consentir, en el tenant de Carlos aparece la app en **Enterprise applications**. Desde allí su
administrador puede revisar los permisos y **revocarlos cuando quiera**, sin depender de nosotros.

Si el inicio de sesión falla con `AADSTS65001` (falta consentimiento) o `AADSTS50020` (la app no
admite otras organizaciones), el conector ya devuelve el mensaje con el paso que falta.

### 2.6 Resumen de los cambios

| Ajuste | Antes | Después |
|---|---|---|
| Supported account types | Single tenant | **Multitenant** (`AzureADMultipleOrgs`) |
| Allow public client flows | — | **Yes** |
| Redirect URI | — | `…/common/oauth2/nativeclient` (+ `http://localhost`) |
| Permisos delegados | `Mail.Read(Write)` | `Mail.ReadWrite`, `Mail.Send`, `offline_access` |
| Consentimiento | Tenant del despacho | Tenant del despacho **y** tenant de Carlos |

---

## 3. Inicio de sesión de la cuenta externa y guardado del token

Implementado en `cuentas.py`. Características:

- **Device code flow** de MSAL contra `https://login.microsoftonline.com/organizations`
  (configurable con `SERVIGEST_AUTORIDAD_EXTERNA`; también vale `common`).
- Carlos inicia sesión **él mismo**, con su contraseña y su MFA: el conector solo recibe el token.
  Nunca se le pide la contraseña ni se escribe en ningún sitio.
- El token (la cache de MSAL, con el refresh token) se guarda **cifrado con Fernet/AES-128-CBC +
  HMAC** en `token_<alias>.enc`, con permisos `0600` y en una carpeta `0700`.
  **Separado del token del despacho**, que sigue donde estaba (la sesión del conector).
- La clave de cifrado sale de `SERVIGEST_TOKEN_KEY` (recomendado) o, si no existe, de
  `clave_tokens.key` (0600) creada automáticamente.
  → Lo ideal es poner `SERVIGEST_TOKEN_KEY` en el entorno del servicio, para que la clave no viva
  en el mismo disco que los tokens.
- Si quien inicia sesión **no es** el buzón registrado, el token **se descarta**.
- Cada acceso al buzón externo queda anotado en `accesos_externos.jsonl` (fecha, buzón,
  herramienta y usuario del despacho que lo pidió).

### Herramientas nuevas en el conector

| Herramienta | Qué hace |
|---|---|
| `cuentas_correo_listar` | Lista los buzones disponibles y el estado de su sesión |
| `cuenta_externa_registrar` | Da de alta el buzón (alias + email). Vista previa → `confirmar=true` |
| `cuenta_externa_iniciar_sesion` | Devuelve el **código y la URL** para dárselos a esa persona |
| `cuenta_externa_estado` | `sin_sesion` / `pendiente` / `activa` / `error`, con el motivo |
| `cuenta_externa_cerrar_sesion` | Borra el token cifrado de ese buzón |

### Lo mismo desde la línea de órdenes del servidor

```bash
python -m servigest_correo.cuentas registrar carlos carlos@empresadecarlos.com "Buzón de Carlos"
python -m servigest_correo.cuentas login carlos      # muestra el código y espera
python -m servigest_correo.cuentas listar
python -m servigest_correo.cuentas logout carlos     # borra el token
python -m servigest_correo.cuentas olvidar carlos    # borra token + registro
```

### Variables de entorno

```bash
SERVIGEST_CLIENT_ID=<client id de la app multiorganización>   # o MS_CLIENT_ID
SERVIGEST_TOKEN_KEY=<clave Fernet>        # python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
SERVIGEST_DATOS_DIR=/ruta/datos/cuentas   # por defecto ~/.servigest/cuentas
SERVIGEST_AUTORIDAD_EXTERNA=https://login.microsoftonline.com/organizations
SERVIGEST_CUENTAS_EXTERNAS=carlos=carlos@empresadecarlos.com   # opcional, alternativa al registro
```

Dependencias: `msal`, `cryptography`, `httpx` (las dos primeras ya las usa el servidor para Graph).

---

## 4. El parámetro `cuenta` en las herramientas de correo

```jsonc
// Buzón del despacho (lo normal: no hay que poner nada)
{"tool": "buscar_correos", "arguments": {"solo_no_leidos": true}}
// → {..., "buzon": "despacho"}

// Buzón de Carlos, pedido expresamente
{"tool": "buscar_correos", "arguments": {"cuenta": "carlos", "solo_no_leidos": true}}
// → {..., "buzon": "carlos <carlos@empresadecarlos.com>", "aviso_buzon": "Buzón EXTERNO..."}

// Un alias que no existe: error, nunca se usa otro buzón
{"tool": "buscar_correos", "arguments": {"cuenta": "carles"}}
// → {"error": "No existe ninguna cuenta de correo llamada «carles». Cuentas disponibles: ..."}
```

Reglas (en `cuentas.resolver_cuenta`):

1. Sin `cuenta`, o con `despacho` (y sinónimos como «mi buzón», «gestoria»), **siempre** el buzón
   del usuario que ha iniciado sesión.
2. Un buzón externo solo se usa nombrando su **alias exacto** o su **email exacto**.
3. Un alias desconocido es un **error**: no hay búsqueda aproximada ni vuelta atrás a otro buzón.
4. La respuesta dice siempre qué buzón se ha usado (`buzon`), y los buzones externos llevan además
   `aviso_buzon` para que quede claro en la conversación.
5. La paginación (`continuar`) va por buzón: un `continuar` sin `cuenta` no sigue por los
   resultados de Carlos.

### Añadirlo al resto de herramientas de correo del servidor

Las de este repo (`buscar_correos`, `mover_correo`) ya lo llevan. Para las que viven en el código
del servidor (`leer_correo`, `leer_adjunto`, `listar_carpetas_correo`, `crear_carpeta_correo`,
`mover_correos`, `crear_borrador`, `enviar_borrador`, `responder_correo`, `reenviar_correo`,
`categorizar_correos`, `listar_envios_programados`, `cancelar_envio_programado`…) el cambio es de
tres líneas por herramienta:

```python
from servigest_correo.correo_graph import con_cuenta   # arriba del fichero

@mcp.tool()
def leer_correo(correo_id: str, cuenta: str = "") -> dict:      # 1) parámetro nuevo
    graph, info, error = con_cuenta(obtener_graph, cuenta, "leer_correo")   # 2) resolver
    if error:
        return error
    ...                                 # 3) usar `graph` donde antes había obtener_graph()
```

Para las que envían correo (`enviar_borrador`, `responder_correo`, `reenviar_correo`) hay que tener
presente que, con `cuenta="carlos"`, **el remitente es Carlos**: conviene decirlo en la vista previa
(`_marcar_buzon` de `correo_graph.py` ya añade `buzon` y `aviso_buzon`, reutilizable tal cual).

---

## 5. Despliegue

1. Copiar la carpeta `servigest_correo/` junto al código del servidor (ya incluye `cuentas.py` y
   `graph_cliente.py`).
2. En el fichero donde se registran las tools:

   ```python
   from servigest_correo.correo_graph import registrar as registrar_correo
   from servigest_correo.cuentas import registrar as registrar_cuentas

   registrar_correo(mcp, obtener_graph)   # buscar_correos y mover_correo, ya con `cuenta`
   registrar_cuentas(mcp)                 # gestión de buzones externos
   ```
3. Poner las variables de entorno del apartado 3 en el servicio y reiniciarlo.
4. En Claude: Settings → Connectors → Servigest → desconectar y volver a conectar (para que
   recargue la lista de herramientas).
5. Registrar el buzón e iniciar sesión (apartado 3), y comprobar con `cuentas_correo_listar`.

Pruebas, con Graph y MSAL simulados y sin red:

```bash
python -m pytest servigest_correo -q
```

---

## 6. Protección de datos

Acceder al correo de otra empresa no es un asunto solo técnico:

- Hace falta **autorización escrita de Carlos** (y de su organización, que es la responsable del
  tratamiento) y un **contrato de encargo de tratamiento** con el despacho, con la finalidad y el
  plazo bien definidos.
- El acceso es **delegado y limitado a ese buzón**: ni otros buzones de su tenant, ni más permisos
  que `Mail.ReadWrite` + `Mail.Send`.
- Su administrador puede **revocarlo en cualquier momento** desde Enterprise applications; el
  despacho puede hacerlo con `cuenta_externa_cerrar_sesion`.
- `accesos_externos.jsonl` da la **traza** de quién del despacho accedió, cuándo y con qué
  herramienta: sirve para el registro de actividades de tratamiento.
- Conviene añadir este tratamiento al registro de actividades y revisar las sesiones externas
  activas de vez en cuando (`cuentas_correo_listar`).
