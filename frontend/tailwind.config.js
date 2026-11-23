/** Тёмная графитовая тема (ТЗ п. 10). Цвета слоёв — ТЗ п. 5.2. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: { 950: "#121417", 900: "#181b1f", 850: "#1e2227", 800: "#252a30", 700: "#323840", 600: "#454c56", 400: "#8b939e", 200: "#c9ced5" },
        layer: { design: "#3b82f6", orebody: "#22c55e", survey: "#9ca3af", loss: "#ef4444", dilution: "#f97316", match: "#14b8a6" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"], mono: ["JetBrains Mono", "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
};
