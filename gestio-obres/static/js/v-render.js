// Pestanya "Maqueta 3D" d'una feina: crear a partir de fotos i mides, veure, canviar materials i compartir.
import { api, buit, comprimeixImatge, confirma, dataCat, del, dictat, errorToast, esc, get, modal, opcions, parseNum, post, put, state, toast } from "./core.js";
import { visor3d } from "./render3d.js";

const TIPUS_ELEMENT = ["plat_dutxa", "banyera", "lavabo", "moble_lavabo", "wc", "bidet", "mampara", "mirall", "armari_baix", "armari_alt",
  "taulell", "pica", "placa", "forn", "nevera", "rentadora", "radiador", "prestatge", "taula", "cadira", "sofa", "llit", "illa", "columna", "altre"];
const PARETS = ["sud", "nord", "oest", "est"];
const MIDES = { plat_dutxa: [1.4, 0.8, 0.05], banyera: [1.7, 0.75, 0.55], lavabo: [0.6, 0.45, 0.18], moble_lavabo: [0.8, 0.46, 0.85],
  wc: [0.37, 0.65, 0.8], mampara: [1.4, 0.8, 2.0], mirall: [0.8, 0.02, 0.9], armari_baix: [0.6, 0.6, 0.9], armari_alt: [0.6, 0.35, 0.7],
  taulell: [2.0, 0.62, 0.04], nevera: [0.6, 0.65, 1.85] };
const nomTipus = (t) => t.replace(/_/g, " ");

export async function tabRender(el, f) {
  const llista = await get(`/api/feines/${f.id}/renders`);
  el.innerHTML = `
    <div class="barra-accions"><button class="btn primari" data-nou>＋ Nova maqueta 3D</button>
      <span class="muted">Fes fotos de l'estat actual, posa les mides i explica com ha de quedar.</span></div>
    ${llista.length ? `<div class="llista">${llista.map((r) => `<button class="fila" data-id="${r.id}"><div><b>${esc(r.titol)}</b>
      ${r.visible_client ? `<span class="badge b-acceptat">el client la veu</span>` : ""}<div class="muted">${dataCat(r.updated_at)}</div></div><div>›</div></button>`).join("")}</div>`
      : buit("Encara no hi ha cap maqueta.")}
    <div data-editor></div>`;
  el.querySelector("[data-nou]").onclick = async () => { const r = await modalNova(f); if (r) obre(el, f, r.id); };
  el.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => obre(el, f, +b.dataset.id)));
  if (llista.length === 1) obre(el, f, llista[0].id);
}

async function modalNova(f) {
  const m = modal("Nova maqueta 3D", `
    <div class="form">
      <label>Nom<input name="titol" value="Proposta"></label>
      <label class="btn">📷 Fotos de l'estat actual<input type="file" accept="image/*" multiple capture="environment" hidden data-fotos></label>
      <div class="xips" data-prev></div>
      <label>Mides i observacions<textarea name="mesures" rows="3" placeholder="Ex.: 2,40 x 1,80, alçada 2,50. Porta a la paret curta, finestra davant la porta a 1,10 del terra…"></textarea></label>
      <label>Com ha de quedar<textarea name="descripcio" rows="3" placeholder="Ex.: plat de dutxa de 140 a la paret del fons, moble de 80 amb lavabo, rajola gran gris clar a terra i blanca a les parets de la dutxa…"></textarea></label>
      <button class="btn" data-mic>🎤 Dicta</button>
      ${state.ia ? "" : `<p class="avis">Sense IA es crearà una estança bàsica amb les mides i hi afegiràs els elements a mà.</p>`}
    </div>`, {
    botons: [{ text: "Cancel·la" }, {
      text: state.ia ? "Crea la maqueta" : "Crea", classe: "primari", accio: async (e) => {
        const fd = new FormData();
        ["titol", "mesures", "descripcio"].forEach((k) => fd.append(k, e.querySelector(`[name=${k}]`).value));
        for (const fi of fotos) fd.append("fotos", fi);
        e.querySelector("footer .primari, .primari").textContent = "Creant… (pot trigar un minut)";
        const r = await api("POST", `/api/feines/${f.id}/renders`, fd);
        if (r.avis) toast(r.avis);
        return r;
      },
    }],
  });
  let fotos = [];
  m.el.querySelector("[data-fotos]").onchange = async (e) => {
    for (const fi of e.target.files) fotos.push(await comprimeixImatge(fi, 1600));
    m.el.querySelector("[data-prev]").innerHTML = fotos.map((x) => `<img class="mini-foto" src="${URL.createObjectURL(x)}">`).join("");
  };
  let camp = m.el.querySelector("[name=descripcio]");
  m.el.querySelectorAll("textarea").forEach((t) => t.addEventListener("focus", () => (camp = t)));
  const bm = m.el.querySelector("[data-mic]");
  const rec = dictat((fi, p) => { camp.value = fi + p; }, (a) => { bm.classList.toggle("actiu", a); bm.textContent = a ? "⏹ Atura" : "🎤 Dicta"; });
  if (rec) bm.onclick = (e) => { e.preventDefault(); rec.actiu ? rec.stop() : rec.start(camp.value); }; else bm.remove();
  return m.done;
}

async function obre(el, f, id) {
  const r = await get(`/api/renders/${id}`);
  const ed = el.querySelector("[data-editor]");
  let model = r.model;
  const imatges = (await get(`/api/documents?feina_id=${f.id}`)).fitxers.filter((d) => (d.mime || "").startsWith("image/"));
  ed.innerHTML = `
    <div class="targeta render-ed">
      <div class="barra-accions"><h2>${esc(r.titol)}</h2>
        <label class="check"><input type="checkbox" data-visible ${r.visible_client ? "checked" : ""}> Compartir amb el client</label>
        <button class="btn" data-captura>📸 Imatge</button><button class="btn perill" data-esborra>Esborra</button></div>
      <div class="visor" data-visor></div>
      <p class="muted">Arrossega per girar, pinça o roda per apropar. És una maqueta orientativa, no un render fotorealista.</p>
      ${model.suposits?.length ? `<details><summary>Suposicions a confirmar (${model.suposits.length})</summary><ul>${model.suposits.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></details>` : ""}
      ${state.ia ? `<div class="form ia-canvi"><label>Canvia-ho dient-ho<div class="enllac"><input data-instr placeholder="Ex.: posa parquet de roure a terra i el moble a la paret est">
        <button class="btn" data-mic>🎤</button><button class="btn primari" data-aplica-ia>Aplica</button></div></label></div>` : ""}
      <div class="dues-col">
        <div data-panell-acabats></div>
        <div data-panell-materials></div>
      </div>
      <div data-panell-elements></div>
      <div class="barra-final"><button class="btn primari gran" data-desa>Desa els canvis</button></div>
    </div>`;
  const visor = await visor3d(ed.querySelector("[data-visor]"), model, { fotoUrl: (d) => `/api/documents/${d}/fitxer` });
  window.addEventListener("hashchange", () => visor.destrueix(), { once: true });
  const refresca = () => { visor.actualitza(model); pintaPanells(); };

  const pintaPanells = () => {
    const mats = model.materials;
    const selMat = (k, v, buitTxt = "—") => `<select data-acabat="${k}">${opcions(mats, v, { buit: buitTxt })}</select>`;
    const ac = model.acabats;
    const e = model.estanca;
    ed.querySelector("[data-panell-acabats]").innerHTML = `
      <div class="targeta form"><h3>Estança i acabats</h3>
        <div class="tres"><label>Amplada (m)<input data-est="amplada" inputmode="decimal" value="${e.amplada}"></label>
          <label>Llargada (m)<input data-est="llargada" inputmode="decimal" value="${e.llargada}"></label>
          <label>Alçada (m)<input data-est="alcada" inputmode="decimal" value="${e.alcada}"></label></div>
        <label>Terra${selMat("terra", ac.terra)}</label>
        <label>Parets${selMat("parets", ac.parets)}</label>
        <label>Zona diferenciada (dutxa, frontal…)${selMat("zona_humida", ac.zona_humida, "— cap —")}</label>
        ${ac.zona_humida ? `<div class="xips">${PARETS.map((p) => `<label class="xip"><input type="checkbox" data-zh="${p}" ${ac.zona_humida_parets?.includes(p) ? "checked" : ""}> ${p}</label>`).join("")}</div>
          <label>Fins a l'alçada (m, buit = fins al sostre)<input data-zh-alt inputmode="decimal" value="${ac.zona_humida_alcada ?? ""}"></label>` : ""}
        <p class="muted">Paret sud = la de la porta (si no s'ha dit altra cosa). Les posicions es mesuren des de l'oest o des del sud.</p>
      </div>`;
    ed.querySelector("[data-panell-materials]").innerHTML = `
      <div class="targeta"><h3>Materials</h3>${mats.map((x, i) => `
        <div class="mat-fila" data-m="${i}">
          <input type="color" data-mf="color" value="${esc(x.color)}">
          <input data-mf="nom" value="${esc(x.nom)}">
          <select data-mf="patro">${["llis", "rajola", "llistons"].map((p) => `<option ${p === x.patro ? "selected" : ""}>${p}</option>`).join("")}</select>
          <input data-mf="mida_peca_cm" inputmode="decimal" placeholder="cm" value="${x.mida_peca_cm ?? ""}" class="curt" title="Mida de la peça (cm)">
          <select data-mf="foto_document_id" title="Foto del material">${opcions(imatges, x.foto_document_id, { buit: "sense foto", text: "nom" })}</select>
        </div>`).join("")}
        <button class="btn petit" data-nou-mat>＋ Material</button>
        <label class="btn petit">📷 Foto de material<input type="file" accept="image/*" hidden data-foto-mat></label></div>`;
    const els = model.elements;
    ed.querySelector("[data-panell-elements]").innerHTML = `
      <div class="targeta"><h3>Elements</h3>
        <div class="taula-wrap"><table class="taula elements-t"><thead><tr><th>Element</th><th>Paret</th><th>Posició</th><th>Ample</th><th>Fons</th><th>Alt</th><th>Del terra</th><th>Material</th><th></th></tr></thead>
        <tbody>${els.map((x, i) => `<tr data-e="${i}">
          <td><select data-ef="tipus">${TIPUS_ELEMENT.map((t) => `<option value="${t}" ${t === x.tipus ? "selected" : ""}>${nomTipus(t)}</option>`).join("")}</select></td>
          <td><select data-ef="paret"><option value="">mig</option>${PARETS.map((p) => `<option ${p === x.paret ? "selected" : ""}>${p}</option>`).join("")}</select></td>
          <td><input data-ef="posicio" inputmode="decimal" value="${x.posicio ?? ""}"></td>
          <td><input data-ef="amplada" inputmode="decimal" value="${x.amplada}"></td>
          <td><input data-ef="fondaria" inputmode="decimal" value="${x.fondaria}"></td>
          <td><input data-ef="alcada" inputmode="decimal" value="${x.alcada}"></td>
          <td><input data-ef="alcada_terra" inputmode="decimal" value="${x.alcada_terra ?? 0}"></td>
          <td><select data-ef="material_id">${opcions(mats, x.material_id, { buit: "per defecte" })}</select></td>
          <td><button class="btn-icon" data-treu-e>✕</button></td></tr>`).join("")}</tbody></table></div>
        <button class="btn petit" data-nou-e>＋ Element</button> <button class="btn petit" data-nova-ob>＋ Porta / finestra</button>
        ${model.obertures.length ? `<p class="muted">Obertures: ${model.obertures.map((o, i) => `${o.tipus} paret ${o.paret} a ${o.posicio} m <button class="btn-icon" data-treu-ob="${i}">✕</button>`).join(" · ")}</p>` : ""}
      </div>`;
  };

  ed.addEventListener("change", async (ev) => {
    const t = ev.target;
    if (t.dataset.acabat) { model.acabats[t.dataset.acabat] = t.value || null; refresca(); }
    else if (t.dataset.zh) {
      const s = new Set(model.acabats.zona_humida_parets || []);
      t.checked ? s.add(t.dataset.zh) : s.delete(t.dataset.zh);
      model.acabats.zona_humida_parets = [...s]; refresca();
    } else if (t.matches("[data-zh-alt]")) { model.acabats.zona_humida_alcada = parseNum(t.value); refresca(); }
    else if (t.dataset.est) { model.estanca[t.dataset.est] = parseNum(t.value) || model.estanca[t.dataset.est]; refresca(); }
    else if (t.dataset.mf) {
      const x = model.materials[+t.closest("[data-m]").dataset.m];
      const k = t.dataset.mf;
      x[k] = k === "mida_peca_cm" ? parseNum(t.value) : k === "foto_document_id" ? (t.value ? +t.value : null) : t.value;
      if (k === "mida_peca_cm") x.mida_peca_alt_cm = null;
      refresca();
    } else if (t.dataset.ef) {
      const x = model.elements[+t.closest("[data-e]").dataset.e];
      const k = t.dataset.ef;
      if (["posicio", "amplada", "fondaria", "alcada", "alcada_terra"].includes(k)) x[k] = parseNum(t.value) ?? 0;
      else x[k] = t.value || null;
      if (k === "tipus" && MIDES[t.value]) { [x.amplada, x.fondaria, x.alcada] = MIDES[t.value]; x.nom = nomTipus(t.value); }
      refresca();
    } else if (t.matches("[data-foto-mat]") && t.files[0]) {
      const fd = new FormData();
      fd.append("fitxer", await comprimeixImatge(t.files[0], 1200));
      fd.append("feina_id", f.id);
      fd.append("tipus", "material");
      const d = await api("POST", "/api/documents", fd);
      imatges.unshift({ id: d.id, nom: t.files[0].name });
      model.materials.push({ id: `m${Date.now()}`, nom: "Material nou", tipus: "ceramica", color: "#ffffff", patro: "rajola", mida_peca_cm: 30, foto_document_id: d.id });
      refresca(); toast("Foto afegida com a material nou: assigna'l a terra, parets o un element.");
    }
  });
  ed.addEventListener("click", (ev) => {
    const t = ev.target;
    if (t.closest("[data-treu-e]")) { model.elements.splice(+t.closest("[data-e]").dataset.e, 1); refresca(); }
    if (t.closest("[data-treu-ob]")) { model.obertures.splice(+t.closest("[data-treu-ob]").dataset.treuOb, 1); refresca(); }
    if (t.closest("[data-nou-e]")) {
      model.elements.push({ id: `e${Date.now()}`, tipus: "armari_baix", nom: "armari baix", paret: "nord", posicio: model.estanca.amplada / 2,
        amplada: 0.6, fondaria: 0.6, alcada: 0.9, alcada_terra: 0, material_id: null });
      refresca();
    }
    if (t.closest("[data-nova-ob]")) {
      model.obertures.push({ paret: "nord", tipus: "finestra", posicio: model.estanca.amplada / 2, amplada: 0.8, alcada: 1.0, alcada_terra: 1.1 });
      refresca();
    }
    if (t.closest("[data-nou-mat]")) {
      model.materials.push({ id: `m${Date.now()}`, nom: "Material nou", tipus: "ceramica", color: "#d9d4cc", patro: "rajola", mida_peca_cm: 30 });
      refresca();
    }
  });
  const desa = async () => { const res = await put(`/api/renders/${id}`, { model }); model = res.model; toast("Maqueta desada"); };
  ed.querySelector("[data-desa]").onclick = () => desa().catch(errorToast);
  ed.querySelector("[data-visible]").onchange = (e) => put(`/api/renders/${id}`, { visible_client: e.target.checked, model })
    .then(() => toast(e.target.checked ? "El client ja la pot veure al seu enllaç" : "Ja no és visible per al client")).catch(errorToast);
  ed.querySelector("[data-esborra]").onclick = async () => {
    if (!(await confirma("Esborrar aquesta maqueta?", { perill: true, ok: "Esborra" }))) return;
    await del(`/api/renders/${id}`); tabRender(el, f);
  };
  ed.querySelector("[data-captura]").onclick = async () => {
    const url = visor.captura();
    const blob = await (await fetch(url)).blob();
    const fd = new FormData();
    fd.append("fitxer", new File([blob], `maqueta-${r.titol}.jpg`, { type: "image/jpeg" }));
    fd.append("feina_id", f.id);
    fd.append("tipus", "foto");
    await api("POST", "/api/documents", fd);
    const a = document.createElement("a"); a.href = url; a.download = `maqueta-${r.titol}.jpg`; a.click();
    toast("Imatge desada a Documents");
  };
  const bia = ed.querySelector("[data-aplica-ia]");
  if (bia) {
    const inp = ed.querySelector("[data-instr]");
    const bm = ed.querySelector("[data-mic]");
    const rec = dictat((fi, p) => { inp.value = fi + p; }, (a) => bm.classList.toggle("actiu", a));
    if (rec) bm.onclick = () => (rec.actiu ? rec.stop() : rec.start(inp.value)); else bm.remove();
    bia.onclick = async () => {
      if (rec && rec.actiu) rec.stop();
      bia.disabled = true; bia.textContent = "Aplicant…";
      try {
        await put(`/api/renders/${id}`, { model });
        const res = await post(`/api/renders/${id}/ia`, { instruccio: inp.value });
        model = res.model; inp.value = ""; refresca(); toast("Canvi aplicat");
      } catch (e) { errorToast(e); } finally { bia.disabled = false; bia.textContent = "Aplica"; }
    };
  }
  pintaPanells();
  ed.scrollIntoView({ behavior: "smooth" });
}
