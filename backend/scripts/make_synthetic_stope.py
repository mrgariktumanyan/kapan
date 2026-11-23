"""Создаёт файлы эталонной синтетической камеры SYN-01 (STL + DXF) для ручной проверки через интерфейс.

python scripts/make_synthetic_stope.py out_dir
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402

from app.core.synthetic import reference_stope  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "synthetic_SYN-01")
out.mkdir(parents=True, exist_ok=True)
for name, mesh in reference_stope().items():
    mesh.export(out / f"SYN-01_{name}.stl")
    doc = ezdxf.new()
    msp = doc.modelspace()
    for f in mesh.faces:
        a, b, c = (tuple(mesh.vertices[i]) for i in f)
        msp.add_3dface([a, b, c, c], dxfattribs={"layer": name.upper()})
    doc.saveas(out / f"SYN-01_{name}.dxf")
print(f"Файлы записаны в {out.resolve()}")
