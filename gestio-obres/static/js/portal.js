// Portal del client: el que veu el client amb el seu enllaç personal.
  import { esc, eur, dataCat, dataHora, modal, toast, errorToast, badge, ESTATS_PRESSUPOST, ESTATS_FACTURA } from "./core.js";
  import { modalSignatura } from "./forms.js";
let token, base, el;
  const req = async (m, u, b) => {
    const r = await fetch(u, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Error");
    return d;
  };
  const ESTAT_FEINA = { pressupost: "Pendent de pressupost", acceptada: "Acceptada", en_curs: "En curs", acabada: "Acabada", tancada: "Tancada", cancellada: "Cancel·lada" };
  const ESTAT_TASCA = { pendent: "Pendent", en_curs: "En curs", fet: "Fet" };
  const foto = (id) => `/p/${token}/fitxer/${id}`;
  const copia = async (t) => { try { await navigator.clipboard.writeText(t); toast("Copiat"); } catch { toast(t); } };

  function modalPagar(d, f) {
    const pg = d.pagament;
    const m = modal(`Pagar la factura ${f.codi}`, `
      <p>Import: <b class="gran-text">${eur(f.total)}</b></p>
      ${pg.iban ? `<div class="pagament-op"><h3>🏦 Transferència</h3>
        <div class="copia"><code>${esc(pg.iban)}</code><button class="btn petit" data-c="${esc(pg.iban)}">Copia</button></div>
        <div class="muted">Titular: ${esc(pg.titular || "")}</div>
        <div class="copia"><span class="muted">Concepte:</span><code>${esc(f.codi)}</code><button class="btn petit" data-c="${esc(f.codi)}">Copia</button></div>
        <button class="btn primari" data-pagat="transferencia">Ja he fet la transferència</button></div>` : ""}
      ${pg.bizum ? `<div class="pagament-op"><h3>📱 Bizum</h3>
        <p class="muted">Obre l'app del teu banc → Bizum → Enviar diners, i posa:</p>
        <div class="copia"><span class="muted">Telèfon:</span><code>${esc(pg.bizum)}</code><button class="btn petit" data-c="${esc(pg.bizum)}">Copia</button></div>
        <div class="copia"><span class="muted">Import:</span><code>${(+f.total).toFixed(2).replace(".", ",")}</code><button class="btn petit" data-c="${(+f.total).toFixed(2).replace(".", ",")}">Copia</button></div>
        <div class="copia"><span class="muted">Concepte:</span><code>${esc(f.codi)}</code><button class="btn petit" data-c="${esc(f.codi)}">Copia</button></div>
        <p class="muted">Bizum té límits d'import per operació segons cada banc.</p>
        <button class="btn primari" data-pagat="bizum">Ja he fet el Bizum</button></div>` : ""}
      ${!pg.iban && !pg.bizum ? `<p>Poseu-vos en contacte amb nosaltres per fer el pagament.</p>` : ""}`);
    m.el.querySelectorAll("[data-c]").forEach((b) => (b.onclick = () => copia(b.dataset.c)));
    m.el.querySelectorAll("[data-pagat]").forEach((b) => (b.onclick = async () => {
      try { await req("POST", `${base}/factures/${f.id}/pagat`, { metode: b.dataset.pagat }); m.close(); toast("Gràcies! Ho comprovarem i us confirmarem el cobrament."); pinta(); }
      catch (e) { errorToast(e); }
    }));
  }

  async function obreMaqueta(r) {
    const m = modal(r.titol, `<div class="visor gran" data-v></div><p class="muted">Arrossegueu per girar i pinceu per apropar. Maqueta orientativa del resultat.</p>`, { ample: true });
    try {
      const [{ visor3d }, dades] = await Promise.all([import("./render3d.js"), req("GET", `${base}/renders/${r.id}`)]);
      const v = await visor3d(m.el.querySelector("[data-v]"), dades.model, { fotoUrl: foto });
      m.done.then(() => v.destrueix());
    } catch (e) { errorToast(e); }
  }

  async function pinta() {
    const d = await req("GET", base);
    document.title = `${d.feina.nom} · ${d.empresa.nom || ""}`;
    const pendents = d.pressupostos.filter((p) => p.estat === "enviat");
    const perPagar = d.factures.filter((f) => f.estat === "emesa");
    el.innerHTML = `
      <div class="capcalera"><div class="empresa">${esc(d.empresa.nom || "")}</div>
        <h1>${esc(d.feina.nom)}</h1><div class="muted">${esc(d.feina.adreca || "")} · Ref. ${esc(d.feina.codi)} · ${esc(ESTAT_FEINA[d.feina.estat] || d.feina.estat)}</div></div>

      ${d.bloquejos.length ? `<div class="aturada"><h2>⛔ ${d.bloquejos.some((b) => b.tipus === "pressupost") ? "La feina encara no pot començar" : "La feina està aturada"}</h2>
        <p>Fins que no es resolgui el següent no podrem ${d.bloquejos.some((b) => b.tipus === "pressupost") ? "començar" : "continuar"}:</p>
        <ul>${d.bloquejos.map((b) => `<li>${esc(b.text)}</li>`).join("")}</ul></div>` : ""}

      ${pendents.map((p) => `<div class="targeta" style="border-color:var(--blau)">
        <h2 style="margin-top:0">${p.tipus === "extra" ? "⚠️ Canvi / treball fora de pressupost" : "📄 Pressupost"} pendent de la vostra resposta</h2>
        <p><b>${esc(p.numero)}</b> ${esc(p.titol || "")}<br>Import: <b>${eur(p.total)}</b> (IVA inclòs)</p>
        ${p.tipus === "extra" ? `<p class="muted">Aquest treball no estava inclòs al pressupost inicial. No el farem sense la vostra conformitat.</p>` : ""}
        <div class="p-acc"><a class="btn" target="_blank" href="/p/${token}/imprimir/pressupost/${p.id}">Veure el detall</a>
          <button class="btn primari gran" data-accepta="${p.id}">Accepto</button>
          <button class="btn" data-rebutja="${p.id}">No l'accepto</button></div></div>`).join("")}

      ${perPagar.map((f) => `<div class="targeta" style="border-color:var(--groc)">
        <h2 style="margin-top:0">🧾 Factura ${esc(f.codi)} pendent de pagament</h2>
        <p>Import: <b>${eur(f.total)}</b> · venciment ${dataCat(f.venciment)}</p>
        ${f.pagament_notificat_at ? `<p class="verd">Ens heu indicat que ja l'heu pagada (${dataCat(f.pagament_notificat_at)}). La confirmarem en rebre l'ingrés.</p>` : ""}
        <div class="p-acc"><a class="btn" target="_blank" href="/p/${token}/imprimir/factura/${f.id}">Veure la factura</a>
          <button class="btn primari gran" data-paga="${f.id}">Pagar per transferència o Bizum</button></div></div>`).join("")}

      <section class="kpis petits">
        <div class="kpi"><small>Import acceptat (sense IVA)</small><b>${eur(d.resum.contractat)}</b></div>
        <div class="kpi"><small>Ja pagat</small><b>${eur(d.resum.cobrat)}</b></div>
        <div class="kpi"><small>Factures per pagar</small><b>${eur(d.pendent.per_pagar)}</b></div>
        <div class="kpi destacat"><small>Total que us queda</small><b>${eur(d.pendent.total)}</b><span>${eur(d.pendent.per_facturar)} encara per facturar</span></div>
      </section>

      ${d.planning.length ? `<h2>Planning${d.progres !== null ? ` · ${d.progres}% fet` : ""}</h2>
        ${d.progres !== null ? `<div class="barra"><div style="width:${d.progres}%"></div></div>` : ""}
        <div class="llista" style="margin-top:10px">${d.planning.map((t) => `<div class="fila"><div><b>${esc(t.titol)}</b>
          <div class="muted">${t.data_inici ? dataCat(t.data_inici) : ""}${t.data_fi ? " → " + dataCat(t.data_fi) : ""}</div></div>
          <div class="r">${t.estat === "fet" ? "✅" : t.estat === "en_curs" ? "🔨" : "⏳"} ${ESTAT_TASCA[t.estat]}${t.estat === "en_curs" ? ` ${t.pct}%` : ""}</div></div>`).join("")}</div>` : ""}

      ${d.evolucio.length ? `<h2>Evolució de la feina</h2><div class="evolucio">${d.evolucio.slice().reverse().map((e) => `
        <div class="ev"><small class="muted">${dataHora(e.created_at)}</small>${e.text && e.text !== "📷" ? `<p>${esc(e.text)}</p>` : ""}
        ${e.document_id ? `<a href="${foto(e.document_id)}" target="_blank"><img loading="lazy" src="${foto(e.document_id)}" alt=""></a>` : ""}</div>`).join("")}</div>` : ""}

      ${d.renders.length ? `<h2>Com quedarà</h2><div class="llista">${d.renders.map((r) => `<button class="fila" data-maqueta="${r.id}"><div><b>🧊 ${esc(r.titol)}</b><div class="muted">Maqueta 3D</div></div><div>Veure ›</div></button>`).join("")}</div>` : ""}

      <h2>Pressupostos</h2>
      ${d.pressupostos.length ? `<div class="llista">${d.pressupostos.map((p) => `
        <a class="fila" target="_blank" href="/p/${token}/imprimir/pressupost/${p.id}"><div><b>${esc(p.numero)}</b> ${p.tipus === "extra" ? `<span class="badge b-extra">canvi</span>` : ""} ${badge(p.estat, ESTATS_PRESSUPOST)}
          <div class="muted">${esc(p.titol || "")} ${p.acceptat_per ? "· acceptat per " + esc(p.acceptat_per) : ""}</div></div><div class="r"><b>${eur(p.total)}</b></div></a>`).join("")}</div>` : `<p class="muted">Encara no n'hi ha cap.</p>`}

      ${d.albarans.length ? `<h2>Albarans de feina</h2><div class="llista">${d.albarans.map((a) => `
        <div class="fila"><div><b>${esc(a.numero)}</b> · ${dataCat(a.data)}<div class="muted">${esc(a.descripcio || "")}</div></div>
          <div class="botons-fila"><a class="btn petit" target="_blank" href="/p/${token}/imprimir/albara/${a.id}">Veure</a>
          ${a.estat === "signat" ? `<span class="badge b-acceptat">Signat</span>` : `<button class="btn petit primari" data-signa="${a.id}">Signar</button>`}</div></div>`).join("")}</div>` : ""}

      ${d.factures.length ? `<h2>Factures</h2><div class="llista">${d.factures.map((f) => `
        <a class="fila" target="_blank" href="/p/${token}/imprimir/factura/${f.id}"><div><b>${esc(f.codi)}</b> ${badge(f.estat === "cobrada" ? "cobrada" : f.estat, { ...ESTATS_FACTURA, emesa: "Pendent de pagament", cobrada: "Pagada" })}
          <div class="muted">${dataCat(f.data)} · venciment ${dataCat(f.venciment)}</div></div><div class="r"><b>${eur(f.total)}</b></div></a>`).join("")}</div>` : ""}

      <h2>Comentaris i peticions</h2>
      <div class="xat">${d.missatges.filter((m) => m.tipus !== "evolucio" || !m.document_id).map((m) => `<div class="msg ${m.autor === "client" ? "empresa" : m.autor === "empresa" ? "client" : "sistema"} t-${m.tipus}">
        <div class="bombolla">${esc(m.text)}</div><small>${m.autor === "client" ? "Vosaltres" : esc(d.empresa.nom || "Empresa")} · ${dataHora(m.created_at)}</small></div>`).join("") || `<p class="muted">Cap missatge.</p>`}</div>
      <form class="enviar-msg" data-msg>
        <select name="tipus"><option value="comentari">Comentari</option><option value="canvi">Petició de canvi</option><option value="dubte">Dubte</option><option value="incidencia">Incidència</option></select>
        <textarea name="text" rows="2" placeholder="Escriviu-nos aquí qualsevol comentari o el que necessiteu"></textarea>
        <div class="fila-enviar"><span class="muted">${esc(d.empresa.telefon || "")} ${esc(d.empresa.email || "")}</span><button class="btn primari">Envia</button></div></form>

      <h2>Valoració</h2>
      <form class="targeta form" data-val>
        <div class="estrelles-in">${[1, 2, 3, 4, 5].map((i) => `<button type="button" data-st="${i}" aria-label="${i} estrelles">★</button>`).join("")}</div>
        <textarea name="comentari" rows="2" placeholder="Com ho estem fent? (opcional)"></textarea>
        <button class="btn primari">Envia la valoració</button>
        ${d.valoracions.length ? `<div class="muted">${d.valoracions.map((v) => `${"★".repeat(v.puntuacio)}${"☆".repeat(5 - v.puntuacio)} ${esc(v.comentari || "")} · ${dataCat(v.created_at)}`).join("<br>")}</div>` : ""}
      </form>
      <p class="muted" style="margin-top:24px">Aquest enllaç és personal: no el compartiu. Les vostres dades es tracten només per gestionar aquesta feina.</p>`;
    const xat = el.querySelector(".xat"); xat.scrollTop = xat.scrollHeight;

    el.querySelectorAll("[data-accepta]").forEach((b) => (b.onclick = () => {
      const p = d.pressupostos.find((x) => x.id === +b.dataset.accepta);
      const m = modal("Acceptar", `<div class="form"><p>${esc(p.numero)} · <b>${eur(p.total)}</b> IVA inclòs</p>
        <label>Nom i cognoms<input name="nom" autocomplete="name"></label>
        <label class="check"><input type="checkbox" name="accepto"> He llegit el pressupost i l'accepto amb les seves condicions.</label></div>`, {
        botons: [{ text: "Cancel·la" }, { text: "Accepto", classe: "primari", accio: (e) => req("POST", `${base}/pressupostos/${p.id}/acceptar`,
          { nom: e.querySelector("[name=nom]").value, accepto: e.querySelector("[name=accepto]").checked }) }],
      });
      m.done.then((r) => { if (r) { toast("Gràcies! Pressupost acceptat."); pinta(); } });
    }));
    el.querySelectorAll("[data-rebutja]").forEach((b) => (b.onclick = () => {
      const m = modal("No l'accepto", `<div class="form"><label>Ens podeu dir el motiu? (opcional)<textarea name="motiu" rows="3"></textarea></label></div>`, {
        botons: [{ text: "Cancel·la" }, { text: "Envia", classe: "primari", accio: (e) => req("POST", `${base}/pressupostos/${b.dataset.rebutja}/rebutjar`, { motiu: e.querySelector("[name=motiu]").value }) }],
      });
      m.done.then((r) => { if (r) pinta(); });
    }));
    el.querySelectorAll("[data-paga]").forEach((b) => (b.onclick = () => modalPagar(d, d.factures.find((f) => f.id === +b.dataset.paga))));
    el.querySelectorAll("[data-maqueta]").forEach((b) => (b.onclick = () => obreMaqueta(d.renders.find((r) => r.id === +b.dataset.maqueta))));
    el.querySelectorAll("[data-signa]").forEach((b) => (b.onclick = async () => {
      const s = await modalSignatura("Signar l'albarà");
      if (!s) return;
      try { await req("POST", `${base}/albarans/${b.dataset.signa}/signar`, s); toast("Albarà signat"); pinta(); } catch (e) { errorToast(e); }
    }));
    el.querySelector("[data-msg]").onsubmit = async (e) => {
      e.preventDefault();
      const t = e.target.text.value.trim(); if (!t) return;
      const tipus = e.target.tipus.value;
      try {
        if (tipus === "comentari") await req("POST", `${base}/missatges`, { text: t });
        else await req("POST", `${base}/peticions`, { text: t, tipus });
        toast("Enviat"); pinta();
      } catch (err) { errorToast(err); }
    };
    let estrelles = 0;
    const sts = el.querySelectorAll("[data-st]");
    sts.forEach((b) => (b.onclick = () => { estrelles = +b.dataset.st; sts.forEach((x) => x.classList.toggle("on", +x.dataset.st <= estrelles)); }));
    el.querySelector("[data-val]").onsubmit = async (e) => {
      e.preventDefault();
      try { await req("POST", `${base}/valoracions`, { puntuacio: estrelles, comentari: e.target.comentari.value }); toast("Gràcies per la valoració!"); pinta(); }
      catch (err) { errorToast(err); }
    };
  }
export async function vistaPortal(contenidor, tk) {
  el = contenidor;
  token = tk;
  base = `/api/portal/${token}`;
  try { await pinta(); } catch (e) { el.innerHTML = `<div class="buit">${esc(e.message)}</div>`; }
}

