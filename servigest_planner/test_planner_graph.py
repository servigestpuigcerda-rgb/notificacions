"""Pruebas con Graph simulado (sin red ni datos reales).  python -m pytest servigest_planner -q"""
from servigest_planner import planner_graph as pg

PLAN = "PLAN000000000000000000001"
PLAN2 = "PLAN000000000000000000002"
GRUPO = "GRUPO00000000000000000001"
U_ANA, U_BEA, U_BERTA = "u-ana", "u-bea", "u-berta"


class FakeGraph:
    def __init__(self):
        self.llamadas = []
        self.tareas = {
            "t1": {"id": "t1", "planId": PLAN, "bucketId": "b1", "title": "Revisar modelo 303",
                   "percentComplete": 0, "priority": 3, "dueDateTime": "2020-01-10T10:00:00Z",
                   "assignments": {U_ANA: {}}, "@odata.etag": "W/\"e1\"", "conversationThreadId": "hilo1"},
            "t2": {"id": "t2", "planId": PLAN, "bucketId": "b2", "title": "Preparar nóminas",
                   "percentComplete": 100, "priority": 5, "assignments": {U_BEA: {}}, "@odata.etag": "W/\"e2\""},
        }

    def get(self, ruta, params=None, headers=None):
        self.llamadas.append(("GET", ruta, params))
        if ruta == "/me/planner/plans":
            return {"value": [{"id": PLAN, "title": "Fiscal Badalona", "container": {"containerId": GRUPO}}]}
        if ruta == "/me/memberOf/microsoft.graph.group":
            return {"value": [{"id": GRUPO, "displayName": "Equipo", "groupTypes": ["Unified"]}]}
        if ruta == f"/groups/{GRUPO}/planner/plans":
            return {"value": [{"id": PLAN, "title": "Fiscal Badalona", "owner": GRUPO},
                              {"id": PLAN2, "title": "Fiscal Puigcerdà", "owner": GRUPO}]}
        if ruta.startswith("/planner/plans/") and ruta.endswith("/buckets"):
            return {"value": [{"id": "b2", "name": "En curso", "orderHint": "2"},
                              {"id": "b1", "name": "Pendiente", "orderHint": "1"}]}
        if ruta.startswith("/planner/plans/") and ruta.endswith("/tasks"):
            return {"value": list(self.tareas.values()), "@odata.nextLink": None}
        if ruta.startswith("/planner/plans/"):
            pid = ruta.split("/")[3]
            if pid == PLAN:
                return {"id": PLAN, "title": "Fiscal Badalona", "container": {"containerId": GRUPO}}
            raise pg.GraphError(404, "NotFound")
        if ruta == f"/groups/{GRUPO}/members/microsoft.graph.user":
            return {"value": [{"id": U_ANA, "displayName": "Ana Prueba", "mail": "ana@ejemplo.com"},
                              {"id": U_BEA, "displayName": "Bea Ejemplo", "mail": "bea@ejemplo.com"},
                              {"id": U_BERTA, "displayName": "Berta Ejemplo", "mail": "berta@ejemplo.com"}]}
        if ruta.endswith("/details"):
            return {"@odata.etag": "W/\"d1\"", "checklist": {"c1": {"title": "Pedir facturas", "isChecked": False}}}
        if ruta.startswith("/planner/tasks/"):
            tid = ruta.split("/")[3]
            if tid in self.tareas:
                return self.tareas[tid]
            raise pg.GraphError(404, "NotFound")
        if ruta == f"/groups/{GRUPO}/threads/hilo1/posts":
            return {"value": [{"createdDateTime": "2026-11-02", "from": {"emailAddress": {"name": "Bea Ejemplo"}},
                               "body": {"content": "<p>Hecho&nbsp;el borrador</p>"}},
                              {"createdDateTime": "2026-11-01", "from": {"emailAddress": {"name": "Ana Prueba"}},
                               "body": {"content": "<div>¿Cómo va?</div>"}}]}
        raise AssertionError(ruta)

    def post(self, ruta, json=None, headers=None):
        self.llamadas.append(("POST", ruta, json))
        if ruta == "/planner/tasks":
            return {"id": "nueva", **json}
        if ruta.endswith("/threads"):
            return {"id": "hilo-nuevo"}
        return {}

    def patch(self, ruta, json=None, headers=None):
        self.llamadas.append(("PATCH", ruta, json, headers))
        return {}

    def escrituras(self):
        return [c for c in self.llamadas if c[0] in ("POST", "PATCH")]


def test_planes_con_columnas_ordenadas():
    r = pg.planner_planes(FakeGraph())
    assert r["total"] == 2
    assert [c["nombre"] for c in r["planes"][0]["columnas"]] == ["Pendiente", "En curso"]


def test_tareas_de_un_plan_por_nombre_y_responsable():
    r = pg.planner_tareas(FakeGraph(), "badalona", incluir_completadas=True)
    assert r["total"] == 2
    t1 = next(t for t in r["tareas"] if t["id"] == "t1")
    assert t1["responsables"] == ["Ana Prueba"] and t1["columna"] == "Pendiente" and t1["tiene_comentarios"]
    r = pg.planner_tareas(FakeGraph(), PLAN, responsable="bea", incluir_completadas=True)
    assert [t["id"] for t in r["tareas"]] == ["t2"]


def test_tareas_vencidas_y_sin_completadas():
    r = pg.planner_tareas(FakeGraph(), PLAN, vencidas=True)
    assert [t["id"] for t in r["tareas"]] == ["t1"]


def test_plan_ambiguo():
    assert "varios planes" in pg.planner_tareas(FakeGraph(), "fiscal")["error"]


def test_crear_vista_previa_no_escribe():
    g = FakeGraph()
    r = pg.planner_crear_tarea(g, "Fiscal Badalona", "Nueva", responsables=["Ana"], vence="2026-12-01")
    assert r["vista_previa"] and r["responsables"] == ["Ana Prueba"] and r["columna"] == "Pendiente"
    assert not g.escrituras()


def test_crear_confirmado_con_asignacion_y_checklist():
    g = FakeGraph()
    r = pg.planner_crear_tarea(g, PLAN, "Nueva", columna="en curso", responsables=["ana@ejemplo.com", "Bea"],
                               prioridad="urgente", descripcion="Detalle", checklist=["a", "b"], confirmar=True)
    assert r["creada"] and r["id"] == "nueva"
    post = next(c for c in g.llamadas if c[0] == "POST")[2]
    assert set(post["assignments"]) == {U_ANA, U_BEA} and post["bucketId"] == "b2" and post["priority"] == 1
    det = next(c for c in g.llamadas if c[0] == "PATCH")
    assert det[1] == "/planner/tasks/nueva/details" and det[3] == {"If-Match": "W/\"d1\""}
    assert det[2]["description"] == "Detalle" and len(det[2]["checklist"]) == 2


def test_persona_ambigua_o_ajena():
    assert "varias personas" in pg.planner_crear_tarea(FakeGraph(), PLAN, "x", responsables=["Ejemplo"])["error"]
    assert "no es miembro" in pg.planner_crear_tarea(FakeGraph(), PLAN, "x", responsables=["Zoe"])["error"]


def test_modificar_asignar_y_avance():
    g = FakeGraph()
    r = pg.planner_modificar_tarea(g, "t1", anadir_responsables=["Berta"], quitar_responsables=["Ana"],
                                   avance="en curso", marcar_checklist=["facturas"])
    assert r["vista_previa"] and not g.escrituras()
    pg.planner_modificar_tarea(g, "t1", anadir_responsables=["Berta"], quitar_responsables=["Ana"],
                               avance="50", marcar_checklist=["facturas"], confirmar=True)
    tarea, det = g.escrituras()
    assert tarea[2]["assignments"] == {U_BERTA: pg.ASIG, U_ANA: None} and tarea[2]["percentComplete"] == 50
    assert tarea[3] == {"If-Match": "W/\"e1\""}
    assert det[2]["checklist"]["c1"]["isChecked"] is True


def test_modificar_sin_cambios():
    assert "ningún cambio" in pg.planner_modificar_tarea(FakeGraph(), "t1")["error"]


def test_leer_comentarios_ordenados_y_sin_html():
    r = pg.planner_comentarios(FakeGraph(), "t1")
    assert [c["autor"] for c in r["comentarios"]] == ["Ana Prueba", "Bea Ejemplo"]
    assert r["comentarios"][1]["texto"] == "Hecho el borrador"


def test_comentar_hilo_existente_y_nuevo():
    g = FakeGraph()
    assert pg.planner_comentar(g, "t1", "Ok")["vista_previa"] and not g.escrituras()
    pg.planner_comentar(g, "t1", "Ok", confirmar=True)
    assert g.escrituras()[0][1] == f"/groups/{GRUPO}/threads/hilo1/reply"
    g = FakeGraph()
    pg.planner_comentar(g, "t2", "Primero", confirmar=True)
    post, patch = g.escrituras()
    assert post[1] == f"/groups/{GRUPO}/threads" and patch[2] == {"conversationThreadId": "hilo-nuevo"}


def test_sin_permiso():
    class Denegado(FakeGraph):
        def get(self, *a, **k):
            raise pg.GraphError(403, "Forbidden")
    assert "Tasks.ReadWrite" in pg.planner_planes(Denegado())["error"]
