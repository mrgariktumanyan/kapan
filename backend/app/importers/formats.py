"""Импортёры форматов (ТЗ п. 4.1).

Сетки читаются БЕЗ автоматического «исправления» (process=False), чтобы
проверка геометрии видела файл таким, какой он есть: дубли вершин, дыры,
перевёрнутые нормали. Исправления выполняются явно и фиксируются в отчёте.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import trimesh

from ..core.blockmodel import BlockModel
from .base import ImportedData, ImportFailed

MESH_FORMATS = {"stl", "obj", "ply"}
TABLE_FORMATS = {"csv", "txt", "xlsx", "xls"}
SUPPORTED_FORMATS = MESH_FORMATS | TABLE_FORMATS | {"dxf", "zip", "dm", "dwg", "las", "laz"}


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FORMATS:
        raise ImportFailed(
            f"Формат «.{ext}» не поддерживается. Допустимые: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )
    return ext


# ---------------------------------------------------------------------------
# STL / OBJ / PLY
# ---------------------------------------------------------------------------

def read_mesh_file(data: bytes, fmt: str) -> ImportedData:
    try:
        loaded = trimesh.load(io.BytesIO(data), file_type=fmt, process=False, force=None)
    except Exception as exc:  # noqa: BLE001 — показываем причину пользователю
        raise ImportFailed(f"Не удалось прочитать {fmt.upper()}: {exc}") from exc
    out = ImportedData(file_format=fmt)
    if isinstance(loaded, trimesh.Scene):
        for name, geom in loaded.geometry.items():
            if isinstance(geom, trimesh.Trimesh):
                out.meshes[str(name)] = geom
            elif isinstance(geom, trimesh.PointCloud):
                out.points = np.asarray(geom.vertices)
    elif isinstance(loaded, trimesh.Trimesh):
        out.meshes["mesh"] = loaded
    elif isinstance(loaded, trimesh.PointCloud):
        out.points = np.asarray(loaded.vertices)
    if not out.meshes and out.points is None:
        raise ImportFailed(f"{fmt.upper()}: в файле нет треугольников или точек")
    return out


# ---------------------------------------------------------------------------
# DXF: 3DFACE, POLYFACE MESH, POLYGON MESH, MESH, 3D-полилинии и точки
# ---------------------------------------------------------------------------

def read_dxf(data: bytes) -> ImportedData:
    import ezdxf
    from ezdxf import recover

    try:
        doc, auditor = recover.read(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ImportFailed(f"DXF повреждён или не читается: {exc}") from exc

    tris: dict[str, list] = {}
    points: list = []
    polylines = 0
    out = ImportedData(file_format="dxf")
    if auditor.has_errors:
        out.notes.append(f"DXF: исправлено ошибок структуры при чтении: {len(auditor.errors)}")

    def add_tri(layer, a, b, c):
        tris.setdefault(layer, []).append((tuple(a), tuple(b), tuple(c)))

    for e in doc.modelspace():
        layer = e.dxf.layer or "0"
        t = e.dxftype()
        if t == "3DFACE":
            v = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
            add_tri(layer, v[0], v[1], v[2])
            if not np.allclose(v[2], v[3]):
                add_tri(layer, v[0], v[2], v[3])
        elif t == "POLYLINE" and (e.is_poly_face_mesh or e.is_polygon_mesh):
            from ezdxf.render import MeshBuilder
            mb = MeshBuilder.from_polyface(e)
            for face in mb.faces:
                vs = [mb.vertices[i] for i in face]
                for k in range(1, len(vs) - 1):
                    add_tri(layer, vs[0], vs[k], vs[k + 1])
        elif t == "MESH":
            from ezdxf.render import MeshBuilder
            mb = MeshBuilder.from_mesh(e)
            for face in mb.faces:
                vs = [mb.vertices[i] for i in face]
                for k in range(1, len(vs) - 1):
                    add_tri(layer, vs[0], vs[k], vs[k + 1])
        elif t == "POINT":
            points.append(tuple(e.dxf.location))
        elif t in ("POLYLINE", "LWPOLYLINE", "LINE"):
            polylines += 1

    for layer, tl in tris.items():
        arr = np.asarray(tl, dtype=float)              # (n, 3, 3)
        verts = arr.reshape(-1, 3)
        faces = np.arange(len(verts)).reshape(-1, 3)
        out.meshes[layer] = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    if points:
        out.points = np.asarray(points, dtype=float)
    if polylines:
        out.notes.append(f"DXF: {polylines} контуров (полилиний) — будут использованы на Этапе 2 (разрезы)")
    if not out.meshes and out.points is None:
        raise ImportFailed(
            "DXF не содержит триангуляции (3DFACE / POLYFACE / MESH) или точек. "
            "Для солидов экспортируйте каркас как 3DFACE."
        )
    return out


# ---------------------------------------------------------------------------
# Табличные данные: CSV / TXT / XLSX
# ---------------------------------------------------------------------------

POINT_COLUMNS = [("X", "Y", "Z"), ("XP", "YP", "ZP"), ("EAST", "NORTH", "RL"), ("EASTING", "NORTHING", "ELEVATION")]
BLOCK_CENTER = ("XC", "YC", "ZC")
BLOCK_SIZE = ("XINC", "YINC", "ZINC")
DENSITY_COLUMNS = ("DENSITY", "DENS", "SG", "RHO")
GRADE_COLUMNS = ("AU", "AG", "CU", "ZN", "PB")


def _read_table(data: bytes, fmt: str) -> pd.DataFrame:
    try:
        if fmt in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(data))
        else:
            text = data.decode("utf-8-sig", errors="replace")
            first = next((ln for ln in text.splitlines() if ln.strip()), "")
            has_header = bool(re.search(r"[A-Za-zА-Яа-я]", first))
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python",
                             header=0 if has_header else None, comment="#")
            if not has_header:
                df.columns = [f"C{i + 1}" for i in range(df.shape[1])]
    except Exception as exc:  # noqa: BLE001
        raise ImportFailed(f"Не удалось прочитать таблицу {fmt.upper()}: {exc}") from exc
    df.columns = [str(c).strip().upper() for c in df.columns]
    if df.empty:
        raise ImportFailed("Таблица пустая")
    return df


def _block_model_from_df(df: pd.DataFrame, source: str) -> BlockModel:
    missing = [c for c in BLOCK_CENTER + BLOCK_SIZE if c not in df.columns]
    if missing:
        raise ImportFailed(f"Блочная модель: нет обязательных полей {', '.join(missing)}")
    dens_col = next((c for c in DENSITY_COLUMNS if c in df.columns), None)
    if dens_col is None:
        raise ImportFailed(f"Блочная модель: нет поля плотности ({' / '.join(DENSITY_COLUMNS)})")
    grades = {c: df[c].to_numpy(float) for c in GRADE_COLUMNS if c in df.columns}
    return BlockModel(df[list(BLOCK_CENTER)].to_numpy(float), df[list(BLOCK_SIZE)].to_numpy(float),
                      df[dens_col].to_numpy(float), grades, source)


def read_table(data: bytes, fmt: str, expect: str | None = None) -> ImportedData:
    """expect: 'block_model' | 'points' | 'production' | None (автоопределение)."""
    df = _read_table(data, fmt)
    out = ImportedData(file_format=fmt, table=df)
    cols = set(df.columns)
    is_bm = set(BLOCK_CENTER + BLOCK_SIZE) <= cols
    if expect == "block_model" or (expect is None and is_bm):
        out.block_model = _block_model_from_df(df, fmt)
        return out
    if expect in (None, "points"):
        for cx in POINT_COLUMNS:
            if set(cx) <= cols:
                out.points = df[list(cx)].to_numpy(float)
                return out
        if expect == "points":
            num = df.select_dtypes("number")
            if num.shape[1] >= 3:
                out.points = num.iloc[:, :3].to_numpy(float)
                out.notes.append(f"Координаты взяты из первых трёх числовых столбцов: {list(num.columns[:3])}")
                return out
            raise ImportFailed("Не найдены столбцы координат X, Y, Z")
    return out


# ---------------------------------------------------------------------------
# Datamine
# ---------------------------------------------------------------------------

def read_datamine_wireframe_zip(data: bytes) -> ImportedData:
    """Каркас Datamine, выгруженный в CSV: пара таблиц точек (*pt) и треугольников (*tr) в ZIP.

    Точки: PID, XP, YP, ZP.  Треугольники: PID1, PID2, PID3 (+ TRIANGLE, SURFACE — необязательно).
    Это стандартная структура wireframe-файлов Datamine Studio (xxxpt.dm / xxxtr.dm).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ImportFailed("ZIP-архив повреждён") from exc
    names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".txt"))]
    pt = next((n for n in names if re.search(r"pt\.(csv|txt)$", n.lower())), None)
    tr = next((n for n in names if re.search(r"tr\.(csv|txt)$", n.lower())), None)
    if not pt or not tr:
        raise ImportFailed(
            "ZIP должен содержать пару CSV каркаса Datamine: *pt.csv (PID, XP, YP, ZP) и *tr.csv (PID1, PID2, PID3)"
        )
    pts = _read_table(zf.read(pt), "csv")
    trs = _read_table(zf.read(tr), "csv")
    for need, df, nm in ((("PID", "XP", "YP", "ZP"), pts, pt), (("PID1", "PID2", "PID3"), trs, tr)):
        miss = [c for c in need if c not in df.columns]
        if miss:
            raise ImportFailed(f"{nm}: нет полей {', '.join(miss)}")
    pid = pts["PID"].to_numpy(int)
    index = {p: i for i, p in enumerate(pid)}
    try:
        faces = np.vectorize(index.__getitem__)(trs[["PID1", "PID2", "PID3"]].to_numpy(int))
    except KeyError as exc:
        raise ImportFailed(f"Треугольник ссылается на несуществующую точку PID={exc.args[0]}") from exc
    out = ImportedData(file_format="zip")
    out.meshes["wireframe"] = trimesh.Trimesh(pts[["XP", "YP", "ZP"]].to_numpy(float), faces, process=False)
    return out


def read_datamine_binary(_: bytes) -> ImportedData:
    # Бинарный .dm имеет собственную страничную структуру (заголовок, описание полей,
    # одинарная/расширенная точность). Читать его «обычной библиотекой» нельзя (ТЗ п. 4.1).
    # Прямой ридер будет написан и проверен на реальных файлах рудника; до этого —
    # согласованный промежуточный экспорт.
    raise ImportFailed(
        "Прямое чтение бинарных .dm пока не включено: ридер будет проверен на реальных файлах рудника. "
        "Экспортируйте из Datamine Studio: каркас — в DXF (3DFACE) или STL, либо таблицы *pt/*tr в CSV и "
        "загрузите их ZIP-архивом; блочную модель — в CSV (XC, YC, ZC, XINC, YINC, ZINC, DENSITY, AU…)."
    )


def import_file(data: bytes, filename: str, expect: str | None = None) -> ImportedData:
    fmt = detect_format(filename)
    if fmt in MESH_FORMATS:
        return read_mesh_file(data, fmt)
    if fmt == "dxf":
        return read_dxf(data)
    if fmt in TABLE_FORMATS:
        return read_table(data, fmt, expect)
    if fmt == "zip":
        return read_datamine_wireframe_zip(data)
    if fmt == "dm":
        return read_datamine_binary(data)
    if fmt == "dwg":
        raise ImportFailed("DWG — закрытый формат. Сохраните файл как DXF в AutoCAD (или ODA File Converter) и загрузите DXF.")
    if fmt in ("las", "laz"):
        raise ImportFailed("Облака точек LAS/LAZ будут подключены на Этапе 2 (обработчик laspy/Open3D).")
    raise ImportFailed(f"Формат {fmt} не поддерживается")
