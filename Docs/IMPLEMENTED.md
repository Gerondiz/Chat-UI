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
- Прогрессивный стриминг думания: Ollama отдаёт каждый thinking-токен отдельно, фронтенд показывает блок размышлений по мере поступления
- Сообщения с ролью `system` вставляются в начало списка

### Agent mode
- `POST /api/chat/stream` с `mode: "agent"` — потоковый ответ через SSE
- При отстуствии MCP: pass-through стриминг от провайдера
- При наличии MCP: цикл инструментов (`_run_agent_loop`), затем стриминг финального ответа
- Думание стримится прогрессивно (`<think>` → слова → `</think>`) перед контентом
- Метрики: `time_sec`, `tokens`, `output_time_sec`, `output_tokens`, `tokens_per_sec`

### RAG / коллекции
- ChromaDB: список, создание, удаление коллекций
- Загрузка PDF/TXT/DOCX — извлечение текста (pymupdf, python-docx), чанкинг
- Режим RAG: перед отправкой к LLM поиск + добавление контекста в messages
- Режим Agent+RAG: агент с RAG-контекстом
- Источники возвращаются в ответе (sources)

### Workspace
- CRUD через `/api/workspaces` — **in-memory** (без SQLite)

### Прочее
- CORS (все origins)
- Загрузка `.env` из `backend/.env`
- stream парсит `<think>` теги и `__LMSTATS__` от провайдеров
- `__LMSTATS__`: Ollama присылает `input_tokens`, `output_tokens`, `reasoning_output_tokens`, `tokens_per_second`, `ttft`; OpenAI/LMStudio — только `input_tokens`, `output_tokens`, `reasoning_output_tokens`
- Метрики отображаются в блоке под ответом. Если провайдер прислал `lm_tokens_per_sec` — показывается расширенная статистика (входные токены, размышления, TTFT). Если нет — показывается `output_tokens / output_time_sec / tokens_per_sec` из backend-тайминга.

## Frontend — реализовано

### Страницы
- **Чат** (`pages/ChatPage.jsx`) — основная
- **Коллекции** (`pages/CollectionsPage.jsx`) — управление

### Чат
- Markdown-рендеринг (react-markdown + remark-gfm)
- Потоковый вывод с индикатором печати
- Блок размышлений (сворачиваемый details) — появляется прогрессивно во время стриминга
- Источники под ответом (сворачиваемые)
- Метрики: время, токены, tokens/sec, TTFT, входные токены, размышления
- HTML-теги из ответа удаляются (stripHtml)
- `>` артефакты из reasoning удаляются (cleanThinking)

### Настройки
- Боковая панель слева (300px): провайдер, модель, статус
- Панель настроек (справа, выезжает): системный промпт, temperature, max_tokens, top_p, reasoning
- Переключатель режима Чат / Чат+RAG / Агент с выбором коллекции
- Новый чат, стоп стриминга

### Провайдеры в UI
- `ollama` — Ollama
- `openai` — LMStudio (OpenAI)
- `lmstudio` — LMStudio (Native)

## Не реализовано (отложено)

- SQLite для Workspace (сейчас in-memory)
- Страница Workspace во фронтенде
- Context length (есть в модели, не используется)
- MCP-сервер для ChromaDB
- Drag & drop загрузки документов
- Адаптивность / мобильное меню
