// Assistent: digues o escriu què vols fer i es converteix en accions que confirmes abans d'executar.
import { dictat, errorToast, esc, eur, get, modal, num, opcions, post, state, toast } from "./core.js";

const ICONES = {
  afegir_hores: "⏱️", afegir_linia_pressupost: "📄", modificar_linia_pressupost: "✏️", eliminar_linia_pressupost: "🗑️",
  afegir_linia_factura: "🧾", afegir_despesa: "💶", afegir_missatge: "💬", afegir_planning: "📅",
  canviar_estat_feina: "🔁", crear_feina: "🏗️",
};

function detall(a) {
  const parts = [];
  if (a.hores) parts.push(`${num(a.hores)} h`);
  if (a.quantitat && !a.hores) parts.push(`${num(a.quantitat)} ${esc(a.unitat || "")}`);
  if (a.preu_unitari !== null && a.preu_unitari !== undefined) parts.push(`preu ${eur(a.preu_unitari)}`);
  if (a.cost_unitari !== null && a.cost_unitari !== undefined) parts.push(`cost ${eur(a.cost_unitari)}`);
  if (a.import_total) parts.push(eur(a.import_total));
  if (a.referencia) parts.push(`ref. ${esc(a.referencia)}`);
  if (a.data) parts.push(esc(a.data));
  return parts.join(" · ");
}

export async function obreAssistent(feinaId = null) {
  if (!state.ia) {
    modal("Assistent", `<p>L'assistent per veu necessita la IA activada (clau ANTHROPIC_API_KEY al servidor).</p>`);
    return;
  }
  const m = modal("Què vols fer?", `
    <div class="form assistent">
      <p class="muted">Ex.: «Afegeix 4 hores de mà d'obra a la feina del carrer Major», «al pressupost del bany canvia la rajola a 28 € el m2»,
        «afegeix a la factura 1 desplaçament de 30 €», «posa una nota: dimarts arriba el plat de dutxa».</p>
      <textarea data-text rows="4" placeholder="Digues o escriu què vols fer"></textarea>
      <div class="barra-accions"><button class="btn gran microfon" data-mic>🎤 Parla</button>
        <button class="btn primari gran" data-interpreta>Entesos</button></div>
      <div data-proposta></div>
    </div>`, { ample: true });
  const ta = m.el.querySelector("[data-text]");
  const bmic = m.el.querySelector("[data-mic]");
  const rec = dictat((f, p) => { ta.value = f + p; }, (actiu) => {
    bmic.classList.toggle("actiu", actiu);
    bmic.textContent = actiu ? "⏹ Atura" : "🎤 Parla";
  });
  if (rec) { bmic.onclick = () => (rec.actiu ? rec.stop() : rec.start(ta.value)); rec.start(""); }
  else bmic.style.display = "none";
  m.done.then(() => rec && rec.actiu && rec.stop());

  const zona = m.el.querySelector("[data-proposta]");
  let feines = null;
  m.el.querySelector("[data-interpreta]").onclick = async (e) => {
    if (rec && rec.actiu) rec.stop();
    const b = e.currentTarget;
    b.disabled = true;
    zona.innerHTML = `<div class="llegint"><div class="spinner"></div><p>Entenent què vols fer…</p></div>`;
    try {
      const [r, fs] = await Promise.all([post("/api/assistent/interpretar", { text: ta.value, feina_id: feinaId }),
        feines ? Promise.resolve(feines) : get("/api/feines?estat=")]);
      feines = fs;
      if (!r.accions.length) {
        zona.innerHTML = `<div class="avis">No he trobat cap acció. ${r.dubtes.map(esc).join(" ")}</div>`;
        return;
      }
      zona.innerHTML = `
        ${r.dubtes.length ? `<div class="avis">${r.dubtes.map(esc).join("<br>")}</div>` : ""}
        <h3>Revisa-ho abans de fer-ho</h3>
        <div class="accions-proposades">${r.accions.map((a, i) => `
          <div class="accio-prop" data-i="${i}">
            <label class="check"><input type="checkbox" checked data-sel> <span>${ICONES[a.tipus] || "•"} <b>${esc(a.resum)}</b>
              <small class="muted">${detall(a)}</small></span></label>
            ${a.tipus !== "crear_feina" ? `<select data-feina class="${a.feina_id ? "" : "falta"}">${opcions(feines, a.feina_id,
              { buit: a.opcions_feina?.length ? "— Tria quina feina —" : "— Tria la feina —", text: (f) => `${f.codi} · ${f.nom}` })}</select>` : ""}
          </div>`).join("")}</div>
        <button class="btn primari gran ample" data-executa>Fes-ho</button>`;
      zona.querySelector("[data-executa]").onclick = async (ev) => {
        const accions = [];
        zona.querySelectorAll(".accio-prop").forEach((el) => {
          if (!el.querySelector("[data-sel]").checked) return;
          const a = { ...r.accions[+el.dataset.i] };
          const s = el.querySelector("[data-feina]");
          if (s) a.feina_id = s.value ? +s.value : null;
          accions.push(a);
        });
        if (!accions.length) return;
        ev.currentTarget.disabled = true;
        try {
          const res = await post("/api/assistent/executar", { accions });
          zona.innerHTML = `<h3>Fet</h3>${res.resultats.map((x) => `<div class="avis ${x.ok ? "info" : "error"}">${x.ok ? "✓" : "⛔"} ${esc(x.text)}
            ${x.enllac ? ` · <a href="${esc(x.enllac)}" data-tanca-mod>Obre</a>` : ""}</div>`).join("")}
            <button class="btn" data-altra>Una altra ordre</button>`;
          zona.querySelectorAll("[data-tanca-mod]").forEach((a) => a.addEventListener("click", () => m.close(true)));
          zona.querySelector("[data-altra]").onclick = () => { ta.value = ""; zona.innerHTML = ""; if (rec) rec.start(""); };
          if (res.resultats.some((x) => x.ok)) {
            toast("Fet ✓");
            window.dispatchEvent(new HashChangeEvent("hashchange"));
          }
        } catch (err) { errorToast(err); ev.currentTarget.disabled = false; }
      };
    } catch (err) { zona.innerHTML = ""; errorToast(err); } finally { b.disabled = false; }
  };
  return m.done;
}
