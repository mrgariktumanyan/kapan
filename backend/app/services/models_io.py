"""Хранение исходных файлов, импорт и проверка моделей камеры."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from ..config import settings
from ..core.blockmodel import BlockModel
from ..importers.base import ImportFailed
from ..importers.formats import import_file
from ..models import ModelRole, UploadedFile
from ..validation.checks import Report, validate_block_model, validate_points, validate_solid

SOLID_ROLES = {ModelRole.orebody, ModelRole.low_grade, ModelRole.stope_design, ModelRole.survey_solid}
# Форматы, где каждая грань хранит свои вершины (дубли вершин — норма)
PER_FACE_VERTEX_FORMATS = {"stl", "dxf"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_file(stope_id: int, data: bytes, filename: str) -> tuple[Path, str]:
    digest = sha256_bytes(data)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)[-120:]
    d = settings.storage_dir / f"stope_{stope_id}"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{digest[:16]}_{safe}"
    if not path.exists():
        path.write_bytes(data)
    return path, digest


@dataclass
class LoadedModel:
    role: ModelRole
    report: Report
    summary: dict
    mesh: trimesh.Trimesh | None = None
    block_model: BlockModel | None = None
    points: np.ndarray | None = None
    table: object | None = None

    @property
    def usable(self) -> bool:
        return self.report.status != "error"


def load_and_validate(data: bytes, filename: str, role: ModelRole) -> LoadedModel:
    rep = Report()
    expect = {"block_model": "block_model", "survey_points": "points", "production": "production"}.get(role.value)
    try:
        imp = import_file(data, filename, expect)
    except ImportFailed as exc:
        rep.add("format", "error", str(exc))
        return LoadedModel(role, rep, {})
    rep.add("format", "ok", f"Формат {imp.file_format.upper()} прочитан")
    for note in imp.notes:
        rep.add("import_note", "ok", note)

    if role in SOLID_ROLES:
        mesh = imp.merged_mesh()
        if mesh is None:
            rep.add("solid", "error", "Для этой роли нужен замкнутый 3D-солид, а файл не содержит треугольников")
            return LoadedModel(role, rep, {})
        if len(imp.meshes) > 1:
            rep.add("layers", "ok", f"Объединены слои: {', '.join(imp.meshes)}")
        r, prepared, summary = validate_solid(mesh, indexed_format=imp.file_format not in PER_FACE_VERTEX_FORMATS)
        rep.checks.extend(r.checks)
        return LoadedModel(role, rep, summary, mesh=prepared)

    if role == ModelRole.block_model:
        if imp.block_model is None:
            rep.add("block_model", "error", "Файл не распознан как блочная модель (нужны XC, YC, ZC, XINC, YINC, ZINC, DENSITY)")
            return LoadedModel(role, rep, {})
        r, summary = validate_block_model(imp.block_model)
        rep.checks.extend(r.checks)
        return LoadedModel(role, rep, summary, block_model=imp.block_model)

    if role == ModelRole.survey_points:
        if imp.points is None:
            rep.add("points", "error", "В файле не найдены точки XYZ")
            return LoadedModel(role, rep, {})
        r, summary = validate_points(imp.points)
        rep.checks.extend(r.checks)
        return LoadedModel(role, rep, summary, points=imp.points)

    if role == ModelRole.production:
        if imp.table is None:
            rep.add("table", "error", "Производственные данные должны быть таблицей CSV/XLSX")
            return LoadedModel(role, rep, {})
        cols = set(imp.table.columns)
        tcol = next((c for c in ("TONNES", "TONNAGE", "TONS", "T") if c in cols), None)
        if tcol is None:
            rep.add("required_fields", "error", "Нет обязательного поля тоннажа (TONNES)")
        else:
            rep.add("required_fields", "ok", f"Поле тоннажа: {tcol}")
        return LoadedModel(role, rep, {"rows": int(len(imp.table)), "columns": sorted(cols)}, table=imp.table)

    # other: только проверка формата
    return LoadedModel(role, rep, {})


def load_stored(rec: UploadedFile) -> LoadedModel:
    """Повторно читает сохранённый файл с проверкой целостности (sha256) — для воспроизводимости."""
    data = Path(rec.storage_path).read_bytes()
    if sha256_bytes(data) != rec.sha256:
        rep = Report()
        rep.add("integrity", "error", f"Файл {rec.original_name} изменён после загрузки (sha256 не совпадает)")
        return LoadedModel(rec.model_role, rep, {})
    return load_and_validate(data, rec.original_name, rec.model_role)
