#!/usr/bin/env bash
# Остановка всех процессов Chat-UI (бэкенд, MCP-сервер, фронтенд).
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Chat-UI: остановка ==="

# 1. Скрипты проекта (start.sh и его потомки)
pkill -f "$ROOT/start.sh" 2>/dev/null
pkill -f "$ROOT/backend/start.sh" 2>/dev/null

# 2. Бэкенд
pkill -f "uvicorn main:app" 2>/dev/null

# 3. MCP-сервер (подпроцесс бэкенда, страховка)
pkill -f "mcp_server/server.py" 2>/dev/null

# 4. Фронтенд: vite и esbuild, запущенные из этого проекта
pkill -f "$ROOT/frontend/node_modules/.bin/vite" 2>/dev/null
pkill -f "$ROOT/frontend/node_modules/@esbuild" 2>/dev/null

sleep 1

# 5. Добиваем по портам. Совпадения по имени процесса недостаточно: uvicorn
#    может остаться жив, и тогда следующий start.sh молча поднимет старую
#    версию кода на занятом порте.
for port in 8000 5173; do
  if ss -ltn 2>/dev/null | grep -q ":$port\b"; then
    fuser -k "${port}/tcp" >/dev/null 2>&1
  fi
done

sleep 1

# 6. Проверка портов
left=""
for port in 8000 5173; do
  if ss -ltn 2>/dev/null | grep -q ":$port\b"; then
    left="$left $port"
  fi
done

if [ -n "$left" ]; then
  echo "  ВНИМАНИЕ: порты всё ещё заняты:$left"
  echo "  Проверь вручную:  ss -ltnp | grep -E ':(8000|5173)'"
  exit 1
fi

echo "  Все процессы остановлены. Порты 8000 и 5173 свободны."
