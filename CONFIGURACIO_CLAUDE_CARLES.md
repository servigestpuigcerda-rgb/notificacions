# Configurar Claude (mòbil) perquè el Carles tingui les mateixes eines

## 0. Concepte clau
Les connexions (Servigest, Microsoft 365, GitHub...) **van lligades al compte de Claude de cada persona**, no al dispositiu.
- Si el Carles entra amb **el seu** compte → **no** tindrà res connectat fins que ho faci ell (passos de sota).
- **No** compartir el compte de Claude de la gestoria: tot el que faci quedaria en nom d'una altra persona (correus, WhatsApp, Teams) → problema de traçabilitat i RGPD.
- El connector Servigest actua **amb l'usuari que hi ha iniciat sessió**: el Carles veurà el seu correu/calendari de Microsoft 365, no el de l'altra persona.

## 1. Compte de Claude
1. Ideal: afegir el Carles al **mateix pla Team/Enterprise** de la gestoria (claude.ai → Settings → Organization → Members → Invite). Així l'admin pot publicar els connectors per a tothom i les dades no s'usen per entrenar.
2. Alternativa: compte Pro/Max propi (els connectors personalitzats els haurà d'afegir ell).
3. Instal·lar l'app **Claude** (iOS/Android) i iniciar sessió amb el seu compte.

## 2. Connector Servigest (correu Outlook, SharePoint, Teams, calendari, tasques, apps internes i WhatsApp)
1. Des del compte que ja el té: claude.ai → **Settings → Connectors** → Servigest → copiar la **URL del servidor**.
2. Si és pla Team/Enterprise: l'admin l'afegeix a **Organization settings → Connectors** (custom connector) i queda disponible per a tots els membres.
3. El Carles: Settings → Connectors → **Servigest → Connect** → inicia sessió amb **el seu** usuari de Microsoft 365 de la gestoria.
4. Al servidor Servigest (PC del Xavi) cal que l'usuari del Carles tingui permisos a les apps internes (A3, morositat, laboral, sedes, AEAT...). Si alguna eina li respon "sense permís", s'ha d'habilitar allà.

## 3. Microsoft 365 (connector oficial, opcional)
Ja cobert per Servigest. Si també el vol: Settings → Connectors → **Microsoft 365 → Connect** → compte M365 del Carles.
Si demana "aprovació d'administrador", l'admin del tenant M365 ha de donar consentiment a l'app de Claude (Entra ID → Enterprise applications).

## 4. WhatsApp
- No hi ha connector oficial de WhatsApp: funciona **a través de Servigest**, amb les línies del despatx (`principal`, `seu`, `puigcerda`, `yaiza`) que corren al **PC del Xavi** (ha d'estar engegat).
- Un cop el Carles té Servigest connectat, pot llegir/enviar per aquestes línies (si el servidor li dona permís).
- Si vol **la seva pròpia línia**: s'ha d'afegir com a 5è telèfon a l'app "WhatsApp del despatx" de Servigest i vincular-la escanejant el QR des del seu mòbil (WhatsApp → Dispositius vinculats).

## 5. Correu personal (si no és Outlook)
Gmail: Settings → Connectors → **Gmail / Google Calendar / Drive → Connect** amb el seu compte Google.

## 6. Claude Code des del mòbil (repositoris i scripts)
1. App Claude → pestanya **Code** (o claude.ai/code).
2. Connectar GitHub: claude.ai/connect-github amb el **seu** usuari de GitHub.
3. Donar-li accés al repo: GitHub → `servigestpuigcerda-rgb/notificacions` → Settings → Collaborators → afegir el Carles.
4. Els connectors del punt 2–5 estan disponibles també dins les sessions de Claude Code.

## 7. Comprovació final (que ho escrigui el Carles a Claude)
- "Quins correus nous tinc avui?" → Servigest/Outlook ✔
- "Estat dels WhatsApp del despatx" → Servigest WhatsApp ✔
- "Les meves tasques pendents" → Servigest tasques ✔

## 8. RGPD
- Cada persona amb el seu compte i les seves credencials; mai compartir contrasenyes.
- Preferible pla Team/Enterprise (sense entrenament amb dades, gestió centralitzada).
- Registrar el Carles com a usuari autoritzat al registre d'activitats de tractament.
