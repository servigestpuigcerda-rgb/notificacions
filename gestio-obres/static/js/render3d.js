// Visor 3D de la maqueta (three.js). La vista és de "casa de nines": les parets més properes a la càmera no es dibuixen.
import { urlFitxer } from "./core.js";

let THREE, OrbitControls;

async function carrega() {
  if (THREE) return;
  THREE = await import("three");
  ({ OrbitControls } = await import("three/addons/controls/OrbitControls.js"));
}

const COLORS_ELEMENT = {
  plat_dutxa: "#f4f4f2", banyera: "#f4f4f2", lavabo: "#ffffff", moble_lavabo: "#c9a77c", wc: "#ffffff", bidet: "#ffffff",
  mampara: "#bfe3f2", mirall: "#dfe8ee", armari_baix: "#d8d2c6", armari_alt: "#d8d2c6", taulell: "#8a8580", pica: "#c8ccd0",
  placa: "#222222", forn: "#3a3a3a", nevera: "#e9ecef", rentadora: "#f1f3f5", radiador: "#f5f5f5", prestatge: "#b08a5a",
  taula: "#a67c52", cadira: "#7b5b3a", sofa: "#7a8a99", llit: "#e6e1d8", illa: "#d8d2c6", columna: "#e8e8e8", altre: "#cccccc",
};

function textura(mat, fotoUrl) {
  if (mat.patro === "llis" && !mat.foto_document_id) return null;
  const pw = (mat.mida_peca_cm || (mat.patro === "llistons" ? 20 : 30)) / 100;
  const ph = (mat.mida_peca_alt_cm || (mat.patro === "llistons" ? 120 : mat.mida_peca_cm || 30)) / 100;
  let tex;
  if (mat.foto_document_id && fotoUrl) {
    tex = new THREE.TextureLoader().load(urlFitxer(fotoUrl(mat.foto_document_id)));
  } else {
    const cv = document.createElement("canvas");
    const S = 256;
    cv.width = S; cv.height = Math.round(S * (mat.patro === "llistons" ? 2 : ph / pw));
    const c = cv.getContext("2d");
    c.fillStyle = mat.color || "#cccccc";
    c.fillRect(0, 0, cv.width, cv.height);
    if (mat.patro === "rajola") {
      c.strokeStyle = mat.color_junta || "#00000033";
      c.lineWidth = 4;
      c.strokeRect(0, 0, cv.width, cv.height);
    } else if (mat.patro === "llistons") {
      // dos llistons d'ample, decalats
      c.strokeStyle = "#00000030"; c.lineWidth = 3;
      c.beginPath(); c.moveTo(S / 2, 0); c.lineTo(S / 2, cv.height); c.moveTo(0, 0); c.lineTo(0, cv.height);
      c.moveTo(0, cv.height * 0.5); c.lineTo(S / 2, cv.height * 0.5); c.moveTo(S / 2, cv.height * 0.15); c.lineTo(S, cv.height * 0.15);
      c.stroke();
      for (let i = 0; i < 60; i++) {
        c.fillStyle = `rgba(0,0,0,${Math.random() * 0.05})`;
        c.fillRect(Math.random() * S, 0, 1 + Math.random() * 2, cv.height);
      }
    }
    tex = new THREE.CanvasTexture(cv);
  }
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.userData = { pw: mat.patro === "llistons" ? pw * 2 : pw, ph };
  return tex;
}

function materialThree(mat, fotoUrl, cache) {
  if (!mat) return new THREE.MeshStandardMaterial({ color: "#dddddd", roughness: 0.9 });
  if (cache[mat.id]) return cache[mat.id];
  const tex = textura(mat, fotoUrl);
  const m = new THREE.MeshStandardMaterial({
    color: tex ? "#ffffff" : mat.color || "#cccccc", map: tex, roughness: mat.brillant ? 0.25 : 0.85,
    metalness: mat.tipus === "metall" ? 0.6 : 0, transparent: mat.tipus === "vidre", opacity: mat.tipus === "vidre" ? 0.35 : 1,
  });
  cache[mat.id] = m;
  return m;
}

// Clona el material ajustant la repetició de la textura a la mida real de la peça
function ambMida(m, w, h, u0 = 0, v0 = 0) {
  if (!m.map) return m;
  const c = m.clone();
  c.map = m.map.clone();
  c.map.needsUpdate = true;
  const { pw, ph } = m.map.userData;
  c.map.repeat.set(w / pw, h / ph);
  c.map.offset.set((u0 / pw) % 1, (v0 / ph) % 1);
  return c;
}

export async function visor3d(container, model, { fotoUrl } = {}) {
  await carrega();
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.innerHTML = "";
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#eef1f5");
  const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  scene.add(new THREE.HemisphereLight("#ffffff", "#8d8a85", 1.6));
  const sol = new THREE.DirectionalLight("#ffffff", 1.4);
  scene.add(sol);
  let grup = null;
  let primer = true;

  const construeix = (md) => {
    if (grup) {
      scene.remove(grup);
      grup.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
    }
    grup = new THREE.Group();
    const cache = {};
    const mats = Object.fromEntries((md.materials || []).map((x) => [x.id, x]));
    const mat = (id) => materialThree(mats[id], fotoUrl, cache);
    const { amplada: W, llargada: L, alcada: H } = md.estanca;
    const ac = md.acabats || {};

    // Terra
    const terraM = ambMida(mat(ac.terra), W, L);
    const terra = new THREE.Mesh(new THREE.PlaneGeometry(W, L), terraM);
    terra.rotation.x = -Math.PI / 2;
    terra.position.set(W / 2, 0, L / 2);
    grup.add(terra);

    // Parets amb obertures
    const parets = {
      sud: { len: W, rot: 0, punt: (u, v) => [u, v, 0], n: [0, 0, 1] },
      nord: { len: W, rot: Math.PI, punt: (u, v) => [u, v, L], n: [0, 0, -1] },
      oest: { len: L, rot: Math.PI / 2, punt: (u, v) => [0, v, u], n: [1, 0, 0] },
      est: { len: L, rot: -Math.PI / 2, punt: (u, v) => [W, v, u], n: [-1, 0, 0] },
    };
    const humida = new Set(ac.zona_humida ? ac.zona_humida_parets || [] : []);
    const hz = ac.zona_humida_alcada || H;
    const pla = (p, u0, u1, v0, v1, mt) => {
      if (u1 - u0 < 0.005 || v1 - v0 < 0.005) return;
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(u1 - u0, v1 - v0), ambMida(mt, u1 - u0, v1 - v0, u0, v0));
      mesh.position.set(...p.punt((u0 + u1) / 2, (v0 + v1) / 2));
      mesh.rotation.y = p.rot;
      grup.add(mesh);
      return mesh;
    };
    const tros = (nom, p, u0, u1, v0, v1) => {
      if (humida.has(nom) && v0 < hz) {
        pla(p, u0, u1, v0, Math.min(v1, hz), mat(ac.zona_humida));
        if (v1 > hz) pla(p, u0, u1, hz, v1, mat(ac.parets));
      } else pla(p, u0, u1, v0, v1, mat(ac.parets));
    };
    for (const [nom, p] of Object.entries(parets)) {
      const ob = (md.obertures || []).filter((o) => o.paret === nom)
        .map((o) => ({ ...o, u0: Math.max(o.posicio - o.amplada / 2, 0), u1: Math.min(o.posicio + o.amplada / 2, p.len) }))
        .sort((a, b) => a.u0 - b.u0);
      let u = 0;
      for (const o of ob) {
        tros(nom, p, u, o.u0, 0, H);
        tros(nom, p, o.u0, o.u1, 0, o.alcada_terra);
        tros(nom, p, o.u0, o.u1, Math.min(o.alcada_terra + o.alcada, H), H);
        const fulla = new THREE.Mesh(new THREE.PlaneGeometry(o.u1 - o.u0, Math.min(o.alcada, H - o.alcada_terra)),
          o.tipus === "porta" ? new THREE.MeshStandardMaterial({ color: "#b48a5e", roughness: 0.7 })
            : new THREE.MeshStandardMaterial({ color: "#bfe3f2", transparent: true, opacity: 0.35, roughness: 0.1 }));
        fulla.position.set(...p.punt((o.u0 + o.u1) / 2, o.alcada_terra + Math.min(o.alcada, H - o.alcada_terra) / 2));
        fulla.position.x += p.n[0] * 0.02; fulla.position.z += p.n[2] * 0.02;
        fulla.rotation.y = p.rot;
        grup.add(fulla);
        u = o.u1;
      }
      tros(nom, p, u, p.len, 0, H);
    }

    // Elements
    for (const e of md.elements || []) {
      const g = new THREE.Group();
      const color = COLORS_ELEMENT[e.tipus] || "#cccccc";
      const mtl = e.material_id && mats[e.material_id] ? mat(e.material_id) : new THREE.MeshStandardMaterial({ color, roughness: 0.5 });
      const caixa = (w, h, d, y, z = 0, m2 = mtl) => {
        const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m2);
        b.position.set(0, y, z);
        g.add(b);
      };
      const { amplada: w, fondaria: d, alcada: h } = e;
      const blanc = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.3 });
      switch (e.tipus) {
        case "wc":
          caixa(w, h * 0.55, d * 0.75, h * 0.275, d * 0.12, blanc);
          caixa(w, h * 0.45, d * 0.22, h * 0.775, -d * 0.39, blanc);
          break;
        case "lavabo":
          caixa(w, Math.min(h, 0.18), d, Math.min(h, 0.18) / 2, 0, blanc);
          break;
        case "moble_lavabo":
          caixa(w, h - 0.03, d, (h - 0.03) / 2);
          caixa(w, 0.03, d, h - 0.015, 0, blanc);
          break;
        case "mampara": {
          const vidre = new THREE.MeshStandardMaterial({ color: "#cfe9f5", transparent: true, opacity: 0.3, roughness: 0.05 });
          caixa(w, h, 0.01, h / 2, d / 2, vidre);
          break;
        }
        case "mirall":
          caixa(w, h, 0.01, h / 2, -d / 2 + 0.005, new THREE.MeshStandardMaterial({ color: "#e6eef3", metalness: 0.9, roughness: 0.05 }));
          break;
        case "pica":
        case "placa":
          caixa(w, 0.02, d, 0.01);
          break;
        default:
          caixa(w, h, d, h / 2);
      }
      const y0 = e.alcada_terra || 0;
      if (e.paret && parets[e.paret]) {
        const p = parets[e.paret];
        const [x, , z] = p.punt(e.posicio ?? p.len / 2, 0);
        g.position.set(x + p.n[0] * d / 2, y0, z + p.n[2] * d / 2);
        g.rotation.y = p.rot;
      } else {
        g.position.set(e.x ?? W / 2, y0, e.y ?? L / 2);
      }
      grup.add(g);
    }
    scene.add(grup);
    if (primer) {
      const r = Math.max(W, L, H);
      camera.position.set(W * 0.75, r * 1.55, -r * 0.95);
      controls.target.set(W / 2, H * 0.3, L / 2);
      sol.position.set(W * 1.5, H * 3, -L);
      primer = false;
    }
  };

  const mida = () => {
    const w = container.clientWidth || 600;
    const h = container.clientHeight || 360;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(mida);
  ro.observe(container);
  mida();
  construeix(model);
  let viu = true;
  const loop = () => { if (!viu) return; controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop); };
  loop();
  return {
    actualitza: construeix,
    captura: () => { renderer.render(scene, camera); return renderer.domElement.toDataURL("image/jpeg", 0.9); },
    destrueix: () => { viu = false; ro.disconnect(); renderer.dispose(); },
  };
}
