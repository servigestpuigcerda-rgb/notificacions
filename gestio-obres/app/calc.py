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


# ------------------------------------------------------------ bloquejos

def _eur(v) -> str:
    return f"{(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def bloquejos(feina_id: int) -> list:
    """El que el client ha de fer perquè la feina comenci o continuï."""
    res = []
    for p in db.rows("SELECT id, numero, tipus, titol FROM pressupostos WHERE feina_id = ? AND estat = 'enviat' ORDER BY id",
                     (feina_id,)):
        t = totals_pressupost(p["id"])
        if p["tipus"] == "principal":
            res.append({"tipus": "pressupost", "ref_id": p["id"],
                        "text": f"Pendent d'acceptar el pressupost {p['numero']} ({_eur(t['total'])}). "
                                "La feina no es pot començar fins que l'accepteu."})
        else:
            res.append({"tipus": "canvi", "ref_id": p["id"],
                        "text": f"Pendent d'acceptar els canvis {p['numero']} {p['titol'] or ''} ({_eur(t['total'])}). "
                                "Aquests treballs no es faran, i si afecten la resta, la feina queda aturada, fins que els accepteu."})
    for f in db.rows("SELECT id, codi, total, venciment FROM factures WHERE feina_id = ? AND estat = 'emesa' AND bloqueja = 1 "
                     "AND rectifica_id IS NULL ORDER BY data", (feina_id,)):
        res.append({"tipus": "pagament", "ref_id": f["id"],
                    "text": f"Pendent de pagament la factura {f['codi']} ({_eur(f['total'])}). "
                            "La feina es reprendrà quan rebem l'ingrés."})
    return res


def pendent_client(feina_id: int) -> dict:
    """Què li queda al client: factures per pagar i resta de l'obra per facturar (IVA inclòs, aproximat)."""
    per_pagar = db.scalar("SELECT COALESCE(SUM(total),0) FROM factures WHERE feina_id = ? AND estat = 'emesa'", (feina_id,))
    p = db.row("SELECT iva_pct, irpf_pct FROM pressupostos WHERE feina_id = ? AND estat = 'acceptat' ORDER BY id LIMIT 1", (feina_id,))
    iva = (p["iva_pct"] if p else db.setting_float("iva_defecte", 21)) - (p["irpf_pct"] if p else 0)
    resta = pendent_facturar(feina_id)["total"]
    return {"per_pagar": r2(per_pagar), "per_facturar": r2(resta * (1 + iva / 100)),
            "total": r2(per_pagar + resta * (1 + iva / 100))}


# --------------------------------------------------- estimació d'impostos

def _rendiment(ini: str, fi: str) -> dict:
    ing = db.row("SELECT COALESCE(SUM(base),0) AS base, COALESCE(SUM(irpf_import),0) AS ret FROM factures "
                 "WHERE estat IN ('emesa','cobrada','anullada') AND numero IS NOT NULL AND data >= ? AND data < ?", (ini, fi))
    desp = db.scalar("SELECT COALESCE(SUM(base),0) FROM despeses WHERE data >= ? AND data < ?", (ini, fi))
    return {"ingressos": ing["base"], "despeses": desp, "retencions": ing["ret"]}


def estimacio_trimestre(any_: int, trimestre: int, avui: str | None = None) -> dict:
    """Estimació de l'IVA (303) i del pagament fraccionat d'IRPF (130) del trimestre.

    Inclou el real fins avui i una projecció lineal a final de trimestre. És orientativa."""
    from datetime import date
    avui_d = date.fromisoformat(avui or db.today())
    real = resum_impostos(any_, trimestre)
    ini = date.fromisoformat(real["periode"]["inici"])
    fi = date.fromisoformat(real["periode"]["fi"])
    total_dies = (fi - ini).days
    transcorreguts = min(max((avui_d - ini).days + 1, 0), total_dies)
    factor = total_dies / transcorreguts if 0 < transcorreguts < total_dies else 1
    en_curs = 0 < transcorreguts < total_dies

    # IRPF model 130 (estimació directa): 20% del rendiment acumulat de l'any
    pct = db.setting_float("irpf_fraccionat_pct", 20)

    def quota_130(fins_tri: int, proj: float = 1.0) -> float:
        fi_t = f"{any_ + 1}-01-01" if fins_tri == 4 else f"{any_}-{fins_tri * 3 + 1:02d}-01"
        acum = _rendiment(f"{any_}-01-01", fi_t)
        if proj != 1.0:
            q = _rendiment(real["periode"]["inici"], real["periode"]["fi"])
            acum = {k: acum[k] + q[k] * (proj - 1) for k in acum}
        base = (acum["ingressos"] - acum["despeses"]) * pct / 100 - acum["retencions"]
        anteriors = sum(max(quota_130(t), 0) for t in range(1, fins_tri)) if fins_tri > 1 else 0
        return r2(max(base - anteriors, 0))

    regim = db.setting("regim_fiscal", "autonom")
    esborranys = db.row("SELECT COUNT(*) AS n, COALESCE(SUM(base),0) AS base, COALESCE(SUM(iva_import),0) AS iva "
                        "FROM factures WHERE estat = 'esborrany'")
    res = {
        "any": any_, "trimestre": trimestre, "regim": regim, "en_curs": en_curs,
        "dies": {"transcorreguts": transcorreguts, "total": total_dies},
        "real": {"iva_repercutit": real["iva_repercutit"], "iva_suportat": real["iva_suportat"],
                 "iva_resultat": real["resultat_iva"], "ingressos": real["ingressos"], "despeses": real["despeses"],
                 "retencions": real["retencions_irpf"]},
        "projeccio": {"iva_repercutit": r2(real["iva_repercutit"] * factor), "iva_suportat": r2(real["iva_suportat"] * factor),
                      "iva_resultat": r2(real["resultat_iva"] * factor), "ingressos": r2(real["ingressos"] * factor),
                      "despeses": r2(real["despeses"] * factor)},
        "esborranys": esborranys,
        "avis_tiquets": real["avis_tiquets"],
    }
    if regim == "autonom":
        res["real"]["irpf_130"] = quota_130(trimestre)
        res["projeccio"]["irpf_130"] = quota_130(trimestre, factor) if en_curs else res["real"]["irpf_130"]
        res["irpf_pct"] = pct
    return res


# --------------------------------------------------- anàlisi de tancament

def analisi_feina(feina_id: int) -> dict:
    """Dades i conclusions objectives d'una feina per aprendre'n."""
    from datetime import date
    f = db.row("SELECT * FROM feines WHERE id = ?", (feina_id,))
    r = resum_feina(feina_id)
    pres = r["pressupostos"]
    principal = sum(p["totals"]["base"] for p in pres if p["estat"] == "acceptat" and p["tipus"] == "principal")
    extres = [p for p in pres if p["estat"] == "acceptat" and p["tipus"] == "extra"]
    extres_import = sum(p["totals"]["base"] for p in extres)
    marge_real = r2((r["contractat"] - r["cost_real"]) / r["contractat"] * 100) if r["contractat"] else None
    cobraments = db.rows("SELECT data, cobrada_at FROM factures WHERE feina_id = ? AND estat = 'cobrada' AND cobrada_at IS NOT NULL", (feina_id,))
    dies_cobrament = [(date.fromisoformat(c["cobrada_at"][:10]) - date.fromisoformat(c["data"][:10])).days for c in cobraments]
    val = db.row("SELECT COUNT(*) AS n, AVG(puntuacio) AS mitjana FROM valoracions WHERE feina_id = ?", (feina_id,))
    comentaris = [v["comentari"] for v in db.rows("SELECT comentari FROM valoracions WHERE feina_id = ? AND comentari <> ''", (feina_id,))]
    durada = None
    if f["data_inici"] and f["data_fi"]:
        durada = (date.fromisoformat(f["data_fi"][:10]) - date.fromisoformat(f["data_inici"][:10])).days + 1

    be, malament, propostes = [], [], []
    tipus = f["tipus"] or "aquest tipus"
    if marge_real is not None:
        if marge_real >= r["marge_previst_pct"] - 2:
            be.append(f"Marge real {marge_real:.1f}% (previst {r['marge_previst_pct']:.1f}%).")
        else:
            malament.append(f"Marge real {marge_real:.1f}%, per sota del previst ({r['marge_previst_pct']:.1f}%).")
    if r["hores_previstes"]:
        dh = (r["hores_reals"] / r["hores_previstes"] - 1) * 100
        if dh > 10:
            malament.append(f"Hores reals un {dh:.0f}% per sobre de les pressupostades ({r['hores_reals']:.1f} h vs {r['hores_previstes']:.1f} h).")
            propostes.append(f"En feines de {tipus}, pressuposta un {dh:.0f}% més d'hores de mà d'obra.")
        elif dh < -10:
            be.append(f"S'han fet un {-dh:.0f}% menys d'hores de les previstes.")
            propostes.append(f"En feines de {tipus} es pot ajustar el preu: es van fer menys hores de les previstes.")
        else:
            be.append("Les hores s'han ajustat al pressupost.")
    for p in r["partides"]:
        if p["previst"] and p["pct"] and p["pct"] > 110:
            malament.append(f"Partida «{p['nom']}» desviada un {p['pct'] - 100:.0f}% (+{p['desviacio']:.2f} €).")
            propostes.append(f"Revisa l'amidament i els preus de «{p['nom']}» en feines de {tipus}.")
        elif not p["previst"] and p["real"] > 50:
            malament.append(f"Cost no previst a «{p['nom']}»: {p['real']:.2f} €.")
            propostes.append(f"Inclou la partida «{p['nom']}» als pressupostos de {tipus}.")
    if principal and extres_import / principal > 0.1:
        malament.append(f"Treballs fora de pressupost per {extres_import:.2f} € ({extres_import / principal * 100:.0f}% del principal).")
        propostes.append("Fes una visita i un amidament més detallats abans de pressupostar: hi ha hagut molts canvis.")
    elif extres:
        be.append(f"Els canvis ({len(extres)}) s'han pressupostat i acceptat abans de fer-los.")
    if r["pendent_facturar"] > 0.01:
        malament.append(f"S'ha tancat amb {r['pendent_facturar']:.2f} € per facturar.")
    if r["pendent_cobrar"] > 0.01:
        malament.append(f"Queden {r['pendent_cobrar']:.2f} € pendents de cobrar.")
    if dies_cobrament:
        mitjana = sum(dies_cobrament) / len(dies_cobrament)
        (be if mitjana <= 30 else malament).append(f"Cobrament mitjà en {mitjana:.0f} dies.")
        if mitjana > 30:
            propostes.append("Demana una bestreta en acceptar i factura per certificacions més freqüents.")
    if val["n"]:
        (be if val["mitjana"] >= 4 else malament).append(f"Valoració del client: {val['mitjana']:.1f}/5 ({val['n']}).")
    return {
        "feina": {"codi": f["codi"], "nom": f["nom"], "tipus": f["tipus"]},
        "xifres": {"contractat": r["contractat"], "principal": r2(principal), "extres": r2(extres_import), "n_extres": len(extres),
                   "cost_previst": r["cost_previst"], "cost_real": r["cost_real"], "marge_previst_pct": r["marge_previst_pct"],
                   "marge_real_pct": marge_real, "hores_previstes": r["hores_previstes"], "hores_reals": r["hores_reals"],
                   "facturat": r["facturat"], "cobrat": r["cobrat"], "pendent_facturar": r["pendent_facturar"],
                   "durada_dies": durada, "dies_cobrament": r2(sum(dies_cobrament) / len(dies_cobrament)) if dies_cobrament else None,
                   "valoracio": r2(val["mitjana"]) if val["n"] else None},
        "partides": r["partides"],
        "comentaris_client": comentaris,
        "be": be, "malament": malament, "propostes": propostes,
    }
