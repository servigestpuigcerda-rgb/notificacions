# Correo Outlook para el conector Servigest: `buscar_correos` ampliada y `mover_correo` nueva

Código listo para integrar en el servidor MCP de Servigest (Python, FastMCP), que corre en el PC del Xavi.
Va siempre contra `/me` con el **token delegado** de quien ha iniciado sesión. Así, cada persona (por ejemplo, Carles) trabaja con su propio buzón.

## Cambios

**buscar_correos**
- Nuevo parámetro `solo_no_leidos` (por defecto `false`).
- Cada correo incluye `leido` (true/false).
- Sin texto, remitente ni destinatario, todo va en `$filter`: `receivedDateTime ge … and isRead eq false`, ordenado por fecha. Graph exige que `receivedDateTime` aparezca primero en el filtro.
- Con texto, remitente o destinatario se usa `$search`. Graph **no permite combinar `$search` con `$filter`** en mensajes. En ese caso se piden más resultados y los no leídos se filtran en local.
- Se combina con todos los filtros: carpeta, fechas, adjuntos, paginación con `continuar`.
- La descripción incluye «resúmeme los correos que no he leído».

**mover_correo**: tool nueva
- `correo_id` acepta un id, una lista de ids o ids separados por comas (máximo 50). Genera una sola vista previa.
- `carpeta_destino` acepta:
  - un id de `listar_carpetas_correo`;
  - un nombre estándar: `inbox`, `archive`, `deleteditems`, `junkemail`…, o un alias como «archivo» o «papelera»;
  - un nombre o una ruta de carpeta propia, como `Clientes/2026`.
- Si la carpeta no existe o el nombre es ambiguo, devuelve un error que lista las coincidencias y sugiere usar `listar_carpetas_correo`.
- Sin `confirmar=true` devuelve una vista previa: asunto, remitente, fecha, carpeta actual y carpeta de destino.
- Con `confirmar=true` mueve el correo con `POST /me/messages/{id}/move` y devuelve `id_anterior` → `id_nuevo`.
- Si Graph responde 403, devuelve un mensaje claro: falta Mail.ReadWrite.

## Ejemplos de llamada

```jsonc
// «Resúmeme los correos que no he leído»
{"tool": "buscar_correos", "arguments": {"solo_no_leidos": true, "carpeta": "inbox", "maximo": 20}}
// → {"total": 1, "correos": [{"id": "AAMk…", "fecha": "…", "asunto": "…", "remitente": "…", "leido": false, "adjuntos": []}], "filtro": "solo no leídos"}

// No leídos de un remitente desde una fecha
{"tool": "buscar_correos", "arguments": {"remitente": "notificaciones@ejemplo.es", "desde": "2026-11-01", "solo_no_leidos": true}}

// Mover: 1) vista previa  2) confirmar
{"tool": "mover_correo", "arguments": {"correo_id": ["AAMk…1", "AAMk…2"], "carpeta_destino": "Clientes/2026"}}
{"tool": "mover_correo", "arguments": {"correo_id": ["AAMk…1", "AAMk…2"], "carpeta_destino": "Clientes/2026", "confirmar": true}}
// → {"movidos": [{"id_anterior": "AAMk…1", "id_nuevo": "AAMk…X", "asunto": "…"}], "carpeta_destino": "Clientes/2026", …}
```

Pruebas, con Graph simulado y sin red: `python -m pytest servigest_correo -q`

## Despliegue en el servidor Servigest

1. Copia la carpeta `servigest_correo/` junto al código del servidor.
2. En el archivo donde se definen las tools de correo:
   - **borra** la función `buscar_correos` actual;
   - añade:
   ```python
   from servigest_correo.correo_graph import registrar as registrar_correo
   registrar_correo(mcp, obtener_graph)   # mcp = la instancia FastMCP del servidor
   ```
   `obtener_graph()` debe devolver el cliente Graph **del usuario de la petición**, el mismo que usan `leer_correo` y `crear_carpeta_correo`. Ese cliente necesita:
   - `get(ruta_o_url, params=None) -> dict` y `post(ruta, json=None) -> dict`, que acepten una URL absoluta (para el `@odata.nextLink`);
   - en caso de error, lanzar una excepción con `.status` (código HTTP) y `.code` (error de Graph), o `GraphError`;
   - un atributo `usuario` (id o UPN), para guardar la paginación de cada persona por separado.

   Si el cliente actual tiene otra forma, basta un adaptador de unas 10 líneas.
3. Reinicia el servicio del servidor MCP.
4. En Claude, desconecta y vuelve a conectar Servigest (Settings → Connectors) para que recargue la lista de tools.

## Permiso Mail.ReadWrite en Azure (imprescindible para mover)

1. Abre portal.azure.com → **Microsoft Entra ID → App registrations** → app de Servigest → **API permissions**.
2. Comprueba que esté **Microsoft Graph → Delegated → Mail.ReadWrite**. Si solo aparece `Mail.Read`, añade `Mail.ReadWrite`.
3. Pulsa **Grant admin consent** para el tenant.
4. Si el servidor pide scopes explícitos al hacer login, añade `Mail.ReadWrite` a esa lista.
5. Cada usuario, Carles incluido, debe volver a iniciar sesión en Servigest para obtener un token con el permiso nuevo.
6. Para comprobarlo, ejecuta `python -m servigest_correo.permisos <access_token>`. El resultado indica si el token tiene `Mail.ReadWrite` o solo `Mail.Read`.

Usa el permiso **delegado**, no el de aplicación. Con el delegado, cada persona solo puede tocar su propio buzón (RGPD).
