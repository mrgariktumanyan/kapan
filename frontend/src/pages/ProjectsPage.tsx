import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Section } from "../components/ui";

export default function ProjectsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [crs, setCrs] = useState("Kapan local grid");
  const [err, setErr] = useState<string | null>(null);
  const canEdit = user?.role === "admin" || user?.role === "planner";

  const load = () => api.get<Project[]>("/api/projects").then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await api.post("/api/projects", { name, crs }); setName(""); load(); }
    catch (ex) { setErr((ex as Error).message); }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-white">Проекты</h1>
      <ErrorBox error={err} />
      <Section title="Список проектов">
        {items.length === 0 ? <div className="text-sm text-graphite-400">Проектов пока нет.</div> : (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Проект</th><th>Система координат</th><th>Описание</th></tr></thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td><Link className="text-teal-400 hover:underline" to={`/projects/${p.id}`}>{p.name}</Link></td>
                    <td>{p.crs}</td>
                    <td className="text-graphite-400">{p.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      {canEdit && (
        <Section title="Новый проект">
          <form onSubmit={create} className="grid gap-3 sm:grid-cols-3">
            <div><label className="label">Название</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label className="label">Система координат</label><input className="input" value={crs} onChange={(e) => setCrs(e.target.value)} /></div>
            <div className="flex items-end"><button className="btn btn-primary" disabled={!name}>Создать</button></div>
          </form>
        </Section>
      )}
    </div>
  );
}
