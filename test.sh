#!/usr/bin/env bash
set -e

echo "=== Chat-UI Test ==="
echo ""

# 1. Backend
echo "[1] Проверка бэкенда..."
if curl -sf http://localhost:8000/api/provider/status > /dev/null 2>&1; then
  echo "  ✅ Бэкенд доступен"
  curl -s http://localhost:8000/api/provider/status | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'     Провайдер: {d[\"name\"]}  ({\"🟢\" if d[\"online\"] else \"🔴\"})')
print(f'     Модель: {d[\"chat_model\"]}')
print(f'     Доступные модели: {d[\"chat_models\"]}')
"
else
  echo "  ❌ Бэкенд НЕ доступен"
fi

echo ""

# 2. Ollama
echo "[2] Проверка Ollama..."
if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "  ✅ Ollama доступен"
  curl -s http://localhost:11434/api/tags | python3 -c "
import sys,json
for m in json.load(sys.stdin).get('models',[]):
  print(f'     • {m[\"name\"]}  ({m[\"details\"][\"parameter_size\"]})')
"
else
  echo "  ❌ Ollama НЕ доступен"
fi

echo ""

# 3. Чат (short query)
echo "[3] Тест чата..."
RESP=$(curl -s --max-time 60 -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Привет! Ответь одним словом."}],"temperature":0.7,"max_tokens":50,"stream":false}')
if echo "$RESP" | python3 -c "import sys,json; json.load(sys.stdin)['content']" 2>/dev/null; then
  echo "  ✅ Чат работает"
  echo "  Ответ: $(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['content'])")"
else
  echo "  ❌ Ошибка чата: $RESP"
fi

echo ""

# 4. Streaming
echo "[4] Тест streaming..."
TOKENS=$(curl -s --max-time 30 -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Скажи Привет"}],"temperature":0.7,"max_tokens":50,"stream":true}' | grep 'data:' | wc -l)
if [ "$TOKENS" -gt 0 ]; then
  echo "  ✅ Streaming работает ($TOKENS токенов)"
else
  echo "  ❌ Streaming не работает"
fi

echo ""

# 5. Frontend
echo "[5] Проверка фронтенда..."
if curl -sf http://localhost:5173 > /dev/null 2>&1; then
  echo "  ✅ Фронтенд доступен (http://localhost:5173)"
else
  echo "  ❌ Фронтенд НЕ доступен"
fi

echo ""
echo "=== Готово ==="
