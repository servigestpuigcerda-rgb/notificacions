import { api, esc, errorToast, formData, get, post, state, toast } from "./core.js";
import { vistaInici } from "./v-inici.js";
import { obreAssistent } from "./assistent.js";
import { vistaFeines, vistaFeina } from "./v-feines.js";
import { vistaPressupost } from "./v-pressupost.js";
import { vistaCaptura, vistaHores, vistaDictar } from "./v-captura.js";
import { vistaFactures, vistaFactura } from "./v-factures.js";
import { vistaClients, vistaArticles, vistaDocuments, vistaImpostos, vistaAprenentatge, vistaConfig, vistaMes } from "./v-altres.js";

const RUTES = [
  [/^\/?$/, vistaInici],
  [/^\/inici$/, vistaInici],
  [/^\/feines$/, vistaFeines],
  [/^\/feina\/(\d+)(?:\/(\w+))?$/, vistaFeina],
  [/^\/pressupost\/(\d+)$/, vistaPressupost],
  [/^\/captura$/, vistaCaptura],
  [/^\/hores$/, vistaHores],
  [/^\/dictar$/, vistaDictar],
  [/^\/factures$/, vistaFactures],
  [/^\/factura\/(\d+)$/, vistaFactura],
  [/^\/clients$/, vistaClients],
  [/^\/articles$/, vistaArticles],
  [/^\/documents$/, vistaDocuments],
  [/^\/impostos$/, vistaImpostos],
  [/^\/aprenentatge$/, vistaAprenentatge],
  [/^\/config$/, vistaConfig],
  [/^\/mes$/, vistaMes],
];

const MENU = [
  ["inici", "Inici", "🏠"],
  ["feines", "Feines", "🏗️"],
  ["captura", "Foto tiquet", "📷"],
  ["hores", "Hores", "⏱️"],
  ["dictar", "Dictar pressupost", "🎤"],
  ["factures", "Factures", "🧾"],
  ["documents", "Documents", "📁"],
  ["clients", "Clients", "👥"],
  ["articles", "Articles", "📦"],
  ["impostos", "Impostos", "🏛️", "admin"],
  ["aprenentatge", "Aprenentatge", "📈"],
  ["config", "Configuració", "⚙️"],
];

function layout() {
  const app = document.getElementById("app");
  const items = MENU.filter((m) => !m[3] || state.usuari.rol === "admin");
  app.innerHTML = `
    <aside class="lateral">
      <div class="marca">${esc(state.empresa || "Gestió d'obres")}</div>
      <button class="btn primari assistent-btn" data-assistent>🎙️ Digues què vols fer</button>
      <nav>${items.map(([r, t, i]) => `<a href="#/${r}" data-r="${r}"><span>${i}</span>${esc(t)}</a>`).join("")}</nav>
      <div class="peu-lateral">${esc(state.usuari.nom)} · <a href="#" data-logout>Surt</a></div>
    </aside>
    <main id="vista"></main>
    <nav class="inferior">
      <a href="#/inici" data-r="inici"><span>🏠</span>Inici</a>
      <a href="#/feines" data-r="feines"><span>🏗️</span>Feines</a>
      <button class="mes-gran" data-rapid aria-label="Acció ràpida">＋</button>
      <a href="#/factures" data-r="factures"><span>🧾</span>Factures</a>
      <a href="#/mes" data-r="mes"><span>☰</span>Més</a>
    </nav>`;
  app.querySelector("[data-logout]").onclick = async (e) => {
    e.preventDefault();
    await post("/api/logout");
    location.hash = "#/login";
    location.reload();
  };
  app.querySelector("[data-rapid]").onclick = accioRapida;
  app.querySelector("[data-assistent]").onclick = () => obreAssistent(feinaActual());
}

export function accioRapida() {
  const fons = document.createElement("div");
  fons.className = "full-fons";
  fons.innerHTML = `<div class="full">
      <button class="accio destacada" data-assist><span>🎙️</span>Digues què vols fer</button>
      <a href="#/captura" class="accio"><span>📷</span>Foto de tiquet o factura</a>
      <a href="#/hores" class="accio"><span>⏱️</span>Apuntar hores</a>
      <a href="#/dictar" class="accio"><span>🎤</span>Dictar un pressupost</a>
      <a href="#/feines?nova=1" class="accio"><span>🏗️</span>Nova feina</a>
      <button class="btn" data-tanca>Tanca</button></div>`;
  fons.onclick = (e) => {
    if (e.target.closest("[data-assist]")) { fons.remove(); obreAssistent(feinaActual()); return; }
    if (e.target === fons || e.target.closest("a,[data-tanca]")) fons.remove();
  };
  document.body.appendChild(fons);
}

export function feinaActual() {
  const m = location.hash.match(/^#\/feina\/(\d+)/);
  return m ? +m[1] : null;
}

async function pantallaAcces(configurat) {
  document.getElementById("app").innerHTML = `
    <div class="acces">
      <form class="targeta">
        <h1>${configurat ? "Entra" : "Benvingut/da"}</h1>
        ${configurat ? "" : `<p class="muted">Crea l'usuari administrador. Les dades es guarden només al teu servidor.</p>
          <label>Nom de l'empresa<input name="empresa_nom" autocomplete="organization"></label>
          <label>El teu nom<input name="nom" required></label>`}
        <label>Usuari<input name="usuari" required autocomplete="username" autocapitalize="none"></label>
        <label>Contrasenya<input name="password" type="password" required minlength="8" autocomplete="${configurat ? "current-password" : "new-password"}"></label>
        <button class="btn primari gran">${configurat ? "Entra" : "Crea i entra"}</button>
      </form>
    </div>`;
  const form = document.querySelector(".acces form");
  form.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api(configurat ? "POST" : "POST", configurat ? "/api/login" : "/api/setup", formData(form), { noRedirect: true });
      location.hash = "#/inici";
      location.reload();
    } catch (err) { errorToast(err); }
  };
}

let vistaActual = 0;

async function navega() {
  const hash = location.hash.replace(/^#/, "") || "/inici";
  const [path, query] = hash.split("?");
  if (path === "/login") return;
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  const ruta = RUTES.find(([re]) => re.test(path));
  const vista = document.getElementById("vista");
  if (!vista) return;
  document.querySelectorAll("[data-r]").forEach((a) => {
    const r = path.split("/")[1] || "inici";
    a.classList.toggle("actiu", a.dataset.r === r || (r === "feina" && a.dataset.r === "feines") ||
      (r === "pressupost" && a.dataset.r === "feines") || (r === "factura" && a.dataset.r === "factures"));
  });
  const id = ++vistaActual;
  vista.innerHTML = `<div class="carregant">Carregant…</div>`;
  window.scrollTo(0, 0);
  if (!ruta) { vista.innerHTML = `<p>Pàgina no trobada.</p>`; return; }
  const m = path.match(ruta[0]);
  try {
    await ruta[1](vista, m.slice(1), params, () => id === vistaActual);
  } catch (err) {
    if (id === vistaActual) vista.innerHTML = `<div class="buit"><p>${esc(err.message)}</p></div>`;
  }
}

async function inicia() {
  let estat;
  try { estat = await api("GET", "/api/estat", undefined, { noRedirect: true }); }
  catch (e) { document.getElementById("app").innerHTML = `<p class="buit">No es pot connectar amb el servidor.</p>`; return; }
  if (!estat.usuari) {
    if (location.hash !== "#/login") history.replaceState(null, "", "#/login");
    return pantallaAcces(estat.configurat);
  }
  Object.assign(state, { usuari: estat.usuari, ia: estat.ia, empresa: estat.empresa });
  try {
    state.partides = await get("/api/partides");
    state.usuaris = await get("/api/usuaris");
    state.settings = (await get("/api/config")).settings;
  } catch (e) { errorToast(e); }
  if (location.hash === "#/login" || !location.hash) history.replaceState(null, "", "#/inici");
  layout();
  window.addEventListener("hashchange", navega);
  navega();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
window.addEventListener("unhandledrejection", (e) => { if (e.reason && e.reason.message) toast(e.reason.message, "error"); });
inicia();
