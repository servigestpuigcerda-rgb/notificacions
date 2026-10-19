// Formularis compartits entre vistes.
import { esc, formData, get, modal, opcions, parseNum, post, put, r2, state, today, toast, del, confirma } from "./core.js";

export async function feinesObertes() {
  return (await get("/api/feines?estat=actives")).map((f) => ({ ...f, etiqueta: `${f.codi} · ${f.nom}` }));
}

export function camps(f, etiqueta, html, cls = "") {
  return `<label class="${cls}">${esc(etiqueta)}${html}</label>`;
}

// ---------------------------------------------------------------- feina nova

export async function modalNovaFeina(valors = {}) {
  const clients = await get("/api/clients");
  const m = modal("Nova feina", `
    <div class="form">
      <label>Nom de la feina<input name="nom" required placeholder="Ex.: Reforma bany planta 1" value="${esc(valors.nom || "")}"></label>
      <label>Tipus de feina <small class="muted">(serveix per aprendre de l'historial)</small>
        <input name="tipus" list="tipus-feina" placeholder="bany, cuina, electricitat…" value="${esc(valors.tipus || "")}"></label>
      <datalist id="tipus-feina">${["bany", "cuina", "pintura", "electricitat", "fontaneria", "reforma integral", "teulada", "façana", "manteniment", "reparació"].map((t) => `<option value="${t}">`).join("")}</datalist>
      <label>Client<select name="client_id">${opcions(clients, valors.client_id, { buit: "— Client nou o sense client —" })}</select></label>
      <fieldset class="client-nou"><legend>Client nou</legend>
        <label>Nom<input name="c_nom"></label>
        <div class="dues"><label>Telèfon<input name="c_telefon" type="tel"></label><label>Correu<input name="c_email" type="email"></label></div>
        <div class="dues"><label>NIF<input name="c_nif"></label><label>Adreça fiscal<input name="c_adreca"></label></div>
      </fieldset>
      <label>Adreça de l'obra<input name="adreca"></label>
      <label>Facturació<select name="mode_facturacio">
        <option value="pressupost">Per pressupost (preu tancat)</option>
        <option value="administracio">Per administració (hores + material amb marge)</option></select></label>
    </div>`, {
    botons: [{ text: "Cancel·la" }, {
      text: "Crea la feina", classe: "primari", accio: async (el) => {
        const d = formData(el);
        if (!d.nom) throw new Error("Cal un nom per a la feina.");
        const body = { nom: d.nom, tipus: d.tipus, adreca: d.adreca, mode_facturacio: d.mode_facturacio, client_id: d.client_id || null };
        if (!d.client_id && d.c_nom) body.client_nou = { nom: d.c_nom, telefon: d.c_telefon, email: d.c_email, nif: d.c_nif, adreca: d.c_adreca };
        return await post("/api/feines", body);
      },
    }],
  });
  const sel = m.el.querySelector("[name=client_id]");
  const fs = m.el.querySelector(".client-nou");
  const upd = () => (fs.style.display = sel.value ? "none" : "");
  sel.onchange = upd;
  upd();
  return m.done;
}

// ------------------------------------------------------------------ despesa

export function formDespesa(d = {}, feines = [], { avisos = [], linies = [] } = {}) {
  const pm = state.partides;
  return `
    <div class="form despesa-form">
      ${avisos.length ? `<div class="avisos">${avisos.map((a) => `<div class="avis">⚠ ${esc(a)}</div>`).join("")}</div>` : ""}
      ${d.ia_confianca !== undefined && d.ia_confianca !== null ? `<div class="muted">Lectura automàtica · confiança ${Math.round(d.ia_confianca * 100)}%. Revisa-ho abans de desar.</div>` : ""}
      <label class="destacat">Feina<select name="feina_id">${opcions(feines, d.feina_id, { buit: "— Sense imputar (general) —", text: "etiqueta" })}</select></label>
      <label class="destacat">Partida<select name="partida_id">${opcions(pm, d.partida_id, { buit: "— Tria partida —" })}</select></label>
      <div class="dues">
        <label>Proveïdor<input name="proveidor" value="${esc(d.proveidor || "")}" list="llista-proveidors"></label>
        <label>NIF proveïdor<input name="proveidor_nif" value="${esc(d.proveidor_nif || "")}"></label>
      </div>
      <div class="tres">
        <label>Tipus<select name="tipus_doc">${opcions([{ id: "tiquet", nom: "Tiquet" }, { id: "factura", nom: "Factura" }, { id: "albara", nom: "Albarà" }], d.tipus_doc || "tiquet")}</select></label>
        <label>Núm.<input name="num_document" value="${esc(d.num_document || "")}"></label>
        <label>Data<input name="data" type="date" value="${esc(d.data || today())}"></label>
      </div>
      <label>Concepte<input name="concepte" value="${esc(d.concepte || "")}"></label>
      <div class="tres imports">
        <label>Base €<input name="base" inputmode="decimal" value="${d.base ?? ""}"></label>
        <label>IVA %<input name="iva_pct" inputmode="decimal" value="${d.iva_pct ?? state.settings.iva_defecte ?? 21}"></label>
        <label>Total €<input name="total" inputmode="decimal" value="${d.total ?? ""}"></label>
      </div>
      <div class="dues">
        <label class="check"><input type="checkbox" name="facturable" ${d.facturable ? "checked" : ""}> Repercutir al client</label>
        <label>Benefici %<input name="marge_pct" inputmode="decimal" value="${d.marge_pct ?? state.settings.marge_defecte ?? 20}"></label>
      </div>
      <label>Notes<input name="notes" value="${esc(d.notes || "")}"></label>
      ${linies.length ? `<details><summary>${linies.length} línia(es) llegides</summary><table class="taula mini">
        ${linies.map((l) => `<tr><td>${esc(l.descripcio)}</td><td class="r">${l.quantitat ?? ""}</td><td class="r">${l.import_linia ?? ""}</td></tr>`).join("")}</table></details>` : ""}
    </div>`;
}

export function lligaImports(el) {
  const base = el.querySelector("[name=base]"), iva = el.querySelector("[name=iva_pct]"), total = el.querySelector("[name=total]");
  base.addEventListener("input", () => { const b = parseNum(base.value), i = parseNum(iva.value) ?? 0; if (b !== null) total.value = r2(b * (1 + i / 100)); });
  total.addEventListener("input", () => { const t = parseNum(total.value), i = parseNum(iva.value) ?? 0; if (t !== null) base.value = r2(t / (1 + i / 100)); });
  iva.addEventListener("input", () => { const b = parseNum(base.value), i = parseNum(iva.value) ?? 0; if (b !== null) total.value = r2(b * (1 + i / 100)); });
}

export function valorsDespesa(el) {
  const d = formData(el);
  return { ...d, feina_id: d.feina_id || null, partida_id: d.partida_id || null };
}

export async function modalDespesa(despesa = null, { feina_id = null } = {}) {
  const feines = await feinesObertes();
  if (despesa && despesa.feina_id && !feines.find((f) => f.id === despesa.feina_id))
    feines.unshift({ id: despesa.feina_id, etiqueta: `${despesa.feina_codi} · ${despesa.feina_nom}` });
  const d = despesa || { feina_id };
  const botons = [{ text: "Cancel·la" }];
  if (despesa) botons.unshift({
    text: "Esborra", classe: "perill", accio: async () => {
      if (!(await confirma("Esborrar aquesta despesa?", { perill: true, ok: "Esborra" }))) return false;
      await del(`/api/despeses/${despesa.id}`);
    },
  });
  botons.push({
    text: "Desa", classe: "primari", accio: async (el) => {
      const v = valorsDespesa(el);
      if (despesa) await put(`/api/despeses/${despesa.id}`, v);
      else await post("/api/despeses", v);
      toast("Despesa desada");
    },
  });
  const m = modal(despesa ? "Despesa" : "Nova despesa", formDespesa(d, feines) +
    (despesa && despesa.document_id ? `<p><a href="/api/documents/${despesa.document_id}/fitxer" target="_blank">📎 Veure el document</a></p>` : ""), { botons });
  lligaImports(m.el);
  return m.done;
}

// -------------------------------------------------------------------- hores

export async function modalHores(h = null, { feina_id = null } = {}) {
  const feines = await feinesObertes();
  const d = h || { feina_id, data: today(), hores: 1 };
  const admin = state.usuari.rol === "admin";
  const botons = [{ text: "Cancel·la" }];
  if (h) botons.unshift({
    text: "Esborra", classe: "perill", accio: async () => {
      if (!(await confirma("Esborrar aquest registre d'hores?", { perill: true, ok: "Esborra" }))) return false;
      await del(`/api/hores/${h.id}`);
    },
  });
  botons.push({
    text: "Desa", classe: "primari", accio: async (el) => {
      const v = formData(el);
      if (!v.feina_id) throw new Error("Tria la feina.");
      if (!admin) { delete v.cost_hora; delete v.preu_hora; }
      if (h) await put(`/api/hores/${h.id}`, v); else await post("/api/hores", v);
      toast("Hores desades");
    },
  });
  const m = modal(h ? "Hores" : "Apuntar hores", `
    <div class="form">
      <label>Feina<select name="feina_id">${opcions(feines, d.feina_id, { buit: "— Tria —", text: "etiqueta" })}</select></label>
      <div class="dues"><label>Data<input type="date" name="data" value="${esc(d.data)}"></label>
        <label>Hores<input name="hores" inputmode="decimal" value="${d.hores}"></label></div>
      ${admin ? `<label>Treballador<select name="usuari_id">${opcions(state.usuaris || [], d.usuari_id || state.usuari.id)}</select></label>
      <div class="dues"><label>Cost/h<input name="cost_hora" inputmode="decimal" value="${d.cost_hora ?? ""}" placeholder="segons treballador"></label>
        <label>Preu venda/h<input name="preu_hora" inputmode="decimal" value="${d.preu_hora ?? ""}" placeholder="segons treballador"></label></div>` : ""}
      <label>Què s'ha fet<input name="descripcio" value="${esc(d.descripcio || "")}"></label>
      <label class="check"><input type="checkbox" name="facturable" ${d.facturable ? "checked" : ""}> Facturar a part (fora de pressupost / administració)</label>
    </div>`, { botons });
  return m.done;
}

// ------------------------------------------------------------------ signatura

export function modalSignatura(titol = "Signatura del client") {
  const m = modal(titol, `
    <div class="form"><label>Nom de qui signa<input name="nom" required></label>
    <div class="signatura"><canvas width="600" height="220"></canvas><button class="btn petit" data-neteja>Esborra</button></div>
    <p class="muted">Signa amb el dit o el ratolí.</p></div>`, {
    botons: [{ text: "Cancel·la" }, {
      text: "Signa", classe: "primari", accio: async (el) => {
        const nom = el.querySelector("[name=nom]").value.trim();
        if (!nom) throw new Error("Cal el nom.");
        if (!dibuixat) throw new Error("Falta la signatura.");
        return { nom, signatura: cv.toDataURL("image/png") };
      },
    }],
  });
  const cv = m.el.querySelector("canvas");
  const ctx = cv.getContext("2d");
  ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.strokeStyle = "#1d2433";
  let dibuixant = false, dibuixat = false;
  const pos = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * cv.width / r.width, (e.clientY - r.top) * cv.height / r.height]; };
  cv.addEventListener("pointerdown", (e) => { dibuixant = true; cv.setPointerCapture(e.pointerId); ctx.beginPath(); ctx.moveTo(...pos(e)); });
  cv.addEventListener("pointermove", (e) => { if (!dibuixant) return; ctx.lineTo(...pos(e)); ctx.stroke(); dibuixat = true; });
  cv.addEventListener("pointerup", () => (dibuixant = false));
  m.el.querySelector("[data-neteja]").onclick = () => { ctx.clearRect(0, 0, cv.width, cv.height); dibuixat = false; };
  return m.done;
}
