"""Base de dades SQLite: esquema, connexió i utilitats.

Totes les dades (incloses les dels clients) es guarden NOMÉS a la carpeta
DATA_DIR del servidor. Aquesta carpeta no s'ha de pujar mai al repositori.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("GESTIO_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DOCS_DIR = DATA_DIR / "documents"
DB_PATH = DATA_DIR / "gestio.sqlite3"

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS usuaris (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    usuari TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'admin',          -- admin | treballador
    cost_hora REAL NOT NULL DEFAULT 0,
    preu_hora REAL NOT NULL DEFAULT 0,
    actiu INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    usuari_id INTEGER NOT NULL REFERENCES usuaris(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS partides (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE,
    tipus TEXT NOT NULL DEFAULT 'material',     -- ma_obra | material | subcontracta | altres
    ordre INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    nif TEXT,
    email TEXT,
    telefon TEXT,
    adreca TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    codi TEXT,
    nom TEXT NOT NULL,
    unitat TEXT NOT NULL DEFAULT 'u',
    partida_id INTEGER REFERENCES partides(id),
    cost REAL NOT NULL DEFAULT 0,
    marge_pct REAL,                              -- NULL = marge per defecte
    preu REAL,                                   -- NULL = cost * (1 + marge)
    descompte_pct REAL NOT NULL DEFAULT 0,
    iva_pct REAL,
    proveidor TEXT,
    notes TEXT,
    actiu INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feines (
    id INTEGER PRIMARY KEY,
    codi TEXT NOT NULL UNIQUE,
    nom TEXT NOT NULL,
    client_id INTEGER REFERENCES clients(id),
    adreca TEXT,
    tipus TEXT,                                  -- categoria per a l'aprenentatge (bany, cuina...)
    estat TEXT NOT NULL DEFAULT 'pressupost',    -- pressupost | acceptada | en_curs | acabada | tancada | cancellada
    mode_facturacio TEXT NOT NULL DEFAULT 'pressupost',  -- pressupost | administracio
    data_inici TEXT,
    data_fi TEXT,
    notes TEXT,
    token TEXT NOT NULL UNIQUE,                  -- enllaç del portal del client
    tancada_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pressupostos (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER NOT NULL REFERENCES feines(id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    tipus TEXT NOT NULL DEFAULT 'principal',     -- principal | extra (fora de pressupost)
    titol TEXT,
    estat TEXT NOT NULL DEFAULT 'esborrany',     -- esborrany | enviat | acceptat | rebutjat
    data TEXT NOT NULL,
    validesa_dies INTEGER NOT NULL DEFAULT 30,
    descompte_pct REAL NOT NULL DEFAULT 0,
    iva_pct REAL NOT NULL DEFAULT 21,
    irpf_pct REAL NOT NULL DEFAULT 0,
    notes TEXT,
    condicions TEXT,
    text_origen TEXT,                            -- dictat / explicació original
    enviat_at TEXT,
    acceptat_at TEXT,
    acceptat_per TEXT,
    rebutjat_motiu TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linies_pressupost (
    id INTEGER PRIMARY KEY,
    pressupost_id INTEGER NOT NULL REFERENCES pressupostos(id) ON DELETE CASCADE,
    ordre INTEGER NOT NULL DEFAULT 0,
    article_id INTEGER REFERENCES articles(id),
    partida_id INTEGER REFERENCES partides(id),
    descripcio TEXT NOT NULL,
    quantitat REAL NOT NULL DEFAULT 1,
    unitat TEXT NOT NULL DEFAULT 'u',
    cost_unitari REAL NOT NULL DEFAULT 0,
    marge_pct REAL NOT NULL DEFAULT 0,
    preu_unitari REAL NOT NULL DEFAULT 0,
    descompte_pct REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER REFERENCES feines(id) ON DELETE SET NULL,
    tipus TEXT NOT NULL DEFAULT 'altres',        -- tiquet | factura_proveidor | albara_proveidor | foto | pressupost | factura | altres
    nom TEXT NOT NULL,
    fitxer TEXT NOT NULL,
    mime TEXT,
    mida INTEGER,
    text_extret TEXT,
    dades_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS despeses (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER REFERENCES feines(id) ON DELETE SET NULL,
    partida_id INTEGER REFERENCES partides(id),
    proveidor TEXT,
    proveidor_nif TEXT,
    tipus_doc TEXT NOT NULL DEFAULT 'tiquet',    -- tiquet | factura | albara
    num_document TEXT,
    data TEXT NOT NULL,
    concepte TEXT,
    base REAL NOT NULL DEFAULT 0,
    iva_pct REAL NOT NULL DEFAULT 21,
    iva_import REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    marge_pct REAL NOT NULL DEFAULT 0,           -- benefici aplicat si es repercuteix al client
    facturable INTEGER NOT NULL DEFAULT 0,       -- es factura a part (administració / fora pressupost)
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    estat TEXT NOT NULL DEFAULT 'ok',            -- pendent_revisio | ok
    ia_confianca REAL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS albarans (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER NOT NULL REFERENCES feines(id) ON DELETE CASCADE,
    numero TEXT NOT NULL,
    data TEXT NOT NULL,
    descripcio TEXT,
    estat TEXT NOT NULL DEFAULT 'obert',         -- obert | signat
    signat_per TEXT,
    signatura TEXT,                              -- imatge PNG (data URL)
    signat_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linies_albara (
    id INTEGER PRIMARY KEY,
    albara_id INTEGER NOT NULL REFERENCES albarans(id) ON DELETE CASCADE,
    article_id INTEGER REFERENCES articles(id),
    descripcio TEXT NOT NULL,
    quantitat REAL NOT NULL DEFAULT 1,
    unitat TEXT NOT NULL DEFAULT 'u'
);

CREATE TABLE IF NOT EXISTS hores (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER NOT NULL REFERENCES feines(id) ON DELETE CASCADE,
    usuari_id INTEGER REFERENCES usuaris(id),
    treballador TEXT,
    data TEXT NOT NULL,
    hores REAL NOT NULL,
    cost_hora REAL NOT NULL DEFAULT 0,
    preu_hora REAL NOT NULL DEFAULT 0,
    descripcio TEXT,
    facturable INTEGER NOT NULL DEFAULT 0,
    albara_id INTEGER REFERENCES albarans(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factures (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER REFERENCES feines(id) ON DELETE SET NULL,
    client_id INTEGER REFERENCES clients(id),
    serie TEXT NOT NULL,
    numero INTEGER,                              -- NULL mentre és esborrany
    codi TEXT,
    data TEXT NOT NULL,
    venciment TEXT,
    concepte TEXT,
    base REAL NOT NULL DEFAULT 0,
    iva_pct REAL NOT NULL DEFAULT 21,
    iva_import REAL NOT NULL DEFAULT 0,
    irpf_pct REAL NOT NULL DEFAULT 0,
    irpf_import REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    estat TEXT NOT NULL DEFAULT 'esborrany',     -- esborrany | emesa | cobrada | anullada
    cobrada_at TEXT,
    rectifica_id INTEGER REFERENCES factures(id),  -- factura rectificativa d'una altra
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (serie, numero)
);

CREATE TABLE IF NOT EXISTS linies_factura (
    id INTEGER PRIMARY KEY,
    factura_id INTEGER NOT NULL REFERENCES factures(id) ON DELETE CASCADE,
    descripcio TEXT NOT NULL,
    quantitat REAL NOT NULL DEFAULT 1,
    preu_unitari REAL NOT NULL DEFAULT 0,
    descompte_pct REAL NOT NULL DEFAULT 0,
    import REAL NOT NULL DEFAULT 0,
    origen_tipus TEXT NOT NULL DEFAULT 'manual', -- linia_pressupost | despesa | hores | manual
    origen_id INTEGER
);

CREATE TABLE IF NOT EXISTS missatges (
    id INTEGER PRIMARY KEY,
    feina_id INTEGER NOT NULL REFERENCES feines(id) ON DELETE CASCADE,
    autor TEXT NOT NULL,                         -- empresa | client | sistema
    tipus TEXT NOT NULL DEFAULT 'missatge',      -- missatge | nota | pressupost | acceptacio | rebuig | fora_pressupost | factura | tancament
    text TEXT NOT NULL,
    intern INTEGER NOT NULL DEFAULT 0,           -- 1 = nota interna, el client no la veu
    ref_tipus TEXT,
    ref_id INTEGER,
    llegit INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprenentatge_proveidors (
    proveidor TEXT PRIMARY KEY,
    partida_id INTEGER REFERENCES partides(id),
    usos INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_despeses_feina ON despeses(feina_id);
CREATE INDEX IF NOT EXISTS idx_hores_feina ON hores(feina_id);
CREATE INDEX IF NOT EXISTS idx_pressupostos_feina ON pressupostos(feina_id);
CREATE INDEX IF NOT EXISTS idx_factures_feina ON factures(feina_id);
CREATE INDEX IF NOT EXISTS idx_missatges_feina ON missatges(feina_id);
CREATE INDEX IF NOT EXISTS idx_documents_feina ON documents(feina_id);
"""

PARTIDES_INICIALS = [
    ("Mà d'obra", "ma_obra"),
    ("Material", "material"),
    ("Subcontractes", "subcontracta"),
    ("Maquinària i lloguers", "altres"),
    ("Desplaçaments i dietes", "altres"),
    ("Runa i residus", "altres"),
    ("Altres", "altres"),
]

SETTINGS_INICIALS = {
    "empresa_nom": "",
    "empresa_nif": "",
    "empresa_adreca": "",
    "empresa_telefon": "",
    "empresa_email": "",
    "empresa_iban": "",
    "iva_defecte": "21",
    "irpf_defecte": "0",
    "marge_defecte": "20",
    "cost_hora_defecte": "25",
    "preu_hora_defecte": "38",
    "serie_factura": "F",
    "validesa_pressupost": "30",
    "venciment_dies": "30",
    "condicions_pressupost": "Pressupost vàlid durant el termini indicat. Qualsevol treball no inclòs es comunicarà i pressupostarà a part abans d'executar-lo.",
    "ia_activa": "1",
    "ia_model": "claude-opus-5-5",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().date().isoformat()


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


def close():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM partides").fetchone()[0] == 0:
        for i, (nom, tipus) in enumerate(PARTIDES_INICIALS):
            conn.execute("INSERT INTO partides(nom, tipus, ordre) VALUES (?,?,?)", (nom, tipus, i))
    for k, v in SETTINGS_INICIALS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v))
    conn.commit()


def rows(sql, params=()):
    return [dict(r) for r in connect().execute(sql, params).fetchall()]


def row(sql, params=()):
    r = connect().execute(sql, params).fetchone()
    return dict(r) if r else None


def scalar(sql, params=()):
    r = connect().execute(sql, params).fetchone()
    return r[0] if r else None


def insert(table: str, data: dict) -> int:
    cols = ", ".join(data.keys())
    marks = ", ".join("?" for _ in data)
    with tx() as conn:
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))
        return cur.lastrowid


def update(table: str, id_: int, data: dict):
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    with tx() as conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), id_))


def delete(table: str, id_: int):
    with tx() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (id_,))


def settings() -> dict:
    return {r["key"]: r["value"] for r in rows("SELECT key, value FROM settings")}


def setting(key: str, default=None):
    v = scalar("SELECT value FROM settings WHERE key = ?", (key,))
    return default if v is None else v


def setting_float(key: str, default: float = 0.0) -> float:
    try:
        return float(setting(key, default))
    except (TypeError, ValueError):
        return default


def set_settings(values: dict):
    with tx() as conn:
        for k, v in values.items():
            conn.execute("INSERT INTO settings(key, value) VALUES (?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, str(v)))
