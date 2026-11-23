"""Проверка исходных данных до расчёта (ТЗ п. 4.3, 11).

Каждая проверка возвращает запись {code, level, message, details}.
level: ok | warning | error. Любой error блокирует использование файла в расчёте.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from ..core.blockmodel import BlockModel
from ..core.geometry import GeometryError, Solid, union_all

# Габариты, при которых модель в метрах выглядит подозрительно (вероятно мм/км/футы)
MIN_EXTENT_M = 0.5
MAX_EXTENT_M = 20_000.0


@dataclass
class Report:
    checks: list[dict] = field(default_factory=list)

    def add(self, code: str, level: str, message: str, **details):
        self.checks.append({"code": code, "level": level, "message": message, "details": details})

    @property
    def status(self) -> str:
        levels = {c["level"] for c in self.checks}
        return "error" if "error" in levels else "warning" if "warning" in levels else "ok"

    @property
    def errors(self) -> list[dict]:
        return [c for c in self.checks if c["level"] == "error"]


def _n_components(m: trimesh.Trimesh) -> int:
    groups = trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(m.faces)), engine="scipy")
    return int(len(groups))


def _unit_checks(rep: Report, lo: np.ndarray, hi: np.ndarray):
    ext = hi - lo
    if not np.all(np.isfinite(ext)):
        rep.add("coords_finite", "error", "В координатах есть NaN или бесконечные значения")
        return
    rep.add("bbox", "ok", "Габарит модели", min=lo.tolist(), max=hi.tolist(), extent=ext.tolist())
    if ext.max() < MIN_EXTENT_M:
        rep.add("units", "warning", f"Габарит модели {ext.max():.3f} — слишком мал для метров. Проверьте единицы (км?)")
    elif ext.max() > MAX_EXTENT_M:
        rep.add("units", "warning", f"Габарит модели {ext.max():.0f} — слишком велик для камеры в метрах. Проверьте единицы (мм? футы?)")
    else:
        rep.add("units", "ok", "Габарит соответствует метрам")


def validate_solid(mesh: trimesh.Trimesh, *, merge_tol: float = 1e-6,
                   indexed_format: bool = True) -> tuple[Report, trimesh.Trimesh | None, dict]:
    """Проверка замкнутого солида. Возвращает отчёт, подготовленную сетку (или None) и сводку.

    indexed_format=False для STL/DXF(3DFACE): там каждая грань хранит свои вершины,
    и совпадающие вершины — норма формата, а не ошибка.
    """
    rep = Report()
    summary: dict = {}
    if mesh is None or len(mesh.faces) == 0:
        rep.add("empty", "error", "В файле нет треугольников")
        return rep, None, summary

    m = mesh.copy()
    n_v0, n_f0 = len(m.vertices), len(m.faces)
    summary.update(vertices=n_v0, triangles=n_f0)

    # Дубли вершин (типично для 3DFACE/STL — каждая грань со своими вершинами)
    m.merge_vertices(digits_vertex=int(-np.log10(merge_tol)))
    dup = n_v0 - len(m.vertices)
    if dup:
        rep.add("duplicate_vertices", "warning" if indexed_format else "ok",
                f"Объединено совпадающих вершин: {dup}" + ("" if indexed_format else " (норма для формата)"),
                count=int(dup))
    else:
        rep.add("duplicate_vertices", "ok", "Дублирующих вершин нет")

    # Вырожденные и повторяющиеся треугольники
    areas = m.area_faces
    degen = int((areas <= 1e-10).sum())
    if degen:
        m.update_faces(areas > 1e-10)
        rep.add("degenerate_faces", "warning", f"Удалено вырожденных треугольников: {degen}", count=degen)
    uniq = m.unique_faces()
    dup_f = int(len(m.faces) - uniq.sum())
    if dup_f:
        m.update_faces(uniq)
        rep.add("duplicate_faces", "warning", f"Удалено повторяющихся треугольников: {dup_f}", count=dup_f)
    m.remove_unreferenced_vertices()

    lo, hi = m.bounds
    _unit_checks(rep, lo, hi)

    # Топология: рёбра, принадлежащие не ровно двум треугольникам
    edges = m.edges_sorted
    _, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int((counts == 1).sum())
    nonmanifold = int((counts > 2).sum())
    if open_edges:
        rep.add("watertight", "error", f"Солид не замкнут: {open_edges} открытых рёбер (дыры в каркасе)",
                open_edges=open_edges)
    else:
        rep.add("watertight", "ok", "Солид замкнут")
    if nonmanifold:
        rep.add("non_manifold", "error", f"Неманифолдные рёбра (общие для >2 треугольников): {nonmanifold}",
                count=nonmanifold)
    if open_edges or nonmanifold:
        summary["components"] = _n_components(m)
        return rep, None, summary

    if not m.is_winding_consistent:
        rep.add("winding", "error", "Несогласованная ориентация треугольников (часть нормалей перевёрнута)")
        return rep, None, summary
    rep.add("winding", "ok", "Ориентация треугольников согласована")

    if m.volume < 0:
        m.invert()
        rep.add("orientation", "warning", "Нормали направлены внутрь — ориентация инвертирована автоматически")
    else:
        rep.add("orientation", "ok", "Нормали направлены наружу")

    n_comp = _n_components(m)
    summary["components"] = n_comp
    if n_comp > 1:
        rep.add("components", "warning", f"Файл содержит {n_comp} отдельных тел — будут объединены",
                count=n_comp)

    # Перенос в локальные координаты для точных булевых операций
    origin = np.floor(lo)
    local = m.copy()
    local.apply_translation(-origin)
    try:
        if n_comp > 1:
            parts = [Solid.from_trimesh(c) for c in local.split(only_watertight=False, repair=False)]
            raw_v = sum(p.volume for p in parts)
            solid = union_all(parts)
        else:
            solid = Solid.from_trimesh(local)
            raw_v = solid.volume
    except GeometryError as exc:
        rep.add("manifold", "error", str(exc))
        return rep, None, summary
    clean_v = solid.volume
    if raw_v > 0 and abs(raw_v - clean_v) / raw_v > 1e-6:
        rep.add("overlap", "warning",
                f"Тела в файле перекрываются: сумма объёмов {raw_v:.2f} м³, объединённый объём {clean_v:.2f} м³. "
                "В расчёте используется объединение (без двойного счёта).",
                raw_volume=raw_v, clean_volume=clean_v)
        m = solid.to_trimesh()
        m.apply_translation(origin)
    else:
        rep.add("overlap", "ok", "Перекрытий тел нет")

    summary.update(volume_m3=float(clean_v), area_m2=float(m.area), bbox=[lo.tolist(), hi.tolist()],
                   triangles_clean=int(len(m.faces)), vertices_clean=int(len(m.vertices)))
    return rep, m, summary


def validate_points(points: np.ndarray) -> tuple[Report, dict]:
    rep = Report()
    pts = np.asarray(points, float)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) == 0:
        rep.add("points", "error", "Нет корректных точек XYZ")
        return rep, {}
    bad = int((~np.isfinite(pts)).any(axis=1).sum())
    if bad:
        rep.add("coords_finite", "error", f"Строк с пустыми/нечисловыми координатами: {bad}", count=bad)
        pts = pts[np.isfinite(pts).all(axis=1)]
    uniq = np.unique(np.round(pts, 6), axis=0)
    dup = len(pts) - len(uniq)
    rep.add("duplicate_points", "warning" if dup else "ok",
            f"Дублирующих точек: {dup}" if dup else "Дублирующих точек нет", count=int(dup))
    if len(pts):
        _unit_checks(rep, pts.min(axis=0), pts.max(axis=0))
    return rep, {"points": int(len(pts)), "bbox": [pts.min(0).tolist(), pts.max(0).tolist()] if len(pts) else None}


def validate_block_model(bm: BlockModel) -> tuple[Report, dict]:
    rep = Report()
    n = len(bm.centers)
    if n == 0:
        rep.add("empty", "error", "Блочная модель пустая")
        return rep, {}
    if not np.isfinite(bm.centers).all() or not np.isfinite(bm.sizes).all():
        rep.add("coords_finite", "error", "Пустые значения в координатах или размерах блоков")
        return rep, {}
    if (bm.sizes <= 0).any():
        rep.add("block_size", "error", f"Блоков с неположительным размером: {int((bm.sizes <= 0).any(axis=1).sum())}")
    if not np.isfinite(bm.density).all():
        rep.add("density", "error", f"Блоков без плотности: {int((~np.isfinite(bm.density)).sum())}")
    elif ((bm.density < 1.0) | (bm.density > 6.0)).any():
        k = int(((bm.density < 1.0) | (bm.density > 6.0)).sum())
        rep.add("density", "warning", f"Плотность вне диапазона 1–6 т/м³ у {k} блоков")
    else:
        rep.add("density", "ok", f"Плотность {bm.density.min():.2f}–{bm.density.max():.2f} т/м³")
    for e, g in bm.grades.items():
        if (g < 0).any() or not np.isfinite(g).all():
            rep.add(f"grade_{e}", "warning", f"{e}: отрицательные или пустые содержания у {int(((g < 0) | ~np.isfinite(g)).sum())} блоков")
    _unit_checks(rep, bm.lo.min(axis=0), bm.hi.max(axis=0))
    return rep, {"blocks": n, "elements": list(bm.grades), "volume_m3": float(np.prod(bm.sizes, axis=1).sum()),
                 "bbox": [bm.lo.min(0).tolist(), bm.hi.max(0).tolist()]}


def check_compatibility(bboxes: dict[str, list]) -> Report:
    """Совместимость координат моделей одной камеры (ТЗ п. 4.3, 11).

    bboxes: role -> [[xmin,ymin,zmin],[xmax,ymax,zmax]].
    Модели должны перекрываться в пространстве; разница порядков координат
    указывает на разные системы координат (локальная сетка vs UTM).
    """
    rep = Report()
    items = {k: (np.array(v[0], float), np.array(v[1], float)) for k, v in bboxes.items() if v}
    if "stope_design" not in items:
        return rep
    dlo, dhi = items["stope_design"]
    dsize = float(np.max(dhi - dlo))
    for role, (lo, hi) in items.items():
        if role == "stope_design":
            continue
        overlap = np.all(hi > dlo) and np.all(lo < dhi)
        dist = float(np.linalg.norm((lo + hi) / 2 - (dlo + dhi) / 2))
        if not overlap:
            mag_d, mag_r = np.log10(np.abs(dlo).max() + 1), np.log10(np.abs(lo).max() + 1)
            hint = " Порядки координат различаются — вероятно, разные системы координат." if abs(mag_d - mag_r) >= 1 else ""
            rep.add(f"overlap_{role}", "error",
                    f"Модель «{role}» не пересекается с проектом камеры (расстояние центров {dist:.1f} м).{hint}",
                    distance_m=dist)
        elif dist > 3 * dsize:
            rep.add(f"offset_{role}", "warning", f"Центр модели «{role}» смещён на {dist:.1f} м от проекта", distance_m=dist)
        else:
            rep.add(f"overlap_{role}", "ok", f"Модель «{role}» совмещена с проектом", distance_m=dist)
    return rep
