"""Расчётное ядро сверки: геометрические потери (Ore Loss) и разубоживание (Dilution).

Все формулы — ТЗ разделы 6, 7, 18. Расчёт полностью детерминирован: одинаковые
входные сетки и параметры дают одинаковый результат. Каждый показатель в
результате сопровождается формулой (см. FORMULAS) и проверками баланса объёмов.

Обозначения:
    D — проектный солид камеры (Design)
    O — солид кондиционной руды (Orebody)
    L — солид некондиционной руды (Low grade), необязателен; L := L − O
    S — солид фактической выемки по маркшейдерской съёмке (Survey)
    BM — блочная модель (плотность, содержания), необязательна
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import trimesh

from . import ENGINE_VERSION
from .blockmodel import BlockModel, tonnage_by_blocks
from .geometry import Solid

FORMULAS: dict[str, str] = {
    "V_plan_ore": "Volume(D ∩ O)",
    "V_extracted_ore": "Volume(D ∩ O ∩ S)",
    "V_loss": "V_plan_ore − V_extracted_ore  (проверка: Volume((D ∩ O) − S))",
    "ore_loss_pct": "V_loss / V_plan_ore × 100",
    "T_loss": "Σ Volume(Loss ∩ Block_i) × ρ_i  (без блочной модели: V_loss × ρ_ore)",
    "M_loss": "Σ T_i × G_i / 1000 [г/т → кг];  Σ T_i × G_i / 100 [% → т]",
    "V_actual": "Volume(S)",
    "V_ore_in_survey": "Volume(S ∩ O)",
    "V_low_grade": "Volume(S ∩ L)",
    "V_waste": "Volume(S − O − L) в пределах геологической модели",
    "V_undefined": "Volume(S − O − L) вне области блочной модели",
    "dilution_volume_pct": "V_waste / V_actual × 100",
    "dilution_tonnage_pct": "T_waste / (T_ore + T_waste) × 100",
    "planned_dilution_design_pct": "Volume(D − O − L) / Volume(D) × 100",
    "planned_dilution_pct": "Volume((S ∩ D) − O − L) / V_actual × 100",
    "unplanned_dilution_pct": "Volume((S − D) − O − L) / V_actual × 100",
    "total_dilution_pct": "planned_dilution_pct + unplanned_dilution_pct",
    "V_overbreak": "Volume(S − D)",
    "V_underbreak": "Volume(D − S)",
    "V_conformance": "Volume(S ∩ D)",
    "G_actual": "Σ(T_i × G_i) / Σ T_i по блокам фактической выемки",
}


@dataclass
class ReconciliationParams:
    density_ore: float = 2.8            # т/м³, если нет блочной модели
    density_low_grade: float = 2.75
    density_waste: float = 2.7
    zone_cell_size: float = 2.0         # м, шаг сетки для разбивки по зонам
    zone_max_cells: int = 6000          # ограничение числа ячеек (шаг увеличивается автоматически)
    roof_floor_angle_deg: float = 45.0  # нормаль круче этого угла к горизонту — кровля/почва
    elevation_bin: float = 5.0          # м, шаг профиля по высоте
    balance_tolerance_pct: float = 0.01 # допуск невязки баланса объёмов, %

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ReconciliationInput:
    design: trimesh.Trimesh
    orebody: trimesh.Trimesh
    survey: trimesh.Trimesh
    low_grade: trimesh.Trimesh | None = None
    block_model: BlockModel | None = None
    params: ReconciliationParams = field(default_factory=ReconciliationParams)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _pct(a: float, b: float) -> float | None:
    return a / b * 100.0 if b > 0 else None


def _split_axis(solid: Solid, axis: int, edges: np.ndarray) -> list[tuple[int, Solid]]:
    """Точное разрезание солида плоскостями, перпендикулярными оси, по заданным отметкам."""
    out: list[tuple[int, Solid]] = []
    rest = solid.manifold
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    for k in range(1, len(edges) - 1):
        if rest.is_empty():
            break
        above, below = rest.split_by_plane(tuple(normal), float(edges[k]))
        if not below.is_empty():
            out.append((k - 1, Solid(below)))
        rest = above
    if not rest.is_empty():
        out.append((len(edges) - 2, Solid(rest)))
    return out


def _grid_pieces(solid: Solid, cell: float, max_cells: int) -> list[Solid]:
    """Разбивает солид на куски по регулярной 3D-сетке (точные плоские сечения)."""
    if solid.is_empty:
        return []
    lo, hi = solid.bounds
    ext = np.maximum(hi - lo, 1e-9)
    n_cells = np.prod(np.ceil(ext / cell))
    if n_cells > max_cells:
        cell = float((np.prod(ext) / max_cells) ** (1 / 3))
    edges = [np.append(np.arange(lo[a], hi[a], cell), hi[a] + 1e-6) for a in range(3)]
    pieces: list[Solid] = []
    for _, sx in _split_axis(solid, 0, edges[0]):
        for _, sy in _split_axis(sx, 1, edges[1]):
            for _, sz in _split_axis(sy, 2, edges[2]):
                if sz.volume > 0:
                    pieces.append(sz)
    return pieces


def _zone_of_normal(n: np.ndarray, roof_floor_angle_deg: float) -> str:
    sin_lim = math.sin(math.radians(roof_floor_angle_deg))
    if n[2] >= sin_lim:
        return "roof"
    if n[2] <= -sin_lim:
        return "floor"
    az = (math.degrees(math.atan2(n[0], n[1])) + 360.0) % 360.0  # азимут от севера (+Y) по часовой
    if az < 45 or az >= 315:
        return "wall_N"
    if az < 135:
        return "wall_E"
    if az < 225:
        return "wall_S"
    return "wall_W"


ZONE_LABELS = {
    "roof": "Кровля",
    "floor": "Почва",
    "wall_N": "Стенка С",
    "wall_E": "Стенка В",
    "wall_S": "Стенка Ю",
    "wall_W": "Стенка З",
}


def _zones(solid: Solid, ref_mesh: trimesh.Trimesh, p: ReconciliationParams) -> dict[str, float]:
    """Объём солида по зонам камеры (кровля, почва, стенки).

    Солид режется на ячейки сетки; каждая ячейка относится к зоне по внешней
    нормали ближайшей грани опорной поверхности — того солида, за пределами
    которого лежит анализируемый объём:
        потери и недобор  (… − S)  → контур съёмки S;
        перебор           (S − D)  → проектный контур D;
        пустая порода     (S − O)  → контур рудного тела O.
    Сумма объёмов зон равна объёму солида.
    """
    res = {k: 0.0 for k in ZONE_LABELS}
    pieces = _grid_pieces(solid, p.zone_cell_size, p.zone_max_cells)
    if not pieces:
        return res
    centroids = np.array([pc.to_trimesh().center_mass for pc in pieces])
    _, _, tri = trimesh.proximity.closest_point(ref_mesh, centroids)
    normals = ref_mesh.face_normals[tri]
    for pc, n in zip(pieces, normals):
        res[_zone_of_normal(n, p.roof_floor_angle_deg)] += pc.volume
    return res


def _elevation_profile(solid: Solid, z0: float, z1: float, step: float, origin_z: float) -> list[dict]:
    """Объём солида по горизонтальным слоям (отметки в исходной системе координат)."""
    if solid.is_empty or step <= 0:
        return []
    start = math.floor((z0 + origin_z) / step) * step - origin_z
    edges = np.arange(start, z1 + step, step)
    if len(edges) < 2:
        edges = np.array([z0, z1])
    vols = np.zeros(len(edges) - 1)
    for k, piece in _split_axis(solid, 2, np.concatenate([[edges[0] - 1], edges[1:-1], [edges[-1] + 1]])):
        vols[k] += piece.volume
    return [
        {"z_from": float(edges[i] + origin_z), "z_to": float(edges[i + 1] + origin_z), "volume_m3": float(v)}
        for i, v in enumerate(vols) if v > 0
    ]


def _components(solid: Solid, origin: np.ndarray, ref_mesh: trimesh.Trimesh,
                p: ReconciliationParams, min_volume: float = 0.01) -> list[dict]:
    """Отдельные связные участки (для ссылок на пространственные зоны и AI-анализа)."""
    out = []
    for i, c in enumerate(sorted(solid.components(), key=lambda s: -s.volume)):
        if c.volume < min_volume:
            continue
        tm = c.to_trimesh()
        cm = tm.center_mass
        _, _, tri = trimesh.proximity.closest_point(ref_mesh, [cm])
        lo, hi = c.bounds
        out.append({
            "id": i + 1,
            "volume_m3": c.volume,
            "centroid": (cm + origin).tolist(),
            "bbox_min": (lo + origin).tolist(),
            "bbox_max": (hi + origin).tolist(),
            "dominant_zone": _zone_of_normal(ref_mesh.face_normals[tri[0]], p.roof_floor_angle_deg),
        })
    return out


def _tonnage(solid: Solid, bm: BlockModel | None, density: float) -> dict:
    if bm is not None:
        return tonnage_by_blocks(solid, bm).as_dict()
    v = solid.volume
    return {"volume_m3": v, "tonnes": v * density, "metal": {}, "grade": {},
            "covered_volume_m3": None, "uncovered_volume_m3": None, "n_blocks": 0,
            "density_source": f"constant {density} t/m3"}


# ---------------------------------------------------------------------------
# Основной расчёт
# ---------------------------------------------------------------------------

def run_reconciliation(inp: ReconciliationInput) -> dict:
    p = inp.params
    warnings: list[str] = []

    # Перенос в локальное начало координат: булевы операции на UTM-координатах
    # (~10^6 м) теряют значащие цифры. Объёмы от переноса не зависят.
    origin = np.floor(inp.design.bounds[0])
    def local(m: trimesh.Trimesh | None) -> trimesh.Trimesh | None:
        if m is None:
            return None
        c = m.copy()
        c.apply_translation(-origin)
        return c

    design_m, ore_m, survey_m, lg_m = map(local, (inp.design, inp.orebody, inp.survey, inp.low_grade))
    bm = inp.block_model.translate(-origin) if inp.block_model is not None else None

    D = Solid.from_trimesh(design_m, "design")
    O = Solid.from_trimesh(ore_m, "orebody")
    S = Solid.from_trimesh(survey_m, "survey")
    L = (Solid.from_trimesh(lg_m, "low_grade") - O) if lg_m is not None else Solid.empty("low_grade")
    OL = O | L  # всё, что не пустая порода

    # ---------------- Ore Loss ----------------
    P = D & O                       # плановая руда
    E = P & S                       # извлечённая плановая руда
    LOSS = P - S                    # геометрические потери (недоотработка руды)
    V_plan_ore, V_extr, V_loss_direct = P.volume, E.volume, LOSS.volume
    V_loss = V_plan_ore - V_extr
    unplanned_ore = (S & O) - D     # руда, добытая за проектным контуром

    loss_balance = abs(V_loss - V_loss_direct)
    if V_plan_ore > 0 and loss_balance / V_plan_ore * 100 > p.balance_tolerance_pct:
        warnings.append(f"Невязка баланса потерь {loss_balance:.3f} м³ превышает допуск")
    if V_plan_ore == 0:
        warnings.append("Проектный контур не пересекает рудное тело: V_plan_ore = 0")

    plan_ore_t = _tonnage(P, bm, p.density_ore)
    extracted_t = _tonnage(E, bm, p.density_ore)
    loss_t = _tonnage(LOSS, bm, p.density_ore)

    # ---------------- Dilution ----------------
    V_actual = S.volume
    S_ore = S & O
    S_lg = S & L
    S_nonore = S - OL
    if bm is not None:
        cover = bm.coverage()
        S_waste = S_nonore & cover
        S_undef = S_nonore - cover
    else:
        S_waste, S_undef = S_nonore, Solid.empty()
    V_ore_s, V_lg_s, V_waste, V_undef = S_ore.volume, S_lg.volume, S_waste.volume, S_undef.volume

    survey_balance = abs(V_actual - (V_ore_s + V_lg_s + V_waste + V_undef))
    if V_actual > 0 and survey_balance / V_actual * 100 > p.balance_tolerance_pct:
        warnings.append(f"Невязка баланса фактической выемки {survey_balance:.3f} м³ превышает допуск")
    if V_undef > 0:
        warnings.append(f"{V_undef:.1f} м³ фактической выемки вне блочной модели — категория «не определено»")

    SD = S & D
    planned_waste = (SD - OL)
    unplanned_waste = (S - D) - OL
    planned_lg = SD & L
    unplanned_lg = (S - D) & L
    design_waste = D - OL

    ore_t = _tonnage(S_ore, bm, p.density_ore)
    lg_t = _tonnage(S_lg, bm, p.density_low_grade)
    waste_t = _tonnage(S_waste, bm, p.density_waste)
    T_ore, T_waste, T_lg = ore_t["tonnes"], waste_t["tonnes"], lg_t["tonnes"]
    actual_t = _tonnage(S, bm, p.density_ore) if bm is not None else None

    OVER, UNDER = S - D, D - S

    # ---------------- Зоны и профиль ----------------
    z_lo, z_hi = min(D.bounds[0][2], S.bounds[0][2]), max(D.bounds[1][2], S.bounds[1][2])
    ref_s, ref_d, ref_o = S.to_trimesh(), D.to_trimesh(), OL.to_trimesh()
    loss_zones = _zones(LOSS, ref_s, p)
    waste_zones = _zones(S_waste | S_undef, ref_o, p)
    over_zones = _zones(OVER, ref_d, p)
    under_zones = _zones(UNDER, ref_s, p)

    result = {
        "engine_version": ENGINE_VERSION,
        "params": p.as_dict(),
        "local_origin": origin.tolist(),
        "formulas": FORMULAS,
        "ore_loss": {
            "V_plan_ore": V_plan_ore,
            "V_extracted_ore": V_extr,
            "V_loss": V_loss,
            "V_loss_direct": V_loss_direct,
            "ore_loss_pct": _pct(V_loss, V_plan_ore),
            "T_plan_ore": plan_ore_t["tonnes"],
            "T_extracted_ore": extracted_t["tonnes"],
            "T_loss": loss_t["tonnes"],
            "ore_loss_tonnage_pct": _pct(loss_t["tonnes"], plan_ore_t["tonnes"]),
            "metal_loss": loss_t["metal"],
            "grade_loss": loss_t["grade"],
            "metal_plan": plan_ore_t["metal"],
            "V_unplanned_ore_extracted": unplanned_ore.volume,
            "by_zone": loss_zones,
            "by_elevation": _elevation_profile(LOSS, z_lo, z_hi, p.elevation_bin, origin[2]),
            "areas": _components(LOSS, origin, ref_s, p),
        },
        "dilution": {
            "V_actual": V_actual,
            "V_ore": V_ore_s,
            "V_low_grade": V_lg_s,
            "V_waste": V_waste,
            "V_undefined": V_undef,
            "dilution_volume_pct": _pct(V_waste, V_actual),
            "low_grade_volume_pct": _pct(V_lg_s, V_actual),
            "T_ore": T_ore,
            "T_low_grade": T_lg,
            "T_waste": T_waste,
            "dilution_tonnage_pct": _pct(T_waste, T_ore + T_waste),
            "planned_dilution_design_pct": _pct(design_waste.volume, D.volume),
            "V_planned_waste": planned_waste.volume,
            "V_unplanned_waste": unplanned_waste.volume,
            "V_planned_low_grade": planned_lg.volume,
            "V_unplanned_low_grade": unplanned_lg.volume,
            "planned_dilution_pct": _pct(planned_waste.volume, V_actual),
            "unplanned_dilution_pct": _pct(unplanned_waste.volume, V_actual),
            "total_dilution_pct": _pct(planned_waste.volume + unplanned_waste.volume, V_actual),
            "grade_actual": actual_t["grade"] if actual_t else {},
            "grade_status": "model_estimate",  # фактическое содержание — только из производственных данных
            "by_zone": waste_zones,
            "by_elevation": _elevation_profile(S_waste | S_undef, z_lo, z_hi, p.elevation_bin, origin[2]),
            "areas": _components(S_waste | S_undef, origin, ref_o, p),
        },
        "conformance": {
            "V_design": D.volume,
            "V_survey": V_actual,
            "V_conformance": SD.volume,
            "V_overbreak": OVER.volume,
            "V_underbreak": UNDER.volume,
            "overbreak_pct": _pct(OVER.volume, D.volume),
            "underbreak_pct": _pct(UNDER.volume, D.volume),
            "conformance_pct": _pct(SD.volume, D.volume),
            "overbreak_by_zone": over_zones,
            "underbreak_by_zone": under_zones,
        },
        "checks": {
            "loss_balance_m3": loss_balance,
            "survey_balance_m3": survey_balance,
        },
        "warnings": warnings,
    }
    return result
