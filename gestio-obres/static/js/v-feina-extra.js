// Pestanyes de feina: planning i evolució, anàlisi de tancament.
import { api, buit, comprimeixImatge, confirma, dataCat, del, errorToast, esc, eur, get, modal, num, pct, post, put, state, toast } from "./core.js";

const ESTATS = { pendent: "Pendent", en_curs: "En curs", fet: "Fet" };

export async function tabPlanning(el, f, recarrega) {
  const [tasques, valoracions] = await Promise.all([get(`/api/feines/${f.id}/planning`), get(`/api/feines/${f.id}/valoracions`)]);
  const progres = tasques.length ? Math.round(tasques.reduce((s, t) => s + t.pct, 0) / tasques.length) : null;
  el.innerHTML = `
    <div class="barra-accions"><button class="btn primari" data-nova>＋ Fase / tasca</button>
      <button class="btn" data-evolucio>📸 Publicar evolució</button>
      ${progres !== null ? `<span class="muted">Avanç global: <b>${progres}%</b></span>` : ""}</div>
    <p class="muted">El client veu el planning, l'avanç i les fotos d'evolució al seu enllaç.</p>
    ${tasques.length ? `<div class="llista planning">${tasques.map((t) => `
      <div class="fila" data-id="${t.id}">
        <div class="pl-info"><b>${esc(t.titol)}</b>
          <div class="muted">${t.data_inici ? dataCat(t.data_inici) : "sense data"}${t.data_fi ? " → " + dataCat(t.data_fi) : ""}</div>
          <div class="barra ${t.estat === "fet" ? "ok" : ""}"><div style="width:${t.pct}%"></div></div></div>
        <div class="botons-fila">
          <select data-estat>${Object.entries(ESTATS).map(([k, v]) => `<option value="${k}" ${k === t.estat ? "selected" : ""}>${v}</option>`).join("")}</select>
          <input data-pct inputmode="numeric" value="${t.pct}" class="curt" title="% fet">
          <button class="btn-icon" data-edita>✏️</button><button class="btn-icon" data-treu>✕</button></div>
      </div>`).join("")}</div>` : buit("Encara no hi ha planning. Afegeix les fases de la feina (enderroc, instal·lacions, rajola…).")}
    ${valoracions.length ? `<h2>Valoracions del client</h2><div class="llista">${valoracions.map((v) => `<div class="fila"><div>
      <span class="estrelles">${"★".repeat(v.puntuacio)}${"☆".repeat(5 - v.puntuacio)}</span><div class="muted">${esc(v.comentari || "")}</div></div>
      <div class="muted">${dataCat(v.created_at)}</div></div>`).join("")}</div>` : ""}`;

  const edita = async (t = {}) => {
    const m = modal(t.id ? "Tasca" : "Nova fase o tasca", `<div class="form">
      <label>Nom<input name="titol" value="${esc(t.titol || "")}" placeholder="Ex.: Enderroc i retirada de runa"></label>
      <div class="dues"><label>Inici<input type="date" name="data_inici" value="${esc(t.data_inici || "")}"></label>
        <label>Final<input type="date" name="data_fi" value="${esc(t.data_fi || "")}"></label></div></div>`, {
      botons: [{ text: "Cancel·la" }, { text: "Desa", classe: "primari", accio: (e) => {
        const d = Object.fromEntries([...e.querySelectorAll("[name]")].map((i) => [i.name, i.value]));
        return t.id ? put(`/api/planning/${t.id}`, d) : post(`/api/feines/${f.id}/planning`, d);
      } }],
    });
    if (await m.done) recarrega();
  };
  el.querySelector("[data-nova]").onclick = () => edita();
  el.querySelector("[data-evolucio]").onclick = async () => { if (await modalEvolucio(f)) recarrega(); };
  el.querySelectorAll("[data-id]").forEach((row) => {
    const t = tasques.find((x) => x.id === +row.dataset.id);
    row.querySelector("[data-estat]").onchange = async (e) => {
      const pctV = e.target.value === "fet" ? 100 : e.target.value === "en_curs" ? Math.max(t.pct, 10) : 0;
      await put(`/api/planning/${t.id}`, { estat: e.target.value, pct: pctV }).catch(errorToast); recarrega();
    };
    row.querySelector("[data-pct]").onchange = async (e) => {
      const v = Math.max(0, Math.min(100, parseInt(e.target.value) || 0));
      await put(`/api/planning/${t.id}`, { pct: v, estat: v >= 100 ? "fet" : v > 0 ? "en_curs" : "pendent" }).catch(errorToast); recarrega();
    };
    row.querySelector("[data-edita]").onclick = () => edita(t);
    row.querySelector("[data-treu]").onclick = async () => {
      if (await confirma(`Treure «${t.titol}» del planning?`, { ok: "Treu", perill: true })) { await del(`/api/planning/${t.id}`); recarrega(); }
    };
  });
}

export function modalEvolucio(f) {
  let fotos = [];
  const m = modal("Publicar evolució", `<div class="form">
    <label>Què s'ha fet<textarea name="text" rows="3" placeholder="Ex.: Avui hem acabat l'enrajolat de la dutxa."></textarea></label>
    <label class="btn">📷 Afegir fotos<input type="file" accept="image/*" multiple capture="environment" hidden data-f></label>
    <div class="xips" data-prev></div>
    <p class="muted">Es publicarà al portal del client.</p></div>`, {
    botons: [{ text: "Cancel·la" }, { text: "Publica", classe: "primari", accio: async (e) => {
      const fd = new FormData();
      fd.append("text", e.querySelector("[name=text]").value);
      fotos.forEach((x) => fd.append("fotos", x));
      await api("POST", `/api/feines/${f.id}/evolucio`, fd);
      toast("Evolució publicada");
    } }],
  });
  m.el.querySelector("[data-f]").onchange = async (e) => {
    for (const x of e.target.files) fotos.push(await comprimeixImatge(x, 1600));
    m.el.querySelector("[data-prev]").innerHTML = fotos.map((x) => `<img class="mini-foto" src="${URL.createObjectURL(x)}">`).join("");
  };
  return m.done;
}

export async function tabAnalisi(el, f, recarrega) {
  const a = await get(`/api/feines/${f.id}/analisi`);
  const d = a.dades, x = d.xifres;
  const t = a.text || { be: d.be, malament: d.malament, propostes: d.propostes };
  const llista = (arr, cls) => arr && arr.length ? `<ul class="${cls}">${arr.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : `<p class="muted">—</p>`;
  el.innerHTML = `
    <div class="barra-accions">
      <span class="muted">${a.created_at ? `Anàlisi del ${dataCat(a.created_at)}${a.text?.font === "ia" ? " (amb IA)" : ""}` : "Previsualització amb les dades actuals"}</span>
      <button class="btn primari" data-genera>${a.created_at ? "Actualitza l'anàlisi" : "Genera l'anàlisi"}</button></div>
    ${t.resum ? `<div class="targeta"><p><b>${esc(t.resum)}</b></p></div>` : ""}
    <section class="kpis">
      <div class="kpi"><small>Contractat</small><b>${eur(x.contractat)}</b>${x.n_extres ? `<span class="muted">${x.n_extres} canvis: ${eur(x.extres)}</span>` : ""}</div>
      <div class="kpi"><small>Cost real / previst</small><b>${eur(x.cost_real)}</b><span class="muted">previst ${eur(x.cost_previst)}</span></div>
      <div class="kpi ${x.marge_real_pct !== null && x.marge_real_pct < x.marge_previst_pct - 2 ? "dolent" : "bo"}"><small>Marge real</small>
        <b>${x.marge_real_pct !== null ? pct(x.marge_real_pct) : "—"}</b><span class="muted">previst ${pct(x.marge_previst_pct)}</span></div>
      <div class="kpi ${x.hores_previstes && x.hores_reals > x.hores_previstes * 1.1 ? "dolent" : ""}"><small>Hores</small><b>${num(x.hores_reals)} / ${num(x.hores_previstes)} h</b></div>
      ${x.durada_dies ? `<div class="kpi"><small>Durada</small><b>${x.durada_dies} dies</b></div>` : ""}
      ${x.dies_cobrament !== null ? `<div class="kpi"><small>Cobrament mitjà</small><b>${num(x.dies_cobrament)} dies</b></div>` : ""}
      ${x.valoracio !== null ? `<div class="kpi"><small>Valoració client</small><b>${num(x.valoracio)} / 5</b></div>` : ""}
    </section>
    <div class="dues-col">
      <div class="targeta"><h3>✅ Què ha anat bé</h3>${llista(t.be, "be")}</div>
      <div class="targeta"><h3>⚠️ Què ha fallat</h3>${llista(t.malament, "malament")}</div>
    </div>
    <div class="targeta destacada"><h3>💡 Propostes per al proper pressupost${f.tipus ? ` de ${esc(f.tipus)}` : ""}</h3>${llista(t.propostes, "propostes")}
      <p class="muted">Aquestes propostes es tenen en compte automàticament quan prepares pressupostos del mateix tipus.</p></div>
    ${d.comentaris_client?.length ? `<div class="targeta"><h3>Comentaris del client</h3>${llista(d.comentaris_client, "")}</div>` : ""}`;
  el.querySelector("[data-genera]").onclick = async (e) => {
    e.target.disabled = true; e.target.textContent = "Analitzant…";
    try { await post(`/api/feines/${f.id}/analisi`); toast("Anàlisi actualitzada"); recarrega(); }
    catch (err) { errorToast(err); e.target.disabled = false; }
  };
}
