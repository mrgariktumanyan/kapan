import type { Analysis, ReconResult, Zones } from "../api";
import { fmt, ROLE_LABELS, ZONE_LABELS } from "../format";
import { Kpi, Section } from "./ui";

function Row({ label, v, unit, f, r, digits = 1 }: { label: string; v: number | null | undefined; unit: string; f?: string; r: ReconResult; digits?: number }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="num">{fmt(v, digits)}</td>
      <td className="text-graphite-400">{unit}</td>
      <td className="hidden font-mono text-[11px] text-graphite-400 md:table-cell">{f ? r.formulas[f] : ""}</td>
    </tr>
  );
}

function ZoneBars({ zones, color }: { zones: Zones; color: string }) {
  const total = Object.values(zones).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-1.5">
      {Object.entries(zones).map(([k, v]) => (
        <div key={k} className="grid grid-cols-[6rem_1fr_5rem] items-center gap-2 text-xs">
          <span className="text-graphite-400">{ZONE_LABELS[k] ?? k}</span>
          <div className="h-2 rounded bg-graphite-800"><div className="h-2 rounded" style={{ width: `${total ? (v / total) * 100 : 0}%`, background: color }} /></div>
          <span className="num">{fmt(v)} м³</span>
        </div>
      ))}
    </div>
  );
}

export default function ResultsView({ job }: { job: Analysis }) {
  const r = job.result;
  if (!r) return null;
  const ol = r.ore_loss, dl = r.dilution, cf = r.conformance;
  const metals = Object.entries(ol.metal_loss ?? {});
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Ore Loss (геом.)" value={fmt(ol.ore_loss_pct)} unit="%" hint={r.formulas.ore_loss_pct} />
        <Kpi label="Dilution (геом., объём)" value={fmt(dl.dilution_volume_pct)} unit="%" hint={r.formulas.dilution_volume_pct} />
        <Kpi label="Тоннаж потерь" value={fmt(ol.T_loss, 0)} unit="т" hint={r.formulas.T_loss} />
        <Kpi label="Совпадение план-факт" value={fmt(cf.conformance_pct)} unit="%" hint="Volume(S ∩ D) / Volume(D)" />
      </div>

      {r.warnings.length > 0 && (
        <div className="rounded-md border border-yellow-800 bg-yellow-950/40 px-3 py-2 text-sm text-yellow-200">
          {r.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Ore Loss — геометрические потери">
          <table className="tbl">
            <tbody>
              <Row r={r} label="Плановый объём руды" v={ol.V_plan_ore} unit="м³" f="V_plan_ore" />
              <Row r={r} label="Извлечённая плановая руда" v={ol.V_extracted_ore} unit="м³" f="V_extracted_ore" />
              <Row r={r} label="Объём потерь" v={ol.V_loss} unit="м³" f="V_loss" />
              <Row r={r} label="Потери" v={ol.ore_loss_pct} unit="%" f="ore_loss_pct" />
              <Row r={r} label="Тоннаж плановой руды" v={ol.T_plan_ore} unit="т" />
              <Row r={r} label="Тоннаж потерь" v={ol.T_loss} unit="т" f="T_loss" />
              <Row r={r} label="Руда, добытая вне проекта" v={ol.V_unplanned_ore_extracted} unit="м³" />
              {metals.map(([e, v]) => <Row key={e} r={r} label={`Потери металла ${e}`} v={v} unit={e === "AU" || e === "AG" ? "кг" : "т"} f="M_loss" digits={3} />)}
            </tbody>
          </table>
          <div className="mt-4"><div className="label">Потери по зонам камеры</div><ZoneBars zones={ol.by_zone} color="#ef4444" /></div>
        </Section>

        <Section title="Dilution — геометрическое разубоживание">
          <table className="tbl">
            <tbody>
              <Row r={r} label="Фактическая выемка" v={dl.V_actual} unit="м³" f="V_actual" />
              <Row r={r} label="Руда в выемке" v={dl.V_ore} unit="м³" f="V_ore_in_survey" />
              <Row r={r} label="Некондиционная руда" v={dl.V_low_grade} unit="м³" f="V_low_grade" />
              <Row r={r} label="Пустая порода" v={dl.V_waste} unit="м³" f="V_waste" />
              <Row r={r} label="Не определено" v={dl.V_undefined} unit="м³" f="V_undefined" />
              <Row r={r} label="Разубоживание (объём)" v={dl.dilution_volume_pct} unit="%" f="dilution_volume_pct" />
              <Row r={r} label="Разубоживание (тоннаж)" v={dl.dilution_tonnage_pct} unit="%" f="dilution_tonnage_pct" />
              <Row r={r} label="Planned dilution (проект)" v={dl.planned_dilution_design_pct} unit="%" f="planned_dilution_design_pct" />
              <Row r={r} label="Planned dilution (факт)" v={dl.planned_dilution_pct} unit="%" f="planned_dilution_pct" />
              <Row r={r} label="Unplanned dilution" v={dl.unplanned_dilution_pct} unit="%" f="unplanned_dilution_pct" />
              <Row r={r} label="Total dilution" v={dl.total_dilution_pct} unit="%" f="total_dilution_pct" />
            </tbody>
          </table>
          <div className="mt-4"><div className="label">Пустая порода по зонам</div><ZoneBars zones={dl.by_zone} color="#f97316" /></div>
        </Section>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Соответствие контуру (проект vs съёмка)">
          <table className="tbl">
            <tbody>
              <Row r={r} label="Объём проекта" v={cf.V_design} unit="м³" />
              <Row r={r} label="Объём по съёмке" v={cf.V_survey} unit="м³" />
              <Row r={r} label="Совпадение" v={cf.V_conformance} unit="м³" f="V_conformance" />
              <Row r={r} label="Перебор" v={cf.V_overbreak} unit="м³" f="V_overbreak" />
              <Row r={r} label="Недобор" v={cf.V_underbreak} unit="м³" f="V_underbreak" />
            </tbody>
          </table>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div><div className="label">Перебор по зонам</div><ZoneBars zones={cf.overbreak_by_zone} color="#f97316" /></div>
            <div><div className="label">Недобор по зонам</div><ZoneBars zones={cf.underbreak_by_zone} color="#ef4444" /></div>
          </div>
        </Section>

        <Section title="Участки потерь">
          {ol.areas.length === 0 ? <div className="text-sm text-graphite-400">Потерь нет.</div> : (
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead><tr><th>#</th><th>Зона</th><th className="num">Объём, м³</th><th className="num">Центр X / Y / Z</th></tr></thead>
                <tbody>
                  {ol.areas.slice(0, 20).map((a) => (
                    <tr key={a.id}>
                      <td>{a.id}</td><td>{ZONE_LABELS[a.dominant_zone]}</td><td className="num">{fmt(a.volume_m3)}</td>
                      <td className="num whitespace-nowrap">{a.centroid.map((c) => fmt(c, 1)).join(" / ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      <Section title="Исходные данные и воспроизводимость">
        <table className="tbl">
          <thead><tr><th>Модель</th><th>Файл</th><th className="num">Версия</th><th>sha256</th></tr></thead>
          <tbody>
            {Object.entries(job.inputs).map(([role, i]) => (
              <tr key={role}><td>{ROLE_LABELS[role] ?? role}</td><td>{i.name}</td><td className="num">v{i.version}</td><td className="font-mono text-[11px] text-graphite-400">{i.sha256.slice(0, 16)}…</td></tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 text-xs text-graphite-400">
          Ядро расчёта v{r.engine_version}. Невязка балансов: потери {fmt(r.checks.loss_balance_m3, 4)} м³, выемка {fmt(r.checks.survey_balance_m3, 4)} м³.
          Геометрические показатели — оценка по пространственным моделям, не прямое измерение добытого тоннажа.
        </div>
      </Section>
    </div>
  );
}
