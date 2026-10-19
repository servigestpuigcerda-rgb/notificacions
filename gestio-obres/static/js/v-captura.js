import {
  api, buit, comprimeixImatge, dataCat, dictat, errorToast, esc, eur, get, modal, num, opcions, parseNum, post, r2,
  state, today, toast,
} from "./core.js";
import { feinesObertes, formDespesa, lligaImports, modalDespesa, modalNovaFeina, valorsDespesa } from "./forms.js";

// ------------------------------------------------------------ foto de tiquet

export async function vistaCaptura(el, _p, q, viva) {
  const feines = await feinesObertes();
  if (!viva()) return;
  const feinaDef = q.feina ? +q.feina : null;
  el.innerHTML = `
    <header class="cap"><h1>Foto de tiquet o factura</h1></header>
    <div class="captura">
      <label class="boto-foto">
        <span>📷</span><b>Fes una foto</b><small>o tria una imatge / PDF</small>
        <input type="file" accept="image/*,application/pdf" capture="environment" hidden data-foto>
      </label>
      <label class="btn">Triar de la galeria<input type="file" accept="image/*,application/pdf" hidden data-galeria></label>
      ${state.ia ? `<p class="muted">Llegiré les dades i proposaré la feina i la partida. Tu només revises i confirmes.</p>`
        : `<p class="avis">La lectura automàtica no està activada: es desarà la foto i hauràs d'omplir les dades.</p>`}
    </div>
    <div data-form></div>
    <section><h2>Despeses per revisar</h2><div data-pendents></div></section>`;

  const zona = el.querySelector("[data-form]");
  const processa = async (file) => {
    if (!file) return;
    zona.innerHTML = `<div class="targeta llegint"><div class="spinner"></div><p>${state.ia ? "Llegint el document…" : "Pujant el document…"}</p></div>`;
    try {
      const fd = new FormData();
      fd.append("fitxer", await comprimeixImatge(file));
      if (feinaDef) fd.append("feina_id", feinaDef);
      const r = await api("POST", "/api/ia/document", fd);
      const d = r.dades || {};
      if (feinaDef && !d.feina_id) d.feina_id = feinaDef;
      if (d.feina_id === undefined) d.feina_id = feinaDef;
      zona.innerHTML = `
        <div class="targeta">
          <div class="preview-doc"><img src="/api/documents/${r.document_id}/fitxer" alt="" onerror="this.remove()"></div>
          ${r.error ? `<p class="avis">${esc(r.error)}</p>` : ""}
          ${formDespesa(d, feines, { avisos: d.avisos || [], linies: d.linies || [] })}
          <div class="barra-final"><button class="btn" data-descarta>Descarta</button><button class="btn primari gran" data-desa>Desa la despesa</button></div>
        </div>`;
      lligaImports(zona);
      zona.querySelector("[data-desa]").onclick = async () => {
        const v = valorsDespesa(zona);
        v.document_id = r.document_id;
        if (d.ia_confianca !== undefined) v.ia_confianca = d.ia_confianca;
        if (!v.total && !v.base) return errorToast(new Error("Falta l'import."));
        try {
          await post("/api/despeses", v);
          toast("Despesa desada ✓");
          zona.innerHTML = `<div class="targeta"><p class="verd"><b>Desada.</b> ${esc(v.proveidor || "")} · ${eur(parseNum(v.total) || 0)}</p></div>`;
          carregaPendents();
        } catch (e) { errorToast(e); }
      };
      zona.querySelector("[data-descarta]").onclick = () => (zona.innerHTML = "");
      zona.scrollIntoView({ behavior: "smooth" });
    } catch (e) {
      zona.innerHTML = "";
      errorToast(e);
    }
  };
  el.querySelector("[data-foto]").onchange = (e) => processa(e.target.files[0]);
  el.querySelector("[data-galeria]").onchange = (e) => processa(e.target.files[0]);

  const pend = el.querySelector("[data-pendents]");
  const carregaPendents = async () => {
    const ds = await get("/api/despeses?estat=pendents");
    pend.innerHTML = ds.length ? `<div class="llista">${ds.map((d) => `
      <button class="fila" data-id="${d.id}"><div><b>${esc(d.proveidor || "Sense proveïdor")}</b>
        <div class="muted">${dataCat(d.data)} · ${esc(d.feina_codi || "sense feina")} · ${esc(d.partida_nom || "sense partida")}</div></div>
        <div class="r"><b>${eur(d.total)}</b></div></button>`).join("")}</div>` : buit("Tot revisat 👍");
    pend.querySelectorAll("[data-id]").forEach((b) => (b.onclick = async () => {
      if (await modalDespesa(ds.find((d) => d.id === +b.dataset.id))) carregaPendents();
    }));
  };
  carregaPendents();
}

// ------------------------------------------------------------- hores ràpides

export async function vistaHores(el, _p, _q, viva) {
  const feines = (await feinesObertes()).filter((f) => f.estat !== "acabada");
  if (!viva()) return;
  const desde = new Date(Date.now() - 6 * 864e5).toISOString().slice(0, 10);
  let feinaSel = +(localStorage.getItem("darrera_feina") || 0);
  if (!feines.find((f) => f.id === feinaSel)) feinaSel = feines[0]?.id || 0;
  let hores = 8;
  el.innerHTML = `
    <header class="cap"><h1>Apuntar hores</h1></header>
    ${feines.length ? `
    <div class="targeta hores-rapides">
      <h3>Feina</h3><div class="xips" data-feines>${feines.slice(0, 8).map((f) => `<button class="xip ${f.id === feinaSel ? "actiu" : ""}" data-f="${f.id}">${esc(f.codi)}<br><small>${esc(f.nom)}</small></button>`).join("")}</div>
      ${feines.length > 8 ? `<select data-totes>${opcions(feines, feinaSel, { text: "etiqueta" })}</select>` : ""}
      <h3>Hores</h3>
      <div class="comptador"><button class="btn gran" data-menys>−</button><output data-h>${hores}</output><button class="btn gran" data-mes>＋</button></div>
      <div class="xips">${[1, 2, 4, 6, 8, 10].map((h) => `<button class="xip" data-hh="${h}">${h} h</button>`).join("")}</div>
      <div class="dues form"><label>Data<input type="date" data-data value="${today()}"></label>
        ${state.usuari.rol === "admin" ? `<label>Treballador<select data-usuari>${opcions(state.usuaris || [], state.usuari.id)}</select></label>` : ""}</div>
      <div class="form"><label>Què s'ha fet (opcional)<input data-desc placeholder="Ex.: enrajolat paret dutxa"></label>
        <label class="check"><input type="checkbox" data-fact> Facturar a part (fora de pressupost)</label></div>
      <button class="btn primari gran ample" data-desa>Desa les hores</button>
    </div>` : buit("No hi ha feines obertes.", `<a class="btn primari" href="#/feines?nova=1">Crea una feina</a>`)}
    <section><h2>Darrers 7 dies</h2><div data-recents></div></section>`;

  const recents = el.querySelector("[data-recents]");
  const carrega = async () => {
    const hs = await get(`/api/hores?desde=${desde}`);
    const tot = hs.reduce((s, h) => s + h.hores, 0);
    recents.innerHTML = hs.length ? `<p class="muted">Total: <b>${num(tot)} h</b></p><div class="llista">${hs.map((h) => `
      <div class="fila"><div><b>${dataCat(h.data)}</b> · ${esc(h.feina_codi)} ${esc(h.feina_nom)}<div class="muted">${esc(h.treballador || "")} ${esc(h.descripcio || "")}</div></div>
      <div class="r"><b>${num(h.hores)} h</b></div></div>`).join("")}</div>` : buit("Cap hora aquesta setmana.");
  };
  carrega();
  if (!feines.length) return;
  const out = el.querySelector("[data-h]");
  const setH = (h) => { hores = Math.max(0.5, r2(h)); out.textContent = num(hores); };
  el.querySelector("[data-menys]").onclick = () => setH(hores - 0.5);
  el.querySelector("[data-mes]").onclick = () => setH(hores + 0.5);
  el.querySelectorAll("[data-hh]").forEach((b) => (b.onclick = () => setH(+b.dataset.hh)));
  const marcaFeina = (id) => {
    feinaSel = id;
    el.querySelectorAll("[data-f]").forEach((b) => b.classList.toggle("actiu", +b.dataset.f === id));
    const s = el.querySelector("[data-totes]"); if (s) s.value = id;
  };
  el.querySelectorAll("[data-f]").forEach((b) => (b.onclick = () => marcaFeina(+b.dataset.f)));
  const totes = el.querySelector("[data-totes]");
  if (totes) totes.onchange = () => marcaFeina(+totes.value);
  el.querySelector("[data-desa]").onclick = async () => {
    try {
      const u = el.querySelector("[data-usuari]");
      await post("/api/hores", { feina_id: feinaSel, hores, data: el.querySelector("[data-data]").value,
        descripcio: el.querySelector("[data-desc]").value, facturable: el.querySelector("[data-fact]").checked,
        ...(u ? { usuari_id: u.value } : {}) });
      localStorage.setItem("darrera_feina", feinaSel);
      toast(`${num(hores)} h desades ✓`);
      el.querySelector("[data-desc]").value = "";
      carrega();
    } catch (e) { errorToast(e); }
  };
}

// ----------------------------------------------------------- dictar pressupost

export async function vistaDictar(el, _p, q, viva) {
  const feines = await feinesObertes();
  if (!viva()) return;
  el.innerHTML = `
    <header class="cap"><h1>Dictar pressupost</h1></header>
    <div class="targeta form">
      <div class="dues">
        <label>Feina<select data-feina>${opcions(feines, q.feina || "", { buit: "— Feina nova —", text: "etiqueta" })}</select></label>
        <label>Tipus de feina<input data-tipus list="tipus-dictat" placeholder="bany, cuina…"><datalist id="tipus-dictat">${["bany", "cuina", "pintura", "electricitat", "fontaneria", "reforma integral", "teulada", "façana"].map((t) => `<option value="${t}">`).join("")}</datalist></label>
      </div>
      <label>Explica la feina: què cal fer, mides, materials, qualitats, accessos, terminis…
        <textarea data-text rows="8" placeholder="Ex.: Reforma d'un bany de 2 per 2,5. Treure banyera i posar plat de dutxa de 140 amb mampara. Enrajolar parets fins al sostre, rajola mitjana gamma que posa el client. Canviar el lavabo i el vàter. Instal·lació nova d'aigua..."></textarea></label>
      <div class="barra-accions">
        <button class="btn gran microfon" data-mic>🎤 Dicta</button>
        <span class="muted" data-estat-mic></span>
      </div>
      ${state.ia ? `<button class="btn primari gran ample" data-genera>Prepara el pressupost</button>`
        : `<p class="avis">La IA no està configurada. Pots desar el text com a pressupost buit i omplir les línies a mà.</p>
           <button class="btn primari gran ample" data-buit>Crea pressupost amb aquest text</button>`}
    </div>
    <div data-resultat></div>`;

  const ta = el.querySelector("[data-text]");
  const estat = el.querySelector("[data-estat-mic]");
  const bmic = el.querySelector("[data-mic]");
  const rec = dictat((final, parcial) => { ta.value = final + parcial; }, (actiu) => {
    bmic.classList.toggle("actiu", actiu);
    bmic.textContent = actiu ? "⏹ Atura" : "🎤 Dicta";
    estat.textContent = actiu ? "Escoltant… parla amb normalitat." : "";
  });
  if (!rec) {
    bmic.disabled = true;
    estat.textContent = "Aquest navegador no permet dictar aquí: fes servir el micròfon del teclat del mòbil.";
  } else bmic.onclick = () => (rec.actiu ? rec.stop() : rec.start(ta.value));

  const feinaSel = el.querySelector("[data-feina]");
  const tipusIn = el.querySelector("[data-tipus]");
  const actualitzaTipus = () => { const f = feines.find((x) => x.id === +feinaSel.value); if (f && f.tipus) tipusIn.value = f.tipus; };
  feinaSel.onchange = actualitzaTipus;
  actualitzaTipus();

  const obtenFeina = async (titol) => {
    if (feinaSel.value) return +feinaSel.value;
    const r = await modalNovaFeina({ nom: titol, tipus: tipusIn.value });
    return r ? r.id : null;
  };

  const crea = async (proposta) => {
    const fid = await obtenFeina(proposta?.titol || "");
    if (!fid) return;
    const linies = (proposta?.linies || []).map((l) => ({ ...l, marge_pct: l.cost_unitari ? r2((l.preu_unitari / l.cost_unitari - 1) * 100) : 0 }));
    const notes = proposta ? [proposta.notes_client, proposta.hipotesis?.length ? "Hipòtesis: " + proposta.hipotesis.join("; ") : ""].filter(Boolean).join("\n") : "";
    const r = await post(`/api/feines/${fid}/pressupostos`, { titol: proposta?.titol || "", text_origen: ta.value, linies, notes,
      tipus_feina: proposta?.tipus_feina || tipusIn.value });
    if (rec && rec.actiu) rec.stop();
    location.hash = `#/pressupost/${r.id}`;
  };

  const bb = el.querySelector("[data-buit]");
  if (bb) bb.onclick = () => crea(null).catch(errorToast);
  const bg = el.querySelector("[data-genera]");
  if (bg) bg.onclick = async () => {
    if (rec && rec.actiu) rec.stop();
    const res = el.querySelector("[data-resultat]");
    bg.disabled = true;
    res.innerHTML = `<div class="targeta llegint"><div class="spinner"></div><p>Preparant el pressupost amb el catàleg i l'historial… pot trigar un minut.</p></div>`;
    try {
      const p = await post("/api/ia/pressupost", { text: ta.value, tipus: tipusIn.value, feina_id: feinaSel.value || null });
      const tot = p.linies.reduce((s, l) => s + l.quantitat * l.preu_unitari, 0);
      const cost = p.linies.reduce((s, l) => s + l.quantitat * l.cost_unitari, 0);
      res.innerHTML = `
        <div class="targeta">
          <h2>${esc(p.titol)}</h2>
          ${p.avisos.length ? `<div class="avisos">${p.avisos.map((a) => `<div class="avis">⚠ ${esc(a)}</div>`).join("")}</div>` : ""}
          <div class="taula-wrap"><table class="taula">
            <thead><tr><th>Descripció</th><th>Partida</th><th class="r">Quant.</th><th class="r">Cost</th><th class="r">Preu</th><th class="r">Import</th></tr></thead>
            <tbody>${p.linies.map((l) => `<tr><td>${esc(l.descripcio)}${l.justificacio ? `<div class="muted">${esc(l.justificacio)}</div>` : ""}</td>
              <td>${esc(l.partida)}</td><td class="r">${num(l.quantitat)} ${esc(l.unitat)}</td><td class="r">${eur(l.cost_unitari)}</td>
              <td class="r">${eur(l.preu_unitari)}</td><td class="r">${eur(l.quantitat * l.preu_unitari)}</td></tr>`).join("")}</tbody>
            <tfoot><tr><td colspan="5"><b>Base</b> (cost ${eur(cost)}, marge ${tot ? Math.round((tot - cost) / tot * 100) : 0}%)</td><td class="r"><b>${eur(tot)}</b></td></tr></tfoot>
          </table></div>
          ${p.preguntes.length ? `<h3>Cal confirmar</h3><ul>${p.preguntes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
          ${p.hipotesis.length ? `<h3>Hipòtesis</h3><ul class="muted">${p.hipotesis.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
          <div class="barra-final"><button class="btn" data-refes>Torna-ho a provar</button><button class="btn primari gran" data-crea>Crea el pressupost i edita'l</button></div>
        </div>`;
      res.querySelector("[data-crea]").onclick = () => crea(p).catch(errorToast);
      res.querySelector("[data-refes]").onclick = () => bg.click();
    } catch (e) { res.innerHTML = ""; errorToast(e); } finally { bg.disabled = false; }
  };
}
