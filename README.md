# Chat-UI

Лёгкая альтернатива Open WebUI — веб-интерфейс для общения с LLM через Ollama, OpenAI-совместимые API (LMStudio, vLLM, LocalAI) с поддержкой RAG.

## Архитектура

```
React + Vite (JS) ──HTTP──> FastAPI ──HTTP──> Ollama / OpenAI / LMStudio
                                               ──HTTP──> ChromaDB
```

- **backend/** — FastAPI (Python 3.11+), прокси для чата и эмбеддингов
- **frontend/** — React + Vite (JS, тёмная тема CSS без Tailwind)

## Быстрый старт

```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env        # настройте под своё окружение
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (в другом терминале)
cd frontend && npm install && npm run dev

# Оба сразу (из корня)
./start.sh
```

Фронтенд: http://localhost:5173 (Vite проксирует `/api/*` → `http://localhost:8000`)  
Бэкенд: http://localhost:8000

## Провайдеры

| Провайдер | Эндпоинт | Переменные `.env` |
|-----------|----------|-------------------|
| Ollama | `http://localhost:11434` | `OLLAMA_BASE_URL` |
| OpenAI (LMStudio) | `http://localhost:1234/v1` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| LMStudio (нативный) | `http://20.0.0.136:1234` | хардкод в `main.py` |

## Возможности

- Переключение провайдера и модели на лету
- Потоковый вывод (SSE) с метриками
- RAG-режим: поиск по документам в ChromaDB
- Системный промпт и параметры модели (temp, top_p, max_tokens)
- Загрузка PDF, TXT, DOCX в коллекции
- Чат с `<think>`-тегами (разделение на размышления и ответ)

## Тестирование

Все тесты требуют запущенных бэкенда и фронтенда:

```bash
./test.sh                    # curl smoke-test
python3 run_and_test.py      # запуск + тест + процессы остаются жить
python3 test_frontend.py     # Playwright E2E (без headless)
python3 test_full.py         # Playwright полный сценарий
```

## Технические заметки

- `.env` загружается из `backend/.env` (не из корня репозитория)
- ChromaDB по умолчанию: `localhost:8001` (в `config.py`), в `.env.example` — `:8000`
- Workspace CRUD — in-memory (SQLite отложен)
- Системный промпт по умолчанию: *«Ты — полезный ассистент. Отвечай на русском языке.»*