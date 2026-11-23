"""Контрольные примеры расчётного ядра (ТЗ п. 19): результаты сравниваются с
аналитическими значениями и с независимым методом Монте-Карло."""
import math

import numpy as np
import pytest
import trimesh

from app.core.blockmodel import BlockModel
from app.core.reconciliation import ReconciliationInput, ReconciliationParams, run_reconciliation
from app.core.synthetic import OFFSET, REFERENCE_EXPECTED, box, reference_stope

REL = 1e-9


def run(**kw):
    return run_reconciliation(ReconciliationInput(**kw))


def test_reference_stope_exact_values():
    r = run(**reference_stope())
    ol, dl, cf = r["ore_loss"], r["dilution"], r["conformance"]
    flat = {**ol, **dl, **cf}
    for key, expected in REFERENCE_EXPECTED.items():
        assert flat[key] == pytest.approx(expected, rel=REL), key
    assert dl["planned_dilution_pct"] + dl["unplanned_dilution_pct"] == pytest.approx(dl["total_dilution_pct"])
    assert dl["planned_dilution_design_pct"] == pytest.approx(20.0)  # (6000-4800)/6000
    assert r["checks"]["loss_balance_m3"] < 1e-6
    assert r["checks"]["survey_balance_m3"] < 1e-6
    assert r["warnings"] == []


def test_reference_stope_tonnage_with_constant_density():
    p = ReconciliationParams(density_ore=2.8, density_waste=2.7)
    r = run(**reference_stope(), params=p)
    assert r["ore_loss"]["T_loss"] == pytest.approx(480 * 2.8)
    t_ore, t_waste = 4320 * 2.8, 1620 * 2.7
    assert r["dilution"]["dilution_tonnage_pct"] == pytest.approx(t_waste / (t_ore + t_waste) * 100)


def test_zones_reference_stope():
    r = run(**reference_stope())
    z = r["ore_loss"]["by_zone"]
    assert z["floor"] == pytest.approx(480.0)                      # недобор только по почве
    assert sum(z.values()) == pytest.approx(480.0)
    over = r["conformance"]["overbreak_by_zone"]
    assert over["wall_S"] == pytest.approx(540.0)                  # перебор по южной стенке
    under = r["conformance"]["underbreak_by_zone"]
    assert under["floor"] == pytest.approx(600.0)
    wz = r["dilution"]["by_zone"]
    assert wz["wall_S"] == pytest.approx(20 * 2 * 27)              # порода у южного контакта руды
    assert wz["wall_N"] == pytest.approx(20 * 1 * 27)
    assert sum(wz.values()) == pytest.approx(1620.0)


def test_elevation_profile_and_areas():
    r = run(**reference_stope())
    prof = r["ore_loss"]["by_elevation"]
    assert sum(b["volume_m3"] for b in prof) == pytest.approx(480.0)
    assert all(b["z_from"] >= OFFSET[2] - 5 and b["z_to"] <= OFFSET[2] + 5 for b in prof)
    areas = r["ore_loss"]["areas"]
    assert len(areas) == 1 and areas[0]["dominant_zone"] == "floor"
    assert areas[0]["centroid"][2] == pytest.approx(OFFSET[2] + 1.5)


def test_translation_and_rotation_invariance():
    base = run(**reference_stope(offset=np.zeros(3)))
    utm = run(**reference_stope())
    rot = trimesh.transformations.rotation_matrix(math.radians(33), [0, 0, 1], point=OFFSET)
    rotated = {k: m.copy().apply_transform(rot) for k, m in reference_stope().items()}
    rr = run(**rotated)
    for key in ("V_plan_ore", "V_loss"):
        assert utm["ore_loss"][key] == pytest.approx(base["ore_loss"][key], rel=1e-9)
        assert rr["ore_loss"][key] == pytest.approx(base["ore_loss"][key], rel=1e-9)
    for key in ("V_actual", "V_waste"):
        assert rr["dilution"][key] == pytest.approx(base["dilution"][key], rel=1e-9)


def test_cylinder_against_analytic_polygon_area():
    n, rad, h = 64, 5.0, 20.0
    area = 0.5 * n * rad**2 * math.sin(2 * math.pi / n)   # точная площадь n-угольника
    design = trimesh.creation.cylinder(radius=rad, height=h, sections=n).apply_translation(OFFSET + [0, 0, h / 2])
    survey = design.copy().apply_translation([0, 0, 2.0])  # съёмка поднята на 2 м: недобор 2 м по почве
    ore = box([-50, -50, -50], [50, 50, 50])
    r = run(design=design, orebody=ore, survey=survey)
    assert r["ore_loss"]["V_plan_ore"] == pytest.approx(area * h, rel=1e-9)
    assert r["ore_loss"]["V_loss"] == pytest.approx(area * 2.0, rel=1e-9)
    assert r["conformance"]["V_overbreak"] == pytest.approx(area * 2.0, rel=1e-9)
    assert r["ore_loss"]["by_zone"]["floor"] == pytest.approx(area * 2.0, rel=1e-6)
    assert r["conformance"]["overbreak_by_zone"]["roof"] == pytest.approx(area * 2.0, rel=1e-6)


def _column_intervals(mesh, xy, z0):
    """Пересечения вертикальных лучей с сеткой → список интервалов [z_in, z_out] на каждую колонку."""
    origins = np.column_stack([xy, np.full(len(xy), z0)])
    dirs = np.tile([0.0, 0.0, 1.0], (len(xy), 1))
    loc, idx, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    out = [[] for _ in range(len(xy))]
    for i in np.unique(idx):
        z = np.sort(loc[idx == i, 2])
        z = z[np.concatenate([[True], np.diff(z) > 1e-9])]   # дубли на рёбрах
        if len(z) % 2 == 0:
            out[i] = list(zip(z[0::2], z[1::2]))
    return out


def _len_where(fn, *interval_sets):
    """Длина участков оси z, где логическая функция fn(in_a, in_b, ...) истинна."""
    pts = sorted({z for ivs in interval_sets for a, b in ivs for z in (a, b)})
    total = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        m = (a + b) / 2
        flags = [any(lo <= m <= hi for lo, hi in ivs) for ivs in interval_sets]
        if fn(*flags):
            total += b - a
    return total


def test_irregular_shapes_against_column_integration():
    """Независимая проверка (ТЗ п. 19): объёмы булевых операций сравниваются с
    интегрированием по вертикальным колонкам (трассировка лучей + интервалы по Z)."""
    rng = np.random.default_rng(7)
    design = trimesh.creation.icosphere(subdivisions=3, radius=10).apply_translation(OFFSET)
    survey = trimesh.creation.icosphere(subdivisions=3, radius=10.5)
    survey.vertices *= [1.0, 0.8, 1.1]
    survey.apply_translation(OFFSET + [1.5, -0.5, 0.7])
    ore = trimesh.creation.box(extents=[30, 12, 30]).apply_transform(
        trimesh.transformations.rotation_matrix(0.3, [0, 0, 1])).apply_translation(OFFSET + [0, 1, 0])
    r = run(design=design, orebody=ore, survey=survey)

    lo = np.minimum(design.bounds[0], survey.bounds[0]) - 0.5
    hi = np.maximum(design.bounds[1], survey.bounds[1]) + 0.5
    n = 160
    step = (hi[:2] - lo[:2]) / n
    gx, gy = np.meshgrid(lo[0] + (np.arange(n) + 0.5) * step[0], lo[1] + (np.arange(n) + 0.5) * step[1])
    xy = np.column_stack([gx.ravel(), gy.ravel()]) + rng.uniform(-1e-4, 1e-4, (n * n, 2))
    cols = [_column_intervals(m, xy, lo[2] - 50) for m in (design, survey, ore)]
    cell = step[0] * step[1]

    def vol(fn):
        return cell * sum(_len_where(fn, d, s, o) for d, s, o in zip(*cols))

    checks = {
        "V_plan_ore": (r["ore_loss"]["V_plan_ore"], vol(lambda d, s, o: d and o)),
        "V_loss": (r["ore_loss"]["V_loss"], vol(lambda d, s, o: d and o and not s)),
        "V_waste": (r["dilution"]["V_waste"], vol(lambda d, s, o: s and not o)),
        "V_overbreak": (r["conformance"]["V_overbreak"], vol(lambda d, s, o: s and not d)),
    }
    for key, (exact, est) in checks.items():
        print(f"{key}: boolean={exact:.3f}  columns={est:.3f}  diff={(exact - est) / exact * 100:+.3f}%")
        assert exact == pytest.approx(est, rel=0.01), f"{key}: boolean={exact:.2f}, columns={est:.2f}"


def _layered_block_model(lo, hi, dz=1.0):
    """Блоки 5×2×1 м; плотность и содержание Au меняются по слоям (z)."""
    xs = np.arange(lo[0], hi[0], 5.0) + 2.5
    ys = np.arange(lo[1], hi[1], 2.0) + 1.0
    zs = np.arange(lo[2], hi[2], dz) + dz / 2
    c = np.array(np.meshgrid(xs, ys, zs, indexing="ij")).reshape(3, -1).T
    k = np.floor(c[:, 2] - lo[2]).astype(int)            # номер слоя от низа модели
    dens = 2.5 + 0.1 * (k % 5)
    au = 1.0 + (k % 5)
    cu = 0.5 * np.ones(len(c))
    return BlockModel(c + OFFSET, np.tile([5.0, 2.0, dz], (len(c), 1)), dens, {"AU": au, "CU": cu})


def test_block_model_tonnage_and_metal():
    # Модель от z=0, поэтому слои потерь z∈[0,3] имеют k = 0,1,2
    bm = _layered_block_model([-5, -2, 0], [25, 12, 35])
    st = reference_stope()
    r = run(**st, block_model=bm)
    ol = r["ore_loss"]
    # Потери: [0,20]×[1,9]×[0,3] → по 160 м³ в слоях k=0,1,2
    t_expected = 160 * (2.5 + 2.6 + 2.7)
    au_expected = 160 * (2.5 * 1 + 2.6 * 2 + 2.7 * 3) / 1000      # кг
    cu_expected = t_expected * 0.5 / 100                          # т
    assert ol["T_loss"] == pytest.approx(t_expected, rel=1e-9)
    assert ol["metal_loss"]["AU"] == pytest.approx(au_expected, rel=1e-9)
    assert ol["metal_loss"]["CU"] == pytest.approx(cu_expected, rel=1e-9)
    assert ol["grade_loss"]["AU"] == pytest.approx(au_expected * 1000 / t_expected, rel=1e-9)
    assert r["dilution"]["V_undefined"] == 0.0


def test_undefined_outside_block_model():
    # Блочная модель не покрывает южный перебор y∈[-1,0]
    bm = _layered_block_model([-5, 0, 0], [25, 12, 35])
    r = run(**reference_stope(), block_model=bm)
    dl = r["dilution"]
    assert dl["V_undefined"] == pytest.approx(20 * 1 * 27)
    assert dl["V_waste"] == pytest.approx(1620 - 540)
    assert any("вне блочной модели" in w for w in r["warnings"])


def test_low_grade_separated_from_waste():
    st = reference_stope()
    low = box([-5, -3, -5], [25, 1, 35])     # некондиция у южного контакта (y∈[-3,1])
    r = run(**st, low_grade=low)
    dl = r["dilution"]
    assert dl["V_low_grade"] == pytest.approx(20 * 2 * 27)      # y∈[-1,1]
    assert dl["V_waste"] == pytest.approx(20 * 1 * 27)          # только y∈[9,10]
    assert dl["V_planned_low_grade"] == pytest.approx(20 * 1 * 27)
    assert dl["V_unplanned_low_grade"] == pytest.approx(20 * 1 * 27)
    assert dl["V_ore"] + dl["V_low_grade"] + dl["V_waste"] == pytest.approx(dl["V_actual"])


def test_deterministic():
    a = run(**reference_stope())
    b = run(**reference_stope())
    assert a == b


def test_no_ore_in_design_warns():
    st = reference_stope()
    st["orebody"] = box([100, 100, 100], [110, 110, 110])
    r = run(**st)
    assert r["ore_loss"]["ore_loss_pct"] is None
    assert any("не пересекает" in w for w in r["warnings"])
