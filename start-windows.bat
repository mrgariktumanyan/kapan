@echo off
chcp 65001 >nul
setlocal
title Reconciliation Kapan MPC
cd /d "%~dp0"

echo ============================================================
echo  Reconciliation Kapan MPC - запуск для тестирования
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Установите Python 3.12 с python.org
  echo          и при установке отметьте "Add python.exe to PATH".
  pause & exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] Node.js не найден. Установите Node.js LTS с nodejs.org
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Создаю окружение Python...
  python -m venv .venv || (pause & exit /b 1)
)
echo [1/3] Устанавливаю библиотеки Python (первый раз 2-5 минут)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r backend\requirements.txt || (pause & exit /b 1)

if not exist "frontend\dist\index.html" (
  echo [2/3] Собираю интерфейс (первый раз 1-2 минуты)...
  pushd frontend
  call npm ci --no-audit --no-fund || (popd & pause & exit /b 1)
  call npm run build || (popd & pause & exit /b 1)
  popd
) else (
  echo [2/3] Интерфейс уже собран. Чтобы пересобрать, удалите папку frontend\dist
)

set KAPAN_DATABASE_URL=sqlite:///%~dp0data\kapan.db
set KAPAN_STORAGE_DIR=%~dp0data\storage
set KAPAN_ADMIN_USERNAME=admin
set KAPAN_ADMIN_PASSWORD=kapan2026
set KAPAN_SECRET_KEY=local-test-only-secret-key-kapan-mpc-2026
if not exist data mkdir data

echo [3/3] Запускаю сервер...
echo.
echo   Откройте в браузере:  http://localhost:8000
echo   Логин: admin    Пароль: kapan2026
echo   Тестовые файлы:       samples\SYN-01
echo   Остановить: закройте это окно или нажмите Ctrl+C
echo.
start "" http://localhost:8000
cd backend
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
