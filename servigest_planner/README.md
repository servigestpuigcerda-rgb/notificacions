# Microsoft Planner per al connector Servigest

Sis eines noves per al servidor MCP de Servigest. Totes treballen amb el token **delegat** de qui ha iniciat sessió: cada persona només veu els plans dels seus grups de Microsoft 365.

| Eina | Què fa | Escriu? |
|---|---|---|
| `planner_planes` | Llista els plans de l'usuari amb les seves columnes (*buckets*) i els ids. | No |
| `planner_tareas` | Llista les tasques d'un plan, de qualsevol persona. Mostra responsables i columna pel nom, avanç, prioritat, dates i si tenen comentaris. Es pot filtrar per responsable, columna, text o vençudes. | No |
| `planner_crear_tarea` | Crea una tasca i l'**assigna** a una o més persones. Accepta data, prioritat, descripció i llista de comprovació (*checklist*). | Vista prèvia → `confirmar=true` |
| `planner_modificar_tarea` | Canvia títol, columna, responsables (afegir i treure), dates, avanç, prioritat i descripció. També afegeix i marca punts del checklist. | Vista prèvia → `confirmar=true` |
| `planner_comentarios` | Llegeix el xat de comentaris d'una tasca. | No |
| `planner_comentar` | Escriu un comentari a una tasca. | Vista prèvia → `confirmar=true` |

El pla, la columna i les persones es poden indicar **pel nom**, sense distingir accents ni majúscules, o per id. Si un nom és ambigu, l'eina retorna les opcions perquè l'usuari triï. Només es pot assignar una tasca a membres del grup del pla, perquè és una limitació de Planner.

## Exemples

```jsonc
// «Quins plans tinc?»
{"tool": "planner_planes", "arguments": {}}

// «Quines tasques té en Carles al pla Fiscal Badalona?»
{"tool": "planner_tareas", "arguments": {"plan": "fiscal badalona", "responsable": "Carles"}}

// «Què hi ha vençut a Planner?»
{"tool": "planner_tareas", "arguments": {"plan": "Fiscal Badalona", "vencidas": true}}

// Crear i assignar: 1) vista prèvia  2) confirmar
{"tool": "planner_crear_tarea", "arguments": {"plan": "Fiscal Badalona", "titulo": "Revisar 303 4T",
  "columna": "Pendent", "responsables": ["Berta", "Silvia"], "vence": "2027-01-20", "prioridad": "importante",
  "checklist": ["Demanar factures", "Quadrar IVA"]}}
// … i el mateix amb "confirmar": true

// Reassignar i marcar com a en curs
{"tool": "planner_modificar_tarea", "arguments": {"tarea_id": "…", "anadir_responsables": ["Dani"],
  "quitar_responsables": ["José"], "avance": 50, "confirmar": true}}

// Comentaris
{"tool": "planner_comentarios", "arguments": {"tarea_id": "…"}}
{"tool": "planner_comentar", "arguments": {"tarea_id": "…", "comentario": "Factures rebudes", "confirmar": true}}
```

Proves, amb Graph simulat: `python -m pytest servigest_planner -q` (12 proves).

## Desplegament al servidor Servigest (PC d'en Xavi)

1. Copia la carpeta `servigest_planner/` al costat del codi del servidor.
2. Al fitxer on es registren les eines, afegeix:
   ```python
   from servigest_planner.planner_graph import registrar as registrar_planner
   registrar_planner(mcp, obtener_graph)
   ```
   `obtener_graph()` ha de tornar el client de Graph de l'usuari de la petició. Aquest client necessita `get`, `post` i `patch`, i els tres han d'acceptar `headers`. És imprescindible per enviar `If-Match`, que Planner exigeix en modificar.
   `post` i `patch` han de tornar `{}` quan Graph respon 204. En cas d'error han de llançar una excepció amb `.status` i `.code`.
3. Afegeix els permisos a Azure (secció següent) i reinicia el servei.
4. A Claude, desconnecta i torna a connectar Servigest perquè carregui les eines noves.
5. Recomanat: modifica la descripció de `tareas_crear` perquè remeti a `planner_crear_tarea` quan es parli de Planner.

## Permisos a Azure (Entra ID → App registrations → app de Servigest → API permissions)

Tots són de tipus **delegat**. Després cal fer **Grant admin consent**, i cada usuari ha de tornar a iniciar sessió.

| Permís | Per a què |
|---|---|
| `Tasks.ReadWrite` | Llegir, crear i modificar tasques de Planner. |
| `Group.Read.All` | Llistar els grups de l'usuari i els membres, per assignar per nom. |
| `Group.ReadWrite.All` | Comentaris: llegir i escriure a la conversa del grup. Si no es vol donar aquest permís, `planner_comentar` no funcionarà i la resta sí. |

Si falta algun permís, les eines retornen un missatge clar que indica quin falta.

## Avisos

- **Comentaris:** el Planner clàssic guarda els comentaris com a conversa del grup de Microsoft 365, i és el que fa servir aquest codi. Microsoft està migrant els comentaris al **Planner nou**. Si al tenant la tasca ja fa servir els comentaris nous, Graph encara no els exposa. En aquest cas `planner_comentarios` pot no mostrar-los i `planner_comentar` escriurà a la conversa del grup. Cal provar-ho amb una tasca real abans de dir-ho a l'equip.
- **Plans personals:** els plans de «Les meves tasques» o els plans premium (Project for the web) no són accessibles per Graph.
- **Accents trencats a `tareas_listar`:** alguns títols surten malmesos, com «INFORMACIÃ“» o «Env�o». Vol dir que en algun punt el servidor llegeix la resposta de Graph sense UTF-8. Cal revisar-ho a `tareas_listar`: per exemple, fer servir `response.json()` en comptes de descodificar el text a mà, o forçar `response.encoding = "utf-8"`. Aquest mòdul no en depèn.
