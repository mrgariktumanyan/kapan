"""Блочная модель: плотность и содержания по блокам.

Тоннаж и металл любого солида считаются как сумма по блокам:
    V_i = Volume(Solid ∩ Block_i)          — точное булево пересечение
    T_i = V_i × ρ_i
    M_i = T_i × G_i / k                     — k = 1000 для г/т → кг, 100 для % → т
Средней плотностью по всей камере расчёт не подменяется (ТЗ п. 6.2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import Solid

# Единицы содержания и результата по элементам (ТЗ п. 6.3).
# divisor: на что делить T×G, чтобы получить металл в result_unit.
ELEMENT_UNITS: dict[str, dict] = {
    "AU": {"grade_unit": "g/t", "metal_unit": "kg", "divisor": 1000.0},
    "AG": {"grade_unit": "g/t", "metal_unit": "kg", "divisor": 1000.0},
    "CU": {"grade_unit": "%", "metal_unit": "t", "divisor": 100.0},
    "ZN": {"grade_unit": "%", "metal_unit": "t", "divisor": 100.0},
    "PB": {"grade_unit": "%", "metal_unit": "t", "divisor": 100.0},
}


@dataclass
class BlockModel:
    """Регулярная или субблочная модель с центрами блоков и размерами (Datamine: XC,YC,ZC,XINC,YINC,ZINC)."""

    centers: np.ndarray            # (n, 3)
    sizes: np.ndarray              # (n, 3)
    density: np.ndarray            # (n,) т/м³
    grades: dict[str, np.ndarray] = field(default_factory=dict)  # элемент -> (n,)
    source: str = ""

    def __post_init__(self):
        self.centers = np.asarray(self.centers, dtype=float).reshape(-1, 3)
        self.sizes = np.asarray(self.sizes, dtype=float).reshape(-1, 3)
        self.density = np.asarray(self.density, dtype=float).reshape(-1)
        n = len(self.centers)
        if len(self.sizes) != n or len(self.density) != n:
            raise ValueError("Блочная модель: разная длина массивов координат, размеров и плотности")
        for k, g in list(self.grades.items()):
            g = np.asarray(g, dtype=float).reshape(-1)
            if len(g) != n:
                raise ValueError(f"Блочная модель: поле {k} имеет неверную длину")
            self.grades[k.upper()] = g

    @property
    def lo(self) -> np.ndarray:
        return self.centers - self.sizes / 2

    @property
    def hi(self) -> np.ndarray:
        return self.centers + self.sizes / 2

    def translate(self, v) -> "BlockModel":
        return BlockModel(self.centers + np.asarray(v, float), self.sizes, self.density,
                          dict(self.grades), self.source)

    def coverage(self) -> Solid:
        """Объединение всех блоков — область, где геологическая модель определена."""
        from .geometry import union_all
        return union_all([Solid.box(l, h) for l, h in zip(self.lo, self.hi)], "block_model_extent")


@dataclass
class TonnageResult:
    volume_m3: float
    tonnes: float
    metal: dict[str, float]          # элемент -> количество металла (кг или т)
    grade: dict[str, float]          # элемент -> средневзвешенное по тоннажу содержание
    covered_volume_m3: float         # объём, попавший в блоки модели
    n_blocks: int

    def as_dict(self) -> dict:
        return {
            "volume_m3": self.volume_m3,
            "tonnes": self.tonnes,
            "metal": self.metal,
            "grade": self.grade,
            "covered_volume_m3": self.covered_volume_m3,
            "uncovered_volume_m3": max(self.volume_m3 - self.covered_volume_m3, 0.0),
            "n_blocks": self.n_blocks,
        }


def tonnage_by_blocks(solid: Solid, bm: BlockModel) -> TonnageResult:
    """Тоннаж/металл солида по блокам: Σ Volume(solid ∩ block_i) × ρ_i."""
    total_v = solid.volume
    elements = list(bm.grades)
    if solid.is_empty or len(bm.centers) == 0:
        return TonnageResult(total_v, 0.0, {e: 0.0 for e in elements}, {e: 0.0 for e in elements}, 0.0, 0)

    s_lo, s_hi = solid.bounds
    cand = np.where(np.all(bm.hi > s_lo, axis=1) & np.all(bm.lo < s_hi, axis=1))[0]
    vols = np.zeros(len(cand))
    for j, i in enumerate(cand):
        vols[j] = (solid & Solid.box(bm.lo[i], bm.hi[i])).volume
    mask = vols > 0
    idx, vols = cand[mask], vols[mask]
    t_i = vols * bm.density[idx]
    tonnes = float(t_i.sum())
    metal, grade = {}, {}
    for e in elements:
        g = bm.grades[e][idx]
        div = ELEMENT_UNITS.get(e, {"divisor": 1000.0})["divisor"]
        metal[e] = float((t_i * g).sum() / div)
        grade[e] = float((t_i * g).sum() / tonnes) if tonnes > 0 else 0.0
    return TonnageResult(total_v, tonnes, metal, grade, float(vols.sum()), int(len(idx)))
