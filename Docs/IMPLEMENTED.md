# Chat-UI — текущий статус реализации

## Архитектура

```
React + Vite (JS) ──HTTP──> FastAPI ──HTTP──> Ollama / OpenAI / LMStudio
                                               ──HTTP──> ChromaDB
```

- **backend/** — FastAPI, единый прокси для чата и эмбеддингов
- **frontend/** — React + Vite (JS, CSS dark theme)

## Backend — реализовано

### Провайдеры
- Ollama, OpenAI-совместимые, LMStudio (нативный) — переключение в рантайме
- `PUT /api/provider` — смена провайдера, `PUT /api/provider/config` — обновление параметров
- `GET /api/provider/status` — онлайн + список моделей
- Конфигурация через `.env` + `config.py` с `python-dotenv`

### Чат
- `POST /api/chat` — полный ответ, `POST /api/chat/stream` — SSE
- Параметры: temperature, max_tokens, top_p, reasoning on/off
- Разделение `<think>...</think>` на мышление и ответ (серверная сторона)
- Сообщения с ролью `system` вставляются в начало списка

### RAG / коллекции
- ChromaDB: список, создание, удаление коллекций
- Загрузка PDF/TXT/DOCX — извлечение текста (pymupdf, python-docx), чанкинг
- Режим RAG: перед отправкой к LLM поиск + добавление контекста в messages
- Источники возвращаются в ответе (sources)

### Workspace
- CRUD через `/api/workspaces` — **in-memory** (без SQLite)

### Прочее
- CORS (все origins)
- Загрузка `.env` из `backend/.env`
- LMStudio provider обрезает `/v1` из base_url для корректного пути `/api/v1/...`
- stream парсит `<think>` теги и LMSTATS от LMStudio

## Frontend — реализовано

### Страницы
- **Чат** (`pages/ChatPage.jsx`) — основная
- **Коллекции** (`pages/CollectionsPage.jsx`) — управление

### Чат
- Markdown-рендеринг (react-markdown + remark-gfm)
- Потоковый вывод с индикатором печати
- Блок размышлений (сворачиваемый details)
- Источники под ответом (сворачиваемые)
- Метрики: время, токены, tokens/sec, TTFT
- HTML-теги из ответа удаляются (stripHtml)
- `>` артефакты из reasoning удаляются (cleanThinking)

### Настройки
- Боковая панель слева (300px): провайдер, модель, статус
- Панель настроек (справа, выезжает): системный промпт, temperature, max_tokens, top_p, reasoning
- Переключатель режима Чат / Чат+RAG с выбором коллекции
- Новый чат, стоп стриминга

### Провайдеры в UI
- `ollama` — Ollama
- `lmstudio` — LMStudio (Native)
- `openai` — закомментирован в списке

## Не реализовано (отложено)

- SQLite для Workspace (сейчас in-memory)
- Страница Workspace во фронтенде
- Context length (есть в модели, не используется)
- MCP-сервер для ChromaDB
- Drag & drop загрузки документов
- Адаптивность / мобильное меню
