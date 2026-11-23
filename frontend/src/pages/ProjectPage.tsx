import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Level, type Mine, type Project, type Stope } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Section } from "../components/ui";
import { fmt } from "../format";

export default function ProjectPage() {
  const { projectId } = useParams();
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "planner";
  const [project, setProject] = useState<Project | null>(null);
  const [mines, setMines] = useState<Mine[]>([]);
  const [levels, setLevels] = useState<Record<number, Level[]>>({});
  const [stopes, setStopes] = useState<Stope[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const [mineName, setMineName] = useState("");
  const [levelMine, setLevelMine] = useState<number | "">("");
  const [levelName, setLevelName] = useState("");
  const [stopeLevel, setStopeLevel] = useState<number | "">("");
  const [stopeName, setStopeName] = useState("");
  const [stopeOre, setStopeOre] = useState("");

  const load = useCallback(async () => {
    try {
      const [p, ms, ss] = await Promise.all([
        api.get<Project>(`/api/projects/${projectId}`),
        api.get<Mine[]>(`/api/projects/${projectId}/mines`),
        api.get<Stope[]>(`/api/projects/${projectId}/stopes`),
      ]);
      setProject(p); setMines(ms); setStopes(ss);
      const lv: Record<number, Level[]> = {};
      await Promise.all(ms.map(async (m) => { lv[m.id] = await api.get<Level[]>(`/api/mines/${m.id}/levels`); }));
      setLevels(lv);
    } catch (e) { setErr((e as Error).message); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const run = (fn: () => Promise<unknown>) => async (e: FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await fn(); await load(); } catch (ex) { setErr((ex as Error).message); }
  };
  const allLevels = mines.flatMap((m) => (levels[m.id] ?? []).map((l) => ({ ...l, mineName: m.name })));

  return (
    <div className="space-y-4">
      <div>
        <Link to="/projects" className="text-xs text-graphite-400 hover:underline">← Проекты</Link>
        <h1 className="text-xl font-semibold text-white">{project?.name}</h1>
        <div className="text-xs text-graphite-400">Система координат: {project?.crs} · единицы: {project?.units}</div>
      </div>
      <ErrorBox error={err} />

      <Section title="Очистные камеры">
        {stopes.length === 0 ? <div className="text-sm text-graphite-400">Камер пока нет.</div> : (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Камера</th><th>Рудник</th><th>Горизонт</th><th>Рудное тело</th><th>Статус</th><th className="num">Анализ</th><th className="num">Ore Loss, %</th><th className="num">Dilution, %</th></tr></thead>
              <tbody>
                {stopes.map((s) => (
                  <tr key={s.id}>
                    <td><Link className="text-teal-400 hover:underline" to={`/stopes/${s.id}`}>{s.name}</Link></td>
                    <td>{s.mine_name}</td><td>{s.level_name}</td><td>{s.orebody}</td><td>{s.status}</td>
                    <td className="num">{s.last_analysis ? `v${s.last_analysis.version}` : "—"}</td>
                    <td className="num">{fmt(s.last_analysis?.ore_loss_pct)}</td>
                    <td className="num">{fmt(s.last_analysis?.dilution_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {canEdit && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Section title="Рудник / участок">
            <form className="space-y-2" onSubmit={run(() => api.post(`/api/projects/${projectId}/mines`, { name: mineName }).then(() => setMineName("")))}>
              <input className="input" placeholder="Название" value={mineName} onChange={(e) => setMineName(e.target.value)} />
              <button className="btn btn-primary" disabled={!mineName}>Добавить</button>
            </form>
          </Section>
          <Section title="Горизонт">
            <form className="space-y-2" onSubmit={run(() => api.post(`/api/mines/${levelMine}/levels`, { name: levelName, elevation: Number(levelName) || null }).then(() => setLevelName("")))}>
              <select className="input" value={levelMine} onChange={(e) => setLevelMine(Number(e.target.value) || "")}>
                <option value="">Рудник…</option>
                {mines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
              <input className="input" placeholder="Горизонт, напр. 710" value={levelName} onChange={(e) => setLevelName(e.target.value)} />
              <button className="btn btn-primary" disabled={!levelMine || !levelName}>Добавить</button>
            </form>
          </Section>
          <Section title="Камера">
            <form className="space-y-2" onSubmit={run(() => api.post(`/api/levels/${stopeLevel}/stopes`, { name: stopeName, orebody: stopeOre }).then(() => setStopeName("")))}>
              <select className="input" value={stopeLevel} onChange={(e) => setStopeLevel(Number(e.target.value) || "")}>
                <option value="">Горизонт…</option>
                {allLevels.map((l) => <option key={l.id} value={l.id}>{l.mineName} / {l.name}</option>)}
              </select>
              <input className="input" placeholder="Камера, напр. 710-SH-025" value={stopeName} onChange={(e) => setStopeName(e.target.value)} />
              <input className="input" placeholder="Рудное тело" value={stopeOre} onChange={(e) => setStopeOre(e.target.value)} />
              <button className="btn btn-primary" disabled={!stopeLevel || !stopeName}>Добавить</button>
            </form>
          </Section>
        </div>
      )}
    </div>
  );
}
