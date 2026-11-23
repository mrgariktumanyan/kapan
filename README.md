# Reconciliation Kapan MPC

Платформа сверки «проект / геология / маркшейдерская съёмка» для подземных очистных камер: геометрические потери (Ore Loss), разубоживание (Dilution), план-факт.

**Состояние: Этап 1** (Core Platform + прототип расчётного ядра). Методология и формулы: [docs/methodology.md](docs/methodology.md).

## Что уже работает

* Авторизация (JWT), роли: администратор, планировщик, маркшейдер, геолог, руководство. Журнал действий.
* Иерархия: проект → рудник/участок → горизонт → камера.
* Импорт с Drag & Drop: STL, OBJ, PLY, DXF (3DFACE / POLYFACE / MESH), CSV/TXT (точки XYZ, блочная модель), XLSX (производство), ZIP с каркасом Datamine (*pt.csv + *tr.csv).
  * Бинарный `.dm` пока не читается напрямую: ридер будет проверен на реальных файлах. До этого — экспорт в DXF/STL/CSV.
  * DWG нужно сохранить как DXF. LAS/LAZ будут на Этапе 2.
* Проверка до расчёта: формат, обязательные поля, замкнутость, неманифолдные рёбра, ориентация, дубли вершин и граней, вырожденные треугольники, перекрытие тел, единицы измерения, совместимость систем координат. Файл с ошибкой в расчёт не попадает, причина показывается.
* Версии: каждая загрузка — новая версия (sha256), старые версии и анализы сохраняются.
* Расчёт Ore Loss / Dilution / соответствия контуру по точным булевым операциям (manifold3d), тоннаж и металл по блочной модели, разбивка по зонам (кровля, почва, стенки) и по высоте, участки потерь с координатами. В результате хранятся формулы, параметры, версия ядра и хеши входных файлов.

## Быстрый запуск на Windows (для тестирования)

1. Установите [Python 3.12](https://www.python.org/downloads/) (отметьте «Add python.exe to PATH») и [Node.js LTS](https://nodejs.org/).
2. Скачайте репозиторий: **Code → Download ZIP**, распакуйте.
3. Дважды щёлкните `start-windows.bat`. Первый запуск займёт 3–7 минут, дальше — секунды.
4. Браузер откроется на http://localhost:8000. Логин `admin`, пароль `kapan2026`.
5. Тестовые файлы: `samples/SYN-01` (ожидаемые результаты — в README там же).

Данные сохраняются в папке `data/`. Удалите её, чтобы начать с чистой базы.

## Запуск для разработки

```bash
# backend
cd backend
pip install -r requirements-dev.txt
KAPAN_ADMIN_PASSWORD=<пароль> KAPAN_SECRET_KEY=<32+ символа> uvicorn app.main:app --reload
pytest                      # 35 тестов

# frontend
cd frontend
npm install
npm run dev                 # http://localhost:5173, /api проксируется на :8000
```

По умолчанию используется SQLite. Для PostgreSQL: `KAPAN_DATABASE_URL=postgresql+psycopg2://user:pass@host/db`.

Тестовая камера: `python backend/scripts/make_synthetic_stope.py out/` создаёт STL и DXF эталонной камеры SYN-01 (ожидаемо: Ore Loss 10 %, Dilution 27,27 %).

## Локальное развёртывание

```bash
KAPAN_SECRET_KEY=... KAPAN_ADMIN_PASSWORD=... docker compose up --build
# http://localhost:8080
```

## Этапы

1. **Core Platform** — этот этап.
2. 3D Engine (Three.js / React Three Fiber, разрезы, слои, PostGIS-индексы).
3. Mining Calculations: план-факт с производственными данными, допуски и статусы.
4. Dashboard и графики.
5. AI Analyst и отчёты PDF/XLSX.
6. Тестирование и развёртывание.
