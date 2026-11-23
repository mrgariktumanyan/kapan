import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Analysis, type Stope, type StoredFile } from "../api";
import { useAuth } from "../auth";
import FilesTable from "../components/FilesTable";
import ImportCenter from "../components/ImportCenter";
import ResultsView from "../components/ResultsView";
import { ErrorBox, Section, StatusDot } from "../components/ui";

const PARAMS: [string, string, number][] = [
  ["density_ore", "ρ руды, т/м³", 2.8],
  ["density_low_grade", "ρ некондиции, т/м³", 2.75],
  ["density_waste", "ρ породы, т/м³", 2.7],
  ["zone_cell_size", "Шаг зонирования, м", 2.0],
  ["elevation_bin", "Шаг по высоте, м", 5.0],
];

export default function StopePage() {
  const { stopeId } = useParams();
  const id = Number(stopeId);
  const { user } = useAuth();
  const canRun = user?.role === "admin" || user?.role === "planner";
  const [stope, setStope] = useState<Stope | null>(null);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [jobs, setJobs] = useState<Analysis[]>([]);
  const [current, setCurrent] = useState<Analysis | null>(null);
  const [params, setParams] = useState<Record<string, number>>(Object.fromEntries(PARAMS.map(([k, , v]) => [k, v])));
  const [err, setErr] = useState<string | null>(null);
  const opened = useRef(false);

  const openJob = useCallback(async (jobId: number) => {
    setCurrent(await api.get<Analysis>(`/api/analyses/${jobId}`));
  }, []);

  const load = useCallback(async () => {
    try {
      const [s, f, j] = await Promise.all([
        api.get<Stope>(`/api/stopes/${id}`),
        api.get<StoredFile[]>(`/api/stopes/${id}/files`),
        api.get<Analysis[]>(`/api/stopes/${id}/analyses`),
      ]);
      setStope(s); setFiles(f); setJobs(j);
      const done = j.find((x) => x.status === "done");
      if (done && !opened.current) { opened.current = true; await openJob(done.id); }
    } catch (e) { setErr((e as Error).message); }
  }, [id, openJob]);
  useEffect(() => { load(); }, [load]);

  // Опрос выполняющегося анализа
  useEffect(() => {
    const active = jobs.find((j) => j.status === "queued" || j.status === "running");
    if (!active) return;
    const t = setTimeout(async () => {
      const j = await api.get<Analysis>(`/api/analyses/${active.id}`);
      setJobs((prev) => prev.map((x) => (x.id === j.id ? j : x)));
      if (j.status === "done") setCurrent(j);
    }, 1500);
    return () => clearTimeout(t);
  }, [jobs]);

  const start = async () => {
    setErr(null);
    try {
      const j = await api.post<Analysis>(`/api/stopes/${id}/analyses`, { params });
      setJobs((prev) => [j, ...prev]);
      if (j.status === "done") await openJob(j.id);
      if (j.status === "failed") setErr(j.message);
    } catch (e) { setErr((e as Error).message); }
  };

  return (
    <div className="space-y-4">
      <div>
        <Link to={stope ? "/projects" : "#"} className="text-xs text-graphite-400 hover:underline">← Проекты</Link>
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
          <h1 className="text-xl font-semibold text-white">STOPE: {stope?.name}</h1>
          <span className="text-sm text-graphite-400">Рудник: {stope?.mine_name}</span>
          <span className="text-sm text-graphite-400">Горизонт: {stope?.level_name}</span>
          <span className="text-sm text-graphite-400">Рудное тело: {stope?.orebody || "—"}</span>
          <span className="text-sm text-graphite-400">Статус: {stope?.status}</span>
        </div>
      </div>
      <ErrorBox error={err} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Section title="Импорт данных">
          <ImportCenter stopeId={id} onUploaded={() => load()} />
        </Section>
        <Section title="Исходные модели и проверка">
          <FilesTable files={files} />
        </Section>
      </div>

      <Section
        title="Анализ"
        right={canRun && <button className="btn btn-primary" onClick={start}>Запустить сверку</button>}
      >
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {PARAMS.map(([k, label]) => (
            <div key={k}>
              <label className="label">{label}</label>
              <input className="input font-mono" type="number" step="0.01" value={params[k]}
                onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })} disabled={!canRun} />
            </div>
          ))}
        </div>
        <div className="mt-2 text-xs text-graphite-400">Плотность используется, если не загружена блочная модель. При блочной модели тоннаж считается по блокам.</div>
        {jobs.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {jobs.map((j) => (
              <button key={j.id} onClick={() => j.status === "done" && openJob(j.id)}
                className={`flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs ${current?.id === j.id ? "border-teal-500 text-white" : "border-graphite-700 text-graphite-400"}`}
                title={j.message}>
                <StatusDot level={j.status === "done" ? "ok" : j.status === "failed" ? "error" : "warning"} />
                v{j.version} · {new Date(j.created_at).toLocaleString("ru-RU")}
                {(j.status === "queued" || j.status === "running") && ` · ${Math.round(j.progress * 100)}%`}
              </button>
            ))}
          </div>
        )}
      </Section>

      {current && <ResultsView job={current} />}
    </div>
  );
}
