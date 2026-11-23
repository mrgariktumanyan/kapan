import { useRef, useState, type DragEvent } from "react";
import { api, type StoredFile } from "../api";
import { CATEGORY_LABELS, ROLE_LABELS } from "../format";
import { ErrorBox } from "./ui";

const ROLES: Record<string, string[]> = {
  geological: ["orebody", "low_grade", "block_model", "other"],
  design: ["stope_design", "other"],
  survey: ["survey_solid", "survey_points", "other"],
  production: ["production"],
};
const ACCEPT = ".stl,.obj,.ply,.dxf,.dwg,.csv,.txt,.xlsx,.xls,.zip,.dm,.las,.laz";

export default function ImportCenter({ stopeId, onUploaded }: { stopeId: number; onUploaded: (f: StoredFile) => void }) {
  const [category, setCategory] = useState("design");
  const [role, setRole] = useState("stope_design");
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setErr(null);
    for (const f of Array.from(files)) {
      setBusy(f.name);
      const fd = new FormData();
      fd.append("category", category);
      fd.append("model_role", role);
      fd.append("file", f);
      try { onUploaded(await api.post<StoredFile>(`/api/stopes/${stopeId}/files`, fd)); }
      catch (e) { setErr(`${f.name}: ${(e as Error).message}`); }
    }
    setBusy(null);
  };

  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label">Категория</label>
          <select className="input" value={category} onChange={(e) => { setCategory(e.target.value); setRole(ROLES[e.target.value][0]); }}>
            {Object.keys(ROLES).map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Назначение файла</label>
          <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES[category].map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </div>
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center text-sm transition ${
          drag ? "border-teal-500 bg-teal-950/30" : "border-graphite-700 hover:border-graphite-600"}`}
      >
        <div className="text-graphite-200">{busy ? `Загрузка и проверка: ${busy}…` : "Перетащите файлы сюда или нажмите для выбора"}</div>
        <div className="mt-1 text-xs text-graphite-400">STL, OBJ, PLY, DXF (3DFACE), CSV/TXT, XLSX, ZIP (каркас Datamine *pt/*tr)</div>
        <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { upload(e.target.files); e.target.value = ""; }} />
      </div>
      <ErrorBox error={err} />
    </div>
  );
}
