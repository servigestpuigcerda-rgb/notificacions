"""Prova del flux complet amb dades inventades (cap dada real)."""
import os
import tempfile

os.environ["GESTIO_DATA_DIR"] = tempfile.mkdtemp(prefix="gestio-test-")
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        r = client.post("/api/setup", json={"nom": "Admin", "usuari": "admin", "password": "contrasenya1",
                                            "empresa_nom": "Empresa Prova SL"})
        assert r.status_code == 200, r.text
        client.put("/api/config", json={"empresa_nif": "B00000000", "empresa_adreca": "Carrer Fictici 1"})
        yield client


def partida(c, tipus):
    return next(p["id"] for p in c.get("/api/partides").json() if p["tipus"] == tipus)


def test_sense_sessio():
    with TestClient(app) as anon:
        assert anon.get("/api/feines").status_code == 401


def test_flux_complet(c):
    mo, mat = partida(c, "ma_obra"), partida(c, "material")
    art = c.post("/api/articles", json={"nom": "Rajola prova", "unitat": "m2", "cost": 10, "marge_pct": 50,
                                        "partida_id": mat}).json()["id"]
    a = next(x for x in c.get("/api/articles").json() if x["id"] == art)
    assert a["preu_venda"] == 15

    f = c.post("/api/feines", json={"nom": "Bany de prova", "tipus": "bany",
                                    "client_nou": {"nom": "Client Fictici", "nif": "00000000T", "adreca": "Adreça fictícia"}}).json()
    fid = f["id"]
    p = c.post(f"/api/feines/{fid}/pressupostos", json={"titol": "Reforma bany", "linies": [
        {"descripcio": "Mà d'obra paleta", "partida_id": mo, "quantitat": 10, "unitat": "h", "cost_unitari": 25, "preu_unitari": 40},
        {"descripcio": "Rajola", "article_id": art, "partida_id": mat, "quantitat": 20, "unitat": "m2", "cost_unitari": 10, "preu_unitari": 15},
    ]}).json()
    pid = p["id"]
    det = c.get(f"/api/pressupostos/{pid}").json()
    assert det["totals"]["base"] == 700
    assert det["totals"]["cost"] == 450
    assert det["totals"]["hores"] == 10
    assert det["totals"]["total"] == 847

    rev = c.get(f"/api/pressupostos/{pid}/revisio").json()
    assert any("historial" in a["text"] for a in rev["avisos"])

    env = c.post(f"/api/pressupostos/{pid}/enviar").json()
    token = env["token"]
    portal = c.get(f"/api/portal/{token}").json()
    assert portal["pressupostos"][0]["total"] == 847
    assert c.post(f"/api/portal/{token}/pressupostos/{pid}/acceptar", json={"nom": "", "accepto": True}).status_code == 400
    assert c.post(f"/api/portal/{token}/pressupostos/{pid}/acceptar", json={"nom": "Client Fictici", "accepto": True}).status_code == 200
    # Un pressupost acceptat no es pot modificar
    assert c.put(f"/api/pressupostos/{pid}", json={"titol": "x"}).status_code == 400

    c.post("/api/hores", json={"feina_id": fid, "hores": 12, "cost_hora": 25})
    c.post("/api/despeses", json={"feina_id": fid, "proveidor": "Magatzem Prova", "partida_id": mat, "total": 290.4, "iva_pct": 21})
    # Despesa fora de pressupost repercutible amb benefici
    c.post("/api/despeses", json={"feina_id": fid, "proveidor": "Magatzem Prova", "total": 121, "iva_pct": 21,
                                  "facturable": True, "marge_pct": 30, "concepte": "Mampara"})
    resum = c.get(f"/api/feines/{fid}").json()["resum"]
    assert resum["contractat"] == 700
    assert resum["cost_real"] == 12 * 25 + 240 + 100
    assert resum["hores_reals"] == 12
    assert any("Hores reals" in a for a in resum["alertes"])
    assert resum["pendent_facturar"] == 700 + 130

    # Aprenentatge del proveïdor: la següent despesa s'imputa sola a la partida
    d = c.post("/api/despeses", json={"feina_id": fid, "proveidor": "magatzem prova", "total": 12.1}).json()
    assert next(x for x in c.get(f"/api/despeses?feina_id={fid}").json() if x["id"] == d["id"])["partida_id"] == mat
    c.delete(f"/api/despeses/{d['id']}")

    # Factura parcial: 40% del pressupost
    fac = c.post(f"/api/feines/{fid}/factures", json={"pct": 40}).json()["id"]
    fd = c.get(f"/api/factures/{fac}").json()
    assert fd["base"] == 280
    assert c.get(f"/api/feines/{fid}/pendent").json()["total"] == 550
    em = c.post(f"/api/factures/{fac}/emetre").json()
    assert em["codi"].endswith("-0001")
    assert c.put(f"/api/factures/{fac}", json={"concepte": "x"}).status_code == 400

    # Segona factura: la despesa repercutida
    pend = c.get(f"/api/feines/{fid}/pendent").json()
    desp = pend["despeses"][0]
    fac2 = c.post(f"/api/feines/{fid}/factures", json={"items": [{"origen_tipus": "despesa", "origen_id": desp["origen_id"]}]}).json()["id"]
    assert c.get(f"/api/factures/{fac2}").json()["base"] == 130
    c.post(f"/api/factures/{fac2}/emetre")
    c.post(f"/api/factures/{fac2}/cobrar")

    # Rectificativa
    r = c.post(f"/api/factures/{fac}/rectificar", json={"motiu": "error"}).json()
    rf = c.get(f"/api/factures/{r['id']}").json()
    assert rf["base"] == -280 and rf["codi"]
    assert c.get(f"/api/feines/{fid}/pendent").json()["total"] == 700

    imp = c.get("/api/impostos").json()
    assert imp["iva_repercutit"] == round((280 - 280 + 130) * 0.21, 2)

    # Tancament: queda pendent, cal forçar
    assert c.post(f"/api/feines/{fid}/tancar").status_code == 400
    assert c.post(f"/api/feines/{fid}/tancar", json={"forcar": True}).status_code == 200
    msgs = c.get(f"/api/feines/{fid}/missatges").json()
    tipus = {m["tipus"] for m in msgs}
    assert {"pressupost", "acceptacio", "factura", "tancament"} <= tipus
    portal = c.get(f"/api/portal/{token}").json()
    assert all(m["tipus"] != "nota" for m in portal["missatges"])

    docs = c.get(f"/api/documents?feina_id={fid}").json()
    assert any(d["tipus"] == "factura" for d in docs["fitxers"])
    assert c.get(f"/imprimir/factura/{fac}").status_code == 200
    assert c.get(f"/p/{token}/imprimir/pressupost/{pid}").status_code == 200

    # Historial: una feina tancada de tipus bany amb 12 h reals sobre 10 previstes
    f2 = c.post("/api/feines", json={"nom": "Bany nou", "tipus": "bany"}).json()["id"]
    p2 = c.post(f"/api/feines/{f2}/pressupostos", json={"linies": [
        {"descripcio": "Mà d'obra paleta", "partida_id": mo, "quantitat": 10, "unitat": "h", "cost_unitari": 25, "preu_unitari": 40}]}).json()["id"]
    ap = c.get("/api/aprenentatge").json()
    assert ap["general"]["feines"] == 1
    assert c.get(f"/api/semblants?text=paleta bany").json()


def test_albara_signat(c):
    fid = c.post("/api/feines", json={"nom": "Feina albarà"}).json()["id"]
    h = c.post("/api/hores", json={"feina_id": fid, "hores": 3}).json()["id"]
    a = c.post(f"/api/feines/{fid}/albarans", json={"descripcio": "Reparació", "hores_ids": [h],
                                                    "linies": [{"descripcio": "Aixeta", "quantitat": 1}]}).json()["id"]
    assert c.post(f"/api/albarans/{a}/signar", json={"nom": "Signant", "signatura": "data:image/png;base64,AAAA"}).status_code == 200
    assert c.delete(f"/api/albarans/{a}").status_code == 400
    assert "Aixeta" in c.get(f"/imprimir/albara/{a}").text


def test_ia_desactivada(c):
    r = c.post("/api/ia/pressupost", json={"text": "Pintar un pis de 80 m2"})
    assert r.status_code == 422


def test_ia_document_i_pressupost_simulat(c, monkeypatch):
    """Comprova el circuit de la IA amb un client simulat (sense cridar l'API real)."""
    from types import SimpleNamespace
    from app import ai

    crides = []

    def parse(**kw):
        crides.append(kw)
        fmt = kw["output_format"]
        if fmt is ai.DadesDocument:
            out = ai.DadesDocument(tipus_doc="tiquet", proveidor="Magatzem Prova", concepte="Ciment", total=24.2,
                                   iva_pct=21, partida_suggerida="Material", confianca=0.9)
        else:
            out = ai.PropostaPressupost(titol="Pintura", linies=[ai.LiniaProposta(
                descripcio="Pintar parets", partida="Mà d'obra", quantitat=10, unitat="h", cost_unitari=25, preu_unitari=38)])
        return SimpleNamespace(stop_reason="end_turn", parsed_output=out)

    fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prova")
    monkeypatch.setattr(ai, "_client", lambda: fake)

    r = c.post("/api/ia/document", files={"fitxer": ("t.jpg", b"\xff\xd8\xff fals", "image/jpeg")}).json()
    assert r["error"] is None
    assert r["dades"]["base"] == 20 and r["dades"]["partida_id"]
    assert crides[0]["fallbacks"] == "default" and crides[0]["messages"][0]["content"][0]["type"] == "image"
    # No s'envien dades de clients a la IA
    assert "Client Fictici" not in str(crides[0]["messages"])

    p = c.post("/api/ia/pressupost", json={"text": "Pintar un pis de 80 m2 amb dues capes"}).json()
    assert p["linies"][0]["partida_id"]
    assert "Client Fictici" not in str(crides[1]["messages"])
