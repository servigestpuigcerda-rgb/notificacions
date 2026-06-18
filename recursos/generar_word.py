from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# Marges
sections = doc.sections
for section in sections:
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(3)
    section.right_margin = Cm(2.5)

# Estils base
style_normal = doc.styles['Normal']
style_normal.font.name = 'Arial'
style_normal.font.size = Pt(11)

def add_heading(doc, text, level=1, center=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    if level == 1:
        run.font.size = Pt(14)
    elif level == 2:
        run.font.size = Pt(12)
    else:
        run.font.size = Pt(11)
    run.font.name = 'Arial'
    return p

def add_para(doc, text, bold=False, italic=False, center=False, space_before=0, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.name = 'Arial'
    run.font.size = Pt(11)
    return p

def add_mixed_para(doc, parts, center=False, space_before=0, space_after=6):
    """parts = list of (text, bold, italic)"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for text, bold, italic in parts:
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.name = 'Arial'
        run.font.size = Pt(11)
    return p

def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1+len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Capçalera
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        hdr_cells[i].paragraphs[0].runs[0].bold = True
        hdr_cells[i].paragraphs[0].runs[0].font.name = 'Arial'
        hdr_cells[i].paragraphs[0].runs[0].font.size = Pt(10)
        hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        tc = hdr_cells[i]._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), 'D9D9D9')
        tcPr.append(shd)
    # Files
    for row_data in rows:
        row_cells = table.add_row().cells
        for i, cell_text in enumerate(row_data):
            row_cells[i].text = cell_text
            row_cells[i].paragraphs[0].runs[0].font.name = 'Arial'
            row_cells[i].paragraphs[0].runs[0].font.size = Pt(10)
            if i > 0:
                row_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    # Amplades
    if col_widths:
        for i, row in enumerate(table.rows):
            for j, cell in enumerate(row.cells):
                cell.width = Cm(col_widths[j])
    doc.add_paragraph()
    return table

# ============================================================
# CAPÇALERA
# ============================================================
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(4)
run = p.add_run('RECURS DE REPOSICIÓ')
run.bold = True
run.font.size = Pt(16)
run.font.name = 'Arial'

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
p2.paragraph_format.space_after = Pt(2)
run2 = p2.add_run('Art. 222-225 de la Llei 58/2003, General Tributària')
run2.italic = True
run2.font.size = Pt(11)
run2.font.name = 'Arial'

doc.add_paragraph()

# Destinatari
add_para(doc, 'A L\'OFICINA DE GESTIÓ TRIBUTÀRIA', bold=True, center=True)
add_para(doc, 'DELEGACIÓ DE L\'AGÈNCIA TRIBUTÀRIA A LLEIDA', bold=True, center=True)
add_para(doc, 'Plaça Cervantes, 17 — 25002 Lleida', center=True, space_after=12)

# Línia separadora
p_line = doc.add_paragraph('─' * 70)
p_line.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_line.paragraph_format.space_after = Pt(10)

# Compareixença
add_mixed_para(doc, [
    ('CAROLINA NAVARRO TAURONI', True, False),
    (', amb NIF ', False, False),
    ('43821215M', True, False),
    (', representada per ', False, False),
    ('SERVIGEST BARBERAN SL (B64227937)', True, False),
    (', col·laboradora social de l\'AEAT,', False, False),
], space_after=6)

add_para(doc, 'compareix i, en el termini legalment establert,', space_after=4)

add_mixed_para(doc, [
    ('INTERPOSA RECURS DE REPOSICIÓ', True, False),
    (' contra la Resolució de Liquidació Provisional notificada per la Delegació de Lleida, de data ', False, False),
    ('9 de juny de 2026', True, False),
    (', relativa a l\'IRPF de l\'exercici 2024, i tot això en base als següents', False, False),
], space_after=16)

# ============================================================
# FETS
# ============================================================
add_heading(doc, 'FETS', level=1, center=True)

# Primer
add_heading(doc, 'Primer. — Autoliquidació de l\'IRPF 2024', level=2)
add_mixed_para(doc, [
    ('En data ', False, False),
    ('28 de juny de 2025', True, False),
    (', la contribuent va presentar l\'autoliquidació de l\'Impost sobre la Renda de les Persones Físiques corresponent a l\'exercici 2024 (Model 100, referència ', False, False),
    ('202410021212498Q', True, False),
    (', CSV ', False, False),
    ('G5YS9HB3J9SFBU28', True, False),
    ('), presentada per la col·laboradora social SERVIGEST BARBERAN SL.', False, False),
])
add_para(doc, 'A la declaració es va incloure un guany patrimonial derivat de la transmissió del 50% d\'un immoble situat a França (9 avenue de Cerdagne, 66340 Osséja):')

add_table(doc,
    ['Concepte', 'Valor declarat'],
    [
        ['Valor de transmissió (50%)', '71.000,00 €'],
        ['Valor d\'adquisició (casella 1913)', '42.454,00 €'],
        ['Despeses de transmissió (casella 1912)', '4.106,00 €'],
        ['Guany patrimonial net (casella 1833)', '24.440,00 €'],
        ['Deducció per doble imposició internacional (casella 0588)', '4.910,00 €'],
        ['Resultat de la declaració', '2.583,78 €'],
    ],
    col_widths=[11, 5]
)

add_para(doc, 'El valor d\'adquisició de 42.454 € es compon de: preu d\'adquisició 31.500 € + despeses i tributs d\'adquisició (7,5 %) 2.921 € + millores i inversions 8.033 €, d\'acord amb l\'article 35.1.b) de la Llei 35/2006, de l\'IRPF.')
add_para(doc, 'Les despeses de transmissió de 4.106 € es componen de: 2.124 € de frais et taxes du vendeur (línia 12 del formulari 2048-IMM-SD) i 1.982 € de contribucions socials franceses (CSG + CRDS + prélèvement de solidarité), ambdues degudament documentades.')

# Segon
add_heading(doc, 'Segon. — Primer requeriment i resposta', level=2)
add_mixed_para(doc, [
    ('En data ', False, False),
    ('24 de març de 2026', True, False),
    (', la representant va aportar la documentació justificativa, entre la qual s\'incloïen:', False, False),
])
for item in [
    'L\'escriptura d\'adquisició de l\'immoble (acte notarial de 13 de març de 2023).',
    'L\'escriptura de compravenda (acte de venda de 25 d\'octubre de 2024, comprador: ALBA HERITAGE SL, Montcada i Reixach).',
    'El formulari de la plus-vàlua immobiliária francesa (2048-IMM-SD), en llengua original francesa.',
    'L\'extracte de compte notarial (Étude SCP F. Garrigue, P. Denamiel et P. Garrigue), en llengua original francesa.',
]:
    p = doc.add_paragraph(item, style='List Bullet')
    p.paragraph_format.space_after = Pt(2)
    for run in p.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(11)
add_para(doc, 'Els documents es van aportar en la seva versió original francesa, sense traducció jurada, atès que en procediments anteriors davant l\'AEAT la documentació en llengua francesa havia estat acceptada sense objecció.')

# Tercer
add_heading(doc, 'Tercer. — Segon requeriment i resposta', level=2)
add_mixed_para(doc, [
    ('En data ', False, False),
    ('15 d\'abril de 2026', True, False),
    (', l\'Oficina de Gestió va notificar un ', False, False),
    ('segon requeriment', True, False),
    (', en el qual s\'exigia la traducció jurada dels documents aportats en francès.', False, False),
])
add_mixed_para(doc, [
    ('En data ', False, False),
    ('28 d\'abril de 2026', True, False),
    (' (RGE ', False, False),
    ('57002620 2026', True, False),
    ('), la representant va respondre al segon requeriment i va sol·licitar un termini addicional per obtenir les traduccions jurades, atès que l\'obtenció de traduccions jurades per a documents notarials de dret francès per traductors habilitats a Espanya és un procés que requereix diverses setmanes.', False, False),
])

# Quart
add_heading(doc, 'Quart. — Proposta de liquidació i sol·licitud d\'ampliació de termini', level=2)
add_mixed_para(doc, [
    ('En data ', False, False),
    ('13 de maig de 2026', True, False),
    (', l\'Oficina va notificar la proposta de liquidació provisional (CSV SRXGUTFZBSTPVCAX), que modificava substancialment la base imposable declarada.', False, False),
])
add_mixed_para(doc, [
    ('En data ', False, False),
    ('5 de juny de 2026', True, False),
    (', la representant va presentar una ', False, False),
    ('sol·licitud d\'ampliació del termini d\'al·legacions', True, False),
    (', motivada en el fet que les traduccions jurades es trobaven en fase final. L\'Oficina de Gestió va ', False, False),
    ('DENEGAR', True, False),
    (' la sol·licitud per considerar que havia estat presentada fora dels deu dies des de la notificació de la proposta.', False, False),
])

# Cinquè
add_heading(doc, 'Cinquè. — Lliurament de traduccions jurades i signatura de la resolució el mateix dia', level=2)
add_mixed_para(doc, [
    ('En data ', False, False),
    ('9 de juny de 2026', True, False),
    (', el proveïdor de traduccions jurades ', False, False),
    ('Ibidem Group', True, False),
    (' va lliurar les traduccions jurades realitzades per la traductora Marta López Ruiz (núm. 10807, Màlaga):', False, False),
])
for item in [
    'Traducció jurada del formulari 2048-IMM-SD: data adquisició 13/03/2023, data transmissió 25/10/2024, valor adquisició corregit 42.454 € (línia 25), guany brut 26.422 € (línia 30), impost sobre la renda francès al 19 % = 5.020 € (línia 61), contribucions socials 1.982 €.',
    'Traducció jurada de l\'extracte de compte notarial: producte net rebut per la contribuent 55.853,08 €.',
]:
    p = doc.add_paragraph(item, style='List Bullet')
    p.paragraph_format.space_after = Pt(2)
    for run in p.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(11)

add_mixed_para(doc, [
    ('En aquesta mateixa data, 9 de juny de 2026', True, False),
    (', el ', False, False),
    ('Inspector Regional Adjunto per suplència, Sr. BORJA RUIZ ARIZA', True, False),
    (', va signar la ', False, False),
    ('Resolució de Liquidació Provisional', True, False),
    (' (CSV ', False, False),
    ('D3EERKEPGYH26NP9', True, False),
    (', clau de liquidació ', False, False),
    ('A2560026100032236', True, False),
    (', número de justificant ', False, False),
    ('252601079009X', True, False),
    (').', False, False),
], space_before=6)

p_key = doc.add_paragraph()
p_key.paragraph_format.space_before = Pt(6)
p_key.paragraph_format.space_after = Pt(6)
run_key = p_key.add_run('La resolució definitiva va ser dictada el mateix dia en què les proves documentals que acreditaven la posició de la contribuent estaven disponibles i havien estat lliurades. Ni l\'Oficina ni la resolució fan cap referència a les traduccions jurades ni les valoren; la decisió ja estava presa. Constitueix indefensió material que l\'Administració hagi denegat l\'ampliació del termini i hagi dictat la resolució just quan la contribuent podia per fi acreditar documentalment la seva posició.')
run_key.font.name = 'Arial'
run_key.font.size = Pt(11)
run_key.italic = True

# Sisè
add_heading(doc, 'Sisè. — Contingut de la Resolució impugnada', level=2)
add_table(doc,
    ['Concepte', 'Declarat', 'AEAT (Resolució)', 'Diferència'],
    [
        ['Valor d\'adquisició', '42.454,00 €', '31.500,00 €', '−10.954,00 €'],
        ['Despeses de transmissió', '4.106,00 €', '0,00 €', '−4.106,00 €'],
        ['Guany patrimonial net', '24.440,00 €', '39.500,00 €', '+15.060,00 €'],
        ['Deducció doble imposició', '4.910,00 €', '5.020,00 €', '+110,00 €'],
    ],
    col_widths=[6, 4, 4, 4]
)
add_para(doc, 'Liquidació resultant: Quota 3.052,60 € + Interessos 116,88 € (344 dies al 4,0625%, del 01/07/2025 al 09/06/2026) = ')
p_total = doc.add_paragraph()
p_total.paragraph_format.space_before = Pt(2)
p_total.paragraph_format.space_after = Pt(10)
run_total = p_total.add_run('TOTAL: 3.169,48 €')
run_total.bold = True
run_total.font.size = Pt(13)
run_total.font.name = 'Arial'

# ============================================================
# FONAMENTS
# ============================================================
add_heading(doc, 'FONAMENTS DE DRET', level=1, center=True)

# Fonament 1
add_heading(doc, 'Primer fonament. — INDEFENSIÓ PER MANCA DE TEMPS MATERIAL PER APORTAR LES PROVES: NUL·LITAT DE LA RESOLUCIÓ', level=2)
add_para(doc, 'La resolució s\'ha dictat vulnerant el dret de defensa i el dret a la tutela judicial efectiva garantits per l\'article 24 de la Constitució Espanyola, i concretats en l\'àmbit tributari en els articles 34.1.a) i 34.1.e) de la LGT, que reconeixen el dret a ser escoltat i a aportar proves.')
add_para(doc, 'La seqüència cronològica és inequívoca:')
for item in [
    '09/06/2026: Lliurament de les traduccions jurades del formulari 2048-IMM-SD i de l\'extracte de compte notarial.',
    '09/06/2026: Signatura de la resolució definitiva per BORJA RUIZ ARIZA.',
]:
    p = doc.add_paragraph(item, style='List Bullet')
    for run in p.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(11)

add_para(doc, 'Constitueix indefensió material el fet que l\'Administració hagi denegat l\'ampliació del termini el 05/06/2026 i hagi dictat la resolució el 09/06/2026, just quan la contribuent podia per fi acreditar documentalment la seva posició. La manca d\'oportunitat no és imputable a la contribuent: els terminis per a l\'obtenció de traduccions jurades de documents notarials de dret estranger excedeixen habitualment els 30 dies.')
add_mixed_para(doc, [
    ('En conseqüència, la resolució s\'ha dictat en frau del dret de defensa i ha de ser ', False, False),
    ('ANUL·LADA', True, False),
    (' per restablir a la contribuent en el seu dret a aportar les proves que ara s\'acompanyen.', False, False),
])

# Fonament 2
add_heading(doc, 'Segon fonament. — ARBITRARIETAT EN L\'EXIGÈNCIA DE TRADUCCIÓ JURADA: VULNERACIÓ DEL PRINCIPI DE CONFIANÇA LEGÍTIMA', level=2)
add_para(doc, 'L\'article 3 de la Llei 39/2015 consagra el principi de confiança legítima: l\'Administració no pot adoptar conductes contràries als actes o comportaments propis que hagin generat confiança en els interessats.')
add_para(doc, 'En nombrosos procediments anteriors de comprovació tributària, la documentació en llengua francesa ha estat admesa i valorada sense exigir traducció jurada.')
add_para(doc, 'A més, si l\'Administració no hagués llegit el formulari 2048-IMM-SD, no hauria pogut determinar autònomament que la DDI correcta era 5.020 € en lloc dels 4.910 € declarats. Això demostra que l\'AEAT va llegir i comprendre el document en la seva versió original francesa, la qual cosa fa encara menys justificable la invocació del requisit de traducció jurada com a motiu per desestimar les despeses documentades en el mateix formulari.')
add_para(doc, 'L\'exigència de traducció jurada en el present cas, mentre que en altres casos semblants la mateixa Administració ha renunciat a aquest requisit, constitueix una aplicació arbitrària i discriminatòria de la norma (art. 9.3 CE) i una vulneració del principi de confiança legítima.')

# Fonament 3
add_heading(doc, 'Tercer fonament. — VALOR D\'ADQUISICIÓ: ART. 35.1.b) LLEI 35/2006 (LIRPF)', level=2)
add_para(doc, 'L\'article 35.1.b) de la Llei 35/2006 estableix que el valor d\'adquisició inclou el cost de les inversions i millores, i les despeses i tributs inherents a l\'adquisició.')
add_table(doc,
    ['Concepte', 'Import'],
    [
        ['Preu d\'adquisició (acte notarial 13/03/2023, 50%)', '31.500,00 €'],
        ['Despeses i tributs d\'adquisició (7,5% — droits de mutation + notaire)', '2.921,00 €'],
        ['Millores i reformes realitzades a l\'immoble', '8.033,00 €'],
        ['TOTAL VALOR D\'ADQUISICIÓ', '42.454,00 €'],
    ],
    col_widths=[11, 5]
)
add_para(doc, 'Aquests imports queden acreditats per l\'acte notarial d\'adquisició, el formulari 2048-IMM-SD (línia 25: "Prix de revient corrigé" = 42.454 €, en traducció jurada) i els justificants de les despeses de reforma.')

# Fonament 4
add_heading(doc, 'Quart fonament. — DESPESES DE TRANSMISSIÓ: 4.106 € DOCUMENTATS I LEGALMENT DEDUÏBLES', level=2)
add_para(doc, 'La Resolució fixa les despeses de transmissió en 0 €, eliminant la totalitat dels 4.106 € declarats. Aquesta eliminació és incorrecta:')
add_mixed_para(doc, [('4.1. Frais et taxes du vendeur — 2.124 €', True, False)])
add_para(doc, 'El formulari 2048-IMM-SD (línia 12) acredita despeses i taxes pròpies del venedor per 2.124 €. Encaixen en el concepte de "gastos inherentes a la transmisión" de l\'article 35.1.a) LIRPF.')
add_mixed_para(doc, [('4.2. Contribucions socials franceses (CSG + CRDS + prélèvement de solidarité) — 1.982 €', True, False)])
add_para(doc, 'El formulari 2048-IMM-SD acredita contribucions socials per 1.982 € derivades directament de la transmissió. Constitueixen un cost real i efectiu.')
add_para(doc, 'Alternativament, en cas que no s\'admetin com a despesa de transmissió, les contribucions socials poden ampliar la deducció per doble imposició (art. 24 CDI) fins a 7.002 € totals d\'impost suportat a França (5.020 € IR + 1.982 € contribucions).')

# Fonament 5
add_heading(doc, 'Cinquè fonament. — DEDUCCIÓ PER DOBLE IMPOSICIÓ INTERNACIONAL: CDI ESPANYA-FRANÇA', level=2)
add_para(doc, 'El Conveni entre el Regne d\'Espanya i la República Francesa per evitar la doble imposició (BOE 12/06/1995), articles 13 i 24, atorga a França el dret d\'imposar la plus-vàlua de béns immobles situats en territori francès i obliga Espanya a deduir de la quota l\'impost satisfet a França.')
add_para(doc, 'L\'impost sobre la renda francès efectivament satisfet és de 5.020 € (línia 61 del formulari 2048-IMM-SD, en traducció jurada), tal com ha reconegut la pròpia Resolució en fixar la DDI en 5.020 €.')

# Fonament 6
add_heading(doc, 'Sisè fonament. — ERROR MATERIAL EN LA CASELLA 1825 DE LA DECLARACIÓ', level=2)
add_para(doc, 'La data que consta en la casella 1825 (01/01/2024) és un error material de transcripció en la declaració presentada: la data correcta d\'adquisició és 13 de març de 2023, tal com acredita l\'acte notarial d\'adquisició i el formulari 2048-IMM-SD. Aquest error no té incidència en el resultat tributari, però ha de ser correctament reflectit en la liquidació definitiva.')

# ============================================================
# SUSPENSIÓ
# ============================================================
add_heading(doc, 'SOL·LICITUD DE SUSPENSIÓ DE L\'EXECUCIÓ', level=1, center=True)
add_para(doc, 'A l\'empara dels articles 224 LGT i 39-46 del Reglament General de Revisió en Via Administrativa (RD 520/2005), la recurrent sol·licita la SUSPENSIÓ DE L\'EXECUCIÓ de la liquidació impugnada durant la tramitació del present recurs.')
add_table(doc,
    ['Concepte', 'Import'],
    [
        ['Liquidació provisional impugnada (clau A2560026100032236)', '3.169,48 €'],
        ['Autoliquidació IRPF 2024 pendent (ref. 202410021212498Q)', '2.583,78 €'],
        ['TOTAL SOL·LICITUD SUSPENSIÓ', '5.753,26 €'],
    ],
    col_widths=[11, 5]
)
add_para(doc, 'En alternativa, si l\'Administració exigís garantia, la recurrent ofereix caucionar l\'import total de 5.753,26 € mitjançant aval bancari, dipòsit de valors o qualsevol altra garantia admesa per l\'article 224 LGT i el RGRV.')

# ============================================================
# SOL·LICITUD
# ============================================================
add_heading(doc, 'SOL·LICITUD', level=1, center=True)
add_para(doc, 'Per tot l\'exposat, es sol·licita a l\'Oficina de Gestió Tributària de la Delegació de Lleida que:')

requests = [
    ('1r.', 'ADMETI a tràmit el present recurs de reposició i SUSPENGUI CAUTELARMENT l\'execució de la liquidació provisional impugnada.'),
    ('2n.', 'ESTIMI íntegrament el recurs i ANUL·LI la Resolució de Liquidació Provisional de data 9 de juny de 2026 (CSV D3EERKEPGYH26NP9, clau A2560026100032236), per vulneració del dret de defensa i indefensió material de la contribuent.'),
    ('3r.', 'Subsidiàriament, ESTIMI PARCIALMENT el recurs i fixi els elements de la liquidació d\'acord amb els valors declarats:'),
    ('4t.', 'RECTIFIQUI l\'error material de la casella 1825 (data d\'adquisició) per reflectir la data correcta de 13 de març de 2023.'),
]

for num, text in requests:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    r1 = p.add_run(num + ' ')
    r1.bold = True
    r1.font.name = 'Arial'
    r1.font.size = Pt(11)
    r2 = p.add_run(text)
    r2.font.name = 'Arial'
    r2.font.size = Pt(11)

add_table(doc,
    ['Concepte', 'Import correcte'],
    [
        ['Valor de transmissió', '71.000,00 €'],
        ['Valor d\'adquisició (art. 35.1.b) LIRPF)', '42.454,00 €'],
        ['Despeses de transmissió (art. 35.1.a) LIRPF)', '4.106,00 €'],
        ['Guany patrimonial net', '24.440,00 €'],
        ['Deducció doble imposició (art. 24 CDI Espanya-França)', '5.020,00 €'],
    ],
    col_widths=[11, 5]
)

# ============================================================
# DOCUMENTACIÓ
# ============================================================
add_heading(doc, 'DOCUMENTACIÓ ADJUNTA', level=1, center=True)

docs_list = [
    'Còpia de la Resolució de Liquidació Provisional (CSV D3EERKEPGYH26NP9, data 09/06/2026).',
    'Còpia de l\'autoliquidació IRPF 2024 (Model 100, ref. 202410021212498Q, CSV G5YS9HB3J9SFBU28).',
    'Traducció jurada del formulari 2048-IMM-SD (plus-vàlua immobiliária francesa, exercici 2024) — Marta López Ruiz, traductora jurada núm. 10807, Màlaga, 8 de juny de 2026.',
    'Traducció jurada de l\'extracte de compte notarial (Étude SCP F. Garrigue, P. Denamiel et P. Garrigue, periode 26/08/2024 a 27/01/2025) — Marta López Ruiz, traductora jurada núm. 10807, Màlaga, 8 de juny de 2026.',
    'Còpia de l\'acte notarial d\'adquisició de l\'immoble (13 de març de 2023, 50% — Carolina Navarro Tauroni i Mariona Ventura Serra).',
    'Còpia de l\'acte de compravenda (25 d\'octubre de 2024, comprador: ALBA HERITAGE SL).',
    'Justificants de les despeses de reforma/millores (8.033 €).',
    'Còpia de la resposta al segon requeriment (RGE 57002620 2026, de 28 d\'abril de 2026).',
    'Còpia de la sol·licitud d\'ampliació de termini d\'al·legacions (5 de juny de 2026) i de la seva denegació.',
]

for i, item in enumerate(docs_list, 1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    r_num = p.add_run(f'{i}. ')
    r_num.bold = True
    r_num.font.name = 'Arial'
    r_num.font.size = Pt(11)
    r_text = p.add_run(item)
    r_text.font.name = 'Arial'
    r_text.font.size = Pt(11)

# ============================================================
# SIGNATURA
# ============================================================
doc.add_paragraph()
p_loc = doc.add_paragraph()
p_loc.paragraph_format.space_before = Pt(16)
r_loc = p_loc.add_run('Puigcerdà, a _____ de juny de 2026')
r_loc.font.name = 'Arial'
r_loc.font.size = Pt(11)

doc.add_paragraph()
doc.add_paragraph()

p_sig = doc.add_paragraph()
p_sig.paragraph_format.space_before = Pt(6)
r_s1 = p_sig.add_run('SERVIGEST BARBERAN SL\n')
r_s1.bold = True
r_s1.font.name = 'Arial'
r_s1.font.size = Pt(11)
r_s2 = p_sig.add_run('Col·laboradora social de l\'AEAT (B64227937)\n')
r_s2.font.name = 'Arial'
r_s2.font.size = Pt(11)
r_s3 = p_sig.add_run('En representació de CAROLINA NAVARRO TAURONI (NIF 43821215M)')
r_s3.font.name = 'Arial'
r_s3.font.size = Pt(11)

doc.add_paragraph()
p_ref = doc.add_paragraph()
p_ref.paragraph_format.space_before = Pt(20)
r_ref = p_ref.add_run('Recurs de reposició | IRPF 2024 | Clau liquidació A2560026100032236 | CSV D3EERKEPGYH26NP9 | Delegació AEAT Lleida')
r_ref.italic = True
r_ref.font.size = Pt(9)
r_ref.font.name = 'Arial'
r_ref.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

output_path = '/home/user/notificacions/recursos/recurs_reposicio_carolina_navarro.docx'
doc.save(output_path)
print(f'Document guardat: {output_path}')
