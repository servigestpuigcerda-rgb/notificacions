# Gestió d'obres

Aplicació web per portar pressupostos, albarans de feina, costos i benefici de cada feina, facturació i la comunicació amb el client. Funciona al mòbil (es pot instal·lar com una app) i a l'ordinador, amb la pantalla adaptada a cada un.

## Què fa

**Feines**
- Crees una feina (amb client nou o existent) i hi vas penjant pressupostos, hores, despeses, albarans, factures, missatges i documents.
- En qualsevol moment veus com va: contractat, cost previst i cost real, hores previstes i reals, facturat, cobrat, **el que queda per facturar** i el benefici previst al final.
- Comparació partida a partida (mà d'obra, material, subcontractes…) entre el previst i el real, amb alertes quan una partida es desvia o les hores superen les previstes.
- Dos modes de facturació: per pressupost (preu tancat) o per administració (hores + material amb benefici).

**Assistent per veu (o escrit), a qualsevol pantalla**
- 🎙️ «Digues què vols fer»: «afegeix 4 hores de mà d'obra a la feina del carrer Major», «al pressupost del bany canvia la rajola a 28 € el m2», «afegeix a la factura un desplaçament de 30 €», «posa una nota: dimarts arriba el plat de dutxa», «afegeix al planning la fase d'enrajolat de dilluns a dimecres».
- La IA ho converteix en accions i **te les mostra abans de fer res**: tu confirmes, tries la feina si no està clara i després s'executen.
- Si afegeixes alguna cosa a un pressupost ja acceptat, es crea automàticament un «fora de pressupost» per enviar al client.

**Captura ràpida des del mòbil**
- 📷 Fas una foto d'un tiquet, albarà o factura de proveïdor. La IA en llegeix proveïdor, NIF, número, data, base, IVA i total, i proposa la feina i la partida. Tu revises i confirmes.
- L'app aprèn a quina partida va cada proveïdor i la següent vegada l'imputa sola.
- ⏱️ Apuntar hores amb dos tocs: tries la feina (recorda l'última) i les hores.
- Les despeses es poden repercutir al client amb un % de benefici.

**Pressupostos**
- Editor amb línies d'article, mà d'obra o lliures. Cost, marge %, preu i descompte per línia, descompte global, IVA i IRPF. Veus el cost, el benefici, el marge i les hores en directe.
- 🎤 **Dictes l'explicació de la feina** i la IA prepara les línies a partir del catàleg d'articles, les tarifes i l'historial. Et diu les hipòtesis que ha fet i què cal confirmar.
- **Revisió amb l'historial**: detecta errors (sense preu, per sota de cost, marges baixos, línies repetides, sense mà d'obra) i et diu si **anem curts d'hores o de material** segons com van anar les feines semblants. Mostra els pressupostos semblants amb les hores i el cost reals que van tenir.
- Cada línia pot portar la **referència o model del material** i una **foto** (també surten al pressupost imprès i al portal del client).
- Enviament al client per WhatsApp o correu amb un enllaç on el pot veure i acceptar.
- Un pressupost acceptat queda bloquejat. Per a qualsevol treball afegit es fa un **«fora de pressupost»**, que s'envia al client com a avís i que també ha d'acceptar.

**Maqueta 3D del resultat**
- Fas fotos de l'estat actual, poses les mides i expliques com ha de quedar. La IA construeix una maqueta 3D de l'estança acabada (parets, porta i finestres, plat de dutxa, mobles, sanitaris…).
- La pots girar i apropar amb el dit, canviar mides, moure elements i **canviar els materials** (color, rajola, parquet, mida de la peça o la **foto real del material**). També pots demanar canvis dient-los («posa parquet de roure a terra»).
- La pots compartir amb el client, que la veu al seu enllaç, i desar-ne una imatge.
- És una maqueta orientativa, no un render fotorealista: Claude no genera imatges. Per a renders fotogràfics caldria connectar un servei extern de generació d'imatges.

**Planning i evolució**
- Fases de la feina amb dates i % fet. Publicació d'evolució amb text i fotos. El client ho veu al seu enllaç.

**Articles**
- Catàleg amb cost, marge o preu fix, descompte i proveïdor. Pots aplicar un marge o un descompte a molts articles alhora (per selecció o per partida).

**Albarans de feina**
- Recullen la feina feta, el material i les hores. El client els signa al mòbil (amb el dit) o des del seu enllaç.

**Facturació**
- Factures parcials: un % del pressupost (10, 25, 30, 50…), línia a línia (certificació d'obra), o les despeses i hores pendents de repercutir.
- Numeració correlativa per sèrie i any, assignada en emetre (els esborranys no consumeixen número). Una factura emesa no es pot modificar: s'anul·la amb una **factura rectificativa**.
- Control de vençuts i cobraments. Còpia fixa de cada factura emesa a la carpeta de documents.

**Impostos i gestor**
- Resum per trimestre o any: IVA repercutit i suportat (303), retencions d'IRPF, ingressos i despeses. Avisa dels tiquets sense NIF del proveïdor, que no donen dret a deduir l'IVA.
- **Estimació del trimestre**: IVA a pagar i pagament fraccionat d'IRPF (model 130, si ets autònom), amb el real fins avui i la projecció a final de trimestre.
- **Envia al gestor** amb un botó: un ZIP amb les factures de venda, les factures i tiquets de compra (amb les fotos), els llibres de registre en CSV i el resum. Al mòbil s'obre el menú de compartir (correu, WhatsApp…); a l'ordinador es descarrega i s'obre el correu.

**Anàlisi en tancar cada feina**
- Previst vs real per partida, hores, marge, canvis fora de pressupost, temps de cobrament i valoració del client.
- **Què ha anat bé, què ha fallat i propostes per al proper pressupost** (amb IA, si està activa). Les propostes es fan servir automàticament quan prepares pressupostos del mateix tipus.

**Comunicació amb el client**
- Cada feina té un enllaç personal per al client (sense usuari ni contrasenya) on veu: pressupostos, canvis fora de pressupost, albarans, factures, planning, evolució amb fotos i la maqueta 3D. Pot acceptar, rebutjar, signar, comentar, fer peticions de canvi, consultar dubtes i **deixar valoracions**.
- **Pagament**: cada factura té el botó «Pagar per transferència o Bizum» amb l'IBAN, el telèfon de Bizum, l'import i el concepte per copiar. Quan el client prem «Ja he pagat», t'arriba l'avís per comprovar l'ingrés i marcar-la cobrada. (No és un cobrament automàtic: Bizum per a empreses requereix contractar-lo amb el banc.)
- **Bloquejos visibles**: el client veu clarament que la feina **no pot començar** fins que accepti el pressupost, i que **queda aturada** mentre hi hagi canvis pendents d'acceptar o una factura enviada sense pagar (pots desactivar el bloqueig a cada factura).
- **El que li queda**: factures pendents de pagar i la resta de l'obra per facturar.
- L'app hi deixa constància automàticament de l'enviament i l'acceptació de pressupostos, els avisos de fora de pressupost, les factures i el tancament. Les notes internes no les veu el client.

**Documents**
- Una carpeta per feina amb fotos, tiquets, factures de proveïdor, pressupostos acceptats i factures emeses, amb cercador.

**Aprenentatge**
- Amb cada feina tancada, l'app calcula la desviació real d'hores i de material per tipus de feina (bany, cuina, pintura…), el marge real i la partida habitual de cada proveïdor. Ho fa servir per avisar en els pressupostos nous i com a context per a la IA quan prepara un pressupost dictat.
- Tot és visible a la secció «Què he après». Perquè aprengui bé, cal posar el **tipus de feina**, imputar bé les hores i les despeses i **tancar les feines** quan s'acaben.

## Posar-la en marxa

Cal Python 3.10 o posterior.

```sh
cd gestio-obres
cp .env.example .env      # opcional: hi poses la clau de la IA
./arrenca.sh
```

Obre `http://localhost:8000` a l'ordinador. El primer cop et demana crear l'usuari administrador. Des del mòbil, connectat a la mateixa xarxa, obre `http://<ip-de-l'ordinador>:8000` i, al menú del navegador, tria «Afegeix a la pantalla d'inici».

Perquè el client pugui obrir el seu enllaç des de fora i perquè el micròfon funcioni al mòbil, l'app ha d'estar publicada en un servidor amb **HTTPS** (per exemple un servidor privat virtual amb un proxy com Caddy, o un túnel). Sense HTTPS els navegadors no deixen fer servir el micròfon.

### IA (opcional)

Les funcions de lectura de tiquets, pressupost dictat i revisió amb IA fan servir l'API de Claude d'Anthropic. Cal posar `ANTHROPIC_API_KEY` al fitxer `.env`. Sense clau, l'app funciona igual i aquestes dades s'omplen a mà. La revisió amb l'historial no necessita IA.

### Usuaris

L'administrador pot crear usuaris «treballador» a Configuració, amb el seu cost i preu per hora. Els treballadors poden apuntar hores, fer fotos de tiquets i consultar les feines; els impostos i la configuració només els veu l'administrador.

## Protecció de dades (RGPD)

- Totes les dades (clients, feines, documents, base de dades) es guarden **només** a la carpeta `data/` del servidor on s'executa l'app. Aquesta carpeta està exclosa del repositori (`.gitignore`) i no s'ha de pujar mai.
- A la IA **no s'envien mai** el nom, NIF, adreça, telèfon ni correu dels clients. S'hi envien: la foto del document del proveïdor, el text que dictes, el catàleg d'articles, xifres agregades de l'historial i el codi, nom i tipus de les feines obertes. Amb l'assistent per veu també s'envia el que dius: si hi anomenes el client, aquest nom arriba a la IA (la feina es busca després al servidor). Per això és millor referir-te a la feina per l'adreça o el codi, i no posar el nom del client al **nom de la feina** (fes servir, per exemple, «Reforma bany c/ Major»), i no dictar dades personals en l'explicació del pressupost.
- Si fas servir la IA, Anthropic actua com a encarregat del tractament: revisa'n les condicions i el contracte d'encàrrec de tractament abans de fer-la servir amb dades reals.
- L'enllaç del client és personal i difícil d'endevinar; qui el tingui pot veure aquella feina. No el publiquis.
- Fes còpies de seguretat periòdiques de la carpeta `data/` en un lloc segur.

## Limitacions

- Les factures segueixen el contingut obligatori bàsic (numeració correlativa, dades de les parts, base, tipus i quota d'IVA, retenció). **L'app no està certificada com a sistema VERI\*FACTU** (RD 1007/2023 i la seva normativa de desenvolupament), que serà obligatori per al programari de facturació en els terminis que fixi Hisenda. Abans de fer-la servir com a programari de facturació oficial cal adaptar-la o fer servir un programa homologat per emetre les factures.
- El resum d'impostos és orientatiu: revisa'l abans de presentar qualsevol model.
- La lectura de tiquets per IA pot equivocar-se: les dades sempre es revisen abans de desar.
- El dictat per veu depèn del navegador (Chrome i Edge funcionen bé; si no, es pot fer servir el micròfon del teclat del mòbil).

## Desenvolupament

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

- `app/` — servidor (FastAPI + SQLite): `main.py` (API), `calc.py` (totals, pendent de facturar, impostos), `learning.py` (historial i revisions), `ai.py` (Claude API), `printing.py` (documents imprimibles).
- `static/` — interfície web sense dependències externes (mòduls JS), portal del client i service worker.
- `tests/` — prova del flux complet amb dades inventades.
