"""Documents imprimibles (pressupost, factura, albarà) en HTML.
Des del navegador es poden desar com a PDF (Imprimeix → Desa com a PDF)."""
from html import escape

from . import calc, db


def _e(v) -> str:
    return escape(str(v)) if v not in (None, "") else ""


def eur(v) -> str:
    s = f"{(v or 0):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def num(v) -> str:
    v = v or 0
    return (f"{v:,.2f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v)}").replace(".", ",")


def data_cat(d) -> str:
    if not d:
        return ""
    d = str(d)[:10]
    y, m, dd = d.split("-")
    return f"{dd}/{m}/{y}"


CSS = """
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d2433;margin:0;background:#eef1f5}
.doc{max-width:860px;margin:24px auto;background:#fff;padding:40px 44px;box-shadow:0 2px 12px #0002}
header{display:flex;justify-content:space-between;gap:24px;border-bottom:3px solid #1f5fae;padding-bottom:16px}
h1{margin:0 0 4px;font-size:26px;color:#1f5fae;letter-spacing:.5px}.muted{color:#5b6475;font-size:13px;line-height:1.5}
.parts{display:flex;gap:24px;margin:22px 0}.parts>div{flex:1;background:#f5f7fa;border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.55}
.parts b{display:block;font-size:11px;text-transform:uppercase;color:#5b6475;letter-spacing:.6px;margin-bottom:4px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;background:#1f5fae;color:#fff;padding:8px;font-weight:600}
td{padding:8px;border-bottom:1px solid #e3e7ee;vertical-align:top}.r{text-align:right;white-space:nowrap}
.grup td{background:#f0f4fa;font-weight:600}
.totals{margin-left:auto;margin-top:16px;width:320px}.totals td{border:0;padding:4px 8px}.totals .t td{font-size:17px;font-weight:700;border-top:2px solid #1f5fae;padding-top:8px}
.notes{margin-top:24px;font-size:12px;color:#5b6475;white-space:pre-wrap;line-height:1.5}
.firma{margin-top:30px;display:flex;gap:30px}.firma div{flex:1;border-top:1px solid #aab;padding-top:6px;font-size:12px;color:#5b6475;min-height:90px}
.firma img{max-height:90px;display:block}
.bar{max-width:860px;margin:16px auto 0;display:flex;gap:8px;justify-content:flex-end}
.bar button{background:#1f5fae;color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:15px;cursor:pointer}
.estat{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;background:#e8f5ec;color:#1b7a3d;font-weight:600}
@media print{body{background:#fff}.doc{box-shadow:none;margin:0;padding:0}.bar{display:none}}
@media (max-width:640px){.doc{padding:20px 16px;margin:0}header,.parts{flex-direction:column}.totals{width:100%}th:nth-child(3),td:nth-child(3){display:none}}
"""


def _pagina(titol: str, cos: str) -> str:
    return (f"<!doctype html><html lang='ca'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{_e(titol)}</title>"
            f"<style>{CSS}</style></head><body>"
            f"<div class='bar'><button onclick='window.print()'>Imprimeix / PDF</button></div>"
            f"<div class='doc'>{cos}</div></body></html>")


def _empresa(s: dict) -> str:
    return "<br>".join(_e(x) for x in [s.get("empresa_nom"), s.get("empresa_nif") and f"NIF {s['empresa_nif']}",
                                       s.get("empresa_adreca"), s.get("empresa_telefon"), s.get("empresa_email")] if x)


def _client(c: dict | None) -> str:
    if not c:
        return ""
    return "<br>".join(_e(x) for x in [c.get("nom"), c.get("nif") and f"NIF {c['nif']}", c.get("adreca"),
                                       c.get("telefon"), c.get("email")] if x)


def pressupost(pid: int) -> str:
    s = db.settings()
    p = db.row("SELECT * FROM pressupostos WHERE id = ?", (pid,))
    f = db.row("SELECT * FROM feines WHERE id = ?", (p["feina_id"],))
    c = db.row("SELECT * FROM clients WHERE id = ?", (f["client_id"],)) if f["client_id"] else None
    t = calc.totals_pressupost(pid)
    pm = calc.partides_map()
    files = []
    actual = object()
    for l in t["linies"]:
        if l["partida_id"] != actual:
            actual = l["partida_id"]
            files.append(f"<tr class='grup'><td colspan='5'>{_e((pm.get(actual) or {}).get('nom', 'Altres'))}</td></tr>")
        desc = f" <span class='muted'>(-{num(l['descompte_pct'])}%)</span>" if l["descompte_pct"] else ""
        files.append(f"<tr><td>{_e(l['descripcio'])}</td><td class='r'>{num(l['quantitat'])} {_e(l['unitat'])}</td>"
                     f"<td class='r'>{eur(l['preu_unitari'])}</td><td class='r'>{desc}</td><td class='r'>{eur(l['import'])}</td></tr>")
    titol = "PRESSUPOST FORA DE PRESSUPOST" if p["tipus"] == "extra" else "PRESSUPOST"
    estat = ""
    if p["estat"] == "acceptat":
        estat = f"<p><span class='estat'>Acceptat el {data_cat(p['acceptat_at'])} per {_e(p['acceptat_per'])}</span></p>"
    cos = f"""
<header><div><h1>{titol}</h1><div class='muted'>Núm. {_e(p['numero'])}<br>Data {data_cat(p['data'])}<br>
Validesa {p['validesa_dies']} dies</div>{estat}</div><div class='muted' style='text-align:right'>{_empresa(s)}</div></header>
<div class='parts'><div><b>Client</b>{_client(c)}</div><div><b>Obra</b>{_e(f['nom'])}<br>{_e(f['adreca'])}<br>Ref. {_e(f['codi'])}</div></div>
{f"<p><b>{_e(p['titol'])}</b></p>" if p['titol'] else ''}
<table><thead><tr><th>Descripció</th><th class='r'>Quantitat</th><th class='r'>Preu</th><th class='r'>Dte.</th><th class='r'>Import</th></tr></thead>
<tbody>{''.join(files)}</tbody></table>
<table class='totals'>
<tr><td>Subtotal</td><td class='r'>{eur(t['subtotal'])}</td></tr>
{f"<tr><td>Descompte {num(p['descompte_pct'])}%</td><td class='r'>-{eur(t['descompte'])}</td></tr>" if t['descompte'] else ''}
<tr><td>Base imposable</td><td class='r'>{eur(t['base'])}</td></tr>
<tr><td>IVA {num(p['iva_pct'])}%</td><td class='r'>{eur(t['iva'])}</td></tr>
{f"<tr><td>Retenció IRPF {num(p['irpf_pct'])}%</td><td class='r'>-{eur(t['irpf'])}</td></tr>" if t['irpf'] else ''}
<tr class='t'><td>TOTAL</td><td class='r'>{eur(t['total'])}</td></tr></table>
<div class='notes'>{_e(p['notes'])}\n\n{_e(p['condicions'] or s.get('condicions_pressupost'))}</div>
<div class='firma'><div>Signatura empresa</div><div>Acceptació del client{('<br>' + _e(p['acceptat_per'])) if p['acceptat_per'] else ''}</div></div>"""
    return _pagina(f"Pressupost {p['numero']}", cos)


def factura(fid: int) -> str:
    s = db.settings()
    f = db.row("SELECT * FROM factures WHERE id = ?", (fid,))
    feina = db.row("SELECT * FROM feines WHERE id = ?", (f["feina_id"],)) if f["feina_id"] else None
    c = db.row("SELECT * FROM clients WHERE id = ?", (f["client_id"],)) if f["client_id"] else None
    linies = db.rows("SELECT * FROM linies_factura WHERE factura_id = ? ORDER BY id", (fid,))
    files = "".join(
        f"<tr><td>{_e(l['descripcio'])}</td><td class='r'>{num(l['quantitat'])}</td><td class='r'>{eur(l['preu_unitari'])}</td>"
        f"<td class='r'>{(num(l['descompte_pct']) + '%') if l['descompte_pct'] else ''}</td><td class='r'>{eur(l['import'])}</td></tr>"
        for l in linies)
    rect = ""
    if f["rectifica_id"]:
        o = db.row("SELECT codi, data FROM factures WHERE id = ?", (f["rectifica_id"],))
        rect = f"<p><b>Factura rectificativa de la factura {_e(o['codi'])} del {data_cat(o['data'])}</b></p>"
    titol = "FACTURA RECTIFICATIVA" if f["rectifica_id"] else ("ESBORRANY DE FACTURA" if f["estat"] == "esborrany" else "FACTURA")
    cos = f"""
<header><div><h1>{titol}</h1><div class='muted'>Núm. {_e(f['codi'] or '(pendent d’emetre)')}<br>Data {data_cat(f['data'])}<br>
{('Venciment ' + data_cat(f['venciment'])) if f['venciment'] else ''}</div></div><div class='muted' style='text-align:right'>{_empresa(s)}</div></header>
<div class='parts'><div><b>Client</b>{_client(c)}</div><div><b>Obra</b>{_e(feina['nom']) if feina else ''}<br>{_e(feina['adreca']) if feina else ''}<br>{('Ref. ' + _e(feina['codi'])) if feina else ''}</div></div>
{rect}{f"<p>{_e(f['concepte'])}</p>" if f['concepte'] else ''}
<table><thead><tr><th>Concepte</th><th class='r'>Quant.</th><th class='r'>Preu</th><th class='r'>Dte.</th><th class='r'>Import</th></tr></thead><tbody>{files}</tbody></table>
<table class='totals'>
<tr><td>Base imposable</td><td class='r'>{eur(f['base'])}</td></tr>
<tr><td>IVA {num(f['iva_pct'])}%</td><td class='r'>{eur(f['iva_import'])}</td></tr>
{f"<tr><td>Retenció IRPF {num(f['irpf_pct'])}%</td><td class='r'>-{eur(f['irpf_import'])}</td></tr>" if f['irpf_import'] else ''}
<tr class='t'><td>TOTAL</td><td class='r'>{eur(f['total'])}</td></tr></table>
<div class='notes'>{('Forma de pagament: transferència al compte ' + _e(s.get('empresa_iban'))) if s.get('empresa_iban') else ''}
{_e(f['notes'])}</div>"""
    return _pagina(f"Factura {f['codi'] or ''}", cos)


def albara(aid: int) -> str:
    s = db.settings()
    a = db.row("SELECT * FROM albarans WHERE id = ?", (aid,))
    feina = db.row("SELECT * FROM feines WHERE id = ?", (a["feina_id"],))
    c = db.row("SELECT * FROM clients WHERE id = ?", (feina["client_id"],)) if feina["client_id"] else None
    linies = db.rows("SELECT * FROM linies_albara WHERE albara_id = ?", (aid,))
    hores = db.rows("SELECT * FROM hores WHERE albara_id = ? ORDER BY data", (aid,))
    files = "".join(f"<tr><td>{_e(l['descripcio'])}</td><td class='r'>{num(l['quantitat'])} {_e(l['unitat'])}</td></tr>" for l in linies)
    files += "".join(f"<tr><td>Mà d'obra {data_cat(h['data'])} {_e(h['treballador'])} {_e(h['descripcio'])}</td>"
                     f"<td class='r'>{num(h['hores'])} h</td></tr>" for h in hores)
    firma = (f"<img src='{_e(a['signatura'])}' alt='signatura'>" if a["signatura"] else "")
    cos = f"""
<header><div><h1>ALBARÀ DE FEINA</h1><div class='muted'>Núm. {_e(a['numero'])}<br>Data {data_cat(a['data'])}</div></div>
<div class='muted' style='text-align:right'>{_empresa(s)}</div></header>
<div class='parts'><div><b>Client</b>{_client(c)}</div><div><b>Obra</b>{_e(feina['nom'])}<br>{_e(feina['adreca'])}</div></div>
<p style='white-space:pre-wrap'>{_e(a['descripcio'])}</p>
<table><thead><tr><th>Treball / material</th><th class='r'>Quantitat</th></tr></thead><tbody>{files}</tbody></table>
<div class='firma'><div>Per l'empresa</div><div>Conforme client: {_e(a['signat_per'])} {data_cat(a['signat_at'])}{firma}</div></div>"""
    return _pagina(f"Albarà {a['numero']}", cos)
