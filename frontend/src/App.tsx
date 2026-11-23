import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { ROLE_TITLES } from "./format";
import LoginPage from "./pages/LoginPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectPage from "./pages/ProjectPage";
import StopePage from "./pages/StopePage";

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded px-3 py-1.5 text-sm ${isActive ? "bg-graphite-800 text-white" : "text-graphite-400 hover:text-graphite-200"}`;
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-graphite-800 bg-graphite-900 p-4 md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <div className="mb-6">
          <div className="text-sm font-semibold tracking-wide text-white">Reconciliation</div>
          <div className="text-xs text-graphite-400">Kapan MPC</div>
        </div>
        <nav className="space-y-1">
          <NavLink to="/projects" className={link}>Проекты и камеры</NavLink>
          <span className="block px-3 py-1.5 text-sm text-graphite-600" title="Этап 4">Dashboard</span>
          <span className="block px-3 py-1.5 text-sm text-graphite-600" title="Этап 2">3D Viewer</span>
          <span className="block px-3 py-1.5 text-sm text-graphite-600" title="Этап 5">AI Analyst</span>
          <span className="block px-3 py-1.5 text-sm text-graphite-600" title="Этап 5">Отчёты</span>
        </nav>
        <div className="mt-8 border-t border-graphite-800 pt-4 text-xs text-graphite-400">
          <div className="text-graphite-200">{user?.full_name || user?.username}</div>
          <div>{user && ROLE_TITLES[user.role]}</div>
          <button className="mt-2 text-teal-400 hover:underline" onClick={logout}>Выйти</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-6 text-graphite-400">Загрузка…</div>;
  if (!user)
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  return (
    <Shell>
      <Routes>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
        <Route path="/stopes/:stopeId" element={<StopePage />} />
        <Route path="*" element={<Navigate to="/projects" replace />} />
      </Routes>
    </Shell>
  );
}
