"""Синтетические камеры с аналитически известными объёмами — для тестов и демонстрации.

Эталонная камера «SYN-01» (локальные размеры, м; сдвиг в UTM-подобные координаты):
    Проект  D = [0,20] × [0,10] × [0,30]               V = 6000
    Руда    O = [-5,25] × [1,9] × [-5,35]               (мощность 8 м, проект шире на 1 м с каждой стороны)
    Съёмка  S = [0,20] × [-1,10] × [3,30]               недобор 3 м по почве, перебор 1 м по южной стенке
Ожидаемые значения (рассчитаны вручную):
    V_plan_ore = 20·8·30 = 4800;  V_extracted = 20·8·27 = 4320;  V_loss = 480;  Ore loss = 10 %
    V_actual = 20·11·27 = 5940;   V_waste = 20·2·27 + 20·1·27 = 1620;  Dilution = 27.27 %
    Плановое разубоживание (в контуре проекта) = 20·2·27 = 1080;  внеплановое = 20·1·27 = 540
"""
from __future__ import annotations

import numpy as np
import trimesh

OFFSET = np.array([500_000.0, 4_300_000.0, 700.0])  # типичный порядок координат UTM


def box(lo, hi, offset=OFFSET) -> trimesh.Trimesh:
    lo, hi = np.asarray(lo, float) + offset, np.asarray(hi, float) + offset
    return trimesh.creation.box(extents=hi - lo).apply_translation((lo + hi) / 2)


def reference_stope(offset=OFFSET) -> dict[str, trimesh.Trimesh]:
    return {
        "design": box([0, 0, 0], [20, 10, 30], offset),
        "orebody": box([-5, 1, -5], [25, 9, 35], offset),
        "survey": box([0, -1, 3], [20, 10, 30], offset),
    }


REFERENCE_EXPECTED = {
    "V_plan_ore": 4800.0, "V_extracted_ore": 4320.0, "V_loss": 480.0, "ore_loss_pct": 10.0,
    "V_actual": 5940.0, "V_waste": 1620.0, "dilution_volume_pct": 1620 / 5940 * 100,
    "V_planned_waste": 1080.0, "V_unplanned_waste": 540.0,
    "V_overbreak": 540.0, "V_underbreak": 600.0,
}
