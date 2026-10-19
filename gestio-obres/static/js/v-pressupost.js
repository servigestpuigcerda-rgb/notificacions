import {
  badge, compartir, confirma, del, errorToast, esc, eur, ESTATS_PRESSUPOST, get, modal, num, obre, opcions, parseNum,
  pct, post, put, r2, state, toast, debounce,
} from "./core.js";

function calculaLinia(l) {
  l.import = r2((+l.quantitat || 0) * (+l.preu_unitari || 0) * (1 - (+l.descompte_pct || 0) / 100));
  l.cost = r2((+l.quantitat || 0) * (+l.cost_unitari || 0));
  return l;
}

function totals(p, linies) {
  const tipusPartida = Object.fromEntries(state.partides.map((x) => [x.id, x.tipus]));
  let sub = 0, cost = 0, hores = 0;
  for (const l of linies) {
    calculaLinia(l);
    sub += l.import; cost += l.cost;
    if (tipusPartida[l.partida_id] === "ma_obra" && /^(h|hora|hores|hr|hrs)\.?$/i.test((l.unitat || "").trim())) hores += +l.quantitat || 0;
  }
  const desc = r2(sub * (+p.descompte_pct || 0) / 100), base = r2(sub - desc);
  const iva = r2(base * (+p.iva_pct || 0) / 100), irpf = r2(base * (+p.irpf_pct || 0) / 100);
  return { sub: r2(sub), desc, base, iva, irpf, total: r2(base + iva - irpf), cost: r2(cost), benefici: r2(base - cost),
    marge: base ? ((base - cost) / base) * 100 : 0, hores };
}

export async function vistaPressupost(el, [id], _q, viva) {
  const p = await get(`/api/pressupostos/${id}`);
  if (!viva()) return;
  const bloquejat = p.estat === "acceptat";
  let linies = p.totals.linies.map((l) => ({ ...l }));
  let brut = false;
  const margeDef = parseNum(state.settings.marge_defecte) ?? 20;
  const pmo = state.partides.find((x) => x.tipus === "ma_obra");
  const pmat = state.partides.find((x) => x.tipus === "material");

  el.innerHTML = `
    <header class="cap">
      <div><a class="tornar" href="#/feina/${p.feina.id}/pressupostos">‹ ${esc(p.feina.codi)} ${esc(p.feina.nom)}</a>
        <h1>${p.tipus === "extra" ? "Fora de pressupost" : "Pressupost"} ${esc(p.numero)} ${badge(p.estat, ESTATS_PRESSUPOST)}</h1>
        ${p.acceptat_per ? `<div class="verd">Acceptat per ${esc(p.acceptat_per)} el ${esc((p.acceptat_at || "").slice(0, 10))}</div>` : ""}
        ${p.rebutjat_motiu ? `<div class="vermell">Rebutjat: ${esc(p.rebutjat_motiu)}</div>` : ""}</div>
      <div class="accions-cap">
        <button class="btn" data-imprimir>Imprimir / PDF</button>
        <button class="btn" data-duplicar>Duplicar</button>
        ${!bloquejat ? `<button class="btn primari" data-desar>Desa</button>` : ""}
      </div>
    </header>
    ${bloquejat ? `<div class="avis info">Aquest pressupost està acceptat i no es pot modificar. Per a treballs nous, crea un «fora de pressupost» des de la feina.</div>` : ""}
    <div class="form targeta">
      <label>Títol<input data-cap="titol" value="${esc(p.titol || "")}" ${bloquejat ? "disabled" : ""}></label>
      ${p.text_origen ? `<details><summary>Explicació original</summary><p class="muted pre">${esc(p.text_origen)}</p></details>` : ""}
    </div>
    <section class="editor-linies">
      <div class="cap-linies"><span>Descripció</span><span>Partida</span><span class="r">Quant.</span><span>Unit.</span>
        <span class="r">Cost</span><span class="r">Marge %</span><span class="r">Preu</span><span class="r">Dte %</span><span class="r">Import</span><span></span></div>
      <div data-linies></div>
      ${!bloquejat ? `<div class="barra-accions">
        <button class="btn" data-article>＋ Article</button>
        <button class="btn" data-ma>＋ Mà d'obra</button>
        <button class="btn" data-lliure>＋ Línia lliure</button>
        <button class="btn" data-marge-tot>Aplicar marge a tot</button>
      </div>` : ""}
    </section>
    <div class="dues-col">
      <div class="targeta form">
        <div class="tres">
          <label>Dte. global %<input data-cap="descompte_pct" inputmode="decimal" value="${p.descompte_pct}" ${bloquejat ? "disabled" : ""}></label>
          <label>IVA %<input data-cap="iva_pct" inputmode="decimal" value="${p.iva_pct}" ${bloquejat ? "disabled" : ""}></label>
          <label>IRPF %<input data-cap="irpf_pct" inputmode="decimal" value="${p.irpf_pct}" ${bloquejat ? "disabled" : ""}></label>
        </div>
        <div class="dues"><label>Data<input type="date" data-cap="data" value="${esc(p.data)}" ${bloquejat ? "disabled" : ""}></label>
          <label>Validesa (dies)<input data-cap="validesa_dies" inputmode="numeric" value="${p.validesa_dies}" ${bloquejat ? "disabled" : ""}></label></div>
        <label>Notes per al client<textarea data-cap="notes" rows="3" ${bloquejat ? "disabled" : ""}>${esc(p.notes || "")}</textarea></label>
        <label>Condicions<textarea data-cap="condicions" rows="3" ${bloquejat ? "disabled" : ""}>${esc(p.condicions || "")}</textarea></label>
      </div>
      <div class="targeta totals" data-totals></div>
    </div>
    <section class="targeta" data-revisio-box>
      <div class="barra-accions"><h2>Revisió</h2>
        <button class="btn" data-revisa>Revisa amb l'historial</button>
        ${state.ia ? `<button class="btn" data-revisa-ia>Revisa amb IA</button>` : ""}</div>
      <div data-revisio class="muted">Comprova errors i si anem curts d'hores o de material segons les feines anteriors.</div>
    </section>
    ${!bloquejat ? `<div class="barra-final">
      ${p.estat !== "esborrany" ? "" : `<button class="btn perill" data-esborra>Esborra</button>`}
      <button class="btn" data-acceptat>Marcar acceptat</button>
      ${p.estat === "enviat" ? `<button class="btn" data-rebutjat>Rebutjat</button>` : ""}
      <button class="btn primari gran" data-envia>${p.estat === "enviat" ? "Tornar a enviar" : "Envia al client"}</button>
    </div>` : ""}`;

  const cont = el.querySelector("[data-linies]");
  const cap = () => Object.fromEntries([...el.querySelectorAll("[data-cap]")].map((i) => [i.dataset.cap, i.value]));

  const pintaTotals = () => {
    const t = totals(cap(), linies);
    el.querySelector("[data-totals]").innerHTML = `
      <table class="taula-totals">
        <tr><td>Subtotal</td><td class="r">${eur(t.sub)}</td></tr>
        ${t.desc ? `<tr><td>Descompte</td><td class="r">-${eur(t.desc)}</td></tr>` : ""}
        <tr><td>Base</td><td class="r">${eur(t.base)}</td></tr>
        <tr><td>IVA</td><td class="r">${eur(t.iva)}</td></tr>
        ${t.irpf ? `<tr><td>IRPF</td><td class="r">-${eur(t.irpf)}</td></tr>` : ""}
        <tr class="gran"><td>Total</td><td class="r">${eur(t.total)}</td></tr>
      </table>
      <div class="intern">
        <div><small>Cost</small><b>${eur(t.cost)}</b></div>
        <div><small>Benefici</small><b class="${t.benefici < 0 ? "vermell" : "verd"}">${eur(t.benefici)}</b></div>
        <div><small>Marge</small><b>${pct(t.marge)}</b></div>
        <div><small>Hores</small><b>${num(t.hores)} h</b></div>
      </div>`;
    linies.forEach((l, i) => { const c = cont.querySelector(`[data-i="${i}"] [data-import]`); if (c) c.textContent = eur(l.import); });
  };

  const filaHtml = (l, i) => `
    <div class="linia" data-i="${i}">
      <textarea data-f="descripcio" rows="1" placeholder="Descripció" ${bloquejat ? "disabled" : ""}>${esc(l.descripcio)}</textarea>
      <select data-f="partida_id" ${bloquejat ? "disabled" : ""}>${opcions(state.partides, l.partida_id, { buit: "—" })}</select>
      <label class="mob">Quant.<input data-f="quantitat" inputmode="decimal" value="${l.quantitat}" ${bloquejat ? "disabled" : ""}></label>
      <label class="mob">Unitat<input data-f="unitat" value="${esc(l.unitat)}" ${bloquejat ? "disabled" : ""}></label>
      <label class="mob">Cost<input data-f="cost_unitari" inputmode="decimal" value="${l.cost_unitari}" ${bloquejat ? "disabled" : ""}></label>
      <label class="mob">Marge %<input data-f="marge_pct" inputmode="decimal" value="${r2(l.marge_pct)}" ${bloquejat ? "disabled" : ""}></label>
      <label class="mob">Preu<input data-f="preu_unitari" inputmode="decimal" value="${l.preu_unitari}" ${bloquejat ? "disabled" : ""}></label>
      <label class="mob">Dte %<input data-f="descompte_pct" inputmode="decimal" value="${l.descompte_pct || 0}" ${bloquejat ? "disabled" : ""}></label>
      <b class="r import" data-import>${eur(l.import)}</b>
      ${!bloquejat ? `<div class="ops"><button class="btn-icon" data-amunt title="Puja">↑</button><button class="btn-icon" data-treu title="Treu">✕</button></div>` : "<span></span>"}
    </div>`;

  const pinta = () => {
    cont.innerHTML = linies.length ? linies.map(filaHtml).join("") : `<div class="buit"><p>Afegeix línies amb els botons de sota o dicta el pressupost.</p></div>`;
    pintaTotals();
  };

  const marca = () => { brut = true; const b = el.querySelector("[data-desar]"); if (b) b.textContent = "Desa *"; };

  cont.addEventListener("input", (e) => {
    const fila = e.target.closest("[data-i]"); if (!fila) return;
    const l = linies[+fila.dataset.i], camp = e.target.dataset.f;
    const v = e.target.value;
    if (["descripcio", "unitat"].includes(camp)) l[camp] = v;
    else if (camp === "partida_id") l[camp] = v ? +v : null;
    else {
      l[camp] = parseNum(v) ?? 0;
      if (camp === "cost_unitari" || camp === "marge_pct") {
        if (l.cost_unitari) { l.preu_unitari = r2(l.cost_unitari * (1 + (l.marge_pct || 0) / 100)); fila.querySelector("[data-f=preu_unitari]").value = l.preu_unitari; }
      } else if (camp === "preu_unitari" && l.cost_unitari) {
        l.marge_pct = r2((l.preu_unitari / l.cost_unitari - 1) * 100); fila.querySelector("[data-f=marge_pct]").value = l.marge_pct;
      }
    }
    if (e.target.tagName === "TEXTAREA") { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; }
    marca(); pintaTotals();
  });
  cont.addEventListener("change", (e) => { if (e.target.tagName === "SELECT") { marca(); } });
  cont.addEventListener("click", (e) => {
    const fila = e.target.closest("[data-i]"); if (!fila) return;
    const i = +fila.dataset.i;
    if (e.target.closest("[data-treu]")) { linies.splice(i, 1); marca(); pinta(); }
    if (e.target.closest("[data-amunt]") && i > 0) { [linies[i - 1], linies[i]] = [linies[i], linies[i - 1]]; marca(); pinta(); }
  });
  el.querySelectorAll("[data-cap]").forEach((i) => i.addEventListener("input", () => { marca(); pintaTotals(); }));

  const afegeix = (l) => { linies.push(calculaLinia({ quantitat: 1, unitat: "u", cost_unitari: 0, marge_pct: margeDef, preu_unitari: 0, descompte_pct: 0, ...l })); marca(); pinta(); };

  const desa = async () => {
    const res = await put(`/api/pressupostos/${id}`, { ...cap(), linies });
    linies = res.totals.linies.map((l) => ({ ...l }));
    brut = false;
    const b = el.querySelector("[data-desar]"); if (b) b.textContent = "Desa";
    pinta();
    return res;
  };

  if (!bloquejat) {
    el.querySelector("[data-desar]").onclick = async () => { try { await desa(); toast("Pressupost desat"); } catch (e) { errorToast(e); } };
    el.querySelector("[data-lliure]").onclick = () => afegeix({ descripcio: "", partida_id: pmat?.id });
    el.querySelector("[data-ma]").onclick = () => {
      const c = parseNum(state.settings.cost_hora_defecte) ?? 25, v = parseNum(state.settings.preu_hora_defecte) ?? 38;
      afegeix({ descripcio: "Mà d'obra", partida_id: pmo?.id, unitat: "h", cost_unitari: c, preu_unitari: v, marge_pct: r2((v / c - 1) * 100) });
    };
    el.querySelector("[data-article]").onclick = async () => { const a = await triaArticle(); if (a) afegeix(a); };
    el.querySelector("[data-marge-tot]").onclick = async () => {
      const m = modal("Aplicar marge", `<div class="form"><label>Marge % sobre el cost<input name="m" inputmode="decimal" value="${margeDef}"></label>
        <label>Aplica a<select name="a"><option value="">Totes les línies</option>${opcions(state.partides, "")}</select></label></div>`, {
        botons: [{ text: "Cancel·la" }, { text: "Aplica", classe: "primari", accio: (el2) => ({ m: parseNum(el2.querySelector("[name=m]").value), a: el2.querySelector("[name=a]").value }) }],
      });
      const r = await m.done; if (!r || r.m === null) return;
      linies.forEach((l) => { if ((!r.a || String(l.partida_id) === r.a) && l.cost_unitari) { l.marge_pct = r.m; l.preu_unitari = r2(l.cost_unitari * (1 + r.m / 100)); } });
      marca(); pinta();
    };
    el.querySelector("[data-envia]").onclick = async () => {
      try {
        await desa();
        const rev = await get(`/api/pressupostos/${id}/revisio`);
        const errors = rev.avisos.filter((a) => a.nivell === "error");
        if (errors.length && !(await confirma(`Hi ha ${errors.length} error(s): ${errors.map((e) => e.text).join(" ")} Vols enviar-lo igualment?`, { ok: "Envia" }))) return;
        const r = await post(`/api/pressupostos/${id}/enviar`);
        compartir({ token: r.token, text: r.text, telefon: p.feina.client_telefon, email: p.feina.client_email, assumpte: `Pressupost ${p.numero}` });
        toast("Pressupost marcat com a enviat");
      } catch (e) { errorToast(e); }
    };
    el.querySelector("[data-acceptat]").onclick = async () => {
      const m = modal("Marcar com a acceptat", `<div class="form"><label>Acceptat per<input name="per" value="${esc(p.feina.client_nom || "")}"></label>
        <p class="muted">Fes-ho servir si el client l'ha acceptat per telèfon, en persona o signat en paper. També el pot acceptar ell mateix des de l'enllaç.</p></div>`, {
        botons: [{ text: "Cancel·la" }, { text: "Acceptat", classe: "primari", accio: async (e2) => { if (brut) await desa(); await post(`/api/pressupostos/${id}/acceptar`, { per: e2.querySelector("[name=per]").value }); } }],
      });
      if (await m.done) { toast("Pressupost acceptat"); vistaPressupost(el, [id], _q, viva); }
    };
    const rb = el.querySelector("[data-rebutjat]");
    if (rb) rb.onclick = async () => {
      const m = modal("Pressupost rebutjat", `<div class="form"><label>Motiu<input name="motiu"></label></div>`, {
        botons: [{ text: "Cancel·la" }, { text: "Desa", classe: "primari", accio: (e2) => post(`/api/pressupostos/${id}/rebutjar`, { motiu: e2.querySelector("[name=motiu]").value }) }],
      });
      if (await m.done) vistaPressupost(el, [id], _q, viva);
    };
    const eb = el.querySelector("[data-esborra]");
    if (eb) eb.onclick = async () => {
      if (!(await confirma("Esborrar aquest esborrany de pressupost?", { perill: true, ok: "Esborra" }))) return;
      await del(`/api/pressupostos/${id}`); location.hash = `#/feina/${p.feina.id}/pressupostos`;
    };
  }

  el.querySelector("[data-imprimir]").onclick = async () => { if (brut) await desa(); obre(`/imprimir/pressupost/${id}`); };
  el.querySelector("[data-duplicar]").onclick = async () => {
    const feines = await get("/api/feines?estat=");
    const m = modal("Duplicar pressupost", `<div class="form"><label>A la feina<select name="f">${opcions(feines, p.feina.id, { text: (f) => `${f.codi} · ${f.nom}` })}</select></label>
      <p class="muted">Útil per fer un pressupost nou a partir d'un de semblant.</p></div>`, {
      botons: [{ text: "Cancel·la" }, { text: "Duplica", classe: "primari", accio: (e2) => post(`/api/pressupostos/${id}/duplicar`, { feina_id: e2.querySelector("[name=f]").value }) }],
    });
    const r = await m.done; if (r && r.id) location.hash = `#/pressupost/${r.id}`;
  };

  const caixa = el.querySelector("[data-revisio]");
  el.querySelector("[data-revisa]").onclick = async () => {
    try {
      if (brut && !bloquejat) await desa();
      const r = await get(`/api/pressupostos/${id}/revisio`);
      caixa.classList.remove("muted");
      caixa.innerHTML = `${r.avisos.map((a) => `<div class="avis ${a.nivell}">${a.nivell === "error" ? "⛔" : a.nivell === "avis" ? "⚠" : "ℹ"} ${esc(a.text)}</div>`).join("") || `<div class="avis info">Cap problema detectat.</div>`}
        ${r.semblants.length ? `<h3>Pressupostos semblants</h3><div class="llista">${r.semblants.map((s) => `<a class="fila" href="#/pressupost/${s.id}">
          <div><b>${esc(s.numero)}</b> ${esc(s.titol || "")}<div class="muted">${esc(s.tipus || "")} · ${num(s.hores)} h pressupostades${s.hores_reals !== null ? ` · ${num(s.hores_reals)} h reals` : ""}</div></div>
          <div class="r"><b>${eur(s.base)}</b>${s.cost_real !== null ? `<div class="muted">cost real ${eur(s.cost_real)}</div>` : ""}</div></a>`).join("")}</div>` : ""}`;
    } catch (e) { errorToast(e); }
  };
  const bia = el.querySelector("[data-revisa-ia]");
  if (bia) bia.onclick = async () => {
    try {
      if (brut && !bloquejat) await desa();
      bia.disabled = true; bia.textContent = "Revisant…";
      const r = await post(`/api/pressupostos/${id}/revisio-ia`);
      caixa.classList.remove("muted");
      caixa.innerHTML = `<p><b>${esc(r.resum)}</b></p>${r.avisos.map((a) => `<div class="avis">⚠ ${esc(a)}</div>`).join("")}
        ${r.suggeriments.length ? `<h3>Suggeriments</h3><ul>${r.suggeriments.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}`;
    } catch (e) { errorToast(e); } finally { bia.disabled = false; bia.textContent = "Revisa amb IA"; }
  };

  window.onbeforeunload = () => (brut ? true : undefined);
  window.addEventListener("hashchange", () => { window.onbeforeunload = null; }, { once: true });
  pinta();
  cont.querySelectorAll("textarea").forEach((t) => { t.style.height = t.scrollHeight + "px"; });
}

export async function triaArticle() {
  const m = modal("Tria article", `<div class="form"><input type="search" placeholder="Cerca article" data-q></div><div class="llista" data-r></div>
    <p class="muted">Pots crear articles a la secció Articles.</p>`, { ample: true });
  const res = m.el.querySelector("[data-r]");
  let llista = [];
  const cerca = async () => {
    llista = await get(`/api/articles?q=${encodeURIComponent(m.el.querySelector("[data-q]").value)}`);
    res.innerHTML = llista.map((a, i) => `<button class="fila" data-i="${i}"><div><b>${esc(a.nom)}</b><div class="muted">${esc(a.codi || "")} ${esc(a.proveidor || "")} · cost ${eur(a.cost)}/${esc(a.unitat)}</div></div>
      <div class="r"><b>${eur(a.preu_venda)}</b>${a.descompte_pct ? `<div class="muted">-${num(a.descompte_pct)}%</div>` : ""}</div></button>`).join("") || `<p class="muted">Cap article.</p>`;
  };
  m.el.querySelector("[data-q]").oninput = debounce(cerca, 250);
  res.onclick = (e) => {
    const b = e.target.closest("[data-i]"); if (!b) return;
    const a = llista[+b.dataset.i];
    m.close({ article_id: a.id, descripcio: a.nom, partida_id: a.partida_id, unitat: a.unitat, cost_unitari: a.cost,
      preu_unitari: a.preu_venda, marge_pct: a.cost ? r2((a.preu_venda / a.cost - 1) * 100) : 0, descompte_pct: a.descompte_pct || 0 });
  };
  cerca();
  return m.done;
}
