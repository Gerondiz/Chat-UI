# Актуальные проблемы

## RESOLVED

### ✓ 1. Thinking-теги: конфликт форматов между провайдерами, бэкендом и фронтендом

**Статус:** Исправлено

**Файлы:** `backend/providers/ollama.py`, `backend/main.py`

**Что было:** Провайдеры использовали разные форматы тегов думания, бэкенд и фронтенд искали разные паттерны. Thinking никогда не отделялся от контента в стриминге.

**Что сделано:**
- Ollama `chat_stream()` теперь отдаёт каждый thinking-токен отдельно (не накапливает), обёрнутый в `<think>`/`</think>` маркеры
- `_extract_thinking()` использует regex `<think[\s\S]*?</think>` в первую очередь
- Фронтенд парсит `<think>`/`</think>` state machine корректно
- `emit_agent()` стримит `<think>` → слова думания → `</think>` перед контентом

---

### ✓ 2. Ollama `chat_stream()` не читает поле `thinking` из чанков

**Статус:** Исправлено

**Файл:** `backend/providers/ollama.py`

**Что было:** В стриминговом режиме Ollama присылает `thinking` в чанках, но `chat_stream()` читала только `message.content`.

**Что сделано:** `chat_stream()` теперь читает `chunk.get("thinking")` или `msg.get("thinking")`, и если есть думание — отдаёт его как `<think>`... токены прогрессивно, без аккумулирования.

---

### ✓ 3. Метрики токенов: неконсистентная структура `__LMSTATS__`

**Статус:** Исправлено

**Файлы:** `backend/providers/ollama.py`, `backend/providers/openai.py`, `backend/providers/lmstudio.py`, `backend/main.py`, `frontend/src/pages/ChatPage.tsx`

**Что было:** Каждый провайдер отдаёт разный набор полей в `__LMSTATS__`. `lm_tokens_per_sec` есть только у Ollama, но `generate()` всегда устанавливал его (в 0 для OpenAI/LMStudio). Фронтенд через truthy-check `lm_tokens_per_sec ?` падал на вторую ветку при 0.

**Что сделано:**
- `generate()` устанавливает `lm_tokens_per_sec` и `ttft` только когда провайдер их прислал
- Фронтенд проверяет `typeof === 'number'` вместо truthy
- Если провайдер не прислал `lm_tokens_per_sec` — показывается `output_tokens / output_time_sec / tokens_per_sec` из backend-тайминга

---

### ✓ 4. Agent mode: опечатки и путаница форматов

**Статус:** Исправлено

**Файл:** `backend/main.py`

**Что было:** Опечатки в `emit_agent()` (`" thinking"` вместо `"<think"`), несоответствие форматов в `stream_agent()`.

**Что сделано:**
- `_extract_thinking()` полностью переписан: regex на первом месте, хрупкая эвристика " response" отодвинута
- `emit_agent()` использует `_extract_thinking()` корректно
- `asyncio.sleep(0.03)` между словами для ненулевых метрик

---

### ✓ 8. Agent mode: метрики считаются по словам, не по токенам

**Статус:** Исправлено

**Файл:** `backend/main.py`

**Что было:** В `emit_agent()` метрики `time_sec` = 0 (все слова за один чанк), `tokens_per_sec` = 0.

**Что сделано:** `asyncio.sleep(0.03)` между словами — `elapsed > 0`, метрики ненулевые.

---

### ✓ 13. Non-streaming chat в agent mode не разделяет thinking

**Статус:** Исправлено

**Файл:** `backend/main.py`

**Что было:** В агентском режиме при отсутствии контента думание не попадало в ответ.

**Что сделано:** Fallback во всех трёх путях (`generate()`, `pass_through()`, `emit_agent()`):
```python
if not content_only.strip() and thinking_full:
    content_only = thinking_full.replace("<think>", "").replace("</think>", "")
    thinking_full = ""
```

---

## HIGH

### 5. Фронтенд парсит thinking дублирующе (и неверно)

**Файл:** `frontend/src/api.ts:119-181`

**Проблема:** Фронтенд самостоятельно парсит `<think>`/`</think>` во время стриминга (state machine), хотя бэкенд в `done`-событии уже присылает готовые `full` и `thinking` поля.

Парсинг на фронтенде:
- Ищет `<think` → `</think>` (формат 2)
- Провайдеры отдают `<think... response` (формат 1)
- Фронтенд входит в режим thinking на `<think` и никогда не выходит (нет `</think>`)

**Частично исправлено:** Ollama провайдер теперь оборачивает думание в `<think>`/`</think>` маркеры, поэтому фронтенд корректно входит и выходит из thinking-режима. Однако парсинг на фронтенде дублирует серверный — можно было бы полагаться только на `full`/`thinking` из `done`-события.

---

### 6. Отсутствует `.env` — провайдеры работают с дефолтами

**Файл:** `backend/config.py`

**Проблема:** `load_dotenv()` загружает `backend/.env`, которого нет. Есть только `.env.example`. Бэкенд работает с дефолтными значениями `os.getenv()`, которые могут не соответствовать реальной инфраструктуре.

---

### 7. Ollama `chat()` (не-стриминг) всегда использует stream внутри

**Файл:** `backend/providers/ollama.py:72`

**Проблема:** В `chat()` тело запроса содержит `"stream": True`, и парсинг идёт через NDJSON в `_post()`. Это избыточно для не-стримингового вызова — можно было бы отправить `stream: False` и получить обычный JSON.

---

### 9. ChatPage.tsx: `cleanThinking` для русских моделей

**Файл:** `frontend/src/pages/ChatPage.tsx:429, 500`

**Проблема:** `cleanThinking()` использует `text.replace(/^<think\s*/i, '')` — предполагает латинский `<think`. Для моделей, которые могут использовать кириллические теги (или их отсутствие), очистка может не сработать.

---

## MEDIUM

### 10. Нет проверки работающего ChromaDB при старте

**Файл:** `backend/main.py`

**Проблема:** При старте нет проверки, доступна ли ChromaDB. Ошибки RAG проявляются только при первом поиске. Пользователь видит ошибку в рантайме, а не при запуске.

---

### 11. Состояние гонки: `current_provider` и `current_config`

**Файл:** `backend/main.py:39-41`

**Проблема:** `current_provider` и `current_config` — глобальные переменные. Несмотря на `_provider_lock` для endpoint-ов провайдера, запросы на `/api/chat` и `/api/chat/stream` не используют этот лок, и могут прочитать провайдера в момент переключения.

---

### 12. LMStudio: нестандартный API `/api/v1/chat`

**Файл:** `backend/providers/lmstudio.py`

**Проблема:** LMStudio Native API использует нестандартный формат:
- Не `messages`/OpenAI format, а `"input": "System: ...\nUser: ...\nAssistant: ..."`
- Не `max_tokens`, а `max_output_tokens`
- Не `stream: True` в теле, а SSE с кастомными событиями (`reasoning.delta`, `message.delta`, `chat.end`)
- API endpoint — `/api/v1/chat`, а не `/v1/chat/completions`

При переключении с OpenAI-совместимого на Native API у пользователей с LMStudio часто ломается подключение, если указан неверный `base_url`.

---

### 14. Ошибки стриминга не доходят до фронтенда

**Файл:** `frontend/src/api.ts:112-114`

**Проблема:** Если стриминг прерывается середине (обрыв соединения, таймаут прокси), фронтенд получает `done: true` от ReadableStream, но событие `done` так и не приходит. `loading` остаётся `true`, интерфейс застывает. Нет таймаута на стриминг.

---

### 15. `mcp_host.is_ready` не сбрасывается при ошибке

**Файл:** `backend/mcp_host.py`

**Проблема:** Если MCP-сервер упал после того, как стал ready, `is_ready` остаётся `True`. Агентный режим продолжает пытаться вызывать `_run_agent_loop`, который падает с исключением, и падает на fallback chat без уведомления.
