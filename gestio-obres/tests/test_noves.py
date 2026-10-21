"""Assistent, planning, bloquejos, pagaments, valoracions, maqueta 3D, anàlisi i paquet del gestor (dades inventades)."""
import io
import zipfile
from types import SimpleNamespace

from app import ai


def _ia_falsa(monkeypatch, sortides):
    crides = []

    def parse(**kw):
        crides.append(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=sortides[kw["output_format"]](kw))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "prova")
    monkeypatch.setattr(ai, "_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse))))
    return crides


def _nova_feina(c, nom="Cuina carrer Inventat", client="Senyora Exemple"):
    return c.post("/api/feines", json={"nom": nom, "tipus": "cuina", "adreca": "Carrer Inventat 9",
                                       "client_nou": {"nom": client, "nif": "00000001R", "adreca": "Adreça fictícia"}}).json()


def test_assistent_ordres(c, monkeypatch):
    f = _nova_feina(c)
    p = c.post(f"/api/feines/{f['id']}/pressupostos", json={"linies": [
        {"descripcio": "Taulell", "quantitat": 3, "unitat": "ml", "cost_unitari": 100, "preu_unitari": 150}]}).json()

    def resposta(kw):
        # El nom del client no s'envia a la IA, però sí el text de l'usuari
        assert "Senyora Exemple" not in kw["messages"][0]["content"].split("Ordre de l'usuari")[0]
        return ai.RespostaAssistent(accions=[
            ai.AccioAssistent(tipus="afegir_hores", resum="4 h", feina_text="senyora exemple", hores=4),
            ai.AccioAssistent(tipus="afegir_linia_pressupost", resum="aixeta", feina_text="exemple", descripcio="Aixeta monocomandament",
                              quantitat=1, unitat="u", cost_unitari=60),
            ai.AccioAssistent(tipus="modificar_linia_pressupost", resum="taulell", feina_text="exemple", linia_index=1, preu_unitari=170),
            ai.AccioAssistent(tipus="afegir_linia_factura", resum="desplaçament", feina_text="exemple", descripcio="Desplaçament",
                              quantitat=1, preu_unitari=30),
            ai.AccioAssistent(tipus="afegir_missatge", resum="nota", feina_text="exemple", text="Dimarts arriba el material", intern=True),
        ])

    _ia_falsa(monkeypatch, {ai.RespostaAssistent: resposta})
    r = c.post("/api/assistent/interpretar", json={"text": "afegeix 4 hores a la senyora exemple..."}).json()
    assert all(a["feina_id"] == f["id"] for a in r["accions"])
    res = c.post("/api/assistent/executar", json={"accions": r["accions"]}).json()["resultats"]
    assert all(x["ok"] for x in res), res
    assert c.get(f"/api/hores?feina_id={f['id']}").json()[0]["hores"] == 4
    det = c.get(f"/api/pressupostos/{p['id']}").json()
    assert [l["preu_unitari"] for l in det["totals"]["linies"]] == [170, 72]
    fac = c.get(f"/api/factures?feina_id={f['id']}").json()[0]
    assert fac["estat"] == "esborrany" and fac["base"] == 30

    # Amb el pressupost acceptat, afegir una línia crea un "fora de pressupost"
    c.post(f"/api/pressupostos/{p['id']}/acceptar", json={"per": "Senyora Exemple"})
    acc = ai.AccioAssistent(tipus="afegir_linia_pressupost", resum="x", descripcio="Endoll extra", quantitat=2, unitat="u",
                            cost_unitari=10).model_dump() | {"feina_id": f["id"]}
    out = c.post("/api/assistent/executar", json={"accions": [acc]}).json()["resultats"][0]
    assert out["ok"] and "fora de pressupost" in out["text"]


def test_portal_bloquejos_pagament_valoracio(c):
    f = _nova_feina(c, "Pintura pis exemple", "Client Portal")
    p = c.post(f"/api/feines/{f['id']}/pressupostos", json={"linies": [
        {"descripcio": "Pintar", "quantitat": 10, "unitat": "h", "cost_unitari": 25, "preu_unitari": 40}]}).json()
    token = c.post(f"/api/pressupostos/{p['id']}/enviar").json()["token"]
    portal = c.get(f"/api/portal/{token}").json()
    assert portal["bloquejos"][0]["tipus"] == "pressupost"
    c.post(f"/api/portal/{token}/pressupostos/{p['id']}/acceptar", json={"nom": "Client Portal", "accepto": True})
    fac = c.post(f"/api/feines/{f['id']}/factures", json={"pct": 50}).json()["id"]
    c.post(f"/api/factures/{fac}/emetre")
    portal = c.get(f"/api/portal/{token}").json()
    assert [b["tipus"] for b in portal["bloquejos"]] == ["pagament"]
    assert portal["pagament"]["bizum"] == "600000000"
    assert portal["pendent"]["per_pagar"] == 242 and portal["pendent"]["per_facturar"] == 242
    assert c.post(f"/api/portal/{token}/factures/{fac}/pagat", json={"metode": "bizum"}).status_code == 200
    assert c.get("/api/inici").json()["pagaments_notificats"]
    c.post(f"/api/factures/{fac}/cobrar")
    assert c.get(f"/api/portal/{token}").json()["bloquejos"] == []

    assert c.post(f"/api/portal/{token}/valoracions", json={"puntuacio": 7}).status_code == 400
    assert c.post(f"/api/portal/{token}/valoracions", json={"puntuacio": 5, "comentari": "Molt bé"}).status_code == 200
    assert c.post(f"/api/portal/{token}/peticions", json={"tipus": "canvi", "text": "Podeu canviar el color?"}).status_code == 200
    msgs = c.get(f"/api/feines/{f['id']}/missatges").json()
    assert {"pagament", "valoracio", "peticio"} <= {m["tipus"] for m in msgs}

    # Planning i evolució amb foto
    t = c.post(f"/api/feines/{f['id']}/planning", json={"titol": "Preparació de parets"}).json()["id"]
    c.put(f"/api/planning/{t}", json={"pct": 100})
    c.post(f"/api/feines/{f['id']}/evolucio", data={"text": "Parets preparades"},
           files=[("fotos", ("ev.jpg", b"\xff\xd8\xff fals", "image/jpeg"))])
    portal = c.get(f"/api/portal/{token}").json()
    assert portal["progres"] == 100
    ev = [e for e in portal["evolucio"] if e["document_id"]][0]
    assert c.get(f"/p/{token}/fitxer/{ev['document_id']}").status_code == 200
    # Un document no publicat no es pot veure des del portal
    privat = c.post("/api/documents", data={"feina_id": f["id"], "tipus": "altres"}, files={"fitxer": ("x.txt", b"privat", "text/plain")}).json()["id"]
    assert c.get(f"/p/{token}/fitxer/{privat}").status_code == 404

    # Tancament amb anàlisi
    c.post(f"/api/feines/{f['id']}/tancar", json={"forcar": True})
    an = c.get(f"/api/feines/{f['id']}/analisi").json()
    assert an["created_at"] and an["dades"]["xifres"]["valoracio"] == 5


def test_foto_material_i_maqueta(c):
    f = _nova_feina(c, "Bany maqueta exemple", "Client Maqueta")
    p = c.post(f"/api/feines/{f['id']}/pressupostos", json={}).json()["id"]
    doc = c.post(f"/api/pressupostos/{p}/foto", files={"fitxer": ("rajola.jpg", b"\xff\xd8\xff fals", "image/jpeg")}).json()["document_id"]
    c.put(f"/api/pressupostos/{p}", json={"linies": [{"descripcio": "Rajola", "quantitat": 10, "unitat": "m2", "cost_unitari": 20,
                                                      "preu_unitari": 30, "referencia": "Model Exemple 60x60", "foto_document_id": doc}]})
    l = c.get(f"/api/pressupostos/{p}").json()["totals"]["linies"][0]
    assert l["referencia"] == "Model Exemple 60x60" and l["foto_document_id"] == doc
    assert "Model Exemple 60x60" in c.get(f"/imprimir/pressupost/{p}").text

    r = c.post(f"/api/feines/{f['id']}/renders", data={"titol": "Proposta", "mesures": "240 x 180 alçada 250"}).json()
    model = c.get(f"/api/renders/{r['id']}").json()["model"]
    assert model["estanca"]["amplada"] == 2.4 and model["estanca"]["alcada"] == 2.5
    model["materials"][0]["foto_document_id"] = doc
    model["elements"].append({"id": "e1", "tipus": "lavabo", "nom": "lavabo", "paret": "nord", "posicio": 1.2,
                              "amplada": 0.6, "fondaria": 0.45, "alcada": 0.18, "alcada_terra": 0.7})
    assert c.put(f"/api/renders/{r['id']}", json={"model": model, "visible_client": True}).status_code == 200
    assert c.put(f"/api/renders/{r['id']}", json={"model": {"estanca": {}}}).status_code == 400
    token = c.get(f"/api/feines/{f['id']}").json()["token"]
    portal = c.get(f"/api/portal/{token}").json()
    assert portal["renders"][0]["id"] == r["id"]
    assert c.get(f"/api/portal/{token}/renders/{r['id']}").json()["model"]["elements"][0]["tipus"] == "lavabo"


def test_impostos_i_gestor(c):
    est = c.get("/api/impostos/estimacio").json()
    assert "irpf_130" in est["real"] and est["real"]["iva_resultat"] == round(est["real"]["iva_repercutit"] - est["real"]["iva_suportat"], 2)
    r = c.get("/api/gestor/paquet")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    noms = z.namelist()
    assert "llibre_factures_emeses.csv" in noms and "llibre_factures_rebudes.csv" in noms and "LLEGEIX-ME.txt" in noms
    assert any(n.startswith("factures_emeses/") for n in noms)
