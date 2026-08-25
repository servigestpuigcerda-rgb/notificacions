---
name: reunio-zoom-comunitat
description: Programa reunions per Zoom de comunitats de propietaris administrades amb Bell-Estar Pirineus (Alícia Ester) — comprova el calendari d'Outlook, crea l'esdeveniment, prepara la invitació de Zoom amb el format del despatx i, si cal, la convocatòria formal amb ordre del dia. Fes servir aquesta skill sempre que aparegui una petició de reunió, assemblea, junta o videoconferència d'una comunitat de propietaris (CTAT/C.P./Ctat, Llívia 7, Euro, Julia Lybica, La Solana...), quan es demanin "codis de Zoom" o un enllaç de reunió per a una comunitat, o quan l'Alícia demani per WhatsApp, correu o telèfon que es convoqui o es passi l'enllaç d'una reunió — encara que el missatge sigui molt curt i només porti data, hora i nom de la comunitat.
---

# Reunió per Zoom d'una comunitat de propietaris

Aquesta skill recull el procés del despatx (Servigest Barberán, Puigcerdà) quan l'Alícia
Ester i Roca — administradora de **Bell-Estar Pirineus**, `alicia@bell-estar.es` — demana
que es programi una reunió per Zoom d'una de les comunitats que gestiona.

Les peticions arriben normalment per WhatsApp i són telegràfiques: *"Codis zoom / Dimecres
26 Agost / A les 12:00h / Ctat llivia 7"*. La feina consisteix a convertir aquestes quatre
línies en una reunió ben plantada: hora lliure a l'agenda, esdeveniment al calendari,
invitació de Zoom amb el format de sempre i, quan és una assemblea de veritat, la
convocatòria formal per als propietaris.

## Límits del sistema (important dir-ho d'entrada)

- **No hi ha connector de Zoom.** La reunió s'ha de crear a mà des del compte Zoom del
  despatx (**Desptax Cerdanya**, `us02web.zoom.us`). Tu prepares tota la resta i deixes els
  camps de l'ID i el codi d'accés marcats perquè s'hi enganxin.
- **No hi ha connector de WhatsApp.** Si la petició ve d'un WhatsApp, demana que te'l
  copiïn o te'l resumeixin; no diguis que l'has llegit.
- **Microsoft 365 sí que hi és**: calendari i correu d'Outlook, i xats de Teams. Aquí és on
  trobaràs els precedents.

## El procés

### 1. Fixa les dades mínimes

Necessites quatre coses: **comunitat**, **data**, **hora** i **tipus de reunió**. Si en
falta alguna, pregunta-ho abans de tocar el calendari — una reunió mal datada genera més
feina que no fer-la.

El punt que més sovint queda ambigu és el tipus: no és el mateix una **trucada de treball**
entre el despatx i l'administradora (només cal l'enllaç) que una **assemblea convocada**
amb propietaris (cal convocatòria, ordre del dia i terminis). Si el missatge no ho aclareix,
pregunta-ho explícitament; la resta de la feina en depèn.

Comunitats que apareixen habitualment: **CTAT LLÍVIA 7** (per blocs, p. ex. bloc 3),
**CTAT EURO** (Raval, 32), **JULIA LYBICA**, **C.P. LA SOLANA**. El nom exacte, tal com
s'escriu als documents, surt dels precedents del pas següent.

### 2. Busca el precedent

Dos cerques ràpides que estalvien molta feina i eviten inventar-se formats:

- **Convocatòries i actes anteriors** d'aquella comunitat, al correu:
  cerca a Outlook per remitent `alicia@bell-estar.es` amb el nom de la comunitat. Els
  assumptes segueixen el patró `ALICIA ESTER-BELL-ESTAR PIRINEUS. CONVOCATORIA REUNIO
  EXTRAORDINARIA CTAT LLIVIA 7 BLOC 3 ...`. D'aquí surten el nom oficial de la comunitat,
  l'ordre del dia habitual i els temes que van quedar pendents l'última vegada.
- **Invitacions de Zoom anteriors**, als xats de Teams: cerca `zoom` i mira com es va
  redactar l'última (p. ex. la de la C.P. LA SOLANA). Reutilitza aquell format exacte:
  els propietaris ja hi estan acostumats i qualsevol variació genera trucades.

### 3. Comprova l'agenda

Cerca al calendari d'Outlook el dia sencer de la reunió abans de crear res. No busques
només si l'hora exacta està lliure, sinó si hi ha res encavalcat amb la durada probable
(una assemblea de comunitat ocupa fàcilment una hora). Si hi ha solapament, **crea igualment
l'esdeveniment i avisa'n** amb el detall del que xoca — qui decideix què es mou és l'usuari,
no tu.

### 4. Crea l'esdeveniment al calendari

Amb `outlook_create_event`, zona horària **Romance Standard Time**:

- **Assumpte**: `Reunió [NOM COMUNITAT] (Zoom) — Alícia / Bell-Estar Pirineus`
- **Ubicació**: `Zoom (compte Desptax Cerdanya)`
- **Durada**: 1 hora si no es diu res
- **Cos**: qui ho ha demanat i per quin canal, i el bloc de dades de Zoom amb els camps
  pendents (`ID de reunió: ___`, `Codi d'accés: ___`) perquè es vegi d'un cop d'ull que
  encara falta generar-los.
- **Sense convidats**, tret que l'usuari ho demani explícitament. Afegir assistents envia
  invitacions reals a propietaris i administradors: això no es fa per iniciativa pròpia.

Quan després t'arribin els codis, actualitza el mateix esdeveniment amb
`outlook_update_event` en comptes de crear-ne un de nou.

### 5. Prepara la invitació de Zoom

Fes servir `assets/plantilla-zoom.txt`, que reprodueix el format del despatx en castellà
(és el que genera el mateix Zoom i el que ja han rebut altres vegades). Omple el tema, la
data i l'hora, i deixa marcats l'enllaç, l'ID i el codi d'accés.

Acompanya-ho de les instruccions per generar-la: al compte **Desptax Cerdanya** →
*Programar reunió* → tema amb el nom de la comunitat, data i hora en zona Madrid, durada,
i amb **codi d'accés i sala d'espera activats** (són reunions on es prenen acords: convé
saber qui entra).

### 6. Convocatòria formal, només si és una assemblea

Si el pas 1 ha confirmat que és una assemblea de propietaris, prepara la convocatòria a
partir de `assets/plantilla-convocatoria.md`, que porta l'ordre del dia, la primera i
segona convocatòria, el model de delegació de vot i el recordatori sobre els propietaris
amb deutes pendents.

Deixa-la **com a esborrany per revisar**, no la enviïs. Les formalitats legals (terminis
d'antelació, contingut de l'ordre del dia, validesa de la reunió telemàtica segons el
llibre cinquè del Codi civil de Catalunya) les valida l'administradora, que és qui convoca.
La teva feina és que no hi falti res, no decidir per ella.

## Què entregues

Un missatge curt amb, en aquest ordre:

1. **L'esdeveniment creat**, amb data, hora i enllaç a Outlook.
2. **Els conflictes d'agenda**, si n'hi ha, dits clarament i amb una proposta concreta.
3. **El text de la invitació de Zoom** llest per copiar, amb els camps a omplir marcats.
4. **Què queda pendent de l'usuari**: generar la reunió a Zoom i passar-te els codis.

Escriu en català, que és la llengua del despatx, encara que la invitació de Zoom vagi en
castellà perquè així la genera l'eina. Sigues breu: aquestes peticions es resolen entre
dues coses que cremen més.

## Coses que no fas sense demanar-ho

- Enviar correus o invitacions a propietaris.
- Afegir assistents a l'esdeveniment.
- Moure o esborrar altres cites del calendari per fer lloc.
- Donar per bona una data que no t'han confirmat.
