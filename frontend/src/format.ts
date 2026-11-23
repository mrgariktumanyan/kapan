export const fmt = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const ZONE_LABELS: Record<string, string> = {
  roof: "Кровля", floor: "Почва", wall_N: "Стенка С", wall_E: "Стенка В", wall_S: "Стенка Ю", wall_W: "Стенка З",
};

export const CATEGORY_LABELS: Record<string, string> = {
  geological: "A. Геологическая модель", design: "B. Проект камеры", survey: "C. Маркшейдерская съёмка", production: "D. Производственные данные",
};

export const ROLE_LABELS: Record<string, string> = {
  orebody: "Рудное тело (кондиция)", low_grade: "Некондиционная руда", block_model: "Блочная модель",
  stope_design: "Проектный солид камеры", survey_solid: "Солид выработанного пространства", survey_points: "Точки съёмки XYZ",
  production: "Производственные показатели", other: "Прочее",
};

export const ROLE_TITLES: Record<string, string> = {
  admin: "Администратор", planner: "Горный инженер-планировщик", surveyor: "Маркшейдер", geologist: "Геолог", management: "Руководство",
};
