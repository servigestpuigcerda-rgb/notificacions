// Utilitats comunes: API, format, modals, avisos.

export const state = { usuari: null, ia: false, partides: [], settings: {}, empresa: "" };

export async function api(method, url, body, opts = {}) {
  const init = { method, headers: {}, credentials: "same-origin" };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const r = await fetch(url, init);
  if (r.status === 401 && !opts.noRedirect) {
    location.hash = "#/login";
    throw new Error("Cal iniciar sessió.");
  }
  let data = null;
  const text = await r.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    let msg = data && data.detail ? data.detail : `Error ${r.status}`;
    if (Array.isArray(msg)) msg = msg.map((x) => x.msg).join(". ");
    throw new Error(msg);
  }
  return data;
}

export const get = (u) => api("GET", u);
export const post = (u, b) => api("POST", u, b ?? {});
export const put = (u, b) => api("PUT", u, b);
export const del = (u) => api("DELETE", u);

export function esc(v) {
  return v === null || v === undefined ? "" : String(v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const fmtEur = new Intl.NumberFormat("ca-ES", { style: "currency", currency: "EUR" });
const fmtNum = new Intl.NumberFormat("ca-ES", { maximumFractionDigits: 2 });
export const eur = (v) => fmtEur.format(+v || 0);
export const num = (v) => fmtNum.format(+v || 0);
export const pct = (v) => `${fmtNum.format(Math.round((+v || 0) * 10) / 10)}%`;
export const today = () => new Date().toISOString().slice(0, 10);
export function dataCat(d) {
  if (!d) return "";
  const [y, m, dd] = String(d).slice(0, 10).split("-");
  return `${dd}/${m}/${y}`;
}
export function dataHora(d) {
  if (!d) return "";
  return `${dataCat(d)} ${String(d).slice(11, 16)}`;
}
export const r2 = (x) => Math.round(((+x || 0) + Number.EPSILON) * 100) / 100;
export const parseNum = (v) => {
  if (v === "" || v === null || v === undefined) return null;
  const n = parseFloat(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : null;
};

export function toast(msg, tipus = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${tipus}`;
  el.textContent = msg;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => el.classList.add("out"), 3200);
  setTimeout(() => el.remove(), 3700);
}

export function errorToast(e) {
  toast(e.message || String(e), "error");
}

// Modal genèric. contingut: HTML. Retorna {el, close, done:Promise}
export function modal(titol, contingut, { botons = [], ample = false } = {}) {
  const fons = document.createElement("div");
  fons.className = "modal-fons";
  fons.innerHTML = `
    <div class="modal ${ample ? "ample" : ""}" role="dialog" aria-modal="true">
      <header><h3>${esc(titol)}</h3><button class="btn-icon" data-tanca aria-label="Tanca">✕</button></header>
      <div class="modal-cos">${contingut}</div>
      ${botons.length ? `<footer>${botons.map((b, i) =>
        `<button class="btn ${b.classe || ""}" data-boto="${i}">${esc(b.text)}</button>`).join("")}</footer>` : ""}
    </div>`;
  document.body.appendChild(fons);
  document.body.classList.add("amb-modal");
  let resol;
  const done = new Promise((r) => (resol = r));
  const close = (v = null) => {
    fons.remove();
    if (!document.querySelector(".modal-fons")) document.body.classList.remove("amb-modal");
    resol(v);
  };
  fons.addEventListener("click", async (e) => {
    if (e.target === fons || e.target.closest("[data-tanca]")) return close(null);
    const b = e.target.closest("[data-boto]");
    if (b) {
      const def = botons[+b.dataset.boto];
      if (def.accio) {
        b.disabled = true;
        try {
          const res = await def.accio(fons.querySelector(".modal"));
          if (res !== false) close(res ?? true);
        } catch (err) {
          errorToast(err);
        } finally {
          b.disabled = false;
        }
      } else close(def.valor ?? null);
    }
  });
  const primer = fons.querySelector("input,select,textarea");
  if (primer && window.matchMedia("(pointer:fine)").matches) setTimeout(() => primer.focus(), 50);
  return { el: fons.querySelector(".modal"), close, done };
}

export async function confirma(text, { ok = "D'acord", perill = false } = {}) {
  const m = modal("Confirmació", `<p>${esc(text)}</p>`, {
    botons: [{ text: "Cancel·la", valor: false }, { text: ok, classe: perill ? "perill" : "primari", valor: true }],
  });
  return (await m.done) === true;
}

// Llegeix els camps [name] d'un contenidor
export function formData(el) {
  const out = {};
  el.querySelectorAll("[name]").forEach((i) => {
    if (i.type === "checkbox") out[i.name] = i.checked;
    else if (i.type === "radio") { if (i.checked) out[i.name] = i.value; }
    else out[i.name] = i.value;
  });
  return out;
}

export function opcions(llista, sel, { buit = null, valor = "id", text = "nom" } = {}) {
  const ops = llista.map((x) => `<option value="${esc(x[valor])}" ${String(x[valor]) === String(sel ?? "") ? "selected" : ""}>${esc(typeof text === "function" ? text(x) : x[text])}</option>`).join("");
  return (buit !== null ? `<option value="">${esc(buit)}</option>` : "") + ops;
}

export const ESTATS_FEINA = {
  pressupost: "Pressupost", acceptada: "Acceptada", en_curs: "En curs", acabada: "Acabada",
  tancada: "Tancada", cancellada: "Cancel·lada",
};
export const ESTATS_PRESSUPOST = { esborrany: "Esborrany", enviat: "Enviat", acceptat: "Acceptat", rebutjat: "Rebutjat" };
export const ESTATS_FACTURA = { esborrany: "Esborrany", emesa: "Emesa", cobrada: "Cobrada", anullada: "Anul·lada" };

export function badge(estat, mapa) {
  return `<span class="badge b-${esc(estat)}">${esc((mapa && mapa[estat]) || estat)}</span>`;
}

export function barra(valor, maxim, { etiqueta = "", inversa = false } = {}) {
  const p = maxim ? Math.min((valor / maxim) * 100, 130) : 0;
  let cls = "ok";
  if (!inversa && p > 100) cls = "mal";
  else if (!inversa && p > 85) cls = "avis";
  return `<div class="barra ${cls}" title="${esc(etiqueta)}"><div style="width:${Math.min(p, 100)}%"></div></div>`;
}

export function buit(text, extra = "") {
  return `<div class="buit"><p>${esc(text)}</p>${extra}</div>`;
}

// Redueix les fotos abans de pujar-les (menys dades mòbils i lectura més ràpida)
export async function comprimeixImatge(file, maxDim = 2000, qualitat = 0.85) {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  try {
    const bmp = await createImageBitmap(file);
    const escala = Math.min(1, maxDim / Math.max(bmp.width, bmp.height));
    if (escala === 1 && file.size < 1.5e6) return file;
    const cv = document.createElement("canvas");
    cv.width = Math.round(bmp.width * escala);
    cv.height = Math.round(bmp.height * escala);
    cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
    const blob = await new Promise((r) => cv.toBlob(r, "image/jpeg", qualitat));
    return new File([blob], (file.name || "foto").replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;
  }
}

export function enllacPortal(token) {
  return window.DEMO ? window.DEMO.enllacPortal(token) : `${location.origin}/p/${token}`;
}

// Adreça real d'un fitxer (a la demo, les fotos viuen al navegador)
export function urlFitxer(u) {
  return window.DEMO ? window.DEMO.url(u) : u;
}

// Diàleg per compartir amb el client (WhatsApp, correu, copiar)
export function compartir({ token, text, telefon, email, assumpte = "" }) {
  const url = enllacPortal(token);
  const msg = `${text ? text + "\n\n" : ""}Podeu consultar-ho i respondre aquí: ${url}`;
  const tel = (telefon || "").replace(/[^\d+]/g, "").replace(/^\+/, "");
  const wa = `https://wa.me/${tel && tel.length === 9 ? "34" + tel : tel}?text=${encodeURIComponent(msg)}`;
  const mail = `mailto:${encodeURIComponent(email || "")}?subject=${encodeURIComponent(assumpte)}&body=${encodeURIComponent(msg)}`;
  const m = modal("Envia al client", `
    <p class="muted">El client veurà la feina, els pressupostos, les factures i els missatges en aquest enllaç, i podrà acceptar o respondre.</p>
    <div class="enllac"><input readonly value="${esc(url)}"><button class="btn" data-copia>Copia</button></div>
    <div class="botons-grans">
      <a class="btn gran whatsapp" href="${esc(wa)}" target="_blank" rel="noopener">WhatsApp</a>
      <a class="btn gran" href="${esc(mail)}">Correu</a>
      ${navigator.share ? `<button class="btn gran" data-share>Comparteix…</button>` : ""}
      <a class="btn gran" href="#/portal/${esc(token)}" data-veure>Veure com ho veu el client</a>
    </div>`);
  m.el.querySelector("[data-veure]").addEventListener("click", () => m.close());
  m.el.querySelector("[data-copia]").onclick = async () => {
    try { await navigator.clipboard.writeText(url); toast("Enllaç copiat"); } catch { m.el.querySelector("input").select(); }
  };
  const sh = m.el.querySelector("[data-share]");
  if (sh) sh.onclick = () => navigator.share({ title: assumpte, text: msg }).catch(() => {});
}

export function debounce(fn, ms = 300) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export function obre(url) {
  window.open(url, "_blank", "noopener");
}

// Dictat per veu (Web Speech API). Retorna null si el navegador no ho permet.
export function dictat(onText, onEstat) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = "ca-ES";
  rec.continuous = true;
  rec.interimResults = true;
  let actiu = false;
  let base = "";
  rec.onresult = (e) => {
    let final = "", parcial = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) final += t; else parcial += t;
    }
    if (final) base += (base && !base.endsWith(" ") ? " " : "") + final.trim() + " ";
    onText(base, parcial);
  };
  rec.onend = () => { if (actiu) { try { rec.start(); } catch { /* ja actiu */ } } else onEstat(false); };
  rec.onerror = (e) => {
    if (e.error === "not-allowed") { actiu = false; toast("Cal donar permís al micròfon.", "error"); }
  };
  return {
    start(textInicial = "") { base = textInicial ? textInicial.trim() + " " : ""; actiu = true; rec.start(); onEstat(true); },
    stop() { actiu = false; rec.stop(); onEstat(false); },
    get actiu() { return actiu; },
  };
}
