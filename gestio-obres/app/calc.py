"""Càlculs: totals de pressupostos i factures, estat econòmic de les feines,
pendent de facturar i resum d'impostos."""
from . import db

ESTATS_FACTURA_VALIDS = ("esborrany", "emesa", "cobrada")


def r2(x) -> float:
    return round((x or 0) + 1e-9, 2)


def preu_article(article: dict) -> float:
    """Preu de venda d'un article: preu fix o cost + marge."""
    if article.get("preu") not in (None, ""):
        return r2(article["preu"])
    marge = article.get("marge_pct")
    if marge is None:
        marge = db.setting_float("marge_defecte", 20)
    return r2(article.get("cost", 0) * (1 + marge / 100))


def import_linia(l: dict) -> float:
    return r2(l["quantitat"] * l["preu_unitari"] * (1 - (l.get("descompte_pct") or 0) / 100))


def es_hora(l: dict) -> bool:
    return (l.get("unitat") or "").lower().strip(". ") in ("h", "hora", "hores", "hr", "hrs")


def partides_map() -> dict:
    return {p["id"]: p for p in db.rows("SELECT * FROM partides")}


def totals_pressupost(pressupost_id: int) -> dict:
    p = db.row("SELECT * FROM pressupostos WHERE id = ?", (pressupost_id,))
    linies = db.rows("SELECT * FROM linies_pressupost WHERE pressupost_id = ? ORDER BY ordre, id", (pressupost_id,))
    pm = partides_map()
    subtotal = cost = hores = 0.0
    per_partida = {}
    for l in linies:
        imp = import_linia(l)
        c = r2(l["quantitat"] * l["cost_unitari"])
        l["import"] = imp
        l["cost"] = c
        subtotal += imp
        cost += c
        part = pm.get(l["partida_id"]) or {}
        if part.get("tipus") == "ma_obra" and es_hora(l):
            hores += l["quantitat"]
        key = l["partida_id"] or 0
        pp = per_partida.setdefault(key, {"partida_id": l["partida_id"], "nom": part.get("nom", "Sense partida"),
                                          "tipus": part.get("tipus"), "import": 0.0, "cost": 0.0})
        pp["import"] = r2(pp["import"] + imp * (1 - p["descompte_pct"] / 100))
        pp["cost"] = r2(pp["cost"] + c)
    descompte = r2(subtotal * p["descompte_pct"] / 100)
    base = r2(subtotal - descompte)
    iva = r2(base * p["iva_pct"] / 100)
    irpf = r2(base * p["irpf_pct"] / 100)
    benefici = r2(base - cost)
    return {
        "linies": linies,
        "subtotal": r2(subtotal),
        "descompte": descompte,
        "base": base,
        "iva": iva,
        "irpf": irpf,
        "total": r2(base + iva - irpf),
        "cost": r2(cost),
        "benefici": benefici,
        "marge_pct": r2(benefici / base * 100) if base else 0,
        "hores": r2(hores),
        "per_partida": list(per_partida.values()),
    }


def recalcula_factura(factura_id: int):
    f = db.row("SELECT * FROM factures WHERE id = ?", (factura_id,))
    linies = db.rows("SELECT * FROM linies_factura WHERE factura_id = ?", (factura_id,))
    base = 0.0
    with db.tx() as conn:
        for l in linies:
            imp = import_linia(l)
            base += imp
            conn.execute("UPDATE linies_factura SET import = ? WHERE id = ?", (imp, l["id"]))
        base = r2(base)
        iva = r2(base * f["iva_pct"] / 100)
        irpf = r2(base * f["irpf_pct"] / 100)
        conn.execute("UPDATE factures SET base = ?, iva_import = ?, irpf_import = ?, total = ? WHERE id = ?",
                     (base, iva, irpf, r2(base + iva - irpf), factura_id))


def _facturat_per_origen(tipus: str) -> dict:
    """Import ja facturat (o en esborrany) per a cada element d'origen."""
    res = db.rows(
        "SELECT lf.origen_id AS id, SUM(lf.import) AS imp FROM linies_factura lf "
        "JOIN factures f ON f.id = lf.factura_id "
        f"WHERE lf.origen_tipus = ? AND f.estat IN {ESTATS_FACTURA_VALIDS} GROUP BY lf.origen_id", (tipus,))
    return {r["id"]: r["imp"] or 0 for r in res}


def pendent_facturar(feina_id: int) -> dict:
    """Tot el que queda per facturar d'una feina, element a element."""
    feina = db.row("SELECT * FROM feines WHERE id = ?", (feina_id,))
    fet_linies = _facturat_per_origen("linia_pressupost")
    fet_desp = _facturat_per_origen("despesa")
    fet_hores = _facturat_per_origen("hores")

    linies = []
    for p in db.rows("SELECT * FROM pressupostos WHERE feina_id = ? AND estat = 'acceptat' ORDER BY id", (feina_id,)):
        t = totals_pressupost(p["id"])
        for l in t["linies"]:
            net = r2(l["import"] * (1 - p["descompte_pct"] / 100))
            fet = r2(fet_linies.get(l["id"], 0))
            if net - fet > 0.009:
                linies.append({
                    "origen_tipus": "linia_pressupost", "origen_id": l["id"],
                    "pressupost": p["numero"], "pressupost_tipus": p["tipus"],
                    "descripcio": l["descripcio"], "total": net, "facturat": fet,
                    "pendent": r2(net - fet), "pct_facturat": r2(fet / net * 100) if net else 0,
                })

    despeses = []
    for d in db.rows("SELECT * FROM despeses WHERE feina_id = ? AND facturable = 1 ORDER BY data", (feina_id,)):
        imp = r2(d["base"] * (1 + d["marge_pct"] / 100))
        fet = r2(fet_desp.get(d["id"], 0))
        if imp - fet > 0.009:
            despeses.append({
                "origen_tipus": "despesa", "origen_id": d["id"],
                "descripcio": f"{d['concepte'] or 'Material'} ({d['proveidor'] or ''} {d['num_document'] or ''})".strip(),
                "data": d["data"], "cost": d["base"], "marge_pct": d["marge_pct"],
                "total": imp, "facturat": fet, "pendent": r2(imp - fet),
            })

    hores = []
    for h in db.rows("SELECT * FROM hores WHERE feina_id = ? AND facturable = 1 ORDER BY data", (feina_id,)):
        imp = r2(h["hores"] * h["preu_hora"])
        fet = r2(fet_hores.get(h["id"], 0))
        if imp - fet > 0.009:
            hores.append({
                "origen_tipus": "hores", "origen_id": h["id"],
                "descripcio": f"Mà d'obra {h['data']} {h['treballador'] or ''} ({h['hores']} h)".strip(),
                "hores": h["hores"], "preu_hora": h["preu_hora"],
                "total": imp, "facturat": fet, "pendent": r2(imp - fet),
            })

    total = r2(sum(x["pendent"] for x in linies + despeses + hores))
    return {"feina": feina, "linies_pressupost": linies, "despeses": despeses, "hores": hores, "total": total}


def resum_feina(feina_id: int) -> dict:
    """Com va una feina: previst vs real, facturat, cobrat i pendent."""
    pm = partides_map()
    pressupostos = db.rows("SELECT * FROM pressupostos WHERE feina_id = ? ORDER BY id", (feina_id,))
    contractat = cost_previst = hores_previstes = 0.0
    previst_partida = {}
    pendent_acceptar = 0.0
    for p in pressupostos:
        t = totals_pressupost(p["id"])
        p["totals"] = {k: t[k] for k in ("base", "total", "cost", "benefici", "marge_pct", "hores")}
        if p["estat"] == "acceptat":
            contractat += t["base"]
            cost_previst += t["cost"]
            hores_previstes += t["hores"]
            for pp in t["per_partida"]:
                d = previst_partida.setdefault(pp["partida_id"] or 0, {"previst": 0.0, "venda": 0.0})
                d["previst"] += pp["cost"]
                d["venda"] += pp["import"]
        elif p["estat"] == "enviat":
            pendent_acceptar += t["base"]

    despeses = db.rows("SELECT partida_id, SUM(base) AS base FROM despeses WHERE feina_id = ? GROUP BY partida_id", (feina_id,))
    hores = db.row("SELECT COALESCE(SUM(hores),0) AS h, COALESCE(SUM(hores*cost_hora),0) AS cost, "
                   "COALESCE(SUM(hores*preu_hora),0) AS venda FROM hores WHERE feina_id = ?", (feina_id,))
    real_partida = {(d["partida_id"] or 0): d["base"] or 0 for d in despeses}
    ma_obra_ids = [pid for pid, p in pm.items() if p["tipus"] == "ma_obra"]
    ma_obra_id = ma_obra_ids[0] if ma_obra_ids else 0
    real_partida[ma_obra_id] = real_partida.get(ma_obra_id, 0) + hores["cost"]
    cost_real = sum(real_partida.values())

    partides = []
    for pid in sorted(set(previst_partida) | set(real_partida), key=lambda x: (pm.get(x) or {}).get("ordre", 99)):
        prev = r2(previst_partida.get(pid, {}).get("previst", 0))
        real = r2(real_partida.get(pid, 0))
        partides.append({
            "partida_id": pid or None, "nom": (pm.get(pid) or {}).get("nom", "Sense partida"),
            "previst": prev, "real": real, "desviacio": r2(real - prev),
            "pct": r2(real / prev * 100) if prev else None,
        })

    fact = db.row(
        "SELECT COALESCE(SUM(base),0) AS base, COALESCE(SUM(total),0) AS total, "
        "COALESCE(SUM(CASE WHEN estat='cobrada' THEN total ELSE 0 END),0) AS cobrat "
        "FROM factures WHERE feina_id = ? AND estat IN ('emesa','cobrada') AND rectifica_id IS NULL", (feina_id,))
    esborranys = db.scalar("SELECT COUNT(*) FROM factures WHERE feina_id = ? AND estat = 'esborrany'", (feina_id,))
    pend = pendent_facturar(feina_id)

    contractat = r2(contractat)
    cost_previst = r2(cost_previst)
    cost_real = r2(cost_real)
    cost_restant = max(cost_previst - cost_real, 0)
    # Tot el que s'ha facturat més tot el que queda per facturar.
    base_esborranys = db.scalar("SELECT COALESCE(SUM(base),0) FROM factures WHERE feina_id = ? AND estat = 'esborrany'", (feina_id,))
    ingressos_previstos = r2(fact["base"] + base_esborranys + pend["total"])
    alertes = []
    if cost_previst and cost_real > cost_previst:
        alertes.append(f"El cost real ({cost_real:.2f} €) ja supera el cost previst ({cost_previst:.2f} €).")
    elif cost_previst and cost_real > cost_previst * 0.85:
        alertes.append(f"Ja s'ha consumit el {cost_real / cost_previst * 100:.0f}% del cost previst.")
    if hores_previstes and hores["h"] > hores_previstes:
        alertes.append(f"Hores reals ({hores['h']:.1f} h) per sobre de les pressupostades ({hores_previstes:.1f} h).")
    for p in partides:
        if p["previst"] and p["real"] > p["previst"] * 1.1:
            alertes.append(f"Partida «{p['nom']}» desviada un {p['pct'] - 100:.0f}%.")
    sense_partida = db.scalar("SELECT COUNT(*) FROM despeses WHERE feina_id = ? AND (partida_id IS NULL OR estat='pendent_revisio')", (feina_id,))
    if sense_partida:
        alertes.append(f"{sense_partida} despesa(es) pendents de revisar o sense partida.")

    return {
        "contractat": contractat,
        "pendent_acceptar": r2(pendent_acceptar),
        "cost_previst": cost_previst,
        "cost_real": cost_real,
        "benefici_previst": r2(contractat - cost_previst),
        "marge_previst_pct": r2((contractat - cost_previst) / contractat * 100) if contractat else 0,
        "benefici_projectat": r2(ingressos_previstos - cost_real - cost_restant),
        "resultat_actual": r2(fact["base"] - cost_real),
        "hores_previstes": r2(hores_previstes),
        "hores_reals": r2(hores["h"]),
        "facturat": r2(fact["base"]),
        "facturat_total": r2(fact["total"]),
        "cobrat": r2(fact["cobrat"]),
        "pendent_cobrar": r2(fact["total"] - fact["cobrat"]),
        "pendent_facturar": pend["total"],
        "factures_esborrany": esborranys,
        "pct_facturat": r2(fact["base"] / contractat * 100) if contractat else 0,
        "pct_cost": r2(cost_real / cost_previst * 100) if cost_previst else 0,
        "partides": partides,
        "pressupostos": pressupostos,
        "alertes": alertes,
    }


def resum_impostos(any_: int, trimestre: int | None = None) -> dict:
    """IVA repercutit (factures emeses) i suportat (despeses), i retencions d'IRPF.

    És una ajuda per preparar els models 303/130; no substitueix la revisió de la gestoria."""
    if trimestre:
        mes_ini = (trimestre - 1) * 3 + 1
        ini = f"{any_}-{mes_ini:02d}-01"
        fi = f"{any_ + 1}-01-01" if trimestre == 4 else f"{any_}-{mes_ini + 3:02d}-01"
    else:
        ini, fi = f"{any_}-01-01", f"{any_ + 1}-01-01"
    rep = db.rows(
        "SELECT iva_pct, SUM(base) AS base, SUM(iva_import) AS iva, SUM(irpf_import) AS irpf, COUNT(*) AS n "
        "FROM factures WHERE estat IN ('emesa','cobrada','anullada') AND numero IS NOT NULL "
        "AND data >= ? AND data < ? GROUP BY iva_pct ORDER BY iva_pct", (ini, fi))
    sup = db.rows(
        "SELECT iva_pct, SUM(base) AS base, SUM(iva_import) AS iva, COUNT(*) AS n FROM despeses "
        "WHERE tipus_doc IN ('factura','tiquet') AND data >= ? AND data < ? GROUP BY iva_pct ORDER BY iva_pct", (ini, fi))
    sense_fra = db.row(
        "SELECT COUNT(*) AS n, COALESCE(SUM(iva_import),0) AS iva FROM despeses WHERE tipus_doc = 'tiquet' "
        "AND (proveidor_nif IS NULL OR proveidor_nif = '') AND data >= ? AND data < ?", (ini, fi))
    iva_rep = r2(sum(x["iva"] or 0 for x in rep))
    iva_sup = r2(sum(x["iva"] or 0 for x in sup))
    ingressos = r2(sum(x["base"] or 0 for x in rep))
    despeses = r2(sum(x["base"] or 0 for x in sup))
    hores_cost = db.scalar("SELECT COALESCE(SUM(hores*cost_hora),0) FROM hores WHERE data >= ? AND data < ?", (ini, fi))
    return {
        "periode": {"inici": ini, "fi": fi, "any": any_, "trimestre": trimestre},
        "repercutit": rep, "suportat": sup,
        "iva_repercutit": iva_rep, "iva_suportat": iva_sup,
        "resultat_iva": r2(iva_rep - iva_sup),
        "retencions_irpf": r2(sum(x["irpf"] or 0 for x in rep)),
        "ingressos": ingressos, "despeses": despeses,
        "cost_ma_obra_intern": r2(hores_cost),
        "rendiment": r2(ingressos - despeses),
        "avis_tiquets": (f"{sense_fra['n']} tiquet(s) sense NIF del proveïdor ({sense_fra['iva']:.2f} € d'IVA): "
                         "només és deduïble l'IVA de factures completes o simplificades amb les dades del destinatari."
                         if sense_fra["n"] else None),
    }
