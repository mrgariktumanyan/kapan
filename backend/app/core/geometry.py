"""Точные булевы операции над замкнутыми триангулированными солидами.

Все объёмные операции выполняются через manifold3d (робастные булевы операции
над многообразными сетками). Объём считается по формуле дивергенции
(сумма знаковых объёмов тетраэдров), т.е. точно для заданной триангуляции.
Никакой воксельной/визуальной аппроксимации здесь нет.
"""
from __future__ import annotations

from dataclasses import dataclass

import manifold3d as m3d
import numpy as np
import trimesh


class GeometryError(ValueError):
    """Геометрия непригодна для булевых операций (не замкнута, самопересечения и т.п.)."""


@dataclass(frozen=True)
class Solid:
    """Обёртка над manifold3d.Manifold с удобным доступом к объёму и сетке."""

    manifold: m3d.Manifold
    name: str = ""

    # --- конструкторы -----------------------------------------------------
    @classmethod
    def from_trimesh(cls, mesh: trimesh.Trimesh, name: str = "") -> "Solid":
        verts = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
        faces = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
        if len(faces) == 0:
            raise GeometryError(f"{name or 'solid'}: пустая сетка")
        # Mesh64 — двойная точность. Дополнительно движок сверки переносит все модели
        # в локальное начало координат, чтобы не терять точность на UTM-координатах.
        mm = m3d.Mesh64(vert_properties=verts, tri_verts=faces.astype(np.uint64))
        man = m3d.Manifold(mm)
        status = man.status()
        if status != m3d.Error.NoError:
            raise GeometryError(
                f"{name or 'solid'}: сетка не является замкнутым многообразием ({status.name}). "
                "Проверьте замкнутость солида, дубли вершин и ориентацию треугольников."
            )
        if man.volume() <= 0:
            raise GeometryError(f"{name or 'solid'}: нулевой или отрицательный объём")
        return cls(man, name)

    @classmethod
    def box(cls, lo, hi, name: str = "") -> "Solid":
        lo = np.asarray(lo, dtype=float)
        hi = np.asarray(hi, dtype=float)
        size = hi - lo
        if np.any(size <= 0):
            return cls(m3d.Manifold(), name)
        man = m3d.Manifold.cube(tuple(size.tolist())).translate(tuple(lo.tolist()))
        return cls(man, name)

    @classmethod
    def empty(cls, name: str = "") -> "Solid":
        return cls(m3d.Manifold(), name)

    # --- свойства ---------------------------------------------------------
    @property
    def volume(self) -> float:
        return float(self.manifold.volume()) if not self.manifold.is_empty() else 0.0

    @property
    def is_empty(self) -> bool:
        return self.manifold.is_empty()

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        b = self.manifold.bounding_box()
        return np.array(b[:3]), np.array(b[3:])

    def to_trimesh(self) -> trimesh.Trimesh:
        if self.is_empty:
            return trimesh.Trimesh()
        if hasattr(self.manifold, "to_mesh64"):
            mesh = self.manifold.to_mesh64()
        else:
            mesh = self.manifold.to_mesh()
        v = np.asarray(mesh.vert_properties)[:, :3]
        f = np.asarray(mesh.tri_verts)
        return trimesh.Trimesh(vertices=v, faces=f, process=False)

    def components(self) -> list["Solid"]:
        if self.is_empty:
            return []
        return [Solid(c, f"{self.name}#{i}") for i, c in enumerate(self.manifold.decompose())]

    # --- булевы операции --------------------------------------------------
    def __and__(self, other: "Solid") -> "Solid":  # пересечение
        return Solid(m3d.Manifold.batch_boolean([self.manifold, other.manifold], m3d.OpType.Intersect))

    def __sub__(self, other: "Solid") -> "Solid":  # разность
        return Solid(m3d.Manifold.batch_boolean([self.manifold, other.manifold], m3d.OpType.Subtract))

    def __or__(self, other: "Solid") -> "Solid":  # объединение
        return Solid(m3d.Manifold.batch_boolean([self.manifold, other.manifold], m3d.OpType.Add))

    def translate(self, v) -> "Solid":
        return Solid(self.manifold.translate(tuple(float(x) for x in v)), self.name)


def union_all(solids: list[Solid], name: str = "") -> Solid:
    solids = [s for s in solids if not s.is_empty]
    if not solids:
        return Solid.empty(name)
    if len(solids) == 1:
        return Solid(solids[0].manifold, name)
    return Solid(m3d.Manifold.batch_boolean([s.manifold for s in solids], m3d.OpType.Add), name)
