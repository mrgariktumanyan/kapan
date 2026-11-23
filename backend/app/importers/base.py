"""Общие структуры импорта."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import trimesh

from ..core.blockmodel import BlockModel


class ImportFailed(ValueError):
    """Файл не удалось прочитать. Сообщение показывается пользователю как есть."""


@dataclass
class ImportedData:
    file_format: str
    meshes: dict[str, trimesh.Trimesh] = field(default_factory=dict)   # слой -> сетка (без обработки)
    points: np.ndarray | None = None                                    # (n, 3)
    table: pd.DataFrame | None = None
    block_model: BlockModel | None = None
    notes: list[str] = field(default_factory=list)

    def merged_mesh(self) -> trimesh.Trimesh | None:
        if not self.meshes:
            return None
        parts = [m for m in self.meshes.values() if len(m.faces)]
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
