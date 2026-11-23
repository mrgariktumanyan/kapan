import { Fragment, useState } from "react";
import type { StoredFile } from "../api";
import { fmt, ROLE_LABELS } from "../format";
import { StatusDot } from "./ui";

export default function FilesTable({ files }: { files: StoredFile[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!files.length) return <div className="text-sm text-graphite-400">Файлы ещё не загружены.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="tbl">
        <thead><tr><th></th><th>Назначение</th><th>Файл</th><th className="num">Версия</th><th className="num">Объём, м³</th><th>Статус</th><th>Загружен</th></tr></thead>
        <tbody>
          {files.map((f) => (
            <Fragment key={f.id}>
              <tr className={`cursor-pointer hover:bg-graphite-850 ${f.is_active ? "" : "opacity-60"}`} onClick={() => setOpen(open === f.id ? null : f.id)}>
                <td><StatusDot level={f.validation_status} /></td>
                <td>{ROLE_LABELS[f.model_role] ?? f.model_role}</td>
                <td className="max-w-[16rem] truncate" title={`sha256: ${f.sha256}`}>{f.original_name}</td>
                <td className="num">v{f.version}</td>
                <td className="num">{fmt(f.summary.volume_m3 as number | undefined)}</td>
                <td>{f.is_active ? "активная" : f.validation_status === "error" ? "отклонён" : "архив"}</td>
                <td className="whitespace-nowrap text-graphite-400">{new Date(f.uploaded_at).toLocaleString("ru-RU")}</td>
              </tr>
              {open === f.id && (
                <tr>
                  <td colSpan={7} className="bg-graphite-850">
                    <ul className="space-y-1 py-1">
                      {f.validation_report.map((c, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs">
                          <span className="mt-1"><StatusDot level={c.level} /></span>
                          <span className={c.level === "error" ? "text-red-300" : c.level === "warning" ? "text-yellow-200" : "text-graphite-200"}>{c.message}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-1 font-mono text-[11px] text-graphite-400">sha256 {f.sha256}</div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
