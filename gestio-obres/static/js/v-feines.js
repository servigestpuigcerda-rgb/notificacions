import {
  badge, barra, buit, compartir, comprimeixImatge, confirma, dataCat, dataHora, del, esc, eur, ESTATS_FACTURA,
  ESTATS_FEINA, ESTATS_PRESSUPOST, errorToast, formData, get, modal, num, opcions, pct, post, put, state, toast, api, debounce,
} from "./core.js";
import { modalDespesa, modalHores, modalNovaFeina, modalSignatura } from "./forms.js";
import { targetaFeina } from "./v-inici.js";
import { modalFacturar } from "./v-factures.js";
import { obreAssistent } from "./assistent.js";
import { tabRender } from "./v-render.js";
import { tabAnalisi, tabPlanning } from "./v-feina-extra.js";

// ------------------------------------------------------------------ llista

export async function vistaFeines(el, _p, q, viva) {
  el.innerHTML = `
    <header class="cap"><h1>Feines</h1><button class="btn primari" data-nova>＋ Nova feina</button></header>
    <div class="filtres">
      <input type="search" placeholder="Cerca per nom, codi, client o adreça" data-q>
      <select data-estat><option value="actives">Actives</option><option value="">Totes</option>
        ${Object.entries(ESTATS_FEINA).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
    </div>
    <div data-llista class="graella"></div>`;
  const llista = el.querySelector("[data-llista]");
  const carrega = async () => {
    const fs = await get(`/api/feines?estat=${el.querySelector("[data-estat]").value}&q=${encodeURIComponent(el.querySelector("[data-q]").value)}`);
    if (!viva()) return;
    llista.innerHTML = fs.length ? fs.map(targetaFeina).join("") : buit("No hi ha feines amb aquest filtre.");
  };
  el.querySelector("[data-q]").oninput = debounce(carrega);
  el.querySelector("[data-estat]").onchange = carrega;
  const nova = async () => {
    const r = await modalNovaFeina();
    if (r) location.hash = `#/feina/${r.id}`;
  };
  el.querySelector("[data-nova]").onclick = nova;
  await carrega();
  if (q.nova) { history.replaceState(null, "", "#/feines"); nova(); }
}

// ------------------------------------------------------------------ detall

const PESTANYES = [
  ["resum", "Resum"], ["pressupostos", "Pressupostos"], ["planning", "Planning"], ["despeses", "Despeses"], ["hores", "Hores"],
  ["albarans", "Albarans"], ["factures", "Factures"], ["missatges", "Missatges"], ["render", "Maqueta 3D"],
  ["documents", "Documents"], ["analisi", "Anàlisi"], ["dades", "Dades"],
];

export async function vistaFeina(el, [id, tab = "resum"], _q, viva) {
  const f = await get(`/api/feines/${id}`);
  if (!viva()) return;
  el.innerHTML = `
    <header class="cap feina-cap">
      <div><a href="#/feines" class="tornar">‹ Feines</a>
        <h1>${esc(f.nom)}</h1>
        <div class="muted">${esc(f.codi)} · ${esc(f.client ? f.client.nom : "Sense client")} ${f.adreca ? "· " + esc(f.adreca) : ""}</div></div>
      <div class="accions-cap">
        <select data-estat class="estat-sel">${Object.entries(ESTATS_FEINA).map(([k, v]) => `<option value="${k}" ${k === f.estat ? "selected" : ""}>${v}</option>`).join("")}</select>
        <button class="btn primari" data-assistent title="Digues què vols fer">🎙️</button>
        <button class="btn" data-comparteix>Enllaç client</button>
        ${f.estat !== "tancada" ? `<button class="btn" data-tanca>Tancar feina</button>` : ""}
      </div>
    </header>
    ${f.bloquejos.length ? `<div class="bloquejos">${f.bloquejos.map((b) => `<div class="avis error">⛔ ${esc(b.text)}</div>`).join("")}</div>` : ""}
    <nav class="pestanyes">${PESTANYES.map(([k, t]) => `<a href="#/feina/${id}/${k}" class="${k === tab ? "actiu" : ""}">${t}${k === "missatges" && f.no_llegits ? ` <span class="punt">${f.no_llegits}</span>` : ""}</a>`).join("")}</nav>
    <div data-tab></div>`;
  el.querySelector("[data-estat]").onchange = async (e) => {
    try { await put(`/api/feines/${id}`, { estat: e.target.value }); toast("Estat actualitzat"); } catch (err) { errorToast(err); }
  };
  el.querySelector("[data-comparteix]").onclick = () => compartir({
    token: f.token, telefon: f.client?.telefon, email: f.client?.email, assumpte: f.nom,
    text: `Hola! Us passem l'enllaç per seguir la feina «${f.nom}».`,
  });
  el.querySelector("[data-assistent]").onclick = () => obreAssistent(f.id);
  const bt = el.querySelector("[data-tanca]");
  if (bt) bt.onclick = () => tancaFeina(f);
  const cos = el.querySelector("[data-tab]");
  const recarrega = () => vistaFeina(el, [id, tab], _q, viva);
  await (TABS[tab] || TABS.resum)(cos, f, recarrega, viva);
}

async function tancaFeina(f) {
  const r = f.resum;
  const m = modal("Tancar la feina", `
    <table class="taula mini">
      <tr><td>Contractat</td><td class="r">${eur(r.contractat)}</td></tr>
      <tr><td>Cost real</td><td class="r">${eur(r.cost_real)}</td></tr>
      <tr><td>Facturat</td><td class="r">${eur(r.facturat)}</td></tr>
      <tr><td><b>Queda per facturar</b></td><td class="r"><b>${eur(r.pendent_facturar)}</b></td></tr>
      <tr><td>Pendent de cobrar</td><td class="r">${eur(r.pendent_cobrar)}</td></tr>
      <tr><td>Hores</td><td class="r">${num(r.hores_reals)} de ${num(r.hores_previstes)}</td></tr>
    </table>
    ${r.pendent_facturar > 0.01 ? `<p class="avis">⚠ Encara queda import per facturar. Factura-ho abans de tancar o tanca igualment.</p>` : ""}
    <p class="muted">Es notificarà el tancament al client i es generarà l'anàlisi de la feina (què ha anat bé, què ha fallat i propostes per al proper pressupost).</p>`, {
    botons: [{ text: "Cancel·la" }, { text: "Tanca la feina", classe: "primari", accio: () => post(`/api/feines/${f.id}/tancar`, { forcar: true }) }],
  });
  if (await m.done) { toast("Feina tancada. Aquí tens l'anàlisi."); location.hash = `#/feina/${f.id}/analisi`; }
}

// ------------------------------------------------------------------- resum

async function tabResum(el, f, recarrega) {
  const r = f.resum;
  el.innerHTML = `
    <div class="rapides petites">
      <a class="rapida" href="#/captura?feina=${f.id}"><span>📷</span>Tiquet</a>
      <button class="rapida" data-hores><span>⏱️</span>Hores</button>
      <button class="rapida" data-facturar><span>🧾</span>Facturar</button>
      <a class="rapida" href="#/feina/${f.id}/missatges"><span>💬</span>Missatge</a>
    </div>
    <section class="kpis">
      <div class="kpi"><small>Contractat</small><b>${eur(r.contractat)}</b>${r.pendent_acceptar ? `<span class="muted">+${eur(r.pendent_acceptar)} per acceptar</span>` : ""}</div>
      <div class="kpi"><small>Cost previst</small><b>${eur(r.cost_previst)}</b><span class="muted">marge ${pct(r.marge_previst_pct)}</span></div>
      <div class="kpi ${r.pct_cost > 100 ? "dolent" : ""}"><small>Cost real</small><b>${eur(r.cost_real)}</b>${barra(r.cost_real, r.cost_previst)}</div>
      <div class="kpi ${r.hores_previstes && r.hores_reals > r.hores_previstes ? "dolent" : ""}"><small>Hores</small><b>${num(r.hores_reals)} / ${num(r.hores_previstes)} h</b>${barra(r.hores_reals, r.hores_previstes)}</div>
      <div class="kpi"><small>Facturat</small><b>${eur(r.facturat)}</b>${barra(r.facturat, r.contractat, { inversa: true })}</div>
      <div class="kpi destacat"><small>Queda per facturar</small><b>${eur(r.pendent_facturar)}</b></div>
      <div class="kpi"><small>Cobrat</small><b>${eur(r.cobrat)}</b>${r.pendent_cobrar ? `<span class="muted">${eur(r.pendent_cobrar)} pendent</span>` : ""}</div>
      <div class="kpi ${r.benefici_projectat < 0 ? "dolent" : "bo"}"><small>Benefici previst al final</small><b>${eur(r.benefici_projectat)}</b></div>
    </section>
    ${r.alertes.length ? `<section class="avisos">${r.alertes.map((a) => `<div class="avis">⚠ ${esc(a)}</div>`).join("")}</section>` : ""}
    <section><h2>Partides: previst vs real</h2>
      ${r.partides.length ? `<div class="taula-wrap"><table class="taula">
        <thead><tr><th>Partida</th><th class="r">Previst</th><th class="r">Real</th><th class="r">Desviació</th><th></th></tr></thead>
        <tbody>${r.partides.map((p) => `<tr><td>${esc(p.nom)}</td><td class="r">${eur(p.previst)}</td><td class="r">${eur(p.real)}</td>
          <td class="r ${p.desviacio > 0 ? "vermell" : "verd"}">${p.desviacio > 0 ? "+" : ""}${eur(p.desviacio)}</td>
          <td style="min-width:90px">${barra(p.real, p.previst)}</td></tr>`).join("")}</tbody></table></div>` : buit("Encara no hi ha costos ni pressupost acceptat.")}
    </section>`;
  el.querySelector("[data-hores]").onclick = async () => { if (await modalHores(null, { feina_id: f.id })) recarrega(); };
  el.querySelector("[data-facturar]").onclick = () => modalFacturar(f.id);
}

// ------------------------------------------------------------ pressupostos

async function tabPressupostos(el, f) {
  const ps = f.resum.pressupostos;
  el.innerHTML = `
    <div class="barra-accions">
      <button class="btn primari" data-nou>＋ Pressupost</button>
      <a class="btn" href="#/dictar?feina=${f.id}">🎤 Dictar pressupost</a>
      <button class="btn" data-extra>＋ Fora de pressupost</button>
    </div>
    ${ps.length ? `<div class="llista">${ps.map((p) => `
      <a class="fila" href="#/pressupost/${p.id}">
        <div><b>${esc(p.numero)}</b> ${p.tipus === "extra" ? `<span class="badge b-extra">Fora de pressupost</span>` : ""} ${badge(p.estat, ESTATS_PRESSUPOST)}
          <div class="muted">${esc(p.titol || "")} · ${dataCat(p.data)}${p.acceptat_per ? ` · acceptat per ${esc(p.acceptat_per)}` : ""}</div></div>
        <div class="r"><b>${eur(p.totals.total)}</b><div class="muted">marge ${pct(p.totals.marge_pct)} · ${num(p.totals.hores)} h</div></div>
      </a>`).join("")}</div>` : buit("Aquesta feina encara no té pressupost.")}`;
  const crea = async (tipus) => {
    const r = await post(`/api/feines/${f.id}/pressupostos`, { tipus, titol: tipus === "extra" ? "Treballs fora de pressupost" : f.nom });
    location.hash = `#/pressupost/${r.id}`;
  };
  el.querySelector("[data-nou]").onclick = () => crea("principal");
  el.querySelector("[data-extra]").onclick = () => crea("extra");
}

// ---------------------------------------------------------------- despeses

async function tabDespeses(el, f, recarrega) {
  const ds = await get(`/api/despeses?feina_id=${f.id}`);
  const total = ds.reduce((s, d) => s + d.base, 0);
  el.innerHTML = `
    <div class="barra-accions">
      <a class="btn primari" href="#/captura?feina=${f.id}">📷 Foto tiquet</a>
      <button class="btn" data-nova>＋ Despesa manual</button>
      <span class="muted">Total (base): <b>${eur(total)}</b></span>
    </div>
    ${ds.length ? `<div class="llista">${ds.map((d) => `
      <button class="fila" data-id="${d.id}">
        <div><b>${esc(d.proveidor || "Sense proveïdor")}</b> ${d.estat === "pendent_revisio" || !d.partida_id ? `<span class="badge b-alerta">revisar</span>` : ""}
          ${d.facturable ? `<span class="badge b-extra">repercutir +${num(d.marge_pct)}%</span>` : ""}
          <div class="muted">${dataCat(d.data)} · ${esc(d.partida_nom || "Sense partida")} · ${esc(d.concepte || "")} ${d.document_id ? "📎" : ""}</div></div>
        <div class="r"><b>${eur(d.base)}</b><div class="muted">${eur(d.total)} amb IVA</div></div>
      </button>`).join("")}</div>` : buit("Encara no hi ha despeses imputades.")}`;
  el.querySelector("[data-nova]").onclick = async () => { if (await modalDespesa(null, { feina_id: f.id })) recarrega(); };
  el.querySelectorAll("[data-id]").forEach((b) => (b.onclick = async () => {
    if (await modalDespesa(ds.find((d) => d.id === +b.dataset.id))) recarrega();
  }));
}

// ------------------------------------------------------------------- hores

async function tabHores(el, f, recarrega) {
  const hs = await get(`/api/hores?feina_id=${f.id}`);
  const total = hs.reduce((s, h) => s + h.hores, 0);
  const cost = hs.reduce((s, h) => s + h.hores * h.cost_hora, 0);
  el.innerHTML = `
    <div class="barra-accions"><button class="btn primari" data-nova>＋ Apuntar hores</button>
      <span class="muted">${num(total)} h · cost ${eur(cost)} · previstes ${num(f.resum.hores_previstes)} h</span></div>
    ${hs.length ? `<div class="llista">${hs.map((h) => `
      <button class="fila" data-id="${h.id}"><div><b>${dataCat(h.data)}</b> · ${esc(h.treballador || "")}
        ${h.facturable ? `<span class="badge b-extra">facturable</span>` : ""}${h.albara_id ? `<span class="badge">albarà</span>` : ""}
        <div class="muted">${esc(h.descripcio || "")}</div></div>
        <div class="r"><b>${num(h.hores)} h</b><div class="muted">${eur(h.hores * h.cost_hora)}</div></div></button>`).join("")}</div>`
      : buit("Encara no hi ha hores apuntades.")}`;
  el.querySelector("[data-nova]").onclick = async () => { if (await modalHores(null, { feina_id: f.id })) recarrega(); };
  el.querySelectorAll("[data-id]").forEach((b) => (b.onclick = async () => {
    if (await modalHores(hs.find((h) => h.id === +b.dataset.id))) recarrega();
  }));
}

// ---------------------------------------------------------------- albarans

async function tabAlbarans(el, f, recarrega) {
  const as = await get(`/api/feines/${f.id}/albarans`);
  el.innerHTML = `
    <div class="barra-accions"><button class="btn primari" data-nou>＋ Albarà de feina</button>
      <span class="muted">Recull la feina feta i el material, i fes-lo signar al client.</span></div>
    ${as.length ? `<div class="llista">${as.map((a) => `
      <div class="fila"><div><b>${esc(a.numero)}</b> · ${dataCat(a.data)} ${a.estat === "signat" ? `<span class="badge b-acceptat">Signat per ${esc(a.signat_per)}</span>` : `<span class="badge">Pendent de signar</span>`}
        <div class="muted">${esc(a.descripcio || "")} · ${a.linies.length} material(s) · ${num(a.hores.reduce((s, h) => s + h.hores, 0))} h</div></div>
        <div class="botons-fila">
          <a class="btn petit" href="/imprimir/albara/${a.id}" target="_blank">Veure</a>
          ${a.estat !== "signat" ? `<button class="btn petit" data-edita="${a.id}">Edita</button><button class="btn petit primari" data-signa="${a.id}">Signar</button>` : ""}
        </div></div>`).join("")}</div>` : buit("No hi ha albarans de feina.")}`;
  el.querySelector("[data-nou]").onclick = async () => { if (await modalAlbara(f)) recarrega(); };
  el.querySelectorAll("[data-edita]").forEach((b) => (b.onclick = async () => {
    if (await modalAlbara(f, as.find((a) => a.id === +b.dataset.edita))) recarrega();
  }));
  el.querySelectorAll("[data-signa]").forEach((b) => (b.onclick = async () => {
    const s = await modalSignatura();
    if (!s) return;
    try { await post(`/api/albarans/${b.dataset.signa}/signar`, s); toast("Albarà signat"); recarrega(); } catch (e) { errorToast(e); }
  }));
}

async function modalAlbara(f, a = null) {
  const hores = (await get(`/api/hores?feina_id=${f.id}`)).filter((h) => !h.albara_id || (a && h.albara_id === a.id));
  const linies = a ? a.linies : [];
  const filaLinia = (l = {}) => `<div class="linia-alb"><input placeholder="Material o treball" name="ld" value="${esc(l.descripcio || "")}">
    <input name="lq" inputmode="decimal" value="${l.quantitat ?? 1}" class="curt"><input name="lu" value="${esc(l.unitat || "u")}" class="curt"></div>`;
  const m = modal(a ? `Albarà ${a.numero}` : "Nou albarà de feina", `
    <div class="form">
      <label>Data<input type="date" name="data" value="${esc(a?.data || new Date().toISOString().slice(0, 10))}"></label>
      <label>Feina feta<textarea name="descripcio" rows="3">${esc(a?.descripcio || "")}</textarea></label>
      <div><b>Material</b><div data-linies>${(linies.length ? linies : [{}]).map(filaLinia).join("")}</div>
        <button class="btn petit" data-mes>＋ Línia</button></div>
      ${hores.length ? `<div><b>Hores incloses</b>${hores.map((h) => `<label class="check"><input type="checkbox" name="h_${h.id}" ${a && h.albara_id === a.id ? "checked" : ""}>
        ${dataCat(h.data)} · ${esc(h.treballador || "")} · ${num(h.hores)} h ${esc(h.descripcio || "")}</label>`).join("")}</div>` : ""}
    </div>`, {
    botons: [{ text: "Cancel·la" }, {
      text: "Desa", classe: "primari", accio: async (el) => {
        const ls = [...el.querySelectorAll(".linia-alb")].map((r) => ({
          descripcio: r.querySelector("[name=ld]").value, quantitat: r.querySelector("[name=lq]").value, unitat: r.querySelector("[name=lu]").value,
        })).filter((l) => l.descripcio.trim());
        const hores_ids = [...el.querySelectorAll("[name^=h_]")].filter((c) => c.checked).map((c) => +c.name.slice(2));
        const body = { data: el.querySelector("[name=data]").value, descripcio: el.querySelector("[name=descripcio]").value, linies: ls, hores_ids };
        if (a) await put(`/api/albarans/${a.id}`, body); else await post(`/api/feines/${f.id}/albarans`, body);
      },
    }],
  });
  m.el.querySelector("[data-mes]").onclick = (e) => { e.preventDefault(); m.el.querySelector("[data-linies]").insertAdjacentHTML("beforeend", filaLinia()); };
  return m.done;
}

// ---------------------------------------------------------------- factures

async function tabFactures(el, f) {
  const fs = await get(`/api/factures?feina_id=${f.id}`);
  const r = f.resum;
  el.innerHTML = `
    <section class="kpis petits">
      <div class="kpi"><small>Contractat</small><b>${eur(r.contractat)}</b></div>
      <div class="kpi"><small>Facturat</small><b>${eur(r.facturat)}</b></div>
      <div class="kpi destacat"><small>Queda per facturar</small><b>${eur(r.pendent_facturar)}</b></div>
      <div class="kpi"><small>Pendent de cobrar</small><b>${eur(r.pendent_cobrar)}</b></div>
    </section>
    <div class="barra-accions"><button class="btn primari" data-facturar ${r.pendent_facturar <= 0 ? "disabled" : ""}>🧾 Facturar</button></div>
    ${fs.length ? `<div class="llista">${fs.map((x) => `
      <a class="fila" href="#/factura/${x.id}"><div><b>${esc(x.codi || "Esborrany")}</b> ${badge(x.estat, ESTATS_FACTURA)} ${x.vencuda ? `<span class="badge b-alerta">vençuda</span>` : ""}
        <div class="muted">${dataCat(x.data)} · ${esc(x.concepte || "")}</div></div>
        <div class="r"><b>${eur(x.total)}</b><div class="muted">base ${eur(x.base)}</div></div></a>`).join("")}</div>` : buit("Encara no s'ha facturat res.")}`;
  el.querySelector("[data-facturar]").onclick = () => modalFacturar(f.id);
}

// --------------------------------------------------------------- missatges

const ICONES_MSG = { pressupost: "📄", acceptacio: "✅", rebuig: "❌", fora_pressupost: "⚠️", factura: "🧾", tancament: "🏁", nota: "📝",
  evolucio: "🔨", pagament: "💶", valoracio: "⭐", peticio: "🙋" };

async function tabMissatges(el, f, recarrega) {
  const ms = await get(`/api/feines/${f.id}/missatges`);
  el.innerHTML = `
    <div class="xat">${ms.length ? ms.map((m) => `
      <div class="msg ${m.autor} ${m.intern ? "intern" : ""} t-${m.tipus}">
        <div class="bombolla">${ICONES_MSG[m.tipus] ? ICONES_MSG[m.tipus] + " " : ""}${esc(m.text)}
          ${m.document_id ? `<a href="/api/documents/${m.document_id}/fitxer" target="_blank"><img class="foto-msg" src="/api/documents/${m.document_id}/fitxer" alt=""></a>` : ""}</div>
        <small>${m.autor === "client" ? "Client" : m.autor === "empresa" ? "Nosaltres" : "Sistema"}${m.intern ? " · nota interna" : ""} · ${dataHora(m.created_at)}</small>
      </div>`).join("") : buit("Encara no hi ha missatges.")}</div>
    <form class="enviar-msg">
      <textarea name="text" rows="2" placeholder="Escriu al client… (o una nota interna)"></textarea>
      <div class="fila-enviar"><label class="check"><input type="checkbox" name="intern"> Nota interna (el client no la veu)</label>
        <button class="btn" type="button" data-comparteix>Avisar per WhatsApp</button>
        <button class="btn primari">Envia</button></div>
    </form>`;
  const xat = el.querySelector(".xat");
  xat.scrollTop = xat.scrollHeight;
  const form = el.querySelector("form");
  form.onsubmit = async (e) => {
    e.preventDefault();
    const d = formData(form);
    if (!d.text.trim()) return;
    try { await post(`/api/feines/${f.id}/missatges`, d); recarrega(); } catch (err) { errorToast(err); }
  };
  el.querySelector("[data-comparteix]").onclick = () => compartir({
    token: f.token, telefon: f.client?.telefon, email: f.client?.email, assumpte: f.nom,
    text: form.querySelector("[name=text]").value || `Teniu novetats sobre la feina «${f.nom}».`,
  });
}

// --------------------------------------------------------------- documents

export function llistaDocuments(docs) {
  const icona = (d) => (d.mime || "").startsWith("image/") ? "🖼️" : d.mime === "application/pdf" ? "📕" : d.mime === "text/html" ? "📄" : "📎";
  const fitxers = docs.fitxers.map((d) => `
    <a class="doc" href="/api/documents/${d.id}/fitxer" target="_blank" rel="noopener">
      ${(d.mime || "").startsWith("image/") ? `<img loading="lazy" src="/api/documents/${d.id}/fitxer" alt="">` : `<span class="icona">${icona(d)}</span>`}
      <div><b>${esc(d.nom)}</b><small>${esc(d.tipus.replace("_", " "))} · ${dataCat(d.created_at)}${d.feina_codi ? " · " + esc(d.feina_codi) : ""}</small></div></a>`).join("");
  const gen = docs.generats.map((g) => `
    <a class="doc" href="${g.generat === "factura" ? `#/factura/${g.id}` : g.generat === "pressupost" ? `#/pressupost/${g.id}` : `/imprimir/albara/${g.id}`}" ${g.generat === "albara" ? 'target="_blank"' : ""}>
      <span class="icona">${g.generat === "factura" ? "🧾" : g.generat === "pressupost" ? "📄" : "📋"}</span>
      <div><b>${esc(g.generat[0].toUpperCase() + g.generat.slice(1))} ${esc(g.numero || "esborrany")}</b>
      <small>${esc(g.estat)} · ${dataCat(g.data)} · ${esc(g.feina_codi || "")} ${esc(g.titol || "")}</small></div></a>`).join("");
  return `${gen ? `<h3>Generats</h3><div class="docs">${gen}</div>` : ""}
    <h3>Fitxers</h3>${fitxers ? `<div class="docs">${fitxers}</div>` : buit("No hi ha fitxers.")}`;
}

async function tabDocuments(el, f, recarrega) {
  const docs = await get(`/api/documents?feina_id=${f.id}`);
  el.innerHTML = `
    <div class="barra-accions">
      <label class="btn primari">＋ Afegir fitxer o foto<input type="file" multiple hidden data-fitxer></label>
      <select data-tipus>${["foto", "albara_proveidor", "factura_proveidor", "tiquet", "altres"].map((t) => `<option value="${t}">${t.replace("_", " ")}</option>`).join("")}</select>
    </div>
    ${llistaDocuments(docs)}`;
  el.querySelector("[data-fitxer]").onchange = async (e) => {
    for (const file of e.target.files) {
      const fd = new FormData();
      fd.append("fitxer", await comprimeixImatge(file));
      fd.append("feina_id", f.id);
      fd.append("tipus", el.querySelector("[data-tipus]").value);
      try { await api("POST", "/api/documents", fd); } catch (err) { errorToast(err); }
    }
    toast("Fitxer(s) desat(s)");
    recarrega();
  };
}

// -------------------------------------------------------------------- dades

async function tabDades(el, f) {
  const clients = await get("/api/clients");
  el.innerHTML = `
    <form class="form targeta">
      <label>Nom<input name="nom" value="${esc(f.nom)}"></label>
      <div class="dues"><label>Client<select name="client_id">${opcions(clients, f.client_id, { buit: "— Sense client —" })}</select></label>
        <label>Tipus de feina<input name="tipus" value="${esc(f.tipus || "")}"></label></div>
      <label>Adreça de l'obra<input name="adreca" value="${esc(f.adreca || "")}"></label>
      <div class="tres"><label>Facturació<select name="mode_facturacio">
        <option value="pressupost" ${f.mode_facturacio === "pressupost" ? "selected" : ""}>Per pressupost</option>
        <option value="administracio" ${f.mode_facturacio === "administracio" ? "selected" : ""}>Per administració</option></select></label>
        <label>Inici<input type="date" name="data_inici" value="${esc(f.data_inici || "")}"></label>
        <label>Final<input type="date" name="data_fi" value="${esc(f.data_fi || "")}"></label></div>
      <label>Notes internes<textarea name="notes" rows="4">${esc(f.notes || "")}</textarea></label>
      <button class="btn primari">Desa</button>
    </form>
    ${f.client ? `<div class="targeta"><h3>Client</h3><p>${esc(f.client.nom)}<br>${esc(f.client.telefon || "")} ${esc(f.client.email || "")}<br>
      NIF ${esc(f.client.nif || "—")} · ${esc(f.client.adreca || "")}</p><a class="btn petit" href="#/clients">Edita clients</a></div>` : ""}`;
  el.querySelector("form").onsubmit = async (e) => {
    e.preventDefault();
    try { await put(`/api/feines/${f.id}`, formData(e.target)); toast("Desat"); } catch (err) { errorToast(err); }
  };
}

const TABS = {
  resum: tabResum, pressupostos: tabPressupostos, despeses: tabDespeses, hores: tabHores, albarans: tabAlbarans,
  factures: tabFactures, missatges: tabMissatges, documents: tabDocuments, dades: tabDades,
  planning: tabPlanning, render: tabRender, analisi: tabAnalisi,
};
