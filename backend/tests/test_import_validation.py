import io
import zipfile

import ezdxf
import numpy as np
import pytest
import trimesh

from app.core.synthetic import box
from app.importers.base import ImportFailed
from app.importers.formats import import_file
from app.models import ModelRole
from app.services.models_io import load_and_validate
from app.validation.checks import check_compatibility, validate_solid


def stl_bytes(mesh):
    return mesh.export(file_type="stl")


def dxf_bytes(mesh, layer="SOLID"):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for f in mesh.faces:
        a, b, c = (tuple(mesh.vertices[i]) for i in f)
        msp.add_3dface([a, b, c, c], dxfattribs={"layer": layer})
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode()


@pytest.mark.parametrize("fmt", ["stl", "obj", "ply"])
def test_mesh_formats_roundtrip(fmt):
    m = box([0, 0, 0], [20, 10, 30])
    data = m.export(file_type=fmt)
    data = data.encode() if isinstance(data, str) else data
    lm = load_and_validate(data, f"design.{fmt}", ModelRole.stope_design)
    assert lm.report.status in ("ok", "warning"), lm.report.checks
    assert lm.summary["volume_m3"] == pytest.approx(6000.0)


def test_dxf_3dface_solid():
    m = box([0, 0, 0], [20, 10, 30])
    lm = load_and_validate(dxf_bytes(m), "design.dxf", ModelRole.stope_design)
    assert lm.report.status == "ok", lm.report.checks
    assert lm.summary["volume_m3"] == pytest.approx(6000.0)
    assert lm.summary["vertices_clean"] == 8


def test_datamine_wireframe_zip():
    m = box([0, 0, 0], [20, 10, 30])
    pts = "PID,XP,YP,ZP\n" + "\n".join(f"{i + 1},{x},{y},{z}" for i, (x, y, z) in enumerate(m.vertices))
    trs = "TRIANGLE,PID1,PID2,PID3\n" + "\n".join(f"{i + 1},{a + 1},{b + 1},{c + 1}" for i, (a, b, c) in enumerate(m.faces))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("stope710pt.csv", pts)
        z.writestr("stope710tr.csv", trs)
    lm = load_and_validate(buf.getvalue(), "stope710.zip", ModelRole.survey_solid)
    assert lm.report.status == "ok", lm.report.checks
    assert lm.summary["volume_m3"] == pytest.approx(6000.0)


def test_datamine_binary_gives_clear_instruction():
    with pytest.raises(ImportFailed, match="Datamine"):
        import_file(b"\x00" * 4096, "stope.dm")


def test_dwg_requires_dxf():
    with pytest.raises(ImportFailed, match="DXF"):
        import_file(b"AC1032", "plan.dwg")


def test_unknown_format():
    with pytest.raises(ImportFailed, match="не поддерживается"):
        import_file(b"x", "a.xyz")


def test_block_model_csv():
    csv = "XC,YC,ZC,XINC,YINC,ZINC,DENSITY,AU,CU\n1,1,1,2,2,2,2.8,3.1,0.5\n3,1,1,2,2,2,2.7,0.2,0.1\n"
    lm = load_and_validate(csv.encode(), "bm.csv", ModelRole.block_model)
    assert lm.report.status == "ok", lm.report.checks
    assert lm.summary["blocks"] == 2 and set(lm.summary["elements"]) == {"AU", "CU"}


def test_block_model_missing_density():
    lm = load_and_validate(b"XC,YC,ZC,XINC,YINC,ZINC\n1,1,1,2,2,2\n", "bm.csv", ModelRole.block_model)
    assert lm.report.status == "error"
    assert "плотности" in lm.report.errors[0]["message"]


def test_points_txt_without_header_and_duplicates():
    txt = "100 200 300\n100 200 300\n101 200 300\n"
    lm = load_and_validate(txt.encode(), "pts.txt", ModelRole.survey_points)
    assert lm.summary["points"] == 3
    dup = next(c for c in lm.report.checks if c["code"] == "duplicate_points")
    assert dup["level"] == "warning" and dup["details"]["count"] == 1


def test_open_solid_is_rejected_with_reason():
    m = box([0, 0, 0], [20, 10, 30])
    holed = trimesh.Trimesh(m.vertices, m.faces[:-2], process=False)
    lm = load_and_validate(stl_bytes(holed), "survey.stl", ModelRole.survey_solid)
    assert lm.report.status == "error"
    assert "не замкнут" in lm.report.errors[0]["message"]
    assert lm.mesh is None


def test_inverted_normals_fixed_with_warning():
    m = box([0, 0, 0], [20, 10, 30])
    m.invert()
    rep, prepared, summary = validate_solid(m)
    assert rep.status == "warning"
    assert prepared.volume == pytest.approx(6000.0)


def test_inconsistent_winding_rejected():
    m = box([0, 0, 0], [20, 10, 30])
    faces = m.faces.copy()
    faces[0] = faces[0][::-1]
    rep, prepared, _ = validate_solid(trimesh.Trimesh(m.vertices, faces, process=False))
    assert rep.status == "error" and prepared is None


def test_units_warning_for_millimetres():
    m = box([0, 0, 0], [20000, 10000, 30000])
    rep, _, _ = validate_solid(m)
    assert any(c["code"] == "units" and c["level"] == "warning" for c in rep.checks)


def test_overlapping_bodies_are_unioned():
    m = trimesh.util.concatenate([box([0, 0, 0], [10, 10, 10]), box([5, 0, 0], [15, 10, 10])])
    rep, prepared, summary = validate_solid(m)
    assert summary["volume_m3"] == pytest.approx(1500.0)
    assert any(c["code"] == "overlap" and c["level"] == "warning" for c in rep.checks)


def test_compatibility_detects_different_coordinate_systems():
    rep = check_compatibility({
        "stope_design": [[500000, 4300000, 700], [500020, 4300010, 730]],
        "survey_solid": [[0, 0, 0], [20, 10, 30]],
    })
    assert rep.errors and "разные системы координат" in rep.errors[0]["message"]
