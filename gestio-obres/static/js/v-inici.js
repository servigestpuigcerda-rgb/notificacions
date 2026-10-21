import { badge, barra, buit, dataCat, esc, eur, ESTATS_FEINA, get, num, state } from "./core.js";
import { obreAssistent } from "./assistent.js";

export function targetaFeina(f) {
  const r = f.resum;
  return `
    <a class="targeta feina" href="#/feina/${f.id}">
      <div class="fila-sup"><span class="codi">${esc(f.codi)}</span>${badge(f.estat, ESTATS_FEINA)}
        ${f.n_alertes || (f.alertes && f.alertes.length) ? `<span class="badge b-alerta">⚠ ${f.n_alertes || f.alertes.length}</span>` : ""}</div>
      <h3>${esc(f.nom)}</h3>
      <div class="muted">${esc(f.client_nom || "Sense client")}</div>
      ${r.contractat ? `
      <div class="mini-kpis">
        <div><small>Contractat</small><b>${eur(r.contractat)}</b></div>
        <div><small>Cost real</small><b>${eur(r.cost_real)}</b></div>
        <div><small>Per facturar</small><b>${eur(r.pendent_facturar)}</b></div>
      </div>
      <div class="etiq-barra"><small>Cost ${num(r.pct_cost)}% del previst</small>${barra(r.cost_real, r.cost_previst)}</div>
      ${r.hores_previstes ? `<div class="etiq-barra"><small>Hores ${num(r.hores_reals)} / ${num(r.hores_previstes)}</small>${barra(r.hores_reals, r.hores_previstes)}</div>` : ""}
      <div class="etiq-barra"><small>Facturat ${num(r.pct_facturat)}%</small>${barra(r.facturat, r.contractat, { inversa: true })}</div>`
      : r.pendent_acceptar ? `<p class="muted">Pressupost enviat: ${eur(r.pendent_acceptar)} pendent d'acceptar</p>`
      : r.cost_real ? `<p class="muted">Cost acumulat ${eur(r.cost_real)} · ${num(r.hores_reals)} h</p>` : `<p class="muted">Sense pressupost acceptat</p>`}
    </a>`;
}

export async function vistaInici(el, _p, _q, viva) {
  const d = await get("/api/inici");
  if (!viva()) return;
  const t = d.totals;
  el.innerHTML = `
    <header class="cap"><h1>Hola, ${esc(state.usuari.nom.split(" ")[0])}</h1>
      <div class="muted">${dataCat(new Date().toISOString())} · avui portes ${num(d.hores_avui)} h apuntades</div></header>

    <button class="barra-assistent" data-assistent><span>🎙️</span>Digues què vols fer… <small>«afegeix 4 hores a la feina del carrer Major»</small></button>

    <div class="rapides">
      <a href="#/captura" class="rapida"><span>📷</span>Foto tiquet</a>
      <a href="#/hores" class="rapida"><span>⏱️</span>Hores</a>
      <a href="#/dictar" class="rapida"><span>🎤</span>Dictar pressupost</a>
      <a href="#/feines?nova=1" class="rapida"><span>🏗️</span>Nova feina</a>
    </div>

    <section class="kpis">
      <div class="kpi"><small>Contractat (actives)</small><b>${eur(t.contractat)}</b></div>
      <div class="kpi"><small>Cost real</small><b>${eur(t.cost_real)}</b></div>
      <div class="kpi"><small>Facturat</small><b>${eur(t.facturat)}</b></div>
      <div class="kpi destacat"><small>Queda per facturar</small><b>${eur(t.pendent_facturar)}</b></div>
      <div class="kpi"><small>Pendent de cobrar</small><b>${eur(d.pendents_cobrar.total)}</b>
        ${d.pendents_cobrar.vencut ? `<span class="vermell">${eur(d.pendents_cobrar.vencut)} vençut</span>` : ""}</div>
      <div class="kpi"><small>Pressupostos per acceptar</small><b>${eur(t.pendent_acceptar)}</b></div>
    </section>

    ${d.pagaments_notificats.length ? `<section class="avisos-inici">${d.pagaments_notificats.map((p) => `<a class="avis-fila verd-f" href="#/factura/${p.id}">💶 El client diu que ha pagat la factura ${esc(p.codi)} (${eur(p.total)}) · ${esc(p.feina_nom || "")}. Comprova l'ingrés i marca-la cobrada.</a>`).join("")}</section>` : ""}
    ${d.bloquejades.length ? `<section><h2>Feines aturades pel client</h2><div class="avisos-inici">${d.bloquejades.map((b) => `<a class="avis-fila vermell-f" href="#/feina/${b.feina_id}">⛔ <b>${esc(b.feina)}</b> — ${b.bloquejos.map((x) => esc(x.text.split(".")[0])).join(" · ")}</a>`).join("")}</div></section>` : ""}

    ${d.no_llegits.length || d.despeses_pendents || d.pressupostos_enviats.length ? `
    <section class="avisos-inici">
      ${d.no_llegits.map((m) => `<a class="avis-fila blau" href="#/feina/${m.feina_id}/missatges">💬 ${m.n} missatge(s) nou(s) del client · ${esc(m.codi)} ${esc(m.nom)}</a>`).join("")}
      ${d.despeses_pendents ? `<a class="avis-fila" href="#/captura?pendents=1">🧾 ${d.despeses_pendents} despesa(es) per revisar o imputar</a>` : ""}
      ${d.pressupostos_enviats.map((p) => `<a class="avis-fila gris" href="#/pressupost/${p.id}">⏳ ${p.tipus === "extra" ? "Fora de pressupost" : "Pressupost"} ${esc(p.numero)} pendent de resposta · ${esc(p.feina_nom)} (enviat ${dataCat(p.enviat_at)})</a>`).join("")}
    </section>` : ""}

    ${d.alertes.length ? `<section><h2>Alertes</h2><div class="llista-alertes">
      ${d.alertes.slice(0, 12).map((a) => `<a class="avis-fila" href="#/feina/${a.feina_id}">⚠ <b>${esc(a.feina)}</b> — ${esc(a.text)}</a>`).join("")}
    </div></section>` : ""}

    <section><h2>Feines actives</h2>
      ${d.feines.length ? `<div class="graella">${d.feines.map(targetaFeina).join("")}</div>`
        : buit("Encara no hi ha cap feina.", `<a class="btn primari" href="#/feines?nova=1">Crea la primera feina</a>`)}
    </section>`;
  el.querySelector("[data-assistent]").onclick = () => obreAssistent();
}
