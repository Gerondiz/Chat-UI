#!/usr/bin/env bash
set -e

echo "=== Chat-UI ==="

# 1. Backend
echo "[1/2] Запуск бэкенда (FastAPI)..."
cd "$(dirname "$0")/backend"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "  Бэкенд запущен (PID: $BACKEND_PID)"

# 2. Frontend
echo "[2/2] Запуск фронтенда (Vite)..."
cd "$(dirname "$0")/frontend"
npm run dev &
FRONTEND_PID=$!
echo "  Фронтенд запущен (PID: $FRONTEND_PID)"

echo ""
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo ""
echo "Для остановки: kill $BACKEND_PID $FRONTEND_PID"
