import os
import tempfile

os.environ["GESTIO_DATA_DIR"] = tempfile.mkdtemp(prefix="gestio-test-")
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def c():
    with TestClient(app) as client:
        r = client.post("/api/setup", json={"nom": "Admin Prova", "usuari": "admin", "password": "contrasenya1",
                                            "empresa_nom": "Empresa Prova SL"})
        assert r.status_code == 200, r.text
        client.put("/api/config", json={"empresa_nif": "B00000000", "empresa_adreca": "Carrer Fictici 1",
                                        "empresa_iban": "ES00 0000 0000 0000 0000 0000", "empresa_bizum": "600000000"})
        yield client
