import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorBox } from "../components/ui";

export default function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try { await login(u, p); nav("/projects"); }
    catch (ex) { setErr((ex as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div>
          <div className="text-lg font-semibold text-white">Reconciliation Kapan MPC</div>
          <div className="text-xs text-graphite-400">Сверка, потери и разубоживание очистных камер</div>
        </div>
        <div><label className="label">Логин</label><input className="input" value={u} onChange={(e) => setU(e.target.value)} autoFocus /></div>
        <div><label className="label">Пароль</label><input className="input" type="password" value={p} onChange={(e) => setP(e.target.value)} /></div>
        <ErrorBox error={err} />
        <button className="btn btn-primary w-full justify-center" disabled={busy || !u || !p}>Войти</button>
      </form>
    </div>
  );
}
