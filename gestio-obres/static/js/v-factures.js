import {
  badge, buit, compartir, confirma, dataCat, del, errorToast, esc, eur, ESTATS_FACTURA, get, modal, num, obre,
  opcions, parseNum, post, put, r2, toast,
} from "./core.js";

export async function vistaFactures(el, _p, _q, viva) {
  el.innerHTML = `
    <header class="cap"><h1>Factures</h1></header>
    <div class="filtres"><select data-estat>
      <option value="">Totes</option><option value="pendents_cobrar">Pendents de cobrar</option>
      <option value="esborrany">Esborranys</option><option value="cobrada">Cobrades</option><option value="anullada">Anul·lades</option></select></div>
    <div data-res></div>
    <section><h2>Feines amb import per facturar</h2><div data-pendent></div></section>`;
  const res = el.querySelector("[data-res]");
  const carrega = async () => {
    const fs = await get(`/api/factures?estat=${el.querySelector("[data-estat]").value}`);
    if (!viva()) return;
    const tot = fs.filter((f) => f.estat !== "anullada").reduce((s, f) => s + f.total, 0);
    res.innerHTML = fs.length ? `<p class="muted">${fs.length} factures · ${eur(tot)}</p><div class="llista">${fs.map((x) => `
      <a class="fila" href="#/factura/${x.id}"><div><b>${esc(x.codi || "Esborrany")}</b> ${badge(x.estat, ESTATS_FACTURA)} ${x.vencuda ? `<span class="badge b-alerta">vençuda</span>` : ""}
        <div class="muted">${dataCat(x.data)} · ${esc(x.client_nom || "")} · ${esc(x.feina_codi || "")} ${esc(x.feina_nom || "")}</div></div>
        <div class="r"><b>${eur(x.total)}</b><div class="muted">venç. ${dataCat(x.venciment)}</div></div></a>`).join("")}</div>` : buit("No hi ha factures.");
  };
  el.querySelector("[data-estat]").onchange = carrega;
  await carrega();
  const feines = (await get("/api/feines?estat=")).filter((f) => f.resum.pendent_facturar > 0.01);
  if (!viva()) return;
  el.querySelector("[data-pendent]").innerHTML = feines.length ? `<div class="llista">${feines.map((f) => `
    <button class="fila" data-f="${f.id}"><div><b>${esc(f.codi)}</b> ${esc(f.nom)}<div class="muted">${esc(f.client_nom || "")}</div></div>
      <div class="r"><b>${eur(f.resum.pendent_facturar)}</b><div class="muted">per facturar</div></div></button>`).join("")}</div>` : buit("Tot facturat 👍");
  el.querySelectorAll("[data-f]").forEach((b) => (b.onclick = () => modalFacturar(+b.dataset.f)));
}

// Assistent per facturar una part del pendent
export async function modalFacturar(feinaId) {
  const p = await get(`/api/feines/${feinaId}/pendent`);
  const totalPress = p.linies_pressupost.reduce((s, x) => s + x.total, 0);
  const fila = (x, i, grup) => `
    <div class="fila-fact" data-g="${grup}" data-i="${i}">
      <label class="check"><input type="checkbox" data-sel ${grup !== "lp" ? "checked" : ""}> <span>${esc(x.descripcio)}
        <small class="muted">${x.facturat ? `ja facturat ${eur(x.facturat)} de ${eur(x.total)}` : `total ${eur(x.total)}`}</small></span></label>
      <input data-imp inputmode="decimal" value="${x.pendent}" class="curt">
    </div>`;
  const m = modal("Facturar", `
    <div class="form">
      <p>Queda per facturar: <b>${eur(p.total)}</b></p>
      ${p.linies_pressupost.length ? `
        <div class="targeta"><h3>Pressupost acceptat</h3>
          <div class="xips">${[10, 25, 30, 40, 50, 100].map((v) => `<button class="xip" data-pct="${v}">${v}%</button>`).join("")}</div>
          <label>% del pressupost a facturar ara<input data-pct-in inputmode="decimal" placeholder="Ex.: 30"></label>
          <details><summary>O tria línia a línia (certificació d'obra)</summary>${p.linies_pressupost.map((x, i) => fila(x, i, "lp")).join("")}</details>
        </div>` : ""}
      ${p.despeses.length ? `<div class="targeta"><h3>Material i despeses a repercutir</h3>${p.despeses.map((x, i) => fila(x, i, "d")).join("")}</div>` : ""}
      ${p.hores.length ? `<div class="targeta"><h3>Hores facturables</h3>${p.hores.map((x, i) => fila(x, i, "h")).join("")}</div>` : ""}
      <label>Concepte<input data-concepte placeholder="Ex.: Certificació 1 – enderrocs i instal·lacions"></label>
      <p class="gran-text">A facturar: <b data-suma>0 €</b> + IVA</p>
    </div>`, {
    ample: true,
    botons: [{ text: "Cancel·la" }, {
      text: "Crea l'esborrany", classe: "primari", accio: async (el) => {
        const body = { concepte: el.querySelector("[data-concepte]").value || undefined, items: [] };
        const pctv = parseNum(el.querySelector("[data-pct-in]")?.value);
        if (pctv) body.pct = pctv;
        el.querySelectorAll(".fila-fact").forEach((f) => {
          if (!f.querySelector("[data-sel]").checked) return;
          if (f.dataset.g === "lp" && pctv) return;
          const x = { lp: p.linies_pressupost, d: p.despeses, h: p.hores }[f.dataset.g][+f.dataset.i];
          body.items.push({ origen_tipus: x.origen_tipus, origen_id: x.origen_id, import: parseNum(f.querySelector("[data-imp]").value) });
        });
        return await post(`/api/feines/${feinaId}/factures`, body);
      },
    }],
  });
  const suma = () => {
    const pctv = parseNum(m.el.querySelector("[data-pct-in]")?.value);
    let s = pctv ? p.linies_pressupost.reduce((a, x) => a + Math.min(x.total * pctv / 100, x.pendent), 0) : 0;
    m.el.querySelectorAll(".fila-fact").forEach((f) => {
      if (!f.querySelector("[data-sel]").checked || (f.dataset.g === "lp" && pctv)) return;
      s += parseNum(f.querySelector("[data-imp]").value) || 0;
    });
    m.el.querySelector("[data-suma]").textContent = eur(s);
  };
  m.el.addEventListener("input", suma);
  m.el.addEventListener("change", suma);
  m.el.querySelectorAll("[data-pct]").forEach((b) => (b.onclick = (e) => {
    e.preventDefault();
    m.el.querySelector("[data-pct-in]").value = b.dataset.pct;
    m.el.querySelectorAll("[data-pct]").forEach((x) => x.classList.toggle("actiu", x === b));
    suma();
  }));
  suma();
  const r = await m.done;
  if (r && r.id) location.hash = `#/factura/${r.id}`;
  return r;
}

export async function vistaFactura(el, [id], _q, viva) {
  const f = await get(`/api/factures/${id}`);
  if (!viva()) return;
  const esb = f.estat === "esborrany";
  el.innerHTML = `
    <header class="cap">
      <div>${f.feina_id ? `<a class="tornar" href="#/feina/${f.feina_id}/factures">‹ ${esc(f.feina_codi)} ${esc(f.feina_nom)}</a>` : `<a class="tornar" href="#/factures">‹ Factures</a>`}
        <h1>${f.rectifica_id ? "Rectificativa" : "Factura"} ${esc(f.codi || "(esborrany)")} ${badge(f.estat, ESTATS_FACTURA)}</h1>
        <div class="muted">${esc(f.client_nom || "Sense client")} ${f.client_nif ? "· " + esc(f.client_nif) : ""}</div></div>
      <div class="accions-cap"><button class="btn" data-imprimir>Imprimir / PDF</button></div>
    </header>
    <div class="targeta form">
      <div class="tres"><label>Data<input type="date" data-c="data" value="${esc(f.data)}" ${esb ? "" : "disabled"}></label>
        <label>Venciment<input type="date" data-c="venciment" value="${esc(f.venciment || "")}" ${esb ? "" : "disabled"}></label>
        <label>IVA %<input data-c="iva_pct" inputmode="decimal" value="${f.iva_pct}" ${esb ? "" : "disabled"}></label></div>
      <div class="dues"><label>Concepte<input data-c="concepte" value="${esc(f.concepte || "")}" ${esb ? "" : "disabled"}></label>
        <label>IRPF %<input data-c="irpf_pct" inputmode="decimal" value="${f.irpf_pct}" ${esb ? "" : "disabled"}></label></div>
    </div>
    <div class="targeta">
      <div data-linies></div>
      ${esb ? `<button class="btn petit" data-mes>＋ Línia</button>` : ""}
      <table class="taula-totals" data-totals></table>
    </div>
    <label class="form targeta">Notes<textarea data-c="notes" rows="2" ${esb ? "" : "disabled"}>${esc(f.notes || "")}</textarea></label>
    <div class="barra-final">
      ${esb ? `<button class="btn perill" data-esborra>Esborra</button><button class="btn" data-desa>Desa</button>
        <button class="btn primari gran" data-emet>Emetre factura</button>` : ""}
      ${f.estat === "emesa" ? `<button class="btn" data-envia>Envia al client</button><button class="btn primari gran" data-cobra>Marcar cobrada</button>` : ""}
      ${f.estat === "cobrada" ? `<button class="btn" data-descobra>Desmarcar cobrada</button>` : ""}
      ${(f.estat === "emesa" || f.estat === "cobrada") && !f.rectifica_id ? `<button class="btn perill" data-rectifica>Anul·lar (rectificativa)</button>` : ""}
    </div>
    ${esb ? `<p class="muted">En emetre-la s'hi assigna el número correlatiu i ja no es pot modificar. Se'n desa una còpia a Documents.</p>` : ""}`;

  let linies = f.linies.map((l) => ({ ...l }));
  const cont = el.querySelector("[data-linies]");
  const pinta = () => {
    cont.innerHTML = linies.map((l, i) => `
      <div class="linia-fact" data-i="${i}">
        <input data-f="descripcio" value="${esc(l.descripcio)}" ${esb ? "" : "disabled"}>
        <label class="mob">Quant.<input data-f="quantitat" inputmode="decimal" value="${l.quantitat}" ${esb ? "" : "disabled"}></label>
        <label class="mob">Preu<input data-f="preu_unitari" inputmode="decimal" value="${l.preu_unitari}" ${esb ? "" : "disabled"}></label>
        <label class="mob">Dte %<input data-f="descompte_pct" inputmode="decimal" value="${l.descompte_pct || 0}" ${esb ? "" : "disabled"}></label>
        <b class="r" data-imp>${eur(l.quantitat * l.preu_unitari * (1 - (l.descompte_pct || 0) / 100))}</b>
        ${esb ? `<button class="btn-icon" data-treu>✕</button>` : ""}
      </div>`).join("");
    totals();
  };
  const totals = () => {
    const c = Object.fromEntries([...el.querySelectorAll("[data-c]")].map((i) => [i.dataset.c, i.value]));
    const base = r2(linies.reduce((s, l) => s + l.quantitat * l.preu_unitari * (1 - (l.descompte_pct || 0) / 100), 0));
    const iva = r2(base * (parseNum(c.iva_pct) || 0) / 100), irpf = r2(base * (parseNum(c.irpf_pct) || 0) / 100);
    el.querySelector("[data-totals]").innerHTML = `<tr><td>Base</td><td class="r">${eur(base)}</td></tr><tr><td>IVA</td><td class="r">${eur(iva)}</td></tr>
      ${irpf ? `<tr><td>IRPF</td><td class="r">-${eur(irpf)}</td></tr>` : ""}<tr class="gran"><td>Total</td><td class="r">${eur(base + iva - irpf)}</td></tr>`;
    return c;
  };
  cont.addEventListener("input", (e) => {
    const r = e.target.closest("[data-i]"); if (!r) return;
    const l = linies[+r.dataset.i]; const k = e.target.dataset.f;
    l[k] = k === "descripcio" ? e.target.value : parseNum(e.target.value) || 0;
    r.querySelector("[data-imp]").textContent = eur(l.quantitat * l.preu_unitari * (1 - (l.descompte_pct || 0) / 100));
    totals();
  });
  cont.addEventListener("click", (e) => { const r = e.target.closest("[data-i]"); if (r && e.target.closest("[data-treu]")) { linies.splice(+r.dataset.i, 1); pinta(); } });
  el.querySelectorAll("[data-c]").forEach((i) => i.addEventListener("input", totals));
  pinta();

  const desa = () => put(`/api/factures/${id}`, { ...totals(), linies });
  const recarrega = () => vistaFactura(el, [id], _q, viva);
  const on = (sel, fn) => { const b = el.querySelector(sel); if (b) b.onclick = async () => { try { await fn(); } catch (e) { errorToast(e); } }; };
  on("[data-mes]", () => { linies.push({ descripcio: "", quantitat: 1, preu_unitari: 0, descompte_pct: 0 }); pinta(); });
  on("[data-desa]", async () => { await desa(); toast("Desat"); recarrega(); });
  on("[data-imprimir]", async () => { if (esb) await desa(); obre(`/imprimir/factura/${id}`); });
  on("[data-esborra]", async () => { if (await confirma("Esborrar l'esborrany?", { perill: true, ok: "Esborra" })) { await del(`/api/factures/${id}`); history.back(); } });
  on("[data-emet]", async () => {
    await desa();
    if (!(await confirma("Emetre la factura? Rebrà número i ja no es podrà modificar.", { ok: "Emet" }))) return;
    await post(`/api/factures/${id}/emetre`); toast("Factura emesa"); recarrega();
  });
  on("[data-cobra]", async () => { await post(`/api/factures/${id}/cobrar`, { cobrada: true }); toast("Cobrada ✓"); recarrega(); });
  on("[data-descobra]", async () => { await post(`/api/factures/${id}/cobrar`, { cobrada: false }); recarrega(); });
  on("[data-envia]", () => compartir({ token: f.token, telefon: f.client_telefon, email: f.client_email, assumpte: `Factura ${f.codi}`,
    text: `Us enviem la factura ${f.codi} per import de ${eur(f.total)}, amb venciment ${dataCat(f.venciment)}.` }));
  on("[data-rectifica]", async () => {
    const m = modal("Anul·lar factura", `<div class="form"><p>Es crearà una factura rectificativa per l'import negatiu i l'import tornarà a quedar pendent de facturar.</p>
      <label>Motiu<input name="motiu" required></label></div>`, {
      botons: [{ text: "Cancel·la" }, { text: "Crea rectificativa", classe: "perill", accio: (e2) => post(`/api/factures/${id}/rectificar`, { motiu: e2.querySelector("[name=motiu]").value }) }],
    });
    const r = await m.done; if (r && r.id) location.hash = `#/factura/${r.id}`;
  });
}
