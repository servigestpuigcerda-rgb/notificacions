import {
  api, buit, confirma, debounce, del, errorToast, esc, eur, formData, get, modal, num, opcions, pct, post, put, state, toast, comprimeixImatge,
} from "./core.js";
import { llistaDocuments } from "./v-feines.js";

// ------------------------------------------------------------------ clients

export async function vistaClients(el, _p, _q, viva) {
  el.innerHTML = `<header class="cap"><h1>Clients</h1><button class="btn primari" data-nou>＋ Client</button></header>
    <div class="filtres"><input type="search" placeholder="Cerca" data-q></div><div data-r></div>`;
  let llista = [];
  const carrega = async () => {
    llista = await get(`/api/clients?q=${encodeURIComponent(el.querySelector("[data-q]").value)}`);
    if (!viva()) return;
    el.querySelector("[data-r]").innerHTML = llista.length ? `<div class="llista">${llista.map((c) => `
      <button class="fila" data-id="${c.id}"><div><b>${esc(c.nom)}</b><div class="muted">${esc(c.telefon || "")} ${esc(c.email || "")}</div></div>
      <div class="r muted">${c.feines} feina(es)</div></button>`).join("")}</div>` : buit("Encara no hi ha clients.");
    el.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => edita(llista.find((c) => c.id === +b.dataset.id))));
  };
  const edita = async (c = {}) => {
    const botons = [{ text: "Cancel·la" }];
    if (c.id) botons.unshift({ text: "Esborra", classe: "perill", accio: async () => {
      if (!(await confirma("Esborrar el client?", { perill: true, ok: "Esborra" }))) return false;
      await del(`/api/clients/${c.id}`);
    } });
    botons.push({ text: "Desa", classe: "primari", accio: async (m) => {
      const d = formData(m);
      if (c.id) await put(`/api/clients/${c.id}`, d); else await post("/api/clients", d);
    } });
    const m = modal(c.id ? "Client" : "Nou client", `<div class="form">
      <label>Nom o raó social<input name="nom" value="${esc(c.nom || "")}"></label>
      <div class="dues"><label>NIF/CIF<input name="nif" value="${esc(c.nif || "")}"></label><label>Telèfon<input name="telefon" type="tel" value="${esc(c.telefon || "")}"></label></div>
      <label>Correu<input name="email" type="email" value="${esc(c.email || "")}"></label>
      <label>Adreça fiscal<input name="adreca" value="${esc(c.adreca || "")}"></label>
      <label>Notes<textarea name="notes" rows="2">${esc(c.notes || "")}</textarea></label></div>`, { botons });
    if (await m.done) carrega();
  };
  el.querySelector("[data-nou]").onclick = () => edita();
  el.querySelector("[data-q]").oninput = debounce(carrega);
  await carrega();
}

// ----------------------------------------------------------------- articles

export async function vistaArticles(el, _p, _q, viva) {
  const admin = state.usuari.rol === "admin";
  el.innerHTML = `<header class="cap"><h1>Articles</h1><button class="btn primari" data-nou>＋ Article</button></header>
    <div class="filtres"><input type="search" placeholder="Cerca per nom, codi o proveïdor" data-q>
      ${admin ? `<button class="btn" data-aplica>Aplicar marge / descompte</button>` : ""}</div>
    <div data-r></div>`;
  let llista = [];
  const carrega = async () => {
    llista = await get(`/api/articles?q=${encodeURIComponent(el.querySelector("[data-q]").value)}`);
    if (!viva()) return;
    const pm = Object.fromEntries(state.partides.map((p) => [p.id, p.nom]));
    el.querySelector("[data-r]").innerHTML = llista.length ? `<div class="taula-wrap"><table class="taula clicable">
      <thead><tr>${admin ? `<th><input type="checkbox" data-tots></th>` : ""}<th>Article</th><th>Partida</th><th class="r">Cost</th><th class="r">Marge</th><th class="r">Preu</th><th class="r">Dte.</th><th class="r">Net</th></tr></thead>
      <tbody>${llista.map((a) => `<tr data-id="${a.id}">${admin ? `<td><input type="checkbox" data-sel="${a.id}"></td>` : ""}
        <td><b>${esc(a.nom)}</b><div class="muted">${esc(a.codi || "")} ${esc(a.proveidor || "")} · ${esc(a.unitat)}</div></td>
        <td>${esc(pm[a.partida_id] || "")}</td><td class="r">${eur(a.cost)}</td>
        <td class="r">${a.preu !== null ? "preu fix" : pct(a.marge_pct ?? state.settings.marge_defecte ?? 20)}</td>
        <td class="r">${eur(a.preu_venda)}</td><td class="r">${a.descompte_pct ? pct(a.descompte_pct) : ""}</td><td class="r"><b>${eur(a.preu_net)}</b></td></tr>`).join("")}</tbody></table></div>`
      : buit("Encara no hi ha articles. Crea els que facis servir sovint per pressupostar més ràpid.");
    el.querySelectorAll("tr[data-id]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("input")) edita(llista.find((a) => a.id === +tr.dataset.id)); }));
    const tots = el.querySelector("[data-tots]");
    if (tots) tots.onchange = () => el.querySelectorAll("[data-sel]").forEach((c) => (c.checked = tots.checked));
  };
  const edita = async (a = {}) => {
    const botons = [{ text: "Cancel·la" }];
    if (a.id) botons.unshift({ text: "Esborra", classe: "perill", accio: async () => { await del(`/api/articles/${a.id}`); } });
    botons.push({ text: "Desa", classe: "primari", accio: async (m) => {
      const d = formData(m);
      if (!d.nom) throw new Error("Cal el nom.");
      if (a.id) await put(`/api/articles/${a.id}`, d); else await post("/api/articles", d);
    } });
    const m = modal(a.id ? "Article" : "Nou article", `<div class="form">
      <div class="dues"><label>Nom<input name="nom" value="${esc(a.nom || "")}"></label><label>Codi<input name="codi" value="${esc(a.codi || "")}"></label></div>
      <div class="dues"><label>Partida<select name="partida_id">${opcions(state.partides, a.partida_id, { buit: "—" })}</select></label>
        <label>Unitat<input name="unitat" value="${esc(a.unitat || "u")}" list="unitats"></label></div>
      <datalist id="unitats">${["u", "h", "m", "m2", "m3", "ml", "kg", "l", "pa", "sac"].map((u) => `<option value="${u}">`).join("")}</datalist>
      <div class="tres"><label>Cost €<input name="cost" inputmode="decimal" value="${a.cost ?? ""}"></label>
        <label>Marge %<input name="marge_pct" inputmode="decimal" value="${a.marge_pct ?? ""}" placeholder="per defecte ${esc(state.settings.marge_defecte ?? 20)}"></label>
        <label>o preu fix €<input name="preu" inputmode="decimal" value="${a.preu ?? ""}"></label></div>
      <div class="dues"><label>Descompte %<input name="descompte_pct" inputmode="decimal" value="${a.descompte_pct ?? 0}"></label>
        <label>Proveïdor<input name="proveidor" value="${esc(a.proveidor || "")}"></label></div>
      <p class="muted" data-calc></p></div>`, { botons });
    const calc = () => {
      const d = formData(m.el), cost = +String(d.cost).replace(",", ".") || 0;
      const marge = d.marge_pct !== "" ? +String(d.marge_pct).replace(",", ".") : +(state.settings.marge_defecte ?? 20);
      const preu = d.preu !== "" ? +String(d.preu).replace(",", ".") : cost * (1 + marge / 100);
      const net = preu * (1 - (+d.descompte_pct || 0) / 100);
      m.el.querySelector("[data-calc]").textContent = `Preu de venda ${eur(preu)} · net ${eur(net)} · benefici ${eur(net - cost)} (${cost && net ? Math.round((net - cost) / net * 100) : 0}%)`;
    };
    m.el.addEventListener("input", calc); calc();
    if (await m.done) carrega();
  };
  el.querySelector("[data-nou]").onclick = () => edita();
  el.querySelector("[data-q]").oninput = debounce(carrega);
  const ap = el.querySelector("[data-aplica]");
  if (ap) ap.onclick = async () => {
    const ids = [...el.querySelectorAll("[data-sel]:checked")].map((c) => +c.dataset.sel);
    const m = modal("Aplicar a diversos articles", `<div class="form">
      <p>${ids.length ? `${ids.length} article(s) seleccionat(s)` : "Cap article seleccionat: tria una partida."}</p>
      <label>O tots els de la partida<select name="partida_id">${opcions(state.partides, "", { buit: "—" })}</select></label>
      <div class="dues"><label>Nou marge %<input name="marge_pct" inputmode="decimal"></label><label>Nou descompte %<input name="descompte_pct" inputmode="decimal"></label></div></div>`, {
      botons: [{ text: "Cancel·la" }, { text: "Aplica", classe: "primari", accio: async (e2) => {
        const r = await post("/api/articles/aplicar", { ids, ...formData(e2) }); toast(`${r.actualitzats} article(s) actualitzat(s)`);
      } }],
    });
    if (await m.done) carrega();
  };
  await carrega();
}

// ---------------------------------------------------------------- documents

export async function vistaDocuments(el, _p, _q, viva) {
  const feines = await get("/api/feines?estat=");
  el.innerHTML = `<header class="cap"><h1>Documents</h1>
      <label class="btn primari">＋ Afegir<input type="file" multiple hidden data-fitxer></label></header>
    <div class="filtres">
      <input type="search" placeholder="Cerca (proveïdor, concepte, número…)" data-q>
      <select data-feina>${opcions(feines, "", { buit: "Totes les feines", text: (f) => `${f.codi} · ${f.nom}` })}</select>
      <select data-tipus><option value="">Tots els tipus</option>${["pressupost", "factura", "albara", "tiquet", "factura_proveidor", "albara_proveidor", "foto", "altres"].map((t) => `<option value="${t}">${t.replace("_", " ")}</option>`).join("")}</select>
    </div><div data-r></div>`;
  const carrega = async () => {
    const qs = new URLSearchParams({ q: el.querySelector("[data-q]").value, tipus: el.querySelector("[data-tipus]").value });
    const fv = el.querySelector("[data-feina]").value; if (fv) qs.set("feina_id", fv);
    const docs = await get(`/api/documents?${qs}`);
    if (!viva()) return;
    el.querySelector("[data-r]").innerHTML = llistaDocuments(docs);
  };
  el.querySelector("[data-q]").oninput = debounce(carrega);
  el.querySelector("[data-feina]").onchange = carrega;
  el.querySelector("[data-tipus]").onchange = carrega;
  el.querySelector("[data-fitxer]").onchange = async (e) => {
    for (const file of e.target.files) {
      const fd = new FormData();
      fd.append("fitxer", await comprimeixImatge(file));
      const fv = el.querySelector("[data-feina]").value; if (fv) fd.append("feina_id", fv);
      fd.append("tipus", "altres");
      try { await api("POST", "/api/documents", fd); } catch (err) { errorToast(err); }
    }
    toast("Desat"); carrega();
  };
  await carrega();
}

// ----------------------------------------------------------------- impostos

export async function vistaImpostos(el, _p, _q, viva) {
  const any = new Date().getFullYear();
  const tri = Math.floor(new Date().getMonth() / 3) + 1;
  el.innerHTML = `<header class="cap"><h1>Impostos</h1></header>
    <div class="filtres"><select data-any>${[any, any - 1, any - 2].map((a) => `<option>${a}</option>`).join("")}</select>
      <select data-tri><option value="">Tot l'any</option>${[1, 2, 3, 4].map((t) => `<option value="${t}" ${t === tri ? "selected" : ""}>${t}T</option>`).join("")}</select></div>
    <div data-r></div>`;
  const carrega = async () => {
    const r = await get(`/api/impostos?any=${el.querySelector("[data-any]").value}&trimestre=${el.querySelector("[data-tri]").value}`);
    if (!viva()) return;
    const taula = (rows, irpf) => rows.length ? `<table class="taula"><thead><tr><th>IVA</th><th class="r">Docs</th><th class="r">Base</th><th class="r">Quota</th>${irpf ? `<th class="r">IRPF</th>` : ""}</tr></thead>
      <tbody>${rows.map((x) => `<tr><td>${num(x.iva_pct)}%</td><td class="r">${x.n}</td><td class="r">${eur(x.base)}</td><td class="r">${eur(x.iva)}</td>${irpf ? `<td class="r">${eur(x.irpf)}</td>` : ""}</tr>`).join("")}</tbody></table>` : `<p class="muted">Cap.</p>`;
    el.querySelector("[data-r]").innerHTML = `
      <section class="kpis">
        <div class="kpi"><small>IVA repercutit</small><b>${eur(r.iva_repercutit)}</b></div>
        <div class="kpi"><small>IVA suportat</small><b>${eur(r.iva_suportat)}</b></div>
        <div class="kpi destacat"><small>Resultat IVA (303)</small><b>${eur(r.resultat_iva)}</b><span class="muted">${r.resultat_iva >= 0 ? "a ingressar" : "a compensar"}</span></div>
        <div class="kpi"><small>Retencions que us han fet</small><b>${eur(r.retencions_irpf)}</b></div>
        <div class="kpi"><small>Ingressos (base)</small><b>${eur(r.ingressos)}</b></div>
        <div class="kpi"><small>Despeses (base)</small><b>${eur(r.despeses)}</b></div>
        <div class="kpi"><small>Rendiment aproximat</small><b>${eur(r.rendiment)}</b><span class="muted">sense nòmines ni amortitzacions</span></div>
      </section>
      ${r.avis_tiquets ? `<div class="avis">⚠ ${esc(r.avis_tiquets)}</div>` : ""}
      <div class="dues-col"><div class="targeta"><h3>Factures emeses</h3>${taula(r.repercutit, true)}</div>
        <div class="targeta"><h3>Despeses</h3>${taula(r.suportat)}</div></div>
      <p class="muted">Resum orientatiu per preparar les declaracions. Revisa'l amb la gestoria abans de presentar res.</p>`;
  };
  el.querySelector("[data-any]").onchange = carrega;
  el.querySelector("[data-tri]").onchange = carrega;
  await carrega();
}

// ------------------------------------------------------------- aprenentatge

export async function vistaAprenentatge(el, _p, _q, viva) {
  const r = await get("/api/aprenentatge");
  if (!viva()) return;
  const g = r.general;
  const ratio = (x) => x === null || x === undefined ? "—" : `${x > 1 ? "+" : ""}${Math.round((x - 1) * 100)}%`;
  el.innerHTML = `<header class="cap"><h1>Què he après</h1></header>
    <p class="muted">Tot surt de les feines acabades o tancades. Com més feines tanquis amb les hores i despeses ben imputades, més afinats seran els avisos i els pressupostos.</p>
    <section class="kpis">
      <div class="kpi"><small>Feines analitzades</small><b>${g.feines}</b></div>
      <div class="kpi ${g.ratio_hores > 1.05 ? "dolent" : ""}"><small>Desviació d'hores</small><b>${ratio(g.ratio_hores)}</b><span class="muted">real vs pressupostat</span></div>
      <div class="kpi ${g.ratio_material > 1.05 ? "dolent" : ""}"><small>Desviació de material</small><b>${ratio(g.ratio_material)}</b></div>
      <div class="kpi"><small>Marge real mitjà</small><b>${g.marge_real_mitja !== null ? pct(g.marge_real_mitja) : "—"}</b></div>
    </section>
    <section class="targeta"><h2>Per tipus de feina</h2>${r.per_tipus.length ? `<div class="taula-wrap"><table class="taula">
      <thead><tr><th>Tipus</th><th class="r">Feines</th><th class="r">Hores</th><th class="r">Material</th><th class="r">Marge real</th></tr></thead>
      <tbody>${r.per_tipus.map((t) => `<tr><td>${esc(t.tipus)}</td><td class="r">${t.feines}</td><td class="r ${t.ratio_hores > 1.05 ? "vermell" : ""}">${ratio(t.ratio_hores)}</td>
        <td class="r ${t.ratio_material > 1.05 ? "vermell" : ""}">${ratio(t.ratio_material)}</td><td class="r">${t.marge_real_mitja !== null ? pct(t.marge_real_mitja) : "—"}</td></tr>`).join("")}</tbody></table></div>`
      : buit("Encara no hi ha feines acabades amb tipus assignat.")}</section>
    <section class="targeta"><h2>Proveïdors → partida</h2><p class="muted">Quan llegeixo un tiquet d'aquests proveïdors, l'imputo automàticament a la partida.</p>
      ${r.proveidors.length ? `<div class="llista">${r.proveidors.map((p) => `<div class="fila"><div><b>${esc(p.proveidor)}</b></div><div class="r">${esc(p.partida || "")} <span class="muted">(${p.usos})</span></div></div>`).join("")}</div>` : buit("Encara res.")}
    </section>`;
}

// ------------------------------------------------------------ configuració

export async function vistaConfig(el, _p, _q, viva) {
  const c = await get("/api/config");
  if (!viva()) return;
  const s = c.settings;
  const admin = state.usuari.rol === "admin";
  const camp = (k, t, attrs = "") => `<label>${t}<input name="${k}" value="${esc(s[k] || "")}" ${attrs} ${admin ? "" : "disabled"}></label>`;
  el.innerHTML = `<header class="cap"><h1>Configuració</h1></header>
    <form class="targeta form" data-empresa><h2>Empresa</h2>
      ${camp("empresa_nom", "Nom o raó social")}
      <div class="dues">${camp("empresa_nif", "NIF")}${camp("empresa_telefon", "Telèfon")}</div>
      ${camp("empresa_adreca", "Adreça")}
      <div class="dues">${camp("empresa_email", "Correu")}${camp("empresa_iban", "IBAN (per a les factures)")}</div>
      <h2>Valors per defecte</h2>
      <div class="tres">${camp("iva_defecte", "IVA %", 'inputmode="decimal"')}${camp("irpf_defecte", "IRPF %", 'inputmode="decimal"')}${camp("marge_defecte", "Marge material %", 'inputmode="decimal"')}</div>
      <div class="tres">${camp("cost_hora_defecte", "Cost hora €", 'inputmode="decimal"')}${camp("preu_hora_defecte", "Preu venda hora €", 'inputmode="decimal"')}${camp("serie_factura", "Sèrie factures")}</div>
      <div class="dues">${camp("validesa_pressupost", "Validesa pressupost (dies)")}${camp("venciment_dies", "Venciment factures (dies)")}</div>
      <label>Condicions dels pressupostos<textarea name="condicions_pressupost" rows="3" ${admin ? "" : "disabled"}>${esc(s.condicions_pressupost || "")}</textarea></label>
      <h2>Intel·ligència artificial</h2>
      <p class="${c.ia ? "verd" : "muted"}">${c.ia ? "✓ Activa" : "No activa: cal definir ANTHROPIC_API_KEY al servidor."}</p>
      <label class="check"><input type="checkbox" name="ia_activa" ${s.ia_activa === "1" ? "checked" : ""} ${admin ? "" : "disabled"}> Fer servir la IA (lectura de tiquets, pressupostos dictats, revisions)</label>
      <p class="muted">A la IA només s'hi envien les fotos dels documents de proveïdors, el text dictat, el catàleg d'articles i xifres agregades. Mai el nom, NIF, adreça ni contacte dels clients.</p>
      ${admin ? `<button class="btn primari">Desa</button>` : ""}
    </form>
    ${admin ? `<section class="targeta"><h2>Partides</h2><div class="llista">${c.partides.map((p) => `<div class="fila"><div>${esc(p.nom)}</div><div class="muted">${esc(p.tipus)}</div></div>`).join("")}</div>
      <button class="btn" data-partida>＋ Partida</button></section>
    <section class="targeta"><h2>Usuaris</h2><div class="llista">${c.usuaris.map((u) => `<button class="fila" data-u="${u.id}"><div><b>${esc(u.nom)}</b> <span class="muted">${esc(u.usuari)} · ${esc(u.rol)}${u.actiu ? "" : " · inactiu"}</span></div>
      <div class="r muted">${eur(u.cost_hora)}/h cost · ${eur(u.preu_hora)}/h venda</div></button>`).join("")}</div>
      <button class="btn" data-nou-u>＋ Usuari</button></section>` : ""}`;
  const fe = el.querySelector("[data-empresa]");
  fe.onsubmit = async (e) => {
    e.preventDefault();
    const d = formData(fe); d.ia_activa = d.ia_activa ? "1" : "0";
    try { const r = await put("/api/config", d); state.settings = r.settings; toast("Configuració desada"); } catch (err) { errorToast(err); }
  };
  if (!admin) return;
  el.querySelector("[data-partida]").onclick = async () => {
    const m = modal("Nova partida", `<div class="form"><label>Nom<input name="nom"></label><label>Tipus<select name="tipus">
      <option value="material">Material</option><option value="ma_obra">Mà d'obra</option><option value="subcontracta">Subcontracta</option><option value="altres">Altres</option></select></label></div>`, {
      botons: [{ text: "Cancel·la" }, { text: "Crea", classe: "primari", accio: (e2) => post("/api/partides", { ...formData(e2), ordre: 50 }) }],
    });
    if (await m.done) { state.partides = await get("/api/partides"); vistaConfig(el, _p, _q, viva); }
  };
  const usuari = async (u = null) => {
    const m = modal(u ? u.nom : "Nou usuari", `<div class="form">
      <label>Nom<input name="nom" value="${esc(u?.nom || "")}"></label>
      ${u ? "" : `<label>Usuari<input name="usuari" autocapitalize="none"></label>`}
      <label>${u ? "Nova contrasenya (deixa-ho buit per no canviar-la)" : "Contrasenya"}<input name="password" type="password" minlength="8"></label>
      <label>Rol<select name="rol"><option value="treballador" ${u?.rol === "treballador" ? "selected" : ""}>Treballador (hores, tiquets, feines)</option><option value="admin" ${u?.rol === "admin" ? "selected" : ""}>Administrador</option></select></label>
      <div class="dues"><label>Cost/hora €<input name="cost_hora" inputmode="decimal" value="${u?.cost_hora ?? s.cost_hora_defecte}"></label>
        <label>Preu venda/hora €<input name="preu_hora" inputmode="decimal" value="${u?.preu_hora ?? s.preu_hora_defecte}"></label></div>
      ${u ? `<label class="check"><input type="checkbox" name="actiu" ${u.actiu ? "checked" : ""}> Actiu</label>` : ""}</div>`, {
      botons: [{ text: "Cancel·la" }, { text: "Desa", classe: "primari", accio: (e2) => u ? put(`/api/usuaris/${u.id}`, formData(e2)) : post("/api/usuaris", formData(e2)) }],
    });
    if (await m.done) vistaConfig(el, _p, _q, viva);
  };
  el.querySelector("[data-nou-u]").onclick = () => usuari();
  el.querySelectorAll("[data-u]").forEach((b) => (b.onclick = () => usuari(c.usuaris.find((u) => u.id === +b.dataset.u))));
}

// --------------------------------------------------------------- menú "Més"

export async function vistaMes(el) {
  const items = [["captura", "📷", "Foto de tiquet"], ["hores", "⏱️", "Apuntar hores"], ["dictar", "🎤", "Dictar pressupost"],
    ["documents", "📁", "Documents"], ["clients", "👥", "Clients"], ["articles", "📦", "Articles"],
    ...(state.usuari.rol === "admin" ? [["impostos", "🏛️", "Impostos"]] : []), ["aprenentatge", "📈", "Què he après"], ["config", "⚙️", "Configuració"]];
  el.innerHTML = `<header class="cap"><h1>Més</h1></header><div class="menu-mes">${items.map(([r, i, t]) => `<a href="#/${r}"><span>${i}</span>${t}</a>`).join("")}
    <a href="#" data-logout><span>🚪</span>Surt</a></div>`;
  el.querySelector("[data-logout]").onclick = async (e) => { e.preventDefault(); await post("/api/logout"); location.hash = "#/login"; location.reload(); };
}
