"""Сквозной сценарий через API: проект → камера → загрузка → проверка → анализ → история версий."""
import pytest
from fastapi.testclient import TestClient

from app.core.synthetic import REFERENCE_EXPECTED, box, reference_stope
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def auth(client, username="admin", password="admin-password"):
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def upload(client, h, stope_id, category, role, name, data):
    return client.post(f"/api/stopes/{stope_id}/files", headers=h,
                       data={"category": category, "model_role": role}, files={"file": (name, data)})


@pytest.fixture(scope="module")
def stope(client):
    h = auth(client)
    p = client.post("/api/projects", headers=h, json={"name": "Kapan", "crs": "Kapan local grid"}).json()
    m = client.post(f"/api/projects/{p['id']}/mines", headers=h, json={"name": "Shahumyan"}).json()
    lv = client.post(f"/api/mines/{m['id']}/levels", headers=h, json={"name": "710", "elevation": 710}).json()
    s = client.post(f"/api/levels/{lv['id']}/stopes", headers=h, json={"name": "710-SH-025", "orebody": "Vein 1"})
    assert s.status_code == 201, s.text
    return {"project": p, "stope": s.json(), "h": h}


def test_requires_auth(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/login", data={"username": "admin", "password": "wrong"}).status_code == 401


def test_full_reconciliation_flow(client, stope):
    h, sid = stope["h"], stope["stope"]["id"]
    st = reference_stope()

    # Анализ без данных не запускается и объясняет причину
    r = client.post(f"/api/stopes/{sid}/analyses", headers=h, json={})
    assert r.status_code == 422 and "Не загружены" in r.json()["detail"]

    for cat, role, key in (("design", "stope_design", "design"), ("geological", "orebody", "orebody"),
                           ("survey", "survey_solid", "survey")):
        r = upload(client, h, sid, cat, role, f"{key}.stl", st[key].export(file_type="stl"))
        assert r.status_code == 201, r.text
        assert r.json()["validation_status"] == "ok", r.json()["validation_report"]

    assert client.get(f"/api/stopes/{sid}", headers=h).json()["bbox"] is not None

    r = client.post(f"/api/stopes/{sid}/analyses", headers=h, json={"params": {"density_ore": 2.8}})
    assert r.status_code == 202, r.text
    job = client.get(f"/api/analyses/{r.json()['id']}", headers=h).json()
    assert job["status"] == "done", job["message"]
    res = job["result"]
    assert res["ore_loss"]["V_loss"] == pytest.approx(REFERENCE_EXPECTED["V_loss"])
    assert res["ore_loss"]["ore_loss_pct"] == pytest.approx(10.0)
    assert res["dilution"]["dilution_volume_pct"] == pytest.approx(REFERENCE_EXPECTED["dilution_volume_pct"])
    assert set(job["inputs"]) == {"stope_design", "orebody", "survey_solid"}
    assert all(len(v["sha256"]) == 64 for v in job["inputs"].values())
    assert "V_loss" in res["formulas"]

    # Новая съёмка → новая версия файла и новый анализ; старые сохраняются (ТЗ п. 13, 19.13)
    new_survey = box([0, -1, 1], [20, 10, 30])
    r = upload(client, h, sid, "survey", "survey_solid", "survey_v2.stl", new_survey.export(file_type="stl"))
    assert r.json()["version"] == 2
    r = client.post(f"/api/stopes/{sid}/analyses", headers=h, json={})
    job2 = client.get(f"/api/analyses/{r.json()['id']}", headers=h).json()
    assert job2["version"] == 2 and job2["inputs"]["survey_solid"]["version"] == 2
    assert job2["result"]["ore_loss"]["V_loss"] == pytest.approx(20 * 8 * 1)
    hist = client.get(f"/api/stopes/{sid}/analyses", headers=h).json()
    assert [j["version"] for j in hist] == [2, 1]
    files = client.get(f"/api/stopes/{sid}/files", headers=h).json()
    surveys = [f for f in files if f["model_role"] == "survey_solid"]
    assert len(surveys) == 2 and sum(f["is_active"] for f in surveys) == 1

    # Проект-уровень: последние результаты в списке камер
    lst = client.get(f"/api/projects/{stope['project']['id']}/stopes", headers=h).json()
    assert lst[0]["last_analysis"]["version"] == 2


def test_bad_file_blocks_nothing_but_is_recorded(client, stope):
    h, sid = stope["h"], stope["stope"]["id"]
    m = box([0, 0, 0], [20, 10, 30])
    import trimesh
    holed = trimesh.Trimesh(m.vertices, m.faces[:-1], process=False)
    r = upload(client, h, sid, "survey", "survey_solid", "broken.stl", holed.export(file_type="stl"))
    assert r.status_code == 201
    body = r.json()
    assert body["validation_status"] == "error" and body["is_active"] is False
    # активной остаётся предыдущая корректная версия
    files = client.get(f"/api/stopes/{sid}/files", headers=h).json()
    assert [f["version"] for f in files if f["model_role"] == "survey_solid" and f["is_active"]] == [2]
    # явный выбор ошибочного файла запрещён
    r = client.post(f"/api/stopes/{sid}/analyses", headers=h, json={"file_ids": {"survey_solid": body["id"]}})
    assert r.status_code == 422 and "не прошёл проверку" in r.json()["detail"]


def test_role_permissions(client, stope):
    h, sid = stope["h"], stope["stope"]["id"]
    r = client.post("/api/users", headers=h, json={"username": "surveyor1", "password": "survey-pass-1",
                                                     "role": "surveyor"})
    assert r.status_code == 201
    hs = auth(client, "surveyor1", "survey-pass-1")
    data = box([0, 0, 0], [1, 1, 1]).export(file_type="stl")
    assert upload(client, hs, sid, "design", "stope_design", "d.stl", data).status_code == 403
    assert upload(client, hs, sid, "survey", "survey_points", "p.stl", data).status_code == 201
    assert client.post(f"/api/stopes/{sid}/analyses", headers=hs, json={}).status_code == 403
    assert client.post("/api/projects", headers=hs, json={"name": "X"}).status_code == 403


def test_role_category_mismatch(client, stope):
    h, sid = stope["h"], stope["stope"]["id"]
    data = box([0, 0, 0], [1, 1, 1]).export(file_type="stl")
    assert upload(client, h, sid, "design", "orebody", "x.stl", data).status_code == 422


def test_audit_log(client, stope):
    rows = client.get("/api/audit", headers=stope["h"]).json()
    actions = {r["action"] for r in rows}
    assert {"file.upload", "analysis.create", "stope.create", "auth.login"} <= actions
