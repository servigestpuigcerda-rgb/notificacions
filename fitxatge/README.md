# Fitxatge — registre horari

App de fitxatge (entrada / pausa / represa / sortida) pensada per fer-se servir
des del mòbil o des de qualsevol ordinador, sense instal·lar res.

## Fitxers

| Fitxer | Què és |
| --- | --- |
| `app.html` | **La font de veritat.** Fragment HTML (sense `<html>`/`<head>`/`<body>`), que és el format que demana el publicador d'Artifacts de Claude. |
| `index.html` | Pàgina completa **generada** a partir d'`app.html`, per servir-la com a web estàtica (GitHub Pages). No l'editis a mà. |
| `build.py` | Regenera `index.html`. Executa `python3 fitxatge/build.py` després de tocar `app.html`. |

## Dues maneres d'entrar-hi

**1. Com a Artifact de Claude (registre compartit).**
La pàgina demana la capacitat `db`, així que tots els fitxatges es desen al
servidor i totes les persones que obren l'enllaç veuen i escriuen **el mateix
registre**, en temps real. Cal que qui hi entri estigui identificat amb un
compte que tingui accés a l'artifact.

**2. Com a web estàtica (registre per dispositiu).**
Serveix `index.html` des de GitHub Pages o de qualsevol allotjament. Aquí no hi
ha `window.claude`, així que l'app cau automàticament a `localStorage`: cada
mòbil o ordinador porta el **seu propi** registre. Serveix per a una persona o
per a un terminal únic de fitxatge; per ajuntar dades cal exportar el CSV.

L'app detecta sola en quin dels dos modes s'està executant i ho diu al peu de
pàgina.

## Model de dades

- `config/equip` → `{ treballadors: [{ id, nom, actiu }] }`
- `registres/<idTreballador>__<AAAA-MM>` → `{ treballador, mes, events: [{ t, tipus }] }`

Els esdeveniments s'agrupen per persona i mes en un sol document per no fer
créixer el nombre de documents sense límit (el magatzem té un topall de 5.000).
Les escriptures són last-writer-wins: dos fitxatges simultanis **de la mateixa
persona** des de dos dispositius diferents podrien trepitjar-se.

## Conservació legal

L'article 34.9 de l'Estatut dels Treballadors obliga a guardar el registre
diari de jornada durant 4 anys i a tenir-lo a disposició de la persona
treballadora, dels seus representants i de la Inspecció de Treball. La pestanya
*Registre* exporta un CSV mensual amb el detall de moviments i el resum diari.
