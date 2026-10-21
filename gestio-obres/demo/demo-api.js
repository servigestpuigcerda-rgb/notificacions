// DEMO: simula el servidor dins del navegador amb dades inventades.
// Reprodueix la lògica de l'app real (app/*.py) de manera simplificada. La IA és simulada.
const CLAU = "gestio-obres-demo-v1";
const r2 = (x) => Math.round(((+x || 0) + Number.EPSILON) * 100) / 100;
const ara = () => new Date().toISOString().slice(0, 19);
const avui = () => new Date().toISOString().slice(0, 10);
const dies = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
const eurTxt = (v) => new Intl.NumberFormat("ca-ES", { style: "currency", currency: "EUR" }).format(+v || 0);
const norm = (t) => (t || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
const STOP = new Set("a al als amb de del dels el els en es i la les o per pel pels que un una uns unes fer posa afegeix canvia feina".split(" "));
const paraules = (t) => new Set((norm(t).match(/[a-z0-9]{3,}/g) || []).filter((w) => !STOP.has(w)));
const comunes = (a, b) => [...a].filter((x) => b.has(x)).length;

class Err extends Error { constructor(status, detail) { super(detail); this.status = status; this.detail = detail; } }
const falla = (detail, status = 400) => { throw new Err(status, detail); };

let db;
const fitxers = {}; // id -> dataURL (no es desen si no hi caben)

function buida() {
  return {
    seq: {}, settings: {
      empresa_nom: "Reformes Exemple SL", empresa_nif: "B00000000", empresa_adreca: "Carrer Fictici 1, 17520 Població",
      empresa_telefon: "600 000 000", empresa_email: "info@exemple.cat", empresa_iban: "ES00 0000 0000 0000 0000 0000",
      empresa_bizum: "600000000", gestor_nom: "Gestoria Exemple", gestor_email: "gestor@exemple.cat", regim_fiscal: "autonom",
      irpf_fraccionat_pct: "20", iva_defecte: "21", irpf_defecte: "0", marge_defecte: "25", cost_hora_defecte: "25",
      preu_hora_defecte: "38", serie_factura: "F", validesa_pressupost: "30", venciment_dies: "30",
      condicions_pressupost: "Pressupost vàlid durant el termini indicat. Qualsevol treball no inclòs es comunicarà i pressupostarà a part abans d'executar-lo.",
      ia_activa: "1", ia_model: "simulada",
    },
    usuaris: [], partides: [], clients: [], articles: [], feines: [], pressupostos: [], linies: [], documents: [],
    despeses: [], albarans: [], linies_albara: [], hores: [], factures: [], linies_factura: [], missatges: [],
    apren: {}, planning: [], valoracions: [], renders: [], analisis: [],
  };
}

function desa() {
  try { localStorage.setItem(CLAU, JSON.stringify(db)); } catch { /* sense espai: es manté en memòria */ }
  try { localStorage.setItem(CLAU + "-fitxers", JSON.stringify(fitxers)); } catch { /* fotos només en memòria */ }
}

const id = (t) => (db.seq[t] = (db.seq[t] || 0) + 1);
const nou = (t, o) => { const x = { id: id(t), ...o }; db[t].push(x); return x; };
const troba = (t, i) => db[t].find((x) => x.id === +i);
const cal = (x, msg = "No trobat.") => x || falla(msg, 404);
const sett = (k, d = 0) => { const v = parseFloat(db.settings[k]); return Number.isFinite(v) ? v : d; };
const partida = (i) => db.partides.find((p) => p.id === i);
const client = (i) => db.clients.find((c) => c.id === i);

// ------------------------------------------------------------------ càlculs

const esHora = (l) => /^(h|hora|hores|hr|hrs)\.?$/i.test((l.unitat || "").trim());
const importLinia = (l) => r2((+l.quantitat || 0) * (+l.preu_unitari || 0) * (1 - (+l.descompte_pct || 0) / 100));
const preuArticle = (a) => (a.preu !== null && a.preu !== undefined && a.preu !== "" ? r2(a.preu) : r2(a.cost * (1 + (a.marge_pct ?? sett("marge_defecte", 20)) / 100)));

function totals(pid) {
  const p = troba("pressupostos", pid);
  const linies = db.linies.filter((l) => l.pressupost_id === pid).sort((a, b) => a.ordre - b.ordre).map((l) => ({ ...l }));
  let sub = 0, cost = 0, hores = 0;
  const pp = {};
  for (const l of linies) {
    l.import = importLinia(l); l.cost = r2(l.quantitat * l.cost_unitari);
    sub += l.import; cost += l.cost;
    const part = partida(l.partida_id) || {};
    if (part.tipus === "ma_obra" && esHora(l)) hores += +l.quantitat;
    const k = l.partida_id || 0;
    pp[k] = pp[k] || { partida_id: l.partida_id, nom: part.nom || "Sense partida", tipus: part.tipus, import: 0, cost: 0 };
    pp[k].import = r2(pp[k].import + l.import * (1 - p.descompte_pct / 100)); pp[k].cost = r2(pp[k].cost + l.cost);
  }
  const desc = r2(sub * p.descompte_pct / 100), base = r2(sub - desc);
  const iva = r2(base * p.iva_pct / 100), irpf = r2(base * p.irpf_pct / 100);
  return { linies, subtotal: r2(sub), descompte: desc, base, iva, irpf, total: r2(base + iva - irpf), cost: r2(cost),
    benefici: r2(base - cost), marge_pct: base ? r2((base - cost) / base * 100) : 0, hores: r2(hores), per_partida: Object.values(pp) };
}

function recalculaFactura(fid) {
  const f = troba("factures", fid);
  let base = 0;
  for (const l of db.linies_factura.filter((x) => x.factura_id === fid)) { l.import = importLinia(l); base += l.import; }
  f.base = r2(base); f.iva_import = r2(f.base * f.iva_pct / 100); f.irpf_import = r2(f.base * f.irpf_pct / 100);
  f.total = r2(f.base + f.iva_import - f.irpf_import);
}

const VALIDES = ["esborrany", "emesa", "cobrada"];
function facturat(tipus) {
  const out = {};
  for (const l of db.linies_factura) {
    if (l.origen_tipus !== tipus) continue;
    const f = troba("factures", l.factura_id);
    if (f && VALIDES.includes(f.estat)) out[l.origen_id] = (out[l.origen_id] || 0) + l.import;
  }
  return out;
}

function pendentFacturar(fid) {
  const fl = facturat("linia_pressupost"), fd = facturat("despesa"), fh = facturat("hores");
  const linies = [], despeses = [], hores = [];
  for (const p of db.pressupostos.filter((x) => x.feina_id === fid && x.estat === "acceptat")) {
    for (const l of totals(p.id).linies) {
      const net = r2(l.import * (1 - p.descompte_pct / 100)), fet = r2(fl[l.id] || 0);
      if (net - fet > 0.009) linies.push({ origen_tipus: "linia_pressupost", origen_id: l.id, pressupost: p.numero, pressupost_tipus: p.tipus,
        descripcio: l.descripcio, total: net, facturat: fet, pendent: r2(net - fet), pct_facturat: net ? r2(fet / net * 100) : 0 });
    }
  }
  for (const d of db.despeses.filter((x) => x.feina_id === fid && x.facturable)) {
    const imp = r2(d.base * (1 + d.marge_pct / 100)), fet = r2(fd[d.id] || 0);
    if (imp - fet > 0.009) despeses.push({ origen_tipus: "despesa", origen_id: d.id, descripcio: `${d.concepte || "Material"} (${d.proveidor || ""})`,
      data: d.data, cost: d.base, marge_pct: d.marge_pct, total: imp, facturat: fet, pendent: r2(imp - fet) });
  }
  for (const h of db.hores.filter((x) => x.feina_id === fid && x.facturable)) {
    const imp = r2(h.hores * h.preu_hora), fet = r2(fh[h.id] || 0);
    if (imp - fet > 0.009) hores.push({ origen_tipus: "hores", origen_id: h.id, descripcio: `Mà d'obra ${h.data} ${h.treballador || ""} (${h.hores} h)`,
      hores: h.hores, preu_hora: h.preu_hora, total: imp, facturat: fet, pendent: r2(imp - fet) });
  }
  return { feina: troba("feines", fid), linies_pressupost: linies, despeses, hores,
    total: r2([...linies, ...despeses, ...hores].reduce((s, x) => s + x.pendent, 0)) };
}

function resumFeina(fid) {
  const pres = db.pressupostos.filter((p) => p.feina_id === fid).map((p) => ({ ...p }));
  let contractat = 0, costPrev = 0, horesPrev = 0, pendAcc = 0;
  const prevP = {};
  for (const p of pres) {
    const t = totals(p.id);
    p.totals = { base: t.base, total: t.total, cost: t.cost, benefici: t.benefici, marge_pct: t.marge_pct, hores: t.hores };
    if (p.estat === "acceptat") {
      contractat += t.base; costPrev += t.cost; horesPrev += t.hores;
      for (const x of t.per_partida) { const k = x.partida_id || 0; prevP[k] = (prevP[k] || 0) + x.cost; }
    } else if (p.estat === "enviat") pendAcc += t.base;
  }
  const realP = {};
  for (const d of db.despeses.filter((x) => x.feina_id === fid)) realP[d.partida_id || 0] = (realP[d.partida_id || 0] || 0) + d.base;
  const hs = db.hores.filter((x) => x.feina_id === fid);
  const horesR = hs.reduce((s, h) => s + h.hores, 0), costH = hs.reduce((s, h) => s + h.hores * h.cost_hora, 0);
  const mo = db.partides.find((p) => p.tipus === "ma_obra")?.id || 0;
  realP[mo] = (realP[mo] || 0) + costH;
  const costReal = r2(Object.values(realP).reduce((a, b) => a + b, 0));
  const keys = [...new Set([...Object.keys(prevP), ...Object.keys(realP)].map(Number))].sort((a, b) => (partida(a)?.ordre ?? 99) - (partida(b)?.ordre ?? 99));
  const partides = keys.map((k) => {
    const prev = r2(prevP[k] || 0), real = r2(realP[k] || 0);
    return { partida_id: k || null, nom: partida(k)?.nom || "Sense partida", previst: prev, real, desviacio: r2(real - prev), pct: prev ? r2(real / prev * 100) : null };
  });
  const fs = db.factures.filter((f) => f.feina_id === fid && ["emesa", "cobrada"].includes(f.estat) && !f.rectifica_id);
  const fBase = r2(fs.reduce((s, f) => s + f.base, 0)), fTot = r2(fs.reduce((s, f) => s + f.total, 0));
  const cobrat = r2(fs.filter((f) => f.estat === "cobrada").reduce((s, f) => s + f.total, 0));
  const esb = db.factures.filter((f) => f.feina_id === fid && f.estat === "esborrany");
  const pend = pendentFacturar(fid);
  contractat = r2(contractat); costPrev = r2(costPrev);
  const costRestant = Math.max(costPrev - costReal, 0);
  const alertes = [];
  if (costPrev && costReal > costPrev) alertes.push(`El cost real (${eurTxt(costReal)}) ja supera el cost previst (${eurTxt(costPrev)}).`);
  else if (costPrev && costReal > costPrev * 0.85) alertes.push(`Ja s'ha consumit el ${Math.round(costReal / costPrev * 100)}% del cost previst.`);
  if (horesPrev && horesR > horesPrev) alertes.push(`Hores reals (${horesR} h) per sobre de les pressupostades (${horesPrev} h).`);
  for (const p of partides) if (p.previst && p.real > p.previst * 1.1) alertes.push(`Partida «${p.nom}» desviada un ${Math.round(p.pct - 100)}%.`);
  const sense = db.despeses.filter((d) => d.feina_id === fid && (!d.partida_id || d.estat === "pendent_revisio")).length;
  if (sense) alertes.push(`${sense} despesa(es) pendents de revisar o sense partida.`);
  return {
    contractat, pendent_acceptar: r2(pendAcc), cost_previst: costPrev, cost_real: costReal,
    benefici_previst: r2(contractat - costPrev), marge_previst_pct: contractat ? r2((contractat - costPrev) / contractat * 100) : 0,
    benefici_projectat: r2(fBase + esb.reduce((s, f) => s + f.base, 0) + pend.total - costReal - costRestant),
    resultat_actual: r2(fBase - costReal), hores_previstes: r2(horesPrev), hores_reals: r2(horesR), facturat: fBase, facturat_total: fTot,
    cobrat, pendent_cobrar: r2(fTot - cobrat), pendent_facturar: pend.total, factures_esborrany: esb.length,
    pct_facturat: contractat ? r2(fBase / contractat * 100) : 0, pct_cost: costPrev ? r2(costReal / costPrev * 100) : 0,
    partides, pressupostos: pres, alertes,
  };
}

function bloquejos(fid) {
  const res = [];
  for (const p of db.pressupostos.filter((x) => x.feina_id === fid && x.estat === "enviat")) {
    const t = totals(p.id);
    res.push(p.tipus === "principal"
      ? { tipus: "pressupost", ref_id: p.id, text: `Pendent d'acceptar el pressupost ${p.numero} (${eurTxt(t.total)}). La feina no es pot començar fins que l'accepteu.` }
      : { tipus: "canvi", ref_id: p.id, text: `Pendent d'acceptar els canvis ${p.numero} ${p.titol || ""} (${eurTxt(t.total)}). Aquests treballs no es faran, i si afecten la resta, la feina queda aturada, fins que els accepteu.` });
  }
  for (const f of db.factures.filter((x) => x.feina_id === fid && x.estat === "emesa" && x.bloqueja && !x.rectifica_id))
    res.push({ tipus: "pagament", ref_id: f.id, text: `Pendent de pagament la factura ${f.codi} (${eurTxt(f.total)}). La feina es reprendrà quan rebem l'ingrés.` });
  return res;
}

function pendentClient(fid) {
  const perPagar = db.factures.filter((f) => f.feina_id === fid && f.estat === "emesa").reduce((s, f) => s + f.total, 0);
  const p = db.pressupostos.find((x) => x.feina_id === fid && x.estat === "acceptat");
  const iva = (p ? p.iva_pct - p.irpf_pct : sett("iva_defecte", 21));
  const resta = pendentFacturar(fid).total;
  return { per_pagar: r2(perPagar), per_facturar: r2(resta * (1 + iva / 100)), total: r2(perPagar + resta * (1 + iva / 100)) };
}

function periode(any, tri) {
  if (!tri) return [`${any}-01-01`, `${any + 1}-01-01`];
  const m = (tri - 1) * 3 + 1;
  return [`${any}-${String(m).padStart(2, "0")}-01`, tri === 4 ? `${any + 1}-01-01` : `${any}-${String(m + 3).padStart(2, "0")}-01`];
}

function resumImpostos(any, tri) {
  const [ini, fi] = periode(any, tri);
  const agrupa = (llista, camps) => {
    const g = {};
    for (const x of llista) {
      const k = x.iva_pct; g[k] = g[k] || { iva_pct: k, base: 0, iva: 0, irpf: 0, n: 0 };
      g[k].base = r2(g[k].base + x.base); g[k].iva = r2(g[k].iva + (x.iva_import || 0)); g[k].irpf = r2(g[k].irpf + (x.irpf_import || 0)); g[k].n++;
    }
    return Object.values(g);
  };
  const em = db.factures.filter((f) => ["emesa", "cobrada", "anullada"].includes(f.estat) && f.numero && f.data >= ini && f.data < fi);
  const de = db.despeses.filter((d) => d.data >= ini && d.data < fi);
  const rep = agrupa(em), sup = agrupa(de);
  const ivaR = r2(rep.reduce((s, x) => s + x.iva, 0)), ivaS = r2(sup.reduce((s, x) => s + x.iva, 0));
  const ing = r2(rep.reduce((s, x) => s + x.base, 0)), desp = r2(sup.reduce((s, x) => s + x.base, 0));
  const senseNif = de.filter((d) => d.tipus_doc === "tiquet" && !d.proveidor_nif);
  return { periode: { inici: ini, fi, any, trimestre: tri }, repercutit: rep, suportat: sup, iva_repercutit: ivaR, iva_suportat: ivaS,
    resultat_iva: r2(ivaR - ivaS), retencions_irpf: r2(rep.reduce((s, x) => s + x.irpf, 0)), ingressos: ing, despeses: desp,
    cost_ma_obra_intern: 0, rendiment: r2(ing - desp),
    avis_tiquets: senseNif.length ? `${senseNif.length} tiquet(s) sense NIF del proveïdor: només és deduïble l'IVA de factures completes o simplificades amb les dades del destinatari.` : null };
}

function estimacio(any, tri) {
  const real = resumImpostos(any, tri);
  const ini = new Date(real.periode.inici), fi = new Date(real.periode.fi), ara_ = new Date(avui());
  const total = Math.round((fi - ini) / 864e5), passats = Math.min(Math.max(Math.round((ara_ - ini) / 864e5) + 1, 0), total);
  const enCurs = passats > 0 && passats < total, factor = enCurs ? total / passats : 1;
  const pct = sett("irpf_fraccionat_pct", 20);
  const acum = (fins) => {
    const [, f] = periode(any, fins);
    const r = resumImpostos(any, null);
    const em = db.factures.filter((x) => ["emesa", "cobrada", "anullada"].includes(x.estat) && x.numero && x.data >= `${any}-01-01` && x.data < f);
    const de = db.despeses.filter((x) => x.data >= `${any}-01-01` && x.data < f);
    void r;
    return { ing: em.reduce((s, x) => s + x.base, 0), desp: de.reduce((s, x) => s + x.base, 0), ret: em.reduce((s, x) => s + x.irpf_import, 0) };
  };
  const q130 = (t, proj = 1) => {
    const a = acum(t);
    const q = proj !== 1 ? { ing: real.ingressos * (proj - 1), desp: real.despeses * (proj - 1) } : { ing: 0, desp: 0 };
    let ant = 0; for (let i = 1; i < t; i++) ant += Math.max(q130(i), 0);
    return r2(Math.max(((a.ing + q.ing) - (a.desp + q.desp)) * pct / 100 - a.ret - ant, 0));
  };
  const esb = db.factures.filter((f) => f.estat === "esborrany");
  const res = { any, trimestre: tri, regim: db.settings.regim_fiscal, en_curs: enCurs, dies: { transcorreguts: passats, total },
    real: { iva_repercutit: real.iva_repercutit, iva_suportat: real.iva_suportat, iva_resultat: real.resultat_iva, ingressos: real.ingressos, despeses: real.despeses, retencions: real.retencions_irpf },
    projeccio: { iva_repercutit: r2(real.iva_repercutit * factor), iva_suportat: r2(real.iva_suportat * factor), iva_resultat: r2(real.resultat_iva * factor),
      ingressos: r2(real.ingressos * factor), despeses: r2(real.despeses * factor) },
    esborranys: { n: esb.length, base: r2(esb.reduce((s, f) => s + f.base, 0)), iva: r2(esb.reduce((s, f) => s + f.iva_import, 0)) },
    avis_tiquets: real.avis_tiquets };
  if (res.regim === "autonom") { res.real.irpf_130 = q130(tri); res.projeccio.irpf_130 = enCurs ? q130(tri, factor) : res.real.irpf_130; res.irpf_pct = pct; }
  return res;
}

// --------------------------------------------------------- aprenentatge

function desviacions(tipus) {
  const mostres = [];
  for (const f of db.feines.filter((x) => ["acabada", "tancada"].includes(x.estat) && (!tipus || norm(x.tipus) === norm(tipus)))) {
    if (!db.pressupostos.some((p) => p.feina_id === f.id && p.estat === "acceptat")) continue;
    const r = resumFeina(f.id);
    const matP = r.partides.filter((p) => partida(p.partida_id)?.tipus !== "ma_obra").reduce((s, p) => s + p.previst, 0);
    const matR = r.partides.filter((p) => partida(p.partida_id)?.tipus !== "ma_obra").reduce((s, p) => s + p.real, 0);
    mostres.push({ ratio_hores: r.hores_previstes ? r.hores_reals / r.hores_previstes : null, ratio_material: matP ? matR / matP : null,
      marge_real_pct: r.contractat ? (r.contractat - r.cost_real) / r.contractat * 100 : null });
  }
  const mitj = (k) => { const v = mostres.map((m) => m[k]).filter((x) => x !== null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  return { tipus, feines: mostres.length, ratio_hores: mitj("ratio_hores") && r2(mitj("ratio_hores")), ratio_material: mitj("ratio_material") && r2(mitj("ratio_material")),
    marge_real_mitja: mitj("marge_real_pct") !== null ? r2(mitj("marge_real_pct")) : null };
}

function semblants(text, tipus, excl) {
  const obj = paraules(text + " " + (tipus || ""));
  const res = [];
  for (const p of db.pressupostos.filter((x) => ["acceptat", "enviat"].includes(x.estat) && x.id !== excl)) {
    const f = troba("feines", p.feina_id);
    const t = totals(p.id);
    const bossa = paraules([p.titol, f.nom, ...t.linies.map((l) => l.descripcio)].join(" "));
    const c = comunes(obj, bossa);
    if (!c) continue;
    const punts = c / Math.sqrt(obj.size * Math.max(bossa.size, 1)) + (tipus && norm(f.tipus) === norm(tipus) ? 0.15 : 0);
    const real = ["acabada", "tancada"].includes(f.estat) ? resumFeina(f.id) : null;
    res.push({ id: p.id, numero: p.numero, titol: p.titol || f.nom, tipus: f.tipus, similitud: r2(punts), base: t.base, hores: t.hores, cost: t.cost,
      hores_reals: real ? real.hores_reals : null, cost_real: real ? real.cost_real : null });
  }
  return res.sort((a, b) => b.similitud - a.similitud).slice(0, 3);
}

function revisar(pid) {
  const p = troba("pressupostos", pid), f = troba("feines", p.feina_id), t = totals(pid);
  const margeMin = sett("marge_defecte", 20) / 2, av = [];
  const add = (nivell, text) => av.push({ nivell, text });
  if (!t.linies.length) add("error", "El pressupost no té cap línia.");
  t.linies.forEach((l, i) => {
    const nom = `Línia ${i + 1} «${l.descripcio.slice(0, 40)}»`;
    if (l.quantitat <= 0) add("error", `${nom}: quantitat zero o negativa.`);
    if (l.preu_unitari <= 0) add("error", `${nom}: sense preu.`);
    else if (l.cost_unitari && l.preu_unitari * (1 - l.descompte_pct / 100) < l.cost_unitari) add("error", `${nom}: es ven per sota de cost.`);
    else if (l.cost_unitari && (l.preu_unitari * (1 - l.descompte_pct / 100) - l.cost_unitari) / l.preu_unitari * 100 < margeMin) add("avis", `${nom}: marge molt baix.`);
    if (!l.cost_unitari) add("avis", `${nom}: sense cost; no es podrà controlar el benefici.`);
  });
  if (t.linies.length && !t.linies.some((l) => partida(l.partida_id)?.tipus === "ma_obra")) add("avis", "No hi ha cap línia de mà d'obra. És correcte?");
  let hist = desviacions(f.tipus), origen = `feines de tipus «${f.tipus}»`;
  if (hist.feines < 1) { hist = desviacions(); origen = "totes les feines acabades"; }
  if (hist.feines >= 1) {
    if (hist.ratio_hores > 1.05 && t.hores) add("avis", `Anem curts d'hores: a les ${origen} les hores reals han estat un ${Math.round((hist.ratio_hores - 1) * 100)}% més de les pressupostades. Caldrien ~${r2(t.hores * hist.ratio_hores)} h (+${r2(t.hores * (hist.ratio_hores - 1))} h).`);
    const mat = t.per_partida.filter((x) => x.tipus !== "ma_obra").reduce((s, x) => s + x.cost, 0);
    if (hist.ratio_material > 1.05 && mat) add("avis", `Anem curts de material: a les ${origen} el material real ha costat un ${Math.round((hist.ratio_material - 1) * 100)}% més del previst. Cost previst ${Math.round(mat)} € → probable ${Math.round(mat * hist.ratio_material)} €.`);
    if (hist.marge_real_mitja !== null) add("info", `Marge real mitjà de l'historial: ${hist.marge_real_mitja}% (aquest pressupost: ${t.marge_pct}%).`);
  } else add("info", "Encara no hi ha prou feines acabades per comparar amb l'historial.");
  for (const a of db.analisis.filter((x) => norm(troba("feines", x.feina_id)?.tipus) === norm(f.tipus)).slice(-2))
    for (const pr of a.text.propostes.slice(0, 2)) add("info", `Lliçó d'una feina anterior: ${pr}`);
  return { avisos: av, historial: { ...hist, origen }, semblants: semblants([p.titol, f.nom, ...t.linies.map((l) => l.descripcio)].join(" "), f.tipus, pid),
    totals: { base: t.base, cost: t.cost, benefici: t.benefici, marge_pct: t.marge_pct, hores: t.hores, total: t.total } };
}

function analisiFeina(fid) {
  const f = troba("feines", fid), r = resumFeina(fid);
  const principal = r.pressupostos.filter((p) => p.estat === "acceptat" && p.tipus === "principal").reduce((s, p) => s + p.totals.base, 0);
  const extres = r.pressupostos.filter((p) => p.estat === "acceptat" && p.tipus === "extra");
  const extresImp = extres.reduce((s, p) => s + p.totals.base, 0);
  const margeReal = r.contractat ? r2((r.contractat - r.cost_real) / r.contractat * 100) : null;
  const vals = db.valoracions.filter((v) => v.feina_id === fid);
  const be = [], mal = [], prop = [], tipus = f.tipus || "aquest tipus";
  if (margeReal !== null) (margeReal >= r.marge_previst_pct - 2 ? be : mal).push(`Marge real ${margeReal}% (previst ${r.marge_previst_pct}%).`);
  if (r.hores_previstes) {
    const dh = (r.hores_reals / r.hores_previstes - 1) * 100;
    if (dh > 10) { mal.push(`Hores reals un ${Math.round(dh)}% per sobre de les pressupostades (${r.hores_reals} h vs ${r.hores_previstes} h).`); prop.push(`En feines de ${tipus}, pressuposta un ${Math.round(dh)}% més d'hores de mà d'obra.`); }
    else if (dh < -10) be.push(`S'han fet un ${Math.round(-dh)}% menys d'hores de les previstes.`);
    else be.push("Les hores s'han ajustat al pressupost.");
  }
  for (const p of r.partides) {
    if (p.previst && p.pct > 110) { mal.push(`Partida «${p.nom}» desviada un ${Math.round(p.pct - 100)}% (+${eurTxt(p.desviacio)}).`); prop.push(`Revisa l'amidament i els preus de «${p.nom}» en feines de ${tipus}.`); }
    else if (!p.previst && p.real > 50) { mal.push(`Cost no previst a «${p.nom}»: ${eurTxt(p.real)}.`); prop.push(`Inclou la partida «${p.nom}» als pressupostos de ${tipus}.`); }
  }
  if (principal && extresImp / principal > 0.1) { mal.push(`Treballs fora de pressupost per ${eurTxt(extresImp)} (${Math.round(extresImp / principal * 100)}% del principal).`); prop.push("Fes una visita i un amidament més detallats abans de pressupostar."); }
  else if (extres.length) be.push(`Els canvis (${extres.length}) s'han pressupostat i acceptat abans de fer-los.`);
  if (r.pendent_facturar > 0.01) mal.push(`S'ha tancat amb ${eurTxt(r.pendent_facturar)} per facturar.`);
  if (vals.length) { const m = vals.reduce((s, v) => s + v.puntuacio, 0) / vals.length; (m >= 4 ? be : mal).push(`Valoració del client: ${r2(m)}/5.`); }
  return { feina: { codi: f.codi, nom: f.nom, tipus: f.tipus }, xifres: { contractat: r.contractat, principal: r2(principal), extres: r2(extresImp), n_extres: extres.length,
    cost_previst: r.cost_previst, cost_real: r.cost_real, marge_previst_pct: r.marge_previst_pct, marge_real_pct: margeReal, hores_previstes: r.hores_previstes,
    hores_reals: r.hores_reals, facturat: r.facturat, cobrat: r.cobrat, pendent_facturar: r.pendent_facturar,
    durada_dies: f.data_inici && f.data_fi ? Math.round((new Date(f.data_fi) - new Date(f.data_inici)) / 864e5) + 1 : null,
    dies_cobrament: null, valoracio: vals.length ? r2(vals.reduce((s, v) => s + v.puntuacio, 0) / vals.length) : null },
    partides: r.partides, comentaris_client: vals.map((v) => v.comentari).filter(Boolean), be, malament: mal, propostes: prop };
}

function generaAnalisi(fid) {
  const dades = analisiFeina(fid);
  const xf = dades.xifres;
  const resum = `Feina ${xf.marge_real_pct !== null && xf.marge_real_pct >= xf.marge_previst_pct - 2 ? "rendible i dins de pressupost" : "amb menys marge del previst"}: cost real ${eurTxt(xf.cost_real)} sobre ${eurTxt(xf.contractat)} contractats. (Anàlisi simulada a la demo.)`;
  const text = { resum, be: dades.be, malament: dades.malament, propostes: dades.propostes, font: "ia" };
  db.analisis.push({ id: id("analisis"), feina_id: fid, dades, text, created_at: ara() });
  return { dades, text };
}

// --------------------------------------------------------------- utilitats

function missatge(fid, text, tipus = "missatge", autor = "sistema", intern = false, extra = {}) {
  nou("missatges", { feina_id: fid, autor, tipus, text, intern: intern ? 1 : 0, llegit: autor === "client" ? 0 : 1, created_at: ara(), document_id: null, ...extra });
}

function seguentCodi(prefix, llista, camp) {
  const pref = `${prefix}${new Date().getFullYear()}-`;
  let n = 0;
  for (const x of llista) if ((x[camp] || "").startsWith(pref)) n = Math.max(n, parseInt(x[camp].slice(pref.length)) || 0);
  return prefix ? `${pref}${String(n + 1).padStart(4, "0")}` : `${pref}${String(n + 1).padStart(3, "0")}`;
}

const num = (v, d = null) => { if (v === "" || v === null || v === undefined) return d; const n = parseFloat(String(v).replace(",", ".")); return Number.isFinite(n) ? n : d; };
const bool = (v) => (v === true || v === 1 || v === "1" || v === "true" || v === "on" ? 1 : 0);
const token = () => Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) => b.toString(16).padStart(2, "0")).join("");

async function llegeixFitxer(file) {
  return new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(file); });
}

async function guardaFitxer(file, feina_id, tipus) {
  const d = nou("documents", { feina_id: feina_id ? +feina_id : null, tipus, nom: file.name || "document", mime: file.type, mida: file.size,
    visible_client: 0, created_at: ara(), text_extret: "" });
  fitxers[d.id] = await llegeixFitxer(file);
  return d;
}

// ------------------------------------------------------------------ rutes

const R = [];
const ruta = (m, patro, fn) => R.push([m, new RegExp("^" + patro.replace(/:(\w+)/g, "(?<$1>[^/]+)") + "$"), fn]);

const usuariDemo = () => db.usuaris[0];

ruta("GET", "/api/estat", () => ({ configurat: true, usuari: usuariDemo(), ia: true, empresa: db.settings.empresa_nom }));
ruta("POST", "/api/logout", () => ({ ok: true }));
ruta("GET", "/api/config", () => ({ settings: db.settings, partides: db.partides, usuaris: db.usuaris, ia: true }));
ruta("PUT", "/api/config", (_, __, b) => { for (const k of Object.keys(b)) if (k in db.settings) db.settings[k] = String(b[k]); return { settings: db.settings, partides: db.partides, usuaris: db.usuaris, ia: true }; });
ruta("GET", "/api/partides", () => db.partides);
ruta("POST", "/api/partides", (_, __, b) => ({ id: nou("partides", { nom: b.nom, tipus: b.tipus || "material", ordre: 50 }).id }));
ruta("GET", "/api/usuaris", () => db.usuaris);
ruta("POST", "/api/usuaris", (_, __, b) => ({ id: nou("usuaris", { nom: b.nom, usuari: b.usuari, rol: b.rol || "treballador", cost_hora: num(b.cost_hora, 0), preu_hora: num(b.preu_hora, 0), actiu: 1 }).id }));
ruta("PUT", "/api/usuaris/:id", ({ id: i }, __, b) => { Object.assign(cal(troba("usuaris", i)), { nom: b.nom, rol: b.rol, cost_hora: num(b.cost_hora, 0), preu_hora: num(b.preu_hora, 0), actiu: bool(b.actiu) }); return { ok: true }; });

// clients
ruta("GET", "/api/clients", (_, q) => db.clients.filter((c) => norm(c.nom + c.telefon + c.nif).includes(norm(q.q || ""))).map((c) => ({ ...c, feines: db.feines.filter((f) => f.client_id === c.id).length })));
ruta("POST", "/api/clients", (_, __, b) => { if (!b.nom) falla("Cal el nom del client."); return { id: nou("clients", { ...pickC(b), created_at: ara() }).id }; });
ruta("PUT", "/api/clients/:id", ({ id: i }, __, b) => { Object.assign(cal(troba("clients", i)), pickC(b)); return { ok: true }; });
ruta("DELETE", "/api/clients/:id", ({ id: i }) => { if (db.feines.some((f) => f.client_id === +i)) falla("El client té feines; no es pot esborrar."); db.clients = db.clients.filter((c) => c.id !== +i); return { ok: true }; });
function pickC(b) { return { nom: b.nom, nif: b.nif, email: b.email, telefon: b.telefon, adreca: b.adreca, notes: b.notes }; }

// articles
const articleOut = (a) => ({ ...a, preu_venda: preuArticle(a), preu_net: r2(preuArticle(a) * (1 - (a.descompte_pct || 0) / 100)) });
const pickA = (b) => ({ codi: b.codi, nom: b.nom, unitat: b.unitat || "u", partida_id: num(b.partida_id), cost: num(b.cost, 0), marge_pct: num(b.marge_pct),
  preu: num(b.preu), descompte_pct: num(b.descompte_pct, 0), proveidor: b.proveidor, notes: b.notes });
ruta("GET", "/api/articles", (_, q) => db.articles.filter((a) => a.actiu && norm(a.nom + a.codi + a.proveidor).includes(norm(q.q || ""))).map(articleOut));
ruta("POST", "/api/articles", (_, __, b) => { if (!b.nom) falla("Cal el nom de l'article."); return { id: nou("articles", { ...pickA(b), actiu: 1 }).id }; });
ruta("PUT", "/api/articles/:id", ({ id: i }, __, b) => { Object.assign(cal(troba("articles", i)), pickA(b)); return { ok: true }; });
ruta("DELETE", "/api/articles/:id", ({ id: i }) => { troba("articles", i).actiu = 0; return { ok: true }; });
ruta("POST", "/api/articles/aplicar", (_, __, b) => {
  let ids = (b.ids || []).map(Number);
  if (b.partida_id) ids = ids.concat(db.articles.filter((a) => a.partida_id === +b.partida_id).map((a) => a.id));
  if (!ids.length) falla("No hi ha cap article seleccionat.");
  for (const i of new Set(ids)) { const a = troba("articles", i); if (b.marge_pct !== "" && b.marge_pct != null) { a.marge_pct = num(b.marge_pct); a.preu = null; } if (b.descompte_pct !== "" && b.descompte_pct != null) a.descompte_pct = num(b.descompte_pct); }
  return { actualitzats: new Set(ids).size };
});

// feines
const CAMPS_FEINA = ["nom", "client_id", "adreca", "tipus", "estat", "mode_facturacio", "data_inici", "data_fi", "notes"];
const miniResum = (r) => Object.fromEntries(["contractat", "cost_previst", "cost_real", "facturat", "pendent_facturar", "pct_cost", "pct_facturat", "hores_reals", "hores_previstes", "benefici_projectat", "pendent_acceptar"].map((k) => [k, r[k]]));
ruta("GET", "/api/feines", (_, q) => {
  let fs = db.feines.map((f) => ({ ...f, client_nom: client(f.client_id)?.nom || null }));
  if (q.estat === "actives") fs = fs.filter((f) => ["pressupost", "acceptada", "en_curs", "acabada"].includes(f.estat));
  else if (q.estat) fs = fs.filter((f) => f.estat === q.estat);
  if (q.q) fs = fs.filter((f) => norm(f.nom + f.codi + f.client_nom + f.adreca).includes(norm(q.q)));
  return fs.reverse().map((f) => { const r = resumFeina(f.id); return { ...f, resum: miniResum(r), n_alertes: r.alertes.length }; });
});
function creaFeina(b) {
  if (!b.nom) falla("Cal un nom per a la feina.");
  const d = {};
  for (const k of CAMPS_FEINA) if (k in b) d[k] = k === "client_id" ? num(b[k]) : b[k];
  if (b.client_nou && b.client_nou.nom) d.client_id = nou("clients", { ...pickC(b.client_nou), created_at: ara() }).id;
  const f = nou("feines", { estat: "pressupost", mode_facturacio: "pressupost", ...d, codi: seguentCodi("", db.feines, "codi"), token: token(), created_at: ara() });
  missatge(f.id, `S'ha obert la feina ${f.codi}: ${f.nom}.`, "nota", "sistema", true);
  return { id: f.id, codi: f.codi };
}
ruta("POST", "/api/feines", (_, __, b) => creaFeina(b));
ruta("GET", "/api/feines/:id", ({ id: i }) => {
  const f = cal(troba("feines", i), "Feina no trobada.");
  const vals = db.valoracions.filter((v) => v.feina_id === f.id);
  return { ...f, client: client(f.client_id) || null, resum: resumFeina(f.id), no_llegits: db.missatges.filter((m) => m.feina_id === f.id && !m.llegit).length,
    bloquejos: bloquejos(f.id), valoracio: { n: vals.length, mitjana: vals.length ? vals.reduce((s, v) => s + v.puntuacio, 0) / vals.length : null } };
});
ruta("PUT", "/api/feines/:id", ({ id: i }, __, b) => { const f = cal(troba("feines", i)); for (const k of CAMPS_FEINA) if (k in b) f[k] = k === "client_id" ? num(b[k]) : b[k]; return { ok: true }; });
function tancaFeina(fid, forcar) {
  const f = troba("feines", fid), r = resumFeina(fid);
  if (r.pendent_facturar > 0.01 && !forcar) falla(`Encara queden ${eurTxt(r.pendent_facturar)} per facturar.`);
  Object.assign(f, { estat: "tancada", tancada_at: ara(), data_fi: f.data_fi || avui() });
  missatge(fid, "Hem donat la feina per acabada i tancada. Gràcies per confiar en nosaltres! Si detecteu qualsevol cosa, escriviu-nos per aquí.", "tancament", "empresa");
  generaAnalisi(fid);
}
ruta("POST", "/api/feines/:id/tancar", ({ id: i }, __, b) => { tancaFeina(+i, b.forcar); return { ok: true }; });

// pressupostos
function guardaLinies(pid, linies) {
  db.linies = db.linies.filter((l) => l.pressupost_id !== pid);
  linies.forEach((l, i) => {
    if (!l.descripcio) return;
    const d = { pressupost_id: pid, ordre: i, article_id: num(l.article_id), partida_id: num(l.partida_id), descripcio: l.descripcio, quantitat: num(l.quantitat, 1),
      unitat: l.unitat || "u", cost_unitari: num(l.cost_unitari, 0), marge_pct: num(l.marge_pct, 0), preu_unitari: num(l.preu_unitari, 0),
      descompte_pct: num(l.descompte_pct, 0), referencia: l.referencia || null, foto_document_id: num(l.foto_document_id) };
    if (!d.preu_unitari && d.cost_unitari) d.preu_unitari = r2(d.cost_unitari * (1 + d.marge_pct / 100));
    if (d.preu_unitari && d.cost_unitari && !l.marge_pct) d.marge_pct = r2((d.preu_unitari / d.cost_unitari - 1) * 100);
    nou("linies", d);
  });
}
function creaPressupost(fid, b = {}) {
  const f = cal(troba("feines", fid));
  const tipus = b.tipus === "extra" ? "extra" : "principal";
  let numero = seguentCodi("P", db.pressupostos, "numero"); if (tipus === "extra") numero += "-E";
  const p = nou("pressupostos", { feina_id: f.id, numero, tipus, titol: b.titol || "", estat: "esborrany", data: b.data || avui(), validesa_dies: 30,
    descompte_pct: num(b.descompte_pct, 0), iva_pct: num(b.iva_pct, sett("iva_defecte", 21)), irpf_pct: num(b.irpf_pct, 0), notes: b.notes || "",
    condicions: b.condicions || db.settings.condicions_pressupost, text_origen: b.text_origen || null, created_at: ara() });
  if (b.tipus_feina && !f.tipus) f.tipus = b.tipus_feina;
  guardaLinies(p.id, b.linies || []);
  return { id: p.id, numero };
}
const detallP = (i) => {
  const p = cal(troba("pressupostos", i)), f = troba("feines", p.feina_id), c = client(f.client_id);
  return { ...p, totals: totals(p.id), feina: { id: f.id, codi: f.codi, nom: f.nom, tipus: f.tipus, token: f.token, client_nom: c?.nom, client_telefon: c?.telefon, client_email: c?.email } };
};
const editable = (p) => { if (p.estat === "acceptat") falla("El pressupost ja està acceptat. Per a canvis, crea un pressupost «fora de pressupost»."); };
ruta("POST", "/api/feines/:id/pressupostos", ({ id: i }, __, b) => creaPressupost(+i, b));
ruta("GET", "/api/pressupostos/:id", ({ id: i }) => detallP(i));
function actualitzaP(i, b) {
  const p = cal(troba("pressupostos", i)); editable(p);
  for (const k of ["titol", "data", "notes", "condicions", "text_origen"]) if (k in b) p[k] = b[k];
  for (const k of ["validesa_dies", "descompte_pct", "iva_pct", "irpf_pct"]) if (k in b) p[k] = num(b[k], 0);
  if (["enviat", "rebutjat"].includes(p.estat)) p.estat = "esborrany";
  if (b.linies) guardaLinies(p.id, b.linies);
  return detallP(i);
}
ruta("PUT", "/api/pressupostos/:id", ({ id: i }, __, b) => actualitzaP(i, b));
ruta("DELETE", "/api/pressupostos/:id", ({ id: i }) => { const p = cal(troba("pressupostos", i)); if (p.estat !== "esborrany") falla("Només es poden esborrar esborranys."); db.pressupostos = db.pressupostos.filter((x) => x !== p); return { ok: true }; });
ruta("POST", "/api/pressupostos/:id/duplicar", ({ id: i }, __, b) => {
  const p = cal(troba("pressupostos", i));
  return creaPressupost(+(b.feina_id || p.feina_id), { ...p, titol: `${p.titol || ""} (còpia)`, linies: totals(p.id).linies });
});
function enviaP(i) {
  const p = cal(troba("pressupostos", i)); editable(p);
  const t = totals(p.id); if (!t.linies.length) falla("El pressupost no té línies.");
  Object.assign(p, { estat: "enviat", enviat_at: ara() });
  const text = p.tipus === "extra" ? `AVÍS DE TREBALL FORA DE PRESSUPOST (${p.numero}): ${p.titol || ""}. Import ${eurTxt(t.total)} (IVA inclòs). Cal la vostra conformitat abans de fer-lo.`
    : `Us hem enviat el pressupost ${p.numero} ${p.titol || ""} per ${eurTxt(t.total)} (IVA inclòs).`;
  missatge(p.feina_id, text, p.tipus === "extra" ? "fora_pressupost" : "pressupost", "empresa");
  return { ok: true, token: troba("feines", p.feina_id).token, text };
}
function acceptaP(p, per, autor) {
  const t = totals(p.id);
  Object.assign(p, { estat: "acceptat", acceptat_at: ara(), acceptat_per: per });
  const f = troba("feines", p.feina_id); if (f.estat === "pressupost") f.estat = "acceptada";
  missatge(p.feina_id, `Pressupost ${p.numero} ACCEPTAT per ${per} (${eurTxt(t.total)}).`, "acceptacio", autor);
}
ruta("POST", "/api/pressupostos/:id/enviar", ({ id: i }) => enviaP(i));
ruta("POST", "/api/pressupostos/:id/acceptar", ({ id: i }, __, b) => { const p = cal(troba("pressupostos", i)); editable(p); acceptaP(p, b.per || "el client", "empresa"); return { ok: true }; });
ruta("POST", "/api/pressupostos/:id/rebutjar", ({ id: i }, __, b) => { const p = cal(troba("pressupostos", i)); Object.assign(p, { estat: "rebutjat", rebutjat_motiu: b.motiu }); missatge(p.feina_id, `Pressupost ${p.numero} rebutjat. ${b.motiu || ""}`, "rebuig"); return { ok: true }; });
ruta("GET", "/api/pressupostos/:id/revisio", ({ id: i }) => revisar(+i));
ruta("POST", "/api/pressupostos/:id/revisio-ia", ({ id: i }) => {
  const r = revisar(+i);
  return { resum: `Revisió simulada (demo): marge del ${r.totals.marge_pct}% i ${r.totals.hores} h de mà d'obra.`,
    avisos: r.avisos.filter((a) => a.nivell !== "info").map((a) => a.text),
    suggeriments: ["Afegeix una partida de protecció i neteja d'obra si no hi és.", "Inclou la retirada de runa i el contenidor.", "Revisa si cal petit material (silicona, cola, cargoleria)."] };
});
ruta("POST", "/api/pressupostos/:id/foto", async ({ id: i }, __, b) => {
  const p = cal(troba("pressupostos", i));
  const d = await guardaFitxer(b.get("fitxer"), p.feina_id, "material"); d.visible_client = 1;
  return { document_id: d.id };
});
ruta("GET", "/api/semblants", (_, q) => semblants(q.text || "", q.tipus));

// IA simulada
ruta("POST", "/api/ia/pressupost", (_, __, b) => propostaSimulada(b.text || "", b.tipus));
ruta("POST", "/api/ia/document", async (_, __, b) => {
  const file = b.get("fitxer"), fid = num(b.get("feina_id"));
  const d = await guardaFitxer(file, fid, "tiquet");
  const mat = db.partides.find((p) => p.tipus === "material");
  const total = r2(35 + Math.random() * 120);
  const dades = { tipus_doc: "tiquet", proveidor: "Magatzem Exemple", proveidor_nif: "B11111111", num_document: `T-${Math.floor(Math.random() * 90000) + 10000}`,
    data: avui(), concepte: "Material de lampisteria i fixacions", linies: [{ descripcio: "Tub multicapa 16 mm", quantitat: 10, import_linia: r2(total * 0.6) },
      { descripcio: "Colzes i maneguets", quantitat: 6, import_linia: r2(total * 0.4) }], base: r2(total / 1.21), iva_pct: 21, iva_import: r2(total - total / 1.21),
    total, partida_id: mat?.id, feina_id: fid || db.feines.find((f) => f.estat === "en_curs")?.id || null, ia_confianca: 0.86,
    avisos: ["DEMO: aquestes dades són d'exemple. A la versió real, la IA llegeix el tiquet de la foto."] };
  d.nom = `Magatzem Exemple ${dades.num_document}`;
  return { document_id: d.id, dades, error: null };
});

function propostaSimulada(text, tipus) {
  if (text.trim().length < 10) falla("Explica una mica més la feina per poder fer el pressupost.", 422);
  const t = norm(text), mo = db.partides.find((p) => p.tipus === "ma_obra").id, mat = db.partides.find((p) => p.tipus === "material").id;
  const runa = db.partides.find((p) => /runa/i.test(p.nom))?.id || mat;
  const m2 = (() => { const m = t.match(/(\d+[.,]?\d*)\s*(m2|metres quadrats|m²)/); if (m) return num(m[1]); const d = t.match(/(\d+[.,]?\d*)\s*(?:x|per)\s*(\d+[.,]?\d*)/); return d ? r2(num(d[1]) * num(d[2])) : null; })();
  const L = (descripcio, partida, quantitat, unitat, cost, preu, just) => ({ descripcio, partida: partida === mo ? "Mà d'obra" : partida === runa ? partida && db.partides.find((p) => p.id === runa).nom : "Material", partida_id: partida, quantitat: r2(quantitat), unitat, cost_unitari: cost, preu_unitari: preu, justificacio: just, article_id: null });
  let titol = "Treballs de reforma", linies = [], tip = tipus;
  if (/bany|dutxa|lavabo|banyera/.test(t)) {
    const s = m2 || 4.5; tip = tip || "bany"; titol = "Reforma de bany";
    linies = [L("Protecció d'elements i neteja d'obra", mo, 3, "h", 25, 38, "Habitual en banys"),
      L("Enderroc de revestiments, sanitaris i retirada de runa", mo, 10, "h", 25, 38, `Bany de ~${s} m2`),
      L("Contenidor de runa i gestió de residus", runa, 1, "u", 180, 230),
      L("Instal·lació nova d'aigua i desguassos", mo, 12, "h", 25, 38),
      L("Material de lampisteria", mat, 1, "pa", 260, 340),
      L("Enrajolat de parets i terra", mo, Math.round(s * 4.2), "h", 25, 38, "~4,2 h per m2 de terra"),
      L("Rajola porcellànica (inclou 10% de mermes)", mat, r2(s * 3.3), "m2", 18, 24.3),
      L("Morter cola i material d'agafament", mat, 1, "pa", 90, 120)];
    if (/dutxa|plat/.test(t)) linies.push(L("Plat de dutxa extraplà 140x80", mat, 1, "u", 160, 208), L("Mampara de vidre", mat, 1, "u", 280, 364));
    linies.push(L("Col·locació de sanitaris i aixetes", mo, 6, "h", 25, 38));
  } else if (/cuina/.test(t)) {
    tip = tip || "cuina"; titol = "Reforma de cuina";
    linies = [L("Enderroc i retirada de mobles antics", mo, 8, "h", 25, 38), L("Instal·lació elèctrica i endolls de cuina", mo, 10, "h", 25, 38),
      L("Material elèctric", mat, 1, "pa", 220, 290), L("Muntatge de mobles de cuina", mo, 14, "h", 25, 38), L("Taulell porcellànic", mat, 3.2, "ml", 180, 240)];
  } else {
    const s = m2 || 80; tip = tip || (/pint/.test(t) ? "pintura" : "reparació"); titol = /pint/.test(t) ? "Pintura" : "Treballs";
    linies = [L("Protecció de mobles i terres", mo, 3, "h", 25, 38), L("Preparació de parets (plastecs i lijat)", mo, r2(s * 0.12), "h", 25, 38),
      L("Pintura plàstica, dues mans", mo, r2(s * 0.18), "h", 25, 38), L("Pintura i material", mat, r2(s * 0.3), "l", 4.5, 6.2)];
  }
  const hist = desviacions(tip);
  const avisos = ["DEMO: proposta simulada amb plantilles. A la versió real la prepara la IA amb el catàleg i l'historial."];
  if (hist.feines && hist.ratio_hores > 1.05) {
    const f = hist.ratio_hores;
    for (const l of linies) if (l.partida_id === mo) l.quantitat = Math.round(l.quantitat * f * 2) / 2;
    avisos.push(`He augmentat les hores un ${Math.round((f - 1) * 100)}%: a les feines de ${tip} anteriors ens vam quedar curts.`);
  }
  return { titol, tipus_feina: tip, linies, hipotesis: m2 ? [] : ["No s'han indicat mides: s'ha suposat una superfície estàndard."],
    preguntes: ["Qui aporta la rajola i els sanitaris?", "Hi ha ascensor o cal pujar el material a mà?"], avisos, notes_client: "Inclou mà d'obra i material indicat. No inclou llicències ni treballs no descrits." };
}

// despeses
const pickD = (b) => {
  const d = {};
  for (const k of ["proveidor", "proveidor_nif", "tipus_doc", "num_document", "data", "concepte", "estat", "notes"]) if (k in b) d[k] = b[k];
  for (const k of ["feina_id", "partida_id", "document_id"]) if (k in b) d[k] = num(b[k]);
  for (const k of ["base", "iva_pct", "iva_import", "total", "marge_pct", "ia_confianca"]) if (k in b) d[k] = num(b[k]);
  if ("facturable" in b) d.facturable = bool(b.facturable);
  return d;
};
function completa(d) {
  if (d.iva_pct === null || d.iva_pct === undefined) d.iva_pct = sett("iva_defecte", 21);
  if (d.base && !d.total) { d.iva_import = r2(d.base * d.iva_pct / 100); d.total = r2(d.base + d.iva_import); }
  else if (d.total && !d.base) { d.base = r2(d.total / (1 + d.iva_pct / 100)); d.iva_import = r2(d.total - d.base); }
  else if (d.base && d.total) d.iva_import = r2(d.total - d.base);
}
const aprendre = (prov, part) => { if (prov && part) { const k = norm(prov).trim(); db.apren[k] = { partida_id: part, usos: (db.apren[k]?.usos || 0) + 1 }; } };
const despesaOut = (d) => ({ ...d, partida_nom: partida(d.partida_id)?.nom, feina_codi: troba("feines", d.feina_id)?.codi, feina_nom: troba("feines", d.feina_id)?.nom });
ruta("GET", "/api/despeses", (_, q) => {
  let ds = db.despeses;
  if (q.feina_id) ds = ds.filter((d) => d.feina_id === +q.feina_id);
  if (q.estat === "pendents") ds = ds.filter((d) => d.estat === "pendent_revisio" || !d.feina_id || !d.partida_id);
  return ds.slice().sort((a, b) => (b.data > a.data ? 1 : -1)).map(despesaOut);
});
function creaDespesa(b) {
  const d = { data: avui(), tipus_doc: "tiquet", marge_pct: 0, ...pickD(b) };
  d.data = d.data || avui();
  if (!d.partida_id && d.proveidor) d.partida_id = db.apren[norm(d.proveidor).trim()]?.partida_id || null;
  if (d.feina_id && !("facturable" in d)) d.facturable = troba("feines", d.feina_id)?.mode_facturacio === "administracio" ? 1 : 0;
  if (d.facturable && (d.marge_pct === null || d.marge_pct === undefined)) d.marge_pct = sett("marge_defecte", 20);
  d.marge_pct = d.marge_pct || 0;
  completa(d); d.base = d.base || 0; d.total = d.total || 0; d.iva_import = d.iva_import || 0;
  d.estat = d.estat || (d.feina_id && d.partida_id ? "ok" : "pendent_revisio");
  const x = nou("despeses", { ...d, created_at: ara() });
  aprendre(d.proveidor, d.partida_id);
  if (d.document_id && d.feina_id) troba("documents", d.document_id).feina_id = d.feina_id;
  return { id: x.id };
}
ruta("POST", "/api/despeses", (_, __, b) => creaDespesa(b));
ruta("PUT", "/api/despeses/:id", ({ id: i }, __, b) => {
  const a = cal(troba("despeses", i)), d = pickD(b);
  if ("base" in d || "total" in d || "iva_pct" in d) { const t = { ...a, ...d }; if ("total" in d && !("base" in d)) t.base = null; if ("base" in d && !("total" in d)) t.total = null; completa(t); Object.assign(d, { base: t.base, total: t.total, iva_import: t.iva_import }); }
  Object.assign(a, d);
  if (!("estat" in d) && a.feina_id && a.partida_id) a.estat = "ok";
  aprendre(a.proveidor, a.partida_id);
  return { ok: true };
});
ruta("DELETE", "/api/despeses/:id", ({ id: i }) => { db.despeses = db.despeses.filter((d) => d.id !== +i); return { ok: true }; });

// hores
ruta("GET", "/api/hores", (_, q) => db.hores.filter((h) => (!q.feina_id || h.feina_id === +q.feina_id) && (!q.desde || h.data >= q.desde))
  .sort((a, b) => (b.data > a.data ? 1 : -1)).map((h) => ({ ...h, feina_codi: troba("feines", h.feina_id)?.codi, feina_nom: troba("feines", h.feina_id)?.nom })));
function creaHores(b) {
  const fid = num(b.feina_id), hores = num(b.hores);
  if (!fid || !hores) falla("Cal la feina i les hores.");
  const f = cal(troba("feines", fid)), u = troba("usuaris", num(b.usuari_id)) || usuariDemo();
  const h = nou("hores", { feina_id: fid, usuari_id: u.id, treballador: u.nom, data: b.data || avui(), hores, cost_hora: num(b.cost_hora) ?? u.cost_hora,
    preu_hora: num(b.preu_hora) ?? u.preu_hora, descripcio: b.descripcio || "", facturable: "facturable" in b ? bool(b.facturable) : f.mode_facturacio === "administracio" ? 1 : 0,
    albara_id: null, created_at: ara() });
  if (["pressupost", "acceptada"].includes(f.estat)) { f.estat = "en_curs"; f.data_inici = f.data_inici || h.data; }
  return { id: h.id };
}
ruta("POST", "/api/hores", (_, __, b) => creaHores(b));
ruta("PUT", "/api/hores/:id", ({ id: i }, __, b) => { const h = cal(troba("hores", i)); for (const k of ["data", "descripcio"]) if (k in b) h[k] = b[k]; for (const k of ["hores", "cost_hora", "preu_hora", "feina_id"]) if (k in b && b[k] !== "") h[k] = num(b[k]); if ("facturable" in b) h.facturable = bool(b.facturable); return { ok: true }; });
ruta("DELETE", "/api/hores/:id", ({ id: i }) => { db.hores = db.hores.filter((h) => h.id !== +i); return { ok: true }; });

// albarans
ruta("GET", "/api/feines/:id/albarans", ({ id: i }) => db.albarans.filter((a) => a.feina_id === +i).map((a) => ({ ...a, signatura: undefined,
  linies: db.linies_albara.filter((l) => l.albara_id === a.id), hores: db.hores.filter((h) => h.albara_id === a.id) })));
function guardaAlbara(a, b) {
  if (b.linies) { db.linies_albara = db.linies_albara.filter((l) => l.albara_id !== a.id); for (const l of b.linies) if (l.descripcio) nou("linies_albara", { albara_id: a.id, descripcio: l.descripcio, quantitat: num(l.quantitat, 1), unitat: l.unitat || "u" }); }
  if (b.hores_ids) { for (const h of db.hores) if (h.albara_id === a.id) h.albara_id = null; for (const i of b.hores_ids) { const h = troba("hores", i); if (h && h.feina_id === a.feina_id) h.albara_id = a.id; } }
}
ruta("POST", "/api/feines/:id/albarans", ({ id: i }, __, b) => { const a = nou("albarans", { feina_id: +i, numero: seguentCodi("A", db.albarans, "numero"), data: b.data || avui(), descripcio: b.descripcio, estat: "obert", created_at: ara() }); guardaAlbara(a, b); return { id: a.id }; });
ruta("PUT", "/api/albarans/:id", ({ id: i }, __, b) => { const a = cal(troba("albarans", i)); if (a.estat === "signat") falla("L'albarà ja està signat."); a.data = b.data || a.data; a.descripcio = b.descripcio; guardaAlbara(a, b); return { ok: true }; });
function signa(a, b, autor) { if (a.estat === "signat") falla("L'albarà ja està signat."); if (!b.nom) falla("Cal el nom de qui signa."); Object.assign(a, { estat: "signat", signat_per: b.nom, signatura: b.signatura, signat_at: ara() }); missatge(a.feina_id, `Albarà ${a.numero} signat per ${b.nom}.`, "nota", autor); }
ruta("POST", "/api/albarans/:id/signar", ({ id: i }, __, b) => { signa(cal(troba("albarans", i)), b, "empresa"); return { ok: true }; });
ruta("DELETE", "/api/albarans/:id", ({ id: i }) => { db.albarans = db.albarans.filter((a) => a.id !== +i); return { ok: true }; });

// factures
const facturaOut = (f) => { const fe = troba("feines", f.feina_id), c = client(f.client_id);
  return { ...f, feina_codi: fe?.codi, feina_nom: fe?.nom, token: fe?.token, client_nom: c?.nom, client_nif: c?.nif, client_email: c?.email, client_telefon: c?.telefon,
    vencuda: f.estat === "emesa" && f.venciment && f.venciment < avui(), linies: db.linies_factura.filter((l) => l.factura_id === f.id) }; };
ruta("GET", "/api/feines/:id/pendent", ({ id: i }) => pendentFacturar(+i));
ruta("GET", "/api/factures", (_, q) => db.factures.filter((f) => (!q.feina_id || f.feina_id === +q.feina_id) &&
  (!q.estat || (q.estat === "pendents_cobrar" ? f.estat === "emesa" : f.estat === q.estat))).slice().reverse().map(facturaOut));
function creaFactura(fid, b) {
  const fe = cal(troba("feines", fid)), pend = pendentFacturar(fid);
  const disp = Object.fromEntries([...pend.linies_pressupost, ...pend.despeses, ...pend.hores].map((x) => [`${x.origen_tipus}:${x.origen_id}`, x]));
  const ls = [];
  const pct = num(b.pct);
  if (pct) { if (pct <= 0 || pct > 100) falla("El percentatge ha d'estar entre 0 i 100."); for (const x of pend.linies_pressupost) { const imp = Math.min(r2(x.total * pct / 100), x.pendent); if (imp > 0) ls.push([x, imp, `${x.descripcio} (${pct}% del pressupost ${x.pressupost})`]); } }
  for (const it of b.items || []) { const x = disp[`${it.origen_tipus}:${it.origen_id}`]; if (!x) continue; const imp = Math.min(r2(num(it.import) ?? x.pendent), x.pendent); if (imp > 0) ls.push([x, imp, x.descripcio]); }
  for (const m of b.linies_manuals || []) if (m.descripcio) ls.push([null, null, m]);
  if (!ls.length) falla("No hi ha res seleccionat per facturar.");
  const pr = db.pressupostos.find((p) => p.feina_id === fid && p.estat === "acceptat");
  const dataF = b.data || avui();
  const f = nou("factures", { feina_id: fid, client_id: fe.client_id, serie: db.settings.serie_factura, numero: null, codi: null, data: dataF,
    venciment: new Date(new Date(dataF).getTime() + sett("venciment_dies", 30) * 864e5).toISOString().slice(0, 10), concepte: b.concepte || `Treballs a ${fe.nom}`,
    iva_pct: pr ? pr.iva_pct : sett("iva_defecte", 21), irpf_pct: pr ? pr.irpf_pct : 0, base: 0, iva_import: 0, irpf_import: 0, total: 0,
    estat: "esborrany", bloqueja: 1, rectifica_id: null, created_at: ara() });
  for (const [x, imp, desc] of ls) {
    if (!x) nou("linies_factura", { factura_id: f.id, descripcio: desc.descripcio, quantitat: num(desc.quantitat, 1), preu_unitari: num(desc.preu_unitari, 0), descompte_pct: num(desc.descompte_pct, 0), origen_tipus: "manual", origen_id: null, import: 0 });
    else nou("linies_factura", { factura_id: f.id, descripcio: desc, quantitat: 1, preu_unitari: imp, descompte_pct: 0, origen_tipus: x.origen_tipus, origen_id: x.origen_id, import: imp });
  }
  recalculaFactura(f.id);
  return { id: f.id };
}
ruta("POST", "/api/feines/:id/factures", ({ id: i }, __, b) => creaFactura(+i, b));
ruta("GET", "/api/factures/:id", ({ id: i }) => facturaOut(cal(troba("factures", i))));
ruta("PUT", "/api/factures/:id", ({ id: i }, __, b) => {
  const f = cal(troba("factures", i)); if (f.estat !== "esborrany") falla("Una factura emesa no es pot modificar. Cal fer-ne una de rectificativa.");
  for (const k of ["data", "venciment", "concepte", "notes"]) if (k in b) f[k] = b[k];
  for (const k of ["iva_pct", "irpf_pct"]) if (k in b) f[k] = num(b[k], 0);
  if (b.linies) {
    const keep = new Set();
    for (const l of b.linies) {
      if (!l.descripcio) continue;
      const ex = l.id && troba("linies_factura", l.id);
      if (ex) { Object.assign(ex, { descripcio: l.descripcio, quantitat: num(l.quantitat, 1), preu_unitari: num(l.preu_unitari, 0), descompte_pct: num(l.descompte_pct, 0) }); keep.add(ex.id); }
      else keep.add(nou("linies_factura", { factura_id: f.id, descripcio: l.descripcio, quantitat: num(l.quantitat, 1), preu_unitari: num(l.preu_unitari, 0), descompte_pct: num(l.descompte_pct, 0), origen_tipus: "manual", origen_id: null }).id);
    }
    db.linies_factura = db.linies_factura.filter((l) => l.factura_id !== f.id || keep.has(l.id));
  }
  recalculaFactura(f.id);
  return facturaOut(f);
});
ruta("DELETE", "/api/factures/:id", ({ id: i }) => { const f = cal(troba("factures", i)); if (f.estat !== "esborrany") falla("Només es poden esborrar esborranys."); db.factures = db.factures.filter((x) => x !== f); return { ok: true }; });
function numera(f) {
  const serie = `${f.serie}${f.data.slice(0, 4)}`;
  const n = Math.max(0, ...db.factures.filter((x) => x.serie === serie && x.numero).map((x) => x.numero)) + 1;
  Object.assign(f, { serie, numero: n, codi: `${serie}-${String(n).padStart(4, "0")}`, estat: "emesa" });
}
function emet(f) {
  if (f.estat !== "esborrany") falla("La factura ja està emesa.");
  const c = client(f.client_id); if (!c || !c.nif || !c.adreca) falla("Falten el NIF o l'adreça del client per poder emetre la factura.");
  if (!f.total) falla("La factura no té import.");
  numera(f);
  if (f.feina_id) missatge(f.feina_id, `Factura ${f.codi} emesa per ${eurTxt(f.total)}. Venciment ${f.venciment.split("-").reverse().join("/")}.`, "factura", "empresa");
}
ruta("POST", "/api/factures/:id/emetre", ({ id: i }) => { const f = cal(troba("factures", i)); emet(f); return facturaOut(f); });
ruta("POST", "/api/factures/:id/cobrar", ({ id: i }, __, b) => { const f = cal(troba("factures", i)); const c = b.cobrada !== false; f.estat = c ? "cobrada" : "emesa"; f.cobrada_at = c ? avui() : null; return { ok: true }; });
ruta("POST", "/api/factures/:id/bloqueja", ({ id: i }, __, b) => { cal(troba("factures", i)).bloqueja = b.bloqueja ? 1 : 0; return { ok: true }; });
ruta("POST", "/api/factures/:id/rectificar", ({ id: i }, __, b) => {
  const f = cal(troba("factures", i)); if (!["emesa", "cobrada"].includes(f.estat) || f.rectifica_id) falla("Només es poden rectificar factures emeses.");
  const { id: _ignora, ...resta } = f;
  const r = nou("factures", { ...resta, serie: db.settings.serie_factura + "R", numero: null, codi: null, data: avui(), concepte: `Rectificació de la factura ${f.codi}. ${b.motiu || ""}`,
    estat: "esborrany", rectifica_id: f.id, pagament_notificat_at: null, created_at: ara() });
  for (const l of db.linies_factura.filter((x) => x.factura_id === f.id)) {
    const { id: _i, ...dades } = l;
    nou("linies_factura", { ...dades, factura_id: r.id, quantitat: -l.quantitat, origen_tipus: "rectificacio", origen_id: null });
  }
  recalculaFactura(r.id); numera(r); f.estat = "anullada";
  missatge(f.feina_id, `Factura ${f.codi} anul·lada amb la rectificativa ${r.codi}.`, "factura", "empresa");
  return { id: r.id };
});

// missatges
ruta("GET", "/api/feines/:id/missatges", ({ id: i }) => { const ms = db.missatges.filter((m) => m.feina_id === +i); for (const m of ms) m.llegit = 1; return ms; });
ruta("POST", "/api/feines/:id/missatges", ({ id: i }, __, b) => { if (!(b.text || "").trim()) falla("Missatge buit."); missatge(+i, b.text.trim(), b.intern ? "nota" : "missatge", "empresa", !!b.intern); return { ok: true }; });

// documents
ruta("GET", "/api/documents", (_, q) => {
  const ok = (x) => (!q.feina_id || x.feina_id === +q.feina_id);
  const fitx = db.documents.filter((d) => ok(d) && (!q.tipus || d.tipus === q.tipus) && (!q.q || norm(d.nom + d.text_extret).includes(norm(q.q))))
    .map((d) => ({ ...d, feina_codi: troba("feines", d.feina_id)?.codi, feina_nom: troba("feines", d.feina_id)?.nom })).reverse();
  const gen = [];
  const fc = (x) => ({ feina_id: x.feina_id, feina_codi: troba("feines", x.feina_id)?.codi, feina_nom: troba("feines", x.feina_id)?.nom });
  if (!q.tipus || q.tipus === "pressupost") gen.push(...db.pressupostos.filter(ok).map((p) => ({ generat: "pressupost", id: p.id, numero: p.numero, titol: p.titol, estat: p.estat, data: p.data, ...fc(p) })));
  if (!q.tipus || q.tipus === "factura") gen.push(...db.factures.filter(ok).map((f) => ({ generat: "factura", id: f.id, numero: f.codi, titol: f.concepte, estat: f.estat, data: f.data, ...fc(f) })));
  if (!q.tipus || q.tipus === "albara") gen.push(...db.albarans.filter(ok).map((a) => ({ generat: "albara", id: a.id, numero: a.numero, titol: a.descripcio, estat: a.estat, data: a.data, ...fc(a) })));
  return { fitxers: fitx, generats: gen.sort((a, b) => (b.data > a.data ? 1 : -1)) };
});
ruta("POST", "/api/documents", async (_, __, b) => ({ id: (await guardaFitxer(b.get("fitxer"), b.get("feina_id"), b.get("tipus") || "altres")).id }));
ruta("DELETE", "/api/documents/:id", ({ id: i }) => { db.documents = db.documents.filter((d) => d.id !== +i); return { ok: true }; });

// inici
ruta("GET", "/api/inici", () => {
  const fs = db.feines.filter((f) => ["pressupost", "acceptada", "en_curs", "acabada"].includes(f.estat)).slice().reverse();
  const tot = { contractat: 0, cost_real: 0, facturat: 0, pendent_facturar: 0, pendent_acceptar: 0 }, alertes = [], bloq = [];
  const feines = fs.map((f) => { const r = resumFeina(f.id); for (const k in tot) tot[k] += r[k]; for (const a of r.alertes) alertes.push({ feina_id: f.id, feina: `${f.codi} ${f.nom}`, text: a });
    const b = bloquejos(f.id); if (b.length) bloq.push({ feina_id: f.id, feina: `${f.codi} ${f.nom}`, bloquejos: b });
    return { id: f.id, codi: f.codi, nom: f.nom, estat: f.estat, tipus: f.tipus, client_nom: client(f.client_id)?.nom, resum: miniResum(r), alertes: r.alertes }; });
  const nl = {};
  for (const m of db.missatges.filter((x) => !x.llegit)) nl[m.feina_id] = (nl[m.feina_id] || 0) + 1;
  const em = db.factures.filter((f) => f.estat === "emesa");
  return { feines, alertes, totals: Object.fromEntries(Object.entries(tot).map(([k, v]) => [k, r2(v)])), bloquejades: bloq,
    pagaments_notificats: em.filter((f) => f.pagament_notificat_at).map((f) => ({ id: f.id, codi: f.codi, total: f.total, feina_nom: troba("feines", f.feina_id)?.nom })),
    no_llegits: Object.entries(nl).map(([fid, n]) => ({ feina_id: +fid, codi: troba("feines", +fid).codi, nom: troba("feines", +fid).nom, n })),
    pendents_cobrar: { n: em.length, total: r2(em.reduce((s, f) => s + f.total, 0)), vencut: r2(em.filter((f) => f.venciment < avui()).reduce((s, f) => s + f.total, 0)) },
    despeses_pendents: db.despeses.filter((d) => d.estat === "pendent_revisio" || !d.feina_id || !d.partida_id).length,
    pressupostos_enviats: db.pressupostos.filter((p) => p.estat === "enviat").map((p) => ({ id: p.id, numero: p.numero, titol: p.titol, enviat_at: p.enviat_at, tipus: p.tipus, feina_id: p.feina_id, feina_nom: troba("feines", p.feina_id).nom })),
    hores_avui: db.hores.filter((h) => h.data === avui() && h.usuari_id === usuariDemo().id).reduce((s, h) => s + h.hores, 0) };
});
ruta("GET", "/api/impostos", (_, q) => resumImpostos(+q.any || new Date().getFullYear(), num(q.trimestre)));
ruta("GET", "/api/impostos/estimacio", (_, q) => estimacio(+q.any || new Date().getFullYear(), num(q.trimestre) || Math.floor(new Date().getMonth() / 3) + 1));
ruta("GET", "/api/gestor/paquet", () => falla("A la demo no es pot descarregar. La versió real genera un ZIP amb les factures de venda, les de compra i tiquets amb fotos, els llibres de registre en CSV i el resum d'impostos, i l'envia al gestor."));
ruta("GET", "/api/aprenentatge", () => {
  const tipus = [...new Set(db.feines.map((f) => f.tipus).filter(Boolean))];
  return { general: desviacions(), per_tipus: tipus.map(desviacions).filter((d) => d.feines),
    proveidors: Object.entries(db.apren).map(([k, v]) => ({ proveidor: k, usos: v.usos, partida: partida(v.partida_id)?.nom })) };
});

// planning, evolució, valoracions
ruta("GET", "/api/feines/:id/planning", ({ id: i }) => db.planning.filter((t) => t.feina_id === +i).sort((a, b) => a.ordre - b.ordre));
const creaTasca = (fid, b) => { if (!b.titol) falla("Cal el nom de la tasca."); return { id: nou("planning", { feina_id: fid, titol: b.titol, data_inici: b.data_inici || null, data_fi: b.data_fi || null, estat: "pendent", pct: 0, ordre: db.planning.length + 1, created_at: ara() }).id }; };
ruta("POST", "/api/feines/:id/planning", ({ id: i }, __, b) => creaTasca(+i, b));
ruta("PUT", "/api/planning/:id", ({ id: i }, __, b) => {
  const t = cal(troba("planning", i)), abans = t.estat;
  for (const k of ["titol", "data_inici", "data_fi", "estat"]) if (k in b) t[k] = b[k];
  if ("pct" in b) t.pct = +b.pct;
  if (t.estat === "fet") t.pct = 100; else if (t.pct === 100) t.estat = "fet";
  if (t.estat === "fet" && abans !== "fet") missatge(t.feina_id, `Fase acabada: ${t.titol}.`, "evolucio", "empresa");
  return { ok: true };
});
ruta("DELETE", "/api/planning/:id", ({ id: i }) => { db.planning = db.planning.filter((t) => t.id !== +i); return { ok: true }; });
ruta("POST", "/api/feines/:id/evolucio", async ({ id: i }, __, b) => {
  const text = (b.get("text") || "").trim(), fotos = b.getAll("fotos");
  if (!text && !fotos.length) falla("Escriu alguna cosa o afegeix una foto.");
  if (!fotos.length) missatge(+i, text, "evolucio", "empresa");
  let k = 0;
  for (const fo of fotos) { const d = await guardaFitxer(fo, +i, "foto"); d.visible_client = 1; missatge(+i, k++ === 0 && text ? text : "📷", "evolucio", "empresa", false, { document_id: d.id }); }
  return { ok: true };
});
ruta("GET", "/api/feines/:id/valoracions", ({ id: i }) => db.valoracions.filter((v) => v.feina_id === +i).reverse());

// anàlisi
ruta("GET", "/api/feines/:id/analisi", ({ id: i }) => { const a = db.analisis.filter((x) => x.feina_id === +i).pop(); return a ? { dades: a.dades, text: a.text, created_at: a.created_at } : { dades: analisiFeina(+i), text: null, created_at: null }; });
ruta("POST", "/api/feines/:id/analisi", ({ id: i }) => generaAnalisi(+i));

// maqueta 3D
function modelBase(W = 2.4, L = 1.8, H = 2.5) {
  return { estanca: { nom: "Estança", amplada: W, llargada: L, alcada: H },
    obertures: [{ paret: "sud", tipus: "porta", posicio: 0.55, amplada: 0.75, alcada: 2.05, alcada_terra: 0 }], elements: [],
    materials: [{ id: "terra", nom: "Porcellànic gris 60x60", tipus: "ceramica", color: "#b9b4ad", patro: "rajola", mida_peca_cm: 60, mida_peca_alt_cm: 60, color_junta: "#9a958f", brillant: false },
      { id: "paret", nom: "Pintura blanca", tipus: "pintura", color: "#f2f0eb", patro: "llis", brillant: false },
      { id: "dutxa", nom: "Rajola blanca 30x60", tipus: "ceramica", color: "#f7f7f5", patro: "rajola", mida_peca_cm: 30, mida_peca_alt_cm: 60, color_junta: "#d0d0d0", brillant: true },
      { id: "fusta", nom: "Roure natural", tipus: "fusta", color: "#b88a5a", patro: "llistons", mida_peca_cm: 20, mida_peca_alt_cm: 120, brillant: false }],
    acabats: { terra: "terra", parets: "paret", sostre: "paret", zona_humida: null, zona_humida_parets: [], zona_humida_alcada: null }, suposits: [] };
}
function modelDesDeText(mesures, desc) {
  const nums = (mesures.match(/\d+(?:[.,]\d+)?/g) || []).map((x) => num(x)).map((n) => (n > 20 ? n / 100 : n)).slice(0, 3);
  const m = modelBase(...nums);
  const t = norm(desc + " " + mesures), W = m.estanca.amplada, L = m.estanca.llargada;
  const el = (id, tipus, nom, paret, posicio, amplada, fondaria, alcada, alcada_terra = 0, material_id = null) => m.elements.push({ id, tipus, nom, paret, posicio, amplada, fondaria, alcada, alcada_terra, material_id });
  if (/bany|dutxa|lavabo|wc|vater/.test(t) || !t.trim()) {
    el("e1", "plat_dutxa", "plat de dutxa", "nord", Math.min(0.7, W / 2), Math.min(1.4, W * 0.6), 0.8, 0.05);
    el("e2", "mampara", "mampara", "nord", Math.min(0.7, W / 2), Math.min(1.4, W * 0.6), 0.8, 2.0);
    el("e3", "moble_lavabo", "moble lavabo", "est", L / 2, 0.8, 0.46, 0.85, 0, "fusta");
    el("e4", "mirall", "mirall", "est", L / 2, 0.8, 0.46, 0.8, 1.1);
    el("e5", "wc", "vàter", "oest", Math.max(L - 0.5, 0.4), 0.37, 0.65, 0.8);
    m.acabats.zona_humida = "dutxa"; m.acabats.zona_humida_parets = ["nord"];
  } else if (/cuina/.test(t)) {
    for (let i = 0; i < Math.floor(W / 0.6); i++) { el(`b${i}`, "armari_baix", "moble baix", "nord", 0.3 + i * 0.6, 0.6, 0.6, 0.85); el(`a${i}`, "armari_alt", "moble alt", "nord", 0.3 + i * 0.6, 0.6, 0.35, 0.7, 1.45); }
    el("t", "taulell", "taulell", "nord", W / 2, Math.floor(W / 0.6) * 0.6, 0.62, 0.04, 0.85);
  }
  if (/parquet|fusta|roure/.test(t)) m.acabats.terra = "fusta";
  m.suposits = ["DEMO: maqueta creada amb plantilles a partir de les mides. A la versió real, la IA la construeix mirant les fotos."];
  return m;
}
function canviIA(model, instr) {
  const t = norm(instr);
  const colors = { gris: "#8f9196", blanc: "#f5f5f2", negre: "#2b2b2b", beix: "#d8c8ad", blau: "#6f8fb3", verd: "#7f9a7a", fosc: "#55585c" };
  let fet = false;
  if (/parquet|fusta|roure/.test(t) && /terra/.test(t)) { model.acabats.terra = "fusta"; fet = true; }
  for (const [nom, hex] of Object.entries(colors)) if (t.includes(nom)) {
    const mid = `m${Date.now()}`;
    model.materials.push({ id: mid, nom: `Rajola ${nom}`, tipus: "ceramica", color: hex, patro: "rajola", mida_peca_cm: 60, mida_peca_alt_cm: 60, brillant: false });
    if (/paret/.test(t)) model.acabats.parets = mid; else if (/dutxa/.test(t)) model.acabats.zona_humida = mid; else model.acabats.terra = mid;
    fet = true; break;
  }
  for (const p of ["nord", "sud", "est", "oest"]) if (t.includes(`paret ${p}`) || t.includes(`a l'${p}`) || t.includes(` ${p}`)) {
    const tipus = /lavabo|moble/.test(t) ? "moble_lavabo" : /vater|wc/.test(t) ? "wc" : /dutxa|plat/.test(t) ? "plat_dutxa" : null;
    const e = tipus && model.elements.find((x) => x.tipus === tipus);
    if (e) { e.paret = p; e.posicio = (p === "nord" || p === "sud" ? model.estanca.amplada : model.estanca.llargada) / 2; fet = true; }
  }
  if (!fet) falla("DEMO: només entenc canvis senzills com «posa parquet a terra», «rajola gris a les parets» o «mou el lavabo a la paret oest».");
  return model;
}
const renderOut = (r) => ({ ...r, model: JSON.parse(JSON.stringify(r.model)), fotos: r.fotos || [] });
ruta("GET", "/api/feines/:id/renders", ({ id: i }) => db.renders.filter((r) => r.feina_id === +i).map(({ model, ...r }) => r).reverse());
ruta("POST", "/api/feines/:id/renders", async ({ id: i }, __, b) => {
  const fotos = [];
  for (const fo of b.getAll("fotos")) fotos.push((await guardaFitxer(fo, +i, "foto")).id);
  const r = nou("renders", { feina_id: +i, titol: b.get("titol") || "Proposta", descripcio: `${b.get("mesures")}\n${b.get("descripcio")}`.trim(),
    model: modelDesDeText(b.get("mesures") || "", b.get("descripcio") || ""), fotos, visible_client: 0, created_at: ara(), updated_at: ara() });
  return { id: r.id, avis: null };
});
ruta("GET", "/api/renders/:id", ({ id: i }) => renderOut(cal(troba("renders", i))));
ruta("PUT", "/api/renders/:id", ({ id: i }, __, b) => {
  const r = cal(troba("renders", i));
  if (b.model) { if (!b.model.estanca || !b.model.estanca.amplada) falla("Model 3D no vàlid."); r.model = b.model; }
  if ("titol" in b) r.titol = b.titol;
  if ("visible_client" in b) { if (b.visible_client && !r.visible_client) missatge(r.feina_id, `Hem compartit la maqueta 3D «${r.titol}» de com quedarà.`, "evolucio", "empresa"); r.visible_client = b.visible_client ? 1 : 0; }
  for (const mt of r.model.materials) if (mt.foto_document_id && r.visible_client) { const d = troba("documents", mt.foto_document_id); if (d) d.visible_client = 1; }
  r.updated_at = ara();
  return renderOut(r);
});
ruta("POST", "/api/renders/:id/ia", ({ id: i }, __, b) => { const r = cal(troba("renders", i)); r.model = canviIA(r.model, b.instruccio || ""); return renderOut(r); });
ruta("DELETE", "/api/renders/:id", ({ id: i }) => { db.renders = db.renders.filter((r) => r.id !== +i); return { ok: true }; });

// assistent simulat
function trobaFeina(text, actual) {
  const obj = paraules(text);
  let millor = null, punts = 0;
  for (const f of db.feines.filter((x) => x.estat !== "cancellada")) {
    const c = comunes(obj, paraules([f.codi, f.nom, f.adreca, client(f.client_id)?.nom].join(" "))) + (f.estat !== "tancada" ? 0.3 : 0);
    if (c > punts && c >= 1) { punts = c; millor = f; }
  }
  return millor ? millor.id : actual;
}
ruta("POST", "/api/assistent/interpretar", (_, __, b) => {
  const text = (b.text || "").trim(); if (text.length < 3) falla("No t'he entès. Digues què vols fer.", 422);
  const t = norm(text), accions = [], fid = trobaFeina(text, b.feina_id ? +b.feina_id : null);
  const imp = (() => { const m = t.match(/(\d+[.,]?\d*)\s*(€|euros?)/); return m ? num(m[1]) : null; })();
  const etiqueta = fid ? `${troba("feines", fid).codi} · ${troba("feines", fid).nom}` : null;
  const base = { feina_id: fid, feina_etiqueta: etiqueta, opcions_feina: [] };
  const mh = t.match(/(\d+[.,]?\d*)\s*(h|hores|hora)\b/);
  if (mh && !/pressupost/.test(t)) accions.push({ ...base, tipus: "afegir_hores", hores: num(mh[1]), resum: `Apuntar ${num(mh[1])} h de mà d'obra${etiqueta ? " a " + etiqueta : ""}`, descripcio: /de (.+?)( a | al |$)/.exec(text)?.[1] || null });
  if (/pressupost/.test(t)) {
    const desc = (text.match(/(?:afegeix|posa|inclou)\s+(?:un |una |uns |unes )?(.+?)\s+(?:al|a el|en el)\s+pressupost/i) || [])[1];
    const mc = t.match(/canvia (?:la |el )?(.+?) a (\d+[.,]?\d*)/);
    if (mc) accions.push({ ...base, tipus: "modificar_linia_pressupost", descripcio: mc[1], preu_unitari: num(mc[2]), resum: `Canviar el preu de «${mc[1]}» a ${num(mc[2])} € al pressupost` });
    else accions.push({ ...base, tipus: "afegir_linia_pressupost", descripcio: desc || "Treball afegit", quantitat: mh ? num(mh[1]) : 1, unitat: mh ? "h" : "u", preu_unitari: imp, resum: `Afegir «${desc || "treball"}» al pressupost${imp ? ` per ${imp} €` : ""}` });
  }
  if (/factura/.test(t)) { const desc = (text.match(/(?:afegeix|posa)\s+(?:a la factura\s+)?(?:un |una )?(.+?)(?:\s+de\s+\d|\s+a la factura|\s+per\s+\d|$)/i) || [])[1]; accions.push({ ...base, tipus: "afegir_linia_factura", descripcio: desc || "Concepte", quantitat: 1, preu_unitari: imp || 0, resum: `Afegir «${desc || "concepte"}» a la factura${imp ? ` per ${imp} €` : ""}` }); }
  const mn = text.match(/(?:nota|apunta)\s*:?\s*(.+)$/i);
  if (mn) accions.push({ ...base, tipus: "afegir_missatge", text: mn[1], intern: true, resum: `Nota interna: «${mn[1]}»` });
  const mm = text.match(/(?:digues|escriu|envia)(?: al client)?\s*:?\s*(?:que\s+)?(.+)$/i);
  if (mm && !mn) accions.push({ ...base, tipus: "afegir_missatge", text: mm[1], intern: false, resum: `Missatge al client: «${mm[1]}»` });
  if (/planning|fase/.test(t)) { const d = (text.match(/(?:fase|planning)\s+(?:de |d')?(.+?)(?:\s+de dilluns|\s+del|$)/i) || [])[1]; accions.push({ ...base, tipus: "afegir_planning", text: d || "Fase nova", resum: `Afegir al planning: «${d || "fase nova"}»` }); }
  return { accions, dubtes: accions.length ? (fid ? ["DEMO: ordres interpretades amb regles senzilles. La versió real fa servir la IA i entén frases lliures."] : ["No sé a quina feina et refereixes: tria-la."])
    : ["DEMO: prova frases com «afegeix 4 hores a la reforma del bany», «afegeix un desplaçament de 30 € a la factura», «nota: dimarts arriba el plat de dutxa»."] };
});
ruta("POST", "/api/assistent/executar", (_, __, b) => {
  const out = [];
  for (const a of b.accions || []) {
    try {
      const fid = +a.feina_id; if (!fid) falla("Cal triar la feina.");
      if (a.tipus === "afegir_hores") { creaHores({ feina_id: fid, hores: a.hores, descripcio: a.descripcio }); out.push({ ok: true, text: `${a.hores} h apuntades`, enllac: `#/feina/${fid}/hores` }); }
      else if (a.tipus === "afegir_linia_pressupost") {
        let p = db.pressupostos.filter((x) => x.feina_id === fid && x.estat !== "acceptat").pop();
        if (!p) { const acc = db.pressupostos.some((x) => x.feina_id === fid && x.estat === "acceptat"); p = troba("pressupostos", creaPressupost(fid, { tipus: acc ? "extra" : "principal", titol: acc ? `Canvis: ${a.descripcio}` : a.descripcio }).id); }
        const ls = totals(p.id).linies; const hores = a.unitat === "h";
        const part = db.partides.find((x) => x.tipus === (hores ? "ma_obra" : "material")).id;
        const preu = a.preu_unitari ?? (hores ? sett("preu_hora_defecte") : 0), cost = hores ? sett("cost_hora_defecte") : r2(preu / (1 + sett("marge_defecte") / 100));
        actualitzaP(p.id, { linies: [...ls, { descripcio: a.descripcio, quantitat: a.quantitat, unitat: a.unitat, partida_id: part, preu_unitari: preu, cost_unitari: cost }] });
        out.push({ ok: true, text: `Línia afegida al pressupost ${p.numero}${p.tipus === "extra" ? " (fora de pressupost)" : ""}`, enllac: `#/pressupost/${p.id}` });
      } else if (a.tipus === "modificar_linia_pressupost") {
        const p = db.pressupostos.filter((x) => x.feina_id === fid && x.estat !== "acceptat").pop(); if (!p) falla("No hi ha cap pressupost modificable (els acceptats no es poden canviar).");
        const ls = totals(p.id).linies; const obj = paraules(a.descripcio);
        const l = ls.sort((x, y) => comunes(obj, paraules(y.descripcio)) - comunes(obj, paraules(x.descripcio)))[0]; if (!l) falla("No trobo la línia.");
        l.preu_unitari = a.preu_unitari; l.marge_pct = l.cost_unitari ? r2((l.preu_unitari / l.cost_unitari - 1) * 100) : 0;
        actualitzaP(p.id, { linies: ls.sort((x, y) => x.ordre - y.ordre) }); out.push({ ok: true, text: `Pressupost ${p.numero} actualitzat`, enllac: `#/pressupost/${p.id}` });
      } else if (a.tipus === "afegir_linia_factura") {
        let f = db.factures.filter((x) => x.feina_id === fid && x.estat === "esborrany").pop();
        if (f) { nou("linies_factura", { factura_id: f.id, descripcio: a.descripcio, quantitat: 1, preu_unitari: a.preu_unitari, descompte_pct: 0, origen_tipus: "manual" }); recalculaFactura(f.id); }
        else f = troba("factures", creaFactura(fid, { linies_manuals: [{ descripcio: a.descripcio, quantitat: 1, preu_unitari: a.preu_unitari }] }).id);
        out.push({ ok: true, text: "Línia afegida a l'esborrany de factura", enllac: `#/factura/${f.id}` });
      } else if (a.tipus === "afegir_missatge") { missatge(fid, a.text, a.intern ? "nota" : "missatge", "empresa", a.intern); out.push({ ok: true, text: a.intern ? "Nota interna desada" : "Missatge enviat al client", enllac: `#/feina/${fid}/missatges` }); }
      else if (a.tipus === "afegir_planning") { creaTasca(fid, { titol: a.text }); out.push({ ok: true, text: "Tasca afegida al planning", enllac: `#/feina/${fid}/planning` }); }
    } catch (e) { out.push({ ok: false, text: `${a.resum}: ${e.detail || e.message}` }); }
  }
  return { resultats: out };
});

// portal del client
const perToken = (tk) => cal(db.feines.find((f) => f.token === tk), "Enllaç no vàlid.");
ruta("GET", "/api/portal/:tk", ({ tk }) => {
  const f = perToken(tk), r = resumFeina(f.id);
  const pres = db.pressupostos.filter((p) => p.feina_id === f.id && p.estat !== "esborrany").map((p) => { const t = totals(p.id); return { ...p, total: t.total, base: t.base }; });
  const msgs = db.missatges.filter((m) => m.feina_id === f.id && !m.intern);
  const pl = db.planning.filter((t) => t.feina_id === f.id).sort((a, b) => a.ordre - b.ordre);
  return { feina: { codi: f.codi, nom: f.nom, estat: f.estat, adreca: f.adreca, data_inici: f.data_inici, data_fi: f.data_fi },
    empresa: { nom: db.settings.empresa_nom, telefon: db.settings.empresa_telefon, email: db.settings.empresa_email },
    pagament: { iban: db.settings.empresa_iban, bizum: db.settings.empresa_bizum, titular: db.settings.empresa_nom },
    pressupostos: pres, factures: db.factures.filter((x) => x.feina_id === f.id && ["emesa", "cobrada", "anullada"].includes(x.estat)),
    albarans: db.albarans.filter((a) => a.feina_id === f.id).map((a) => ({ ...a, signatura: undefined })), missatges: msgs,
    bloquejos: bloquejos(f.id), pendent: pendentClient(f.id), planning: pl, progres: pl.length ? Math.round(pl.reduce((s, t) => s + t.pct, 0) / pl.length) : null,
    evolucio: msgs.filter((m) => m.tipus === "evolucio"), valoracions: db.valoracions.filter((v) => v.feina_id === f.id).reverse(),
    renders: db.renders.filter((x) => x.feina_id === f.id && x.visible_client).map((x) => ({ id: x.id, titol: x.titol })),
    resum: { contractat: r.contractat, facturat: r.facturat_total, cobrat: r.cobrat, pendent_cobrar: r.pendent_cobrar } };
});
ruta("POST", "/api/portal/:tk/pressupostos/:id/acceptar", ({ tk, id: i }, __, b) => {
  const f = perToken(tk), p = cal(db.pressupostos.find((x) => x.id === +i && x.feina_id === f.id));
  if (p.estat !== "enviat") falla("Aquest pressupost ja no està pendent de resposta.");
  if (!(b.nom || "").trim() || !b.accepto) falla("Escriu el teu nom i marca la casella d'acceptació.");
  acceptaP(p, b.nom.trim(), "client"); return { ok: true };
});
ruta("POST", "/api/portal/:tk/pressupostos/:id/rebutjar", ({ tk, id: i }, __, b) => { const f = perToken(tk), p = cal(db.pressupostos.find((x) => x.id === +i && x.feina_id === f.id)); Object.assign(p, { estat: "rebutjat", rebutjat_motiu: b.motiu }); missatge(f.id, `El client ha rebutjat el pressupost ${p.numero}. ${b.motiu || ""}`, "rebuig", "client"); return { ok: true }; });
ruta("POST", "/api/portal/:tk/missatges", ({ tk }, __, b) => { const f = perToken(tk); if (!(b.text || "").trim()) falla("Missatge buit."); missatge(f.id, b.text.trim(), "missatge", "client"); return { ok: true }; });
ruta("POST", "/api/portal/:tk/peticions", ({ tk }, __, b) => { const f = perToken(tk); if (!(b.text || "").trim()) falla("Explica què necessites."); missatge(f.id, `${{ canvi: "Petició de canvi", dubte: "Dubte", incidencia: "Incidència" }[b.tipus] || "Petició"}: ${b.text.trim()}`, "peticio", "client"); return { ok: true }; });
ruta("POST", "/api/portal/:tk/valoracions", ({ tk }, __, b) => { const f = perToken(tk), p = +b.puntuacio; if (!(p >= 1 && p <= 5)) falla("Tria una puntuació de 1 a 5 estrelles."); nou("valoracions", { feina_id: f.id, puntuacio: p, comentari: (b.comentari || "").trim(), created_at: ara() }); missatge(f.id, `Valoració del client: ${"★".repeat(p)}${"☆".repeat(5 - p)} ${b.comentari || ""}`.trim(), "valoracio", "client"); return { ok: true }; });
ruta("POST", "/api/portal/:tk/factures/:id/pagat", ({ tk, id: i }, __, b) => { const f = perToken(tk), fa = cal(db.factures.find((x) => x.id === +i && x.feina_id === f.id && x.estat === "emesa")); fa.pagament_notificat_at = ara(); missatge(f.id, `El client indica que ha pagat la factura ${fa.codi} (${eurTxt(fa.total)}) per ${b.metode === "bizum" ? "Bizum" : "transferència"}. Cal comprovar l'ingrés i marcar-la com a cobrada.`, "pagament", "client"); return { ok: true }; });
ruta("POST", "/api/portal/:tk/albarans/:id/signar", ({ tk, id: i }, __, b) => { const f = perToken(tk); signa(cal(db.albarans.find((a) => a.id === +i && a.feina_id === f.id)), b, "client"); return { ok: true }; });
ruta("GET", "/api/portal/:tk/renders/:id", ({ tk, id: i }) => { const f = perToken(tk), r = cal(db.renders.find((x) => x.id === +i && x.feina_id === f.id && x.visible_client)); return { id: r.id, titol: r.titol, model: r.model }; });

// ------------------------------------------------------------ documents imprimibles

const e = (v) => (v === null || v === undefined ? "" : String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]));
const dc = (d) => (d ? String(d).slice(0, 10).split("-").reverse().join("/") : "");
const CSS_DOC = `body{font-family:system-ui,sans-serif;color:#1d2433;margin:0;padding:24px;background:#fff}h1{color:#1f5fae;margin:0 0 4px}header{display:flex;justify-content:space-between;gap:20px;border-bottom:3px solid #1f5fae;padding-bottom:12px;flex-wrap:wrap}.m{color:#5b6475;font-size:13px;line-height:1.5}.p{display:flex;gap:16px;margin:16px 0;flex-wrap:wrap}.p>div{flex:1;min-width:200px;background:#f5f7fa;border-radius:8px;padding:10px 12px;font-size:13px}table{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}th{background:#1f5fae;color:#fff;text-align:left;padding:7px}td{padding:7px;border-bottom:1px solid #e3e7ee;vertical-align:top}.r{text-align:right;white-space:nowrap}.t{margin-left:auto;width:300px;max-width:100%}.t td{border:0}.big td{font-weight:700;font-size:16px;border-top:2px solid #1f5fae}img.f{max-width:120px;max-height:90px;border-radius:6px;display:block;margin-top:4px}`;
const empresaH = () => [db.settings.empresa_nom, "NIF " + db.settings.empresa_nif, db.settings.empresa_adreca, db.settings.empresa_telefon].map(e).join("<br>");
const clientH = (c) => (c ? [c.nom, c.nif && "NIF " + c.nif, c.adreca, c.telefon].filter(Boolean).map(e).join("<br>") : "");
const eu = (v) => e(eurTxt(v));
function docPressupost(i) {
  const p = troba("pressupostos", i), f = troba("feines", p.feina_id), t = totals(p.id);
  const files = t.linies.map((l) => `<tr><td>${e(l.descripcio)}${l.referencia ? `<div class="m">Ref. ${e(l.referencia)}</div>` : ""}${l.foto_document_id && fitxers[l.foto_document_id] ? `<img class="f" src="${fitxers[l.foto_document_id]}">` : ""}</td>
    <td class="r">${l.quantitat} ${e(l.unitat)}</td><td class="r">${eu(l.preu_unitari)}</td><td class="r">${eu(l.import)}</td></tr>`).join("");
  return `<style>${CSS_DOC}</style><header><div><h1>${p.tipus === "extra" ? "FORA DE PRESSUPOST" : "PRESSUPOST"}</h1><div class="m">Núm. ${e(p.numero)} · ${dc(p.data)}</div>
    ${p.acceptat_per ? `<p style="color:#1b7a3d"><b>Acceptat per ${e(p.acceptat_per)} el ${dc(p.acceptat_at)}</b></p>` : ""}</div><div class="m" style="text-align:right">${empresaH()}</div></header>
    <div class="p"><div><b>Client</b><br>${clientH(client(f.client_id))}</div><div><b>Obra</b><br>${e(f.nom)}<br>${e(f.adreca)}</div></div><p><b>${e(p.titol)}</b></p>
    <table><tr><th>Descripció</th><th class="r">Quant.</th><th class="r">Preu</th><th class="r">Import</th></tr>${files}</table>
    <table class="t"><tr><td>Base</td><td class="r">${eu(t.base)}</td></tr><tr><td>IVA ${p.iva_pct}%</td><td class="r">${eu(t.iva)}</td></tr><tr class="big"><td>TOTAL</td><td class="r">${eu(t.total)}</td></tr></table>
    <p class="m">${e(p.notes)}<br>${e(p.condicions)}</p>`;
}
function docFactura(i) {
  const f = troba("factures", i), fe = troba("feines", f.feina_id), ls = db.linies_factura.filter((l) => l.factura_id === f.id);
  return `<style>${CSS_DOC}</style><header><div><h1>${f.rectifica_id ? "FACTURA RECTIFICATIVA" : f.estat === "esborrany" ? "ESBORRANY DE FACTURA" : "FACTURA"}</h1><div class="m">Núm. ${e(f.codi || "(pendent)")} · ${dc(f.data)} · venciment ${dc(f.venciment)}</div></div>
    <div class="m" style="text-align:right">${empresaH()}</div></header><div class="p"><div><b>Client</b><br>${clientH(client(f.client_id))}</div><div><b>Obra</b><br>${e(fe?.nom)}<br>${e(fe?.adreca)}</div></div>
    <table><tr><th>Concepte</th><th class="r">Quant.</th><th class="r">Preu</th><th class="r">Import</th></tr>${ls.map((l) => `<tr><td>${e(l.descripcio)}</td><td class="r">${l.quantitat}</td><td class="r">${eu(l.preu_unitari)}</td><td class="r">${eu(l.import)}</td></tr>`).join("")}</table>
    <table class="t"><tr><td>Base</td><td class="r">${eu(f.base)}</td></tr><tr><td>IVA ${f.iva_pct}%</td><td class="r">${eu(f.iva_import)}</td></tr><tr class="big"><td>TOTAL</td><td class="r">${eu(f.total)}</td></tr></table>
    <p class="m"><b>Forma de pagament</b> · Transferència: ${e(db.settings.empresa_iban)} · Bizum: ${e(db.settings.empresa_bizum)} · Concepte: ${e(f.codi)}</p>`;
}
function docAlbara(i) {
  const a = troba("albarans", i), f = troba("feines", a.feina_id);
  const files = db.linies_albara.filter((l) => l.albara_id === a.id).map((l) => `<tr><td>${e(l.descripcio)}</td><td class="r">${l.quantitat} ${e(l.unitat)}</td></tr>`).join("")
    + db.hores.filter((h) => h.albara_id === a.id).map((h) => `<tr><td>Mà d'obra ${dc(h.data)} ${e(h.treballador)}</td><td class="r">${h.hores} h</td></tr>`).join("");
  return `<style>${CSS_DOC}</style><header><div><h1>ALBARÀ DE FEINA</h1><div class="m">Núm. ${e(a.numero)} · ${dc(a.data)}</div></div><div class="m" style="text-align:right">${empresaH()}</div></header>
    <div class="p"><div><b>Client</b><br>${clientH(client(f.client_id))}</div><div><b>Obra</b><br>${e(f.nom)}</div></div><p>${e(a.descripcio)}</p>
    <table><tr><th>Treball / material</th><th class="r">Quantitat</th></tr>${files}</table>
    <p class="m">Conforme client: ${e(a.signat_per || "")} ${dc(a.signat_at)}</p>${a.signatura ? `<img src="${a.signatura}" style="max-height:90px">` : ""}`;
}

// ------------------------------------------------------------ dades d'exemple

function sembra() {
  db = buida();
  db.usuaris.push({ id: id("usuaris"), nom: "Usuari Demo", usuari: "demo", rol: "admin", cost_hora: 25, preu_hora: 38, actiu: 1 },
    { id: id("usuaris"), nom: "Operari Exemple", usuari: "operari", rol: "treballador", cost_hora: 22, preu_hora: 36, actiu: 1 });
  [["Mà d'obra", "ma_obra"], ["Material", "material"], ["Subcontractes", "subcontracta"], ["Maquinària i lloguers", "altres"], ["Desplaçaments i dietes", "altres"], ["Runa i residus", "altres"], ["Altres", "altres"]]
    .forEach(([nom, tipus], i) => db.partides.push({ id: id("partides"), nom, tipus, ordre: i }));
  const MO = 1, MAT = 2, RUNA = 6;
  for (const [nom, unitat, cost, marge, prov] of [["Rajola porcellànica 60x60", "m2", 18, 35, "Magatzem Exemple"], ["Rajola blanca 30x60", "m2", 14, 35, "Magatzem Exemple"],
    ["Plat de dutxa extraplà 140x80", "u", 160, 30, "Sanitaris Exemple"], ["Mampara de vidre 140", "u", 280, 30, "Sanitaris Exemple"], ["Moble de lavabo 80 cm", "u", 320, 30, "Sanitaris Exemple"],
    ["Pintura plàstica blanca", "l", 4.5, 40, "Pintures Exemple"], ["Morter cola", "sac", 9, 35, "Magatzem Exemple"], ["Contenidor de runa", "u", 180, 25, "Contenidors Exemple"]])
    db.articles.push({ id: id("articles"), codi: "", nom, unitat, partida_id: nom.startsWith("Contenidor") ? RUNA : MAT, cost, marge_pct: marge, preu: null, descompte_pct: 0, proveidor: prov, actiu: 1 });
  const l = (descripcio, partida_id, quantitat, unitat, cost_unitari, preu_unitari, referencia = null) => ({ descripcio, partida_id, quantitat, unitat, cost_unitari, preu_unitari, referencia });

  // Feina acabada antiga (historial): bany amb hores per sobre del previst
  const f0 = creaFeina({ nom: "Bany planta baixa c/ Antic 4", tipus: "bany", adreca: "Carrer Antic 4", client_nou: { nom: "Client Exemple A", nif: "00000001R", adreca: "Adreça fictícia 1", telefon: "600111111" } });
  const p0 = creaPressupost(f0.id, { titol: "Reforma de bany", linies: [l("Enderroc i runa", MO, 8, "h", 25, 38), l("Enrajolat", MO, 20, "h", 25, 38), l("Rajola", MAT, 18, "m2", 18, 24.3), l("Plat de dutxa", MAT, 1, "u", 160, 208)] });
  enviaP(p0.id); acceptaP(troba("pressupostos", p0.id), "Client Exemple A", "client");
  creaHores({ feina_id: f0.id, hores: 34, data: dies(-120) });
  creaDespesa({ feina_id: f0.id, proveidor: "Magatzem Exemple", proveidor_nif: "B11111111", tipus_doc: "factura", partida_id: MAT, total: 680, data: dies(-118), concepte: "Rajola i material" });
  const fa0 = creaFactura(f0.id, { pct: 100 }); emet(troba("factures", fa0.id)); Object.assign(troba("factures", fa0.id), { estat: "cobrada", cobrada_at: dies(-90) });
  nou("valoracions", { feina_id: f0.id, puntuacio: 4, comentari: "Bona feina, una mica més llarga del previst.", created_at: dies(-95) });
  Object.assign(troba("feines", f0.id), { data_inici: dies(-125), data_fi: dies(-100) });
  tancaFeina(f0.id, true);

  // Feina en curs: bany amb tot
  const f1 = creaFeina({ nom: "Reforma bany c/ Exemple 12", tipus: "bany", adreca: "Carrer Exemple 12, 2n", client_nou: { nom: "Client Exemple B", nif: "00000002W", adreca: "Adreça fictícia 2", telefon: "600222222", email: "client.b@exemple.cat" } });
  const p1 = creaPressupost(f1.id, { titol: "Reforma completa del bany", linies: [
    l("Protecció d'elements i neteja d'obra", MO, 3, "h", 25, 38), l("Enderroc de revestiments i sanitaris", MO, 10, "h", 25, 38),
    l("Contenidor de runa i gestió de residus", RUNA, 1, "u", 180, 230), l("Instal·lació nova d'aigua i desguassos", MO, 12, "h", 25, 38),
    l("Enrajolat de parets i terra", MO, 24, "h", 25, 38), l("Rajola porcellànica 60x60", MAT, 22, "m2", 18, 24.3, "Model Exemple Gris 60x60 rectificat"),
    l("Plat de dutxa extraplà 140x80", MAT, 1, "u", 160, 208, "Sèrie Exemple Slim blanc"), l("Mampara de vidre 140", MAT, 1, "u", 280, 364), l("Col·locació de sanitaris i aixetes", MO, 6, "h", 25, 38)] });
  enviaP(p1.id); acceptaP(troba("pressupostos", p1.id), "Client Exemple B", "client");
  Object.assign(troba("feines", f1.id), { data_inici: dies(-12) });
  creaHores({ feina_id: f1.id, hores: 8, data: dies(-11), descripcio: "Enderroc" });
  creaHores({ feina_id: f1.id, hores: 8, data: dies(-10), descripcio: "Enderroc i runa" });
  creaHores({ feina_id: f1.id, hores: 7, data: dies(-6), descripcio: "Instal·lació d'aigua", usuari_id: 2 });
  creaHores({ feina_id: f1.id, hores: 6, data: dies(-1), descripcio: "Instal·lació i proves" });
  creaDespesa({ feina_id: f1.id, proveidor: "Contenidors Exemple", proveidor_nif: "B22222222", tipus_doc: "factura", partida_id: RUNA, total: 217.8, data: dies(-11), concepte: "Contenidor 3 m3" });
  creaDespesa({ feina_id: f1.id, proveidor: "Magatzem Exemple", proveidor_nif: "B11111111", tipus_doc: "factura", partida_id: MAT, total: 391.6, data: dies(-7), concepte: "Lampisteria" });
  creaDespesa({ feina_id: f1.id, proveidor: "Ferreteria Exemple", tipus_doc: "tiquet", total: 23.4, data: dies(-3), concepte: "Petit material" });
  const pe = creaPressupost(f1.id, { tipus: "extra", titol: "Canviar radiador per tovalloler elèctric", linies: [l("Tovalloler elèctric", MAT, 1, "u", 140, 182), l("Instal·lació i connexió", MO, 2, "h", 25, 38)] });
  enviaP(pe.id);
  const fa1 = creaFactura(f1.id, { pct: 30, concepte: "Bestreta 30% a l'acceptació" }); emet(troba("factures", fa1.id));
  troba("factures", fa1.id).data = dies(-12); troba("factures", fa1.id).venciment = dies(-2);
  for (const [t, a, b] of [["Enderroc i retirada de runa", -12, -10], ["Instal·lacions d'aigua", -9, -1], ["Enrajolat", 1, 5], ["Sanitaris i acabats", 6, 8]]) creaTasca(f1.id, { titol: t, data_inici: dies(a), data_fi: dies(b) });
  const pl = db.planning.filter((x) => x.feina_id === f1.id);
  Object.assign(pl[0], { estat: "fet", pct: 100 }); Object.assign(pl[1], { estat: "en_curs", pct: 80 });
  missatge(f1.id, "Fase acabada: Enderroc i retirada de runa.", "evolucio", "empresa");
  missatge(f1.id, "Hola! Es podria canviar el radiador per un tovalloler?", "peticio", "client");
  missatge(f1.id, "Dimarts arriba el plat de dutxa.", "nota", "empresa", true);
  const r = nou("renders", { feina_id: f1.id, titol: "Bany acabat", descripcio: "240 x 180, alçada 250", model: modelDesDeText("240 180 250", "bany dutxa lavabo wc"), fotos: [], visible_client: 1, created_at: ara(), updated_at: ara() });
  r.model.obertures.push({ paret: "nord", tipus: "finestra", posicio: 1.8, amplada: 0.6, alcada: 0.8, alcada_terra: 1.3 });
  r.model.suposits = [];

  // Feina amb pressupost enviat (bloqueja l'inici)
  const f2 = creaFeina({ nom: "Pintura pis Av. Inventada 5", tipus: "pintura", adreca: "Avinguda Inventada 5, 3r", client_nou: { nom: "Client Exemple C", nif: "00000003A", adreca: "Adreça fictícia 3", telefon: "600333333" } });
  const p2 = creaPressupost(f2.id, { titol: "Pintura completa del pis (80 m2)", linies: [l("Protecció de mobles i terres", MO, 3, "h", 25, 38), l("Preparació de parets", MO, 10, "h", 25, 38),
    l("Pintura plàstica, dues mans", MO, 14, "h", 25, 38), l("Pintura plàstica blanca", MAT, 24, "l", 4.5, 6.3)] });
  enviaP(p2.id);
  for (const m of db.missatges) if (m.autor !== "client" || m.feina_id !== f1.id) m.llegit = 1;
}

// ------------------------------------------------------------------ fetch

function inicia() {
  try {
    const s = localStorage.getItem(CLAU);
    if (s) { db = JSON.parse(s); Object.assign(fitxers, JSON.parse(localStorage.getItem(CLAU + "-fitxers") || "{}")); }
  } catch { db = null; }
  if (!db) { sembra(); desa(); }
}

const fetchReal = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input.url;
  const u = new URL(url, location.href);
  const path = url.startsWith("/") ? url.split("?")[0] : null;
  if (!path || !path.startsWith("/api/")) return fetchReal(input, init);
  const metode = (init.method || "GET").toUpperCase();
  let body = init.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
  body = body || {};
  const query = Object.fromEntries(u.searchParams);
  for (const [m, re, fn] of R) {
    const mt = path.match(re);
    if (m === metode && mt) {
      try {
        const res = await fn(mt.groups || {}, query, body);
        desa();
        return new Response(JSON.stringify(res), { status: 200, headers: { "Content-Type": "application/json" } });
      } catch (err) {
        if (!(err instanceof Err)) console.error(err);
        return new Response(JSON.stringify({ detail: err.detail || err.message }), { status: err.status || 500, headers: { "Content-Type": "application/json" } });
      }
    }
  }
  return new Response(JSON.stringify({ detail: `DEMO: ruta no disponible (${metode} ${path})` }), { status: 404 });
};

// Documents, fotos i enllaços dins la demo
function mostraDocument(html, titol) {
  const fons = document.createElement("div");
  fons.className = "modal-fons";
  fons.innerHTML = `<div class="modal ample" role="dialog"><header><h3>${e(titol)}</h3><button class="btn-icon" data-x>✕</button></header>
    <div class="modal-cos"><iframe class="doc-demo" title="${e(titol)}"></iframe><p class="muted">A la versió real es pot imprimir o desar en PDF.</p></div></div>`;
  fons.querySelector("iframe").srcdoc = html;
  fons.onclick = (ev) => { if (ev.target === fons || ev.target.closest("[data-x]")) fons.remove(); };
  document.body.appendChild(fons);
}
function obreUrl(url) {
  let m;
  if ((m = url.match(/\/imprimir\/(pressupost|factura|albara)\/(\d+)/))) {
    const fn = { pressupost: docPressupost, factura: docFactura, albara: docAlbara }[m[1]];
    if (troba(m[1] === "pressupost" ? "pressupostos" : m[1] === "factura" ? "factures" : "albarans", m[2])) mostraDocument(fn(+m[2]), m[1][0].toUpperCase() + m[1].slice(1));
    return true;
  }
  if ((m = url.match(/\/(?:api\/documents|p\/[^/]+\/fitxer)\/(\d+)/))) {
    const src = fitxers[m[1]];
    if (src) mostraDocument(`<img src="${src}" style="max-width:100%">`, troba("documents", m[1])?.nom || "Document");
    return true;
  }
  return false;
}
window.open = (url) => { obreUrl(String(url)); return null; };
document.addEventListener("click", (ev) => {
  const a = ev.target.closest("a[href]");
  if (!a) return;
  const href = a.getAttribute("href");
  if (href.startsWith("/") && obreUrl(href)) { ev.preventDefault(); ev.stopPropagation(); }
}, true);
const resol = (src) => { const m = src && src.match(/\/(?:api\/documents|p\/[^/]+\/fitxer)\/(\d+)/); return m ? fitxers[m[1]] || "" : src; };
new MutationObserver((ms) => {
  for (const mu of ms) for (const n of mu.addedNodes) if (n.querySelectorAll) for (const img of [n, ...n.querySelectorAll("img")]) {
    if (img.tagName === "IMG") { const s = img.getAttribute("src"); if (s && s.startsWith("/")) img.src = resol(s); }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

// A la demo no hi ha micròfon: es fa servir el teclat (o el micròfon del teclat del mòbil)
window.SpeechRecognition = undefined;
window.webkitSpeechRecognition = undefined;

window.DEMO = {
  enllacPortal: (tk) => `#/portal/${tk}`,
  url: (u) => resol(u) || u,
  reinicia: () => { try { localStorage.removeItem(CLAU); localStorage.removeItem(CLAU + "-fitxers"); } catch { /* res */ } location.hash = "#/inici"; location.reload(); },
};
inicia();
